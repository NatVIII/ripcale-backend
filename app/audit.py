"""Dependency vulnerability audit (F58.01) — osv-scanner wrapper.

Runs `osv-scanner` over the lockfile with the committed ignore config, prints its
severity-sorted report, and gates on severity: exits 1 only when an un-ignored
vulnerability at/above `--fail-severity` (default high) is found. Medium/low/
unknown are warnings (reported but never blocking).
"""
#region: imports
import argparse
import re
import shutil
import subprocess
import sys
#endregion


#region: severity
_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}

_SUMMARY_LEVELS = ("Critical", "High", "Medium", "Low", "Unknown")


def parse_summary(text: str) -> dict[str, int]:
    """Parse osv-scanner's `(N Critical, N High, ...)` summary into counts."""
    counts: dict[str, int] = {}
    for level in _SUMMARY_LEVELS:
        match = re.search(rf"(\d+) {level}", text, re.IGNORECASE)
        counts[level.lower()] = int(match.group(1)) if match else 0
    return counts


def gate(counts: dict[str, int], fail_severity: str | None) -> bool:
    """Return True when the audit should fail (a finding meets the threshold)."""
    if fail_severity is None:
        return False
    threshold = _SEVERITY_RANK.get(fail_severity.lower(), 4)
    for level, rank in _SEVERITY_RANK.items():
        if rank >= threshold and counts.get(level, 0) > 0:
            return True
    return False
#endregion


#region: run
def run(
    lockfile: str,
    config: str,
    fail_severity: str | None,
    *,
    osv_scanner: str = "osv-scanner",
    allow_errors: bool = False,
) -> int:
    """Run the audit and return a process exit code (0 = pass, 1 = gated, 2 = error)."""
    if shutil.which(osv_scanner) is None:
        print(
            f"error: {osv_scanner!r} not found on PATH "
            "(install osv-scanner, or use scripts/audit.sh)",
            file=sys.stderr,
        )
        return 2

    proc = subprocess.run(
        [osv_scanner, "scan", "source", "-L", lockfile, "--config", config, "--format", "table"],
        capture_output=True,
        text=True,
    )

    sys.stdout.write(proc.stdout or "")
    if proc.stderr:
        sys.stderr.write(proc.stderr)

    if fail_severity is None:
        return 0  # report-only

    if proc.returncode >= 2:
        if allow_errors:
            print(
                f"warning: {osv_scanner} exited {proc.returncode} (e.g. OSV unreachable); "
                "continuing because --allow-scan-errors is set",
                file=sys.stderr,
            )
            return 0
        return 2  # osv-scanner errored (network, missing lockfile, ...)

    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    counts = parse_summary(output)
    if gate(counts, fail_severity):
        return 1

    # Findings exist (rc 1) but the summary couldn't be classified — fail
    # conservatively rather than silently pass.
    if proc.returncode == 1 and sum(counts.values()) == 0:
        return 1

    return 0
#endregion


#region: cli
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Audit dependencies for known vulnerabilities (osv-scanner)")
    parser.add_argument("--lockfile", default="uv.lock")
    parser.add_argument("--config", default="osv-scanner.toml")
    parser.add_argument(
        "--fail-severity",
        default="high",
        help="fail on this severity or higher (critical/high/medium/low); empty = report only",
    )
    parser.add_argument(
        "--allow-scan-errors",
        action="store_true",
        help="treat a scanner error (e.g. OSV unreachable) as a warning instead of failing",
    )
    parser.add_argument("--osv-scanner", default="osv-scanner")
    args = parser.parse_args(argv)

    raise SystemExit(
        run(
            args.lockfile,
            args.config,
            args.fail_severity or None,
            osv_scanner=args.osv_scanner,
            allow_errors=args.allow_scan_errors,
        )
    )


if __name__ == "__main__":
    main()
#endregion
