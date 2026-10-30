"""Plan-Pane nach Claude-Neustart wiederverwenden (Issue #493).

Spec: docs/specs/fix-493-plan-pane-doppelt.md (AC-1 bis AC-7; AC-8 ist der
Regressionslauf von tests/test_herdr_plan_pane_476.py und
tests/test_herdr_plan_deploy_sessionstart_478.py).

Aufbau je Fall: ein echtes Git-Repo (Haupt-Repo) mit zwei Worktrees per
`git worktree add`. Der Runner laeuft synchron (`herdr_bridge.py plan-pane
--delay 0`) mit dem Worktree als cwd und `CLAUDE_PROJECT_DIR`, wie eine echte
Session. Der Watcher laeuft als Subprozess `workflow.py plan --watch --target <P>`
mit `OPENSPEC_PLAN_WATCH_ROUNDS` und `OPENSPEC_PLAN_WATCH_INTERVAL=0`.

Verzweigendes Stub-Binary (bash), Muster tests/test_herdr_plan_pane_476.py:
- protokolliert jeden Aufruf NUL-getrennt in STUB_LOG;
- `pane get`: Exit ${STUB_GET_EXIT:-0};
- `pane split`: liefert je Aufruf eine neue ID `pane-new-<n>` (Zaehler in
  STUB_COUNT), Exit 0;
- vermerkt bei jedem Aufruf in STUB_LOCK_LOG, ob die Lock-Dateien unter
  STUB_LOCK_MAIN bzw. STUB_LOCK_WT existieren (`main=0|1 wt=0|1`);
- alles andere: Exit 0.

Vertraege laut Spec (Implementation Details):
- ID-Datei `<haupt-repo>/.claude/herdr_plan_pane.json`, Format
  `{"panes": {"<claude-pane>": {"pane_id": ..., "cwd": ...}}}`;
- Lock `<haupt-repo>/.claude/herdr_plan_pane.lock`;
- `pane run`-Befehl endet mit `plan --watch --target <claude-pane>`.
"""

import json
import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
BRIDGE = HOOKS_DIR / "herdr_bridge.py"

CLAUDE = "pane-claude-493"
CLEAR = "\x1b[H\x1b[2J"
WF_X = "wf-x"
WF_Y = "wf-y"

STUB_SCRIPT = r"""#!/bin/bash
{ for a in "$@"; do printf '%s\0' "$a"; done; printf '\n'; } >> "$STUB_LOG"
if [ -n "$STUB_LOCK_LOG" ]; then
  m=0; w=0
  [ -n "$STUB_LOCK_MAIN" ] && [ -e "$STUB_LOCK_MAIN" ] && m=1
  [ -n "$STUB_LOCK_WT" ] && [ -e "$STUB_LOCK_WT" ] && w=1
  printf 'main=%s wt=%s\n' "$m" "$w" >> "$STUB_LOCK_LOG"
fi
if [ "$1 $2" = "pane get" ]; then exit "${STUB_GET_EXIT:-0}"; fi
if [ "$1 $2" = "pane split" ]; then
  n=0; [ -f "$STUB_COUNT" ] && n=$(< "$STUB_COUNT"); n=$(( n + 1 ))
  printf '%s' "$n" > "$STUB_COUNT"
  printf '{"result":{"pane":{"pane_id":"pane-new-%s"}}}\n' "$n"
  exit 0
fi
exit 0
"""


# --- Helpers ---------------------------------------------------------------

def _git(args, cwd: Path) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "init.defaultBranch=main", *args],
                   cwd=str(cwd), check=True, capture_output=True, text=True)


