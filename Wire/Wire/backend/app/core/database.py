"""Database engines and sessions.

Two Supabase logins are kept apart on purpose (least privilege, unchanged):

* `engine` / `SessionLocal`           -> DATABASE_URL       (wire_main_backend)
* `chat_engine` / `ChatSessionLocal`  -> CHAT_DATABASE_URL  (wire_chat_backend)

For local SQLite development both point at the same file.
"""

import time
import uuid

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


def now():
    return int(time.time())


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


cfg = settings()


def _options(url):
    return (
        {"check_same_thread": False, "timeout": 5}
        if url.startswith("sqlite")
        else {"connect_timeout": 5, "prepare_threshold": None}
    )


def _sqlite_pragmas(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")


def _make_engine(url, pool_size, max_overflow, pool_timeout):
    made = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        connect_args=_options(url),
    )
    if url.startswith("sqlite"):
        event.listen(made, "connect", _sqlite_pragmas)
    return made


engine = _make_engine(cfg.database_url, 5, 2, 5)
SessionLocal = sessionmaker(engine, expire_on_commit=False)

if cfg.chat_url == cfg.database_url:
    chat_engine = engine
else:
    chat_engine = _make_engine(cfg.chat_url, 5, 2, 5)
ChatSessionLocal = sessionmaker(chat_engine, expire_on_commit=False)

rate_engine = _make_engine(cfg.database_url, 2, 0, 2)
RateSessionLocal = sessionmaker(rate_engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db


def get_chat_db():
    with ChatSessionLocal() as db:
        yield db
