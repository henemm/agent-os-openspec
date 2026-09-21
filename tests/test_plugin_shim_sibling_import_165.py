"""Tests fuer #165 — der Plugin-Shim muss Geschwister-Importe ueberstehen.

Gemessen in gregor-zwanzig: Nach `migrate_to_plugin.py --apply` brachen drei
projekteigene Hooks mit `ModuleNotFoundError: No module named 'hook_utils'`.
Vor der Migration liefen sie (Exit 0).

Ursache: Der Shim ersetzt die lokale `config_loader.py` und laedt die Fassung
des Plugins per `spec_from_file_location`. Die des Plugins beginnt mit
`from hook_utils import find_main_repo_from_worktree` — ein Geschwister-Modul im
selben Ordner. Bei diesem Ladeweg steht dieser Ordner nicht im Suchpfad, also
scheitert der Import und der Hook stirbt beim Start.

Der Test baut eine vollstaendige Fake-Plugin-Installation (Registry + Modul mit
Geschwister-Import) und faehrt den gerenderten Shim in einem Subprozess mit
eigenem HOME — hermetisch, ohne echte Plugin-Installation.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from migrate_to_plugin import (  # noqa: E402
    SHIM_MARKER,
    _find_shim_candidates,
    _render_shim,
)


def _fake_plugin(tmp_path: Path) -> Path:
    """Fake-Plugin mit Modul 'config_loader', das ein Geschwister-Modul importiert."""
    home = tmp_path / "home"
    install = tmp_path / "plugin"
    hooks = install / "core" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hook_utils.py").write_text("SIBLING_MARKER = 'aus dem Geschwister-Modul'\n")
    (hooks / "config_loader.py").write_text(
        "from hook_utils import SIBLING_MARKER\n"
        "def load_config():\n"
        "    return SIBLING_MARKER\n"
    )

    registry_dir = home / ".claude" / "plugins"
    registry_dir.mkdir(parents=True)
    (registry_dir / "installed_plugins.json").write_text(json.dumps({
        "plugins": {
            "agent-os-openspec@henemm-private": [
                {"scope": "user", "installPath": str(install)}
            ]
        }
    }))
    return home


def _run_shim(tmp_path: Path, home: Path, snippet: str) -> subprocess.CompletedProcess:
    project_hooks = tmp_path / "project" / ".claude" / "hooks"
    project_hooks.mkdir(parents=True)
    (project_hooks / "config_loader.py").write_text(_render_shim("config_loader"))
    (project_hooks / "consumer.py").write_text(snippet)
    return subprocess.run(
        [sys.executable, str(project_hooks / "consumer.py")],
        capture_output=True, text=True, env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
    )


def test_shim_survives_sibling_import(tmp_path):
    """`from config_loader import X` bricht nicht, wenn das Plugin-Modul ein
    Geschwister-Modul importiert."""
    home = _fake_plugin(tmp_path)

    result = _run_shim(tmp_path, home, (
        "from config_loader import load_config\n"
        "print(load_config())\n"
    ))

    assert "ModuleNotFoundError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert "aus dem Geschwister-Modul" in result.stdout


def test_shim_works_for_plain_module_import(tmp_path):
    """Auch der Stil `import config_loader` bleibt funktionsfaehig."""
    home = _fake_plugin(tmp_path)

    result = _run_shim(tmp_path, home, (
        "import config_loader\n"
        "print(config_loader.load_config())\n"
    ))

    assert result.returncode == 0, result.stderr
    assert "aus dem Geschwister-Modul" in result.stdout


def test_stale_shim_is_replaced(tmp_path):
    """Ein Shim aelterer Fassung wird erneuert — Marker allein genuegt nicht.

    Sonst bliebe die fehlerhafte Fassung in jedem bereits migrierten Projekt
    liegen: Der Marker ist in alt und neu derselbe.
    """
    hooks = tmp_path / "project" / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    stale = hooks / "config_loader.py"
    stale.write_text(SHIM_MARKER + "\n# alte Fassung ohne sys.path-Eintrag\n")

    to_replace, already = _find_shim_candidates(tmp_path / "project")

    assert stale in to_replace
    assert already == []


def test_current_shim_is_left_alone(tmp_path):
    """Ein Shim der heutigen Fassung wird nicht angefasst (Idempotenz)."""
    hooks = tmp_path / "project" / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    current = hooks / "config_loader.py"
    current.write_text(_render_shim("config_loader"))

    to_replace, already = _find_shim_candidates(tmp_path / "project")

    assert to_replace == []
    assert current in already


def test_shim_without_installed_plugin_raises_import_error(tmp_path):
    """Ohne Plugin-Installation meldet der Shim klar, was fehlt."""
    home = tmp_path / "home"
    (home / ".claude" / "plugins").mkdir(parents=True)

    result = _run_shim(tmp_path, home, "import config_loader\n")

    assert result.returncode != 0
    assert "plugin not installed" in result.stderr
