"""Tests für das ADR-Reflexions-Gate (Issue #63, Spec docs/specs/adr-reflection-gate.md).

Erzwingt bei der Spec-Freigabe (Phase 3→4), dass die Sektion
`## Architektur-Entscheidung (ADR)` ausgefüllt ist (ADR-Nr. ODER begründetes
„keine"). Zwei Einhängepunkte:

  A) workflow.py `_validate_transition` (harter Block beim `phase`-Kommando)
  B) phase_listener.py Approval-Block (Soft-Block: spec_approved bleibt False)

Kill-Switch: config.yaml → adr_gate.enabled: false.
Grandfathering: fehlt die ADR-Sektion ganz → kein Block.

TDD-RED-Erwartung: Solange `_check_adr` in workflow.py fehlt, blockieren die
Block-Tests (1, 2, 7) NICHT → sie sind rot. Die Pass-Tests (3, 4, 5, 6, 8) sind
Regressions-Guards und dürfen jetzt schon grün sein.

Muster: Subprozess-Runner + Workflow-JSON-Fixture + echte tmp-Spec-Dateien,
analog tests/test_gate_fixes_26_38_34.py.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


# --- ADR-Sektions-Bausteine -------------------------------------------------

# Nur der unausgefüllte Template-Platzhalter (enthält selbst „keine" und „ADR-N…",
# darf aber NICHT als ausgefüllt gelten → Block erwartet).
ADR_PLACEHOLDER = (
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** [ADR-NNNN oder \"keine\"]\n"
    "- **Rationale:** [kurz: warum diese Entscheidung bzw. warum keine nötig ist]\n"
)

# ADR-Sektion vorhanden, aber ohne ADR-Nr. und ohne „keine" — nur Fließtext.
ADR_MISSING_VALUE = (
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** \n"
    "- **Rationale:** Diese Entscheidung betrifft die interne Struktur des Moduls.\n"
)

# Ausgefüllt mit ADR-Nummer.
ADR_FILLED_NUMBER = (
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** ADR-0001\n"
    "- **Rationale:** Neue Persistenz-Schicht eingeführt.\n"
)

# Ausgefüllt mit begründetem „keine".
ADR_FILLED_NONE = (
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** keine\n"
    "- **Rationale:** Reiner Bugfix ohne Architektur-Relevanz.\n"
)

# F001-Regression: ADR-Nr. LEER, aber Rationale enthält zufällig „keine".
ADR_EMPTY_NR_KEINE_IN_RATIONALE = (
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** \n"
    "- **Rationale:** Diese Änderung betrifft keine Persistenz-Schicht.\n"
)

# F001-Regression: ADR-Nr. LEER, aber Rationale enthält zufällig „none".
ADR_EMPTY_NR_NONE_IN_RATIONALE = (
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** \n"
    "- **Rationale:** This change touches none of the persistence layer.\n"
)

# F002-Regression: ###-Heading (eine Ebene tiefer) mit reinem Platzhalter.
ADR_H3_PLACEHOLDER = (
    "### Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** [ADR-NNNN oder \"keine\"]\n"
    "- **Rationale:** [kurz: warum diese Entscheidung bzw. warum keine nötig ist]\n"
)

# F003-Regression: ADR-Sektion OHNE ausgefüllte ADR-Nr.-Zeile (nur Rationale),
# gefolgt von einem H1-Heading `# Anhang` mit einer fremden `**ADR-Nr.:**`-Zeile
# darunter. Der Sektions-Body darf NICHT bis zum H1 durchlaufen, sonst leakt die
# fremde ADR-Nr. in die Sektion und das Gate passiert fälschlich.
ADR_H1_LEAK = (
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **Rationale:** keine.\n\n"
    "# Anhang\n\n"
    "- **ADR-Nr.:** ADR-9999\n"
)


def _write_spec(tmp_path: Path, rel_spec: str, adr_section: str | None) -> None:
    """Schreibe eine Minimal-Spec nach tmp_path/<rel_spec>.

    adr_section=None → Spec OHNE ADR-Sektion (Grandfathering).
    """
    spec_path = tmp_path / rel_spec
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    body = "# Test Spec\n\n## Purpose\n\nBeliebiger Inhalt.\n\n"
    if adr_section is not None:
        body += adr_section
    spec_path.write_text(body)


# --- Einhängepunkt A: workflow.py phase-Transition -------------------------

def _run_phase(env: dict, target: str, cwd: str) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py"), "phase", target],
        capture_output=True, text=True, env=full_env, cwd=cwd,
    )


def _make_transition_workflow(tmp_path: Path, rel_spec: str) -> None:
    """Workflow am Phase-3→4-Anlauf: current_phase phase4_approved, Ziel phase5.

    context_file/spec_file/spec_approved/red_test_done gesetzt, damit ALLE
    bestehenden Gates passieren und nur das ADR-Gate über das Ergebnis
    entscheidet.
    """
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "_log").mkdir(parents=True, exist_ok=True)
    data = {
        "name": "adr-wf",
        "workflow_type": "feature",
        "current_phase": "phase4_approved",
        "context_file": "docs/context.md",
        "spec_file": rel_spec,
        "spec_approved": True,
        "red_test_done": True,
        "phase_transitions": [],
        "phase_log": [],
    }
    (wf_dir / "adr-wf.json").write_text(json.dumps(data))


def _env(tmp_path: Path) -> dict:
    return {
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "OPENSPEC_ACTIVE_WORKFLOW": "adr-wf",
    }


def test_1_placeholder_blocks_transition(tmp_path):
    """Test 1 — Einhängepunkt A block: Spec mit reinem Platzhalter-ADR
    → phase-Transition Richtung phase5 blockiert (Exit != 0, stderr enthält 'ADR')."""
    rel = "docs/specs/m/spec.md"
    _write_spec(tmp_path, rel, ADR_PLACEHOLDER)
    _make_transition_workflow(tmp_path, rel)
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block bei Platzhalter-ADR, aber Transition ging durch.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "ADR" in result.stderr, result.stderr


def test_2_missing_value_blocks_transition(tmp_path):
    """Test 2 — Einhängepunkt A block: ADR-Sektion vorhanden, aber ohne
    ADR-Nr./'keine' (nur Fließtext) → blockiert."""
    rel = "docs/specs/m/spec.md"
    _write_spec(tmp_path, rel, ADR_MISSING_VALUE)
    _make_transition_workflow(tmp_path, rel)
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block bei ADR ohne Wert, aber Transition ging durch.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "ADR" in result.stderr, result.stderr


def test_3_filled_adr_number_passes(tmp_path):
    """Test 3 — pass: `- **ADR-Nr.:** ADR-0001` → Exit 0."""
    rel = "docs/specs/m/spec.md"
    _write_spec(tmp_path, rel, ADR_FILLED_NUMBER)
    _make_transition_workflow(tmp_path, rel)
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr


def test_4_filled_keine_passes(tmp_path):
    """Test 4 — pass: `- **ADR-Nr.:** keine` + Rationale → Exit 0."""
    rel = "docs/specs/m/spec.md"
    _write_spec(tmp_path, rel, ADR_FILLED_NONE)
    _make_transition_workflow(tmp_path, rel)
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr


def test_5_grandfathering_no_section_passes(tmp_path):
    """Test 5 — Grandfathering: Spec OHNE ADR-Sektion → Exit 0 (nicht blockiert)."""
    rel = "docs/specs/m/spec.md"
    _write_spec(tmp_path, rel, None)
    _make_transition_workflow(tmp_path, rel)
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr


def test_6_kill_switch_disables_gate(tmp_path):
    """Test 6 — Kill-Switch: adr_gate.enabled: false + Platzhalter-ADR → Exit 0.

    config.yaml wird ins tmp_path-Root geschrieben; load_config() findet es über
    find_project_root() (== CLAUDE_PROJECT_DIR)."""
    rel = "docs/specs/m/spec.md"
    _write_spec(tmp_path, rel, ADR_PLACEHOLDER)
    _make_transition_workflow(tmp_path, rel)
    (tmp_path / "config.yaml").write_text("adr_gate:\n  enabled: false\n")
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr


# --- Einhängepunkt B: phase_listener.py Approval-Pfad ----------------------

def _run_phase_listener(env: dict, prompt: str, cwd: str) -> subprocess.CompletedProcess:
    """Ruft phase_listener.py als UserPromptSubmit-Hook auf.

    Input-Kontrakt (aus core/hooks/phase_listener.py main() → get_user_message()
    in hook_utils.py abgeleitet): stdin-JSON mit Feld 'prompt'.
    """
    payload = json.dumps({"prompt": prompt})
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "phase_listener.py")],
        input=payload, capture_output=True, text=True, env=full_env, cwd=cwd,
    )


def _make_spec_phase_workflow(tmp_path: Path, rel_spec: str) -> Path:
    """Workflow in phase3_spec (approval-fähig), spec_approved noch False."""
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "_log").mkdir(parents=True, exist_ok=True)
    data = {
        "name": "adr-wf",
        "workflow_type": "feature",
        "current_phase": "phase3_spec",
        "context_file": "docs/context.md",
        "spec_file": rel_spec,
        "spec_approved": False,
        "phase_transitions": [],
        "phase_log": [],
    }
    wf_file = wf_dir / "adr-wf.json"
    wf_file.write_text(json.dumps(data))
    return wf_file


def test_7_approval_blocked_on_placeholder(tmp_path):
    """Test 7 — Einhängepunkt B block: Spec mit Platzhalter-ADR in phase3_spec,
    Approval-Keyword 'approved' → spec_approved bleibt False (Soft-Block)."""
    rel = "docs/specs/m/spec.md"
    _write_spec(tmp_path, rel, ADR_PLACEHOLDER)
    wf_file = _make_spec_phase_workflow(tmp_path, rel)
    result = _run_phase_listener(_env(tmp_path), "approved", cwd=str(tmp_path))
    # Hook wahrt Exit-0-Vertrag; entscheidend ist der State.
    data = json.loads(wf_file.read_text())
    assert data.get("spec_approved") is not True, (
        "Erwartet: spec_approved bleibt False bei Platzhalter-ADR, "
        f"wurde aber gesetzt. state={data} stderr={result.stderr!r}"
    )
    assert data.get("current_phase") == "phase3_spec", data


def test_8_approval_passes_on_filled(tmp_path):
    """Test 8 — Einhängepunkt B pass: Spec mit ausgefülltem 'keine',
    Approval-Keyword → spec_approved wird True, current_phase → phase4_approved."""
    rel = "docs/specs/m/spec.md"
    _write_spec(tmp_path, rel, ADR_FILLED_NONE)
    wf_file = _make_spec_phase_workflow(tmp_path, rel)
    result = _run_phase_listener(_env(tmp_path), "approved", cwd=str(tmp_path))
    data = json.loads(wf_file.read_text())
    assert data.get("spec_approved") is True, (
        f"Erwartet: spec_approved True bei ausgefülltem ADR. "
        f"state={data} stderr={result.stderr!r}"
    )
    assert data.get("current_phase") == "phase4_approved", data


# --- F001/F002-Regressionen ------------------------------------------------

def test_9_empty_adr_nr_with_keine_in_rationale_blocks(tmp_path):
    """Test 9 — F001-Regression: LEERE `- **ADR-Nr.:**`-Zeile, aber die Rationale
    enthält zufällig „keine" → muss blockieren (Kriterium nur auf ADR-Nr.-Wert)."""
    rel = "docs/specs/m/spec.md"
    _write_spec(tmp_path, rel, ADR_EMPTY_NR_KEINE_IN_RATIONALE)
    _make_transition_workflow(tmp_path, rel)
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block bei leerem ADR-Nr. trotz 'keine' in Rationale, "
        f"aber Transition ging durch.\nstdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "ADR" in result.stderr, result.stderr


