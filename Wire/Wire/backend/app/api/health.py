"""Liveness and readiness probes (used by Render)."""

from fastapi import APIRouter
from sqlalchemy import text

from .deps import ChatDb, Db

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Db, chat_db: ChatDb):
    db.execute(text("SELECT 1"))
    chat_db.execute(text("SELECT 1"))
    return {"status": "ready"}
