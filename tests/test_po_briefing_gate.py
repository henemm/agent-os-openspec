"""Tests für das PO-Briefing-Gate (unabhängiges Freigabe-Briefing vor Phase 4).

Erzwingt bei der Spec-Freigabe (Phase 3→4), dass ein von einem unabhängigen
Agenten (`po-briefer`) erstelltes Briefing vorliegt, das zur AKTUELLEN Spec
passt. Zwei Einhängepunkte — analog zum ADR-Gate (Issue #63):

  A) workflow.py `_validate_transition` (harter Block beim `phase`-Kommando)
  B) phase_listener.py Approval-Block (Soft-Block: spec_approved bleibt False)

Registrierung: `workflow.py set-briefing <pfad>` schreibt Pfad + SHA-256 der
Spec in den Workflow-State. Ändert sich die Spec danach, passt der Hash nicht
mehr → Block ("Briefing veraltet"), damit niemand ein Briefing zu einer
zwischenzeitlich umgeschriebenen Spec abnickt.

Kill-Switch: config.yaml → po_briefing_gate.enabled: false.
Fast-Track: workflow_type feature-fast/bug → kein Block (Default).

Muster: Subprozess-Runner + Workflow-JSON-Fixture + echte tmp-Dateien,
analog tests/test_adr_gate.py.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

REL_SPEC = "docs/specs/m/spec.md"
REL_BRIEFING = "docs/briefings/po-wf.md"


# --- Fixtures ---------------------------------------------------------------

SPEC_BODY = (
    "# Test Spec\n\n"
    "## Purpose\n\nEin Feature, das etwas tut.\n\n"
    "## Definition of Done\n\n- Fertig, wenn X sichtbar ist.\n\n"
    "## Acceptance Criteria\n\n"
    "- **AC-1:** Given ein Nutzer / When er klickt / Then passiert etwas Sichtbares.\n"
)

BRIEFING_COMPLETE = (
    "# PO-Briefing: po-wf\n\n"
    "- **Spec:** docs/specs/m/spec.md\n\n"
    "## Was gebaut wird\n\n"
    "Nutzer können künftig mit einem Klick etwas auslösen, das heute fehlt.\n\n"
    "## Definition of Done\n\n"
    "Fertig ist es, wenn der Klick sichtbar etwas auslöst und das automatisch geprüft wird.\n\n"
    "## Wie geprüft wird\n\n"
    "Ein automatischer Test klickt stellvertretend und prüft das sichtbare Ergebnis.\n\n"
    "## Kritische Anmerkungen\n\n"
    "- Die Spec lässt offen, was bei zweimaligem Klicken passiert.\n"
)

# Abschnitt 'Kritische Anmerkungen' fehlt komplett.
BRIEFING_MISSING_SECTION = (
    "# PO-Briefing: po-wf\n\n"
    "## Was gebaut wird\n\n"
    "Nutzer können künftig mit einem Klick etwas auslösen, das heute fehlt.\n\n"
    "## Definition of Done\n\n"
    "Fertig ist es, wenn der Klick sichtbar etwas auslöst und das geprüft wird.\n\n"
    "## Wie geprüft wird\n\n"
    "Ein automatischer Test klickt stellvertretend und prüft das Ergebnis.\n"
)

# Alle Abschnitte da, aber leer gelassen (Agent hat abgebrochen).
BRIEFING_EMPTY_SECTION = (
    "# PO-Briefing: po-wf\n\n"
    "## Was gebaut wird\n\n"
    "Nutzer können künftig mit einem Klick etwas auslösen, das heute fehlt.\n\n"
    "## Definition of Done\n\n\n"
    "## Wie geprüft wird\n\n"
    "Ein automatischer Test klickt stellvertretend und prüft das Ergebnis.\n\n"
    "## Kritische Anmerkungen\n\n"
    "- Die Spec lässt offen, was bei zweimaligem Klicken passiert.\n"
)

# Alle Abschnitte da, aber mit unausgefülltem Platzhalter.
BRIEFING_PLACEHOLDER = BRIEFING_COMPLETE.replace(
    "Ein automatischer Test klickt stellvertretend und prüft das sichtbare Ergebnis.",
    "[TODO: Tests aus dem Test Plan zusammenfassen]",
)


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _spec_sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _env(tmp_path: Path) -> dict:
    return {
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "OPENSPEC_ACTIVE_WORKFLOW": "po-wf",
    }


def _make_workflow(
    tmp_path: Path,
    phase: str = "phase4_approved",
    *,
    workflow_type: str = "feature",
    spec_approved: bool = True,
    po_briefing: dict | None = None,
) -> Path:
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "_log").mkdir(parents=True, exist_ok=True)
    data = {
        "name": "po-wf",
        "workflow_type": workflow_type,
        "current_phase": phase,
        "context_file": "docs/context.md",
        "spec_file": REL_SPEC,
        "spec_approved": spec_approved,
        "red_test_done": True,
        "phase_transitions": [],
        "phase_log": [],
    }
    if po_briefing is not None:
        data["po_briefing"] = po_briefing
    wf_file = wf_dir / "po-wf.json"
    wf_file.write_text(json.dumps(data))
    return wf_file


def _briefing_entry(spec_content: str = SPEC_BODY, rel: str = REL_BRIEFING) -> dict:
    return {
        "file": rel,
        "spec_sha256": _spec_sha(spec_content),
        "created": "2026-01-01T00:00:00",
    }


def _run_workflow(env: dict, args: list[str], cwd: str) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py"), *args],
        capture_output=True, text=True, env=full_env, cwd=cwd,
    )


def _run_phase(env: dict, target: str, cwd: str) -> subprocess.CompletedProcess:
    return _run_workflow(env, ["phase", target], cwd)


def _run_phase_listener(env: dict, prompt: str, cwd: str) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "phase_listener.py")],
        input=json.dumps({"prompt": prompt}), capture_output=True, text=True,
        env=full_env, cwd=cwd,
    )


# --- Einhängepunkt A: workflow.py phase-Transition -------------------------

def test_1_missing_briefing_blocks_transition(tmp_path):
    """Test 1 — Block: kein po_briefing im State → Transition Richtung phase5
    blockiert, Meldung nennt das Briefing."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    _make_workflow(tmp_path)
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block ohne PO-Briefing, aber Transition ging durch.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "Briefing" in result.stderr, result.stderr


