"""Runtime — node runners that turn a catalog node into a produced result.

The executor depends on the NodeRunner interface, never a concrete runner, so
execution backends (CrewAI, Claude Code headless, fakes) are swappable.
"""

from runtime.completion import ClaudeCodeCompletion, Completion
from runtime.condition import ClaudeCondition, Condition
from runtime.runner import ClaudeCodeRunner, NodeRunner

__all__ = [
    "NodeRunner",
    "ClaudeCodeRunner",
    "Completion",
    "ClaudeCodeCompletion",
    "Condition",
    "ClaudeCondition",
]
