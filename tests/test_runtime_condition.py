"""ClaudeCondition — judges a natural-language condition via the LLM boundary."""

from __future__ import annotations

from common.result import Err, Ok, Result
from runtime.condition import ClaudeCondition, Condition


class FakeCompletion:
    def __init__(self, reply: Result[str, str]) -> None:
        self._reply = reply
        self.prompt: str | None = None

    def complete(self, prompt: str) -> Result[str, str]:
        self.prompt = prompt
        return self._reply


def test_yes_reply_is_true_and_prompt_carries_condition_and_output() -> None:
    completion = FakeCompletion(Ok("Yes."))
    result = ClaudeCondition(completion).evaluate("review passed", "LGTM, approved")

    assert isinstance(result, Ok)
    assert result.value is True
    assert "review passed" in completion.prompt
    assert "LGTM, approved" in completion.prompt


def test_no_reply_is_false() -> None:
    result = ClaudeCondition(FakeCompletion(Ok("no, needs changes"))).evaluate("ok", "x")
    assert isinstance(result, Ok)
    assert result.value is False


def test_ambiguous_reply_is_err() -> None:
    result = ClaudeCondition(FakeCompletion(Ok("maybe?"))).evaluate("ok", "x")
    assert isinstance(result, Err)


def test_completion_error_propagates() -> None:
    result = ClaudeCondition(FakeCompletion(Err("down"))).evaluate("ok", "x")
    assert isinstance(result, Err)
    assert "down" in result.error


def test_satisfies_condition_protocol() -> None:
    assert isinstance(ClaudeCondition(FakeCompletion(Ok("yes"))), Condition)
