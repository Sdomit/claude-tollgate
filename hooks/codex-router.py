import json
import re
import sys

CODEX_TASK = re.compile(
    r"\b(write|add|generate|create|fix|refactor|rename|convert|port|migrate|format|lint|"
    r"test|tests|unit test|boilerplate|scaffold|script|regex|function|cli|parser|"
    r"type hints?|docstrings?|bump|upgrade|translate code)\b",
    re.I,
)
CLAUDE_ONLY = re.compile(
    r"\b(plan|design|architect|review|explain|why|decide|compare|research|"
    r"hooks?|settings|claude|memory|blender|unreal|usd|aces|browser|email|artifacts?|skills?|plugins?)\b",
    re.I,
)

RULES = (
    "ROUTER RULES (global hook, always apply):\n"
    "1. Obey ~/.claude/CLAUDE.md every turn: no preamble, terse, verify before asserting, "
    "<=4 subagents.\n"
    "2. Codex-first: any self-contained coding job (new script/function, tests, mechanical "
    "refactor, bug fix with clear repro, boilerplate, format/lint fixes) goes to Codex, not "
    "your own tokens. Run:\n"
    '   codex exec --skip-git-repo-check -s workspace-write -C "<project dir>" '
    '-c model_reasoning_effort="high" -o "<scratchpad>/codex-out.md" "<self-contained brief>"\n'
    "   Then read ONLY codex-out.md + `git diff --stat`; review the diff, do not re-do the work.\n"
    "3. Keep for yourself: planning, design, review of Codex output, cross-file judgment, "
    "anything needing this chat's context, Blender/UE/USD MCP work, browser/email/artifacts.\n"
    "4. Brief Codex with paths, acceptance check, and 'no explanations'. One codex call per "
    "task; batch small fixes."
)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    prompt = (data.get("prompt") or "").strip()
    if prompt.startswith("/"):
        return

    ctx = RULES
    if CODEX_TASK.search(prompt) and not CLAUDE_ONLY.search(prompt):
        ctx += "\n>> THIS PROMPT LOOKS CODEX-ABLE: delegate it via rule 2 unless it clearly is not."

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        }
    }))


if __name__ == "__main__":
    main()