def test_2_complete_briefing_passes(tmp_path):
    """Test 2 — Pass: vollständiges Briefing + passender Spec-Hash → Exit 0."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    _write(tmp_path, REL_BRIEFING, BRIEFING_COMPLETE)
    _make_workflow(tmp_path, po_briefing=_briefing_entry())
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr


def test_3_registered_but_missing_file_blocks(tmp_path):
    """Test 3 — Block: po_briefing zeigt auf eine Datei, die es nicht gibt."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    _make_workflow(tmp_path, po_briefing=_briefing_entry())
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block bei fehlender Briefing-Datei.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "Briefing" in result.stderr, result.stderr


def test_4_spec_changed_after_briefing_blocks(tmp_path):
    """Test 4 — Block: Spec wurde nach dem Briefing geändert → Hash passt nicht.

    Das ist der Kern des Gates: sonst gibt der PO ein Briefing frei, das eine
    andere Spec beschreibt als die, die umgesetzt wird."""
    _write(tmp_path, REL_SPEC, SPEC_BODY + "\n## Nachtrag\n\nStillschweigend ergänzt.\n")
    _write(tmp_path, REL_BRIEFING, BRIEFING_COMPLETE)
    _make_workflow(tmp_path, po_briefing=_briefing_entry(SPEC_BODY))
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block bei veraltetem Briefing (Spec-Hash weicht ab).\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "Briefing" in result.stderr, result.stderr


