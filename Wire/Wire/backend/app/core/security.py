import hashlib
import time
from fastapi import HTTPException
from .config import settings


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RateLimiter:
    def check(self, key: str, cap: int, seconds: int):
        if not settings().rate_limits_enabled:
            return
        from .database import RateSessionLocal
        from ..models.identity import RateBucket
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        stamp = int(time.time())
        with RateSessionLocal() as db:
            insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
            statement = insert(RateBucket).values(
                key=digest(key),
                bucket=stamp // seconds,
                count=1,
                expires_at=stamp + seconds * 2,
            )
            statement = statement.on_conflict_do_update(
                index_elements=["key", "bucket"],
                set_={"count": RateBucket.count + 1},
                where=RateBucket.count < cap,
            ).returning(RateBucket.count)
            allowed = db.scalar(statement) is not None
            db.commit()
        if not allowed:
            retry = seconds - stamp % seconds
            raise HTTPException(
                429,
                "Too many requests. Try again later.",
                headers={"Retry-After": str(retry)},
            )


limiter = RateLimiter()
