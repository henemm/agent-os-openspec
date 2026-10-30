"""Herdr Plan-Pane (Issue #476) — Renderer, `plan`-CLI und Runner gegen ein Stub-Binary.

Spec: docs/specs/feat-476-herdr-plan-pane.md (AC-1 bis AC-14).

Das verzweigende Stub-Binary (bash) protokolliert jeden Aufruf NUL-getrennt in
STUB_LOG und verzweigt nach Unterbefehl:
- `pane get`: Exit ${STUB_GET_EXIT:-0}.
- `pane split`: Exit ${STUB_SPLIT_EXIT:-0}; stdout ${STUB_SPLIT_OUT}, Default
  `{"result":{"pane":{"pane_id":"pane-new"}}}`.
- alles andere (`pane rename`, `pane run`, `pane report-metadata` ...): Exit 0.

Vertraege, die diese Tests festlegen (die Spec nennt sie nicht exakt):
- Zeilenformat des Renderers: Schrittzeilen exakt `<✔|▶|○> <Nr> <Label>`, der
  laufende Schritt mit Suffix `  (läuft)` (zwei Leerzeichen); Labels laut
  Schrittliste der Spec (Kontext, Analyse, Spec, Freigabe, TDD-RED, Implement,
  Adversary, Validierung, Fertig). Kopfzeile `Workflow #<N>`, zweite Zeile der Name.
- `render_plan(data, archived=False, width=None) -> str` (pure); `data=None`
  -> `Kein aktiver Workflow`.
- `plan --watch` zeichnet je Frame mit `\\x1b[H\\x1b[2J` neu (Frames lassen sich
  daran trennen) und flusht stdout.
- `herdr_bridge.plan_pane_settings() -> dict` mit den Schluesseln `enabled`
  (bool) und `ratio` (float), aus der geladenen Projekt-Config (Spec nennt nur
  `plan_pane_enabled()`; den Ratio-Zugriff legen die Tests so fest).
- Runner-CLI: `herdr_bridge.py plan-pane --pane P --cwd C --ratio R --delay 0`.
- `pane run`-Argument beginnt mit `exec `, enthaelt `workflow.py` und endet mit
  `plan --watch`.

Importfehler/fehlende Funktionen erscheinen als Test-FAIL: Module werden erst im
Testkoerper importiert, Runner und CLI laufen als Subprozess.
"""

import json
import os
import select
import stat
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
BRIDGE = HOOKS_DIR / "herdr_bridge.py"

PANE = "pane-476"
NEW_PANE = "pane-new"
WF = "feat-476-herdr-plan-pane"
CLEAR = "\x1b[H\x1b[2J"

STUB_SCRIPT = r"""#!/bin/bash
{ for a in "$@"; do printf '%s\0' "$a"; done; printf '\n'; } >> "$STUB_LOG"
if [ "$1 $2" = "pane get" ]; then exit "${STUB_GET_EXIT:-0}"; fi
if [ "$1 $2" = "pane split" ]; then
  if [ -n "$STUB_SPLIT_OUT" ]; then
    printf '%s\n' "$STUB_SPLIT_OUT"
  else
    printf '%s\n' '{"result":{"pane":{"pane_id":"pane-new"}}}'
  fi
  exit "${STUB_SPLIT_EXIT:-0}"
fi
exit 0
"""


# --- Helpers ---------------------------------------------------------------

def _make_stub(root: Path) -> Path:
    stub = root / "herdr-stub"
    stub.write_text(STUB_SCRIPT)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _project(root: Path, config: "str | None" = None) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    if config is not None:
        (proj / "config.yaml").write_text(config)
    return proj


