"""Regression checks for the hooks. Run: python tests/test_hooks.py (needs git on PATH, Python 3.10+)."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")
GUARD = os.path.join(HOOKS, "token-guard.py")
ROUTER = os.path.join(HOOKS, "codex-router.py")
TMP = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
BASE = TMP.name
HOME = os.path.join(BASE, "home")
os.makedirs(HOME)
ENV = {**os.environ, "USERPROFILE": HOME, "HOME": HOME}
ENV.pop("PYTHONUTF8", None)
ENV.pop("PYTHONIOENCODING", None)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tg, router = load(GUARD, "tg"), load(ROUTER, "router")


def hook(args, payload):
    r = subprocess.run([sys.executable, *args], input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       capture_output=True, env=ENV, timeout=120)
    return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")


def guard(mode, payload):
    return hook([GUARD, mode], payload)[1]


def repo(name, files):
    d = os.path.join(BASE, name)
    os.makedirs(d)
    write(d, files)
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t.t", "commit", "-q", "-m", "i"]):
        subprocess.run(["git", *args], cwd=d, capture_output=True, check=True)
    return d


def write(d, files):
    for name, body in files.items():
        os.makedirs(os.path.dirname(os.path.join(d, name)), exist_ok=True)
        with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(body)


def transcript(name, entries, sub=None):
    path = os.path.join(BASE, name + ".jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(e if isinstance(e, str) else json.dumps(e) for e in entries) + "\n")
    if sub:
        os.makedirs(os.path.join(BASE, name, "subagents", "workflows", "wf"))
        with open(os.path.join(BASE, name, "subagents", "workflows", "wf", "agent-a1.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(e) for e in sub) + "\n")
    return path


def user(text, **extra):
    return {"type": "user", "timestamp": "2026-01-01T00:00:00.000Z", "message": {"content": text}, **extra}


def calls(*tools, ts="2026-01-01T00:00:01.000Z"):
    blocks = [{"type": "tool_use", "id": f"t{i}", "name": n, "input": inp} for i, (n, inp) in enumerate(tools)]
    return {"type": "assistant", "timestamp": ts, "message": {"content": blocks}}


def edits(*paths):
    return calls(*[("Edit", {"file_path": p}) for p in paths])


def stop(name, entries, sub=None):
    return guard("stop", {"transcript_path": transcript(name, entries, sub)})


CODE3 = edits("C:/proj/a.py", "C:/proj/b.py", "C:/proj/c.py")


def test_codex_detection():
    hit = ['codex exec "x"', 'cd "C:/proj" && codex exec "x"', 'rtk codex exec "x"', 'codex.exe exec "x"',
           '$o = "a"\ncodex exec "x"', 'SP="a b" && codex exec "x"', 'CODEX_HOME=x codex exec "x"',
           'timeout 900 codex exec "x"', 'cat brief.md | codex exec -', '& codex exec "x"',
           '"C:\\Program Files\\nodejs\\codex.cmd" exec "x"', 'C:\\Users\\u\\npm\\codex.cmd exec "x"',
           'npx -y @openai/codex exec "x"', '$r = codex exec "x"']
    miss = ['echo codex exec', 'git commit -m "fix; codex exec regex"', 'codex --version', 'codex execute x',
            'grep "codex exec" notes.md']
    assert [c for c in hit if not tg.codex_call(c)] == []
    assert [c for c in miss if tg.codex_call(c)] == []
    assert tg.codex_call('echo "a`"b" ; codex exec x', "PowerShell")


def test_read_guard():
    big = {n: os.path.join(BASE, n) for n in ("big.log", "café_report.log", "big.pdf", "big.ipynb")}
    for p in big.values():
        with open(p, "wb") as f:
            f.write(b"x" * 150000)
    read = lambda **ti: guard("read", {"tool_input": ti})
    assert "deny" in read(file_path=big["big.log"])
    assert "deny" in read(file_path=big["café_report.log"]), "non-ASCII path must not bypass"
    assert "deny" in read(file_path=big["big.log"], offset=100)
    assert "deny" in read(file_path=big["big.log"], limit=10**9)
    assert "deny" in read(file_path=big["big.log"], pages="1")
    assert "deny" in read(file_path=big["big.ipynb"])
    assert read(file_path=big["big.log"], limit=200) == ""
    assert read(file_path=big["big.pdf"]) == ""
    assert read(file_path=GUARD) == ""
    assert read(file_path=123) == ""
    if os.name == "nt":
        drive, rest = os.path.splitdrive(big["big.log"])
        assert "deny" in read(file_path="/" + drive[0].lower() + rest.replace("\\", "/"))
        assert "deny" in guard("read", {"cwd": BASE, "tool_input": {"file_path": "big.log"}})


def test_sandbox_bypass_denied():
    pre = lambda cmd: guard("pre", {"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert "deny" in pre('codex exec --dangerously-bypass-approvals-and-sandbox "x"')
    assert "deny" in pre('codex exec -s danger-full-access "x"')
    assert "deny" in pre('cd p && codex exec -c sandbox_mode="danger-full-access" "x"')
    assert "deny" in pre('codex exec --yolo "x"')
    assert pre('codex exec -s workspace-write -c model_reasoning_effort="high" "explain the --yolo flag"') == ""
    assert pre('git log --grep danger-full-access') == ""


def test_post_check():
    post = lambda cwd, cmd, **ti: guard("codex", {"cwd": cwd, "tool_name": "Bash", "tool_input": {"command": cmd, **ti}})
    marker = os.path.join(BASE, "marker.txt")
    r1 = repo("r1", {"a.py": "x = 1\n"})
    write(r1, {"conftest.py": f"open(r'{marker}', 'w').write('ran')\n", "tests/test_new.py": "def test_ok(): pass\n",
               "a.py": "x = 2\n"})
    a = post(r1, 'codex exec "x"')
    assert "?? conftest.py" in a and "M a.py" in a, a
    assert "warning:" not in a and "pytest" not in a
    assert not os.path.exists(marker), "repo code must not be executed"
    assert "background" in post(r1, 'codex exec "x"', run_in_background=True)
    assert post(r1, "git status") == ""

    clean = repo("clean", {"a.py": "x = 1\n"})
    assert "(no changes)" in post(clean, 'codex exec "x"')
    assert "M a.py" in post(clean, f'codex exec -C "{r1}" "x"'), "-C target must be checked"
    assert "M a.py" in post(clean, f'cd "{r1}" && codex exec "x"')

    uni = repo("prójecto", {"Árbol.py": "x = 1\n"})
    write(uni, {"Árbol.py": "x = 2\n"})
    assert "M Árbol.py" in json.loads(post(uni, 'codex exec "x"'))["hookSpecificOutput"]["additionalContext"]

    plain = os.path.join(BASE, "plain")
    os.makedirs(plain)
    assert "not a git repo" in post(plain, 'codex exec "secret-brief"')
    with open(os.path.join(HOME, ".claude", "hooks", "codex-usage.log"), encoding="utf-8") as f:
        log = f.read()
    assert "secret-brief" not in log and "| bg |" in log and "| fg |" in log


def test_stop_check():
    scratch = [os.path.join(tempfile.gettempdir(), f"brief{i}.md") for i in range(3)]
    assert "3 code files" in stop("warn", [user("go"), CODE3])
    assert stop("docs", [user("go"), edits(*scratch, "C:/proj/NOTES.md", "C:/proj/a.py")]) == ""
    assert stop("delegated", [user("go"), CODE3, calls(("Bash", {"command": 'cd "C:/p" && codex exec "x"'}))]) == ""
    assert stop("spellings", [user("go"), edits("C:/p/a.py", "C:\\p\\a.py", "c:/p/a.py", "C:/p/b.py")]) == ""
    denied = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t0", "is_error": True}]}}
    assert stop("failed", [user("go"), CODE3, denied]) == ""
    assert "3 code files" in stop("injected", [user("go"), CODE3, user("<task-notification>done</task-notification>")])
    assert "3 code files" in stop("badline", [user("go"), CODE3, "\x00\x00", "[1]", '{"trunc'])
    image = {"type": "user", "message": {"content": [{"type": "image"}]}}
    assert stop("image", [user("go"), CODE3, image, calls()]) == ""
    summary = {"type": "system", "subtype": "stop_hook_summary", "timestamp": "2026-01-01T00:00:02.000Z"}
    assert stop("prev-stop", [user("go"), CODE3, summary, user("<task-notification>x</task-notification>")]) == ""
    late = dict(ts="2026-01-01T00:00:05.000Z")
    assert stop("sub-codex", [user("go"), CODE3], [calls(("Bash", {"command": 'codex exec "x"'}), **late)]) == ""
    assert "3 code files" in stop("sub-edits", [user("go")], [calls(*[("Write", {"file_path": f"C:/p/{i}.py"}) for i in "abc"], **late)])
    assert stop("sub-old", [user("go")], [calls(*[("Write", {"file_path": f"C:/p/{i}.py"}) for i in "abc"], ts="2025-12-31T00:00:00.000Z")]) == ""


def test_router():
    yes = ["write a regex parser", "implement a retry decorator for the downloader",
           "debug the crash in whisperx_batch.py", "fixing the off-by-one in pad_version"]
    no = ["write a LinkedIn post about our new showreel", "add milk to my shopping list",
          "what port does the dev server use?", "how does this function work?", "Yes, fix all",
          "fix the blender export script", "add a hook that formats code"]
    assert [p for p in yes if not router.codexable(p)] == []
    assert [p for p in no if router.codexable(p)] == []
    ctx = lambda prompt: hook([ROUTER], {"prompt": prompt})[1]
    assert "CODEX-ABLE" in ctx("write a regex parser")
    assert "ROUTER RULES" in ctx("مرحبا café") and "CODEX-ABLE" not in ctx("مرحبا café")
    assert ctx("/model") == ""


def test_dispatch():
    rc, _, err = hook([GUARD], {})
    assert rc == 1 and "usage" in err and "Traceback" not in err
    assert hook([GUARD, "bogus"], {})[0] == 1
    for mode in tg.MODES:
        r = subprocess.run([sys.executable, GUARD, mode], input=b"null", capture_output=True, env=ENV)
        assert r.returncode == 0 and r.stdout == b"", mode


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} test groups passed")
