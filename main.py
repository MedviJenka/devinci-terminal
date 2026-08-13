"""Entry point — launch the TUI or run a saved flow headlessly."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import TextIO

from common.logging import configure_logging, get_logger
from common.result import Err
from discovery import scan
from flows import execute, load
from runtime import ClaudeCodeCompletion, ClaudeCodeRunner, NodeRunner
from tui import run

logger = get_logger(__name__)


def _default_roots() -> tuple[Path, ...]:
    return (Path.cwd() / ".claude", Path.home() / ".claude")


async def run_saved_flow(
    name: str,
    *,
    flows_dir: Path = Path(".devinci") / "flows",
    roots: tuple[Path, ...] | None = None,
    runner: NodeRunner | None = None,
    output: TextIO = sys.stdout,
) -> int:
    """Run a saved flow by name; this is what generated slash commands invoke."""
    logger.info("run_saved_flow_started", name=name, flows_dir=str(flows_dir))
    flow_result = load(flows_dir / f"{name}.yaml")
    if isinstance(flow_result, Err):
        logger.error("run_saved_flow_load_failed", name=name, error=flow_result.error)
        output.write(f"{flow_result.error}\n")
        return 1

    flow = flow_result.value
    catalog = scan(roots if roots is not None else _default_roots())
    node_runner = runner if runner is not None else ClaudeCodeRunner(ClaudeCodeCompletion())
    report = await execute(flow, catalog, node_runner, goal=flow.description)
    if isinstance(report, Err):
        logger.error("run_saved_flow_failed", name=name, error=report.error)
        output.write(f"{report.error}\n")
        return 1

    outcome = "completed" if report.value.ok else "finished with failures"
    logger.info("run_saved_flow_finished", name=name, ok=report.value.ok)
    output.write(f"{flow.name} {outcome}\n")
    for node_id, status in report.value.statuses.items():
        output.write(f"{node_id}: {status.value}\n")
    return 0 if report.value.ok else 1


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="devinci")
    parser.add_argument("--run-flow", metavar="NAME", help="run a saved flow by name")
    parser.add_argument(
        "--flows-dir",
        type=Path,
        default=Path(".devinci") / "flows",
        help="directory containing saved flow YAML files",
    )
    args = parser.parse_args(argv)

    if args.run_flow:
        return asyncio.run(run_saved_flow(args.run_flow, flows_dir=args.flows_dir))

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
