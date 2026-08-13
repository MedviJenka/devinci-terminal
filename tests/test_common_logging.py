"""configure_logging() wires structlog to a colourised file under `.logs/`,
never to stdout — the TUI owns the terminal, so a stray print would corrupt
the display.
"""

from __future__ import annotations

import logging
from pathlib import Path

import structlog

import common.logging as devinci_logging


def _reset() -> None:
    devinci_logging._log_file = None
    logging.getLogger().handlers.clear()


def test_configure_logging_creates_a_file_under_the_given_dir(tmp_path: Path) -> None:
    _reset()
    logs_dir = tmp_path / ".logs"
    log_file = devinci_logging.configure_logging(logs_dir)

    assert log_file.parent == logs_dir
    assert log_file.exists()
    assert log_file.name.startswith("devinci-") and log_file.suffix == ".log"


def test_get_logger_writes_structured_colourised_lines_to_the_file(tmp_path: Path) -> None:
    _reset()
    log_file = devinci_logging.configure_logging(tmp_path / ".logs")
    log = devinci_logging.get_logger("test.module")
    log.info("node_added", node_id="reviewer", ref="agent:reviewer")

    content = log_file.read_text(encoding="utf-8")
    assert "node_added" in content
    assert "reviewer" in content
    assert "\x1b[" in content  # ANSI colour codes from ConsoleRenderer(colors=True)


def test_configure_logging_is_idempotent(tmp_path: Path) -> None:
    _reset()
    first = devinci_logging.configure_logging(tmp_path / "a")
    second = devinci_logging.configure_logging(tmp_path / "b")

    assert first == second  # second call is a no-op; original file wins
    assert len(logging.getLogger().handlers) == 1  # no duplicate handler added


def test_get_logger_returns_a_structlog_bound_logger() -> None:
    _reset()
    log = devinci_logging.get_logger(__name__)
    assert hasattr(log, "info") and hasattr(log, "warning") and hasattr(log, "error")
