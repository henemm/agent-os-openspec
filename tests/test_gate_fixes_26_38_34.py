"""Tests für Gate-Fixes #26, #38, #34 (Fast-Track fix-gate-bugs-26-38-34).

#26 — Rebase-Check prüft den tatsächlichen Aufrufkontext (cwd), nicht das Hauptrepo.
#38 — Aktiver Workflow gewinnt Datei-Ownership gegen fremden stale affected_files-Match.
#34 — phase8_complete-Transition auch bei AMBIGUOUS + adversary_ambiguous_override erlaubt.
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


# --- Subprocess-Runner (hermetisch, cwd immer im tmp_path) ---

def _run_bash_gate(env: dict, command: str, cwd: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"command": command}})
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bash_gate.py")],
        input=payload, capture_output=True, text=True, env=full_env, cwd=cwd,
    )


def _run_edit_gate(env: dict, file_path: str, cwd: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"file_path": file_path}})
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "edit_gate.py")],
        input=payload, capture_output=True, text=True, env=full_env, cwd=cwd,
    )


# --- #26: Rebase-Check nutzt cwd statt _root ---

def _git(args, cwd):
    res = subprocess.run(
        ["git", "-c", "user.email=t@t.de", "-c", "user.name=Test",
         "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main"] + args,
        cwd=str(cwd), capture_output=True, text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    assert res.returncode == 0, f"git {args} failed: {res.stderr}"
    return res


def _make_rebase_fixture(tmp_path: Path):
    """origin (bare) + mainrepo (1 Commit hinter origin/main) + current (aktuell)."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(["init", "--bare", "-b", "main", "."], origin)

    work = tmp_path / "work"
    work.mkdir()
    _git(["clone", str(origin), "."], work)
    (work / "f1.txt").write_text("commit1\n")
    _git(["add", "f1.txt"], work)
    _git(["commit", "-m", "c1"], work)
    _git(["push", "-u", "origin", "main"], work)

    # mainrepo: Klon auf Stand commit1
    mainrepo = tmp_path / "mainrepo"
    mainrepo.mkdir()
    _git(["clone", str(origin), "."], mainrepo)

    # origin auf commit2 vorschieben
    (work / "f2.txt").write_text("commit2\n")
    _git(["add", "f2.txt"], work)
    _git(["commit", "-m", "c2"], work)
    _git(["push", "origin", "main"], work)

    # current: frischer Klon → auf origin/main-Stand (commit2)
    current = tmp_path / "current"
    current.mkdir()
    _git(["clone", str(origin), "."], current)

    # Aktiver Workflow-State im Hauptrepo (=_root via CLAUDE_PROJECT_DIR).
    # adversary_verdict=VERIFIED → nur der Rebase-Check (5b) bestimmt das Ergebnis.
    wf_dir = mainrepo / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    wf_data = {
        "name": "rebase-wf",
        "workflow_type": "feature",
        "current_phase": "phase7_validate",
        "spec_approved": True,
        "adversary_verdict": "VERIFIED",
    }
    (wf_dir / "rebase-wf.json").write_text(json.dumps(wf_data))
    return mainrepo, current


def test_26_worktree_current_not_blocked(tmp_path):
    """cwd auf aktuellem Checkout → kein 'hinter origin/main'-Block,
    obwohl das Hauptrepo (CLAUDE_PROJECT_DIR) hinter origin/main liegt."""
    mainrepo, current = _make_rebase_fixture(tmp_path)
    env = {
        "CLAUDE_PROJECT_DIR": str(mainrepo),
        "OPENSPEC_ACTIVE_WORKFLOW": "rebase-wf",
    }
    result = _run_bash_gate(env, "git commit -m test26", cwd=str(current))
    assert "hinter origin/main" not in result.stderr
    assert result.returncode == 0


def test_26_current_behind_still_blocks(tmp_path):
    """Gegenprobe: cwd auf einem Checkout, der selbst hinter origin/main liegt →
    Block-Meldung 'hinter origin/main' bleibt erhalten."""
    mainrepo, current = _make_rebase_fixture(tmp_path)
    env = {
        "CLAUDE_PROJECT_DIR": str(mainrepo),
        "OPENSPEC_ACTIVE_WORKFLOW": "rebase-wf",
    }
    result = _run_bash_gate(env, "git commit -m test26", cwd=str(mainrepo))
    assert result.returncode == 2
    assert "hinter origin/main" in result.stderr


# --- #38: Aktiver Workflow gewinnt gegen fremden stale affected_files-Match ---

_AC_SECTION = (
    "## Acceptance Criteria\n\n"
    "- **AC-1:** Given a valid workflow / When implementing / Then the code passes\n"
)


