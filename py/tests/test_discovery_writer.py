"""Writing edits back to a .claude definition — the inverse of the scanner.

The contract is round-trip fidelity: an edited CatalogNode written to its source
file must re-scan into the same node. Editing must never clobber the Markdown body
or drop frontmatter keys the model doesn't map (e.g. `color`), and must update the
same key the file already used (`tools` vs `allowed-tools`). Unreadable/unparseable
sources return Err, never raise.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import yaml

from common.result import Err, Ok
from discovery.frontmatter import parse_frontmatter
from discovery.models import CatalogNode, NodeKind
from discovery.scanner import scan
from discovery.writer import write_node


def _agent_file(root: Path, name: str, text: str) -> Path:
    agents = root / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    path = agents / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


_SAMPLE = """---
name: code-reviewer
description: reviews diffs for bugs
tools:
  - Read
  - Grep
model: opus
color: cyan
---

# Code Reviewer

Does a thorough review of the diff.
"""


def _node_from(path: Path) -> CatalogNode:
    catalog = scan((path.parent.parent,))
    found = catalog.find(NodeKind.AGENT, "code-reviewer")
    assert found is not None
    return found


def test_edit_round_trips_through_the_scanner(tmp_path: Path) -> None:
    path = _agent_file(tmp_path, "code-reviewer", _SAMPLE)
    node = _node_from(path)

    edited = replace(
        node,
        description="reviews diffs for bugs AND security holes",
        tools=("Read", "Grep", "Bash"),
        model="sonnet",
    )
    written = write_node(edited)
    assert isinstance(written, Ok)
    assert written.value == path

    rescanned = _node_from(path)
    assert rescanned.description == "reviews diffs for bugs AND security holes"
    assert rescanned.tools == ("Read", "Grep", "Bash")
    assert rescanned.model == "sonnet"


def test_body_and_unmapped_keys_are_preserved(tmp_path: Path) -> None:
    path = _agent_file(tmp_path, "code-reviewer", _SAMPLE)
    node = _node_from(path)

    write_node(replace(node, description="new description"))

    text = path.read_text(encoding="utf-8")
    assert "# Code Reviewer" in text  # body kept verbatim
    assert "Does a thorough review of the diff." in text

    parsed = parse_frontmatter(text)
    assert isinstance(parsed, Ok)
    frontmatter, _body = parsed.value
    assert frontmatter.get("color") == "cyan"  # unmapped key survives


def test_clearing_the_model_removes_the_key(tmp_path: Path) -> None:
    path = _agent_file(tmp_path, "code-reviewer", _SAMPLE)
    node = _node_from(path)

    write_node(replace(node, model=None))

    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, Ok)
    frontmatter, _ = parsed.value
    assert "model" not in frontmatter


def test_updates_the_existing_key_when_source_used_allowed_tools(tmp_path: Path) -> None:
    text = (
        "---\n"
        "name: releaser\n"
        "description: cuts releases\n"
        "allowed-tools: Bash, Read\n"
        "---\n\n"
        "body\n"
    )
    path = _agent_file(tmp_path, "releaser", text)
    catalog = scan((tmp_path,))
    node = catalog.find(NodeKind.AGENT, "releaser")
    assert node is not None
    assert node.tools == ("Bash", "Read")

    write_node(replace(node, tools=("Bash", "Read", "Git")))

    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, Ok)
    frontmatter, _ = parsed.value
    assert "tools" not in frontmatter  # did not introduce a competing key
    assert frontmatter["allowed-tools"] == ["Bash", "Read", "Git"]


def test_unreadable_source_is_err(tmp_path: Path) -> None:
    missing = CatalogNode(
        kind=NodeKind.AGENT,
        name="ghost",
        description="not on disk",
        source=tmp_path / "agents" / "ghost.md",
    )
    result = write_node(missing)
    assert isinstance(result, Err)


def test_unparseable_source_is_err_and_never_clobbers(tmp_path: Path) -> None:
    # A readable file whose frontmatter cannot be parsed must return Err WITHOUT
    # rewriting a single byte — we never overwrite a file we don't understand.
    garbage = "not frontmatter at all\njust: [unterminated\n# body\n"
    path = _agent_file(tmp_path, "broken", garbage)
    node = CatalogNode(
        kind=NodeKind.AGENT,
        name="broken",
        description="edited in the UI",
        source=path,
        tools=("Read",),
    )

    result = write_node(node)

    assert isinstance(result, Err)
    assert path.read_text(encoding="utf-8") == garbage  # untouched on disk
