"""Database engine and schema bootstrap.

`engine` is created once at import and shared by everything (routers, ingest,
stats, debug). `init_db()` is called from `app.main.main()` and
`app.ingest.run()`; it creates the SQLite file (if needed) and the tables.
"""
#region: imports
from pathlib import Path

from sqlalchemy import event, func
from sqlmodel import Session, SQLModel, create_engine, delete, select

from app.config import settings
from app.models import Event, Source
#endregion


#region: engine
def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


engine = create_engine(
    settings.resolved_database_url,
    connect_args={"check_same_thread": False} if _is_sqlite(settings.resolved_database_url) else {},
)


if _is_sqlite(settings.resolved_database_url):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        """Enable WAL (concurrent reads) and foreign-key enforcement."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
#endregion


#region: bootstrap
def init_db() -> None:
    """Create the DB file + tables (idempotent)."""
    if _is_sqlite(settings.resolved_database_url):
        db_path = settings.resolved_database_url.removeprefix("sqlite:///")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
#endregion


#region: wipe
def wipe_db() -> tuple[int, int]:
    """Delete every Event and Source row, leaving the schema intact.

    Returns `(events_deleted, sources_deleted)`. Events are deleted before
    sources so foreign-key enforcement doesn't block the source removal.
    """
    with Session(engine) as session:
        events = session.exec(select(func.count()).select_from(Event)).one()
        sources = session.exec(select(func.count()).select_from(Source)).one()
        session.exec(delete(Event))
        session.exec(delete(Source))
        session.commit()
    return events, sources
#endregion


#region: session
def get_session():
    """Yield a Session (dependency-injection style helper)."""
    with Session(engine) as session:
        yield session
#endregion
