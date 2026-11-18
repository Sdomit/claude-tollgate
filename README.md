# Tollgate

**Send the coding to Codex. Keep Claude for the thinking.**

Tollgate is a small set of Claude Code hooks. On every prompt it reminds Claude to hand self-contained coding jobs to the Codex CLI, then it checks what Codex changed, and it blocks the most common ways a session burns tokens for nothing.

Two Python files, standard library only, no background service.

![Tollgate hooks reacting to a prompt, a Codex run, a sandbox bypass, a large read and unrouted edits](docs/demo.gif)

<details>
<summary>Same thing as a still image</summary>

![Output of all five Tollgate hooks](docs/screenshot.png)
</details>

Both images are the hooks' real output, rendered by `docs/demo.py`.

## What it does

| When | Hook | Effect |
|------|------|--------|
| You send a prompt | Router | Adds four short routing rules to Claude's context. Flags prompts that look like pure coding work as "Codex-able". |
| Claude reads a file | Read guard | Blocks a full read of any text file over 100KB. Claude has to grep, or read a window of up to 2000 lines. |
| Claude runs a shell command | Sandbox guard | Blocks a Codex command that switches off the sandbox or approvals (`--dangerously-*`, `--yolo`, `danger-full-access`). |
| A `codex exec` finishes | Post-check | Gives Claude `git status --short` for the folder Codex worked in, so it reviews the change instead of redoing it. Logs each run. |
| Claude finishes a turn | Stop check | Warns you when Claude edited three or more code files itself without calling Codex. |

## Install

Requirements: Claude Code, the [Codex CLI](https://github.com/openai/codex), git, and Python 3.10+ available as `python`.

In Claude Code:

```
/plugin marketplace add Sdomit/claude-tollgate
/plugin install tollgate@tollgate
```

Start a new session. That is all.

<details>
<summary>Manual install, without the plugin system</summary>

Copy `hooks/*.py` to `~/.claude/hooks/` and merge this into `~/.claude/settings.json`, replacing `<HOOKS>` with the full path to that folder:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "python", "args": ["<HOOKS>/codex-router.py"], "timeout": 5 }] }
    ],
    "PreToolUse": [
      { "matcher": "Read", "hooks": [{ "type": "command", "command": "python", "args": ["<HOOKS>/token-guard.py", "read"], "timeout": 5 }] },
      { "matcher": "Bash|PowerShell", "hooks": [{ "type": "command", "command": "python", "args": ["<HOOKS>/token-guard.py", "pre"], "timeout": 5 }] }
    ],
    "PostToolUse": [
      { "matcher": "Bash|PowerShell", "hooks": [{ "type": "command", "command": "python", "args": ["<HOOKS>/token-guard.py", "codex"], "timeout": 60 }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "python", "args": ["<HOOKS>/token-guard.py", "stop"], "timeout": 10 }] }
    ]
  }
}
```

Use one install method, not both, or every hook runs twice.
</details>

## How a delegated task flows

1. You ask for something like "add retry logic to downloader.py".
2. The router marks the prompt as Codex-able. Claude writes a brief and runs `codex exec -s workspace-write -C <project> ...`.
3. The sandbox guard lets the command through because it keeps Codex sandboxed.
4. When Codex returns, the post-check lists the changed and new files. Claude reviews the diff and runs your tests.
5. If Claude skips Codex and edits several files itself, the Stop check tells you.

## Configure

**Your own routing rules.** Create `~/.claude/tollgate-rules.md`. Its text replaces the built-in rules on every prompt. Keep it short: it is added to every prompt you send.

**Run Codex without a permission prompt (optional).** Add this to `~/.claude/settings.json`. Sandboxed runs are then pre-approved, in any folder Claude passes with `-C`; the sandbox guard still blocks the bypass flags.

```json
{ "permissions": { "allow": ["Bash(codex exec *)", "PowerShell(codex exec *)"] } }
```

**Usage log.** Each Codex run adds a line (time, foreground or background, folder) to `~/.claude/hooks/codex-usage.log`. No prompt text is stored.

## Limits

- These hooks are nudges, not a security boundary. They fail open: if a script crashes, the tool call goes ahead. The Read guard does not cover shell reads such as `cat`.
- The sandbox guard only stops bypass flags written literally in the command.
- The post-check does not run tests. Running a repo's tests automatically would execute code nobody has reviewed.
- `codex exec` is detected after `&&`, `;`, `|`, a newline, wrappers such as `timeout`, env assignments or a path. It is not detected with global flags before `exec`, or nested in a quoted string (`bash -c "codex exec ..."`).
- The Stop check reads the session transcript, which Claude Code writes asynchronously, so the last tool calls of a turn can be missing. It finds subagent transcripts through an undocumented folder layout.
- Each shell command pays for two short Python starts, about 0.15s each on Windows.
- Developed and used on Windows 11. CI also runs the tests on Linux.

## Develop

```
python tests/test_hooks.py
```

The tests build throwaway git repos in the temp folder and never call the real `codex`. Issues and pull requests are welcome.

## Uninstall

```
/plugin uninstall tollgate@tollgate
```

## License

MIT
