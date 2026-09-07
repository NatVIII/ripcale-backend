"""Category classification helpers (read-time, config-backed).

A category has a *class* — a higher-level bucket. Two classes today:
`intake` (auto-ingested, the default) and `external` (promoted to the public
set). Classes live in `intake.yaml` under `category_definitions`, stored class-first:
`{class: [category, ...]}`.
"""
#region: imports
from app.intake import load as load_intake
#endregion


#region: constants
INTAKE = "intake"
EXTERNAL = "external"
DEFAULT_CLASS = INTAKE
#endregion


#region: class
def category_class(name: str) -> str:
    """Return the class `name` belongs to (defaults to `intake` if unlisted)."""
    classes = load_intake().category_definitions
    for class_name, names in classes.items():
        if name in names:
            return class_name
    return DEFAULT_CLASS
#endregion


#region: symlinks
def resolve_categories(categories: list[str], links: dict[str, str] | None = None) -> list[str]:
    """Map each category via `category_symlinks` (else pass through); dedupe + sort."""
    if links is None:
        links = load_intake().category_symlinks
    return sorted({links.get(c, c) for c in categories})


def resolve_event_categories(comma_joined: str | None) -> list[str]:
    """Split a stored comma-joined category string and resolve its symlinks."""
    if not comma_joined:
        return []
    return resolve_categories([c for c in comma_joined.split(",") if c])
#endregion
