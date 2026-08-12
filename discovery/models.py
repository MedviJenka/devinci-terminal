from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from common.result import Err, Ok, Result

__all__ = ["Catalog", "CatalogNode", "Diagnostic", "NodeKind"]


class NodeKind(str, Enum):
    """The kind of composable node a catalog entry represents."""

    AGENT = "agent"
    SKILL = "skill"
    COMMAND = "command"


@dataclass(frozen=True, slots=True)
class CatalogNode:
    """One composable node parsed from a .claude definition file.

    Fields mirror the *-md-contract skills: agents carry name/description/tools/
    model/skills; skills carry name/description; commands carry description
    (name derived from the filename).
    """

    kind: NodeKind
    name: str
    description: str
    source: Path
    tools: tuple[str, ...] = ()
    model: str | None = None
    skills: tuple[str, ...] = ()
    user_invocable: bool | None = None

    @property
    def key(self) -> str:
        """Catalog-unique key, e.g. 'agent:code-reviewer'."""
        return f"{self.kind.value}:{self.name}"


@dataclass(frozen=True, slots=True)
class Diagnostic:

    """A file that could not be parsed into a node — skipped, not fatal."""

    source: Path
    message: str


@dataclass(slots=True)
class Catalog:
    """Discovered nodes plus diagnostics for files skipped during scanning.

    Nodes are keyed by (kind, name); the first-seen entry wins.
    """

    _nodes: dict[str, CatalogNode] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def add(self, node: CatalogNode) -> bool:
        """Add a node; return False if its key was already present (kept first)."""
        if node.key in self._nodes:
            return False
        self._nodes[node.key] = node
        return True

    def find(self, kind: NodeKind, name: str) -> CatalogNode | None:
        return self._nodes.get(f"{kind.value}:{name}")

    def resolve(self, ref: str) -> Result[CatalogNode, str]:
        """Resolve a 'kind:name' ref to its node — the inverse of CatalogNode.key."""
        kind_str, _, name = ref.partition(":")
        if not name:
            return Err(f"malformed node ref '{ref}' (expected 'kind:name')")
        try:
            kind = NodeKind(kind_str)
        except ValueError:
            return Err(f"unknown node kind '{kind_str}' in ref '{ref}'")
        node = self.find(kind, name)
        if node is None:
            return Err(f"no catalog node matches ref '{ref}'")
        return Ok(node)

    @property
    def nodes(self) -> tuple[CatalogNode, ...]:
        return tuple(self._nodes.values())

    def of_kind(self, kind: NodeKind) -> tuple[CatalogNode, ...]:
        return tuple(n for n in self._nodes.values() if n.kind is kind)
