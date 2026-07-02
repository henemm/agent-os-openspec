"""Tests für spec: Resolve Execution Context Consolidation.

Deckt Test-Plan-Punkte 1-4 und 9 aus
docs/specs/resolve-execution-context-consolidation.md ab.

Kernaussage: `workflow.py` löst den aktiven Workflow-Namen NICHT mehr über eigene
duplizierte Logik auf, sondern delegiert an `hook_utils.resolve_active_workflow()`.
Dadurch verschwindet der Live-Bug (Issue #13): worktree-lokale
`.claude/active_workflow`-Datei zeigt auf Workflow A, aber die (veraltete)
`OPENSPEC_ACTIVE_WORKFLOW`-Env-Var zeigt auf Workflow B → früher FATAL, jetzt
wird Workflow A verwendet.

Diese Tests laufen in-process und mocken die Auflösungs-Kontext-Funktionen
(`find_project_root`, `_find_worktree_root`, `_worktree_root_if_any`), damit sie
hermetisch vom echten Worktree-Zustand der Testsession sind.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import hook_utils  # noqa: E402
import workflow as wf_module  # noqa: E402


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _write_workflow(root: Path, name: str) -> None:
    """Lege eine gültige workflows/<name>.json unter root/.claude/ ab."""
    wf_dir = root / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{name}.json").write_text(
        json.dumps(
            {
                "name": name,
                "workflow_type": "feature",
                "current_phase": "phase1_context",
            }
        )
    )


def _bind_context(monkeypatch, tmp_path: Path, worktree: "Path | None") -> None:
    """Verankere alle Auflösungs-Kontext-Funktionen deterministisch auf tmp_path.

    Patcht sowohl die von workflow.py als auch die von hook_utils genutzten
    Kontext-Funktionen, damit die Tests unabhängig davon grün/rot sind, ob
    workflow.py die alte (duplizierte) oder die neue (delegierende) Logik hat.
    """
    monkeypatch.setattr(wf_module, "find_project_root", lambda: tmp_path)
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: tmp_path)
    monkeypatch.setattr(hook_utils, "_find_worktree_root", lambda: worktree)
    monkeypatch.setattr(wf_module, "_worktree_root_if_any", lambda: worktree)


# --------------------------------------------------------------------------
# Test 1: Live-Bug-Regression (Issue #13)
# --------------------------------------------------------------------------

def test_1_file_beats_stale_env_no_fatal(monkeypatch, tmp_path):
    """Worktree-Datei zeigt auf A, Env (veraltet) auf B → A wird verwendet, kein FATAL.

    Reproduziert den Live-Bug: der alte `_read_active()`-FATAL-Pfad liest die
    Env-Var zuerst, findet keine passende workflows/B.json und ruft sys.exit(1).
    Nach der Konsolidierung gewinnt die worktree-lokale active_workflow-Datei
    (Workflow A).
    """
    _write_workflow(tmp_path, "workflow-a")  # existiert
    # Workflow B (aus Env) existiert bewusst NICHT
    (tmp_path / ".claude" / "active_workflow").write_text("workflow-a")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-b")
    _bind_context(monkeypatch, tmp_path, worktree=tmp_path)

    data, name = wf_module._read_active()

    assert name == "workflow-a"
    assert data.get("name") == "workflow-a"


def test_1b_fast_file_beats_stale_env(monkeypatch, tmp_path):
    """read_active_workflow_fast() löst im selben Live-Bug-Szenario Workflow A auf."""
    _write_workflow(tmp_path, "workflow-a")
    (tmp_path / ".claude" / "active_workflow").write_text("workflow-a")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-b")
    _bind_context(monkeypatch, tmp_path, worktree=tmp_path)

    result = wf_module.read_active_workflow_fast()

    assert result is not None
    name, data = result
    assert name == "workflow-a"


# --------------------------------------------------------------------------
# Test 2: Env als dritte Priorität (kein Worktree)
# --------------------------------------------------------------------------

def test_2_env_resolves_when_no_worktree_no_file(monkeypatch, tmp_path):
    """Kein Worktree, keine Datei/Settings, gültige Env-Var → Auflösung aus Env."""
    _write_workflow(tmp_path, "workflow-env")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-env")
    _bind_context(monkeypatch, tmp_path, worktree=None)

    data, name = wf_module._read_active()

    assert name == "workflow-env"
    assert data.get("name") == "workflow-env"


def test_2b_fast_env_resolves_when_no_worktree(monkeypatch, tmp_path):
    """read_active_workflow_fast() löst ebenfalls aus der Env-Var auf (kein Worktree)."""
    _write_workflow(tmp_path, "workflow-env")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-env")
    _bind_context(monkeypatch, tmp_path, worktree=None)

    result = wf_module.read_active_workflow_fast()

    assert result is not None
    name, _data = result
    assert name == "workflow-env"


# --------------------------------------------------------------------------
# Test 3: Kein Workflow auflösbar → FATAL + sys.exit(1)
# --------------------------------------------------------------------------

def test_3_no_workflow_resolvable_exits(monkeypatch, tmp_path):
    """Weder Datei noch Env noch Settings → 'No active workflow' + sys.exit(1)."""
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    _bind_context(monkeypatch, tmp_path, worktree=None)

    with pytest.raises(SystemExit) as exc:
        wf_module._read_active()

    assert exc.value.code == 1


# --------------------------------------------------------------------------
# Test 4: read_active_workflow_fast() non-fatal → None
# --------------------------------------------------------------------------

def test_4_fast_returns_none_when_unresolvable(monkeypatch, tmp_path):
    """Kein Workflow auflösbar → None, ohne sys.exit()."""
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    _bind_context(monkeypatch, tmp_path, worktree=None)

    # Darf keinen SystemExit auslösen
    result = wf_module.read_active_workflow_fast()

    assert result is None


# --------------------------------------------------------------------------
# Test 9: Regressionsfreiheit — Konsumenten-Signatur bleibt stabil (AC-6)
# --------------------------------------------------------------------------

def test_9_fast_signature_is_tuple_or_none(monkeypatch, tmp_path):
    """read_active_workflow_fast() liefert (name: str, data: dict) oder None — nie sys.exit.

    Absichert die von tdd_enforcement.py und post_implementation_gate.py erwartete
    Rückgabe-Signatur (AC-6): kein Verhaltensbruch bei den Konsumenten.
    """
    _write_workflow(tmp_path, "workflow-sig")
    (tmp_path / ".claude" / "active_workflow").write_text("workflow-sig")
    monkeypatch.setenv("OPENSPEC_ACTIVE_WORKFLOW", "workflow-sig")
    _bind_context(monkeypatch, tmp_path, worktree=tmp_path)

    result = wf_module.read_active_workflow_fast()

    assert result is not None
    assert isinstance(result, tuple) and len(result) == 2
    name, data = result
    assert isinstance(name, str)
    assert isinstance(data, dict)
