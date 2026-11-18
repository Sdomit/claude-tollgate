# Claude Code token hooks

Global hooks that keep Claude on the best model, route coding work to Codex, and enforce CLAUDE.md token rules.

## Files

| File | Event | What it does |
|------|-------|--------------|
| `hooks/codex-router.py` | `UserPromptSubmit` | Injects router rules every prompt. Flags a prompt as "Codex-able" when it has a coding verb and a code noun and no Claude-only word (plan, design, review, research, hooks, skills, plugins, Blender, Unreal/UE, browser, ...). Skips `/` commands. |
| `hooks/token-guard.py read` | `PreToolUse` (Read) | Denies a Read of a file over 100KB unless `limit` is 1 to 2000. Images, PDF, EXR, TIFF exempt. |
| `hooks/token-guard.py pre` | `PreToolUse` (Bash, PowerShell) | Denies a Codex command that carries a sandbox-bypass flag (`--dangerously-*`, `--yolo`, `danger-full-access`). |
| `hooks/token-guard.py codex` | `PostToolUse` (Bash, PowerShell) | After `codex exec`: logs time, mode and folder to `~/.claude/hooks/codex-usage.log`, then feeds back `git status --short` (20 lines) for the folder Codex worked in (`-C`, a leading `cd`, else the session folder). Background runs get a reminder instead, because nothing has changed yet. |
| `hooks/token-guard.py stop` | `Stop` | Warns if Claude edited 3+ code files itself since the last stop with no successful Codex call. Scratch files, `.md/.txt/.rst/.log` and `~/.claude` do not count. Subagent edits and Codex calls do. |
| `tests/test_hooks.py` | | Regression checks for all of the above. |

## Requirements

- Python 3.10+ on PATH as `python` (tested on 3.11.9)
- Codex CLI (`codex exec`), tested on 0.169.0
- git

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
        "args": ["C:\\Users\\<USER>\\.claude\\hooks\\token-guard.py", "read"], "timeout": 5 }] },
      { "matcher": "Bash|PowerShell", "hooks": [{ "type": "command", "command": "python",
        "args": ["C:\\Users\\<USER>\\.claude\\hooks\\token-guard.py", "pre"], "timeout": 5 }] }
    ],
    "PostToolUse": [
      { "matcher": "Bash|PowerShell", "hooks": [{ "type": "command", "command": "python",
        "args": ["C:\\Users\\<USER>\\.claude\\hooks\\token-guard.py", "codex"], "timeout": 60,
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
python tests\test_hooks.py
```

Prints `7 test groups passed`. It builds throwaway git repos in the temp folder and never runs the real `codex`.

## Limits

- The hooks are budget nudges, not a security boundary. They fail open: if a script crashes, the tool call goes ahead. The Read guard does not cover shell reads (`cat`, `Get-Content`).
- The allow rules still pre-approve sandboxed `codex exec` runs, in any folder passed with `-C`. Remove them if every Codex call should ask first. The `pre` hook only stops bypass flags written literally in the command.
- The post-check does not run tests. It used to run pytest, which executed unreviewed repo code with full user rights.
- `codex exec` is detected at a command position (after `&&`, `;`, `|`, a newline, wrappers such as `rtk` or `timeout`, env assignments, or a path). It is not detected with global flags before `exec`, or nested in a quoted string (`bash -c "codex exec ..."`).
- The Stop check reads the transcript file, which Claude Code writes asynchronously, so the last tool calls of a turn can be missing. Subagent transcripts are found through an undocumented folder layout.
- `effortLevel: xhigh` is the highest value settings accept.
- These are copies. Live versions run from `~/.claude/hooks`; edit there, then re-copy here.
