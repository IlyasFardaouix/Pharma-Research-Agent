"""FastAPI endpoints for a bounded, per-application research runtime."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
import re
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from app.agent.graph import PharmaAgent
from app.config import ROOT_DIR, get_settings
from app.http_limits import AskBodyLimit
from app.models import AnswerResponse, AskRequest, HealthResponse, public_answer
from app.rag.index import CorpusIndex
from app.runtime import Runtime, ServiceUnavailable

logger = logging.getLogger("pharma-agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

FRONTEND = ROOT_DIR / "frontend" / "index.html"


def _consume_late_result(worker: asyncio.Future) -> None:
    # A 504/disconnect can stop awaiting a still-running provider call.
    if not worker.cancelled():
        worker.exception()


async def _wait_for_disconnect(request: Request) -> None:
    while True:
        if await request.is_disconnected():
            return
        await asyncio.sleep(0.25)


def create_app(*, settings=None, corpus_builder=None, agent_factory=None) -> FastAPI:
    """Create an independent app; tests can inject fakes without global patching."""
    build = corpus_builder or CorpusIndex.build
    make_agent = agent_factory or PharmaAgent

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = Runtime(settings if settings is not None else get_settings(), build, make_agent)
        app.state.runtime = runtime
        runtime.start()
        try:
            yield
        finally:
            runtime.shutdown()

    api = FastAPI(title="Pharma Research Agent", version="0.1.0", lifespan=lifespan)
    api.add_middleware(AskBodyLimit)

    @api.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        snap = request.app.state.runtime.snapshot()
        return HealthResponse(
            status=snap.status,
            retriever_ready=snap.retriever_ready,
            corpus_files=snap.corpus_files,
            chunks=snap.chunks,
            llm_configured=snap.llm_configured,
            answer_timeout=snap.answer_timeout,
        )

    @api.post("/ask", response_model=AnswerResponse)
    async def ask(request: Request, body: AskRequest) -> AnswerResponse:
        runtime: Runtime = request.app.state.runtime
        try:
            job = runtime.submit(body.question)
        except ServiceUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None

        worker = asyncio.wrap_future(job.future)
        worker.add_done_callback(_consume_late_result)
        disconnected = asyncio.create_task(_wait_for_disconnect(request))
        try:
            done, _ = await asyncio.wait(
                {worker, disconnected},
                timeout=max(0, job.deadline - time.monotonic()),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if worker in done:
                return public_answer(worker.result())
            job.cancel()
            if disconnected in done:
                raise HTTPException(status_code=499, detail="Client disconnected.")
            logger.warning("Request timed out")
            raise HTTPException(status_code=504, detail="Answer timed out; retry with a narrower question.")
        except asyncio.CancelledError:
            job.cancel()
            if job.future.cancelled():
                raise HTTPException(status_code=503, detail="Service is shutting down.") from None
            raise
        except APITimeoutError:
            raise HTTPException(status_code=504, detail="Upstream LLM timed out.")
        except TimeoutError:
            raise HTTPException(status_code=504, detail="Answer timed out; retry with a narrower question.")
        except RateLimitError:
            raise HTTPException(status_code=503, detail="Upstream LLM rate limited; retry later.")
        except APIConnectionError:
            raise HTTPException(status_code=502, detail="Could not reach the LLM provider.")
        except APIStatusError as exc:
            logger.warning("Upstream error status=%s", getattr(exc, "status_code", "?"))
            body = exc.body if isinstance(exc.body, dict) else {}
            error = body.get("error", body)
            if exc.status_code == 400 and isinstance(error, dict):
                markers = " ".join(str(error.get(k, "")) for k in ("code", "type", "message")).lower()
                if any(marker in markers for marker in (
                    "content_filter", "responsibleaipolicyviolation", "contentpolicyviolationerror"
                )):
                    raise HTTPException(status_code=422,
                                        detail="The configured provider declined this request under its content policy.")
            raise HTTPException(status_code=502, detail="Upstream LLM returned an error.")
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Error answering question (%s).", type(exc).__name__)
            raise HTTPException(status_code=500, detail="Internal error answering the question.")
        finally:
            disconnected.cancel()
            try:
                await disconnected
            except asyncio.CancelledError:
                pass

    @api.get("/")
    async def index() -> FileResponse:
        if FRONTEND.exists():
            return FileResponse(FRONTEND)
        return JSONResponse({"message": "Pharma Research Agent API. POST /ask with a question."})

    @api.get("/sources/{filename}", response_class=Response)
    async def source_document(request: Request, filename: str,
                              sha256: str = Query(pattern=r"^[a-f0-9]{64}$")) -> Response:
        """Expose only immutable corpus documents whose fingerprint was cited."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:md|txt)", filename):
            raise HTTPException(status_code=404, detail="Source not found.")
        cfg = request.app.state.runtime.settings
        directory = Path(getattr(cfg, "corpus_dir", ROOT_DIR / "corpus")).resolve()
        candidate = directory / filename
        # Symlinks are not a corpus-download escape hatch, including in local demos.
        if candidate.is_symlink() or candidate.resolve().parent != directory or not candidate.is_file():
            raise HTTPException(status_code=404, detail="Source not found.")
        content = candidate.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != sha256:
            raise HTTPException(status_code=409, detail="Source changed since this citation was created.")
        return Response(content=content, media_type="text/plain; charset=utf-8", headers={
            "ETag": '"' + digest + '"', "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Cache-Control": "no-cache",
        })

    return api


app = create_app()
