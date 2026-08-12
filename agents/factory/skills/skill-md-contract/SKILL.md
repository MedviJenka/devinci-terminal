---
name: skill-md-contract
description: Use when authoring a Claude Code SKILL.md so its frontmatter and instructions meet the DeVinci pipeline's registration contract.
---

## SKILL.md Output Contract

A skill is a single Markdown document the DeVinci app registers and loads on demand.

- Open with a `---` YAML frontmatter block:
  - `name`: kebab-case, unique.
  - `description`: one line stating *exactly when* the skill should trigger.
- Follow with concise, ordered instructions the calling agent executes.

## Strict Rules

- The `description` is trigger-focused — it decides *when* the skill fires, not what it is.
- Instructions are concrete and bounded — no open-ended loops or dead ends.
- Output only the document, written to `output/skill.md`.
