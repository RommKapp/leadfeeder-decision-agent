from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from chatkit.server import ChatKitServer
from chatkit.store import NotFoundError, Store
from chatkit.types import (
    Action,
    AssistantMessageContent,
    AssistantMessageContentPartTextDelta,
    AssistantMessageItem,
    Attachment,
    ErrorEvent,
    Page,
    SyncCustomActionResponse,
    ThreadItem,
    ThreadItemAddedEvent,
    ThreadItemDoneEvent,
    ThreadItemUpdatedEvent,
    ThreadMetadata,
    ThreadStreamEvent,
    UserMessageItem,
    WidgetItem,
)
from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, Sandbox
from openai_codex.generated.v2_all import (
    AgentMessageDeltaNotification,
    TurnCompletedNotification,
    TurnStatus,
)


MODEL = "gpt-5.6-sol"
# The pinned SDK enum stops at xhigh; its thread config forwards current values.
REASONING_EFFORT = "max"
CHAT_PRESENTATION_INSTRUCTIONS = """
Presentation rules for this simple ChatKit surface only:
- Keep each progress update to one short paragraph and send it only when the
  work enters a materially different phase.
- Separate paragraphs and sections with blank lines.
- Lead the final answer with the direct outcome and practical next action,
  followed by clear Markdown headings, bullets, and compact tables.
- Put exhaustive ledgers after the summary and shortlist.
- Use Markdown only. Never emit raw HTML, including <details> or <summary>.
Do not weaken requested analysis, safety, completeness, or domain rules merely
to shorten the presentation.
""".strip()

AUTH_MESSAGE = (
    "Codex is not signed in. Reconnect your Codex account in Codex, then "
    "restart the local app."
)
RUNTIME_MESSAGE = (
    "The local Codex runtime is unavailable. Check Codex, then restart the "
    "local app."
)
TURN_MESSAGE = (
    "Codex could not complete this request. Check the Codex and Leadfeeder "
    "connections in Codex, then retry."
)
UNSUPPORTED_MESSAGE = "This local chat accepts text messages only."
ACTION_DENIED_MESSAGE = "This read-only chat cannot perform that action."


class AuthenticationUnavailableError(RuntimeError):
    """The existing Codex account cannot be used by the local runtime."""


class RuntimeUnavailableError(RuntimeError):
    """The managed Codex runtime could not be started or contacted."""


class TurnFailedError(RuntimeError):
    """A Codex turn reached a terminal failure without exposing its payload."""


class TurnInterruptedError(RuntimeError):
    """A Codex turn was interrupted before it completed."""


def _assistant_item_separator(
    previous_item_id: str | None,
    current_item_id: str,
    previous_output_tail: str,
    current_delta: str,
) -> str:
    """Keep separate Codex messages readable inside one ChatKit response."""
    if previous_item_id is None or previous_item_id == current_item_id:
        return ""
    trailing = len(previous_output_tail) - len(previous_output_tail.rstrip("\n"))
    leading = len(current_delta) - len(current_delta.lstrip("\n"))
    return "\n" * max(0, 2 - min(2, trailing + leading))


@dataclass(frozen=True, slots=True)
class RuntimeReadiness:
    runtime_initialized: bool
    account_ready: bool
    status: str

    @property
    def ready(self) -> bool:
        return self.runtime_initialized and self.account_ready


class RuntimeThread(Protocol):
    def stream(self, prompt: str) -> AsyncIterator[str]: ...

    async def close(self) -> None: ...


class ChatRuntime(Protocol):
    async def start(self) -> RuntimeReadiness: ...

    async def start_thread(self) -> RuntimeThread: ...

    async def close(self) -> None: ...


RuntimeFactory = Callable[[Path], ChatRuntime | Awaitable[ChatRuntime]]


def _looks_like_auth_failure(exc: BaseException | str | None) -> bool:
    if exc is None:
        return False
    text = str(exc).casefold()
    markers = (
        "authentication",
        "not logged in",
        "not signed in",
        "login required",
        "unauthorized",
        "refresh token",
    )
    return any(marker in text for marker in markers)


