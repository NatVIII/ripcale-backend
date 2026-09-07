"""Shared helpers for contract-compliance tests.

Not collected by pytest (no `test_` prefix); imported by the per-stage
`tests/test_contract_*.py` modules.
"""
#region: imports
import re
from pathlib import Path
#endregion


#region: paths
DOCS = Path(__file__).resolve().parents[1] / "docs"
#endregion


#region: version
def read_contract_version(doc_name: str) -> int:
    """Read the `Version: N` stamp from a contract doc."""
    text = (DOCS / doc_name).read_text()
    match = re.search(r"^Version:\s*(\d+)\s*$", text, re.MULTILINE)
    assert match is not None, f"{doc_name}: missing `Version:` stamp"
    return int(match.group(1))
#endregion
