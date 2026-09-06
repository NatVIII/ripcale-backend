"""Standalone entry point: run the Elfsight gatherer and print its GathererResult.

Usage:
    python -m app.sources.elfsight                    # all elfsight sources
    python -m app.sources.elfsight --url <boot-url> --name <name>
"""
#region: imports
import argparse
import json

from app.registry import load_sources
from app.schema import SourceConfig
from app.sources.elfsight.module import run
#endregion


#region: entry point
def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Elfsight gatherer standalone")
    parser.add_argument("--url", help="Elfsight boot URL")
    parser.add_argument("--name", default="standalone", help="source name (with --url)")
    args = parser.parse_args()

    if args.url:
        sources = [SourceConfig(name=args.name, gatherer="elfsight", url=args.url)]
    else:
        sources = [s for s in load_sources() if s.gatherer == "elfsight"]

    payload = [run(s).model_dump(mode="json") for s in sources]
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
#endregion
