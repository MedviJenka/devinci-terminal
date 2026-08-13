"""
ClaudeCodeCompletion — the LLM boundary backed by `claude` headless.

Satisfies the flows.author.Completion interface by shelling out to Claude Code
in print mode (`claude -p <prompt>`). The subprocess call is injected (default:
`_subprocess_runner`) so it is testable without a real process, and the real
runner passes an argument list (never a shell string) with a fixed timeout — no
shell injection, no unbounded wait.
"""

import subprocess
import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable, Optional
from common.logging import get_logger
from common.result import Err, Ok, Result


__all__ = ["Completion", "ClaudeCodeCompletion", "CommandRunner"]

CommandRunner = Callable[[list[str]], Result[str, str]]

_DEFAULT_TIMEOUT_SECONDS = 180.0
_PREVIEW_CHARS = 200  # how much of a prompt to log, not the whole thing

logger = get_logger(__name__)


@runtime_checkable
class Completion(Protocol):
    """The LLM boundary: a prompt in, a text reply (or error) out.

    Synchronous — callers offload to a thread when inside an event loop. This is
    the seam both flow authoring (design a DAG) and node execution (run a node)
    depend on, so any backend (Claude Code headless, a fake) is swappable.
    """

    def complete(self, prompt: str) -> Result[str, str]: ...


class ClaudeCodeCompletion:
    """Run a prompt through Claude Code headless and return its text reply."""

    def __init__(self, runner: Optional[CommandRunner] = None, *, binary: str = "claude") -> None:
        self._runner = runner if runner is not None else _subprocess_runner
        self._binary = binary

    def complete(self, prompt: str) -> Result[str, str]:
        if not prompt.strip():
            logger.warning("completion_rejected", reason="empty prompt")
            return Err("prompt must not be empty")
        preview = prompt[:_PREVIEW_CHARS] + ("…" if len(prompt) > _PREVIEW_CHARS else "")
        logger.info("completion_started", binary=self._binary, prompt_len=len(prompt), preview=preview)
        started = time.perf_counter()
        result = self._runner([self._binary, "-p", prompt])
        elapsed = time.perf_counter() - started
        if isinstance(result, Err):
            logger.error(
                "completion_failed", binary=self._binary, elapsed_s=round(elapsed, 2),
                error=result.error,
            )
        else:
            logger.info(
                "completion_succeeded", binary=self._binary, elapsed_s=round(elapsed, 2),
                output_len=len(result.value),
            )
        return result


def _subprocess_runner(args: list[str]) -> Result[str, str]:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=_DEFAULT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        logger.error("subprocess_not_found", command=args[0])
        return Err(f"command not found: {args[0]}")
    except subprocess.TimeoutExpired:
        logger.error("subprocess_timed_out", command=args[0], timeout_s=_DEFAULT_TIMEOUT_SECONDS)
        return Err(f"'{args[0]}' timed out after {_DEFAULT_TIMEOUT_SECONDS:.0f}s")
    except OSError as exc:
        logger.error("subprocess_failed", command=args[0], error=str(exc))
        return Err(f"failed to run '{args[0]}': {exc}")

    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit code {completed.returncode}"
        logger.error("subprocess_nonzero_exit", command=args[0], detail=detail)
        return Err(f"'{args[0]}' failed: {detail}")
    return Ok(completed.stdout)
