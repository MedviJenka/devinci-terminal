"""Shared primitives used across devinci packages."""

from common.logging import configure_logging, get_logger
from common.result import Err, Ok, Result

__all__ = ["Err", "Ok", "Result", "configure_logging", "get_logger"]
