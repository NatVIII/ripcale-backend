"""Logging configuration.

`setup_logging()` configures the root logger; call it once from each entrypoint's
`main()`. Individual modules use `logging.getLogger(__name__)`.
"""
#region: imports
import logging
#endregion


def setup_logging() -> None:
    """Configure the root logger with a clear format at INFO level."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
