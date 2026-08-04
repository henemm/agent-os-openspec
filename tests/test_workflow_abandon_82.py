"""Regressionstests für Issue #82: Workflows ohne Implementierung abschließen.

Befund: Ein feature-Workflow, der nie eine Implementierung hatte (reine
Analyse-/Kontext-Arbeit), war nicht regelkonform beendbar — `complete`
verlangt ein Adversary-Verdict, das es ohne Prüfgegenstand nie geben kann.
Der einzige Ausweg war eine Typ-Umklassifizierung (`set-field workflow_type
bug`) — genau das Gaming-Muster, das die Gates verhindern sollen.

Fix 1: `workflow.py abandon --reason "..."` — ehrlicher Endzustand
`abandoned` (nicht `complete`), Pflicht-Begründung, Archivierung.
Fix 2: Die Statusmeldung nach einem Abschluss meldet den gewollten Zustand
"kein aktiver Workflow" nicht mehr als FATAL und empfiehlt nicht mehr,
einen archivierten Workflow per `switch` zu reaktivieren.

Subprozess-Tests hermetisch (cwd/CLAUDE_PROJECT_DIR=tmp_path).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"


def _run_workflow(tmp_path: Path, args: list, wf_name: str = "analyse-vorlauf"):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = wf_name
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py")] + args,
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )


def _make_analysis_workflow(tmp_path: Path, name: str = "analyse-vorlauf"):
    """Der #82-Fall: phase3_spec, context_file gesetzt, keine Implementierung."""
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{name}.json").write_text(json.dumps({
        "name": name,
        "workflow_type": "feature",
        "current_phase": "phase3_spec",
        "context_file": "docs/context/analyse.md",
        "affected_files": [],
        "test_artifacts": [],
        "adversary_verdict": None,
    }))
    return wf_dir


class TestAbandonCommand:
    def test_complete_still_blocked_without_verdict(self, tmp_path):
        """Kontrolle: der #82-Zustand blockt bei `complete` weiterhin —
        abandon ist der Ausweg, nicht eine Aufweichung von complete."""
        _make_analysis_workflow(tmp_path)
        result = _run_workflow(tmp_path, ["complete"])
        assert result.returncode == 1
        assert "BLOCKED" in result.stderr

    def test_abandon_archives_with_reason(self, tmp_path):
        wf_dir = _make_analysis_workflow(tmp_path)
        result = _run_workflow(
            tmp_path,
            ["abandon", "--reason", "Analyse-Vorlauf, Umsetzung in FEAT_002"],
        )
        assert result.returncode == 0, result.stderr
        assert "abandoned" in result.stdout

        # Aktiver Eintrag weg, Archiv-Eintrag da, Status ehrlich benannt
        assert not (wf_dir / "analyse-vorlauf.json").exists()
        archived = json.loads(
            (wf_dir / "_archive" / "analyse-vorlauf.json").read_text()
        )
        assert archived["status"] == "abandoned"
        assert archived["abandon_reason"] == "Analyse-Vorlauf, Umsetzung in FEAT_002"
        assert archived["current_phase"] == "phase3_spec"  # NICHT phase8_complete

    def test_abandon_without_reason_refused(self, tmp_path):
        wf_dir = _make_analysis_workflow(tmp_path)
        result = _run_workflow(tmp_path, ["abandon"])
        assert result.returncode == 1
        assert "Begruendung" in result.stderr or "reason" in result.stderr
        assert (wf_dir / "analyse-vorlauf.json").exists()  # nichts passiert

    def test_abandon_accepts_positional_reason(self, tmp_path):
        _make_analysis_workflow(tmp_path)
        result = _run_workflow(tmp_path, ["abandon", "Ergebnisse", "in", "Folge-Workflow"])
        assert result.returncode == 0, result.stderr

    def test_retro_list_shows_abandoned(self, tmp_path):
        _make_analysis_workflow(tmp_path)
        _run_workflow(tmp_path, ["abandon", "--reason", "Analyse-Vorlauf"])
        result = _run_workflow(tmp_path, ["retro-list"], wf_name="")
        assert "abgebrochen" in result.stdout


class TestNoActiveWorkflowMessage:
    def test_stale_symlink_to_archived_workflow_not_fatal(self, tmp_path):
        """#82 Nebenbefund: Nach dem Abschluss zeigte ein veralteter
        .active-Symlink auf den gerade archivierten Workflow — status
        meldete FATAL und empfahl, ihn per switch zu reaktivieren."""
        wf_dir = _make_analysis_workflow(tmp_path)
        _run_workflow(tmp_path, ["abandon", "--reason", "Analyse-Vorlauf"])
        # Veralteten Symlink auf den archivierten Workflow legen
        link = wf_dir / ".active"
        if not link.is_symlink():
            link.symlink_to(wf_dir / "analyse-vorlauf.json")

        result = _run_workflow(tmp_path, ["status"], wf_name="")
        assert result.returncode == 1
        assert "FATAL" not in result.stderr
        assert "switch analyse-vorlauf" not in result.stderr
        assert "No active workflow" in result.stderr

    def test_symlink_to_existing_workflow_still_suggests_switch(self, tmp_path):
        """Zeigt der Symlink auf einen NICHT archivierten Workflow, bleibt
        der switch-Hinweis erhalten (ohne FATAL-Einstufung)."""
        wf_dir = _make_analysis_workflow(tmp_path, name="noch-aktiv")
        link = wf_dir / ".active"
        link.symlink_to(wf_dir / "noch-aktiv.json")

        result = _run_workflow(tmp_path, ["status"], wf_name="")
        assert result.returncode == 1
        assert "FATAL" not in result.stderr
        assert "switch noch-aktiv" in result.stderr
