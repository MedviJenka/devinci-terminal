from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "agents"


def _load_agent_config(package: str) -> dict[str, object]:
    return yaml.safe_load((AGENTS / package / "config" / "agents.yaml").read_text(encoding="utf-8"))


def _load_task_config(package: str) -> dict[str, object]:
    return yaml.safe_load((AGENTS / package / "config" / "tasks.yaml").read_text(encoding="utf-8"))


def test_each_factory_agent_lives_in_its_own_package() -> None:
    expected = {
        "command_agent": ("command_writer", ["command-writer"]),
        "skill_author_agent": ("skill_author", ["skill-md-contract"]),
        "tool_author_agent": ("tool_author", ["tool-md-contract"]),
        "factory_lead_agent": (
            "factory_lead",
            ["agent-skill-md-contract", "skill-md-contract", "tool-md-contract"],
        ),
    }

    for package, (agent_name, skills) in expected.items():
        package_dir = AGENTS / package
        assert package_dir.is_dir()
        assert (package_dir / "agent.py").is_file()
        assert (package_dir / "crew.py").is_file()
        assert (package_dir / "__init__.py").is_file()

        agents_config = _load_agent_config(package)
        assert list(agents_config) == [agent_name]
        assert "skills" not in agents_config[agent_name]

        skill_names = sorted(path.name for path in (package_dir / "skills").iterdir())
        assert skill_names == sorted(skills)

        tasks_config = _load_task_config(package)
        assert len(tasks_config) == 1
        assert next(iter(tasks_config.values()))["agent"] == agent_name


def test_split_agent_packages_export_their_runner_functions() -> None:
    from agents.command_agent import command_agent
    from agents.factory_lead_agent import factory_lead
    from agents.skill_author_agent import skill_author
    from agents.tool_author_agent import tool_author

    assert command_agent.__name__ == "command_agent"
    assert skill_author.__name__ == "skill_author"
    assert tool_author.__name__ == "tool_author"
    assert factory_lead.__name__ == "factory_lead"
