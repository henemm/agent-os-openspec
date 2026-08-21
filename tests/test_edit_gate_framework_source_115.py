"""Tests für #115 — edit_gate blockt Fast-Track-Wartung an core/hooks.

Ausgangslage: Im Framework-Repo selbst liegen die Hook-Quellen unter
`core/hooks/`, in Konsumenten-Projekten unter `.claude/hooks/`. Nur der
zweite Pfad stand in INFRASTRUCTURE_DIRS. Ein Edit auf `core/hooks/*.py`
fiel deshalb durch bis zum "No active workflow"-Block — eine Meldung ohne
gangbaren Ausweg, die zum Bash-Umweg einlädt.

Fix: Framework-Quellverzeichnisse zählen als Infrastruktur, aber NUR im
Framework-Repo selbst (Marker: .claude-plugin/plugin.json). Damit greift
der bestehende, TTL-begrenzte Override-Token — kein neuer Bypass.

Alle Tests hermetisch: Fake-HOME + Fake-Projekt im tmp_path, Subprozess
mit cwd=tmp_path (Muster aus test_edit_gate_orchestrator_files.py).
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


def _make_project(tmp_path: Path, framework: bool = False) -> Path:
    """Fake-Projekt. framework=True setzt den Framework-Repo-Marker."""
    proj = tmp_path / "project"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude").mkdir(parents=True)
    if framework:
        marker_dir = proj / ".claude-plugin"
        marker_dir.mkdir()
        (marker_dir / "plugin.json").write_text(
            json.dumps({"name": "agent-os-openspec", "version": "3.14.0"})
        )
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
    """Gültigen Override-Token anlegen (Format aus override_token.py)."""
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


# --- AC-1: Framework-Quelle ohne Workflow → Infrastruktur-Block mit Ausweg ---

def test_framework_core_hooks_blocks_with_override_hint(tmp_path):
    """core/hooks/*.py im Framework-Repo blockt als Infrastruktur, nicht als
    'No active workflow' — die Meldung nennt den gangbaren Weg ('override')."""
    proj = _make_project(tmp_path, framework=True)
    target = _touch(proj, "core/hooks/workflow.py")

    result = _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))

    assert result.returncode == 2, f"erwarteter Block fehlt: {result.stderr}"
    assert "No active workflow" not in result.stderr, (
        "Sackgassen-Meldung statt Infrastruktur-Hinweis: " + result.stderr
    )
    assert "override" in result.stderr.lower(), result.stderr


def test_framework_core_agents_blocks_with_override_hint(tmp_path):
    """Gleiche Regel für core/agents/ — Symmetrie zu .claude/agents/."""
    proj = _make_project(tmp_path, framework=True)
    target = _touch(proj, "core/agents/helper.py")

    result = _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))

    assert result.returncode == 2, result.stderr
    assert "No active workflow" not in result.stderr, result.stderr
    assert "override" in result.stderr.lower(), result.stderr


# --- AC-2: Mit Override-Token ist der reguläre Weg offen ---

def test_framework_core_hooks_allowed_with_global_override_token(tmp_path):
    """Ein '__global__'-Token (den phase_listener ohne Workflow anlegt) gibt
    core/hooks/ frei — Edit/Write wird zum regulären Wartungsweg."""
    proj = _make_project(tmp_path, framework=True)
    target = _touch(proj, "core/hooks/workflow.py")
    _write_token(proj, "__global__")

    result = _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))

    assert result.returncode == 0, f"Token wirkungslos: {result.stderr}"


def test_framework_core_hooks_allowed_with_infra_token(tmp_path):
    """Auch der explizite __infra__-Token gibt frei (Bestandsverhalten aus
    dem .claude/hooks/-Zweig gilt unverändert)."""
    proj = _make_project(tmp_path, framework=True)
    target = _touch(proj, "core/hooks/workflow.py")
    _write_token(proj, "__infra__")

    result = _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))

    assert result.returncode == 0, result.stderr


# --- AC-3: Keine Regression in Konsumenten-Projekten ---

def test_consumer_project_core_hooks_is_not_infrastructure(tmp_path):
    """Ohne Framework-Marker ist 'core/hooks/' ein gewöhnliches Verzeichnis
    (z.B. React-Hooks unter src/core/hooks/) — die Sonderregel greift nicht."""
    proj = _make_project(tmp_path, framework=False)
    target = _touch(proj, "src/core/hooks/useAuth.ts")

    result = _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))

    assert result.returncode == 2, result.stderr
    assert "No active workflow" in result.stderr, (
        "Konsumenten-Projekt fälschlich als Framework behandelt: " + result.stderr
    )


def test_foreign_plugin_marker_is_not_the_framework(tmp_path):
    """Ein .claude-plugin/plugin.json eines FREMDEN Plugins darf die
    Sonderregel nicht auslösen — es zählt nur der Framework-Name."""
    proj = _make_project(tmp_path, framework=False)
    marker = proj / ".claude-plugin"
    marker.mkdir()
    (marker / "plugin.json").write_text(json.dumps({"name": "some-other-plugin"}))
    target = _touch(proj, "core/hooks/thing.py")

    result = _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))

    assert result.returncode == 2, result.stderr
    assert "No active workflow" in result.stderr, result.stderr


# --- AC-4: Infrastruktur-Verzeichnisse sind konfigurierbar ---

def test_infrastructure_dirs_configurable_via_config(tmp_path):
    """Projekte mit eigener Hook-Ablage können sie über
    strict_code_gate.infrastructure_dirs als Infrastruktur deklarieren."""
    proj = _make_project(tmp_path, framework=False)
    (proj / "config.yaml").write_text(
        "strict_code_gate:\n"
        "  infrastructure_dirs:\n"
        '    - "lib/gates/"\n'
    )
    target = _touch(proj, "lib/gates/custom.py")

    result = _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))

    assert result.returncode == 2, result.stderr
    assert "No active workflow" not in result.stderr, result.stderr
    assert "override" in result.stderr.lower(), result.stderr


def test_configured_infrastructure_dirs_replace_defaults_safely(tmp_path):
    """Eine gesetzte Konfiguration darf .claude/hooks/ nicht entsichern —
    der Kern-Schutz bleibt unabhängig von der Projekt-Config bestehen."""
    proj = _make_project(tmp_path, framework=False)
    (proj / "config.yaml").write_text(
        "strict_code_gate:\n"
        "  infrastructure_dirs:\n"
        '    - "lib/gates/"\n'
    )
    target = _touch(proj, ".claude/hooks/edit_gate.py")

    result = _run_edit_gate(_env(tmp_path, proj), str(target), cwd=str(proj))

    assert result.returncode == 2, result.stderr
    assert "override" in result.stderr.lower(), result.stderr
