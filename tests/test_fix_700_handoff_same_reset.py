"""Vermerk `handoff_same` wird bei jedem Phasenwechsel verworfen (Issue #700).

Spec: docs/specs/fix-700-handoff-same-reset.md (AC-1 bis AC-5).

Fehlerbild: `handoff --same --start` meldete nach einem Ruecksprung
phase6_implement -> phase6b_adversary -> phase6_implement `STARTED=already`, weil der
Vermerk `handoff_same = {phase, next, at}` aus dem ersten Besuch der Phase noch im
State stand. Erwartung: `record_transition` (einziger Wechselpfad, #111) und
`cmd_complete` entfernen den Vermerk wie `waiting_on` (#550).

Kein Netz: Fake-herdr und Fake-`claude` aus den Helfern von #694/#696; workflow.py laeuft
als Subprozess aus einer Hook-Kopie im tmp-Projekt (cwd = tmp-Projekt).
"""

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_handoff_667 import HOOKS_DIR, REPO_ROOT, WF, _calls, _kv, _of, _parse  # noqa: E402
from test_handoff_tab_694 import _fake  # noqa: E402
from test_feat_696_handoff_same import (  # noqa: E402
    NEXT, STATE_RED_DONE, _full_env, _same, _set_state, _state, _state_file, _wf_project,
)

NEXT_PHASE6 = "/50-implement #547"
AT = "2026-11-26T09:00:00Z"

# Felder, mit denen die Vorwaertswechsel bis phase6b_adversary nicht vom Gate geblockt
# werden: Kontext, freigegebene Spec (Datei fehlt -> ADR-/Briefing-Gate lenient), RED fertig.
GATE_OK = {"context_file": "docs/context/feat-547-x.md",
           "spec_file": "docs/specs/feat-547-x.md", "spec_approved": True,
           "red_test_done": True}


def _wf(proj: Path, *args: str, env: dict):
    return subprocess.run([sys.executable, str(proj / ".claude" / "hooks" / "workflow.py"),
                           *args], capture_output=True, text=True, env=env, cwd=str(proj),
                          timeout=60)


def _phase(proj: Path, target: str, env: dict) -> None:
    res = _wf(proj, "phase", target, env=env)
    assert res.returncode == 0, (target, res.stdout, res.stderr)
    assert _state(proj)["current_phase"] == target, _state(proj)


# --- AC-1 -------------------------------------------------------------------

def test_phase_change_removes_handoff_same_note(tmp_path):
    """AC-1: `workflow.py phase <andere Phase>` entfernt den Vermerk `handoff_same`."""
    note = {"phase": "phase6_implement", "next": NEXT_PHASE6, "at": AT}
    proj = _wf_project(tmp_path / "p", current_phase="phase6_implement",
                       handoff_same=note, **GATE_OK)
    herdr = _fake(tmp_path / "p")
    env = _full_env(proj, herdr)
    assert _state(proj).get("handoff_same") == note
    _phase(proj, "phase6b_adversary", env)
    assert "handoff_same" not in _state(proj), _state(proj)


# --- AC-2 -------------------------------------------------------------------

def test_restart_possible_after_return_to_same_phase(tmp_path):
    """AC-2: Ruecksprung 6 -> 6b -> 6 mit altem Vermerk -> `--same --start` startet neu."""
    proj = _wf_project(tmp_path / "p", current_phase="phase6_implement", **GATE_OK)
    herdr = _fake(tmp_path / "p")
    env = _full_env(proj, herdr)

    probe = _same(proj, env=env)
    assert probe.returncode == 0, (probe.stdout, probe.stderr)
    next_cmd = _kv(_parse(probe.stdout)[0], "NEXT")
    assert next_cmd == NEXT_PHASE6, probe.stdout
    _set_state(proj, handoff_same={"phase": "phase6_implement", "next": next_cmd, "at": AT})

    _phase(proj, "phase6b_adversary", env)
    _phase(proj, "phase6_implement", env)
    assert _of(_calls(proj), "tab create") == [], _calls(proj)

    res = _same(proj, "--start", env=env)
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, _ = _parse(res.stdout)
    assert _kv(lines, "HANDOFF") == "herdr", res.stdout
    assert _kv(lines, "STARTED") == "yes", (res.stdout, res.stderr)
    assert len(_of(_calls(proj), "tab create")) == 1, _calls(proj)


