---
description: Open the DeVinci orchestration terminal.
allowed-tools: Bash, PowerShell
shell: powershell
disable-model-invocation: true
---

```!
Set-Location ..

if (Get-Command uv -ErrorAction SilentlyContinue) {
  uv run python main.py
} else {
  python main.py
}
```