def _make_ownership_fixture(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    specs = tmp_path / "docs" / "specs"
    specs.mkdir(parents=True)

    # stale-wf: listet die Zieldatei, Spec OHNE AC-Sektion
    (specs / "stale.md").write_text("# Stale Spec\n\nKein AC-Abschnitt.\n")
    stale = {
        "name": "stale-wf",
        "workflow_type": "feature",
        "current_phase": "phase6_implement",
        "spec_file": "docs/specs/stale.md",
        "spec_approved": True,
        "red_test_done": True,
        "affected_files": ["src/module.py"],
    }
    (wf_dir / "stale-wf.json").write_text(json.dumps(stale))

    # active-wf: Spec MIT AC-Sektion, listet die Datei NICHT
    (specs / "active.md").write_text("# Active Spec\n\n" + _AC_SECTION)
    active = {
        "name": "active-wf",
        "workflow_type": "feature",
        "current_phase": "phase6_implement",
        "spec_file": "docs/specs/active.md",
        "spec_approved": True,
        "red_test_done": True,
        "affected_files": [],
    }
    (wf_dir / "active-wf.json").write_text(json.dumps(active))

    code_file = tmp_path / "src" / "module.py"
    code_file.parent.mkdir(parents=True)
    return str(code_file)


def test_38_active_workflow_wins_over_stale(tmp_path):
    """Mit aktivem Workflow wird gegen dessen (AC-vollständige) Spec validiert,
    nicht gegen die stale Spec des fremden affected_files-Match → kein Block."""
    code_file = _make_ownership_fixture(tmp_path)
    env = {
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "OPENSPEC_ACTIVE_WORKFLOW": "active-wf",
    }
    result = _run_edit_gate(env, code_file, cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr


def test_38_fallback_without_active_workflow(tmp_path):
    """Gegenprobe: ohne aktiven Workflow greift der affected_files-Fallback
    weiterhin → stale-wf (ohne AC) ownt die Datei → Block wie bisher."""
    code_file = _make_ownership_fixture(tmp_path)
    env = {
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "OPENSPEC_ACTIVE_WORKFLOW": "",
    }
    result = _run_edit_gate(env, code_file, cwd=str(tmp_path))
    assert result.returncode == 2
    assert "Acceptance Criteria" in result.stderr


# --- #34: phase8_complete bei AMBIGUOUS + Override erlaubt ---

def _run_phase(env: dict, target: str, cwd: str) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py"), "phase", target],
        capture_output=True, text=True, env=full_env, cwd=cwd,
    )


def _make_verdict_workflow(tmp_path: Path, verdict: str, with_override: bool) -> dict:
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    log_dir = wf_dir / "_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "name": "verdict-wf",
        "workflow_type": "feature",
        "current_phase": "phase7_validate",
        "context_file": "docs/context.md",
        "spec_file": "docs/specs/s.md",
        "spec_approved": True,
        "red_test_done": True,
        "adversary_verdict": verdict,
        "phase_transitions": [],
        "phase_log": [],
    }
    if with_override:
        data["adversary_ambiguous_override"] = {"reason": "test", "at": "2026-01-01T00:00:00"}
    (wf_dir / "verdict-wf.json").write_text(json.dumps(data))
    return data


def _env(tmp_path):
    return {
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "OPENSPEC_ACTIVE_WORKFLOW": "verdict-wf",
    }


def test_34_ambiguous_with_override_transitions(tmp_path):
    """AMBIGUOUS + adversary_ambiguous_override → phase8_complete erlaubt (Exit 0)."""
    _make_verdict_workflow(tmp_path, "AMBIGUOUS: unklar", with_override=True)
    result = _run_phase(_env(tmp_path), "phase8_complete", cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr


def test_34_ambiguous_without_override_blocks(tmp_path):
    """Gegenprobe: AMBIGUOUS ohne Override → Block mit 'Adversary verdict'."""
    _make_verdict_workflow(tmp_path, "AMBIGUOUS: unklar", with_override=False)
    result = _run_phase(_env(tmp_path), "phase8_complete", cwd=str(tmp_path))
    assert result.returncode != 0
    assert "Adversary verdict" in result.stderr


def test_34_broken_with_override_still_blocks(tmp_path):
    """Gegenprobe: BROKEN + Override → weiterhin Block (Override gilt nur für AMBIGUOUS)."""
    _make_verdict_workflow(tmp_path, "BROKEN: kaputt", with_override=True)
    result = _run_phase(_env(tmp_path), "phase8_complete", cwd=str(tmp_path))
    assert result.returncode != 0
    assert "Adversary verdict" in result.stderr


def test_34_verified_still_transitions(tmp_path):
    """Invariante: VERIFIED-Pfad unverändert → phase8_complete erlaubt."""
    _make_verdict_workflow(tmp_path, "VERIFIED", with_override=False)
    result = _run_phase(_env(tmp_path), "phase8_complete", cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr
