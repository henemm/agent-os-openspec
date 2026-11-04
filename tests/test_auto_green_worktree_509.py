"""auto-green findet das GREEN-Artefakt im Worktree (Issue #509) — Tests zu AC-1 bis AC-12.

Spec: docs/specs/fix-509-auto-green-worktree.md

Aufbau (alle Worktree-Faelle, echtes `tmp_path`, kein Mock der Pfadaufloesung ausser AC-11):
- Hauptrepo `<main>` mit `.git`-Ordner, State unter `<main>/.claude/workflows/`,
  Auto-Modus in `<main>/openspec.yaml`, Workflow in `phase6_implement` mit `red_test_done: true`.
- Worktree mit `.git`-Datei (`gitdir: <main>/.git/worktrees/<n>`) und worktree-lokalem
  `.claude/active_workflow`; `cwd` und `CLAUDE_PROJECT_DIR` = Worktree.
- GREEN-Log mit "3 passed" unter `docs/artifacts/<wf>/green.log`.

Vertrag wie in tests/test_auto_green_471.py: stdout `AUTO_GREEN=done|human` + `REASON=...`,
Exit immer 0; bei `human` bleibt die State-Datei byte-identisch.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

WF = "fix-509-demo"
WF_CREATED = "2026-11-04T10:00:00.000000"
REL_GREEN = f"docs/artifacts/{WF}/green.log"
REL_RED = f"docs/artifacts/{WF}/red.log"

REASON_PATH = ("GREEN-Artefakt fehlt, ist keine regulaere Datei "
               "oder liegt ausserhalb des Projekts")

PYTEST_GREEN = (
    "============================= test session starts ==============================\n"
    "platform linux -- Python 3.11.9, pytest-8.2.0, pluggy-1.5.0\n"
    "rootdir: /work/demo\n"
    "collected 3 items\n"
    "\n"
    "tests/test_demo.py::test_alpha PASSED                                    [ 33%]\n"
    "tests/test_demo.py::test_beta PASSED                                     [ 66%]\n"
    "tests/test_demo.py::test_gamma PASSED                                    [100%]\n"
    "\n"
    "============================== 3 passed in 0.12s ===============================\n"
)

PYTEST_RED = (
    "============================= test session starts ==============================\n"
    "platform linux -- Python 3.11.9, pytest-8.2.0, pluggy-1.5.0\n"
    "rootdir: /work/demo\n"
    "collected 3 items\n"
    "\n"
    "tests/test_demo.py::test_alpha PASSED                                    [ 33%]\n"
    "tests/test_demo.py::test_beta FAILED                                     [ 66%]\n"
    "tests/test_demo.py::test_gamma PASSED                                    [100%]\n"
    "\n"
    "=========================== short test summary info ============================\n"
    "FAILED tests/test_demo.py::test_beta - assert 1 == 2\n"
    "========================= 1 failed, 2 passed in 0.15s ==========================\n"
)


# --- Helpers ---------------------------------------------------------------

def _artifact(path: str, *, phase: str = "phase6_implement") -> dict:
    return {"type": "test_output", "path": path, "description": "pytest run",
            "phase": phase, "created": datetime.now().isoformat()}


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


class Setup:
    def __init__(self, main: Path, wt: Path, session: Path, home: Path):
        self.main = main
        self.wt = wt
        self.session = session  # cwd + CLAUDE_PROJECT_DIR
        self.home = home

    @property
    def state_path(self) -> Path:
        return self.main / ".claude" / "workflows" / f"{WF}.json"

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())

    def env(self) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("HERDR_", "OPENSPEC_", "CLAUDE_"))}
        env["CLAUDE_PROJECT_DIR"] = str(self.session)
        env["HOME"] = str(self.home)
        return env


def _setup(tmp_path: Path, *, art_path: str = REL_GREEN, wt_outside: bool = False,
           main_session: bool = False) -> Setup:
    """Hauptrepo + Worktree im Happy-Path-Zustand, aber noch ohne GREEN-Log."""
    main = tmp_path / "main"
    (main / ".git").mkdir(parents=True)
    (main / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (main / "openspec.yaml").write_text("autonomy:\n  mode: auto\n")
    home = tmp_path / "_home"
    home.mkdir()

    wt = (tmp_path / "wt-sibling") if wt_outside else (main / ".claude" / "worktrees" / "wt")
    wt.mkdir(parents=True)
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {main}/.git/worktrees/wt\n")
    (wt / ".claude").mkdir()
    (wt / ".claude" / "active_workflow").write_text(WF)
    if main_session:
        (main / ".claude" / "active_workflow").write_text(WF)

    s = Setup(main, wt, main if main_session else wt, home)
    s.state_path.write_text(json.dumps({
        "name": WF, "workflow_type": "bugfix", "current_phase": "phase6_implement",
        "created": WF_CREATED, "spec_file": "docs/specs/demo.md", "spec_approved": True,
        "red_test_done": True, "green_approved": False,
        "test_artifacts": [_artifact(REL_RED, phase="phase5_tdd_red"), _artifact(art_path)],
        "phase_transitions": [], "phase_log": [], "approvals": [],
    }))
    return s


def _run(s: Setup, script: Path = WORKFLOW_PY, args=("auto-green",)):
    res = subprocess.run([sys.executable, str(script), *args], capture_output=True,
                         text=True, env=s.env(), cwd=str(s.session), timeout=30)
    assert res.returncode == 0, (res.returncode, res.stdout, res.stderr)
    m = re.search(r"^AUTO_GREEN=(\w+)\s*$", res.stdout, re.M)
    assert m, f"Zeile AUTO_GREEN=... fehlt: stdout={res.stdout!r} stderr={res.stderr!r}"
    r = re.search(r"^REASON=(.*)$", res.stdout, re.M)
    assert r, res.stdout
    return m.group(1), r.group(1), res


def _assert_done(s: Setup) -> None:
    verdict, reason, res = _run(s)
    assert verdict == "done", (reason, res.stdout, res.stderr)
    assert s.state()["green_approved"] is True


def _assert_human(s: Setup, reason_part: "str | tuple" = REASON_PATH) -> str:
    before = s.state_path.read_bytes()
    verdict, reason, res = _run(s)
    assert verdict == "human", (reason, res.stdout, res.stderr)
    parts = (reason_part,) if isinstance(reason_part, str) else reason_part
    assert any(p in reason for p in parts), f"Grund {reason!r} erwartet einen von {parts!r}"
    assert s.state_path.read_bytes() == before, "State darf bei human nicht veraendert werden"
    return reason


_SPY_WRAPPER = """\
import sys, runpy
sys.path.insert(0, {hooks!r})
import qa_gate
_orig = qa_gate.validate_test_output
def _spy(*a, **k):
    with open({sentinel!r}, "a") as fh:
        fh.write(repr(a) + "\\n")
    return _orig(*a, **k)
