from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any

from crewai import Crew

from common.result import Err, Ok, Result


def kickoff_raw(
    crew_factory: Callable[[], Crew],
    inputs: str | Mapping[str, Any],
) -> Result[str, str]:
    prepared = _prepare_inputs(inputs)
    if isinstance(prepared, Err):
        return prepared

    try:
        output = crew_factory().kickoff(inputs=prepared.value)
    except Exception as exc:  # crewai/litellm raise a variety of error types
        return Err(f"crew kickoff failed: {exc}")

    if inspect.iscoroutine(output):
        output.close()
        return Err("crew kickoff returned a coroutine — call from a sync context")

    raw = getattr(output, "raw", None)
    if not isinstance(raw, str):
        return Err("crew kickoff produced no textual output")
    return Ok(raw)


def _prepare_inputs(inputs: str | Mapping[str, Any]) -> Result[dict[str, Any], str]:
    if isinstance(inputs, str):
        description = inputs.strip()
        return Ok({"description": description}) if description else Err("inputs string must not be empty")
    if not inputs:
        return Err("inputs mapping must not be empty")
    return Ok(dict(inputs))
