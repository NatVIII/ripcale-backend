"""Standalone entry point for the Instagram (HikerAPI) gatherer.

Fetches an account's recent posts and prints the resulting GathererResult.
`--save-raw` / `--fixture` support offline verification; `--verify` sanity-checks
the response shape against what the gatherer expects.

Usage:
    python -m app.gatherers.hikerapi                    # all `hikerapi` sources
    python -m app.gatherers.hikerapi --url <profile>    # one account
    python -m app.gatherers.hikerapi --save-raw <dir>   # save full raw responses (diagnosis)
    python -m app.gatherers.hikerapi --fixture <file>   # replay cached JSON (offline)
    python -m app.gatherers.hikerapi --verify           # sanity-check the response shape
"""
#region: imports
import argparse
import json
from pathlib import Path

from app.registry import load_sources
from app.schema import GathererResult, SourceConfig

from app.gatherers.hikerapi.gatherer import (
    _media_list,
    fetch_medias,
    fetch_raw,
    to_event,
    verify,
)
#endregion


#region: helpers
def _print_verify(user, medias) -> None:
    warnings = verify(user, medias)
    if warnings:
        print(f"verify: {len(warnings)} warning(s):")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("verify: OK — response shapes look right")
    print()


def _write_raw(directory: str, captured: list[dict]) -> None:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(
        json.dumps([{"url": c["url"], "status": c["status"]} for c in captured], indent=2)
    )
    (path / "headers.json").write_text(
        json.dumps([{"url": c["url"], "headers": c["headers"]} for c in captured], indent=2)
    )
    for c in captured:
        if "user/by/username" in c["url"]:
            (path / "user.json").write_text(json.dumps(c["body"], indent=2))
        elif "user/medias" in c["url"]:
            (path / "medias.json").write_text(json.dumps(c["body"], indent=2))
    print(f"saved raw responses to {path}/")


def _sources(args) -> list[SourceConfig]:
    if args.url:
        return [SourceConfig(name=args.name, gatherer="hikerapi", url=args.url)]
    return [s for s in load_sources() if s.gatherer == "hikerapi"]
#endregion


#region: entry point
def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Instagram (HikerAPI) gatherer standalone")
    parser.add_argument("--url", help="Instagram profile URL (or bare username)")
    parser.add_argument("--name", default="standalone", help="source name (with --url)")
    parser.add_argument("--fixture", help="replay a cached media JSON file (offline)")
    parser.add_argument("--save-raw", help="save the full raw responses to this directory")
    parser.add_argument("--verify", action="store_true", help="sanity-check the response shape")
    args = parser.parse_args()

    if args.fixture:
        with open(args.fixture, encoding="utf-8") as fh:
            medias = _media_list(json.load(fh))
        if args.verify:
            _print_verify(None, medias)
        print(json.dumps(
            GathererResult(source=SourceConfig(name="fixture", gatherer="hikerapi", url=""), events=[to_event(m) for m in medias]).model_dump(mode="json"),
            indent=2,
        ))
        return

    for source in _sources(args):
        if args.save_raw:
            captured = fetch_raw(source)
            _write_raw(args.save_raw, captured)
            user = next((c["body"] for c in captured if "user/by/username" in c["url"]), None)
            medias = _media_list(next((c["body"] for c in captured if "user/medias" in c["url"]), []))
        else:
            medias = fetch_medias(source)
            user = None

        if args.verify:
            _print_verify(user, medias)
        print(json.dumps(
            GathererResult(source=source, events=[to_event(m) for m in medias]).model_dump(mode="json"),
            indent=2,
        ))


if __name__ == "__main__":
    main()
#endregion
