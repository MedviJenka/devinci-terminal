"""Parse the compact edge-wiring command typed into the builder's wire input.

A tiny, unambiguous grammar so the user can add branch and loop edges by hand
without a mouse. Parse-at-boundary: raw user text in, a typed tuple or an Err out,
never an exception.

    from ARROW to [condition words...]

where ARROW is `>` (NEXT), `true>` (ON_TRUE), or `false>` (ON_FALSE). Everything
after the target is the natural-language condition (only meaningful for branches).
"""

from __future__ import annotations

from common.result import Err, Ok, Result
from flows.graph import EdgeKind

__all__ = ["parse_wire", "Wire"]

# (from_id, to_id, edge kind, condition text)
Wire = tuple[str, str, EdgeKind, str]

_ARROWS: dict[str, EdgeKind] = {
    ">": EdgeKind.NEXT,
    "true>": EdgeKind.ON_TRUE,
    "false>": EdgeKind.ON_FALSE,
}


def parse_wire(text: str) -> Result[Wire, str]:
    """Parse `from ARROW to [condition]` into a typed edge spec, or explain why not."""
    parts = text.split()
    if len(parts) < 3:
        return Err("wire needs 'from > to' (e.g. 'review true> test passed')")

    from_id, arrow, to_id = parts[0], parts[1], parts[2]
    kind = _ARROWS.get(arrow)
    if kind is None:
        options = ", ".join(_ARROWS)
        return Err(f"unknown arrow '{arrow}' — use one of: {options}")

    condition = " ".join(parts[3:])
    return Ok((from_id, to_id, kind, condition))
