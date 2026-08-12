"""Parse a leading YAML frontmatter block from a Markdown document.

Parse-at-boundary: this is the trust boundary between raw .claude files and the
typed catalog, so it returns a Result rather than throwing on malformed input.
"""

from __future__ import annotations
from typing import Any
import yaml

from common.result import Result, Ok, Err

__all__ = ["parse_frontmatter"]

_FENCE = "---"


def parse_frontmatter(text: str) -> Result[tuple[dict[str, Any], str], str]:
    """Split `---\\n<yaml>\\n---\\n<body>` into (frontmatter dict, body).

    Returns Err when the leading fence is missing, unterminated, or the YAML
    block does not parse to a mapping.
    """

    stripped = text.lstrip("﻿")  # tolerate a UTF-8 BOM
    if not stripped.startswith(_FENCE):
        return Err("missing leading '---' frontmatter fence")

    # Drop the opening fence line, then find the closing fence.
    after_open = stripped.split("\n", 1)
    if len(after_open) != 2:
        return Err("frontmatter fence is not terminated")
    remainder = after_open[1]

    end = remainder.find(f"\n{_FENCE}")
    if end == -1:
        return Err("frontmatter fence is not terminated")

    raw_yaml = remainder[:end]
    body = remainder[end + len(_FENCE) + 1 :].lstrip("\n")

    try:
        loaded = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        return Err(f"invalid YAML frontmatter: {exc}")

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        return Err(f"frontmatter is not a mapping (got {type(loaded).__name__})")

    return Ok((loaded, body))
