---
description: Run DeVinci flow 'sd' — hand-built in the terminal
allowed-tools: Task
---

# /sd

Run this DeVinci orchestration end to end. Execute each step by delegating
to its agent with the Task tool, passing the step instruction plus the
relevant upstream results. Follow the routing exactly and never exceed a
step's repeat cap or the overall visit cap of 5.

Start at step **accessibility-agent**.

## Steps

- **accessibility-agent** — run `agent:accessibility-agent`
    - instruction: xcvv
    - then: finish
