"""ICS feed endpoints (RFC 5545 subscription).

`register(app)` is called from `app/main.py`. Serves `GET /feed.ics`
(optionally `?tag=`-filtered) and `GET /events/{id}/ics` (single event).
"""
#region: imports
from urllib.parse import unquote_plus

from robyn import Response, jsonify
from sqlmodel import Session

from app.db import engine
from app.services.events import get_event, query_events, source_names
from app.services.ics import events_to_ics
#endregion


#region: helpers
def _ics(body: str) -> Response:
    return Response(
        status_code=200,
        headers={"Content-Type": "text/calendar; charset=utf-8"},
        description=body,
    )
#endregion


#region: routes
def register(app) -> None:
    @app.get("/feed.ics")
    def feed(request):
        q = request.query_params or {}
        raw_tag = q.get("tag", None)
        tag = unquote_plus(raw_tag) if raw_tag else None
        with Session(engine) as session:
            events = query_events(session, category=tag, limit=None)
            names = source_names(session, events)
            body = events_to_ics(events, names)
        return _ics(body)

    @app.get("/events/:id/ics")
    def event_ics(request):
        event_id = request.path_params.get("id", None)
        with Session(engine) as session:
            event = get_event(session, event_id)
            if event is None:
                return Response(
                    status_code=404,
                    headers={"Content-Type": "application/json"},
                    description=jsonify({"error": "not found"}),
                )
            names = source_names(session, [event])
            body = events_to_ics([event], names)
        return _ics(body)
#endregion
