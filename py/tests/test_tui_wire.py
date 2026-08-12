"""The compact edge-wiring grammar typed into the builder's wire input.

Grammar (whitespace-tolerant):
    a > b                 → NEXT edge a→b
    a true> b passed      → ON_TRUE edge a→b, condition "passed"
    a false> b passed     → ON_FALSE edge a→b, condition "passed"
Malformed input returns Err with a human message, never raises.
"""

from __future__ import annotations

from common.result import Err, Ok
from flows.graph import EdgeKind
from tui.wire import parse_wire


def test_plain_next_edge() -> None:
    result = parse_wire("review > test")
    assert isinstance(result, Ok)
    assert result.value == ("review", "test", EdgeKind.NEXT, "")


def test_true_branch_with_condition() -> None:
    result = parse_wire("review true> test passed review")
    assert isinstance(result, Ok)
    frm, to, kind, cond = result.value
    assert (frm, to, kind) == ("review", "test", EdgeKind.ON_TRUE)
    assert cond == "passed review"


def test_false_branch_back_edge() -> None:
    result = parse_wire("review false> code needs work")
    assert isinstance(result, Ok)
    assert result.value == ("review", "code", EdgeKind.ON_FALSE, "needs work")


def test_missing_target_is_err() -> None:
    assert isinstance(parse_wire("review >"), Err)


def test_garbage_is_err() -> None:
    assert isinstance(parse_wire("just some words"), Err)
    assert isinstance(parse_wire(""), Err)
