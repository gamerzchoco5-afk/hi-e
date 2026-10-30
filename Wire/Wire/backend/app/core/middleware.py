import json
import time
import anyio
from sqlalchemy.exc import SQLAlchemyError
import uuid
from fastapi import HTTPException
from .security import limiter
from .config import settings


class BoundaryMiddleware:
    """Bounded body buffering handles chunked requests as well as Content-Length."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        rid = uuid.uuid4().hex

        async def wrapped(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"cache-control", b"no-store"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"x-request-id", rid.encode()),
                    ]
                )
                if settings().environment == "production":
                    headers.append(
                        (
                            b"strict-transport-security",
                            b"max-age=31536000; includeSubDomains",
                        )
                    )
                message["headers"] = headers
            await send(message)

        try:
            ip = (scope.get("client") or ("unknown",))[0]
            await anyio.to_thread.run_sync(limiter.check, "global:" + ip, 180, 60)
            if scope["method"] in ("POST", "PUT", "PATCH", "DELETE"):
                headers = dict(scope["headers"])
                chunks = []
                size = 0
                started = time.monotonic()
                while True:
                    with anyio.fail_after(max(0.01, 10 - (time.monotonic() - started))):
                        message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    data = message.get("body", b"")
                    size += len(data)
                    cap = 1450000 if scope.get("path") == "/v1/me/avatar" else 65536
                    if size > cap:
                        raise HTTPException(413, "Request is too large")
                    chunks.append(data)
                    if not message.get("more_body", False):
                        break
                if (
                    size
                    and headers.get(b"content-type", b"").split(b";")[0].strip().lower()
                    != b"application/json"
                ):
                    raise HTTPException(415, "Use application/json")
                delivered = False

                async def replay():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {
                            "type": "http.request",
                            "body": b"".join(chunks),
                            "more_body": False,
                        }
                    return await receive()

                return await self.app(scope, replay, wrapped)
            return await self.app(scope, receive, wrapped)
        except (TimeoutError, SQLAlchemyError):
            await wrapped(
                {
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await wrapped(
                {
                    "type": "http.response.body",
                    "body": b'{"detail":"Service temporarily unavailable"}',
                }
            )
        except HTTPException as e:
            body = json.dumps({"detail": e.detail}).encode()
            await wrapped(
                {
                    "type": "http.response.start",
                    "status": e.status_code,
                    "headers": [(b"content-type", b"application/json")]
                    + [
                        (k.lower().encode(), v.encode())
                        for k, v in (e.headers or {}).items()
                    ],
                }
            )
            await wrapped({"type": "http.response.body", "body": body})
