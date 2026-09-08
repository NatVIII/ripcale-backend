"""Mass retag — rewrite `Event.categories` across the whole DB.

`retag()` renames or removes one `class:name` category token from every event.
It is a raw DB edit: only `categories` changes (content_hash / updated_at are
untouched), so it is sticky until the source event next changes — pair it with a
config change (symlink/rule) for permanence.
"""
#region: imports
from sqlmodel import Session, select

from app.models import Event
#endregion


#region: helpers
def _replace_token(categories: str, from_cat: str, to_cat: str | None) -> str:
    """Replace/remove one `class:name` token in a comma-joined categories string."""
    if not categories:
        return ""
    tokens = [c for c in categories.split(",") if c]
    new: list[str] = []
    for token in tokens:
        if token == from_cat:
            if to_cat:
                new.append(to_cat)
            # else: dropped (removal)
        else:
            new.append(token)
    return ",".join(sorted(set(new)))
#endregion


#region: retag
def retag(session: Session, from_cat: str, to_cat: str | None = None) -> tuple[int, list]:
    """Rename (or remove, if `to_cat` is None) `from_cat` across all events.

    Does not commit — the caller owns the transaction. Returns
    `(changed_count, preview)` where preview is `[(title, old_categories, new_categories)]`.
    """
    changed = 0
    preview: list[tuple[str, str, str]] = []
    for event in session.exec(select(Event)):
        new_categories = _replace_token(event.categories, from_cat, to_cat)
        if new_categories != event.categories:
            preview.append((event.title, event.categories or "", new_categories))
            event.categories = new_categories
            changed += 1
    return changed, preview
#endregion