def test_5_missing_section_blocks(tmp_path):
    """Test 5 — Block: Briefing ohne '## Kritische Anmerkungen'."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    _write(tmp_path, REL_BRIEFING, BRIEFING_MISSING_SECTION)
    _make_workflow(tmp_path, po_briefing=_briefing_entry())
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block bei fehlendem Pflicht-Abschnitt.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "Kritische Anmerkungen" in result.stderr, result.stderr


def test_6_empty_section_blocks(tmp_path):
    """Test 6 — Block: Pflicht-Abschnitt vorhanden, aber ohne Inhalt."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    _write(tmp_path, REL_BRIEFING, BRIEFING_EMPTY_SECTION)
    _make_workflow(tmp_path, po_briefing=_briefing_entry())
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block bei leerem Pflicht-Abschnitt.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "Definition of Done" in result.stderr, result.stderr


def test_7_placeholder_blocks(tmp_path):
    """Test 7 — Block: Briefing enthält noch einen [TODO:-Platzhalter."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    _write(tmp_path, REL_BRIEFING, BRIEFING_PLACEHOLDER)
    _make_workflow(tmp_path, po_briefing=_briefing_entry())
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block bei Platzhalter im Briefing.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "Briefing" in result.stderr, result.stderr


def test_8_kill_switch_disables_gate(tmp_path):
    """Test 8 — Kill-Switch: po_briefing_gate.enabled: false → kein Block."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    _make_workflow(tmp_path)
    (tmp_path / "config.yaml").write_text("po_briefing_gate:\n  enabled: false\n")
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr


