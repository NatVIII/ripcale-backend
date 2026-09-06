"""Run the pytest suite from the debug tests page.

Shells out to `python -m pytest` in a subprocess (the exact same entrypoint as
the CLI) so the run is fully isolated from the long-lived server process. Used
by `app/routers/tests.py`.
"""
#region: imports
import subprocess
import sys
from pathlib import Path
#endregion


#region: project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
#endregion


#region: helpers
def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *cmd],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
#endregion


#region: collect
def collect_tests() -> list[str]:
    """Return the collected test node ids (e.g. `tests/test_db.py::test_x`)."""
    proc = _run(["--collect-only", "-q"], timeout=120)
    return [
        line.strip()
        for line in proc.stdout.splitlines()
        if line.strip().startswith("tests/")
    ]
#endregion


#region: run
def run_tests(node_id: str | None = None) -> tuple[int, str]:
    """Run the full suite (or a single `node_id`); return `(returncode, output)`."""
    cmd = ["-q"]
    if node_id:
        cmd.append(node_id)
    proc = _run(cmd, timeout=300)
    return proc.returncode, (proc.stdout + proc.stderr).strip()
#endregion
