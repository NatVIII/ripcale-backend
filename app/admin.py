"""Admin (interactive/debug) HTTP app.

Serves the interactive debug + pipeline playground endpoints: `/debug` and
`/debug/pipeline/*` (gather/sieve/decide — the only write surface). Intended to
be bound to loopback only (`admin_host`). `main()` is called by
`python -m app.admin`; it initializes the DB schema then serves on the admin
host/port.
"""
#region: imports
import logging
from pathlib import Path

from robyn import Robyn

from app import models  # noqa: F401  (importing registers the SQLModel tables)
from app.config import settings
from app.db import init_db
from app.logging import setup_logging
from app.routers import api as api_router
from app.routers import approvals as approvals_router
from app.routers import archive as archive_router
from app.routers import auth as auth_router
from app.routers import backup as backup_router
from app.routers import conflicts as conflicts_router
from app.routers import debug as debug_router
from app.routers import event as event_router
from app.routers import images as images_router
from app.routers import images_admin as images_admin_router
from app.routers import ingest as ingest_router
from app.routers import overseer as overseer_router
from app.routers import pipeline as pipeline_router
from app.routers import retag as retag_router
from app.routers import tests as tests_router
from app.routers import wipe as wipe_router
from app.security import in_docker

logger = logging.getLogger(__name__)
#endregion


#region: llm misconfiguration warning (F65)
def _warn_llm_misconfigured() -> None:
    from app.registry import gatherer_decide_before_insert, load_sources

    for cfg in load_sources():
        if not gatherer_decide_before_insert(cfg.gatherer):
            continue
        if not settings.deepseek_key:
            logger.warning("LLM source %r configured but RIPCALE_DEEPSEEK_KEY is not set — posts will queue unresolved", cfg.name)
        elif not settings.llm_enabled:
            logger.warning("LLM source %r configured but llm_enabled is false — posts will queue unresolved", cfg.name)
        break  # one warning is enough
#endregion


#region: startup banner
_BANNER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bannerStart.txt"


def _print_start_banner() -> None:
    """Print the start banner (scripts/bannerStart.txt) if present."""
    try:
        print(_BANNER_PATH.read_text(encoding="utf-8"))
    except OSError:
        pass
#endregion


#region: app + routing
app = Robyn(__file__)

api_router.register(app)       # /api/v1/*
auth_router.register(app)      # /api/v1/auth/*, /debug/login
debug_router.register(app)     # /debug, /debug/*
pipeline_router.register(app)  # /debug/pipeline/*
wipe_router.register(app)      # /debug/wipe
ingest_router.register(app)    # /debug/ingest
tests_router.register(app)     # /debug/tests
retag_router.register(app)     # /debug/retag
archive_router.register(app)   # /debug/archive, /debug/archived
backup_router.register(app)    # /debug/backups (F23)
approvals_router.register(app)  # /debug/approvals (F66)
overseer_router.register(app)   # /debug/overseer (F67)
conflicts_router.register(app)  # /debug/conflicts (F68)
event_router.register(app)     # /debug/event/{id}
images_router.register(app)    # /images/{filename} (image previews on /debug/event)
images_admin_router.register(app)  # /debug/images (orphan prune)
#endregion


#region: entrypoint
def main() -> None:
    _print_start_banner()
    setup_logging()
    init_db()
    from app.services.auth import ensure_admin_user
    from app.services.scheduler import start as start_scheduler
    from app.services.llm_worker import start as start_llm_worker
    from app.services.overseer_worker import start as start_overseer_worker
    from app.services.backup_worker import start as start_backup_worker

    if not settings.admin_password_hash:
        logger.warning("admin_password_hash is not set — no admin user; login is unavailable")
    elif ensure_admin_user():
        logger.info("created admin user %r", settings.admin_username)
    start_scheduler()
    start_llm_worker()
    start_overseer_worker()
    start_backup_worker()
    _warn_llm_misconfigured()
    # Inside Docker the published port DNATs to the container's eth0, so the
    # app must bind 0.0.0.0; the host publish (127.0.0.1:8082) still restricts
    # external reach to loopback.
    host = "0.0.0.0" if in_docker() else settings.admin_host
    app.start(host=host, port=settings.admin_port)


if __name__ == "__main__":
    main()
#endregion
