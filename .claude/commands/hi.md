---
description: Run DeVinci flow 'hi' — hand-built in the terminal
allowed-tools: Task
---

# /hi

Run this DeVinci orchestration end to end. Execute each step by delegating
to its agent with the Task tool, passing the step instruction plus the
relevant upstream results. Follow the routing exactly and never exceed a
step's repeat cap or the overall visit cap of 5.

Start at step **change-analyzer**.

## Steps

- **change-analyzer** — run `agent:change-analyzer`
    - instruction: hi
    - then → go to Git

- **Git** — run `agent:Git`
    - then → go to playwright-test-generator

- **playwright-test-generator** — run `agent:playwright-test-generator`
    - instruction: hi
    - then: finish
