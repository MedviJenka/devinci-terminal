"""Scan .claude roots into a node Catalog.

Skip-with-diagnostic on malformed files, never throw; the walk is bounded by
MAX_FILES so a pathological tree can't run unbounded (reliability rule).
"""

from __future__ import annotations
from collections.abc import Iterable, Iterator, Sequence
from itertools import islice
from pathlib import Path
from typing import Any

from discovery.frontmatter import parse_frontmatter
from discovery.models import Catalog, CatalogNode, Diagnostic, NodeKind
from common.logging import get_logger
from common.result import Ok

__all__ = ["scan", "MAX_FILES"]

MAX_FILES = 5000  # hard upper bound on files inspected per scan

logger = get_logger(__name__)


def scan(roots: Sequence[Path]) -> Catalog:
    """Build a Catalog from the given .claude roots (e.g. project + user dirs).

    Later roots never override earlier ones — the first node seen for a
    (kind, name) key wins, so project definitions shadow user-global ones when
    the project root is listed first.
    """
    logger.debug("scan_started", roots=[str(r) for r in roots])
    catalog = Catalog()
    for source, kind in islice(_iter_definition_files(roots), MAX_FILES):
        _ingest(catalog, source, kind)
    logger.info(
        "scan_completed",
        nodes=len(catalog.nodes),
        diagnostics=len(catalog.diagnostics),
    )
    if catalog.diagnostics:
        for diagnostic in catalog.diagnostics:
            logger.warning(
                "scan_diagnostic", source=str(diagnostic.source), issue=diagnostic.message
            )
    return catalog


def _iter_definition_files(
    roots: Sequence[Path],
) -> Iterator[tuple[Path, NodeKind]]:
    """Yield (file, kind) for every discoverable definition under each root."""
    for root in roots:
        if not root.is_dir():
            continue
        yield from _iter_kind(root / "agents", "*.md", NodeKind.AGENT)
        yield from _iter_kind(root / "commands", "*.md", NodeKind.COMMAND)
        # Skills are a dir-per-skill holding a SKILL.md.
        skills_dir = root / "skills"
        if skills_dir.is_dir():
            for child in sorted(skills_dir.iterdir()):
                skill_md = child / "SKILL.md"
                if child.is_dir() and skill_md.is_file():
                    yield skill_md, NodeKind.SKILL


def _iter_kind(
    directory: Path, glob: str, kind: NodeKind
) -> Iterator[tuple[Path, NodeKind]]:
    if not directory.is_dir():
        return
    # Recursive: agents/commands can be namespaced in subdirs (e.g. testflow/).
    for path in sorted(directory.rglob(glob)):
        if path.is_file():
            yield path, kind


def _ingest(catalog: Catalog, source: Path, kind: NodeKind) -> None:
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        catalog.diagnostics.append(Diagnostic(source, f"unreadable: {exc}"))
        return

    parsed = parse_frontmatter(text)
    if not isinstance(parsed, Ok):
        catalog.diagnostics.append(Diagnostic(source, parsed.error))
        return

    frontmatter, _body = parsed.value
    node = _to_node(kind, frontmatter, source)
    if node is None:
        catalog.diagnostics.append(
            Diagnostic(source, "missing required 'description'")
        )
        return
    catalog.add(node)


def _to_node(
    kind: NodeKind, fm: dict[str, Any], source: Path
) -> CatalogNode | None:
    description = _as_str(fm.get("description"))
    if not description:
        return None

    # Skills derive their name from the parent dir; agents/commands from the
    # frontmatter name, falling back to the file stem.
    if kind is NodeKind.SKILL:
        name = _as_str(fm.get("name")) or source.parent.name
    else:
        name = _as_str(fm.get("name")) or source.stem

    return CatalogNode(
        kind=kind,
        name=name,
        description=description.strip(),
        source=source,
        tools=_as_tuple(fm.get("tools") or fm.get("allowed-tools")),
        model=_as_str(fm.get("model")) or None,
        skills=_as_tuple(fm.get("skills")),
        user_invocable=fm.get("user-invocable") if isinstance(
            fm.get("user-invocable"), bool
        ) else None,
    )


def _as_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_tuple(value: Any) -> tuple[str, ...]:
    """Coerce a frontmatter list or comma string of names into a tuple."""
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, Iterable) and not isinstance(value, (bytes, dict)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()
