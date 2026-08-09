"""Regressionstest für Issue #1478 (Teil 2): `workflow.py complete` ist aus jeder
worktree-isolierten Claude-Code-Sitzung heraus nicht ausführbar — der Worktree-
Wächter des Harness liest das Wort `complete` als bash-Builtin (programmierbare
Vervollständigung) und blockiert die gesamte Kommandozeile, unabhängig vom
vorangestellten Pfad. Gemessen: schon `echo complete` wird abgewiesen, während
`echo finish` durchläuft.

Fix: zusätzlicher, gleichwertiger Unterbefehlsname `finish` im COMMANDS-Dict.
`complete` bleibt unverändert gültig (Rückwärtskompatibilität für alle sechs
Claude-Instanzen, die dasselbe Plugin nutzen).

Subprozess-Tests hermetisch (cwd/CLAUDE_PROJECT_DIR=tmp_path), Muster
test_workflow_abandon_82.py.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"


def _run_workflow(tmp_path: Path, args: list, wf_name: str = "wf-under-test"):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = wf_name
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py")] + args,
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )


def _make_completable_workflow(tmp_path: Path, name: str = "wf-under-test"):
    """workflow_type 'bug' — keine Adversary-/Approval-Vorbedingungen, damit
    ausschliesslich der Unterbefehlsname selbst getestet wird, nicht die
    Gate-Logik von cmd_complete."""
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{name}.json").write_text(json.dumps({
        "name": name,
        "workflow_type": "bug",
        "current_phase": "phase8_complete",
        "context_file": "docs/context/x.md",
        "affected_files": [],
        "test_artifacts": [],
        "adversary_verdict": None,
    }))
    log_dir = wf_dir / "_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    (log_dir / f"{ts}_{name}.yaml").write_text("outcome: success\n")
    return wf_dir


def _normalized(archived: dict) -> dict:
    """Archivstand ohne die Felder, die zwischen zwei Workflows zwangslaeufig
    abweichen. `cmd_complete` erzeugt keine Zeitstempel — es setzt nur
    current_phase und schreibt das Dict unveraendert weg."""
    return {k: v for k, v in archived.items() if k != "name"}


class TestFinishAlias:
    def test_finish_archives_like_complete(self, tmp_path):
        """AC-1: `finish` liefert denselben End-State wie `complete`."""
        wf_dir_a = _make_completable_workflow(tmp_path, name="via-complete")
        result_complete = _run_workflow(tmp_path, ["complete"], wf_name="via-complete")
        assert result_complete.returncode == 0, result_complete.stderr

        wf_dir_b = _make_completable_workflow(tmp_path, name="via-finish")
        result_finish = _run_workflow(tmp_path, ["finish"], wf_name="via-finish")
        assert result_finish.returncode == 0, result_finish.stderr

        archived_complete = json.loads(
            (wf_dir_a / "_archive" / "via-complete.json").read_text()
        )
        archived_finish = json.loads(
            (wf_dir_b / "_archive" / "via-finish.json").read_text()
        )

        # Vollstaendiger Dict-Vergleich, nicht nur current_phase: ein `finish`, das
        # nicht auf dieselbe Funktion zeigt, sondern ein leicht abweichendes Duplikat
        # ist, wuerde bei einer Ein-Feld-Pruefung unentdeckt durchgehen.
        assert _normalized(archived_complete) == _normalized(archived_finish)

        # Gegen einen trivial gruenen Vergleich zweier inhaltsarmer Dicts.
        for key in ("workflow_type", "current_phase", "adversary_verdict", "test_artifacts"):
            assert key in archived_finish, f"Feld '{key}' fehlt — Vergleich waere aussagelos"

        assert archived_complete["current_phase"] == archived_finish["current_phase"] == "phase8_complete"
        assert not (wf_dir_a / "via-complete.json").exists()
        assert not (wf_dir_b / "via-finish.json").exists()

    def test_complete_still_works_unchanged(self, tmp_path):
        """AC-2: der Altname bleibt uneingeschraenkt funktionsfaehig."""
        wf_dir = _make_completable_workflow(tmp_path)
        result = _run_workflow(tmp_path, ["complete"])
        assert result.returncode == 0, result.stderr
        assert "completed and archived" in result.stdout
