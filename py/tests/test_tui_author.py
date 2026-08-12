"""TUI agentic authoring — typing a goal designs and saves a runnable flow.

The app takes an injected Completion, so this drives the real authoring path with
a fake model reply and asserts a flow file lands on disk and the panel refreshes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.result import Err, Ok, Result
from tui.app import DeVinciApp


def _seed_catalog(tmp_path: Path) -> Path:
    claude_root = tmp_path / ".claude"
    (claude_root / "agents").mkdir(parents=True)
    for name in ("planner", "coder"):
        (claude_root / "agents" / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: {name}\n---\nbody\n"
        )
    return claude_root


class FakeCompletion:
    def __init__(self, reply: Result[str, str]) -> None:
        self._reply = reply

    def complete(self, prompt: str) -> Result[str, str]:
        return self._reply


def _good_reply() -> Result[str, str]:
    return Ok(
        json.dumps(
            {
                "name": "review-and-fix",
                "description": "review a PR then fix",
                "nodes": [
                    {"id": "review", "ref": "agent:planner"},
                    {"id": "fix", "ref": "agent:coder", "after": ["review"]},
                ],
            }
        )
    )


@pytest.mark.asyncio
async def test_authoring_a_goal_saves_a_flow_and_refreshes(tmp_path: Path) -> None:
    claude_root = _seed_catalog(tmp_path)
    flows_dir = tmp_path / "flows"
    app = DeVinciApp(
        roots=(claude_root,),
        flows_dir=flows_dir,
        completion=FakeCompletion(_good_reply()),
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        result = await app.author_and_save("review a PR and fix issues")

        assert isinstance(result, Ok)
        assert (flows_dir / "review-and-fix.yaml").exists()
        # The authored flow is now discoverable — what the FLOWS panel reloads.
        from flows import list_flows

        assert "review-and-fix" in {f.name for f in list_flows(flows_dir)}


@pytest.mark.asyncio
async def test_authoring_bad_ref_returns_err_and_saves_nothing(tmp_path: Path) -> None:
    claude_root = _seed_catalog(tmp_path)
    flows_dir = tmp_path / "flows"
    bad = Ok(
        json.dumps(
            {"name": "bad", "description": "", "nodes": [{"id": "a", "ref": "agent:ghost"}]}
        )
    )
    app = DeVinciApp(
        roots=(claude_root,), flows_dir=flows_dir, completion=FakeCompletion(bad)
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        result = await app.author_and_save("do something impossible")

        assert isinstance(result, Err)
        assert not flows_dir.exists() or not any(flows_dir.glob("*.yaml"))
