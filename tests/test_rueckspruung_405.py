"""Tests fuer Issue #405: Ruecksprung setzt Freigaben zurueck.

Befund: Nach `workflow.py phase phase3_spec` aus einer spaeteren Phase blieben
`spec_approved` und `green_approved` auf `true`. Der phase_listener ignorierte
daraufhin ein erneutes `approved` ("bereits freigegeben"), und umgekehrt galt die
alte Freigabe fuer eine inzwischen geaenderte Spec.

ACs laut docs/specs/infra/fix-405-424-workflow-ausgaenge.md (AC-1 bis AC-5).
Hermetische Subprozess-Tests nach Vorlage tests/test_write_log_phases_111.py:
CLAUDE_PROJECT_DIR=tmp_path, `.git` als Verzeichnis (kein Worktree), echte
Aufrufe von workflow.py und phase_listener.py.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

WF_NAME = "fix-405-rueckspruung"
REL_SPEC = "docs/specs/fix-405.md"
REL_BRIEFING = "docs/briefings/fix-405.md"

SPEC_BODY = (
    "# Spec fix-405\n\n"
    "## Purpose\n\nRuecksprung nimmt die Freigabe mit zurueck.\n\n"
    "## Definition of Done\n\n- Fertig, wenn erneutes approved wirkt.\n\n"
    "## Acceptance Criteria\n\n"
    "- **AC-1:** Given ein Ruecksprung / When approved / Then Phase 4.\n\n"
    "## Test Plan\n\n- pytest tests/test_rueckspruung_405.py\n\n"
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** keine\n"
    "- **Rationale:** Bestehendes Muster, keine neue Architektur.\n"
)

SPEC_CHANGED = SPEC_BODY + "\n## Nachtrag\n\nNach dem Ruecksprung ergaenzt.\n"

BRIEFING = (
    "# PO-Briefing: fix-405\n\n"
    "## Was gebaut wird\n\n"
    "Ein Ruecksprung zur Spec nimmt die alte Freigabe zurueck, damit neu freigegeben wird.\n\n"
    "## Definition of Done\n\n"
    "Fertig ist es, wenn ein erneutes approved nach dem Ruecksprung wieder wirkt.\n\n"
    "## Wie geprüft wird\n\n"
    "Automatische Tests springen zurueck und geben ueber den echten Listener frei.\n\n"
    "## Kritische Anmerkungen\n\n"
    "- Das Adversary-Verdict bleibt beim Ruecksprung bewusst stehen.\n"
)


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


def _run_listener(project: Path, prompt: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "phase_listener.py")],
        input=json.dumps({"prompt": prompt}), capture_output=True, text=True,
        env=_env(project), cwd=str(project),
    )


def _write(project: Path, rel: str, content: str) -> None:
    path = project / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _make_project(project: Path, phase: str) -> Path:
    """Main-Repo mit freigegebenem Workflow (beide Flags true), Spec + Briefing.

    Das Briefing wird ueber den echten `set-briefing` registriert, damit es
    per SHA an die Spec gebunden ist — das Freigabe-Gate soll nur an der
    Freigabe scheitern koennen, nicht am Testaufbau.
    """
    project.mkdir(parents=True, exist_ok=True)
    (project / ".git").mkdir(exist_ok=True)
    wf_dir = project / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    _write(project, "docs/context/fix-405.md", "# Kontext\n")
    _write(project, REL_SPEC, SPEC_BODY)
    _write(project, REL_BRIEFING, BRIEFING)
    wf_file = wf_dir / f"{WF_NAME}.json"
    wf_file.write_text(json.dumps({
        "name": WF_NAME,
        "workflow_type": "feature",
        "current_phase": phase,
        "context_file": "docs/context/fix-405.md",
        "spec_file": REL_SPEC,
        "spec_approved": True,
        "green_approved": True,
        "red_test_done": True,
        "phase_transitions": [],
        "phase_log": [],
        "test_artifacts": [],
    }))
    reg = _run_workflow(project, ["set-briefing", REL_BRIEFING])
    assert reg.returncode == 0, f"Testaufbau: set-briefing scheiterte: {reg.stderr}"
    return wf_file


def _state(project: Path) -> dict:
    return json.loads(
        (project / ".claude" / "workflows" / f"{WF_NAME}.json").read_text()
    )


def _jump(project: Path, target: str) -> None:
    result = _run_workflow(project, ["phase", target])
    assert result.returncode == 0, f"phase {target} scheiterte: {result.stderr}"
    assert _state(project)["current_phase"] == target


# --- AC-1 ------------------------------------------------------------------

def test_rueckspruch_auf_spec_setzt_beide_flags_zurueck(tmp_path):
    """AC-1: phase6_implement -> phase3_spec setzt beide Freigaben zurueck."""
    _make_project(tmp_path, "phase6_implement")

    _jump(tmp_path, "phase3_spec")

    data = _state(tmp_path)
    assert data["current_phase"] == "phase3_spec"
    assert data.get("spec_approved") is False, (
        f"spec_approved nach Ruecksprung auf phase3_spec: {data.get('spec_approved')!r}"
    )
    assert data.get("green_approved") is False, (
        f"green_approved nach Ruecksprung auf phase3_spec: {data.get('green_approved')!r}"
    )


# --- AC-2 ------------------------------------------------------------------

def test_flags_je_nach_ziel_phase(tmp_path):
    """AC-2: Ziel phase4/phase5 setzt nur green_approved zurueck; Ziel
    phase6_implement (aus phase7) und Vorwaertswechsel aendern nichts."""
    # (Ausgangsphase, Ziel, erwartet spec_approved, erwartet green_approved)
    cases = [
        ("phase6_implement", "phase5_tdd_red", True, False),
        ("phase6_implement", "phase4_approved", True, False),
        ("phase7_validate", "phase6_implement", True, True),
        ("phase5_tdd_red", "phase6_implement", True, True),  # vorwaerts
    ]
    results = {}
    for i, (start, target, _, _) in enumerate(cases):
        project = tmp_path / f"case{i}"
        _make_project(project, start)
        _jump(project, target)
        data = _state(project)
        results[(start, target)] = (data.get("spec_approved"), data.get("green_approved"))

    expected = {(s, t): (sa, ga) for s, t, sa, ga in cases}
    assert results == expected, (
        f"Flags (spec_approved, green_approved) je Wechsel: ist {results}, soll {expected}"
    )


# --- AC-3 ------------------------------------------------------------------

def test_approved_nach_rueckspruch_fuehrt_zu_phase4(tmp_path):
    """AC-3: Ruecksprung, Spec geaendert, Briefing neu gesetzt -> `approved`
    ueber den echten phase_listener fuehrt nach phase4_approved."""
    _make_project(tmp_path, "phase6_implement")
    _jump(tmp_path, "phase3_spec")

    _write(tmp_path, REL_SPEC, SPEC_CHANGED)
    reg = _run_workflow(tmp_path, ["set-briefing", REL_BRIEFING])
    assert reg.returncode == 0, f"set-briefing nach Spec-Aenderung: {reg.stderr}"

    approval = _run_listener(tmp_path, "approved")
    assert approval.returncode == 0, approval.stderr

    data = _state(tmp_path)
    assert data["current_phase"] == "phase4_approved", (
        f"Erneutes approved nach Ruecksprung wirkte nicht: Phase {data['current_phase']}, "
        f"Listener-Ausgabe: {approval.stdout.strip()[:300]!r}"
    )
    assert data.get("spec_approved") is True


# --- AC-4 ------------------------------------------------------------------

def test_alte_freigabe_gilt_nach_rueckspruch_nicht_mehr(tmp_path):
    """AC-4: Nach Ruecksprung ohne neue Freigabe blockt `phase phase4_approved`
    mit der Meldung des Freigabe-Gates; die Phase bleibt phase3_spec."""
    _make_project(tmp_path, "phase6_implement")
    _jump(tmp_path, "phase3_spec")

    result = _run_workflow(tmp_path, ["phase", "phase4_approved"])

    assert result.returncode == 1, (
        f"Alte Freigabe liess den Wechsel durch (Exit {result.returncode}): "
        f"{result.stdout.strip()!r}"
    )
    assert "Spec not approved" in result.stderr, result.stderr
    assert _state(tmp_path)["current_phase"] == "phase3_spec"


# --- AC-5 ------------------------------------------------------------------

def test_is_approved_false_nach_rueckspruch(tmp_path):
    """AC-5: Nach Ruecksprung auf phase3_spec gilt die Freigabe nicht mehr —
    `_is_approved` ist False und `spec_file` ist per set-field wieder aenderbar
    (vor der Freigabe nicht eingefroren, kein Override noetig)."""
    import workflow

    _make_project(tmp_path, "phase6_implement")
    _jump(tmp_path, "phase3_spec")

    assert workflow._is_approved(_state(tmp_path)) is False, (
        f"_is_approved nach Ruecksprung: True (State: spec_approved="
        f"{_state(tmp_path).get('spec_approved')!r})"
    )

    _write(tmp_path, "docs/specs/fix-405-v2.md", SPEC_BODY)
    result = _run_workflow(tmp_path, ["set-field", "spec_file", "docs/specs/fix-405-v2.md"])
    assert result.returncode == 0, (
        f"spec_file nach Ruecksprung weiter eingefroren: {result.stderr.strip()}"
    )
    assert _state(tmp_path)["spec_file"] == "docs/specs/fix-405-v2.md"
