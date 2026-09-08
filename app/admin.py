"""Admin (interactive/debug) HTTP app.

Serves the interactive debug + pipeline playground endpoints: `/debug` and
`/debug/pipeline/*` (gather/sieve/decide — the only write surface). Intended to
be bound to loopback only (`admin_host`). `main()` is called by
`python -m app.admin`; it initializes the DB schema then serves on the admin
host/port.
"""
#region: imports
import logging

from robyn import Robyn

from app import models  # noqa: F401  (importing registers the SQLModel tables)
from app.config import settings
from app.db import init_db
from app.logging import setup_logging
from app.routers import api as api_router
from app.routers import debug as debug_router
from app.routers import ingest as ingest_router
from app.routers import pipeline as pipeline_router
from app.routers import retag as retag_router
from app.routers import tests as tests_router
from app.routers import wipe as wipe_router
from app.security import in_docker

logger = logging.getLogger(__name__)
#endregion


#region: app + routing
app = Robyn(__file__)

api_router.register(app)       # /api/v1/*
debug_router.register(app)     # /debug, /debug/*
pipeline_router.register(app)  # /debug/pipeline/*
wipe_router.register(app)      # /debug/wipe
ingest_router.register(app)    # /debug/ingest
tests_router.register(app)     # /debug/tests
retag_router.register(app)     # /debug/retag
#endregion


#region: entrypoint
def main() -> None:
    setup_logging()
    init_db()
    if not settings.api_token:
        logger.warning("api_token is not set — /api/v1/* is disabled")
    # Inside Docker the published port DNATs to the container's eth0, so the
    # app must bind 0.0.0.0; the host publish (127.0.0.1:8082) still restricts
    # external reach to loopback.
    host = "0.0.0.0" if in_docker() else settings.admin_host
    app.start(host=host, port=settings.admin_port)


if __name__ == "__main__":
    main()
#endregion
