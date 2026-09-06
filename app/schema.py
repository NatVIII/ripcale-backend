"""Pydantic data contracts that flow through the pipeline.

These are the "common format" every module massages its source data into, and
the shapes the sieve and decisionmaker exchange:

    SourceConfig -> (module run) -> ModuleResult -> (sieve) -> SieveResult
                                              -> (decisionmaker) -> Event
"""
#region: imports
import json
from datetime import datetime

from pydantic import BaseModel, Field
#endregion


#region: source config
class SourceConfig(BaseModel):
    """One configured source (parsed from `config.yaml`)."""

    name: str
    module: str
    url: str
    is_public: bool = False
    default_categories: list[str] = Field(default_factory=list)
#endregion


#region: image reference
class ImageRef(BaseModel):
    """One image in an event's ordered gallery.

    `url` is the display image (external today, internal once hosting lands);
    `source_url` preserves the original external URL for provenance; `alt` is
    accessibility text. The primary/cover image is `images[0]`.
    """

    url: str
    alt: str | None = None
    source_url: str | None = None
#endregion


#region: scraped event (module output)
class ScrapedEvent(BaseModel):
    """A single normalized event produced by a source module."""

    uid: str | None = None
    title: str
    description: str | None = None
    location: str | None = None
    url: str | None = None
    images: list[ImageRef] = Field(default_factory=list)
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None
    all_day: bool = False
    categories: list[str] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)  # full source payload, kept for debugging
#endregion


#region: module result
class ModuleResult(BaseModel):
    """The output of a module's `run()`."""

    source: SourceConfig
    events: list[ScrapedEvent] = Field(default_factory=list)
#endregion


#region: sieve result
class ClassifiedEvent(BaseModel):
    """An incoming event annotated by the sieve with its id + content hash."""

    id: str
    content_hash: str
    event: ScrapedEvent
    changed_fields: list[str] = Field(default_factory=list)


class SieveResult(BaseModel):
    """The sieve's verdict: what's new, updated, or unchanged vs the DB."""

    source: SourceConfig
    new: list[ClassifiedEvent] = Field(default_factory=list)
    updated: list[ClassifiedEvent] = Field(default_factory=list)
    unchanged: int = 0
#endregion


#region: image (de)serialization (Event.images is a JSON text column)
def dump_images(images: list[ImageRef]) -> str:
    """Serialize an ordered image list to the JSON string stored in Event.images."""
    return json.dumps([img.model_dump() for img in images])


def load_images(value: str | None) -> list[ImageRef]:
    """Parse the JSON string stored in Event.images back into ImageRefs."""
    if not value:
        return []
    try:
        return [ImageRef(**item) for item in json.loads(value)]
    except (json.JSONDecodeError, TypeError):
        return []
#endregion
