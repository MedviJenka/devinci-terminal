"""
A minimal Result type — fallible operations return values, never throw.

Follows the project rule "never throw in business logic": callers pattern-match
on Ok / Err instead of catching exceptions.
"""

from dataclasses import dataclass

__all__ = ["Err", "Ok", "Result"]

@dataclass(frozen=True, slots=True)
class Ok[T]:
    """A successful result carrying a value."""

    value: T

@dataclass(frozen=True, slots=True)
class Err[E]:
    """A failed result carrying an error describing what went wrong."""

    error: E


type Result[T, E] = Ok[T] | Err[E]
