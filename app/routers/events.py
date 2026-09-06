"""Event read API (FullCalendar-compatible JSON).

`register(app)` is called from `app/main.py`. Serves `GET /events` and
`GET /events/{id}` in FullCalendar's `event-parsing` format.
"""
#region: imports
from urllib.parse import unquote_plus

from robyn import Response, jsonify
from sqlmodel import Session

from app.db import engine
from app.serializers import to_fullcalendar
from app.services.events import get_event, query_events, source_names
from app.timeutil import parse_iso_utc
#endregion


#region: helpers
def _error(message: str, status_code: int = 404) -> Response:
    return Response(
        status_code=status_code,
        headers={"Content-Type": "application/json"},
        description=jsonify({"error": message}),
    )


def _int_or(value: str | None, default: int) -> int:
    try:
        return int(value) if value else default
    except ValueError:
        return default


def _unquote(value: str | None) -> str | None:
    if value is None:
        return None
    return unquote_plus(value)
#endregion


#region: routes
def register(app) -> None:
    @app.get("/events")
    def list_events(request):
        q = request.query_params or {}
        start = parse_iso_utc(_unquote(q.get("start", None)))
        end = parse_iso_utc(_unquote(q.get("end", None)))
        category = _unquote(q.get("category", None))
        limit = _int_or(q.get("limit", None), 200)
        with Session(engine) as session:
            events = query_events(session, start, end, category, limit)
            names = source_names(session, events)
            payload = [to_fullcalendar(e, names.get(e.source_id)) for e in events]
        return payload

    @app.get("/events/:id")
    def get_event_handler(request):
        event_id = request.path_params.get("id", None)
        with Session(engine) as session:
            event = get_event(session, event_id)
            if event is None:
                return _error("not found")
            names = source_names(session, [event])
            payload = to_fullcalendar(event, names.get(event.source_id))
        return payload
#endregion
