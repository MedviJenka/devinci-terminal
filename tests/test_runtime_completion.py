"""ClaudeCodeCompletion — the headless `claude` backend for the LLM boundary.

The subprocess call is injected so these tests assert on how the command is
built and how results/errors are mapped, without spawning a real process.
"""

from __future__ import annotations

from common.result import Err, Ok, Result
from flows.author import Completion
from runtime.completion import ClaudeCodeCompletion


class FakeRunner:
    def __init__(self, result: Result[str, str]) -> None:
        self._result = result
        self.args: list[str] | None = None

    def __call__(self, args: list[str]) -> Result[str, str]:
        self.args = args
        return self._result


def test_complete_invokes_claude_headless_with_the_prompt() -> None:
    runner = FakeRunner(Ok("the reply"))
    completion = ClaudeCodeCompletion(runner=runner, binary="claude")

    result = completion.complete("design a flow")

    assert isinstance(result, Ok)
    assert result.value == "the reply"
    assert runner.args == ["claude", "-p", "design a flow"]


def test_binary_is_configurable() -> None:
    runner = FakeRunner(Ok("ok"))
    ClaudeCodeCompletion(runner=runner, binary="/opt/claude").complete("x")
    assert runner.args is not None
    assert runner.args[0] == "/opt/claude"


def test_runner_error_propagates() -> None:
    completion = ClaudeCodeCompletion(runner=FakeRunner(Err("claude not found")))
    result = completion.complete("x")
    assert isinstance(result, Err)
    assert "claude not found" in result.error


def test_empty_prompt_is_err_without_spawning() -> None:
    runner = FakeRunner(Ok("unused"))
    result = ClaudeCodeCompletion(runner=runner).complete("   ")
    assert isinstance(result, Err)
    assert runner.args is None


def test_satisfies_completion_protocol() -> None:
    assert isinstance(ClaudeCodeCompletion(runner=FakeRunner(Ok("x"))), Completion)
