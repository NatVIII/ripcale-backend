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


#region: resolver
def category_class(name: str) -> str:
    """Return the class `name` belongs to (defaults to `intake` if unlisted)."""
    classes = load_intake().category_definitions
    for class_name, names in classes.items():
        if name in names:
            return class_name
    return DEFAULT_CLASS
#endregion
