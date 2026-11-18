import json
import os
import re
import sys

# A prompt is flagged only when it has a coding verb AND a code noun, so "add milk to my
# list" and "how does this function work?" stay unflagged.
CODE_VERB = re.compile(
    r"\b(?:writ|add|creat|generat|implement|build|mak|fix|debug|refactor|renam|convert|port|migrat|"
    r"format|lint|updat|remov|optimi[sz]|bump|upgrad|scaffold|rewrit)\w*",
    re.I,
)
CODE_NOUN = re.compile(
    r"\b(?:scripts?|functions?|methods?|class(?:es)?|modules?|decorators?|parsers?|regex(?:es)?|cli|api|"
    r"endpoints?|tests?|bugs?|crash(?:es)?|tracebacks?|exceptions?|code|boilerplate|type hints?|"
    r"docstrings?|imports?)\b"
    r"|\w\.(?:py|pyw|js|jsx|ts|tsx|json|ya?ml|toml|ps1|sh|bat|cpp|hpp|h|cs|go|rs|sql|html|css)\b"
    r"|\b[a-z][a-z0-9]*_[a-z0-9_]+\b",
    re.I,
)
CLAUDE_ONLY = re.compile(
    r"\b(?:plan|design|architect\w*|review|research|compare|decide|hooks?|skills?|plugins?|mcp|"
    r"artifacts?|browser|blender|unreal|ue5?|claude)\b",
    re.I,
)

RULES = (
    "ROUTER RULES (global hook, always apply):\n"
    "1. Obey the user's CLAUDE.md every turn.\n"
    "2. Codex-first: any self-contained coding job (new script/function, tests, mechanical "
    "refactor, bug fix with clear repro, boilerplate, format/lint fixes) goes to Codex, not "
    "your own tokens. Run:\n"
    '   codex exec --skip-git-repo-check -s workspace-write -C "<project dir>" '
    '-c model_reasoning_effort="high" -o "<scratchpad>/codex-out.md" "<self-contained brief>"\n'
    "   Then read ONLY codex-out.md + `git status --short` (it lists new files too); review "
    "`git diff`, run the project's tests, do not re-do the work. Never add sandbox-bypass flags.\n"
    "3. Keep for yourself: planning, design, review of Codex output, cross-file judgment, "
    "anything needing this chat's context, work done through MCP tools or the browser.\n"
    "4. Brief Codex with paths, acceptance check, and 'no explanations'. One codex call per "
    "task; batch small fixes."
)


def codexable(prompt):
    return bool(CODE_VERB.search(prompt) and CODE_NOUN.search(prompt) and not CLAUDE_ONLY.search(prompt))


def main():
    try:
        data = json.load(sys.stdin.buffer)  # bytes: Windows would decode piped text as cp1252
    except ValueError:
        data = {}
    prompt = data.get("prompt") if isinstance(data, dict) else ""
    prompt = prompt.strip() if isinstance(prompt, str) else ""
    if prompt.startswith("/"):
        return

    try:  # your own rules replace the defaults
        with open(os.path.expanduser("~/.claude/tollgate-rules.md"), encoding="utf-8") as f:
            ctx = f.read().strip() or RULES
    except OSError:
        ctx = RULES
    if codexable(prompt):
        ctx += "\n>> THIS PROMPT LOOKS CODEX-ABLE: delegate it via rule 2 unless it clearly is not."

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        }
    }))


if __name__ == "__main__":
    main()
