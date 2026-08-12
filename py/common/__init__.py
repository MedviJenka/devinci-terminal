"""Shared, dependency-free primitives used across devinci packages."""

from common.result import Result, Ok, Err, is_ok, is_err

__all__ = ["Result", "Ok", "Err", "is_ok", "is_err"]
