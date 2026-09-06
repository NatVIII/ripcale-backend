"""Database engine and schema bootstrap.

`engine` is created once at import and shared by everything (routers, ingest,
stats, debug). `init_db()` is called from `app.main.main()` and
`app.ingest.run()`; it creates the SQLite file (if needed) and the tables.
"""
#region: imports
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings
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


#region: session
def get_session():
    """Yield a Session (dependency-injection style helper)."""
    with Session(engine) as session:
        yield session
#endregion
