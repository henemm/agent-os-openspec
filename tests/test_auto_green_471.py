"""Automatische GREEN-Freigabe im Auto-Modus (Issue #471) — Tests zu AC-1 bis AC-21.

Spec: docs/specs/feat-471-auto-green.md

Festgelegte Vertraege (die Spec nennt sie nur sinngemaess):
- `workflow.py auto-green`: stdout enthaelt eine Zeile `AUTO_GREEN=done|human` und eine
  Zeile `REASON=...`, Exit immer 0; bei `human` bleibt die State-Datei byte-identisch.
- Bei `done`: `green_approved=True`, genau ein neuer `approvals`-Eintrag
  (gate="green", by="auto", mode="auto", `at` ISO-Zeitstempel,
  `evidence == {"artifact": <Pfad des juengsten test_output-Artefakts, wie registriert>}`),
  Phase bleibt `phase6_implement`, keine Marker-/Lock-Datei.
- `post_implementation_gate.py` ruft im Auto-Modus `workflow.autonomy_mode()` (lazy Import);
  bei Ausnahme gilt `manual`.
- Bewertet wird das juengste `test_output`-Artefakt der Phase `phase6_implement` mit
  `qa_gate.validate_test_output(filepath, trusted=True)`; bei Symlink/ausserhalb des
  Projekts/keiner regulaeren Datei wird `validate_test_output` gar nicht aufgerufen.

Fehlende Funktionen erscheinen pro Test als FAIL (Imports erst im Testkoerper bzw. Subprozess).
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
GATE_PY = HOOKS_DIR / "post_implementation_gate.py"
LISTENER_PY = HOOKS_DIR / "phase_listener.py"

WF = "feat-471-demo"
WF_CREATED = "2026-10-28T10:00:00.000000"
REL_GREEN = "logs/green-test.log"
REL_RED = "logs/red-test.log"

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
    "=================================== FAILURES ===================================\n"
    "___________________________________ test_beta __________________________________\n"
    "\n"
    "    def test_beta():\n"
    ">       assert compute() == 2\n"
    "E       assert 1 == 2\n"
    "\n"
    "tests/test_demo.py:9: AssertionError\n"
    "=========================== short test summary info ============================\n"
    "FAILED tests/test_demo.py::test_beta - assert 1 == 2\n"
    "========================= 1 failed, 2 passed in 0.15s ==========================\n"
)


# --- Helpers ---------------------------------------------------------------

def _env(proj: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    return env


def _wf_path(proj: Path) -> Path:
    return proj / ".claude" / "workflows" / f"{WF}.json"


def _state(proj: Path) -> dict:
    return json.loads(_wf_path(proj).read_text())


def _write_state(proj: Path, **fields) -> None:
    data = _state(proj)
    data.update(fields)
    _wf_path(proj).write_text(json.dumps(data))


def _artifact(path: str, *, type_: str = "test_output", phase: str = "phase6_implement") -> dict:
    return {"type": type_, "path": path, "description": "pytest run", "phase": phase,
            "created": datetime.now().isoformat()}


def _project(tmp_path: Path, *, mode: "str | None" = "auto", phase: str = "phase6_implement",
             red_done: bool = True, green_content: "str | None" = PYTEST_GREEN,
             artifacts: "list | None" = None, green_approved: bool = False) -> Path:
    """Temp-Projekt im Happy-Path-Zustand (Auto-Modus, phase6, RED belegt, GREEN-Artefakt)."""
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    if mode is not None:
        (proj / "openspec.yaml").write_text(f"autonomy:\n  mode: {mode}\n")
    (proj / "logs").mkdir()
    if green_content is not None:
        (proj / REL_GREEN).write_text(green_content)
    if artifacts is None:
        artifacts = [_artifact(REL_RED, phase="phase5_tdd_red"), _artifact(REL_GREEN)]
    _wf_path(proj).write_text(json.dumps({
        "name": WF, "workflow_type": "feature", "current_phase": phase,
        "created": WF_CREATED, "spec_file": "docs/specs/demo.md", "spec_approved": True,
        "red_test_done": red_done, "green_approved": green_approved,
        "test_artifacts": artifacts, "phase_transitions": [], "phase_log": [],
        "approvals": [],
    }))
    (proj / ".claude" / "active_workflow").write_text(WF)
    return proj


def _cli(args, proj: Path, active: str = WF, script: Path = WORKFLOW_PY):
    env = _env(proj)
    if active:
        env["OPENSPEC_ACTIVE_WORKFLOW"] = active
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, env=env,
                          cwd=str(proj), timeout=60)


def _auto_green(proj: Path, active: str = WF):
    res = _cli(["auto-green"], proj, active=active)
    assert res.returncode == 0, (
        f"auto-green muss immer Exit 0 liefern: rc={res.returncode} "
        f"stdout={res.stdout!r} stderr={res.stderr!r}"
    )
    m = re.search(r"^AUTO_GREEN=(\w+)\s*$", res.stdout, re.M)
    assert m, f"Zeile AUTO_GREEN=... fehlt: stdout={res.stdout!r} stderr={res.stderr!r}"
    assert re.search(r"^REASON=.+$", res.stdout, re.M), res.stdout
    return m.group(1), res


def _assert_human_unchanged(proj: Path, active: str = WF) -> None:
    sp = _wf_path(proj)
    before = sp.read_bytes() if sp.exists() else None
    verdict, res = _auto_green(proj, active=active)
    assert verdict == "human", res.stdout
    after = sp.read_bytes() if sp.exists() else None
    assert after == before, "State darf bei human nicht veraendert werden"


def _lock_path(proj: Path) -> Path:
    return proj / ".claude" / f"pending_validation_{WF}.json"


def _marker_path(proj: Path) -> Path:
    return proj / ".claude" / f"user_approved_validation_{WF}"


def _write_lock(proj: Path, created: float) -> Path:
    path = _lock_path(proj)
    path.write_text(json.dumps({
        "workflow": WF, "workflow_created": WF_CREATED,
        "created": created, "created_iso": "irrelevant",
    }))
    return path


def _run_hook(script: Path, proj: Path, payload: dict) -> subprocess.CompletedProcess:
    env = _env(proj)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    return subprocess.run([sys.executable, str(script)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env,
                          cwd=str(proj), timeout=60)


def _run_gate(proj: Path, file_path: str = "src/foo.py") -> subprocess.CompletedProcess:
    return _run_hook(GATE_PY, proj, {"tool_input": {"file_path": file_path}})


# --- AC-1 -------------------------------------------------------------------

def test_auto_green_happy_path_sets_green_approved(tmp_path):
    """AC-1: auto + phase6 + RED + GREEN-Artefakt -> done, green_approved, Phase bleibt."""
    proj = _project(tmp_path)
    verdict, res = _auto_green(proj)
    assert verdict == "done", res.stdout
    data = _state(proj)
    assert data["green_approved"] is True
    assert data["current_phase"] == "phase6_implement"


# --- AC-2 -------------------------------------------------------------------

def test_auto_green_records_approval_with_evidence(tmp_path):
    """AC-2: genau ein neuer approvals-Eintrag, Evidence = Pfad des juengsten Artefakts."""
    older = "logs/green-old.log"
    proj = _project(tmp_path, artifacts=[
        _artifact(REL_RED, phase="phase5_tdd_red"),
        _artifact(older),
        _artifact(REL_GREEN),
    ])
    (proj / older).write_text(PYTEST_GREEN)
    verdict, res = _auto_green(proj)
    assert verdict == "done", res.stdout
    approvals = _state(proj)["approvals"]
    assert len(approvals) == 1, approvals
    entry = approvals[0]
    assert (entry["gate"], entry["by"], entry["mode"]) == ("green", "auto", "auto"), entry
    assert datetime.fromisoformat(entry["at"])
    assert entry["evidence"] == {"artifact": REL_GREEN}, entry


# --- AC-3 -------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["manual", None])
def test_human_in_manual_mode_state_unchanged(tmp_path, mode):
    """AC-3: manual bzw. kein autonomy-Abschnitt -> human, State byte-identisch."""
    proj = _project(tmp_path, mode=mode)
    _assert_human_unchanged(proj)


# --- AC-4 -------------------------------------------------------------------

@pytest.mark.parametrize("phase", ["phase5_tdd_red", "phase6b_adversary"])
def test_human_in_wrong_phase(tmp_path, phase):
    """AC-4: Phase ungleich phase6_implement -> human, State byte-identisch."""
    proj = _project(tmp_path, phase=phase)
    _assert_human_unchanged(proj)


# --- AC-5 -------------------------------------------------------------------

def test_human_without_red_test_done(tmp_path):
    """AC-5: ohne red_test_done -> human, State byte-identisch."""
    proj = _project(tmp_path, red_done=False)
    _assert_human_unchanged(proj)


# --- AC-6 -------------------------------------------------------------------

def test_human_without_green_artifact(tmp_path):
    """AC-6: kein test_output-Artefakt der Phase phase6_implement -> human."""
    # a) nur RED-Artefakt der Phase phase5_tdd_red
    a = _project(tmp_path / "a", artifacts=[_artifact(REL_RED, phase="phase5_tdd_red")])
    _assert_human_unchanged(a)
    # b) Artefakt der richtigen Phase, aber anderen Typs
    b = _project(tmp_path / "b", artifacts=[_artifact(REL_GREEN, type_="screenshot")])
    _assert_human_unchanged(b)
    # c) gar keine Artefakte
    c = _project(tmp_path / "c", artifacts=[])
    _assert_human_unchanged(c)


# --- AC-7 -------------------------------------------------------------------

def test_human_when_stop_locked(tmp_path):
    """AC-7: aktiver Stop-Lock -> human, State byte-identisch."""
    proj = _project(tmp_path)
    (proj / ".claude" / "stop_lock.json").write_text(json.dumps({"enabled": True}))
    _assert_human_unchanged(proj)


# --- AC-8 -------------------------------------------------------------------

def test_human_when_already_green_approved(tmp_path):
    """AC-8: green_approved schon gesetzt -> human, kein zweiter approvals-Eintrag."""
    proj = _project(tmp_path, green_approved=True)
    _assert_human_unchanged(proj)
    assert _state(proj)["approvals"] == []


# --- AC-9 -------------------------------------------------------------------

def test_settings_local_auto_has_no_effect(tmp_path):
    """AC-9: auto nur in settings.local.json, wirksame Config ohne Auto -> human."""
    proj = _project(tmp_path, mode=None)
    (proj / "openspec.yaml").write_text("project:\n  name: x\n")
    local = json.dumps({"autonomy": {"mode": "auto"}})
    (proj / ".claude" / "settings.local.json").write_text(local)
    (proj / "settings.local.json").write_text(local)
    _assert_human_unchanged(proj)


# --- AC-10 ------------------------------------------------------------------

def test_broken_inputs_fail_closed(tmp_path):
    """AC-10: kaputter State, kaputte Config, fehlender Workflow -> human, nichts veraendert."""
    # a) kaputter State (kein JSON)
    a = _project(tmp_path / "a")
    _wf_path(a).write_text("{not json")
    _assert_human_unchanged(a)
    # b) nicht lesbare Config
    b = _project(tmp_path / "b")
    (b / "openspec.yaml").write_text("autonomy: [unclosed\n  mode: : auto\n\t- x")
    _assert_human_unchanged(b)
    # c) fehlender aktiver Workflow (weder Datei noch Env-Var)
    c = _project(tmp_path / "c")
    (c / ".claude" / "active_workflow").unlink()
    _assert_human_unchanged(c, active="")
    # d) aktiver Name zeigt auf nicht existierenden Workflow
    d = _project(tmp_path / "d")
    (d / ".claude" / "active_workflow").write_text("gibt-es-nicht")
    _assert_human_unchanged(d, active="gibt-es-nicht")


# --- AC-11 ------------------------------------------------------------------

def test_gate_auto_mode_creates_no_lock(tmp_path):
    """AC-11: Auto-Modus, kein Lock -> Edit erlaubt, kein pending_validation-Lock."""
    proj = _project(tmp_path)
    res = _run_gate(proj)
    assert res.returncode == 0, res.stderr
    assert not _lock_path(proj).exists(), "Im Auto-Modus darf kein Lock angelegt werden"


# --- AC-12 ------------------------------------------------------------------

def test_gate_auto_mode_no_block_after_window_with_existing_lock(tmp_path):
    """AC-12: Auto-Modus, Lock aelter als Batch-Fenster, kein Marker -> kein Block, Lock bleibt."""
    proj = _project(tmp_path)
    lock = _write_lock(proj, created=time.time() - 20 * 60)
    before = lock.read_bytes()
    res = _run_gate(proj)
    assert res.returncode == 0, res.stderr
    assert lock.exists() and lock.read_bytes() == before, "Lock muss unveraendert liegen bleiben"


# --- AC-13 ------------------------------------------------------------------

def test_gate_manual_mode_unchanged(tmp_path):
    """AC-13: manual -> alter Lock blockt (Exit 2), erster Edit legt Lock an."""
    proj = _project(tmp_path / "old", mode="manual")
    _write_lock(proj, created=time.time() - 20 * 60)
    res = _run_gate(proj)
    assert res.returncode == 2, (res.returncode, res.stderr)
    assert "BLOCKED" in res.stderr

    fresh = _project(tmp_path / "fresh", mode="manual")
    res = _run_gate(fresh)
    assert res.returncode == 0, res.stderr
    assert _lock_path(fresh).exists(), "Erster Edit ohne Lock legt den Lock weiterhin an"


# --- AC-14 ------------------------------------------------------------------

_GATE_WRAPPER = """\
import sys, runpy
sys.path.insert(0, {hooks!r})
import workflow
def _boom(*a, **k):
    raise RuntimeError("autonomy_mode kaputt")
