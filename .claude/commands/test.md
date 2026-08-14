---
description: Run DeVinci flow 'test' — hand-built in the terminal
allowed-tools: Task
---

# /test

Run this DeVinci orchestration end to end. Execute each step by delegating
to its agent with the Task tool, passing the step instruction plus the
relevant upstream results. Follow the routing exactly and never exceed a
step's repeat cap or the overall visit cap of 5.

Start at step **test-coverage-agent**.

## Steps

- **test-coverage-agent** — run `agent:test-coverage-agent`
    - then: finish
