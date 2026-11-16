# Claude Code token hooks

Global hooks that keep Claude on the best model, route coding work to Codex, and enforce CLAUDE.md token rules.

## Files

| File | Event | What it does |
|------|-------|--------------|
| `hooks/codex-router.py` | `UserPromptSubmit` | Injects router rules every prompt. Flags coding prompts as "Codex-able" unless they hit the Claude-only list (plan, review, Blender, UE, USD, hooks, ...). Skips `/` commands. |
| `hooks/token-guard.py read` | `PreToolUse` (Read) | Denies a full Read of any file over 100KB. Allowed with `limit`/`pages`. Images, PDF, EXR, TIFF exempt. |
| `hooks/token-guard.py codex` | `PostToolUse` (Bash, PowerShell) | After `codex exec`: logs to `~/.claude/hooks/codex-usage.log`, feeds back `git diff --stat` (20 lines) and `pytest -q -x` tail (15 lines) if tests exist. |
| `hooks/token-guard.py stop` | `Stop` | Warns if Claude edited 3+ files itself in one turn with no Codex call. |

## Requirements

- Python 3.12 on PATH as `python`
- Codex CLI (`codex exec`), tested on 0.169.0
- git, and pytest in projects that have tests

## Install

1. Copy `hooks/*.py` to `%USERPROFILE%\.claude\hooks\`.
2. Merge into `%USERPROFILE%\.claude\settings.json` (keep existing entries; replace `<USER>`):

```json
{
  "model": "best",
  "effortLevel": "xhigh",
  "permissions": { "allow": ["Bash(codex exec *)", "PowerShell(codex exec *)"] },
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "python",
        "args": ["C:\\Users\\<USER>\\.claude\\hooks\\codex-router.py"], "timeout": 5 }] }
    ],
    "PreToolUse": [
      { "matcher": "Read", "hooks": [{ "type": "command", "command": "python",
        "args": ["C:\\Users\\<USER>\\.claude\\hooks\\token-guard.py", "read"], "timeout": 5 }] }
    ],
    "PostToolUse": [
      { "matcher": "Bash|PowerShell", "hooks": [{ "type": "command", "command": "python",
        "args": ["C:\\Users\\<USER>\\.claude\\hooks\\token-guard.py", "codex"], "timeout": 300,
        "statusMessage": "Checking Codex output" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "python",
        "args": ["C:\\Users\\<USER>\\.claude\\hooks\\token-guard.py", "stop"], "timeout": 10 }] }
    ]
  }
}
```

3. Start a new Claude Code session so hooks load.

## Test

```powershell
'{"prompt":"write a regex parser"}' | python hooks\codex-router.py
'{"tool_input":{"file_path":"C:\\big.log"}}' | python hooks\token-guard.py read
```

First prints router rules with the "CODEX-ABLE" line; second prints a deny if the file is over 100KB.

## Notes

- `effortLevel: xhigh` is the highest value settings accept.
- These are copies. Live versions run from `~/.claude/hooks`; edit there, then re-copy here.
