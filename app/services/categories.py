"""Category classification + resolution helpers.

Categories are `class:name` strings — the class is a fundamental part of the
category identity, not a lookup. Classes are fully dynamic (arbitrary strings);
`intake` is the single default class for tags introduced by gatherers. Names and
classes are slugified (`[a-z0-9-]`) at the categorize gate before they reach the
DB, so every category is a clean, unambiguous `class:name` slug.

Read-time: `resolve_event_categories()` only applies `category_symlinks`
(`class:name` → `class:name`); the class is already baked into the stored string.
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


#region: symlinks
def resolve_categories(categories: list[str], links: dict[str, str] | None = None) -> list[str]:
    """Map each `class:name` via `category_symlinks` (else pass through); dedupe + sort."""
    if links is None:
        links = load_intake().category_symlinks
    return sorted({links.get(c, c) for c in categories})


def resolve_event_categories(comma_joined: str | None) -> list[str]:
    """Split a stored comma-joined `class:name` string and resolve its symlinks."""
    if not comma_joined:
        return []
    return resolve_categories([c for c in comma_joined.split(",") if c])
#endregion
