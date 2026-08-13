"""Node runners — the boundary between a flow step and its execution backend.

`NodeRunner` is the interface the executor depends on: given a resolved
CatalogNode and composed inputs, produce a textual result or an error (never
throw). `ClaudeCodeRunner` is the production backend — it executes a node by
prompting Claude Code headless (via the injected Completion) to act as that node
over the inputs, so agents, skills, and commands are all executable through one
path.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from common.logging import get_logger
from common.result import Err, Result
from discovery import CatalogNode
from runtime.completion import Completion

__all__ = ["NodeRunner", "ClaudeCodeRunner"]

logger = get_logger(__name__)


@runtime_checkable
class NodeRunner(Protocol):
    """Runs one catalog node. Synchronous — the executor offloads to a thread."""

    def run(self, node: CatalogNode, inputs: str) -> Result[str, str]: ...


class ClaudeCodeRunner:
    """Executes a node by asking Claude Code headless to act as it.

    The Completion backend is injected, so tests substitute a fake and the real
    subprocess call lives entirely in ClaudeCodeCompletion.
    """

    def __init__(self, completion: Completion) -> None:
        self._completion = completion

    def run(self, node: CatalogNode, inputs: str) -> Result[str, str]:
        logger.debug("node_prompt_dispatched", node=node.key, input_len=len(inputs))
        result = self._completion.complete(_node_prompt(node, inputs))
        if isinstance(result, Err):
            logger.warning("node_prompt_failed", node=node.key, error=result.error)
        else:
            logger.debug("node_prompt_completed", node=node.key, output_len=len(result.value))
        return result


def _node_prompt(node: CatalogNode, inputs: str) -> str:
    body = inputs.strip() or "(no additional inputs)"
    return (
        f"You are the '{node.name}' {node.kind.value}. {node.description}\n\n"
        "Carry out your part of the flow given the inputs below, then report your "
        "result concisely.\n\n"
        f"INPUTS:\n{body}"
    )
