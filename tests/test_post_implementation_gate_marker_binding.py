"""RED-Tests fuer Issue #134: Freigabe-Marker `user_approved_validation_<name>`
war bislang eine leere Datei, geprueft nur auf Existenz. Ein Marker, der seinen
Workflow ueberlebt, entsperrte damit jeden spaeteren Workflow desselben Namens
beim ersten Code-Edit — ohne dass ein Mensch die neuen Aenderungen gesehen hat.

Diese Tests decken die Bindung des Markers an den `created`-Zeitstempel des
aktuell lebenden `pending_validation_<name>.json`-Locks ab (Spec:
docs/specs/fix-134-approval-marker-binding.md, AC-1 bis AC-7). Sie MUESSEN
fehlschlagen, solange `post_implementation_gate.py` nur `approval_path.exists()`
prueft und `phase_listener.py` den Marker per `touch()` leer schreibt.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def _make_project(tmp_path: Path, phase: str = "phase6_implement",
                   wf_name: str = "wf-134") -> tuple[Path, str]:
    """Main-Repo (.git als DIR -> kein Worktree) mit aktivem Workflow."""
    (tmp_path / ".git").mkdir()
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{wf_name}.json").write_text(json.dumps({
        "name": wf_name,
        "workflow_type": "feature",
        "current_phase": phase,
        "created": _WF_CREATED,
    }))
    return tmp_path, wf_name


_WF_CREATED = "2026-09-30T10:00:00.000000"


def _lock_path(project: Path, wf_name: str) -> Path:
    return project / ".claude" / f"pending_validation_{wf_name}.json"


def _marker_path(project: Path, wf_name: str) -> Path:
    return project / ".claude" / f"user_approved_validation_{wf_name}"


def _write_lock(project: Path, wf_name: str, created: float,
                workflow_created: str = _WF_CREATED) -> Path:
    path = _lock_path(project, wf_name)
    path.write_text(json.dumps({
        "workflow": wf_name, "workflow_created": workflow_created,
        "created": created, "created_iso": "irrelevant",
    }))
    return path


def _write_marker(project: Path, wf_name: str, content: str) -> Path:
    path = _marker_path(project, wf_name)
    path.write_text(content)
    return path


def _run_gate(project: Path, wf_name: str, file_path: str = "src/foo.py") -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"file_path": file_path}})
    full_env = dict(os.environ)
    full_env.update({
        "CLAUDE_PROJECT_DIR": str(project),
        "OPENSPEC_ACTIVE_WORKFLOW": wf_name,
    })
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "post_implementation_gate.py")],
        input=payload, capture_output=True, text=True, env=full_env, cwd=str(project),
    )


def _run_listener(project: Path, wf_name: str, prompt: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"prompt": prompt})
    full_env = dict(os.environ)
    full_env.update({
        "CLAUDE_PROJECT_DIR": str(project),
        "OPENSPEC_ACTIVE_WORKFLOW": wf_name,
    })
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "phase_listener.py")],
        input=payload, capture_output=True, text=True, env=full_env, cwd=str(project),
    )


def _gate_events(project: Path) -> list[dict]:
    path = project / ".claude" / "gate-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class TestAC1StaleMarkerContentMismatch:
    def test_ac1_stale_marker_content_mismatch_blocks_and_discards(self, tmp_path):
        project, wf = _make_project(tmp_path)
        lock_path = _write_lock(project, wf, created=1000.0)
        marker_path = _write_marker(project, wf, "999.0")  # passt nicht zum lebenden Lock

        result = _run_gate(project, wf)

        assert result.returncode == 2
        assert "BLOCKED" in result.stderr
        assert not marker_path.exists(), "Ungueltiger Marker muss verworfen werden"
        assert lock_path.exists(), "Lock bleibt bestehen, neue Freigabe wird verlangt"


class TestAC2MarkerWithoutLockIsDiscarded:
    def test_ac2_marker_without_lock_discarded_and_treated_as_fresh(self, tmp_path):
        project, wf = _make_project(tmp_path)
        marker_path = _write_marker(project, wf, "12345.0")
        assert not _lock_path(project, wf).exists()

        result = _run_gate(project, wf)

        assert result.returncode == 0
        assert not marker_path.exists(), "Marker ohne Lock ist keine gueltige Freigabe"
        assert _lock_path(project, wf).exists(), "Gate legt frischen Lock an wie bei unbekanntem Workflow"


class TestAC3MatchingMarkerAllows:
    def test_ac3_matching_marker_clears_lock_and_allows(self, tmp_path):
        project, wf = _make_project(tmp_path)
        lock_path = _write_lock(project, wf, created=555.5)
        marker_path = _write_marker(project, wf, "555.5")

        result = _run_gate(project, wf)

        assert result.returncode == 0
        assert not marker_path.exists()
        assert not lock_path.exists()


class TestAC4ReusedWorkflowNameDoesNotAutoUnlock:
    def test_ac4_reused_workflow_name_stale_marker_does_not_unlock_new_run(self, tmp_path):
        project, wf = _make_project(tmp_path)
        # Alter Marker eines abgeschlossenen Laufs liegt noch herum (siehe Issue: 9 solcher
        # Dateien im Arbeitsbaum), der zugehoerige Lock existiert nicht mehr — ein neuer
        # Workflow desselben Namens beginnt gerade erst.
        marker_path = _write_marker(project, wf, "111111.0")

        result = _run_gate(project, wf, file_path="src/new_feature.py")

        assert result.returncode == 0, "Erster Edit des neuen Laufs bleibt erlaubt"
        assert not marker_path.exists(), "Alter Marker darf NICHT als Freigabe fuer den neuen Lauf zaehlen"
        new_lock_path = _lock_path(project, wf)
        assert new_lock_path.exists()
        new_lock = json.loads(new_lock_path.read_text())
        assert new_lock["created"] != 111111.0, "Frischer Lock, nicht der alte Zeitstempel"


class TestAC4bStaleLockMarkerPairAcrossWorkflowLifetimes:
    def test_ac4b_stale_lock_marker_pair_from_reused_name_does_not_unlock(self, tmp_path):
        project, wf = _make_project(tmp_path)
        # Zueinander passendes Lock+Marker-Paar aus einem FRUEHEREN Lauf gleichen Namens
        lock_path = _write_lock(project, wf, created=222222.0,
                                workflow_created="2026-01-01T00:00:00.000000")
        marker_path = _write_marker(project, wf, "222222.0")

        result = _run_gate(project, wf, file_path="src/new_feature.py")

        assert result.returncode == 0, "Erster Edit des neuen Laufs bleibt erlaubt"
        assert not marker_path.exists(), "Alter Marker darf den neuen Lauf nicht entsperren"
        assert lock_path.exists(), "Frischer Lock fuer den neuen Lauf statt Entsperren"
        new_lock = json.loads(lock_path.read_text())
        assert new_lock["created"] != 222222.0, "Alter Lock wurde verworfen, nicht wiederverwendet"
        assert new_lock["workflow_created"] == _WF_CREATED


class TestAC5RejectedMarkerIsLogged:
    def test_ac5_rejected_marker_is_logged_to_gate_events(self, tmp_path):
        project, wf = _make_project(tmp_path)
        assert _gate_events(project) == []

        # Mismatch-Fall (AC-1)
        _write_lock(project, wf, created=42.0)
        _write_marker(project, wf, "41.0")
        mismatch_result = _run_gate(project, wf)
        assert mismatch_result.returncode == 2

        events_after_mismatch = _gate_events(project)
        assert any(e.get("hook") == "post_implementation_gate" for e in events_after_mismatch), (
            "Mismatch-Ablehnung muss ueber block() geloggt werden"
        )

        # Lock-loser Verwurf (AC-2/AC-4), eigener Workflow-Name zur sauberen Isolation
        wf2 = "wf-134-lockless"
        (project / ".claude" / "workflows" / f"{wf2}.json").write_text(json.dumps({
            "name": wf2, "workflow_type": "feature", "current_phase": "phase6_implement",
        }))
        _write_marker(project, wf2, "77.0")
        lockless_result = _run_gate(project, wf2)
        assert lockless_result.returncode == 0

        events_after_lockless = _gate_events(project)
        assert len(events_after_lockless) > len(events_after_mismatch), (
            "Auch der nicht-blockierende Verwurf muss einen eigenen Log-Eintrag erzeugen"
        )
        new_events = events_after_lockless[len(events_after_mismatch):]
        assert any(
            e.get("hook") == "post_implementation_gate" and "Pruflauf" in e.get("reason", "")
            for e in new_events
        ), "Log-Grund muss den fehlenden aktiven Pruflauf-Lock nennen"


class TestAC6GreenApprovalWritesLockTimestamp:
    def test_ac6_green_approval_writes_lock_created_value_into_marker(self, tmp_path):
        project, wf = _make_project(tmp_path)
        _write_lock(project, wf, created=987654.321)

        result = _run_listener(project, wf, "go")

        assert result.returncode == 0
        marker_path = _marker_path(project, wf)
        assert marker_path.exists()
        assert marker_path.read_text().strip() == str(987654.321), (
            "Marker-Inhalt muss der created-Wert des Locks sein, kein leerer Touch"
        )


class TestAC7GreenApprovalWithoutLockWritesNoMarker:
    def test_ac7_green_approval_without_lock_writes_no_marker(self, tmp_path):
        project, wf = _make_project(tmp_path)
        assert not _lock_path(project, wf).exists()

        result = _run_listener(project, wf, "go")

        assert result.returncode == 0
        assert not _marker_path(project, wf).exists(), (
            "Ohne lebenden Lock darf kein Marker entstehen (fail-closed)"
        )
        wf_state = json.loads((project / ".claude" / "workflows" / f"{wf}.json").read_text())
        assert wf_state.get("green_approved") is True, (
            "GREEN-Freigabe selbst bleibt im State wirksam, nur das Gate entsperrt sich nicht automatisch"
        )


class TestIssue300MissingIdentity:
    """#300: Lock im Alt-Format (ohne workflow_created) trifft auf Workflow ohne
    `created` — None == None durfte nicht als 'dieselbe Instanz' gelten."""

    def _project_without_created(self, tmp_path):
        project, wf = _make_project(tmp_path)
        wf_file = project / ".claude" / "workflows" / f"{wf}.json"
        data = json.loads(wf_file.read_text())
        del data["created"]
        wf_file.write_text(json.dumps(data))
        return project, wf

    def test_legacy_lock_with_matching_marker_is_not_an_approval(self, tmp_path):
        project, wf = self._project_without_created(tmp_path)
        _lock_path(project, wf).write_text(json.dumps({"workflow": wf, "created": 1000.0}))
        marker = _write_marker(project, wf, "1000.0")

        _run_gate(project, wf)

        assert not marker.exists(), "Marker eines nicht zuordenbaren Locks gilt nicht"
        lock = json.loads(_lock_path(project, wf).read_text())
        assert lock["created"] != 1000.0, "Alt-Lock muss durch frischen Lock ersetzt sein"

    def test_gate_still_works_for_workflow_without_created(self, tmp_path):
        """Kein Fail-open: der vom Gate selbst geschriebene Lock bleibt gueltig."""
        import time
        project, wf = self._project_without_created(tmp_path)
        assert _run_gate(project, wf).returncode == 0  # legt Lock an
        lock = json.loads(_lock_path(project, wf).read_text())
        lock["created"] = time.time() - 10 * 3600  # Batch-Fenster sicher abgelaufen
        _lock_path(project, wf).write_text(json.dumps(lock))
        r = _run_gate(project, wf)
        assert r.returncode == 2 and "BLOCKED" in r.stderr, r.stderr
