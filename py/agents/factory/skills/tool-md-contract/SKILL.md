---
name: tool-md-contract
description: Use when specifying custom tools as a Markdown spec so they slot into the crew's custom:<name> loader and into agent definitions.
---

## Tool Spec Output Contract

One section per tool:

- Heading with the tool name.
- One-line purpose.
- Inputs table: name / type / required.
- Return shape.
- Error-handling notes.

Reference each tool as `custom:<name>`.

## Strict Rules

- Each tool has a single responsibility.
- Validate inputs at the boundary; a tool returns a result, it does not throw.
- Output only the document, written to `output/tool.md`.