# --- AC-3 -------------------------------------------------------------------

def test_second_start_without_phase_change_stays_already(tmp_path):
    """AC-3: ohne Phasenwechsel zweimal starten -> zweites Mal already, nur ein Tab."""
    proj = _wf_project(tmp_path / "p")
    herdr = _fake(tmp_path / "p")
    env = _full_env(proj, herdr)
    first = _same(proj, "--start", env=env)
    lines, _ = _parse(first.stdout)
    assert _kv(lines, "STARTED") == "yes", (first.stdout, first.stderr)
    assert _kv(lines, "NEXT") == NEXT, first.stdout
    note = _state(proj).get("handoff_same")
    assert isinstance(note, dict) and note.get("phase") == "phase5_tdd_red", _state(proj)

    second = _same(proj, "--start", env=env)
    assert second.returncode == 0, (second.stdout, second.stderr)
    assert _kv(_parse(second.stdout)[0], "STARTED") == "already", second.stdout
    assert len(_of(_calls(proj), "tab create")) == 1, _calls(proj)
    assert _state(proj).get("handoff_same") == note


# --- AC-4 -------------------------------------------------------------------

def test_approval_transition_and_complete_remove_note(tmp_path):
    """AC-4: Freigabe-Uebergang nach phase4_approved (record_transition, Trigger approval)
    und `workflow.py complete` entfernen den Vermerk."""
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415

    # (a) Freigabe-Pfad: _apply_spec_approval -> record_transition(..., "phase4_approved")
    data = {"name": WF, "workflow_type": "feature", "current_phase": "phase3_spec",
            "spec_file": "docs/specs/feat-547-x.md", "phase_transitions": [],
            "phase_log": [],
            "handoff_same": {"phase": "phase3_spec", "next": "approved", "at": AT}}
    workflow._apply_spec_approval(data, "approval")
    assert data["current_phase"] == "phase4_approved", data
    assert data["phase_transitions"][-1]["to"] == "phase4_approved", data
    approval_kept = data.get("handoff_same")

    # (b) complete: Fast Track in phase7_validate mit Execution-Log (Gates gruen)
    note = {"phase": "phase7_validate", "next": "/60-validate #547", "at": AT}
    proj = _wf_project(tmp_path / "c", workflow_type="feature-fast",
                       current_phase="phase7_validate",
                       spec_file="docs/specs/feat-547-x.md", spec_approved=True,
                       handoff_same=note)
    log = proj / ".claude" / "workflows" / "_log" / f"20261127100000_{WF}.yaml"
    log.write_text("outcome: success\n")
    herdr = _fake(tmp_path / "c")
    res = _wf(proj, "complete", env=_full_env(proj, herdr))
    assert res.returncode == 0, (res.stdout, res.stderr)
    archived = proj / ".claude" / "workflows" / "_archive" / f"{WF}.json"
    assert archived.exists(), res.stdout
    assert not _state_file(proj).exists(), res.stdout
    data = json.loads(archived.read_text())
    assert data["current_phase"] == "phase8_complete", data
    complete_kept = data.get("handoff_same")
    assert approval_kept is None and complete_kept is None, (
        f"Vermerk nach Freigabe: {approval_kept!r}; nach complete: {complete_kept!r}")


# --- AC-5 -------------------------------------------------------------------

def test_changelog_and_version_consistent():
    """AC-5: CHANGELOG 4.28.1 mit #700; plugin.json und CLAUDE.md nennen 4.28.1."""
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## \[4\.28\.1\][^\n]*\n(.*?)(?=^## \[)", changelog, re.M | re.S)
    assert m, "CHANGELOG ohne Abschnitt 4.28.1"
    assert "#700" in m.group(1), m.group(1)

    plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin.get("version") == "4.28.1", plugin.get("version")
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "**Version**: 4.28.1" in claude_md, "CLAUDE.md-Versionszeile nicht 4.28.1"
