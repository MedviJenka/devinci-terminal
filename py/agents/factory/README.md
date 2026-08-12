# factory_agent

DeVinci factory crew. A single **Agent Factory Lead** agent that assembles a
Claude Code agent definition from a capability plus its skill and tool specs,
and validates the bundle before it enters the DeVinci pipeline.

## Running

```bash
python -m agents.factory.crew
```

Or call it directly with a capability:

```python
from agents.factory.crew import factory_lead

print(factory_lead("summarize a PR diff"))
```

## Project Structure

- `crew.py` - wires the `factory_lead` agent to its `skills/` and exposes
  `factory_lead(capability)`
- `agents/agent_settings.py` - `SingleAgentFactory`: builds a CrewAI `Agent`
  from an `agents.yaml` entry and runs it via `kickoff`
- `config/agents.yaml` - the `factory_lead` (plus `skill_author` / `tool_author`)
  role/goal/backstory definitions
- `skills/` - the `*-md-contract` skills (agent / skill / tool output contracts)
  loaded as the agent's context