def _wf_data(name: str = WF, phase: str = "phase5_tdd_red",
             wtype: str = "feature", **fields) -> dict:
    data = {"name": name, "workflow_type": wtype, "current_phase": phase,
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    return data


def _write_wf(proj: Path, data: dict, active: bool = True) -> Path:
    wf = proj / ".claude" / "workflows" / f"{data['name']}.json"
    wf.write_text(json.dumps(data))
    if active:
        (proj / ".claude" / "active_workflow").write_text(data["name"])
    return wf


def _env(proj: Path, log: Path, stub, *, herdr: bool = True, **extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    if herdr:
        env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": PANE,
                    "HERDR_BIN_PATH": str(stub), "STUB_LOG": str(log)})
    env.update(extra)
    return env


def _run(argv, env, cwd, timeout: float = 30):
    return subprocess.run(argv, capture_output=True, text=True, env=env,
                          cwd=str(cwd), timeout=timeout)


def _workflow(args, env, cwd, **kw):
    return _run([sys.executable, str(WORKFLOW_PY), *args], env, cwd, **kw)


def _calls(log: Path) -> list:
    if not log.exists():
        return []
    out = []
    for line in log.read_bytes().decode("utf-8", "replace").split("\n"):
        if line:
            out.append(line.split("\0")[:-1] if line.endswith("\0") else line.split("\0"))
    return out


def _kind(args: list) -> str:
    return " ".join(args[:2])


def _of(calls: list, kind: str) -> list:
    return [c for c in calls if _kind(c) == kind]


def _wait_kind(log: Path, kind: str, timeout: float = 5.0) -> list:
    deadline = time.monotonic() + timeout
    found = _of(_calls(log), kind)
    while not found and time.monotonic() < deadline:
        time.sleep(0.05)
        found = _of(_calls(log), kind)
    return found


def _flag(args: list, flag: str) -> "str | None":
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            return args[i + 1]
    return None


def _case(tmp_path: Path, label: str, config: "str | None" = "herdr:\n  enabled: true\n",
          herdr: bool = True, **env_extra):
    root = tmp_path / label
    root.mkdir()
    proj = _project(root, config)
    log = root / "stub.log"
    env = _env(proj, log, _make_stub(root), herdr=herdr, **env_extra)
    return proj, log, env


def _run_runner(proj: Path, env: dict, *, ratio: str = "0.75", timeout: float = 30):
    return _run([sys.executable, str(BRIDGE), "plan-pane", "--pane", PANE,
                 "--cwd", str(proj), "--ratio", ratio, "--delay", "0"],
                env, proj, timeout=timeout)


def _runner_log(proj: Path) -> str:
    path = proj / ".claude" / "herdr_plan_pane.log"
    return path.read_text() if path.exists() else ""


def _pane_file(proj: Path) -> Path:
    return proj / ".claude" / "herdr_plan_pane.json"


def _render(*args, **kwargs) -> str:
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow.render_plan(*args, **kwargs)


def _step_lines(text: str) -> list:
    return [ln for ln in text.splitlines() if ln[:1] in ("✔", "▶", "○")]


# --- AC-1 -------------------------------------------------------------------

def test_render_full_workflow_marks_done_running_open():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    data = _wf_data()
    out = workflow.render_plan(data)
    lines = out.splitlines()
    assert lines[0] == "Workflow #476", lines
    assert lines[1] == WF, lines
    assert _step_lines(out) == [
        "✔ 1 Kontext", "✔ 2 Analyse", "✔ 3 Spec", "✔ 4 Freigabe",
        "▶ 5 TDD-RED  (läuft)",
        "○ 6 Implement", "○ 6b Adversary", "○ 7 Validierung", "○ 8 Fertig",
    ]
    assert lines[-1] == "Nächster: " + workflow.expected_footer_command(data)


# --- AC-2 -------------------------------------------------------------------

def test_render_fast_track_steps():
    data = _wf_data("fix-12-quick", "phase6_implement", "feature-fast")
    out = _render(data)
    assert _step_lines(out) == [
        "✔ 3 Spec", "✔ 4 Freigabe", "▶ 6 Implement  (läuft)",
        "○ 7 Validierung", "○ 8 Fertig",
    ]
    for absent in ("Kontext", "Analyse", "TDD-RED", "Adversary"):
        assert absent not in out


# --- AC-3 -------------------------------------------------------------------

def test_render_fast_track_off_list_phase():
    data = _wf_data("fix-12-quick", "phase5_tdd_red", "feature-fast")
    out = _render(data)
    assert _step_lines(out) == [
        "✔ 3 Spec", "▶ 4 Freigabe  (läuft)",
        "○ 6 Implement", "○ 7 Validierung", "○ 8 Fertig",
    ]


# --- AC-4 -------------------------------------------------------------------

def test_render_complete_and_archived():
    for data, kwargs in ((_wf_data(phase="phase8_complete"), {}),
                         (_wf_data(phase="phase5_tdd_red"), {"archived": True})):
        out = _render(data, **kwargs)
        steps = _step_lines(out)
        assert len(steps) == 9, steps
        assert all(s.startswith("✔") for s in steps), steps
        assert "▶" not in out
        assert out.splitlines()[-1] == "abgeschlossen", out


# --- AC-5 -------------------------------------------------------------------

def test_render_no_workflow_and_width():
    assert _render(None).strip() == "Kein aktiver Workflow"
    out = _render(_wf_data(), width=12)
    assert out.strip()
    for line in out.splitlines():
        assert len(line) <= 12, repr(line)


# --- AC-6 -------------------------------------------------------------------

def test_cli_plan_prints_once(tmp_path):
    proj, log, env = _case(tmp_path, "with", herdr=False)
    _write_wf(proj, _wf_data())
    res = _workflow(["plan"], env, proj)
    assert res.returncode == 0, res.stderr
    assert "Workflow #476" in res.stdout, res.stdout
    assert "▶ 5 TDD-RED  (läuft)" in res.stdout, res.stdout

    proj2, log2, env2 = _case(tmp_path, "without", herdr=False)
    res = _workflow(["plan"], env2, proj2)
    assert res.returncode == 0, res.stderr
    assert "Kein aktiver Workflow" in res.stdout, res.stdout


# --- AC-7 -------------------------------------------------------------------

