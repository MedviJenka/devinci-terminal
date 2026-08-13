"""Persist flows as YAML — the "save it as a reusable pipeline" boundary.

Loading is a trust boundary between raw files and the typed Flow model, so it
parses defensively and returns a Result rather than raising. The on-disk shape
mirrors the model exactly:

    name: ship-feature
    description: plan then build+test then ship
    nodes:
      - id: plan
        ref: agent:planner
      - id: build
        ref: agent:builder
        after: [plan]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from common.logging import get_logger
from common.result import Err, Ok, Result
from flows.models import Flow, FlowNode
from flows.parsing import parse_flow_mapping

__all__ = ["save", "load", "list_flows"]

MAX_FLOWS = 1000  # bound on files a single directory listing will parse

logger = get_logger(__name__)


def save(flow: Flow, directory: Path) -> Result[Path, str]:
    """Write `flow` to `<directory>/<name>.yaml`; return the path or an error."""
    payload = {
        "name": flow.name,
        "description": flow.description,
        "nodes": [_node_to_dict(n) for n in flow.nodes],
    }
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{flow.name}.yaml"
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        logger.info("flow_saved", name=flow.name, nodes=len(flow.nodes), path=str(path))
        return Ok(path)
    except OSError as exc:
        logger.error("flow_save_failed", name=flow.name, error=str(exc))
        return Err(f"could not write flow '{flow.name}': {exc}")


def load(path: Path) -> Result[Flow, str]:
    """Read and validate a flow file into a Flow, or explain why it can't."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("flow_load_unreadable", path=str(path), error=str(exc))
        return Err(f"could not read flow file '{path}': {exc}")

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        logger.error("flow_load_invalid_yaml", path=str(path), error=str(exc))
        return Err(f"invalid YAML in '{path}': {exc}")

    result = parse_flow_mapping(raw, context=f"flow '{path}'")
    if isinstance(result, Err):
        logger.warning("flow_load_invalid", path=str(path), error=result.error)
    else:
        logger.debug("flow_loaded", path=str(path), name=result.value.name)
    return result


def list_flows(directory: Path) -> tuple[Flow, ...]:
    """Load every well-formed *.yaml flow in `directory`; skip the malformed."""
    if not directory.is_dir():
        return ()
    flows: list[Flow] = []
    for path in sorted(directory.glob("*.yaml"))[:MAX_FLOWS]:
        result = load(path)
        if isinstance(result, Ok):
            flows.append(result.value)
    return tuple(flows)


def _node_to_dict(node: FlowNode) -> dict[str, Any]:
    out: dict[str, Any] = {"id": node.id, "ref": node.ref}
    if node.after:
        out["after"] = list(node.after)
    return out