workflow.autonomy_mode = _boom
sys.argv = [{gate!r}]
runpy.run_path({gate!r}, run_name="__main__")
"""


def test_gate_falls_back_to_manual_on_error(tmp_path):
    """AC-14: autonomy_mode() wirft -> Gate verhaelt sich wie manual (fail-closed)."""
    wrapper = tmp_path / "gate_wrapper.py"
    wrapper.write_text(_GATE_WRAPPER.format(hooks=str(HOOKS_DIR), gate=str(GATE_PY)))

    # Config auto, alter Lock: manual-Verhalten = Block
    old = _project(tmp_path / "old", mode="auto")
    _write_lock(old, created=time.time() - 20 * 60)
    res = _run_hook(wrapper, old, {"tool_input": {"file_path": "src/foo.py"}})
    assert res.returncode == 2, (res.returncode, res.stdout, res.stderr)
    assert "BLOCKED" in res.stderr

    # Config auto, kein Lock: manual-Verhalten = Lock wird angelegt
    fresh = _project(tmp_path / "fresh", mode="auto")
    res = _run_hook(wrapper, fresh, {"tool_input": {"file_path": "src/foo.py"}})
    assert res.returncode == 0, res.stderr
    assert _lock_path(fresh).exists()


# --- AC-15 ------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["manual", "auto"])
def test_listener_go_still_works(tmp_path, mode):
    """AC-15: `go` setzt green_approved und den Marker (bei Lock) in beiden Modi."""
    proj = _project(tmp_path, mode=mode)
    lock = _write_lock(proj, created=987654.321)
    res = _run_hook(LISTENER_PY, proj, {"prompt": "go"})
    assert res.returncode == 0, res.stderr
    assert _state(proj)["green_approved"] is True
    marker = _marker_path(proj)
    assert marker.exists()
    assert marker.read_text().strip() == str(json.loads(lock.read_text())["created"])


# --- AC-16 ------------------------------------------------------------------

def _step6(text: str) -> str:
    m = re.search(r"### Step 6.*?(?=### Step 7)", text, re.S)
    assert m, "Step 6 nicht gefunden"
    return m.group(0)


def test_command_and_skill_branch_on_autonomy():
    """AC-16: Command und Skill verzweigen in Step 6 nach Modus; kein Skill-Drift."""
    needed = ("workflow.py autonomy", "AUTONOMY=auto", "workflow.py auto-green",
              "AUTO_GREEN=done", "AUTO_GREEN=human", "`go`")
    for rel in ("core/commands/50-implement.md", "skills/50-implement/SKILL.md"):
        step = _step6((REPO_ROOT / rel).read_text())
        for token in needed:
            assert token in step, f"{rel}: Step 6 enthaelt '{token}' nicht"
    res = subprocess.run([sys.executable, "scripts/sync_skills.py", "--check"],
                         capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120)
    assert res.returncode == 0, f"Skill-Drift: {res.stdout!r} {res.stderr!r}"


# --- AC-17 ------------------------------------------------------------------

def test_no_marker_file_written(tmp_path):
    """AC-17: nach auto-green done kein Marker, kein Lock; auch das Gate legt nichts an."""
    proj = _project(tmp_path)
    verdict, res = _auto_green(proj)
    assert verdict == "done", res.stdout
    assert not _marker_path(proj).exists()
    assert not _lock_path(proj).exists()
    assert not list((proj / ".claude").glob("user_approved_validation_*"))
    assert not list((proj / ".claude").glob("pending_validation_*"))
    gate = _run_gate(proj)
    assert gate.returncode == 0, gate.stderr
    assert not _marker_path(proj).exists()
    assert not _lock_path(proj).exists()


# --- AC-18 ------------------------------------------------------------------

def test_artifact_with_3_passed_gives_done(tmp_path):
    """AC-18: regulaere Datei im Projekt mit `3 passed` -> done."""
    proj = _project(tmp_path, green_content=PYTEST_GREEN)
    verdict, res = _auto_green(proj)
    assert verdict == "done", res.stdout
    assert _state(proj)["green_approved"] is True


# --- AC-19 ------------------------------------------------------------------

def test_artifact_with_failures_gives_human(tmp_path):
    """AC-19: juengstes Artefakt `1 failed, 2 passed` -> human, auch wenn ein aelteres gruen war."""
    older = "logs/green-old.log"
    proj = _project(tmp_path, green_content=PYTEST_RED, artifacts=[
        _artifact(REL_RED, phase="phase5_tdd_red"),
        _artifact(older),
        _artifact(REL_GREEN),
    ])
    (proj / older).write_text(PYTEST_GREEN)
    _assert_human_unchanged(proj)


# --- AC-20 ------------------------------------------------------------------

def test_artifact_without_result_empty_or_missing_gives_human(tmp_path):
    """AC-20: leere Datei, Text ohne Testausgabe oder fehlende Datei -> human."""
    empty = _project(tmp_path / "empty", green_content="")
    _assert_human_unchanged(empty)
    text = _project(tmp_path / "text",
                    green_content="Alles ist wunderbar, ich habe nichts ausgefuehrt.\n" * 5)
    _assert_human_unchanged(text)
    missing = _project(tmp_path / "missing", green_content=None)
    assert not (missing / REL_GREEN).exists()
    _assert_human_unchanged(missing)


# --- AC-21 ------------------------------------------------------------------

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


def _run_spied_auto_green(proj: Path, tmp_path: Path) -> "tuple[str, Path, subprocess.CompletedProcess]":
    sentinel = tmp_path / "validate_called.txt"
    wrapper = tmp_path / "spy_wrapper.py"
    wrapper.write_text(_SPY_WRAPPER.format(hooks=str(HOOKS_DIR), sentinel=str(sentinel),
                                           wf=str(WORKFLOW_PY)))
    res = _cli([], proj, script=wrapper)
    assert res.returncode == 0, (res.returncode, res.stdout, res.stderr)
    m = re.search(r"^AUTO_GREEN=(\w+)\s*$", res.stdout, re.M)
    assert m, f"Zeile AUTO_GREEN=... fehlt: {res.stdout!r} {res.stderr!r}"
    return m.group(1), sentinel, res


def test_artifact_outside_project_or_symlink_gives_human(tmp_path):
    """AC-21: Pfad ausserhalb (absolut/..) oder Symlink -> human, State identisch, nicht gelesen."""
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "green.log"
    outside_file.write_text(PYTEST_GREEN)

    def case(label: str, art_path: str, setup=None):
        base = tmp_path / label
        proj = _project(base, artifacts=[_artifact(REL_RED, phase="phase5_tdd_red"),
                                         _artifact(art_path)])
        if setup:
            setup(proj)
        before = _wf_path(proj).read_bytes()
        verdict, sentinel, res = _run_spied_auto_green(proj, base)
        assert verdict == "human", (label, res.stdout)
        assert _wf_path(proj).read_bytes() == before, label
        assert not sentinel.exists(), f"{label}: Datei darf nicht ausgewertet werden"

    # a) absoluter Pfad ausserhalb des Projekts
    case("abs", str(outside_file))
    # b) relativer Pfad mit .. aus dem Projekt heraus
    case("dotdot", os.path.relpath(outside_file, tmp_path / "dotdot" / "proj"))
    # c) Symlink im Projekt auf gruene Datei im Projekt
    def mk_link(proj):
        (proj / "logs" / "link.log").symlink_to(proj / REL_GREEN)
    case("symlink", "logs/link.log", setup=mk_link)
    # d) Symlink im Projekt auf gruene Datei ausserhalb
    def mk_out_link(proj):
        (proj / "logs" / "link2.log").symlink_to(outside_file)
    case("symlink_out", "logs/link2.log", setup=mk_out_link)
