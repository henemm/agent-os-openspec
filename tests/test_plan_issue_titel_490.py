"""Plan-Pane: Kurztitel des Issues unter der Nummer (Issue #490).

Spec: docs/specs/feat-490-plan-issue-titel.md (AC-1 bis AC-6).

Stub-`gh` (bash) liegt in <case>/bin und wird PATH vorangestellt. Es protokolliert
jeden Aufruf als eine Zeile in GH_LOG, schlaeft ${GH_SLEEP:-0} s, gibt ${GH_TITLE}
aus und endet mit ${GH_EXIT:-0}.
"""

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"

LONG_TITLE = "Plan-Pane: Kurzbeschreibung des Issues (5–6 Wörter) unter der Nummer"
SHORT_LONG = "Plan-Pane: Kurzbeschreibung des Issues (5–6 Wörter)…"
WF = "feat-490-x"
CLEAR = "\x1b[H\x1b[2J"

GH_STUB = r"""#!/bin/bash
printf '%s\n' "$*" >> "$GH_LOG"
if [ -n "$GH_SLEEP" ]; then sleep "$GH_SLEEP"; fi
if [ -n "$GH_TITLE" ]; then printf '%s\n' "$GH_TITLE"; fi
exit "${GH_EXIT:-0}"
"""


# --- Helpers ---------------------------------------------------------------

def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _project(root: Path) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    return proj


def _wf_data(name: str = WF, phase: str = "phase5_tdd_red") -> dict:
    return {"name": name, "workflow_type": "feature", "current_phase": phase,
            "phase_transitions": [], "phase_log": []}


def _write_wf(proj: Path, data: dict) -> None:
    (proj / ".claude" / "workflows" / f"{data['name']}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(data["name"])


def _cache(proj: Path) -> Path:
    return proj / ".claude" / "issue_titles.json"


def _case(tmp_path: Path, label: str, *, gh: bool = True, **extra):
    root = tmp_path / label
    root.mkdir()
    proj = _project(root)
    log = root / "gh.log"
    bindir = root / "bin"
    bindir.mkdir()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "GH_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["GH_LOG"] = str(log)
    if gh:
        stub = bindir / "gh"
        stub.write_text(GH_STUB)
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        env["PATH"] = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"
    else:
        # Nur ein python3-Symlink — so findet sich garantiert kein echtes gh.
        (bindir / "python3").symlink_to(sys.executable)
        env["PATH"] = str(bindir)
    env.update(extra)
    return proj, log, env


def _workflow(args, env, cwd, timeout: float = 30):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args], capture_output=True,
                          text=True, env=env, cwd=str(cwd), timeout=timeout)


def _gh_calls(log: Path) -> list:
    return [ln for ln in log.read_text().splitlines() if ln] if log.exists() else []


# --- AC-1 -------------------------------------------------------------------

def test_short_title():
    wf = _wf()
    assert wf.short_title(LONG_TITLE) == SHORT_LONG
    assert wf.short_title("Kurzer Titel") == "Kurzer Titel"
    assert wf.short_title("  a   b  ") == "a b"
    assert wf.short_title("") == ""
    assert wf.short_title(None) == ""
    assert wf.short_title("eins zwei drei vier fünf sechs") == "eins zwei drei vier fünf sechs"


# --- AC-2 -------------------------------------------------------------------

def test_render_shows_title_line():
    wf = _wf()
    base = {"name": "feat-490-x", "workflow_type": "feature",
            "current_phase": "phase5_tdd_red"}
    plain = wf.render_plan(dict(base))
    with_title = wf.render_plan(dict(base, issue_title="Kurzer Titel"))
    lines = with_title.splitlines()
    assert lines[:4] == ["Workflow #490", "feat-490-x", "Kurzer Titel", ""], lines
    # Ohne Titel (oder leer / kein String) exakt wie bisher
    assert wf.render_plan(dict(base, issue_title="")) == plain
    assert wf.render_plan(dict(base, issue_title=None)) == plain
    assert plain.splitlines()[:3] == ["Workflow #490", "feat-490-x", ""]
    assert with_title.replace("Kurzer Titel\n", "", 1) == plain


# --- AC-3 -------------------------------------------------------------------

def test_plan_cli_uses_cache(tmp_path):
    proj, log, env = _case(tmp_path, "ok", gh=False)
    _write_wf(proj, _wf_data())
    _cache(proj).write_text(json.dumps({"490": "Kurzer Titel"}))
    res = _workflow(["plan"], env, proj)
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert lines[:3] == ["Workflow #490", WF, "Kurzer Titel"], res.stdout

    proj2, log2, env2 = _case(tmp_path, "broken", gh=False)
    _write_wf(proj2, _wf_data())
    _cache(proj2).write_text("{kaputt")
    res = _workflow(["plan"], env2, proj2)
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert lines[:3] == ["Workflow #490", WF, ""], res.stdout
    assert "Kurzer Titel" not in res.stdout


# --- AC-4 -------------------------------------------------------------------

def test_issue_title_cli_fetch_and_fail_open(tmp_path):
    # Erfolg: Kurztitel ausgegeben und gecacht
    proj, log, env = _case(tmp_path, "ok", GH_TITLE=LONG_TITLE)
    res = _workflow(["issue-title", "490"], env, proj)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == SHORT_LONG, res.stdout
    assert json.loads(_cache(proj).read_text()) == {"490": SHORT_LONG}
    calls = _gh_calls(log)
    assert len(calls) == 1 and calls[0].startswith("issue view 490"), calls

    # Stub mit Exit 1: leer, Exit 0, Cache unveraendert
    proj2, log2, env2 = _case(tmp_path, "fail", GH_TITLE=LONG_TITLE, GH_EXIT="1")
    _cache(proj2).write_text(json.dumps({"7": "Alt"}))
    before = _cache(proj2).read_text()
    res = _workflow(["issue-title", "490"], env2, proj2)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "", res.stdout
    assert _cache(proj2).read_text() == before
    assert len(_gh_calls(log2)) == 1

    # gh fehlt auf PATH: leer, Exit 0, kein Cache angelegt
    proj3, log3, env3 = _case(tmp_path, "nogh", gh=False)
    res = _workflow(["issue-title", "490"], env3, proj3)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "", res.stdout
    assert not _cache(proj3).exists()


# --- AC-5 -------------------------------------------------------------------

def test_start_fetches_detached(tmp_path):
    proj, log, env = _case(tmp_path, "start", GH_TITLE="Kurzer Titel", GH_SLEEP="3")
    t0 = time.monotonic()
    res = _workflow(["start", WF], env, proj)
    elapsed = time.monotonic() - t0
    assert res.returncode == 0, res.stderr
    assert elapsed < 2.0, f"start dauerte {elapsed:.2f}s"
    deadline = time.monotonic() + 15
    cached = None
    while time.monotonic() < deadline:
        try:
            cached = json.loads(_cache(proj).read_text()).get("490")
        except (OSError, ValueError):
            cached = None
        if cached:
            break
        time.sleep(0.1)
    assert cached == "Kurzer Titel"


# --- AC-6 -------------------------------------------------------------------

def test_watch_fetches_once(tmp_path):
    proj, log, env = _case(tmp_path, "watch", GH_TITLE="Kurzer Titel",
                           OPENSPEC_PLAN_WATCH_ROUNDS="3",
                           OPENSPEC_PLAN_WATCH_INTERVAL="0",
                           PYTHONUNBUFFERED="1")
    _write_wf(proj, _wf_data())
    res = _workflow(["plan", "--watch"], env, proj)
    assert res.returncode == 0, res.stderr
    frames = [f for f in res.stdout.split(CLEAR) if f.strip()]
    assert frames, res.stdout
    assert "Kurzer Titel" not in frames[0]
    assert any(f.splitlines()[:3] == ["Workflow #490", WF, "Kurzer Titel"]
               for f in frames[1:]), frames
    assert len(_gh_calls(log)) == 1, _gh_calls(log)