def test_10_empty_adr_nr_with_none_in_rationale_blocks(tmp_path):
    """Test 10 — F001-Regression: LEERE ADR-Nr.-Zeile, aber Rationale enthält
    zufällig „none" → muss blockieren."""
    rel = "docs/specs/m/spec.md"
    _write_spec(tmp_path, rel, ADR_EMPTY_NR_NONE_IN_RATIONALE)
    _make_transition_workflow(tmp_path, rel)
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block bei leerem ADR-Nr. trotz 'none' in Rationale, "
        f"aber Transition ging durch.\nstdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "ADR" in result.stderr, result.stderr


def test_11_h3_heading_placeholder_blocks(tmp_path):
    """Test 11 — F002-Regression: ###-Heading (eine Ebene tiefer) mit reinem
    Platzhalter in der ADR-Nr.-Zeile → muss blockieren (Heading wird erkannt)."""
    rel = "docs/specs/m/spec.md"
    _write_spec(tmp_path, rel, ADR_H3_PLACEHOLDER)
    _make_transition_workflow(tmp_path, rel)
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block bei ###-ADR-Sektion mit Platzhalter, "
        f"aber Transition ging durch.\nstdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "ADR" in result.stderr, result.stderr


def test_12_h1_heading_leak_blocks(tmp_path):
    """Test 12 — F003-Regression: ADR-Sektion OHNE ausgefüllte ADR-Nr.-Zeile,
    gefolgt von H1 `# Anhang` mit `- **ADR-Nr.:** ADR-9999` darunter. Der
    Sektions-Body muss am H1 enden (Lookahead `(?=^#{1,3}\\s|\\Z)`), damit die
    fremde ADR-Nr. NICHT in die Sektion leakt → muss blockieren."""
    rel = "docs/specs/m/spec.md"
    _write_spec(tmp_path, rel, ADR_H1_LEAK)
    _make_transition_workflow(tmp_path, rel)
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block bei ADR-Sektion ohne ADR-Nr. trotz fremder ADR-Nr. "
        "unter späterem H1-Heading, aber Transition ging durch.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "ADR" in result.stderr, result.stderr
