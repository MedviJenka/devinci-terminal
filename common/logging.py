"""
Structured, colourised logging via structlog — written to `.logs/`, never
to stdout/stderr.

The TUI (`tui.app.DeVinciApp`) owns the terminal for a Textual UI; anything
printed to stdout mid-run corrupts the display. So every log record — from
the TUI, from `main.py`'s headless flow runner, and from library code that
routes through stdlib `logging` — lands only in a timestamped file under
`.logs/`, rendered with the same colourised `ConsoleRenderer` structlog uses
for terminal output. Open the file with a pager that understands ANSI colour
(`less -R`, `bat`, `cat` in most terminals) to see it as intended.
"""

import logging
import structlog
from typing import Optional
from datetime import datetime
from pathlib import Path


__all__ = ["configure_logging", "get_logger"]

_log_file: Optional[Path] = None


def configure_logging(logs_dir: Path | None = None, *, level: int = logging.DEBUG) -> Path:
    """Wire structlog to append colourised, structured records to a file under
    `logs_dir` (default: `<cwd>/.logs`), and return that file's path.

    Idempotent — the first call wins; later calls (safe to make from every
    entrypoint, or repeatedly in tests) just return the already-configured
    file without reconfiguring or opening a second handler.
    """
    global _log_file
    if _log_file is not None:
        return _log_file

    logs_dir = logs_dir if logs_dir is not None else Path.cwd() / ".logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"devinci-{datetime.now():%Y%m%d-%H%M%S}.log"

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setLevel(level)
    # structlog's ConsoleRenderer already produces the full line (timestamp,
    # level, event, colour codes) — stdlib's own "%(levelname)s:%(name)s:..."
    # prefix would just duplicate it, so hand the message through as-is.
    handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%d/%m/%Y - T%H%M", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _log_file = log_file
    return log_file


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """A structlog logger bound to `name` (conventionally `__name__`).

    Modules call this at import time to get a logger; it only actually writes
    to `.logs/` once `configure_logging()` has run (every entrypoint calls it
    before doing anything else — see `main.py` and `tui.app.run`). Calling a
    logger before that point falls back to structlog's own stdout default, so
    entrypoints must configure logging first.
    """
    return structlog.get_logger(name)
