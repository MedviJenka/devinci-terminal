---
description: Run DeVinci flow 'test' — hand-built in the terminal
allowed-tools: Task
---

# /test

Run this DeVinci orchestration end to end. Execute each step by delegating
to its agent with the Task tool, passing the step instruction plus the
relevant upstream results. Follow the routing exactly and never exceed a
step's repeat cap or the overall visit cap of 5.

Start at step **BugAnalyzer**.

## Steps

- **BugAnalyzer** — run `agent:BugAnalyzer`
    - then → go to Coder

- **Coder** — run `agent:Coder`
    - then → go to Evaluator

- **Evaluator** — run `agent:Evaluator`
    - then: finish
