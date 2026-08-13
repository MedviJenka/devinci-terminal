"""Condition evaluation — judge a natural-language condition against an output.

`Condition` is the interface the interpreter depends on to route conditional
edges. `ClaudeCondition` implements it via the Completion boundary: it asks the
model for a strict yes/no verdict and parses it, returning Err (never a guess)
when the reply is ambiguous.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from common.logging import get_logger
from common.result import Err, Ok, Result
from runtime.completion import Completion

__all__ = ["ClaudeCondition", "Condition"]

logger = get_logger(__name__)


@runtime_checkable
class Condition(Protocol):
    """Judge whether `output` satisfies `condition`. Synchronous — offload in loops."""

    def evaluate(self, condition: str, output: str) -> Result[bool, str]: ...


class ClaudeCondition:
    """LLM-backed condition judge over the injected Completion boundary."""

    def __init__(self, completion: Completion) -> None:
        self._completion = completion

    def evaluate(self, condition: str, output: str) -> Result[bool, str]:
        logger.debug("condition_evaluate_started", condition=condition)
        reply = self._completion.complete(_prompt(condition, output))
        if isinstance(reply, Err):
            logger.error("condition_evaluate_failed", condition=condition, error=reply.error)
            return reply
        verdict = _parse_verdict(reply.value)
        if isinstance(verdict, Err):
            logger.warning("condition_verdict_unclear", condition=condition, error=verdict.error)
        else:
            logger.debug("condition_evaluate_verdict", condition=condition, verdict=verdict.value)
        return verdict


def _prompt(condition: str, output: str) -> str:
    return (
        "You are a strict evaluator. Answer with exactly one word: 'yes' or 'no'.\n\n"
        f"CONDITION: {condition}\n\n"
        f"OUTPUT TO JUDGE:\n{output}\n\n"
        "Does the output satisfy the condition? Answer yes or no."
    )


def _parse_verdict(reply: str) -> Result[bool, str]:
    text = reply.strip().lower()
    starts_yes = text.startswith("yes")
    starts_no = text.startswith("no")
    if starts_yes:
        return Ok(True)
    if starts_no:
        return Ok(False)
    return Err(f"could not read a yes/no verdict from: {reply.strip()[:80]!r}")