class CodexRuntimeThread:
    """Narrow adapter that exposes assistant text, never raw Codex events."""

    def __init__(self, sdk_thread: Any, repository_root: Path) -> None:
        self._sdk_thread = sdk_thread
        self._repository_root = repository_root
        self._current_turn: Any | None = None
        self._closed = False

    async def close(self) -> None:
        self._closed = True
        turn = self._current_turn
        if turn is not None:
            try:
                await turn.interrupt()
            except Exception:
                pass

    async def _interrupt(self, turn: Any) -> None:
        try:
            await turn.interrupt()
        except Exception:
            pass

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        if self._closed:
            raise RuntimeUnavailableError

        try:
            turn = await self._sdk_thread.turn(
                prompt,
                approval_mode=ApprovalMode.deny_all,
                cwd=str(self._repository_root),
                model=MODEL,
                sandbox=Sandbox.read_only,
            )
        except Exception as exc:
            if _looks_like_auth_failure(exc):
                raise AuthenticationUnavailableError from None
            raise RuntimeUnavailableError from None

        self._current_turn = turn
        completed = False
        last_assistant_item_id: str | None = None
        assistant_output_tail = ""
        try:
            async for event in turn.stream():
                payload = event.payload
                if (
                    event.method == "item/agentMessage/delta"
                    and isinstance(payload, AgentMessageDeltaNotification)
                ):
                    if payload.delta:
                        separator = _assistant_item_separator(
                            last_assistant_item_id,
                            payload.item_id,
                            assistant_output_tail,
                            payload.delta,
                        )
                        if separator:
                            yield separator
                        last_assistant_item_id = payload.item_id
                        yield payload.delta
                        assistant_output_tail = (
                            assistant_output_tail + separator + payload.delta
                        )[-2:]
                    continue

                if (
                    event.method == "turn/completed"
                    and isinstance(payload, TurnCompletedNotification)
                ):
                    completed = True
                    if payload.turn.status == TurnStatus.completed:
                        continue
                    error_text = (
                        payload.turn.error.message if payload.turn.error else None
                    )
                    if _looks_like_auth_failure(error_text):
                        raise AuthenticationUnavailableError
                    if payload.turn.status == TurnStatus.interrupted:
                        raise TurnInterruptedError
                    raise TurnFailedError
        except asyncio.CancelledError:
            await self._interrupt(turn)
            raise
        finally:
            if self._current_turn is turn:
                self._current_turn = None

        if not completed:
            raise TurnFailedError


class CodexRuntime:
    """Lifecycle owner for one SDK process and its ephemeral chat threads."""

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.resolve()
        self._codex: AsyncCodex | None = None
        self._readiness = RuntimeReadiness(False, False, "starting")

    @property
    def readiness(self) -> RuntimeReadiness:
        return self._readiness

    async def start(self) -> RuntimeReadiness:
        codex = AsyncCodex(CodexConfig(cwd=str(self._repository_root)))
        self._codex = codex
        try:
            await codex.__aenter__()
            account = await codex.account(refresh_token=False)
        except Exception as exc:
            await self.close()
            if _looks_like_auth_failure(exc):
                raise AuthenticationUnavailableError from None
            raise RuntimeUnavailableError from None

        account_ready = account.account is not None
        status = "ready" if account_ready else "account_unavailable"
        self._readiness = RuntimeReadiness(True, account_ready, status)
        return self._readiness

    async def start_thread(self) -> RuntimeThread:
        if not self._readiness.ready or self._codex is None:
            raise AuthenticationUnavailableError
        try:
            thread = await self._codex.thread_start(
                approval_mode=ApprovalMode.deny_all,
                config={"model_reasoning_effort": REASONING_EFFORT},
                cwd=str(self._repository_root),
                developer_instructions=CHAT_PRESENTATION_INSTRUCTIONS,
                ephemeral=True,
                model=MODEL,
                sandbox=Sandbox.read_only,
            )
        except Exception as exc:
            if _looks_like_auth_failure(exc):
                raise AuthenticationUnavailableError from None
            raise RuntimeUnavailableError from None
        return CodexRuntimeThread(thread, self._repository_root)

    async def close(self) -> None:
        codex, self._codex = self._codex, None
        self._readiness = RuntimeReadiness(False, False, "stopped")
        if codex is not None:
            try:
                await codex.close()
            except Exception:
                pass


ThreadDeletedCallback = Callable[[str], Awaitable[None]]


