"""Richtige Issue-Nummer statt erster Ziffer im Namen; /40-tdd-red meldet RED (Issue #513).

Spec: docs/specs/fix-513-issue-nummer.md (AC-1 bis AC-10).

Vertraege, die diese Tests festlegen:
- `hook_utils.issue_number_from_name(name) -> str | None`: Namensregel ueber die
  an `-`/`_` getrennten Teile (erster Teil Zahl; Praefix fix/feat/feature/bug/issue/gh
  + Zahl; letzter Teil Zahl mit Nicht-Zahl davor; sonst None). Wirft nie.
- `hook_utils.workflow_issue_number(data) -> str | None`: State-Feld `issue_number`
  (Ziffern-String, optional mit `#`, oder positive Ganzzahl) vor Namensregel.
- `workflow.py start <name> --issue N` speichert `issue_number`; ungueltiges N -> Exit 1.
- `workflow.py find N` trifft auch ueber das State-Feld.
- `session_singleton_guard` nutzt dieselbe Regel und im Register das State-Feld.

Importfehler/fehlende Funktionen erscheinen als Test-FAIL: Module werden erst im
Testkoerper importiert, die CLI laeuft als Subprozess.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
TDD_RED_CMD = REPO_ROOT / "core" / "commands" / "40-tdd-red.md"
SYNC_SKILLS = REPO_ROOT / "scripts" / "sync_skills.py"


# --- Helpers ---------------------------------------------------------------

def _hook_utils():
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    import hook_utils  # noqa: PLC0415
    return hook_utils


def _workflow():
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _guard():
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    import session_singleton_guard  # noqa: PLC0415
    return session_singleton_guard


def _project(root: Path, active: "dict | None" = None) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    wf_dir = proj / ".claude" / "workflows"
    (wf_dir / "_log").mkdir(parents=True)
    (wf_dir / "_archive").mkdir()
    (proj / "_home").mkdir()
    if active is not None:
        (wf_dir / f"{active['name']}.json").write_text(json.dumps(active))
        (proj / ".claude" / "active_workflow").write_text(active["name"])
    return proj


def _env(proj: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    # Kein echtes gh: der abgekoppelte Titel-Abruf (#490) darf nichts nach aussen tun.
    bindir = proj / "_bin"
    bindir.mkdir(exist_ok=True)
    py = bindir / "python3"
    if not py.exists():
        py.symlink_to(sys.executable)
    env["PATH"] = str(bindir)
    return env


def _cli(proj: Path, *args: str):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args], capture_output=True,
                          text=True, env=_env(proj), cwd=str(proj), timeout=30)


# --- AC-1 -------------------------------------------------------------------

def test_name_rule_finds_real_number():
    hu = _hook_utils()
    cases = {
        "i18n-a2-e2e-2681": "2681",
        "e2e-2681": "2681",
        "p2p-77": "77",
        "fix-1761-xyz": "1761",
        "feat-106-login": "106",
        "513-foo": "513",
        "bug_42_crash": "42",
    }
    got = {name: hu.issue_number_from_name(name) for name in cases}
    assert got == cases


# --- AC-2 -------------------------------------------------------------------

def test_name_rule_returns_none_when_ambiguous():
    hu = _hook_utils()
    for name in ("i18n-feature", "fix-v2-login", "release-4-0-0", "", None):
        assert hu.issue_number_from_name(name) is None, name


# --- AC-3 -------------------------------------------------------------------

def test_state_field_wins_over_name():
    hu = _hook_utils()
    assert hu.workflow_issue_number({"name": "i18n-a2-e2e-18", "issue_number": "2681"}) == "2681"
    assert hu.workflow_issue_number({"name": "x", "issue_number": 2681}) == "2681"
    assert hu.workflow_issue_number({"name": "fix-12-a", "issue_number": "abc"}) == "12"


# --- AC-4 -------------------------------------------------------------------

def test_footer_and_status_use_real_number():
    wf = _workflow()
    data = {"name": "i18n-a2-e2e-2681", "current_phase": "phase4_approved"}
    assert wf.expected_footer_command(data) == "/40-tdd-red #2681"
    note = wf.status_note(data)
    assert note is not None
    assert "#2681" in note
    assert "#18" not in note


# --- AC-5 -------------------------------------------------------------------

def test_start_with_issue_flag(tmp_path):
    proj = _project(tmp_path)
    res = _cli(proj, "start", "login-neu", "--issue", "77")
    assert res.returncode == 0, res.stderr + res.stdout
    state = json.loads((proj / ".claude" / "workflows" / "login-neu.json").read_text())
    assert state.get("issue_number") == "77"

    proj2 = _project(tmp_path / "bad")
    res2 = _cli(proj2, "start", "login-neu", "--issue", "abc")
    assert res2.returncode == 1, res2.stderr + res2.stdout
    assert not (proj2 / ".claude" / "workflows" / "login-neu.json").exists()


# --- AC-6 -------------------------------------------------------------------

def test_find_uses_state_field(tmp_path):
    active = {"name": "login-neu", "workflow_type": "feature",
              "current_phase": "phase1_context", "issue_number": "77",
              "phase_transitions": [], "phase_log": []}
    proj = _project(tmp_path, active=active)
    res = _cli(proj, "find", "77")
    assert res.returncode == 0, res.stderr
    assert "GEFUNDEN: login-neu" in res.stdout, res.stdout
    assert "NAME=login-neu" in res.stdout, res.stdout


# --- AC-7 -------------------------------------------------------------------

def test_guard_uses_shared_rule():
    ssg = _guard()
    hu = _hook_utils()
    for name, expected in (("i18n-a2-e2e-2681", "2681"), ("fix-v2-login", None)):
        assert ssg._extract_issue_number(name) == expected, name
        assert ssg._extract_issue_number(name) == hu.issue_number_from_name(name), name


# --- AC-8 -------------------------------------------------------------------

def test_guard_register_uses_state_field(tmp_path, monkeypatch):
    ssg = _guard()
    hu = _hook_utils()
    root = tmp_path / "root"
    wf_dir = root / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "login-neu.json").write_text(json.dumps(
        {"name": "login-neu", "current_phase": "phase1_context", "issue_number": "77"}))
    monkeypatch.setattr(hu, "find_project_root", lambda: root)
    monkeypatch.setattr(ssg, "find_project_root", lambda: root, raising=False)
    monkeypatch.setattr(hu, "find_worktree_root", lambda: None)
    monkeypatch.setattr(ssg, "find_worktree_root", lambda: None, raising=False)
    monkeypatch.setattr(hu, "resolve_active_workflow", lambda: ("login-neu", "file"))
    monkeypatch.setattr(ssg, "resolve_active_workflow", lambda: ("login-neu", "file"),
                        raising=False)
    fields = ssg._context_fields(str(tmp_path))
    assert fields.get("workflow") == "login-neu"
    assert fields.get("issue") == "77", fields


# --- AC-9 -------------------------------------------------------------------

def test_tdd_red_command_marks_red():
    text = TDD_RED_CMD.read_text()
    reg = text.find("Register Artifacts")
    assert reg != -1
    mark = text.find("workflow.py mark-red", reg)
    assert mark != -1, "workflow.py mark-red fehlt nach 'Register Artifacts'"
    switch = text.find("phase phase6_implement", reg)
    assert switch != -1
    assert mark < switch, "mark-red muss vor dem Phasenwechsel stehen"
    res = subprocess.run([sys.executable, str(SYNC_SKILLS), "--check"], capture_output=True,
                         text=True, cwd=str(REPO_ROOT), timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr


# --- AC-10 ------------------------------------------------------------------

def test_phase5_after_mark_red_points_to_implement():
    wf = _workflow()
    data = {"name": "i18n-a2-e2e-2681", "current_phase": "phase5_tdd_red",
            "red_test_done": True}
    assert wf.expected_footer_command(data) == "/50-implement #2681"