def test_9_fast_track_not_blocked(tmp_path):
    """Test 9 — Fast Track: workflow_type feature-fast → kein Briefing nötig."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    _make_workflow(tmp_path, workflow_type="feature-fast")
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr


def test_10_fast_track_gate_configurable(tmp_path):
    """Test 10 — Fast Track ist konfigurierbar: skip_fast_track: false → Block."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    _make_workflow(tmp_path, workflow_type="feature-fast")
    (tmp_path / "config.yaml").write_text(
        "po_briefing_gate:\n  enabled: true\n  skip_fast_track: false\n"
    )
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode != 0, (
        "Erwartet: Block auch im Fast Track bei skip_fast_track: false.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_11_bug_workflow_not_blocked(tmp_path):
    """Test 11 — Bug-Fast-Track bleibt gateseitig unberührt (Bestandsverhalten)."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    _make_workflow(tmp_path, workflow_type="bug")
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr


# --- Einhängepunkt B: phase_listener.py Approval-Pfad ----------------------

def test_12_approval_blocked_without_briefing(tmp_path):
    """Test 12 — Soft-Block: 'approved' in phase3_spec ohne Briefing →
    spec_approved bleibt False, Phase bleibt phase3_spec."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    wf_file = _make_workflow(tmp_path, phase="phase3_spec", spec_approved=False)
    result = _run_phase_listener(_env(tmp_path), "approved", cwd=str(tmp_path))
    data = json.loads(wf_file.read_text())
    assert data.get("spec_approved") is not True, (
        "Erwartet: spec_approved bleibt False ohne PO-Briefing. "
        f"state={data} stderr={result.stderr!r}"
    )
    assert data.get("current_phase") == "phase3_spec", data
    assert "Briefing" in result.stderr, result.stderr


def test_13_approval_passes_with_briefing(tmp_path):
    """Test 13 — Pass: vollständiges, aktuelles Briefing → Freigabe wirkt."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    _write(tmp_path, REL_BRIEFING, BRIEFING_COMPLETE)
    wf_file = _make_workflow(
        tmp_path, phase="phase3_spec", spec_approved=False,
        po_briefing=_briefing_entry(),
    )
    result = _run_phase_listener(_env(tmp_path), "approved", cwd=str(tmp_path))
    data = json.loads(wf_file.read_text())
    assert data.get("spec_approved") is True, (
        f"Erwartet: Freigabe wirkt mit Briefing. state={data} stderr={result.stderr!r}"
    )
    assert data.get("current_phase") == "phase4_approved", data


def test_14_approval_blocked_on_stale_briefing(tmp_path):
    """Test 14 — Soft-Block: Briefing veraltet (Spec danach geändert)."""
    _write(tmp_path, REL_SPEC, SPEC_BODY + "\n## Nachtrag\n\nStillschweigend ergänzt.\n")
    _write(tmp_path, REL_BRIEFING, BRIEFING_COMPLETE)
    wf_file = _make_workflow(
        tmp_path, phase="phase3_spec", spec_approved=False,
        po_briefing=_briefing_entry(SPEC_BODY),
    )
    result = _run_phase_listener(_env(tmp_path), "approved", cwd=str(tmp_path))
    data = json.loads(wf_file.read_text())
    assert data.get("spec_approved") is not True, (
        f"Erwartet: keine Freigabe auf veraltetem Briefing. state={data} "
        f"stderr={result.stderr!r}"
    )
    assert "Briefing" in result.stderr, result.stderr


# --- CLI: workflow.py set-briefing ----------------------------------------

def test_15_set_briefing_registers_path_and_hash(tmp_path):
    """Test 15 — CLI: set-briefing schreibt Pfad + SHA-256 der Spec in den State."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    wf_file = _make_workflow(tmp_path, phase="phase3_spec", spec_approved=False)
    _write(tmp_path, REL_BRIEFING, BRIEFING_COMPLETE)
    result = _run_workflow(_env(tmp_path), ["set-briefing", REL_BRIEFING], cwd=str(tmp_path))
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    data = json.loads(wf_file.read_text())
    entry = data.get("po_briefing")
    assert isinstance(entry, dict), data
    assert entry.get("file") == REL_BRIEFING, entry
    assert entry.get("spec_sha256") == _spec_sha(SPEC_BODY), entry
    assert entry.get("created"), entry


def test_16_set_briefing_rejects_missing_file(tmp_path):
    """Test 16 — CLI: set-briefing auf nicht existierende Datei → Exit != 0,
    State bleibt unverändert (kein Geister-Briefing)."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    wf_file = _make_workflow(tmp_path, phase="phase3_spec", spec_approved=False)
    result = _run_workflow(
        _env(tmp_path), ["set-briefing", "docs/briefings/gibtsnicht.md"], cwd=str(tmp_path)
    )
    assert result.returncode != 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "po_briefing" not in json.loads(wf_file.read_text())


def test_17_set_briefing_rejects_incomplete_briefing(tmp_path):
    """Test 17 — CLI: set-briefing prüft dieselben Pflicht-Abschnitte wie das Gate
    → der Fehler fällt bei der Registrierung auf, nicht erst bei der Freigabe."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    wf_file = _make_workflow(tmp_path, phase="phase3_spec", spec_approved=False)
    _write(tmp_path, REL_BRIEFING, BRIEFING_MISSING_SECTION)
    result = _run_workflow(_env(tmp_path), ["set-briefing", REL_BRIEFING], cwd=str(tmp_path))
    assert result.returncode != 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "po_briefing" not in json.loads(wf_file.read_text())


def test_18_umlaut_spelling_tolerated(tmp_path):
    """Test 18 — 'Wie geprueft wird' (ASCII statt 'ü') passiert das Gate.

    Ein Gate, das an der Umlaut-Schreibweise einer Überschrift scheitert, blockt
    aus einem Grund, der mit der Sache nichts zu tun hat. Gefunden im
    End-to-End-Durchlauf."""
    _write(tmp_path, REL_SPEC, SPEC_BODY)
    _write(
        tmp_path, REL_BRIEFING,
        BRIEFING_COMPLETE.replace("## Wie geprüft wird", "## Wie geprueft wird"),
    )
    _make_workflow(tmp_path, po_briefing=_briefing_entry())
    result = _run_phase(_env(tmp_path), "phase5_tdd_red", cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr
