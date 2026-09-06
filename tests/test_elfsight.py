import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import app.sources.elfsight.module as elfsight_module
from app.schema import SourceConfig

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "elfsight_boot.json").read_text())

WIDGET_URL = "https://fake/boot/?w=24ddbed9-c732-4102-abd2-02990fae125b"


def _cfg():
    return SourceConfig(name="Studio Two Three", module="elfsight", url=WIDGET_URL)


def test_elfsight_run(monkeypatch):
    monkeypatch.setattr(elfsight_module, "fetch_json", lambda url: FIXTURE)

    result = elfsight_module.run(_cfg())

    assert result.source.name == "Studio Two Three"
    assert len(result.events) == 3

    e = result.events[0]
    assert e.uid == "70e8fcb0-92de-476f-81ec-49d21da955a3"
    assert e.title == "Steel Magnolias Screening benefitting Oakwood Arts"
    assert e.timezone == "America/New_York"
    assert e.categories == ["Film Screenings"]
    assert e.location == "Studio Two Three"
    assert e.images and e.images[0].url.startswith("https://files.elfsightcdn.com")
    assert e.url is not None and "eventbrite.com" in e.url

    expected = (
        datetime(2026, 8, 29, 19, 0, tzinfo=ZoneInfo("America/New_York"))
        .astimezone(ZoneInfo("UTC"))
        .replace(tzinfo=None)
    )
    assert e.start_at == expected
    assert e.start_at.tzinfo is None


def test_elfsight_resolves_types_and_locations(monkeypatch):
    monkeypatch.setattr(elfsight_module, "fetch_json", lambda url: FIXTURE)

    result = elfsight_module.run(_cfg())

    by_title = {e.title: e for e in result.events}
    pigs = by_title["Beautiful Pigs, Forced Resonance, and the Perry Menestres Big Band"]
    assert pigs.categories == ["Community Events"]
    assert pigs.location == "Studio Two Three"
