"""DeVinci slash command — invoking /devinci launches the Textual terminal.

The command must execute through Claude Code's dynamic shell block. A normal
```bash fence is only documentation, so /devinci can load without opening the TUI.
"""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROOT_COMMAND = ROOT / ".claude" / "commands" / "devinci.md"


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    assert text.startswith("---\n")
    _, raw_frontmatter, body = text.split("---", 2)
    return yaml.safe_load(raw_frontmatter), body


def test_devinci_command_executes_terminal_launch_directly() -> None:
    frontmatter, body = _split_frontmatter(ROOT_COMMAND.read_text(encoding="utf-8"))

    assert frontmatter["shell"] == "powershell"
    assert "PowerShell" in frontmatter["allowed-tools"]
    assert body.lstrip().startswith("```!\n")
    assert "uv run python main.py" in body
    assert "python main.py" in body
    assert "```bash" not in body


def test_devinci_command_recovers_when_started_from_py_subdirectory() -> None:
    _, body = _split_frontmatter(ROOT_COMMAND.read_text(encoding="utf-8"))

    assert 'Split-Path -Leaf (Get-Location)' in body
    assert 'Set-Location ..' in body