def test_watch_follows_archive(tmp_path):
    proj, log, env = _case(tmp_path, "watch", herdr=False,
                           OPENSPEC_PLAN_WATCH_ROUNDS="2",
                           OPENSPEC_PLAN_WATCH_INTERVAL="1.5",
                           PYTHONUNBUFFERED="1")
    wf = _write_wf(proj, _wf_data())
    proc = subprocess.Popen([sys.executable, str(WORKFLOW_PY), "plan", "--watch"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                            cwd=str(proj))
    try:
        # Erst archivieren, wenn die erste Runde den laufenden Workflow gezeigt hat.
        first = b""
        deadline = time.monotonic() + 15
        while b"TDD-RED" not in first and time.monotonic() < deadline:
            ready, _, _ = select.select([proc.stdout], [], [], 0.2)
            if ready:
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk:
                    break
                first += chunk
        assert b"TDD-RED" in first, "Erste Watch-Runde zeigte den Workflow nicht"
        archive = proj / ".claude" / "workflows" / "_archive"
        archive.mkdir(exist_ok=True)
        wf.rename(archive / wf.name)
        (proj / ".claude" / "active_workflow").unlink()
        rest, err = proc.communicate(timeout=20)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0, err.decode()
    text = (first + rest).decode("utf-8", "replace")
    last_frame = text.split(CLEAR)[-1]
    assert "abgeschlossen" in last_frame, repr(last_frame)
    assert "▶" not in last_frame, repr(last_frame)


# --- AC-8 -------------------------------------------------------------------

def test_start_opens_pane_with_split_rename_run(tmp_path):
    cfg = "herdr:\n  enabled: true\n"
    proj, log, env = _case(tmp_path, "herdr", cfg)
    res = _workflow(["start", "plan-x"], env, proj)
    assert res.returncode == 0, res.stderr

    runs = _wait_kind(log, "pane run")
    assert runs, f"Runner lief nicht bis `pane run`: {_calls(log)}"
    calls = _calls(log)
    splits = _of(calls, "pane split")
    assert len(splits) == 1, calls
    split = splits[0]
    assert split[2] == PANE, split
    assert _flag(split, "--direction") == "right", split
    assert _flag(split, "--ratio") == "0.75", split
    assert Path(_flag(split, "--cwd")).resolve() == proj.resolve(), split
    assert "--no-focus" in split, split
    renames = _of(calls, "pane rename")
    assert renames and renames[0][2:] == [NEW_PANE, "Workflow"], renames
    run = runs[0]
    assert run[2] == NEW_PANE, run
    assert run[3].startswith("exec "), run
    assert "workflow.py" in run[3] and run[3].endswith(f"plan --watch --target {PANE}"), run
    assert json.loads(_pane_file(proj).read_text())["panes"][PANE]["pane_id"] == NEW_PANE

    # stdout von `start` identisch zu ohne Herdr-Env
    base_proj, _, base_env = _case(tmp_path, "plain", cfg, herdr=False)
    base = _workflow(["start", "plan-x"], base_env, base_proj)
    assert base.returncode == 0, base.stderr

    def norm(r, p, root):
        return r.stdout.replace(str(p), "<P>").replace(str(root), "<R>")

    assert norm(res, proj, tmp_path / "herdr") == norm(base, base_proj, tmp_path / "plain")


# --- AC-9 -------------------------------------------------------------------

def test_runner_reuses_existing_pane_or_reopens(tmp_path):
    proj, log, env = _case(tmp_path, "alive", STUB_GET_EXIT="0")
    _pane_file(proj).write_text(json.dumps({"panes": {PANE: {"pane_id": "pane-old"}}}))
    res = _run_runner(proj, env)
    assert res.returncode == 0, res.stderr
    calls = _calls(log)
    gets = _of(calls, "pane get")
    assert gets and gets[0][2] == "pane-old", calls
    assert _of(calls, "pane split") == [], calls

    proj2, log2, env2 = _case(tmp_path, "dead", STUB_GET_EXIT="1")
    _pane_file(proj2).write_text(json.dumps({"panes": {PANE: {"pane_id": "pane-old"}}}))
    res = _run_runner(proj2, env2)
    assert res.returncode == 0, res.stderr
    calls = _calls(log2)
    assert len(_of(calls, "pane split")) == 1, calls
    assert json.loads(_pane_file(proj2).read_text())["panes"][PANE]["pane_id"] == NEW_PANE


# --- AC-10 ------------------------------------------------------------------

def test_runner_lock_blocks_parallel_and_expires(tmp_path):
    proj, log, env = _case(tmp_path, "fresh")
    lock = proj / ".claude" / "herdr_plan_pane.lock"
    lock.write_text("")
    res = _run_runner(proj, env)
    assert res.returncode == 0, res.stderr
    assert _of(_calls(log), "pane split") == [], _calls(log)
    assert "läuft bereits" in _runner_log(proj), _runner_log(proj)

    proj2, log2, env2 = _case(tmp_path, "stale")
    lock2 = proj2 / ".claude" / "herdr_plan_pane.lock"
    lock2.write_text("")
    old = time.time() - 60
    os.utime(lock2, (old, old))
    res = _run_runner(proj2, env2)
    assert res.returncode == 0, res.stderr
    assert len(_of(_calls(log2), "pane split")) == 1, _calls(log2)


# --- AC-11 ------------------------------------------------------------------

def test_runner_aborts_on_failed_split(tmp_path):
    for label, extra in (("exit1", {"STUB_SPLIT_EXIT": "1"}),
                         ("noid", {"STUB_SPLIT_OUT": '{"result":{"pane":{}}}'})):
        proj, log, env = _case(tmp_path, label, **extra)
        res = _run_runner(proj, env)
        assert res.returncode == 0, res.stderr
        assert "Traceback" not in res.stderr, res.stderr
        calls = _calls(log)
        assert len(_of(calls, "pane split")) == 1, (label, calls)
        assert _of(calls, "pane rename") == [], (label, calls)
        assert _of(calls, "pane run") == [], (label, calls)
        assert not _pane_file(proj).exists(), label
        assert _runner_log(proj).strip(), f"{label}: kein Log-Eintrag"


# --- AC-12 ------------------------------------------------------------------

def test_no_pane_when_disabled_or_outside_herdr(tmp_path):
    # Positiv-Kontrolle: mit Default-Config wird gesplittet.
    proj, log, env = _case(tmp_path, "control", "herdr:\n  enabled: true\n")
    assert _workflow(["start", "ctl-x"], env, proj).returncode == 0
    assert _wait_kind(log, "pane split"), "Kontrolle: Default oeffnet keinen Pane"

    cases = (
        ("plan-off", "herdr:\n  plan_pane:\n    enabled: false\n", True),
        ("herdr-off", "herdr:\n  enabled: false\n", True),
        ("no-env", "herdr:\n  enabled: true\n", False),
    )
    for label, cfg, herdr in cases:
        proj, log, env = _case(tmp_path, label, cfg, herdr=herdr)
        env["STUB_LOG"] = str(log)  # Stub-Log auch ohne Herdr-Env festlegen
        res = _workflow(["start", "off-x"], env, proj)
        assert res.returncode == 0, (label, res.stderr)
        time.sleep(1.5)
        assert _of(_calls(log), "pane split") == [], (label, _calls(log))


# --- AC-13 ------------------------------------------------------------------

def test_plan_open_forces_pane(tmp_path):
    cfg = "herdr:\n  plan_pane:\n    enabled: false\n"
    proj, log, env = _case(tmp_path, "forced", cfg)
    _write_wf(proj, _wf_data())
    res = _workflow(["plan", "--open"], env, proj)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip(), "plan --open gab keine Zeile aus"
    assert _wait_kind(log, "pane split"), f"Kein pane split: {_calls(log)}"

    proj2, log2, env2 = _case(tmp_path, "outside", cfg, herdr=False)
    _write_wf(proj2, _wf_data())
    res = _workflow(["plan", "--open"], env2, proj2)
    assert res.returncode == 0, res.stderr
    assert "kein Herdr-Pane" in res.stdout, res.stdout


# --- AC-14 ------------------------------------------------------------------

def _settings(tmp_path: Path, label: str, config: str) -> dict:
    root = tmp_path / label
    root.mkdir()
    proj = _project(root, config)
    env = _env(proj, tmp_path / "unused.log", None, herdr=False)
    code = ("import sys, json; sys.path.insert(0, %r); import herdr_bridge; "
            "print(json.dumps(herdr_bridge.plan_pane_settings()))" % str(HOOKS_DIR))
    res = _run([sys.executable, "-c", code], env, proj)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def test_config_default_and_ratio_validation(tmp_path):
    import yaml  # noqa: PLC0415
    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())
    section = cfg["herdr"]["plan_pane"]
    assert section["enabled"] is True
    assert section["ratio"] == 0.75

    ok = _settings(tmp_path, "ok", "herdr:\n  plan_pane:\n    enabled: true\n    ratio: 0.6\n")
    assert ok["enabled"] is True and ok["ratio"] == 0.6, ok
    for label, bad in (("two", "2"), ("str", '"x"')):
        got = _settings(tmp_path, label, f"herdr:\n  plan_pane:\n    ratio: {bad}\n")
        assert got["ratio"] == 0.75, (bad, got)