class Case:
    """Isoliertes Projekt: Haupt-Repo + zwei Worktrees + Stub-Herdr."""

    def __init__(self, tmp_path: Path, label: str):
        self.root = tmp_path / label
        self.root.mkdir()
        self.main = self.root / "main"
        self.main.mkdir()
        _git(["init", "-q"], self.main)
        _git(["commit", "-q", "--allow-empty", "-m", "init"], self.main)
        (self.main / ".claude" / "workflows" / "_log").mkdir(parents=True)
        (self.main / "config.yaml").write_text("herdr:\n  enabled: true\n")
        self.home = self.root / "_home"
        self.home.mkdir()
        self.wt_a = self.root / "wt-a"
        self.wt_b = self.root / "wt-b"
        for wt in (self.wt_a, self.wt_b):
            _git(["worktree", "add", "-q", "--detach", str(wt)], self.main)
            (wt / ".claude").mkdir(exist_ok=True)
            (wt / "config.yaml").write_text("herdr:\n  enabled: true\n")
        self.log = self.root / "stub.log"
        self.count = self.root / "stub.count"
        self.lock_log = self.root / "stub.lock.log"
        self.stub = self.root / "herdr-stub"
        self.stub.write_text(STUB_SCRIPT)
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        # PATH nur mit python3: kein echtes gh/herdr erreichbar.
        self.bindir = self.root / "bin"
        self.bindir.mkdir()
        (self.bindir / "python3").symlink_to(sys.executable)

    # -- Umgebung ----------------------------------------------------------
    def env(self, session_dir: Path, **extra) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_", "GH_"))}
        env.update({
            "CLAUDE_PROJECT_DIR": str(session_dir),
            "HOME": str(self.home),
            "PATH": str(self.bindir),
            "HERDR_ENV": "1",
            "HERDR_PANE_ID": CLAUDE,
            "HERDR_BIN_PATH": str(self.stub),
            "STUB_LOG": str(self.log),
            "STUB_COUNT": str(self.count),
        })
        env.update(extra)
        return env

    # -- Runner ------------------------------------------------------------
    def runner(self, wt: Path, pane: str = CLAUDE, **extra):
        res = subprocess.run(
            [sys.executable, str(BRIDGE), "plan-pane", "--pane", pane,
             "--cwd", str(wt), "--ratio", "0.75", "--delay", "0"],
            capture_output=True, text=True, env=self.env(wt, **extra),
            cwd=str(wt), timeout=30)
        assert res.returncode == 0, res.stderr
        return res

    # -- Watcher -----------------------------------------------------------
    def watcher(self, wt: Path, target: str = CLAUDE, rounds: int = 2):
        env = self.env(wt, OPENSPEC_PLAN_WATCH_ROUNDS=str(rounds),
                       OPENSPEC_PLAN_WATCH_INTERVAL="0", PYTHONUNBUFFERED="1")
        return subprocess.run(
            [sys.executable, str(WORKFLOW_PY), "plan", "--watch", "--target", target],
            capture_output=True, text=True, env=env, cwd=str(wt), timeout=30)

    # -- Dateien -----------------------------------------------------------
    def id_file(self, base: "Path | None" = None) -> Path:
        return (base or self.main) / ".claude" / "herdr_plan_pane.json"

    def lock_file(self, base: "Path | None" = None) -> Path:
        return (base or self.main) / ".claude" / "herdr_plan_pane.lock"

    def entries(self) -> dict:
        path = self.id_file()
        assert path.exists(), (
            f"ID-Datei fehlt im Haupt-Repo ({path}); im Worktree: "
            f"{[str(p) for p in (self.id_file(self.wt_a), self.id_file(self.wt_b)) if p.exists()]}")
        data = json.loads(path.read_text())
        assert isinstance(data, dict) and isinstance(data.get("panes"), dict), data
        return data["panes"]

    def write_entries(self, panes: dict) -> None:
        self.id_file().write_text(json.dumps({"panes": panes}))

    def write_wf(self, wt: Path, name: str) -> None:
        data = {"name": name, "workflow_type": "feature",
                "current_phase": "phase5_tdd_red", "phase_transitions": [],
                "phase_log": []}
        (self.main / ".claude" / "workflows" / f"{name}.json").write_text(json.dumps(data))
        (wt / ".claude" / "active_workflow").write_text(name)

    def calls(self) -> list:
        if not self.log.exists():
            return []
        out = []
        for line in self.log.read_bytes().decode("utf-8", "replace").split("\n"):
            if line:
                parts = line.split("\0")
                out.append(parts[:-1] if line.endswith("\0") else parts)
        return out

    def of(self, kind: str) -> list:
        return [c for c in self.calls() if " ".join(c[:2]) == kind]


def _same(a, b) -> bool:
    return Path(a).resolve() == Path(b).resolve()


def _last_frame(stdout: str) -> str:
    frames = [f for f in stdout.split(CLEAR) if f.strip()]
    assert frames, repr(stdout)
    return frames[-1]


# --- AC-1 -------------------------------------------------------------------

def test_second_run_reuses_pane_and_updates_cwd(tmp_path):
    c = Case(tmp_path, "reuse")
    c.runner(c.wt_a)
    c.runner(c.wt_b, STUB_GET_EXIT="0")
    splits = c.of("pane split")
    assert len(splits) == 1, f"Erwartet genau ein pane split, gesehen: {splits}"
    entry = c.entries()[CLAUDE]
    assert entry["pane_id"] == "pane-new-1", entry
    assert _same(entry["cwd"], c.wt_b), entry


# --- AC-2 -------------------------------------------------------------------

def test_id_file_lives_in_main_repo(tmp_path):
    c = Case(tmp_path, "location")
    c.runner(c.wt_a, STUB_LOCK_LOG=str(c.lock_log),
             STUB_LOCK_MAIN=str(c.lock_file()),
             STUB_LOCK_WT=str(c.lock_file(c.wt_a)))
    assert c.id_file().exists(), (
        f"herdr_plan_pane.json fehlt im Haupt-Repo; Worktree-Datei existiert: "
        f"{c.id_file(c.wt_a).exists()}")
    assert not c.id_file(c.wt_a).exists(), "ID-Datei liegt (auch) im Worktree"
    seen = c.lock_log.read_text().splitlines() if c.lock_log.exists() else []
    assert seen, "Stub wurde nicht aufgerufen"
    assert all(s.startswith("main=1") for s in seen), (
        f"Lock nicht waehrend des ganzen Laufs im Haupt-Repo: {seen}")
    assert all(s.endswith("wt=0") for s in seen), f"Lock im Worktree: {seen}"
    assert not c.lock_file().exists(), "Lock nach dem Lauf nicht entfernt"


