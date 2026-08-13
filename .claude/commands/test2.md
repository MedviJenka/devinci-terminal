---
description: Run DeVinci flow 'test2' — hand-built in the terminal
allowed-tools: Task
---

# /test2

Run this DeVinci orchestration end to end. Execute each step by delegating
to its agent with the Task tool, passing the step instruction plus the
relevant upstream results. Follow the routing exactly and never exceed a
step's repeat cap or the overall visit cap of 5.

Start at step **Evaluator**.

## Steps

- **Evaluator** — run `agent:Evaluator`
    - then → go to Git

- **Git** — run `agent:Git`
    - if tests passed → go to BugAnalyzer
    - otherwise → go to BugAnalyzer-2

- **BugAnalyzer** — run `agent:BugAnalyzer`
    - then: finish

- **BugAnalyzer-2** — run `agent:BugAnalyzer`
    - then: finish
