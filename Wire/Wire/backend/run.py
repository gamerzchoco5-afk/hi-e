"""Start the Wire backend:  python run.py   (or start.bat on Windows).

Locally it listens on 127.0.0.1:8000. On Render it listens on 0.0.0.0:$PORT.
"""

import os

import uvicorn

on_render = bool(os.environ.get("RENDER"))
host = os.environ.get("HOST", "0.0.0.0" if on_render else "127.0.0.1")
port = int(os.environ.get("PORT", "8000"))
# Behind a proxy (Render) the client address arrives in X-Forwarded-For. Rate
# limits use it, so the proxy must be trusted explicitly. Empty = trust nobody.
proxy = os.environ.get("TRUSTED_PROXY_IPS", "*" if on_render else "")

uvicorn.run(
    "app.main:app",
    host=host,
    port=port,
    proxy_headers=bool(proxy),
    forwarded_allow_ips=proxy or None,
    timeout_keep_alive=5,
    limit_concurrency=100,
    limit_max_requests=20000,
    access_log=False,
)
