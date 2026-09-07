"""Logging configuration.

`setup_logging()` configures the root logger — a console stream plus a rotating
file (`{data_dir}/ripcale.log` by default) shared by every entrypoint; call it
once from each entrypoint's `main()`. Individual modules use
`logging.getLogger(__name__)`.

`read_log_tail()` is the read side for the admin `/debug/logs` page: a
constant-time tail of the last N lines (seek to end, read backwards in blocks —
never slurping the whole file).
"""
#region: imports
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings
#endregion


#region: defaults
LOG_TAIL_LINES = 200  # lines shown by /debug/logs (single source of truth)
#endregion


#region: log path
def log_path() -> Path:
    """Return the resolved log file path.

    Absolute `settings.log_file` is used as-is; relative paths resolve against
    `settings.data_dir`; empty falls back to `{data_dir}/ripcale.log`.
    """
    if settings.log_file:
        p = Path(settings.log_file)
        if p.is_absolute():
            return p
        return Path(settings.data_dir) / p
    return Path(settings.data_dir) / "ripcale.log"
#endregion


#region: tail
def read_log_tail(n: int = LOG_TAIL_LINES) -> str:
    """Return the last `n` lines of the log file (or fewer if shorter).

    Constant-time with respect to file size: seeks to the end and reads
    backwards in blocks until more than `n` newlines are seen (or the start of
    the file is reached), then drops the leading partial line. Returns "" if
    the file is absent/empty.
    """
    path = log_path()
    if not path.exists():
        return ""

    block_size = 8192
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return ""

            chunks: list[bytes] = []
            newlines = 0
            pos = size
            reached_start = False
            while pos > 0:
                read_len = min(block_size, pos)
                pos -= read_len
                f.seek(pos)
                chunk = f.read(read_len)
                chunks.append(chunk)
                newlines += chunk.count(b"\n")
                if pos == 0:
                    reached_start = True
                if newlines > n:
                    break
            data = b"".join(reversed(chunks))
    except OSError:
        return ""

    text = data.decode("utf-8", errors="replace")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not reached_start and lines:
        lines.pop(0)
    return "\n".join(lines[-n:])
#endregion


#region: setup
def setup_logging() -> None:
    """Configure the root logger: INFO console + rotating file (idempotent)."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    # Console stream — only if we don't already have one of our own. Key on the
    # exact type (not isinstance) so RotatingFileHandler (a StreamHandler
    # subclass) and any pre-installed handler don't suppress it.
    if not any(type(h) is logging.StreamHandler for h in root.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)

    # Rotating file — keyed on our handler so repeat calls don't duplicate it.
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            path,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            delay=True,
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
#endregion
