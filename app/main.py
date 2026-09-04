from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from pathlib import Path

from chatkit.server import NonStreamingResult, StreamingResult
from chatkit.store import NotFoundError
from chatkit.types import (
    ChatKitReq,
    ThreadsAddUserMessageReq,
    ThreadsCreateReq,
)
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import TypeAdapter, ValidationError

from .chat import (
    AuthenticationUnavailableError,
    ChatRuntime,
    CodexChatServer,
    RuntimeFactory,
    RuntimeReadiness,
    RuntimeThread,
    RuntimeUnavailableError,
    default_runtime_factory,
)


class _UnavailableRuntime:
    async def start(self) -> RuntimeReadiness:
        return RuntimeReadiness(False, False, "runtime_unavailable")

    async def start_thread(self) -> RuntimeThread:
        raise RuntimeUnavailableError

    async def close(self) -> None:
        return None


def create_app(
    *,
    runtime_factory: RuntimeFactory | None = None,
    repository_root: str | Path | None = None,
    static_dir: str | Path | None = None,
) -> FastAPI:
    """Build the local app; injected runtimes keep tests offline and deterministic."""

    root = (
        Path(repository_root).resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[1]
    )
    web_root = (
        Path(static_dir).resolve()
        if static_dir is not None
        else Path(__file__).resolve().parent / "static"
    )
    factory = runtime_factory or default_runtime_factory

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        runtime: ChatRuntime
        readiness = RuntimeReadiness(False, False, "starting")
        try:
            candidate = factory(root)
            runtime = await candidate if inspect.isawaitable(candidate) else candidate
        except Exception:
            runtime = _UnavailableRuntime()
            readiness = RuntimeReadiness(False, False, "runtime_unavailable")

        server = CodexChatServer(runtime, readiness)
        application.state.chat_server = server
        try:
            if readiness.status == "starting":
                try:
                    readiness = await runtime.start()
                except AuthenticationUnavailableError:
                    readiness = RuntimeReadiness(
                        False, False, "account_unavailable"
                    )
                except Exception:
                    readiness = RuntimeReadiness(
                        False, False, "runtime_unavailable"
                    )
            server.readiness = readiness
            application.state.readiness = readiness
            yield
        finally:
            await server.close()
            application.state.readiness = RuntimeReadiness(
                False, False, "stopped"
            )

    application = FastAPI(
        title="Leadfeeder Local Agent Chat",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.state.readiness = RuntimeReadiness(False, False, "starting")

    @application.get("/", include_in_schema=False)
    async def index() -> Response:
        index_file = web_root / "index.html"
        if not index_file.is_file():
            return Response(
                content="The local chat surface is unavailable.",
                media_type="text/plain",
                status_code=503,
            )
        return FileResponse(index_file)

    @application.get("/health", include_in_schema=False)
    async def health(request: Request) -> JSONResponse:
        server: CodexChatServer = request.app.state.chat_server
        readiness = server.readiness
        return JSONResponse(
            {
                "status": readiness.status,
                "ready": readiness.ready,
                "runtime_initialized": readiness.runtime_initialized,
                "account_ready": readiness.account_ready,
                "chatkit_ready": True,
            }
        )

    @application.post("/chatkit", include_in_schema=False)
    async def chatkit_endpoint(request: Request) -> Response:
        server: CodexChatServer = request.app.state.chat_server
        try:
            body = await request.body()
            parsed = TypeAdapter(ChatKitReq).validate_json(body)
            blocked_types = {
                "attachments.create",
                "attachments.delete",
                "input.transcribe",
                "threads.add_client_tool_output",
                "threads.add_structured_input",
            }
            if parsed.type in blocked_types:
                return JSONResponse(
                    {"error": "unsupported_request"}, status_code=400
                )
            if isinstance(parsed, (ThreadsCreateReq, ThreadsAddUserMessageReq)):
                if parsed.params.input.attachments:
                    return JSONResponse(
                        {"error": "unsupported_request"}, status_code=400
                    )
            result = await server.process(body, context=None)
        except NotFoundError:
            return JSONResponse({"error": "not_found"}, status_code=404)
        except (ValidationError, ValueError, NotImplementedError):
            return JSONResponse({"error": "unsupported_request"}, status_code=400)
        except Exception:
            return JSONResponse({"error": "request_failed"}, status_code=503)

        if isinstance(result, StreamingResult):
            return StreamingResponse(
                result,
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )
        if isinstance(result, NonStreamingResult):
            return Response(content=result.json, media_type="application/json")
        return JSONResponse({"error": "request_failed"}, status_code=503)

    return application


app = create_app()
