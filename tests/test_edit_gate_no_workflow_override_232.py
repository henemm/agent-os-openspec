"""Tests für #232 — 'No active workflow'-Block prüft keinen Override-Token.

Ausgangslage: Anders als der Infrastruktur-Check (Schritt 4) prüfte der
"No active workflow"-Block (Schritt 7) keinen Override-Token. Ein gültiger
globaler Override (__global__, von phase_listener.py ohne aktiven Workflow
vergeben) lief dadurch ins Leere — strukturell derselbe Sackgassen-Fehler
wie #115, nur ueber einen anderen Pfad (fehlender Workflow statt fehlender
Infrastruktur-Marker).

Fix: Schritt 7 bekommt dieselbe Token-Prüfung wie Schritt 4
(_has_override_token("__infra__") or _has_override_token()).

Hermetisch: Fake-HOME + Fake-Projekt im tmp_path, Subprozess mit cwd=tmp_path
(Muster aus test_edit_gate_framework_source_115.py).
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

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
    proj = tmp_path / "project"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude").mkdir(parents=True)
    return proj


def _env(tmp_path: Path, proj: Path) -> dict:
    fake_home = tmp_path / "fakehome"
    (fake_home / ".claude").mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(fake_home),
        "CLAUDE_PROJECT_DIR": str(proj),
        "OPENSPEC_ACTIVE_WORKFLOW": "",
    }


def _write_token(proj: Path, workflow_name: str = "__global__") -> None:
    (proj / ".claude" / "user_override_token.json").write_text(json.dumps({
        "version": 2,
        "tokens": {workflow_name: {
            "created": datetime.now().isoformat(),
            "granted_by": "user_prompt",
        }},
    }))


def _touch(proj: Path, rel: str) -> Path:
    target = proj / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# placeholder\n")
    return target


def test_no_workflow_blocks_without_token(tmp_path):
    """Ohne Workflow und ohne Token bleibt der Block bestehen (Bestandsverhalten)."""
    proj = _make_project(tmp_path)
    target = _touch(proj, "src/thing.py")

    result = _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))

    assert result.returncode == 2, result.stderr
    assert "No active workflow" in result.stderr, result.stderr


def test_no_workflow_allowed_with_global_override_token(tmp_path):
    """Ein gültiger '__global__'-Token gibt Schritt 7 frei — der Sackgassen-
    Fehler aus #232 ist behoben."""
    proj = _make_project(tmp_path)
    target = _touch(proj, "src/thing.py")
    _write_token(proj, "__global__")

    result = _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))

    assert result.returncode == 0, f"Token wirkungslos: {result.stderr}"


def test_no_workflow_allowed_with_infra_token(tmp_path):
    """Auch der explizite __infra__-Token gibt frei (Symmetrie zu Schritt 4)."""
    proj = _make_project(tmp_path)
    target = _touch(proj, "src/thing.py")
    _write_token(proj, "__infra__")

    result = _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))

    assert result.returncode == 0, result.stderr


def test_no_workflow_expired_token_still_blocks(tmp_path):
    """Ein abgelaufener Token (>1h) darf Schritt 7 nicht freigeben."""
    proj = _make_project(tmp_path)
    target = _touch(proj, "src/thing.py")
    (proj / ".claude" / "user_override_token.json").write_text(json.dumps({
        "version": 2,
        "tokens": {"__global__": {
            "created": "2020-01-01T00:00:00",
            "granted_by": "user_prompt",
        }},
    }))

    result = _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))

    assert result.returncode == 2, result.stderr
    assert "No active workflow" in result.stderr, result.stderr
