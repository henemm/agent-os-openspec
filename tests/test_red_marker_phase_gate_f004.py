"""Phasen-Gate ab phase6: `mark-ui-red` allein muss reichen (F004, 3.25.0).

Bestandsfehler, vom Adversary in Runde 2 gefunden: `_validate_transition` in
`core/hooks/workflow.py` fragte als EINZIGE der sechs RED-Abfragen im Framework
nur `red_test_done` ab. `cmd_mark_ui_red` setzt aber ausschliesslich
`ui_test_red_done` und legt kein Test-Artefakt an. Ein Workflow, der diesen
dokumentierten Kurzweg nutzte (reiner UI-Workflow), kam nie aus
`phase5_tdd_red` heraus — der Phasenwechsel war dauerhaft blockiert.

Alle anderen RED-Abfragen ORen beide Marker bereits: `edit_gate.py:486`,
`tdd_enforcement.py:191` sowie in `workflow.py` `cmd_write_log`, `_retro_hints`
und die Qualitaetssignale in `cmd_retro`.

Geprüft wird das `phase`-Kommando als Subprozess (so ruft Claude es auf),
damit auch der Zustand auf der Platte belegt ist.

**Fixture-Hygiene** — drei Wege, auf denen ein Test hier vakuum-grün wäre:
  1. `workflow_type` `bug`/`feature-fast`: `_validate_transition` steigt früh
     aus (workflow.py:917-936) und erreicht den RED-Check nie. Deshalb ueberall
     `workflow_type: "feature"`.
  2. Ziel <= aktueller Phase: `if tgt_idx <= cur_idx: return None` greift
     vorher. Deshalb steht die Fixture in `phase5_tdd_red`, und jedes Ziel
     liegt strikt dahinter.
  3. Block durch ein FRÜHERES Gate (ADR, PO-Briefing, Spec-Freigabe) statt
     durch den RED-Check. Deshalb setzt die Fixture alle vorgelagerten Gates
     auf "passiert" — und der Negativfall prüft die Meldung, nicht nur den
     Exit-Code.

- AC-6: Phasenwechsel ab phase6 gelingt auch mit ausschliesslich `mark-ui-red`
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

WF_NAME = "ui-red-wf"
SPEC_REL = "docs/specs/ui/spec.md"
BRIEFING_REL = "docs/briefings/ui-red-wf.md"

# Vorgelagerte Gates: Spec mit ausgefüllter ADR-Sektion + vollständiges
# PO-Briefing. Ohne beides würde die Transition schon vor dem RED-Check
# scheitern und der Negativtest wäre wertlos.
SPEC_BODY = (
    "# UI Spec\n\n"
    "## Purpose\n\nEin reiner UI-Workflow.\n\n"
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** keine\n"
    "- **Rationale:** Reine UI-Änderung ohne Architektur-Relevanz.\n"
)

BRIEFING_BODY = (
    "# PO-Briefing: ui-red-wf\n\n"
    "## Was gebaut wird\n\nEine kleine, klar umrissene Änderung an der Oberfläche.\n\n"
    "## Definition of Done\n\nFertig, wenn das beschriebene Verhalten sichtbar eintritt.\n\n"
    "## Wie geprüft wird\n\nEin UI-Test prüft genau dieses Verhalten.\n\n"
    "## Kritische Anmerkungen\n\n- Keine offenen Punkte erkennbar.\n"
)


def _project(tmp_path: Path, **red_fields) -> Path:
    """Workflow in phase5_tdd_red, alle vorgelagerten Gates passiert.

    `red_fields` bestimmt allein, ob der RED-Check greift.
    """
    (tmp_path / SPEC_REL).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / SPEC_REL).write_text(SPEC_BODY)
    (tmp_path / BRIEFING_REL).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / BRIEFING_REL).write_text(BRIEFING_BODY)

    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "_log").mkdir(parents=True, exist_ok=True)

    data = {
        "name": WF_NAME,
        "workflow_type": "feature",
        "current_phase": "phase5_tdd_red",
        "context_file": "docs/context.md",
        "spec_file": SPEC_REL,
        "spec_approved": True,
        "test_artifacts": [],
        "red_test_done": False,
        "ui_test_red_done": False,
        "phase_transitions": [],
        "phase_log": [],
        "po_briefing": {"file": BRIEFING_REL, "created": "2026-01-01T00:00:00"},
    }
    data.update(red_fields)
    (wf_dir / f"{WF_NAME}.json").write_text(json.dumps(data))
    return tmp_path


def _run_phase(project: Path, target: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({
        "CLAUDE_PROJECT_DIR": str(project),
        "OPENSPEC_ACTIVE_WORKFLOW": WF_NAME,
    })
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py"), "phase", target],
        capture_output=True, text=True, env=env, cwd=str(project),
    )


def _phase_on_disk(project: Path) -> str:
    state = json.loads(
        (project / ".claude" / "workflows" / f"{WF_NAME}.json").read_text()
    )
    return state.get("current_phase", "")


# --- AC-6: der UI-Marker allein oeffnet das Gate --------------------------

def test_ui_red_marker_alone_allows_phase6(tmp_path):
    """(a) Nur `ui_test_red_done` -> phase5_tdd_red => phase6_implement geht durch.

    Der Fundfall: `mark-ui-red` war der dokumentierte Kurzweg, fuehrte aber in
    eine Sackgasse.
    """
    project = _project(tmp_path, ui_test_red_done=True)
    result = _run_phase(project, "phase6_implement")
    assert result.returncode == 0, (
        "Erwartet: Durchlass mit ausschliesslich ui_test_red_done.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert _phase_on_disk(project) == "phase6_implement"


def test_ui_red_marker_alone_allows_phase7(tmp_path):
    """(b) Der RED-Check haengt an `tgt_idx >= phase6` — auch ein Sprung nach
    phase7_validate laeuft durch ihn hindurch und darf nicht blockieren."""
    project = _project(tmp_path, ui_test_red_done=True)
    result = _run_phase(project, "phase7_validate")
    assert result.returncode == 0, (
        "Erwartet: Durchlass nach phase7_validate mit ui_test_red_done.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert _phase_on_disk(project) == "phase7_validate"


# --- Regressions-Guards: die bisherigen Wege bleiben offen ----------------

def test_unit_red_marker_alone_still_allows_phase6(tmp_path):
    """(c) Nur `red_test_done` (mark-red) — der bisher einzig funktionierende
    Weg bleibt unveraendert offen."""
    project = _project(tmp_path, red_test_done=True)
    result = _run_phase(project, "phase6_implement")
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert _phase_on_disk(project) == "phase6_implement"


def test_red_artifact_alone_still_allows_phase6(tmp_path):
    """(d) Nur ein Artefakt mit phase=phase5_tdd_red, kein Marker — bleibt
    ebenfalls offen."""
    project = _project(tmp_path, test_artifacts=[
        {"type": "test_output", "path": "logs/test.log",
         "result": "3 failed", "phase": "phase5_tdd_red"},
    ])
    result = _run_phase(project, "phase6_implement")
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert _phase_on_disk(project) == "phase6_implement"


# --- Das Gate bleibt ein Gate ---------------------------------------------

def test_no_marker_and_no_artifact_still_blocked(tmp_path):
    """(e) Weder Marker noch Artefakt -> weiterhin BLOCKED, Phase unveraendert.

    Die Meldung wird mitgeprueft: ein Block durch ein frueheres Gate (ADR,
    PO-Briefing, Freigabe) wuerde den Exit-Code genauso setzen und den Test
    aus dem falschen Grund gruen faerben.
    """
    project = _project(tmp_path)
    result = _run_phase(project, "phase6_implement")
    assert result.returncode != 0, (
        "Erwartet: Block ohne jeden RED-Nachweis.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "RED" in result.stderr, (
        "Block kam nicht vom RED-Gate, sondern von einem vorgelagerten Gate: "
        f"{result.stderr!r}"
    )
    assert _phase_on_disk(project) == "phase5_tdd_red"
