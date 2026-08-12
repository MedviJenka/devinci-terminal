"""TUI run-view — running a saved flow streams live node status to the RunPanel.

The runner is injected, so this drives the real execute() path with a fake runner
and asserts the live status map and the panel reflect success, failure, and skip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.result import Err, Ok, Result
from discovery import CatalogNode
from flows import Flow, FlowNode, NodeStatus, save
from tests.test_tui_app import _plain
from tui.app import DeVinciApp, RunPanel


def _seed_catalog(tmp_path: Path) -> Path:
    claude_root = tmp_path / ".claude"
    (claude_root / "agents").mkdir(parents=True)
    for name in ("planner", "coder"):
        (claude_root / "agents" / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: {name}\n---\nbody\n"
        )
    return claude_root


def _demo_flow() -> Flow:
    return Flow(
        name="demo",
        description="plan then build",
        nodes=(
            FlowNode(id="plan", ref="agent:planner"),
            FlowNode(id="build", ref="agent:coder", after=("plan",)),
        ),
    )


class FakeRunner:
    def __init__(self, fail: set[str] | None = None) -> None:
        self._fail = fail or set()

    def run(self, node: CatalogNode, inputs: str) -> Result[str, str]:
        if node.name in self._fail:
            return Err(f"{node.name} boom")
        return Ok(f"out:{node.name}")


@pytest.mark.asyncio
async def test_running_a_flow_marks_all_nodes_succeeded(tmp_path: Path) -> None:
    claude_root = _seed_catalog(tmp_path)
    flows_dir = tmp_path / "flows"
    save(_demo_flow(), flows_dir)

    app = DeVinciApp(roots=(claude_root,), flows_dir=flows_dir, runner=FakeRunner())
    async with app.run_test() as pilot:
        await pilot.pause()
        report = await app.run_flow_by_name("demo")

        assert isinstance(report, Ok)
        assert report.value.ok
        assert app._run_status == {
            "plan": NodeStatus.SUCCEEDED,
            "build": NodeStatus.SUCCEEDED,
        }
        rendered = _plain(app.query_one(RunPanel)._build(_demo_flow(), app._run_status))
        assert "plan" in rendered and "build" in rendered


@pytest.mark.asyncio
async def test_failure_marks_dependent_skipped(tmp_path: Path) -> None:
    claude_root = _seed_catalog(tmp_path)
    flows_dir = tmp_path / "flows"
    save(_demo_flow(), flows_dir)

    app = DeVinciApp(
        roots=(claude_root,), flows_dir=flows_dir, runner=FakeRunner(fail={"planner"})
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        report = await app.run_flow_by_name("demo")

        assert isinstance(report, Ok)
        assert not report.value.ok
        assert app._run_status["plan"] is NodeStatus.FAILED
        assert app._run_status["build"] is NodeStatus.SKIPPED


@pytest.mark.asyncio
async def test_run_unknown_flow_is_err(tmp_path: Path) -> None:
    claude_root = _seed_catalog(tmp_path)
    app = DeVinciApp(
        roots=(claude_root,), flows_dir=tmp_path / "flows", runner=FakeRunner()
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        result = await app.run_flow_by_name("nope")
        assert isinstance(result, Err)


def test_run_panel_placeholder_when_no_flow_selected() -> None:
    rendered = _plain(RunPanel()._build(None, {}))
    assert "select a flow" in rendered.lower()
