"""Category classification + resolution helpers.

Categories are `class:name` strings — the class is a fundamental part of the
category identity, not a lookup. Classes are fully dynamic (arbitrary strings);
`intake` is the single default class for tags introduced by gatherers. Names and
classes are slugified (`[a-z0-9-]`) at the categorize gate before they reach the
DB, so every category is a clean, unambiguous `class:name` slug.

Read-time: `resolve_event_categories()` applies `category_symlinks`
(`class:name` → `class:name`) and then drops any category whose class is not in
`exposed_classes` (the public "true" categories). The class is already baked
into the stored string; the low-level `resolve_categories()` stays unfiltered so
admin views and tests can see everything.
"""
#region: imports
import re

from app.intake import load as load_intake
#endregion


#region: constants
DEFAULT_CLASS = "intake"  # class for auto-ingested (unlisted) tags
#endregion


#region: slug
def slugify(value: str) -> str:
    """Normalize a name/class to `[a-z0-9-]` (lowercase, spaces→dashes, collapsed)."""
    s = value.lower()
    s = s.replace(" ", "-")
    s = "".join(c for c in s if c.isascii() and (c.isalnum() or c == "-"))
    s = re.sub(r"-+", "-", s)
    return s.strip("-")
#endregion


#region: class
def category_class(name: str) -> str:
    """Return the class `name` belongs to (defaults to `intake` if unlisted)."""
    name = slugify(name)
    classes = load_intake().category_definitions
    for class_name, names in classes.items():
        if name in names:
            return slugify(class_name)
    return DEFAULT_CLASS


def qualify(name: str) -> str:
    """Return the full `class:name` identity for a raw name."""
    slug = slugify(name)
    return f"{category_class(slug)}:{slug}"
#endregion


#region: exposure
_exposed_cache: dict = {"key": None, "data": None}


def exposed_classes() -> frozenset[str]:
    """The slugified classes whose categories are publicly exposed (the "true" ones)."""
    intake = load_intake()
    if _exposed_cache["key"] is not id(intake):
        _exposed_cache["key"] = id(intake)
        _exposed_cache["data"] = frozenset(slugify(c) for c in intake.exposed_classes if slugify(c))
    return _exposed_cache["data"]


def _is_exposed(category: str) -> bool:
    """True when `class:name` belongs to an exposed class."""
    return category.split(":", 1)[0] in exposed_classes()


def expose(categories: list[str]) -> list[str]:
    """Keep only the exposed ("true") categories; dedupe + sort."""
    return sorted({c for c in categories if _is_exposed(c)})
#endregion


#region: symlinks
def resolve_categories(categories: list[str], links: dict[str, str] | None = None) -> list[str]:
    """Map each `class:name` via `category_symlinks` (else pass through); dedupe + sort."""
    if links is None:
        links = load_intake().category_symlinks
    return sorted({links.get(c, c) for c in categories})


def resolve_event_categories(comma_joined: str | None) -> list[str]:
    """Split a stored comma-joined `class:name` string, resolve symlinks, and
    expose only the "true" categories (dropping internal ones)."""
    if not comma_joined:
        return []
    resolved = resolve_categories([c for c in comma_joined.split(",") if c])
    return expose(resolved)
#endregion
