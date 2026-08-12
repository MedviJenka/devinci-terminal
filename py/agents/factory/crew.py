from pathlib import Path
from agents.agent_settings import SingleAgentFactory
from common.result import Result, Ok, Err

_DIR = Path(__file__).parent

# Generated bundles land in a staging dir and are promoted into the live
# .claude/ tree only after review — the factory never writes there directly.
_STAGING = _DIR / "nodes" / "staging"

_agent_factory = SingleAgentFactory(config_dir=_DIR / "config")

# CrewAI scans a skill search path's children for SKILL.md, so point at the
# `skills/` directory (which loads every *-md-contract skill) with an absolute
# path anchored to this file rather than the caller's cwd.
_SKILLS = [str(_DIR / "skills")]


def factory_lead(capability: str) -> Result[Path, str]:
    """Generate an agent bundle for `capability` and stage it for review.

    Returns Ok(path to the staged bundle) or Err(message) — never throws.
    """
    result = _agent_factory.run(
        agent_name="factory_lead",
        skills=_SKILLS,
        inputs={"query": f"Assemble the agent bundle for the capability: {capability}"},
    )
    if isinstance(result, Err):
        return result
    return _stage(capability, result.value)


def _stage(capability: str, markdown: str) -> Result[Path, str]:
    """Write the generated bundle markdown to the staging dir under a slug."""
    slug = _slug(capability)
    if not slug:
        return Err("capability produced an empty slug")
    try:
        _STAGING.mkdir(parents=True, exist_ok=True)
        target = _STAGING / f"{slug}.md"
        target.write_text(markdown, encoding="utf-8")
    except OSError as exc:
        return Err(f"could not write staged bundle: {exc}")
    return Ok(target)


def _slug(capability: str) -> str:
    return "-".join(
        "".join(c for c in word if c.isalnum()) for word in capability.lower().split()
    ).strip("-")


if __name__ == "__main__":
    outcome = factory_lead("example capability")
    if isinstance(outcome, Ok):
        print(f"staged bundle: {outcome.value}")
    else:
        print(f"factory failed: {outcome.error}")
