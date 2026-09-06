"""Public (read-only) HTTP app.

Serves the read-only endpoints: `GET /events`, `GET /events/{id}`,
`GET /feed.ics`, `GET /events/{id}/ics`, and `GET /healthz`. No writes, no
secrets. `main()` is called by `python -m app.public` (and is the Docker
`CMD` default); it initializes the DB schema then serves on the public host/port.
"""
#region: imports
from robyn import ALLOW_CORS, Robyn

from app import models  # noqa: F401  (importing registers the SQLModel tables)
from app.config import settings
from app.db import init_db
from app.logging import setup_logging
from app.routers import events as events_router
from app.routers import feeds as feeds_router
#endregion


#region: app + routing
app = Robyn(__file__)

events_router.register(app)   # /events, /events/{id}
feeds_router.register(app)    # /feed.ics, /events/{id}/ics

if settings.cors_origins:
    ALLOW_CORS(app, settings.cors_origins)
#endregion


#region: health
@app.get("/healthz")
async def healthz(request):
    return {"status": "ok", "service": "ripcale", "version": "0.1.0"}
#endregion


#region: entrypoint
def main() -> None:
    setup_logging()
    init_db()
    app.start(host=settings.public_host, port=settings.public_port)


if __name__ == "__main__":
    main()
#endregion
