"""Builds docs/demo.gif and docs/screenshot.png from the hooks' real output. Needs Pillow and git."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap

from PIL import Image, ImageDraw, ImageFont

DOCS = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(DOCS), "hooks")
BG, DIM, WHITE, CYAN, GREEN, RED, YELLOW = "#0d1117", "#8b949e", "#e6edf3", "#58a6ff", "#3fb950", "#ff7b72", "#d29922"
COLS, PAD, LINE_H = 92, 22, 24


def font(bold=False):
    for path in (f"C:/Windows/Fonts/consola{'b' if bold else ''}.ttf",
                 f"/usr/share/fonts/truetype/dejavu/DejaVuSansMono{'-Bold' if bold else ''}.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, 17)
    return ImageFont.load_default()


def run_hook(script, mode, payload, home):
    env = {**os.environ, "USERPROFILE": home, "HOME": home}
    r = subprocess.run([sys.executable, os.path.join(HOOKS, script), *mode], input=json.dumps(payload).encode(),
                       capture_output=True, env=env, check=True)
    return json.loads(r.stdout)


def scenes(base):
    home = os.path.join(base, "home")
    os.makedirs(home)
    app = os.path.join(base, "app")
    os.makedirs(app)
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t.t", *a], cwd=app,
                                    capture_output=True, check=True)
    open(os.path.join(app, "downloader.py"), "w").write("def get(url): ...\n")
    git("init", "-q"), git("add", "-A"), git("commit", "-q", "-m", "init")
    open(os.path.join(app, "downloader.py"), "a").write("# retry\n")
    open(os.path.join(app, "test_downloader.py"), "w").write("def test_retry(): ...\n")
    big = os.path.join(app, "render.log")
    open(big, "wb").write(b"x" * 150000)
    transcript = os.path.join(base, "t.jsonl")
    edits = [{"type": "tool_use", "name": "Edit", "input": {"file_path": f"C:/work/app/{n}.py"}} for n in "abc"]
    with open(transcript, "w") as f:
        f.write(json.dumps({"type": "user", "message": {"content": "go"}}) + "\n")
        f.write(json.dumps({"type": "assistant", "message": {"content": edits}}) + "\n")

    ctx = lambda o: o["hookSpecificOutput"].get("additionalContext") or o["hookSpecificOutput"]["permissionDecisionReason"]
    shell = lambda cmd: {"cwd": app, "tool_name": "Bash", "tool_input": {"command": cmd}}
    route = ctx(run_hook("codex-router.py", [], {"prompt": "add retry logic to downloader.py"}, home)).splitlines()[-1]
    post = ctx(run_hook("token-guard.py", ["codex"], shell('codex exec -s workspace-write "add retry logic"'), home))
    block = ctx(run_hook("token-guard.py", ["pre"], shell('codex exec --yolo "fix it"'), home))
    read = ctx(run_hook("token-guard.py", ["read"], {"tool_input": {"file_path": big}}, home))
    stop = run_hook("token-guard.py", ["stop"], {"transcript_path": transcript}, home)["systemMessage"]
    clean = lambda s: s.replace(app, "C:/work/app").replace(app.replace("\\", "/"), "C:/work/app").replace("\\", "/")
    return [
        ("You", "add retry logic to downloader.py", "router", GREEN, route),
        ("Claude", 'codex exec -s workspace-write "add retry logic"', "post-check", GREEN, clean(post)),
        ("Claude", 'codex exec --yolo "fix it"', "sandbox guard", RED, block),
        ("Claude", "Read render.log", "read guard", RED, clean(read)),
        ("Claude", "edits a.py, b.py, c.py itself", "stop check", YELLOW, stop),
    ]


def layout(all_scenes):
    """Rows of (color, bold, text); a None row marks the end of a scene."""
    rows = []
    for who, action, hook_name, color, output in all_scenes:
        rows.append((WHITE, True, f"{who}: {action}"))
        rows.append((CYAN, False, f"  [{hook_name}]"))
        for line in output.splitlines():
            for part in textwrap.wrap(line, COLS - 4) or [""]:
                rows.append((color, False, "    " + part))
        rows.append(None)
    return rows


def draw(rows, shown, size):
    img = Image.new("RGB", size, BG)
    d = ImageDraw.Draw(img)
    d.text((PAD, 14), "Tollgate: real hook output", font=font(True), fill=DIM)
    y = 14 + LINE_H + 10
    for row in rows[:shown]:
        if row:
            d.text((PAD, y), row[2], font=font(row[1]), fill=row[0])
            y += LINE_H
        else:
            y += LINE_H // 2
    return img


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as base:
        rows = layout(scenes(base))
    width = int(PAD * 2 + COLS * font().getlength("M"))
    height = 14 + LINE_H + 10 + sum(LINE_H if r else LINE_H // 2 for r in rows) + 10
    frames, durations = [], []
    for i, row in enumerate(rows, 1):
        frames.append(draw(rows, i, (width, height)).quantize(32))
        durations.append(1600 if row is None else 220)
    durations[-1] = 5000
    frames[0].save(os.path.join(DOCS, "demo.gif"), save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True)
    draw(rows, len(rows), (width, height)).save(os.path.join(DOCS, "screenshot.png"), optimize=True)
    print(f"{len(frames)} frames, {width}x{height}")


if __name__ == "__main__":
    main()
