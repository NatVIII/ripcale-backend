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
from app.models import Approval, DedupCandidate, Event, LoginSession, PendingPost, Source
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
    _migrate()
#endregion


#region: migration
#: Idempotent column additions for existing SQLite DBs — `(table, column, DDL)`.
#: `create_all` already creates these on fresh DBs; this backfills older ones.
#: Add a new column by appending one line here (the `db/migrations.py` home is F74).
MIGRATIONS: list[tuple[str, str, str]] = [
    ("event", "archived_at", "DATETIME"),
    ("event", "archived_reason", "VARCHAR"),
    ("event", "pinned", "BOOLEAN NOT NULL DEFAULT 0"),
    ("event", "placeholder", "BOOLEAN NOT NULL DEFAULT 0"),
    ("source", "llm_context", "VARCHAR"),
    ("source", "probe_state", "VARCHAR"),
    ("pendingpost", "published_at", "DATETIME"),
]

#: Idempotent indexes, re-applied on every start.
MIGRATION_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS ix_event_archived_at ON event (archived_at)",
]


def _table_exists(conn, table: str) -> bool:
    return conn.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).first() is not None


def _migrate() -> None:
    """Apply the declarative `MIGRATIONS` (idempotent; a no-op on fresh DBs)."""
    if not _is_sqlite(settings.resolved_database_url):
        return
    with engine.begin() as conn:
        for table, column, ddl in MIGRATIONS:
            if not _table_exists(conn, table):
                continue
            columns = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if column not in columns:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        for statement in MIGRATION_INDEXES:
            conn.exec_driver_sql(statement)
#endregion


#region: wipe
def wipe_db() -> tuple[int, int]:
    """Delete ingest data (Event/PendingPost/Source) and sessions, leaving the schema intact.

    Returns `(events_deleted, sources_deleted)`. `Event`/`PendingPost` are deleted
    before `Source` so foreign-key enforcement doesn't block the source removal.
    `LoginSession` is cleared (so the admin is logged out), but `ApiToken` and the
    `User` table are **preserved** — wiping events must not break API connectivity.
    """
    with Session(engine) as session:
        events = session.exec(select(func.count()).select_from(Event)).one()
        sources = session.exec(select(func.count()).select_from(Source)).one()
        session.exec(delete(Event))
        session.exec(delete(PendingPost))  # child of Source (F65) — delete before its parent
        session.exec(delete(Source))
        session.exec(delete(LoginSession))
        session.exec(delete(Approval))  # proposals reference sources by name — clear on wipe
        session.exec(delete(DedupCandidate))  # dedupe candidates reference event ids — clear on wipe
        session.commit()
    return events, sources
#endregion


#region: session
def get_session():
    """Yield a Session (dependency-injection style helper)."""
    with Session(engine) as session:
        yield session
#endregion
