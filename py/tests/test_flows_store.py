"""Persistence — a designed flow saves to YAML and reloads identically.

Round-trip fidelity is the whole point of "reusable pipelines": what you save
is what you get back. Malformed files load as Err, never raise.
"""

from __future__ import annotations

from pathlib import Path

from common.result import Err, Ok
from flows.models import Flow, FlowNode
from flows.store import list_flows, load, save


def _flow() -> Flow:
    return Flow(
        name="ship-feature",
        description="plan then build+test then ship",
        nodes=(
            FlowNode(id="plan", ref="agent:planner"),
            FlowNode(id="build", ref="agent:builder", after=("plan",)),
            FlowNode(id="test", ref="agent:tester", after=("plan",)),
            FlowNode(id="ship", ref="command:release", after=("build", "test")),
        ),
    )


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    flow = _flow()
    saved = save(flow, tmp_path)
    assert isinstance(saved, Ok)

    loaded = load(saved.value)
    assert isinstance(loaded, Ok)
    assert loaded.value == flow


def test_save_uses_the_flow_name_for_the_filename(tmp_path: Path) -> None:
    saved = save(_flow(), tmp_path)
    assert isinstance(saved, Ok)
    assert saved.value.name == "ship-feature.yaml"


def test_load_missing_file_is_err(tmp_path: Path) -> None:
    result = load(tmp_path / "does-not-exist.yaml")
    assert isinstance(result, Err)


def test_load_malformed_yaml_is_err(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\nnodes: [this is not a mapping]\n")
    result = load(bad)
    assert isinstance(result, Err)


def test_list_flows_returns_every_saved_flow(tmp_path: Path) -> None:
    save(_flow(), tmp_path)
    save(
        Flow(name="tiny", description="", nodes=(FlowNode(id="a", ref="agent:a"),)),
        tmp_path,
    )

    flows = list_flows(tmp_path)

    names = {f.name for f in flows}
    assert names == {"ship-feature", "tiny"}


def test_list_flows_on_empty_dir_is_empty(tmp_path: Path) -> None:
    assert list_flows(tmp_path) == ()
