"""Standalone entry point: run the ICS gatherer and print its GathererResult.

Usage:
    python -m app.gatherers.ics                  # all `ics` sources
    python -m app.gatherers.ics --url <ics-url> --name <name>
"""
#region: imports
import argparse
import json

from app.gatherers.ics.gatherer import run
from app.registry import load_sources
from app.schema import SourceConfig
#endregion


#region: entry point
def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ICS gatherer standalone")
    parser.add_argument("--url", help="ICS feed URL")
    parser.add_argument("--name", default="standalone", help="source name (with --url)")
    args = parser.parse_args()

    if args.url:
        sources = [SourceConfig(name=args.name, gatherer="ics", url=args.url)]
    else:
        sources = [s for s in load_sources() if s.gatherer == "ics"]

    payload = [run(s).model_dump(mode="json") for s in sources]
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
#endregion
