"""Tests for the dependency audit wrapper (F58.01)."""
#region: imports
from app import audit
#endregion


#region: summary parsing + gating
def test_parse_summary():
    text = (
        "Total 2 packages affected by 2 known vulnerabilities "
        "(1 Critical, 1 High, 0 Medium, 0 Low, 0 Unknown) from 2 ecosystems."
    )
    assert audit.parse_summary(text) == {
        "critical": 1, "high": 1, "medium": 0, "low": 0, "unknown": 0,
    }


def test_parse_summary_no_findings():
    assert audit.parse_summary("No issues found") == {
        "critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0,
    }


def test_gate_off_when_no_threshold():
    assert audit.gate({"critical": 1, "high": 0, "medium": 0, "low": 0, "unknown": 0}, None) is False


def test_gate_fails_on_critical_or_high_at_high_threshold():
    assert audit.gate({"critical": 1, "high": 0, "medium": 0, "low": 0, "unknown": 0}, "high") is True
    assert audit.gate({"critical": 0, "high": 1, "medium": 0, "low": 0, "unknown": 0}, "high") is True


def test_gate_warns_below_threshold():
    counts = {"critical": 0, "high": 0, "medium": 1, "low": 2, "unknown": 3}
    assert audit.gate(counts, "high") is False
    assert audit.gate(counts, "critical") is False
    assert audit.gate(counts, "medium") is True
#endregion


#region: run
class _Proc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch(monkeypatch, proc, which="/usr/local/bin/osv-scanner"):
    monkeypatch.setattr(audit.shutil, "which", lambda _: which)
    monkeypatch.setattr(audit.subprocess, "run", lambda *a, **k: proc)


def test_run_report_only_passes_on_findings(monkeypatch):
    proc = _Proc(1, stdout=(
        "Total 1 package affected by 1 known vulnerability "
        "(1 Critical, 0 High, 0 Medium, 0 Low, 0 Unknown) from 1 ecosystem.\n"
    ))
    _patch(monkeypatch, proc)
    assert audit.run("uv.lock", "osv-scanner.toml", None) == 0


def test_run_gates_on_critical(monkeypatch):
    proc = _Proc(1, stdout=(
        "Total 1 package affected by 1 known vulnerability "
        "(1 Critical, 0 High, 0 Medium, 0 Low, 0 Unknown) from 1 ecosystem.\n"
    ))
    _patch(monkeypatch, proc)
    assert audit.run("uv.lock", "osv-scanner.toml", "high") == 1


def test_run_passes_medium_at_high_threshold(monkeypatch):
    proc = _Proc(1, stdout=(
        "Total 1 package affected by 1 known vulnerability "
        "(0 Critical, 0 High, 1 Medium, 0 Low, 0 Unknown) from 1 ecosystem.\n"
    ))
    _patch(monkeypatch, proc)
    assert audit.run("uv.lock", "osv-scanner.toml", "high") == 0


def test_run_errors_when_scanner_missing(monkeypatch):
    _patch(monkeypatch, _Proc(0), which=None)
    assert audit.run("uv.lock", "osv-scanner.toml", "high") == 2


def test_run_errors_when_scanner_errors(monkeypatch):
    _patch(monkeypatch, _Proc(2, stderr="connection error"))
    assert audit.run("uv.lock", "osv-scanner.toml", "high") == 2


def test_run_allow_errors_downgrades_scanner_error(monkeypatch):
    _patch(monkeypatch, _Proc(2, stderr="connection error"))
    assert audit.run("uv.lock", "osv-scanner.toml", "high", allow_errors=True) == 0


def test_run_allow_errors_still_gates_on_critical(monkeypatch):
    proc = _Proc(1, stdout=(
        "Total 1 package affected by 1 known vulnerability "
        "(1 Critical, 0 High, 0 Medium, 0 Low, 0 Unknown) from 1 ecosystem.\n"
    ))
    _patch(monkeypatch, proc)
    assert audit.run("uv.lock", "osv-scanner.toml", "high", allow_errors=True) == 1


def test_run_fails_when_findings_unclassifiable(monkeypatch):
    proc = _Proc(1, stdout="some drift in output without a summary line\n")
    _patch(monkeypatch, proc)
    assert audit.run("uv.lock", "osv-scanner.toml", "high") == 1
#endregion