# --- AC-3 -------------------------------------------------------------------

def test_distinct_claude_panes_keep_own_entries(tmp_path):
    c = Case(tmp_path, "distinct")
    c.runner(c.wt_a, pane="pane-A", HERDR_PANE_ID="pane-A")
    c.runner(c.wt_b, pane="pane-B", HERDR_PANE_ID="pane-B", STUB_GET_EXIT="0")
    assert len(c.of("pane split")) == 2, c.calls()
    panes = c.entries()
    assert set(panes) >= {"pane-A", "pane-B"}, panes
    assert panes["pane-A"]["pane_id"] != panes["pane-B"]["pane_id"], panes
    b_before = dict(panes["pane-B"])

    c.runner(c.wt_b, pane="pane-A", HERDR_PANE_ID="pane-A", STUB_GET_EXIT="0")
    assert len(c.of("pane split")) == 2, f"Erneuter Lauf fuer A splittete: {c.calls()}"
    panes = c.entries()
    assert panes["pane-B"] == b_before, panes
    assert _same(panes["pane-A"]["cwd"], c.wt_b), panes


# --- AC-4 -------------------------------------------------------------------

def test_dead_pane_is_replaced(tmp_path):
    c = Case(tmp_path, "dead")
    c.write_entries({CLAUDE: {"pane_id": "pane-old", "cwd": str(c.wt_a)},
                     "pane-other": {"pane_id": "pane-o", "cwd": str(c.wt_a)}})
    c.runner(c.wt_b, STUB_GET_EXIT="1")
    gets = c.of("pane get")
    assert gets and gets[0][2] == "pane-old", f"pane get fuer pane-old fehlt: {c.calls()}"
    assert len(c.of("pane split")) == 1, c.calls()
    panes = c.entries()
    assert panes[CLAUDE]["pane_id"] == "pane-new-1", panes
    assert _same(panes[CLAUDE]["cwd"], c.wt_b), panes
    assert panes["pane-other"] == {"pane_id": "pane-o", "cwd": str(c.wt_a)}, panes


# --- AC-5 -------------------------------------------------------------------

def test_pane_run_passes_target(tmp_path):
    c = Case(tmp_path, "target")
    c.runner(c.wt_a)
    runs = c.of("pane run")
    assert runs, c.calls()
    run = runs[0]
    assert run[2] == "pane-new-1", run
    command = run[-1]
    assert command.startswith("exec "), command
    tokens = shlex.split(command)
    assert tokens[-4:] == ["plan", "--watch", "--target", CLAUDE], tokens
    assert any(t.endswith("workflow.py") for t in tokens), tokens


# --- AC-6 -------------------------------------------------------------------

def test_watcher_switches_to_registered_base(tmp_path):
    c = Case(tmp_path, "switch")
    c.write_wf(c.wt_a, WF_X)
    c.write_wf(c.wt_b, WF_Y)
    c.write_entries({CLAUDE: {"pane_id": "pane-plan", "cwd": str(c.wt_a)}})
    res = c.watcher(c.wt_b)
    assert res.returncode == 0, res.stderr
    frame = _last_frame(res.stdout)
    assert WF_X in frame, f"Watcher zeigt nicht {WF_X}: {frame!r}"
    assert WF_Y not in frame, f"Watcher zeigt noch {WF_Y}: {frame!r}"


# --- AC-7 -------------------------------------------------------------------

def test_watcher_fail_open(tmp_path):
    c = Case(tmp_path, "failopen")
    c.write_wf(c.wt_a, WF_X)
    c.write_wf(c.wt_b, WF_Y)
    cases = (
        ("datei-fehlt", None),
        ("datei-kaputt", "{kaputt"),
        ("eintrag-fehlt", json.dumps({"panes": {"pane-andere": {
            "pane_id": "pane-plan", "cwd": str(c.wt_a)}}})),
        ("cwd-fehlt", json.dumps({"panes": {CLAUDE: {
            "pane_id": "pane-plan", "cwd": str(c.root / "gibt-es-nicht")}}})),
    )
    for label, content in cases:
        path = c.id_file()
        if content is None:
            if path.exists():
                path.unlink()
        else:
            path.write_text(content)
        res = c.watcher(c.wt_b)
        assert res.returncode == 0, (label, res.stderr)
        assert res.stderr == "", (label, res.stderr)
        frame = _last_frame(res.stdout)
        assert WF_Y in frame, (label, frame)
        assert WF_X not in frame, (label, frame)
