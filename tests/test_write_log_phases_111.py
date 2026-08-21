"""Regressionstests fuer Issue #111 (write-log meldet durchlaufene Phasen als
uebersprungen; /90-retro gibt daraus falsche Hinweise).

Zwei getrennte Ursachen, beide hier abgedeckt:

1. `cmd_write_log` baute die Menge der besuchten Phasen aus dem `to`-Feld von
   `phase_transitions`. Die Startphase taucht dort nur als `from` auf — nie als
   `to`. `phase1_context` galt dadurch in JEDEM Workflow als uebersprungen.
2. Der Uebergang `phase3_spec -> phase4_approved` landete gar nicht in
   `phase_transitions`: die Freigabe laeuft ueber `phase_listener.py`, das nur
   `_log_phase_transition()` (also ausschliesslich `phase_log`) rief.

Gegenprobe inklusive: eine tatsaechlich uebersprungene Phase muss weiterhin in
`phases_skipped` auftauchen — der Fix darf nicht einfach alles als "gelaufen"
melden.

Subprozess-Tests hermetisch (cwd/CLAUDE_PROJECT_DIR=tmp_path); die geschuetzte
Datei `.claude/active_workflow` wird nicht angefasst.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

WF_NAME = "wf-111"


def _env(tmp_path: Path) -> dict:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF_NAME
    return env


def _run_workflow(tmp_path: Path, args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py")] + args,
        capture_output=True, text=True, env=_env(tmp_path), cwd=str(tmp_path),
    )


def _run_listener(tmp_path: Path, prompt: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "phase_listener.py")],
        input=json.dumps({"prompt": prompt}), capture_output=True, text=True,
        env=_env(tmp_path), cwd=str(tmp_path),
    )


def _make_workflow(tmp_path: Path) -> Path:
    """Main-Repo (.git als DIR → kein Worktree) mit Workflow in phase1_context.

    `phase_log` und `current_phase` entsprechen dem Zustand, den `workflow.py
    start` fuer einen feature-Workflow erzeugt: die Startphase steht im Log,
    `phase_transitions` ist noch leer.
    """
    (tmp_path / ".git").mkdir(exist_ok=True)
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf_file = wf_dir / f"{WF_NAME}.json"
    wf_file.write_text(json.dumps({
        "name": WF_NAME,
        "workflow_type": "feature",
        "current_phase": "phase1_context",
        "context_file": "docs/context/wf-111.md",
        "spec_file": "docs/specs/wf-111.md",
        "spec_approved": False,
        "phase_transitions": [],
        "phase_log": [{
            "phase": "phase1_context",
            "entered_at": "2026-08-21T10:00:00",
            "exited_at": None,
            "duration_min": None,
        }],
        "test_artifacts": [],
    }))
    return wf_file


def _wf_state(tmp_path: Path) -> dict:
    return json.loads((tmp_path / ".claude" / "workflows" / f"{WF_NAME}.json").read_text())


def _read_log(tmp_path: Path) -> dict:
    """Minimaler Parser fuer das von `write-log` erzeugte YAML.

    Bewusst ohne PyYAML: das Protokoll ist ein flaches Format aus `key: value`
    und `  - item`, und der Test soll keine Abhaengigkeit einfuehren, die die
    uebrige Suite nicht hat.
    """
    files = list((tmp_path / ".claude" / "workflows" / "_log").glob(f"*_{WF_NAME}.yaml"))
    assert len(files) == 1, f"expected exactly one log file, got {files}"
    result: dict = {}
    key = None
    for raw in files[0].read_text().splitlines():
        if raw.startswith("  - "):
            assert key is not None
            result.setdefault(key, [])
            result[key].append(raw[4:].strip())
        elif ":" in raw:
            key, _, value = raw.partition(":")
            key = key.strip()
            value = value.strip()
            result[key] = value if value else []
    return result


class TestFullyTraversedWorkflowHasNoSkippedPhases:
    def test_context_and_listener_approval_are_not_reported_as_skipped(self, tmp_path):
        """Der #111-Fall: phase1_context wird durchlaufen, die Freigabe kommt ueber
        den phase_listener (NICHT ueber cmd_phase) — `phases_skipped` muss leer sein."""
        _make_workflow(tmp_path)

        assert _run_workflow(tmp_path, ["phase", "phase2_analyse"]).returncode == 0
        assert _run_workflow(tmp_path, ["phase", "phase3_spec"]).returncode == 0

        approval = _run_listener(tmp_path, "approved")
        assert approval.returncode == 0, approval.stderr
        assert _wf_state(tmp_path)["current_phase"] == "phase4_approved"

        assert _run_workflow(tmp_path, ["phase", "phase5_tdd_red"]).returncode == 0
        assert _run_workflow(tmp_path, ["mark-red", "3 tests failed"]).returncode == 0
        assert _run_workflow(tmp_path, ["phase", "phase6_implement"]).returncode == 0

        assert _run_workflow(tmp_path, ["write-log", "success"]).returncode == 0

        log = _read_log(tmp_path)
        assert log["phases_skipped"] == [], (
            f"durchlaufene Phasen als uebersprungen gemeldet: {log['phases_skipped']}"
        )
        assert "phase1_context" in log["phases_completed"]
        assert "phase4_approved" in log["phases_completed"]


class TestGenuinelySkippedPhaseIsStillReported:
    def test_skipped_analysis_phase_appears_in_phases_skipped(self, tmp_path):
        """Gegenprobe: phase2_analyse wird uebersprungen und muss weiterhin
        gemeldet werden — der Fix darf nicht alles als gelaufen ausgeben."""
        _make_workflow(tmp_path)

        assert _run_workflow(tmp_path, ["phase", "phase3_spec"]).returncode == 0
        approval = _run_listener(tmp_path, "approved")
        assert approval.returncode == 0, approval.stderr
        assert _run_workflow(tmp_path, ["phase", "phase5_tdd_red"]).returncode == 0

        assert _run_workflow(tmp_path, ["write-log", "success"]).returncode == 0

        log = _read_log(tmp_path)
        assert log["phases_skipped"] == ["phase2_analyse", "phase6_implement"]
        assert "phase2_analyse" not in log["phases_completed"]
        assert "phase1_context" in log["phases_completed"]


class TestApprovalIsRecordedAsTransition:
    def test_listener_approval_appends_to_phase_transitions(self, tmp_path):
        """Ursache 2: der Freigabe-Pfad muss `phase_transitions` mitpflegen, damit die
        Struktur nicht je nach Uebergangsart unterschiedlich vollstaendig ist."""
        _make_workflow(tmp_path)
        assert _run_workflow(tmp_path, ["phase", "phase3_spec"]).returncode == 0

        before = _wf_state(tmp_path)["phase_transitions"]
        approval = _run_listener(tmp_path, "approved")
        assert approval.returncode == 0, approval.stderr

        transitions = _wf_state(tmp_path)["phase_transitions"]
        assert len(transitions) == len(before) + 1
        entry = transitions[-1]
        assert entry["from"] == "phase3_spec"
        assert entry["to"] == "phase4_approved"
        assert entry["at"]
        assert entry["trigger"] == "approval"

    def test_status_counts_the_approval_transition(self, tmp_path):
        """Nebenbefund aus #111: `status` zaehlt `phase_transitions` und zeigte durch
        die fehlende Freigabe-Transition eine um eins zu niedrige Zahl."""
        _make_workflow(tmp_path)
        assert _run_workflow(tmp_path, ["phase", "phase3_spec"]).returncode == 0
        assert _run_listener(tmp_path, "approved").returncode == 0

        out = _run_workflow(tmp_path, ["status"]).stdout
        assert "Phase Transitions: 2" in out
