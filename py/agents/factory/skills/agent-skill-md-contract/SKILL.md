---
name: agent-skill-md-contract
description: Use when assembling a Claude Code agent definition (.md) from a capability plus its skill and tool specs, and validating the bundle before it enters the DeVinci pipeline.
---

## Agent Factory

Turn a requested pipeline capability into a registerable agent bundle. The three
factory crews run in order; this crew performs the final assembly and validation.

| Step | Task            | Owner agent   | Output           |
|:-----|:----------------|:--------------|:-----------------|
| 1    | Create Skill    | skill_author  | `output/skill.md`|
| 2    | Create Tool     | tool_author   | `output/tool.md` |
| 3    | Create Agent    | factory_lead  | `output/agent.md`|
| 4    | Validate bundle | factory_lead  | `## Validation`  |

## Output contract — agent.md

- `---` frontmatter with `name` (kebab-case), `description` (when to use the agent),
  and `tools` (list; reference tool specs by `custom:<name>`).
- Operating instructions in Markdown.
- A trailing `## Validation` section asserting the skill, tools, and agent
  instructions are mutually consistent.

## Strict Rules

- **Skills:** every skill the agent references must exist as a SKILL.md with a matching `name`.
- **Tools:** every `tools` entry must map to a `custom:<name>` spec produced by tool_author.
- **Agents:** frontmatter must be valid YAML; `name` unique within the pipeline; output is a single `.md` document with no extra prose.
