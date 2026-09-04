"""Deterministic contract tests for the local ChatKit/Codex bridge.

These tests deliberately use only an injected runtime.  They must never start
the real Codex adapter or contact any external service.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ``uv`` runs this intentionally package-less project without adding its root
# to sys.path.  The app is nevertheless a project-root module at runtime.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.chat import (
    AuthenticationUnavailableError,
    CHAT_PRESENTATION_INSTRUCTIONS,
    MODEL,
    REASONING_EFFORT,
    RuntimeReadiness,
    _assistant_item_separator,
)
from app.main import create_app


def chatkit_input(prompt: str) -> dict[str, object]:
    """Build the documented ChatKit user-message payload without attachments."""
    return {
        "type": "threads.create",
        "params": {
            "input": {
                "content": [{"type": "input_text", "text": prompt}],
                "attachments": [],
                "inference_options": {},
            }
        },
    }


def follow_up(thread_id: str, prompt: str) -> dict[str, object]:
    payload = chatkit_input(prompt)
    payload["type"] = "threads.add_user_message"
    payload["params"] = {"thread_id": thread_id, **payload["params"]}
    return payload


def stream_events(response) -> list[dict[str, object]]:
    assert response.headers["content-type"].startswith("text/event-stream")
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def thread_id(events: list[dict[str, object]]) -> str:
    return next(event["thread"]["id"] for event in events if event["type"] == "thread.created")


def assistant_text(events: list[dict[str, object]]) -> str:
    return "".join(
        event["update"]["delta"]
        for event in events
        if event["type"] == "thread.item.updated"
        and event["update"]["type"] == "assistant_message.content_part.text_delta"
    )


@dataclass
class FakeThread:
    number: int
    runtime: "FakeRuntime"
    prompts: list[str] = field(default_factory=list)
    closed: bool = False

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        self.prompts.append(prompt)
        if self.runtime.stream_error is not None:
            raise self.runtime.stream_error
        self.runtime.active_streams += 1
        self.runtime.peak_streams = max(self.runtime.peak_streams, self.runtime.active_streams)
        try:
            for delta in self.runtime.deltas:
                if self.runtime.pause_streams:
                    await self.runtime.stream_gate.wait()
                yield delta
        finally:
            self.runtime.active_streams -= 1

    async def close(self) -> None:
        self.closed = True
        self.runtime.closed_threads.append(self)


@dataclass
class FakeRuntime:
    readiness: RuntimeReadiness = field(
        default_factory=lambda: RuntimeReadiness(
            runtime_initialized=True, account_ready=True, status="ready"
        )
    )
    deltas: tuple[str, ...] = ("Hello", " from fake runtime.")
    start_error: Exception | None = None
    stream_error: Exception | None = None
    pause_streams: bool = False
    stream_gate: asyncio.Event = field(default_factory=asyncio.Event)
    threads: list[FakeThread] = field(default_factory=list)
    closed_threads: list[FakeThread] = field(default_factory=list)
    started: int = 0
    closed: int = 0
    active_streams: int = 0
    peak_streams: int = 0

    async def start(self) -> RuntimeReadiness:
        self.started += 1
        if self.start_error:
            raise self.start_error
        return self.readiness

    async def start_thread(self) -> FakeThread:
        thread = FakeThread(number=len(self.threads) + 1, runtime=self)
        self.threads.append(thread)
        return thread

    async def close(self) -> None:
        self.closed += 1


@pytest.fixture
def runtime() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def app(runtime: FakeRuntime):
    return create_app(runtime_factory=lambda _root: runtime)


def test_health_and_static_chatkit_surface(app) -> None:
    with TestClient(app) as client:
        health = client.get("/health")
        page = client.get("/")

    assert health.json() == {
        "status": "ready",
        "ready": True,
        "runtime_initialized": True,
        "account_ready": True,
        "chatkit_ready": True,
    }
    assert page.status_code == 200
    assert "openai-chatkit" in page.text
    assert 'url: "/chatkit"' in page.text
    assert "domainKey: \"local-dev\"" in page.text
    assert "history:" in page.text
    assert "enabled: false" in page.text
    assert "clientTools" not in page.text
    assert "pointer-events: none" in page.text


def test_chatkit_nonstreaming_thread_lookup_and_streamed_deltas(app, runtime: FakeRuntime) -> None:
    with TestClient(app) as client:
        response = client.post("/chatkit", json=chatkit_input("Say hello"))
        events = stream_events(response)
        identifier = thread_id(events)
        lookup = client.post("/chatkit", json={"type": "threads.get_by_id", "params": {"thread_id": identifier}})

    assert response.status_code == 200
    assert assistant_text(events) == "Hello from fake runtime."
    assert lookup.status_code == 200
    assert lookup.json()["id"] == identifier
    assert runtime.threads[0].prompts == ["Say hello"]


def test_same_chat_thread_continues_one_runtime_thread(app, runtime: FakeRuntime) -> None:
    with TestClient(app) as client:
        first = stream_events(client.post("/chatkit", json=chatkit_input("Remember: lilac")))
        identifier = thread_id(first)
        second = stream_events(client.post("/chatkit", json=follow_up(identifier, "What was it?")))

    assert len(runtime.threads) == 1
    assert runtime.threads[0].prompts == ["Remember: lilac", "What was it?"]
    assert assistant_text(second) == "Hello from fake runtime."


def test_new_chat_starts_a_context_clean_runtime_thread(app, runtime: FakeRuntime) -> None:
    with TestClient(app) as client:
        first = stream_events(client.post("/chatkit", json=chatkit_input("Remember: lilac")))
        second = stream_events(client.post("/chatkit", json=chatkit_input("What was it?")))

    assert thread_id(first) != thread_id(second)
    assert len(runtime.threads) == 2
    assert runtime.threads[0].prompts == ["Remember: lilac"]
    assert runtime.threads[1].prompts == ["What was it?"]


def test_one_turn_at_a_time_per_chatkit_thread(app, runtime: FakeRuntime) -> None:
    # The fake only releases a delta after both requests were scheduled.  The
    # bridge must therefore not enter a second stream on the same thread.
    async def exercise() -> None:
        async with __import__("httpx").AsyncClient(transport=__import__("httpx").ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post("/chatkit", json=chatkit_input("first"))
            identifier = thread_id(stream_events(created))
            runtime.pause_streams = True
            runtime.stream_gate.clear()
            first = asyncio.create_task(client.post("/chatkit", json=follow_up(identifier, "second")))
            await asyncio.sleep(0)
            second = asyncio.create_task(client.post("/chatkit", json=follow_up(identifier, "third")))
            await asyncio.sleep(0)
            assert runtime.peak_streams == 1
            runtime.stream_gate.set()
            await first
            await second

    # TestClient normally owns lifespan; this assertion is about the public
    # endpoint's per-thread lock and requires only the injected fake.
    with TestClient(app):
        asyncio.run(exercise())
    assert runtime.peak_streams == 1


@pytest.mark.parametrize("kind", ["Codex authentication", "Leadfeeder MCP"])
def test_safe_runtime_failures_do_not_leak_error_detail(kind: str) -> None:
    runtime = FakeRuntime(stream_error=RuntimeError(f"{kind}: secret-token-123"))
    app = create_app(runtime_factory=lambda _root: runtime)

    with TestClient(app) as client:
        response = client.post("/chatkit", json=chatkit_input("run"))

    body = response.text.lower()
    assert response.status_code in {200, 503}
    assert "secret-token-123" not in body
    assert "traceback" not in body
    assert "codex" in body


def test_unavailable_runtime_health_is_safe_and_nonsecret() -> None:
    runtime = FakeRuntime(
        readiness=RuntimeReadiness(
            runtime_initialized=True,
            account_ready=False,
            status="account_unavailable",
        )
    )
    app = create_app(runtime_factory=lambda _root: runtime)

    with TestClient(app) as client:
        response = client.get("/health")
        chat = client.post("/chatkit", json=chatkit_input("retry"))

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert "token" not in response.text.lower()
    assert "reconnect" in chat.text.lower()
    assert "restart the local app" in chat.text.lower()


def test_midturn_auth_failure_requires_reconnect_and_restart() -> None:
    runtime = FakeRuntime(stream_error=AuthenticationUnavailableError())
    app = create_app(runtime_factory=lambda _root: runtime)

    with TestClient(app) as client:
        chat = client.post("/chatkit", json=chatkit_input("run"))
        health = client.get("/health")

    assert "reconnect" in chat.text.lower()
    assert "restart the local app" in chat.text.lower()
    assert health.json()["ready"] is False


def test_shutdown_closes_runtime_and_ephemeral_threads(app, runtime: FakeRuntime) -> None:
    with TestClient(app) as client:
        stream_events(client.post("/chatkit", json=chatkit_input("close me")))

    assert runtime.closed == 1
    assert runtime.threads[0].closed is True


def test_read_only_deny_all_ephemeral_configuration_and_prohibited_paths() -> None:
    source = "\n".join(
        (Path("app/main.py").read_text(), Path("app/chat.py").read_text())
    )
    required = (
        "ephemeral=True",
        "Sandbox.read_only",
        "ApprovalMode.deny_all",
        '"model_reasoning_effort": REASONING_EFFORT',
        "developer_instructions=CHAT_PRESENTATION_INSTRUCTIONS",
    )
    forbidden = (
        "Sandbox.workspace_write",
        "Sandbox.full_access",
        "LEADFEEDER_API_KEY",
        "OPENAI_API_KEY",
        "requests.get(",
        "httpx.AsyncClient(",
        "jsonrpc",
        "keyring",
        "Keychain",
        "sqlite",
        "upload",
        "create_web_visits_custom_feed",
    )

    assert all(value in source for value in required)
    assert all(value not in source for value in forbidden)
    assert MODEL == "gpt-5.6-sol"
    assert REASONING_EFFORT == "max"
    assert "Markdown only" in CHAT_PRESENTATION_INSTRUCTIONS
    assert "<details>" in CHAT_PRESENTATION_INSTRUCTIONS


def test_separate_codex_messages_get_markdown_paragraph_boundaries() -> None:
    assert _assistant_item_separator(None, "commentary-1", "", "start") == ""
    assert (
        _assistant_item_separator(
            "commentary-1", "commentary-1", "text", " continues"
        )
        == ""
    )
    assert (
        _assistant_item_separator(
            "commentary-1", "commentary-2", "text", "next"
        )
        == "\n\n"
    )
    assert (
        _assistant_item_separator(
            "commentary-2", "final-answer", "text\n", "final"
        )
        == "\n"
    )
    assert (
        _assistant_item_separator(
            "commentary-2", "final-answer", "text", "\nfinal"
        )
        == "\n"
    )
    assert (
        _assistant_item_separator(
            "commentary-2", "final-answer", "text\n", "\nfinal"
        )
        == ""
    )


def test_fake_runtime_has_no_paid_or_mutation_capability(app, runtime: FakeRuntime) -> None:
    with TestClient(app) as client:
        stream_events(client.post("/chatkit", json=chatkit_input("Analyze visitors")))

    assert runtime.started == 1
    assert len(runtime.threads) == 1
    # The public fake seam has no tool, approval, upload, persistence, or
    # mutation method; all observed work is a single in-memory text stream.
    assert runtime.closed == 1
