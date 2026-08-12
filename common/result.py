"""
A minimal Result type — fallible operations return values, never throw.

Follows the project rule "never throw in business logic": callers pattern-match
on Ok / Err (or use is_ok / is_err) instead of catching exceptions.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Generic, TypeAlias, TypeVar, Union

__all__ = ["Result", "Ok", "Err", "is_ok", "is_err"]

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):

    """A successful result carrying a value."""

    value: T

    def map(self, fn: Callable[[T], U]) -> "Ok[U]":
        return Ok(fn(self.value))

    def unwrap_or(self, _default: T) -> T:
        return self.value


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    
    """A failed result carrying an error describing what went wrong."""

    error: E

    def map(self, _fn: Callable[[T], U]) -> "Err[E]":
        return self

    def unwrap_or(self, default: T) -> T:
        return default


Result: TypeAlias = Union[Ok[T], Err[E]]


def is_ok(result: Result[T, E]) -> bool:
    return isinstance(result, Ok)


def is_err(result: Result[T, E]) -> bool:
    return isinstance(result, Err)
