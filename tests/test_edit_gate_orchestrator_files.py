"""Tests für #48 — edit_gate ORCHESTRATOR_FILES-Sperre.

Zwei Lücken:
1. Der Substring-Match `.claude/settings.json` traf fälschlich auch die
   GLOBALE User-Konfiguration `~/.claude/settings.json`.
2. Der Block feuerte vor der Override-Prüfung → nie überschreibbar.

Alle Tests hermetisch: eigenes Fake-HOME + Fake-Projekt im tmp_path,
Subprozess mit cwd=tmp_path (Muster aus test_gate_fixes_26_38_34.py).
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"


def _run_edit_gate(env: dict, file_path: str, cwd: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"file_path": file_path}})
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "edit_gate.py")],
        input=payload, capture_output=True, text=True, env=full_env, cwd=cwd,
    )


def _make_project(tmp_path: Path) -> Path:
    """Fake-Projekt mit .git und .claude/ (find_project_root findet es via CLAUDE_PROJECT_DIR)."""
    proj = tmp_path / "project"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude").mkdir(parents=True)
    return proj


def _write_token(proj: Path, workflow_name: str = "fix-wf") -> None:
    """Gültigen Override-Token im Fake-Projekt anlegen (Format aus override_token.py)."""
    token_file = proj / ".claude" / "user_override_token.json"
    data = {
        "version": 2,
        "tokens": {
            workflow_name: {
                "created": datetime.now().isoformat(),
                "granted_by": "user_prompt",
            }
        },
    }
    token_file.write_text(json.dumps(data))


# --- (a) Globale ~/.claude/settings.json wird NICHT geblockt ---

def test_global_home_claude_settings_not_blocked(tmp_path):
    """Ein Pfad unter ~/.claude/ (Fake-HOME) ist von der Orchestrator-Sperre ausgenommen."""
    fake_home = tmp_path / "fakehome"
    (fake_home / ".claude").mkdir(parents=True)
    global_settings = fake_home / ".claude" / "settings.json"
    global_settings.write_text("{}")

    proj = _make_project(tmp_path)
    env = {
        "HOME": str(fake_home),
        "CLAUDE_PROJECT_DIR": str(proj),
        "OPENSPEC_ACTIVE_WORKFLOW": "",
    }
    result = _run_edit_gate(env, str(global_settings), cwd=str(proj))
    assert result.returncode == 0, result.stderr


# --- (b) Projekt-.claude/settings.json ohne Token → Block (Bestand) ---

def test_project_settings_blocked_without_token(tmp_path):
    """Projekt-lokale settings.json bleibt ohne Override gesperrt (Kern-Schutz)."""
    fake_home = tmp_path / "fakehome"
    (fake_home / ".claude").mkdir(parents=True)

    proj = _make_project(tmp_path)
    project_settings = proj / ".claude" / "settings.json"
    project_settings.write_text("{}")

    env = {
        "HOME": str(fake_home),
        "CLAUDE_PROJECT_DIR": str(proj),
        "OPENSPEC_ACTIVE_WORKFLOW": "",
    }
    result = _run_edit_gate(env, str(project_settings), cwd=str(proj))
    assert result.returncode == 2
    assert "Orchestrator" in result.stderr


# --- (c) Projekt-.claude/settings.json mit gültigem Token → erlaubt ---

def test_project_settings_allowed_with_valid_token(tmp_path):
    """Gültiger Override-Token gibt die Projekt-settings.json frei (#48)."""
    fake_home = tmp_path / "fakehome"
    (fake_home / ".claude").mkdir(parents=True)

    proj = _make_project(tmp_path)
    project_settings = proj / ".claude" / "settings.json"
    project_settings.write_text("{}")
    _write_token(proj)

    env = {
        "HOME": str(fake_home),
        "CLAUDE_PROJECT_DIR": str(proj),
        "OPENSPEC_ACTIVE_WORKFLOW": "",
    }
    result = _run_edit_gate(env, str(project_settings), cwd=str(proj))
    assert result.returncode == 0, result.stderr