qa_gate.validate_test_output = _spy
sys.argv = [{wf!r}, "auto-green"]
runpy.run_path({wf!r}, run_name="__main__")
"""


# --- AC-1 -------------------------------------------------------------------

def test_relative_artifact_only_in_worktree_gives_done(tmp_path):
    """AC-1: GREEN-Log nur im Worktree (unter .claude/worktrees/wt), relativ -> done."""
    s = _setup(tmp_path)
    _write(s.wt / REL_GREEN, PYTEST_GREEN)
    assert not (s.main / REL_GREEN).exists()
    _assert_done(s)
    data = s.state()
    assert data["approvals"], "approvals-Eintrag fehlt"
    assert data["approvals"][-1].get("evidence") == {"artifact": REL_GREEN}


# --- AC-2 -------------------------------------------------------------------

def test_worktree_outside_main_repo_gives_done(tmp_path):
    """AC-2: Worktree als Geschwister-Ordner von <main>, GREEN-Log nur dort -> done."""
    s = _setup(tmp_path, wt_outside=True)
    _write(s.wt / REL_GREEN, PYTEST_GREEN)
    assert not (s.main / REL_GREEN).exists()
    _assert_done(s)


# --- AC-3 -------------------------------------------------------------------

def test_worktree_copy_wins_over_main_repo(tmp_path):
    """AC-3: Worktree rot, Hauptrepo gruen am selben Pfad -> human (Worktree gewinnt)."""
    s = _setup(tmp_path)
    _write(s.wt / REL_GREEN, PYTEST_RED)
    _write(s.main / REL_GREEN, PYTEST_GREEN)
    _assert_human(s, ("nicht gruen", "FAILED/ERROR-Zeile"))


# --- AC-4 -------------------------------------------------------------------

def test_falls_back_to_main_repo_when_absent_in_worktree(tmp_path):
    """AC-4: Worktree-Sitzung, GREEN-Log nur im Hauptrepo -> done (Rueckfall)."""
    s = _setup(tmp_path)
    _write(s.main / REL_GREEN, PYTEST_GREEN)
    assert not (s.wt / REL_GREEN).exists()
    _assert_done(s)


# --- AC-5 -------------------------------------------------------------------

def test_symlink_in_worktree_gives_human(tmp_path):
    """AC-5: Symlink im Worktree (Ziel im Worktree bzw. ausserhalb) -> human, nicht gelesen."""
    outside = _write(tmp_path / "outside" / "green.log", PYTEST_GREEN)

    def case(label: str, target_fn):
        base = tmp_path / label
        base.mkdir()
        s = _setup(base)
        link = s.wt / REL_GREEN
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target_fn(s))
        sentinel = base / "validate_called.txt"
        wrapper = base / "spy_wrapper.py"
        wrapper.write_text(_SPY_WRAPPER.format(hooks=str(HOOKS_DIR), sentinel=str(sentinel),
                                               wf=str(WORKFLOW_PY)))
        before = s.state_path.read_bytes()
        verdict, reason, res = _run(s, script=wrapper, args=())
        assert verdict == "human", (label, reason, res.stdout, res.stderr)
        assert REASON_PATH in reason, (label, reason)
        assert s.state_path.read_bytes() == before, label
        assert not sentinel.exists(), f"{label}: validate_test_output darf nicht laufen"

    case("in_wt", lambda s: _write(s.wt / "docs" / "real-green.log", PYTEST_GREEN))
    case("to_outside", lambda s: outside)


# --- AC-6 -------------------------------------------------------------------

def test_path_outside_worktree_gives_human(tmp_path):
    """AC-6: `..` aus dem Worktree (nach draussen / ins Hauptrepo), absolut draussen -> human."""
    outside = _write(tmp_path / "outside" / "green.log", PYTEST_GREEN)

    # a) relativer Pfad mit .., der aus dem Worktree nach ausserhalb fuehrt
    base_a = tmp_path / "a"
    base_a.mkdir()
    wt_a = base_a / "main" / ".claude" / "worktrees" / "wt"
    rel_a = os.path.relpath(outside, wt_a)
    assert rel_a.startswith("..")
    s = _setup(base_a, art_path=rel_a)
    assert (s.wt / rel_a).exists()
    _assert_human(s)

    # b) relativer Pfad mit .., der aus dem Worktree auf ein gruenes Log im Hauptrepo fuehrt
    base_b = tmp_path / "b"
    base_b.mkdir()
    main_b = base_b / "main"
    wt_b = main_b / ".claude" / "worktrees" / "wt"
    rel_b = os.path.relpath(main_b / REL_GREEN, wt_b)
    assert rel_b.startswith("..")
    s = _setup(base_b, art_path=rel_b)
    _write(s.main / REL_GREEN, PYTEST_GREEN)
    assert (s.wt / rel_b).exists()
    _assert_human(s)

    # c) absoluter Pfad ausserhalb von Worktree und Hauptrepo
    base_c = tmp_path / "c"
    base_c.mkdir()
    s = _setup(base_c, art_path=str(outside))
    _assert_human(s)


# --- AC-7 -------------------------------------------------------------------

def test_non_regular_file_in_worktree_gives_human(tmp_path):
    """AC-7: Ordner bzw. FIFO am registrierten Pfad im Worktree -> human, ohne zu blockieren."""
    base_d = tmp_path / "dir"
    base_d.mkdir()
    s = _setup(base_d)
    (s.wt / REL_GREEN).mkdir(parents=True)
    _assert_human(s)

    base_f = tmp_path / "fifo"
    base_f.mkdir()
    s = _setup(base_f)
    (s.wt / REL_GREEN).parent.mkdir(parents=True)
    os.mkfifo(s.wt / REL_GREEN)
    _assert_human(s)  # subprocess.run(timeout=30) -> TimeoutExpired, falls es blockiert


# --- AC-8 -------------------------------------------------------------------

def test_absolute_paths_inside_worktree_or_project_give_done(tmp_path):
    """AC-8: Worktree ausserhalb des Hauptrepos; absoluter Pfad in Worktree bzw. Hauptrepo -> done."""
    base_a = tmp_path / "a"
    base_a.mkdir()
    abs_wt = base_a / "wt-sibling" / REL_GREEN
    s = _setup(base_a, art_path=str(abs_wt), wt_outside=True)
    _write(abs_wt, PYTEST_GREEN)
    _assert_done(s)

    base_b = tmp_path / "b"
    base_b.mkdir()
    abs_main = base_b / "main" / REL_GREEN
    s = _setup(base_b, art_path=str(abs_main), wt_outside=True)
    _write(abs_main, PYTEST_GREEN)
    _assert_done(s)


# --- AC-9 -------------------------------------------------------------------

def test_main_repo_session_unchanged(tmp_path):
    """AC-9: Hauptrepo-Sitzung: (a) Log im Hauptrepo -> done, (b) nur im Worktree -> human."""
    base_a = tmp_path / "a"
    base_a.mkdir()
    s = _setup(base_a, main_session=True)
    _write(s.main / REL_GREEN, PYTEST_GREEN)
    _assert_done(s)

    base_b = tmp_path / "b"
    base_b.mkdir()
    s = _setup(base_b, main_session=True)
    _write(s.main / ".claude" / "worktrees" / "wt" / REL_GREEN, PYTEST_GREEN)
    assert not (s.main / REL_GREEN).exists()
    _assert_human(s)


# --- AC-10 ------------------------------------------------------------------

def test_stop_lock_in_worktree_applies(tmp_path):
    """AC-10: Stop-Lock im Worktree (Ablageort seit #422) gilt in der Worktree-Sitzung -> human."""
    s = _setup(tmp_path)
    _write(s.wt / REL_GREEN, PYTEST_GREEN)
    (s.wt / ".claude" / "stop_lock.json").write_text(json.dumps({"enabled": True}))
    _assert_human(s, "Stop-Lock aktiv")


# --- AC-11 ------------------------------------------------------------------

def test_green_artifact_file_uses_worktree_first_root(tmp_path, monkeypatch):
    """AC-11: _green_artifact_file loest relative Pfade ueber _worktree_first_root auf."""
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow

    main = tmp_path / "main"
    (main / ".git").mkdir(parents=True)
    x = tmp_path / "x"
    _write(x / REL_GREEN, PYTEST_GREEN)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main))
    monkeypatch.chdir(main)
    assert workflow.find_project_root() == main
    assert not (main / REL_GREEN).exists()

    monkeypatch.setattr(workflow, "_worktree_first_root", lambda rel: x)
    assert workflow._green_artifact_file(REL_GREEN) == (x / REL_GREEN).resolve()


# --- AC-12 ------------------------------------------------------------------

def test_changelog_mentions_509():
    """AC-12: CHANGELOG.md nennt #509 unter [Unreleased] oder im direkt folgenden,
    obersten Versionsabschnitt `## [x.y.z]` (Release im selben PR geschnitten)."""
    text = CHANGELOG.read_text()
    start = text.index("## [Unreleased]")
    m = re.compile(r"^## \[\d+\.\d+\.\d+\]", re.M).search(text, start + 1)
    assert m, "Kein Versionsabschnitt nach [Unreleased]"
    nxt = text.find("\n## [", m.end())
    section = text[start:nxt if nxt != -1 else len(text)]
    assert "#509" in section, "Kein #509-Eintrag unter [Unreleased] oder oberster Version"
