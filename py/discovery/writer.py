"""Write an edited CatalogNode back to its .claude definition file.

The inverse of scanner._to_node: given a node whose fields were edited in the UI,
rewrite only the frontmatter of `node.source`, leaving the Markdown body and any
frontmatter keys we don't model (e.g. `color`) untouched. Editing updates the key
the file already used — `allowed-tools` stays `allowed-tools`, never duplicated as
`tools`. A boundary operation: it returns a Result and never raises, so a bad path
or unparseable source surfaces as Err rather than crashing the TUI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from common.result import Err, Ok, Result
from discovery.frontmatter import parse_frontmatter
from discovery.models import CatalogNode

__all__ = ["write_node"]

_FENCE = "---"


def write_node(node: CatalogNode) -> Result[Path, str]:
    """Rewrite `node.source`'s frontmatter to reflect `node`; return the path.

    Merges edits onto the file's existing frontmatter so unmodelled keys and the
    Markdown body survive. Returns Err if the source is unreadable or its current
    frontmatter cannot be parsed (we never clobber a file we can't understand).
    """
    try:
        text = node.source.read_text(encoding="utf-8")
    except OSError as exc:
        return Err(f"could not read '{node.source}': {exc}")

    parsed = parse_frontmatter(text)
    if isinstance(parsed, Err):
        return Err(f"cannot edit '{node.source}': {parsed.error}")
    existing, body = parsed.value

    merged = _merge(existing, node)

    try:
        front = yaml.safe_dump(merged, sort_keys=False, allow_unicode=True).rstrip("\n")
        rendered = f"{_FENCE}\n{front}\n{_FENCE}\n\n{body}"
        node.source.write_text(rendered, encoding="utf-8")
    except (OSError, yaml.YAMLError) as exc:
        return Err(f"could not write '{node.source}': {exc}")

    return Ok(node.source)


def _merge(existing: dict[str, Any], node: CatalogNode) -> dict[str, Any]:
    """Overlay the node's editable fields onto the file's existing frontmatter."""
    merged = dict(existing)
    merged["name"] = node.name
    merged["description"] = node.description

    # Update whichever tools key the file already used; default to `tools`.
    tools_key = "allowed-tools" if "allowed-tools" in merged else "tools"
    _set_or_drop(merged, tools_key, list(node.tools) if node.tools else None)
    _set_or_drop(merged, "model", node.model)
    _set_or_drop(merged, "skills", list(node.skills) if node.skills else None)
    return merged


def _set_or_drop(mapping: dict[str, Any], key: str, value: Any) -> None:
    """Set `key` to `value`, or remove it entirely when the value is empty/None."""
    if value:
        mapping[key] = value
    else:
        mapping.pop(key, None)
