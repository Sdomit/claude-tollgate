import datetime
import json
import os
import re
import subprocess
import sys

CODEX_CMD = re.compile(r"^\s*(&\s*)?codex(\.ps1|\.cmd)?\s+exec\b", re.I)

MAX_READ = 100 * 1024
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".pdf", ".ipynb", ".exr", ".tif", ".tiff"}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
LOG = os.path.expanduser("~/.claude/hooks/codex-usage.log")


def out(obj):
    print(json.dumps(obj))


def read_cap(data):
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ""
    if ti.get("limit") or ti.get("pages") or os.path.splitext(path)[1].lower() in BINARY_EXT:
        return
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    if size > MAX_READ:
        out({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"{path} is {size // 1024}KB (>100KB rule). Grep for the relevant part, "
                "or Read with offset/limit."),
        }})


def run(cmd, cwd):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=240)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return f"[{cmd[0]} failed: {e}]"


def has_tests(cwd):
    return any(os.path.exists(os.path.join(cwd, p)) for p in ("tests", "test", "pytest.ini", "conftest.py"))


def codex_check(data):
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not CODEX_CMD.search(cmd):
        return
    cwd = data.get("cwd") or os.getcwd()
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M} | {cwd} | {cmd[:200]!r}\n")
    if run(["git", "rev-parse", "--is-inside-work-tree"], cwd) == "true":
        stat = "\n".join(run(["git", "diff", "--stat"], cwd).splitlines()[-20:]) or "(no changes)"
    else:
        stat = "(not a git repo)"
    parts = ["CODEX POST-CHECK:", "diff --stat:\n" + stat]
    if has_tests(cwd):
        # ponytail: tail-only pytest; per-project test command if repos differ
        tail = "\n".join(run([sys.executable, "-m", "pytest", "-q", "-x"], cwd).splitlines()[-15:])
        parts.append("pytest -q -x (tail):\n" + tail)
    parts.append("Review the diff; do not redo Codex's work.")
    out({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "\n".join(parts)}})


def turn_entries(path):
    with open(path, encoding="utf-8") as f:
        lines = [json.loads(l) for l in f if l.strip()]
    for i in range(len(lines) - 1, -1, -1):
        e = lines[i]
        if e.get("type") != "user" or e.get("isMeta"):
            continue
        c = (e.get("message") or {}).get("content")
        if isinstance(c, str) or (isinstance(c, list) and any(b.get("type") == "text" for b in c if isinstance(b, dict))):
            return lines[i + 1:]
    return lines


def compliance(data):
    if data.get("stop_hook_active") or not data.get("transcript_path"):
        return
    try:
        entries = turn_entries(data["transcript_path"])
    except Exception:
        return
    files, codex = set(), False
    for e in entries:
        if e.get("type") != "assistant":
            continue
        for b in (e.get("message") or {}).get("content") or []:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            ti = b.get("input") or {}
            if b.get("name") in EDIT_TOOLS:
                files.add(ti.get("file_path") or ti.get("notebook_path"))
            if CODEX_CMD.search(str(ti.get("command", ""))):
                codex = True
    if len(files) >= 3 and not codex:
        out({"systemMessage": f"Token guard: Claude edited {len(files)} files itself with no Codex call this turn."})


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    {"read": read_cap, "codex": codex_check, "stop": compliance}[sys.argv[1]](payload)
