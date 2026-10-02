"""Tests für #322 — im Framework-Repo entfällt der Override für core/hooks und
core/agents, solange ein Workflow ab phase6 läuft; die regulären Prüfungen
(Phase, RED-Artefakte) greifen stattdessen.

Gleiche Aufrufart wie tests/test_edit_gate_framework_source_115.py.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_edit_gate_framework_source_115 import (  # noqa: E402
    _env, _make_project, _run_edit_gate, _touch,
)

WF = "wf322"


def _start_workflow(proj: Path, phase: str, red: bool = True, wf_type: str = "feature") -> None:
    (proj / ".claude" / "workflows").mkdir(parents=True, exist_ok=True)
    (proj / ".claude" / "active_workflow").write_text(WF + "\n")
    (proj / ".claude" / "workflows" / f"{WF}.json").write_text(json.dumps({
        "name": WF, "current_phase": phase, "workflow_type": wf_type,
        "red_test_done": red,
    }))


def _edit(tmp_path: Path, proj: Path, rel: str):
    target = _touch(proj, rel)
    return _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))


def test_hooks_im_laufenden_workflow_ohne_override(tmp_path):
    proj = _make_project(tmp_path, framework=True)
    _start_workflow(proj, "phase6_implement")
    for rel in ("core/hooks/workflow.py", "core/agents/helper.py"):
        result = _edit(tmp_path, proj, rel)
        assert result.returncode == 0, f"{rel}: {result.stderr}"


def test_vor_der_umsetzungsphase_bleibt_der_override_noetig(tmp_path):
    proj = _make_project(tmp_path, framework=True)
    _start_workflow(proj, "phase3_spec")
    result = _edit(tmp_path, proj, "core/hooks/workflow.py")
    assert result.returncode == 2, result.stderr
    assert "override" in result.stderr.lower(), result.stderr


def test_ohne_workflow_bleibt_der_override_noetig(tmp_path):
    proj = _make_project(tmp_path, framework=True)
    result = _edit(tmp_path, proj, "core/hooks/workflow.py")
    assert result.returncode == 2, result.stderr
    assert "override" in result.stderr.lower(), result.stderr


def test_reguläre_pruefungen_greifen_statt_des_overrides(tmp_path):
    """Ohne RED-Artefakt blockt weiterhin das TDD-Gate — die Lockerung ist
    kein Freibrief."""
    proj = _make_project(tmp_path, framework=True)
    _start_workflow(proj, "phase6_implement", red=False)
    result = _edit(tmp_path, proj, "core/hooks/workflow.py")
    assert result.returncode == 2, result.stderr
    assert "RED" in result.stderr, result.stderr


def test_projekt_hooks_ordner_bleibt_geschuetzt(tmp_path):
    """Die Lockerung gilt nur für die Framework-Quellen, nicht für .claude/hooks/."""
    proj = _make_project(tmp_path, framework=True)
    _start_workflow(proj, "phase6_implement")
    result = _edit(tmp_path, proj, ".claude/hooks/x.py")
    assert result.returncode == 2, result.stderr
    assert "override" in result.stderr.lower(), result.stderr
