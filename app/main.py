from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.config import get_settings
from app.db import dispose_engine, get_session_factory
from app.routers import applications, job_targets, pipeline, profiles, templates, uploads, users
from app.routers import saved_searches, source_boards, versions
from app.services.errors import (
    ConflictError,
    FileTooLargeError,
    KitMissingPiecesError,
    NeedsAnswerProfileError,
    NotFoundError,
    ProseVerificationError,
    UnsupportedFormatError,
)
from app.services.sources.base import SourceError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.redis = Redis.from_url(get_settings().redis_url)
    yield
    await app.state.redis.aclose()
    await dispose_engine()


async def _not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


async def _too_large_handler(request: Request, exc: FileTooLargeError) -> JSONResponse:
    return JSONResponse(status_code=413, content={"detail": str(exc)})


async def _unsupported_format_handler(
    request: Request, exc: UnsupportedFormatError
) -> JSONResponse:
    return JSONResponse(status_code=415, content={"detail": str(exc)})


async def _prose_verification_handler(
    request: Request, exc: ProseVerificationError
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def _kit_missing_handler(request: Request, exc: KitMissingPiecesError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "detail": str(exc),
            "missing_pieces": exc.missing_pieces,
        },
    )


async def _needs_answer_profile_handler(
    request: Request, exc: NeedsAnswerProfileError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": str(exc),
            "answer_profile_field": exc.answer_profile_field,
            "question": exc.question,
        },
    )


async def _source_error_handler(request: Request, exc: SourceError) -> JSONResponse:
    # Raised when validating a source board at creation time (the live fetch
    # 404'd or the feed was unreachable). Reject the registration up front.
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def create_app() -> FastAPI:
    app = FastAPI(title="refit", lifespan=lifespan)
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(users.router)
    app.include_router(profiles.router)
    app.include_router(applications.router)
    app.include_router(uploads.router)
    app.include_router(job_targets.router)
    app.include_router(versions.router)
    app.include_router(templates.router)
    app.include_router(pipeline.router)
    app.include_router(source_boards.router)
    app.include_router(saved_searches.router)
    app.add_exception_handler(NotFoundError, _not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ConflictError, _conflict_handler)  # type: ignore[arg-type]
    app.add_exception_handler(FileTooLargeError, _too_large_handler)  # type: ignore[arg-type]
    app.add_exception_handler(UnsupportedFormatError, _unsupported_format_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ProseVerificationError, _prose_verification_handler)  # type: ignore[arg-type]
    app.add_exception_handler(KitMissingPiecesError, _kit_missing_handler)  # type: ignore[arg-type]
    app.add_exception_handler(NeedsAnswerProfileError, _needs_answer_profile_handler)  # type: ignore[arg-type]
    app.add_exception_handler(SourceError, _source_error_handler)  # type: ignore[arg-type]

    @app.get("/health")
    async def health(request: Request) -> dict[str, str]:
        postgres = "ok"
        try:
            async with get_session_factory()() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            postgres = "unreachable"

        redis_status = "ok"
        try:
            await request.app.state.redis.ping()
        except Exception:
            redis_status = "unreachable"

        overall = "ok" if postgres == "ok" and redis_status == "ok" else "degraded"
        return {"status": overall, "postgres": postgres, "redis": redis_status}

    return app