class InMemoryChatStore(Store[None]):
    """Process-local ChatKit state; stopping the server discards everything."""

    def __init__(self) -> None:
        self._threads: dict[str, ThreadMetadata] = {}
        self._items: dict[str, list[ThreadItem]] = {}
        self._attachments: dict[str, Attachment] = {}
        self._lock = asyncio.Lock()
        self._thread_deleted: ThreadDeletedCallback | None = None

    def set_thread_deleted_callback(
        self, callback: ThreadDeletedCallback | None
    ) -> None:
        self._thread_deleted = callback

    @staticmethod
    def _clone(value: Any) -> Any:
        return value.model_copy(deep=True)

    @staticmethod
    def _page(
        values: list[Any], after: str | None, limit: int, order: str
    ) -> Page[Any]:
        ordered = list(values)
        if order == "desc":
            ordered.reverse()
        if after is not None:
            cursor = next(
                (index for index, value in enumerate(ordered) if value.id == after),
                None,
            )
            ordered = ordered[cursor + 1 :] if cursor is not None else []
        page_values = ordered[: max(limit, 0)]
        has_more = len(ordered) > len(page_values)
        next_after = page_values[-1].id if has_more and page_values else None
        return Page(data=page_values, has_more=has_more, after=next_after)

    async def load_thread(self, thread_id: str, context: None) -> ThreadMetadata:
        async with self._lock:
            thread = self._threads.get(thread_id)
            if thread is None:
                raise NotFoundError(thread_id)
            return self._clone(thread)

    async def save_thread(self, thread: ThreadMetadata, context: None) -> None:
        async with self._lock:
            self._threads[thread.id] = self._clone(thread)
            self._items.setdefault(thread.id, [])

    async def load_thread_items(
        self,
        thread_id: str,
        after: str | None,
        limit: int,
        order: str,
        context: None,
    ) -> Page[ThreadItem]:
        async with self._lock:
            if thread_id not in self._threads:
                raise NotFoundError(thread_id)
            values = [self._clone(item) for item in self._items[thread_id]]
        return self._page(values, after, limit, order)

    async def save_attachment(self, attachment: Attachment, context: None) -> None:
        async with self._lock:
            self._attachments[attachment.id] = self._clone(attachment)

    async def load_attachment(
        self, attachment_id: str, context: None
    ) -> Attachment:
        async with self._lock:
            attachment = self._attachments.get(attachment_id)
            if attachment is None:
                raise NotFoundError(attachment_id)
            return self._clone(attachment)

    async def delete_attachment(self, attachment_id: str, context: None) -> None:
        async with self._lock:
            self._attachments.pop(attachment_id, None)

    async def load_threads(
        self,
        limit: int,
        after: str | None,
        order: str,
        context: None,
    ) -> Page[ThreadMetadata]:
        async with self._lock:
            threads = sorted(
                (self._clone(thread) for thread in self._threads.values()),
                key=lambda thread: (thread.created_at, thread.id),
            )
        return self._page(threads, after, limit, order)

    async def add_thread_item(
        self, thread_id: str, item: ThreadItem, context: None
    ) -> None:
        async with self._lock:
            if thread_id not in self._threads:
                raise NotFoundError(thread_id)
            items = self._items[thread_id]
            if any(existing.id == item.id for existing in items):
                raise ValueError("duplicate thread item")
            items.append(self._clone(item))

    async def save_item(
        self, thread_id: str, item: ThreadItem, context: None
    ) -> None:
        async with self._lock:
            if thread_id not in self._threads:
                raise NotFoundError(thread_id)
            items = self._items[thread_id]
            for index, existing in enumerate(items):
                if existing.id == item.id:
                    items[index] = self._clone(item)
                    return
            items.append(self._clone(item))

    async def load_item(
        self, thread_id: str, item_id: str, context: None
    ) -> ThreadItem:
        async with self._lock:
            for item in self._items.get(thread_id, []):
                if item.id == item_id:
                    return self._clone(item)
        raise NotFoundError(item_id)

    async def delete_thread(self, thread_id: str, context: None) -> None:
        async with self._lock:
            existed = self._threads.pop(thread_id, None) is not None
            self._items.pop(thread_id, None)
        if existed and self._thread_deleted is not None:
            await self._thread_deleted(thread_id)

    async def delete_thread_item(
        self, thread_id: str, item_id: str, context: None
    ) -> None:
        async with self._lock:
            items = self._items.get(thread_id)
            if items is None:
                raise NotFoundError(thread_id)
            self._items[thread_id] = [item for item in items if item.id != item_id]


@dataclass(slots=True)
class _ActiveThread:
    runtime_thread: RuntimeThread
    turn_lock: asyncio.Lock


