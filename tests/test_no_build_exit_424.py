"""Tests fuer Issue #424: "nichts bauen" bekommt einen sauberen Ausgang.

Befund: Nach einer Analyse mit der PO-Entscheidung "nichts bauen" bleibt der
Workflow in phase2_analyse. Die Fusszeilenpruefung verlangt `/20-analyse` und
lehnt `/99-reset` ab; `abandon` existiert, ist aber nirgends verlinkt.

Loesung laut Spec: `workflow.py no-build --reason "..."` (nur phase1/phase2,
Begruendung Pflicht, Feld per set-field gesperrt) -> next_step() nennt
`/99-reset`; `/99-reset` ruft fuer solche Workflows `abandon --reason` auf.

ACs laut docs/specs/infra/fix-405-424-workflow-ausgaenge.md (AC-6 bis AC-11).
Hermetische Subprozess-Tests nach Vorlage tests/test_write_log_phases_111.py
und tests/test_footer_gate_234.py (CLAUDE_PROJECT_DIR=tmp_path, `.git` als
Verzeichnis, echte Aufrufe von workflow.py und footer_gate.py).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import workflow  # noqa: E402

WF_NAME = "fix-424-nichts-bauen"
PROMPT_ID = "42424242-0000-1111-2222-333333333333"
REASON = "Analyse ergab: Verhalten ist gewollt, nichts zu bauen"


# --- Helpers ---------------------------------------------------------------

def _env(project: Path) -> dict:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF_NAME
    env.pop("OPENSPEC_FRAMEWORK", None)
    return env


def _run_workflow(project: Path, args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py")] + args,
        capture_output=True, text=True, env=_env(project), cwd=str(project),
    )


def _run_footer_gate(project: Path, du_command: str) -> subprocess.CompletedProcess:
    """footer_gate.py als Stop-Hook, mit einer echten Abschlussnachricht."""
    message = (
        "Analyse abgeschlossen. Entscheidung des PO: nichts bauen.\n\n"
        f"❗ Du: `{du_command}` — der naechste Pflicht-Schritt\n"
        "⚙ /20-analyse · agent-os-openspec"
    )
    payload = {
        "session_id": "sess-424",
        "hook_event_name": "Stop",
        "cwd": str(project),
        "prompt_id": PROMPT_ID,
        "last_assistant_message": message,
    }
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "footer_gate.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env=_env(project), cwd=str(project),
    )


def _make_project(project: Path, phase: str = "phase2_analyse") -> Path:
    """Main-Repo (.git als Verzeichnis) mit aktivem Workflow ohne Spec."""
    project.mkdir(parents=True, exist_ok=True)
    (project / ".git").mkdir(exist_ok=True)
    wf_dir = project / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "name": WF_NAME,
        "workflow_type": "feature",
        "current_phase": phase,
        "context_file": "docs/context/fix-424.md",
        "spec_approved": False,
        "phase_transitions": [],
        "phase_log": [],
        "test_artifacts": [],
    }
    if phase == "phase3_spec":
        data["spec_file"] = "docs/specs/fix-424.md"
    wf_file = wf_dir / f"{WF_NAME}.json"
    wf_file.write_text(json.dumps(data))
    (project / ".claude" / "active_workflow").write_text(WF_NAME)
    return wf_file


def _state(project: Path) -> dict:
    return json.loads(
        (project / ".claude" / "workflows" / f"{WF_NAME}.json").read_text()
    )


# --- AC-6 ------------------------------------------------------------------

def test_no_build_ohne_begruendung_schlaegt_fehl(tmp_path):
    """AC-6: no-build ohne --reason bzw. mit leerer Begruendung -> Exit 1,
    Usage des Befehls auf stderr, no_build_reason bleibt ungesetzt."""
    _make_project(tmp_path)

    for args in (["no-build"], ["no-build", "--reason", ""], ["no-build", "--reason", "   "]):
        result = _run_workflow(tmp_path, args)
        assert result.returncode == 1, f"{args}: Exit {result.returncode}"
        assert "Usage: workflow.py no-build" in result.stderr, (
            f"{args}: keine Usage des no-build-Befehls auf stderr: {result.stderr.strip()!r}"
        )
        assert "--reason" in result.stderr
        assert "no_build_reason" not in _state(tmp_path), args


# --- AC-7 ------------------------------------------------------------------

def test_no_build_ausserhalb_phase1_2_schlaegt_fehl(tmp_path):
    """AC-7: no-build in phase3_spec -> Exit 1, Feld ungesetzt. Gegenprobe:
    derselbe Aufruf in phase2_analyse wird angenommen (die Sperre haengt an
    der Phase, nicht daran, dass der Befehl fehlt)."""
    allowed = tmp_path / "phase2"
    _make_project(allowed, "phase2_analyse")
    ok = _run_workflow(allowed, ["no-build", "--reason", "x"])
    assert ok.returncode == 0, f"Gegenprobe phase2_analyse: {ok.stderr.strip()!r}"
    assert _state(allowed).get("no_build_reason") == "x"

    blocked = tmp_path / "phase3"
    _make_project(blocked, "phase3_spec")
    result = _run_workflow(blocked, ["no-build", "--reason", "x"])
    assert result.returncode == 1, f"phase3_spec: Exit {result.returncode}"
    assert "no_build_reason" not in _state(blocked)
    assert _state(blocked)["current_phase"] == "phase3_spec"


# --- AC-8 ------------------------------------------------------------------

def test_fusszeile_nennt_99_reset_nach_no_build(tmp_path):
    """AC-8: Nach no-build liefert expected_footer_command `/99-reset #424`,
    footer_gate akzeptiert `❗ Du: /99-reset #424`, und no_build_reason ist
    per set-field gesperrt."""
    _make_project(tmp_path)

    marked = _run_workflow(tmp_path, ["no-build", "--reason", REASON])
    assert marked.returncode == 0, f"no-build scheiterte: {marked.stderr.strip()!r}"
    data = _state(tmp_path)
    assert data.get("no_build_reason") == REASON

    assert workflow.expected_footer_command(data) == "/99-reset #424"

    gate = _run_footer_gate(tmp_path, "/99-reset #424")
    assert gate.returncode == 0, (
        f"footer_gate lehnte /99-reset #424 ab: {gate.stderr.strip()!r}"
    )

    fresh = tmp_path / "fresh"
    _make_project(fresh)
    forged = _run_workflow(fresh, ["set-field", "no_build_reason", "gefaelscht"])
    assert forged.returncode == 1, "no_build_reason liess sich per set-field setzen"
    assert "no-build" in forged.stderr, forged.stderr
    assert "no_build_reason" not in _state(fresh)


# --- AC-9 ------------------------------------------------------------------

def test_ohne_marker_bleibt_20_analyse(tmp_path):
    """AC-9: Ohne no-build bleibt der Schritt /20-analyse #424, und
    /99-reset wird von footer_gate weiterhin abgelehnt (Exit 2)."""
    _make_project(tmp_path)

    assert workflow.expected_footer_command(_state(tmp_path)) == "/20-analyse #424"

    gate = _run_footer_gate(tmp_path, "/99-reset #424")
    assert gate.returncode == 2, (
        f"footer_gate akzeptierte /99-reset ohne Marker (Exit {gate.returncode})"
    )
    assert "/20-analyse" in gate.stderr


# --- AC-10 -----------------------------------------------------------------

def test_abandon_archiviert_nach_no_build(tmp_path):
    """AC-10: no-build, dann abandon --reason -> archiviert mit status
    abandoned, abandon_reason gesetzt, no_build_reason erhalten; die aktive
    Workflow-Datei existiert nicht mehr."""
    wf_file = _make_project(tmp_path)

    marked = _run_workflow(tmp_path, ["no-build", "--reason", REASON])
    assert marked.returncode == 0, f"no-build scheiterte: {marked.stderr.strip()!r}"

    result = _run_workflow(tmp_path, ["abandon", "--reason", REASON])
    assert result.returncode == 0, result.stderr

    archived = tmp_path / ".claude" / "workflows" / "_archive" / f"{WF_NAME}.json"
    assert archived.exists(), "Workflow nicht archiviert"
    data = json.loads(archived.read_text())
    assert data.get("status") == "abandoned"
    assert data.get("abandon_reason") == REASON
    assert data.get("no_build_reason") == REASON
    assert not wf_file.exists(), "aktive Workflow-Datei existiert noch"


# --- AC-11 -----------------------------------------------------------------

def test_reset_command_und_skill_enthalten_abandon_zweig():
    """AC-11: Quelle und generierter Skill von /99-reset enthalten den
    abandon-Zweig (mit no_build_reason und fehlender spec_file), und
    sync_skills --check meldet keine Drift."""
    for rel in ("core/commands/99-reset.md", "skills/99-reset/SKILL.md"):
        text = (REPO_ROOT / rel).read_text()
        assert "workflow.py abandon --reason" in text, f"{rel}: kein abandon-Zweig"
        assert "no_build_reason" in text, f"{rel}: kein Verweis auf no_build_reason"
        assert "spec_file" in text, f"{rel}: kein Verweis auf fehlende spec_file"

    check = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"), "--check"],
        capture_output=True, text=True,
    )
    assert check.returncode == 0, f"Skill-Drift: {check.stdout}{check.stderr}"
