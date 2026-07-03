"""Tests für SHIM_HOOKS-Ersetzung in migrate_to_plugin.py (Issue #33, Stufe 2).

Deckt ab:
- --apply entfernt alle CORE_HOOKS-Kopien und ersetzt die SHIM_HOOKS durch Shims,
  lässt projekteigene Hooks liegen.
- Der projekteigene Hook läuft NACH der Migration via Shim (Subprozess, Fake-HOME).
- Idempotenz: zweiter --apply-Lauf lässt Shims unverändert.
- Plugin nicht installiert: Shim wirft ImportError mit klarer Meldung.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import migrate_to_plugin as mig


def _make_project(tmp_path):
    """tmp-Projekt mit Framework-Kopien + projekteigenem Hook, der hook_utils importiert."""
    proj = tmp_path / "proj"
    hooks = proj / ".claude" / "hooks"
    hooks.mkdir(parents=True)

    # migrate() benötigt eine settings.json
    (proj / ".claude" / "settings.json").write_text(json.dumps({"hooks": {}}))

    # Stale local copies of core hooks (should be deleted)
    for name in mig.CORE_HOOKS:
        (hooks / name).write_text("# stale local framework copy\n")

    # Stale local copies of shim-target utilities (should be replaced by shim)
    for name in mig.SHIM_HOOKS:
        (hooks / name).write_text(f"# stale local copy of {name}\nLOCAL = True\n")

    # Project-own hook importing hook_utils — must survive and keep working
    (hooks / "myhook.py").write_text(
        "import hook_utils\n"
        "print('PLUGIN_VALUE=' + hook_utils.PLUGIN_MARKER)\n"
    )
    return proj, hooks


def _make_fake_home(tmp_path, with_plugin=True):
    """Fake-HOME mit installed_plugins.json; optional ein Fake-Plugin mit echtem hook_utils."""
    home = tmp_path / "home"
    plugins_dir = home / ".claude" / "plugins"
    plugins_dir.mkdir(parents=True)

    if with_plugin:
        plugin_root = tmp_path / "plugin_install"
        core_hooks = plugin_root / "core" / "hooks"
        core_hooks.mkdir(parents=True)
        (core_hooks / "hook_utils.py").write_text(
            "PLUGIN_MARKER = 'from-installed-plugin'\n"
            "def setup_path():\n    return 'ok'\n"
        )
        (core_hooks / "config_loader.py").write_text(
            "def load_config():\n    return {'source': 'plugin'}\n"
        )
        registry = {
            "plugins": {
                "agent-os-openspec@3.8.0": [
                    {"scope": "user", "installPath": str(plugin_root)},
                ]
            }
        }
    else:
        registry = {"plugins": {}}

    (plugins_dir / "installed_plugins.json").write_text(json.dumps(registry))
    return home


def _run_hook(hooks_dir, home):
    env = dict(os.environ, HOME=str(home))
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    return subprocess.run(
        [sys.executable, "myhook.py"],
        cwd=str(hooks_dir),
        env=env,
        capture_output=True,
        text=True,
    )


def test_apply_removes_core_and_writes_shims(tmp_path):
    proj, hooks = _make_project(tmp_path)

    mig.migrate(proj, dry_run=False)

    # All core hook copies removed
    for name in mig.CORE_HOOKS:
        assert not (hooks / name).exists(), f"{name} should have been removed"

    # Shim hooks replaced by a shim carrying the marker on line 1
    for name in mig.SHIM_HOOKS:
        f = hooks / name
        assert f.exists(), f"{name} must remain (as shim)"
        assert f.read_text().splitlines()[0] == mig.SHIM_MARKER

    # Project-own hook untouched
    myhook = hooks / "myhook.py"
    assert myhook.exists()
    assert "import hook_utils" in myhook.read_text()


def test_dry_run_lists_candidates_without_changing(tmp_path):
    proj, hooks = _make_project(tmp_path)
    before = {f.name: f.read_text() for f in hooks.glob("*.py")}

    to_replace, already = mig._find_shim_candidates(proj)
    assert {f.name for f in to_replace} == set(mig.SHIM_HOOKS)
    assert already == []

    mig.migrate(proj, dry_run=True)

    # Nothing changed on disk
    after = {f.name: f.read_text() for f in hooks.glob("*.py")}
    assert before == after


def test_project_hook_runs_via_shim(tmp_path):
    proj, hooks = _make_project(tmp_path)
    home = _make_fake_home(tmp_path, with_plugin=True)

    mig.migrate(proj, dry_run=False)

    result = _run_hook(hooks, home)
    assert result.returncode == 0, result.stderr
    assert "PLUGIN_VALUE=from-installed-plugin" in result.stdout


def test_second_apply_is_idempotent(tmp_path):
    proj, hooks = _make_project(tmp_path)

    mig.migrate(proj, dry_run=False)
    shim_before = {n: (hooks / n).read_text() for n in mig.SHIM_HOOKS}

    to_replace, already = mig._find_shim_candidates(proj)
    assert to_replace == []
    assert {f.name for f in already} == set(mig.SHIM_HOOKS)

    # Second run must not error and must leave shims unchanged
    mig.migrate(proj, dry_run=False)
    for name, content in shim_before.items():
        assert (hooks / name).read_text() == content


def test_shim_raises_when_plugin_missing(tmp_path):
    proj, hooks = _make_project(tmp_path)
    home = _make_fake_home(tmp_path, with_plugin=False)

    mig.migrate(proj, dry_run=False)

    result = _run_hook(hooks, home)
    assert result.returncode != 0
    assert "agent-os-openspec plugin not installed" in result.stderr