class CodexChatServer(ChatKitServer[None]):
    def __init__(
        self,
        runtime: ChatRuntime,
        readiness: RuntimeReadiness,
        store: InMemoryChatStore | None = None,
    ) -> None:
        self.runtime = runtime
        self.readiness = readiness
        self._active_threads: dict[str, _ActiveThread] = {}
        self._mapping_lock = asyncio.Lock()
        memory_store = store or InMemoryChatStore()
        memory_store.set_thread_deleted_callback(self.release_thread)
        super().__init__(memory_store)

    async def _active_thread(self, thread_id: str) -> _ActiveThread:
        async with self._mapping_lock:
            active = self._active_threads.get(thread_id)
            if active is None:
                stale = list(self._active_threads.values())
                self._active_threads.clear()
                for entry in stale:
                    try:
                        await entry.runtime_thread.close()
                    except Exception:
                        pass
                runtime_thread = await self.runtime.start_thread()
                active = _ActiveThread(runtime_thread, asyncio.Lock())
                self._active_threads[thread_id] = active
            return active

    async def release_thread(self, thread_id: str) -> None:
        async with self._mapping_lock:
            active = self._active_threads.pop(thread_id, None)
        if active is not None:
            try:
                await active.runtime_thread.close()
            except Exception:
                pass

    async def close(self) -> None:
        async with self._mapping_lock:
            active = list(self._active_threads.values())
            self._active_threads.clear()
        for entry in active:
            try:
                await entry.runtime_thread.close()
            except Exception:
                pass
        try:
            await self.runtime.close()
        except Exception:
            pass

    @staticmethod
    def _prompt(item: UserMessageItem) -> str:
        return "\n".join(
            content.text.strip()
            for content in item.content
            if getattr(content, "text", "").strip()
        )

    @staticmethod
    def _error(message: str, *, allow_retry: bool) -> ErrorEvent:
        return ErrorEvent(code="custom", message=message, allow_retry=allow_retry)

    async def respond(
        self,
        thread: ThreadMetadata,
        input_user_message: UserMessageItem | None,
        context: None,
    ) -> AsyncIterator[ThreadStreamEvent]:
        if not self.readiness.ready:
            message = (
                AUTH_MESSAGE
                if self.readiness.status == "account_unavailable"
                else RUNTIME_MESSAGE
            )
            yield self._error(message, allow_retry=False)
            return

        if input_user_message is None or input_user_message.attachments:
            yield self._error(UNSUPPORTED_MESSAGE, allow_retry=False)
            return

        prompt = self._prompt(input_user_message)
        if not prompt:
            yield self._error(UNSUPPORTED_MESSAGE, allow_retry=False)
            return

        try:
            active = await self._active_thread(thread.id)
        except AuthenticationUnavailableError:
            self.readiness = RuntimeReadiness(False, False, "account_unavailable")
            yield self._error(AUTH_MESSAGE, allow_retry=False)
            return
        except RuntimeUnavailableError:
            self.readiness = RuntimeReadiness(False, False, "runtime_unavailable")
            yield self._error(RUNTIME_MESSAGE, allow_retry=True)
            return
        except Exception:
            yield self._error(RUNTIME_MESSAGE, allow_retry=True)
            return

        message_id = self.store.generate_item_id("message", thread, context)
        output: list[str] = []
        started = False
        assistant = AssistantMessageItem(
            id=message_id,
            thread_id=thread.id,
            created_at=datetime.now(),
            content=[AssistantMessageContent(text="")],
        )

        try:
            async with active.turn_lock:
                async for delta in active.runtime_thread.stream(prompt):
                    if not delta:
                        continue
                    if not started:
                        yield ThreadItemAddedEvent(item=assistant)
                        started = True
                    output.append(delta)
                    yield ThreadItemUpdatedEvent(
                        item_id=message_id,
                        update=AssistantMessageContentPartTextDelta(
                            content_index=0,
                            delta=delta,
                        ),
                    )
        except asyncio.CancelledError:
            raise
        except AuthenticationUnavailableError:
            self.readiness = RuntimeReadiness(False, False, "account_unavailable")
            await self.release_thread(thread.id)
            if started:
                assistant.content[0].text = "".join(output)
                yield ThreadItemDoneEvent(item=assistant)
            yield self._error(AUTH_MESSAGE, allow_retry=False)
            return
        except TurnInterruptedError:
            if started:
                assistant.content[0].text = "".join(output)
                yield ThreadItemDoneEvent(item=assistant)
            yield self._error("The response was stopped.", allow_retry=True)
            return
        except Exception:
            await self.release_thread(thread.id)
            if started:
                assistant.content[0].text = "".join(output)
                yield ThreadItemDoneEvent(item=assistant)
            yield self._error(TURN_MESSAGE, allow_retry=True)
            return

        if not started:
            yield self._error(TURN_MESSAGE, allow_retry=True)
            return

        assistant.content[0].text = "".join(output)
        yield ThreadItemDoneEvent(item=assistant)

    async def action(
        self,
        thread: ThreadMetadata,
        action: Action[str, Any],
        sender: WidgetItem | None,
        context: None,
    ) -> AsyncIterator[ThreadStreamEvent]:
        yield self._error(ACTION_DENIED_MESSAGE, allow_retry=False)

    async def sync_action(
        self,
        thread: ThreadMetadata,
        action: Action[str, Any],
        sender: WidgetItem | None,
        context: None,
    ) -> SyncCustomActionResponse:
        return SyncCustomActionResponse(updated_item=None)


def default_runtime_factory(repository_root: Path) -> ChatRuntime:
    return CodexRuntime(repository_root)
