"""Headless flow CLI — generated slash commands can run saved flows."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from common.result import Ok, Result
from discovery import CatalogNode
from flows import Flow, FlowNode, save
from main import run_saved_flow


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, node: CatalogNode, inputs: str) -> Result[str, str]:
        self.calls.append(node.name)
        return Ok(f"out:{node.name}")


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    claude_root = tmp_path / ".claude"
    (claude_root / "agents").mkdir(parents=True)
    (claude_root / "agents" / "planner.md").write_text(
        "---\nname: planner\ndescription: plans work\n---\nbody\n",
        encoding="utf-8",
    )
    flows_dir = tmp_path / ".devinci" / "flows"
    save(
        Flow(
            name="demo",
            description="demo flow",
            nodes=(FlowNode(id="plan", ref="agent:planner"),),
        ),
        flows_dir,
    )
    return claude_root, flows_dir


@pytest.mark.asyncio
async def test_run_saved_flow_executes_named_flow(tmp_path: Path) -> None:
    claude_root, flows_dir = _seed(tmp_path)
    runner = FakeRunner()
    output = StringIO()

    code = await run_saved_flow(
        "demo", flows_dir=flows_dir, roots=(claude_root,), runner=runner, output=output
    )

    assert code == 0
    assert runner.calls == ["planner"]
    assert "demo completed" in output.getvalue()


@pytest.mark.asyncio
async def test_run_saved_flow_reports_missing_flow(tmp_path: Path) -> None:
    output = StringIO()

    code = await run_saved_flow(
        "missing", flows_dir=tmp_path / "flows", roots=(tmp_path / ".claude",), output=output
    )

    assert code == 1
    assert "could not read flow" in output.getvalue()
