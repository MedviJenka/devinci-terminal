---
description: Open the DeVinci orchestration terminal.
allowed-tools: Bash, PowerShell
shell: powershell
disable-model-invocation: true
---

```!
if (-not (Test-Path "pyproject.toml") -or -not (Test-Path "main.py")) {
  if ((Split-Path -Leaf (Get-Location)) -eq "py") {
    Set-Location ..
  }
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
  uv run python main.py
} else {
  python main.py
}
```
