"""Wire backend: ONE FastAPI application for accounts, posts, people and chat.

Layout
------
app/core      settings, database engines, rate limiter, request-boundary middleware
app/models    SQLAlchemy tables (identity / social / chat)
app/schemas   request bodies
app/services  response builders and session issuing
app/api       routers: health, auth, account, me, users, posts, chat
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import models  # noqa: F401  (registers every table)
from .api import account, auth, chat, health, me, posts, users
from .core.config import settings
from .core.database import Base, chat_engine, engine
from .core.maintenance import cleanup_loop
from .core.middleware import BoundaryMiddleware

log = logging.getLogger(__name__)
cfg = settings()


@asynccontextmanager
async def lifespan(_):
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
    if cfg.environment == "production" and (
        not cfg.smtp_host or not cfg.smtp_from or len(cfg.email_code_pepper) < 32
    ):
        raise RuntimeError("Production requires SMTP and EMAIL_CODE_PEPPER")
    if engine.dialect.name != "sqlite":
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        if chat_engine is not engine:
            with chat_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
    cleaner = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        cleaner.cancel()
        try:
            await cleaner
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Wire API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if cfg.environment != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if cfg.environment != "production" else None,
)
app.add_middleware(BoundaryMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=cfg.host_list)


@app.exception_handler(RequestValidationError)
async def invalid(_, exc):
    # FastAPI's default errors may echo input, including a supplied password.
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Check your input",
            "errors": [
                {
                    "field": ".".join(str(x) for x in error["loc"]),
                    "message": error["msg"],
                }
                for error in exc.errors()
            ],
        },
    )


@app.exception_handler(Exception)
async def unexpected(_, exc):
    log.error("Unhandled request error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500, content={"detail": "Something went wrong. Try again later."}
    )


for module in (health, auth, me, users, posts, account, chat):
    app.include_router(module.router)
