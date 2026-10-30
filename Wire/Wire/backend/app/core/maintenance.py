import asyncio
import logging
from sqlalchemy import delete, select
from ..models.identity import EmailChallenge, RateBucket, Session
from .database import SessionLocal, now

log = logging.getLogger(__name__)


def prune():
    with SessionLocal() as db:
        for model in (RateBucket, Session, EmailChallenge):
            keys = list(model.__table__.primary_key.columns)
            from sqlalchemy import tuple_

            expired = select(*keys).where(model.expires_at < now()).limit(2000)
            db.execute(delete(model).where(tuple_(*keys).in_(expired)))
        db.commit()


async def cleanup_loop():
    while True:
        try:
            await asyncio.to_thread(prune)
        except Exception as error:
            log.warning("Maintenance delayed: %s", type(error).__name__)
        await asyncio.sleep(60)
