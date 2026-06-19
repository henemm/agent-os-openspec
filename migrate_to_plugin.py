#!/usr/bin/env python3
"""
Migrate existing OpenSpec project to Plugin Mode (v3.2)

Scans .claude/settings.json and removes hook commands that reference
local .claude/hooks/*.py files which are now provided by the plugin.

The plugin's hooks/hooks.json already declares all core hooks globally
for every project with the plugin enabled. Project-level settings.json
must NOT use ${CLAUDE_PLUGIN_ROOT} — that variable is only valid inside
a plugin's own hooks/hooks.json.

Handles both legacy command formats:
  v2 wrapper: if [ -f "${CLAUDE_PROJECT_DIR}/.claude/hooks/foo.py" ]; then python3 ... ; fi
  v3 direct:  python3 /absolute/path/.claude/hooks/foo.py

Usage:
    python3 migrate_to_plugin.py /path/to/project          # Dry run
    python3 migrate_to_plugin.py /path/to/project --apply  # Apply changes
"""

import json
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent

# Core hooks — live in ${CLAUDE_PLUGIN_ROOT}/core/hooks/
CORE_HOOKS = {
    "edit_gate.py",
    "bash_gate.py",
    "post_bash.py",
    "phase_listener.py",
    "session_singleton_guard.py",
    "qa_gate.py",
    "override_token.py",
    "hook_utils.py",
    "config_loader.py",
    "workflow.py",
    "migrate_state.py",
    "adversary_dialog.py",
}

# Module hooks — live in ${CLAUDE_PLUGIN_ROOT}/modules/<module>/hooks/
MODULE_HOOKS: dict[str, str] = {
    "ui_test_preflight.py": "ios-swiftui",
    "on_ui_test_failure.py": "ios-swiftui",
    "ui_test_debugger_hint.py": "ios-swiftui",
    "test_lock_guard.py": "ios-swiftui",
    "check_ha_restart.py": "home-assistant",
    "lovelace_screenshot_gate.py": "home-assistant",
}

# .py filename regex — matches "foo_bar.py" or "foo-bar.py"
_PY_RE = re.compile(r'([\w][\w\-]*\.py)')


def _parse_hook_command(command: str) -> tuple[str | None, list[str]]:
    """
    Extract (py_filename, extra_args) from any hook command format.

    Works with both:
      python3 /abs/path/file.py arg1
      if [ -f "...file.py" ]; then python3 "...file.py" arg1; fi
    """
    py_files = _PY_RE.findall(command)
    if not py_files:
        return None, []

    filename = py_files[-1]

    # Text after the last .py occurrence → extra args
    last_pos = command.rfind(filename) + len(filename)
    tail = command[last_pos:]
    # Strip shell syntax: quotes, semicolons, "fi"
    tail = re.sub(r'["\';]|\bfi\b', ' ', tail).strip()
    args = tail.split() if tail else []

    return filename, args


_REMOVE = "__REMOVE__"


def _migrate_command(command: str) -> str | None:
    """
    Return _REMOVE if the command references a plugin-provided hook (should be deleted),
    or None if the command is unrelated to the plugin.

    ${CLAUDE_PLUGIN_ROOT} must NOT appear in project-level settings.json — the plugin's
    own hooks/hooks.json already registers all core hooks globally.
    """
    filename, _args = _parse_hook_command(command)
    if not filename:
        return None
    if filename in CORE_HOOKS or filename in MODULE_HOOKS:
        return _REMOVE
    return None


def _patch_settings(settings: dict, dry_run: bool) -> list[tuple[str, str, str]]:
    """
    Remove plugin hook commands from settings dict in-place.
    Returns list of (event_name, old_command, "<removed>").
    """
    changes = []
    for event_name, event_entries in settings.get("hooks", {}).items():
        for entry in event_entries:
            hooks_list = entry.get("hooks", [])
            to_remove = []
            for hook in hooks_list:
                old_cmd = hook.get("command", "")
                if _migrate_command(old_cmd) == _REMOVE:
                    changes.append((event_name, old_cmd, "<removed>"))
                    to_remove.append(hook)
            if to_remove and not dry_run:
                for h in to_remove:
                    hooks_list.remove(h)
    return changes


def _find_removable_hook_files(project_path: Path) -> list[Path]:
    """Return .claude/hooks/*.py files that are provided by the plugin."""
    hooks_dir = project_path / ".claude" / "hooks"
    if not hooks_dir.exists():
        return []
    removable = CORE_HOOKS | set(MODULE_HOOKS.keys())
    return [f for f in hooks_dir.glob("*.py") if f.name in removable]


def _read_installed_modules(project_path: Path) -> list[str]:
    version_file = project_path / ".claude" / "framework_version.json"
    if version_file.exists():
        try:
            data = json.loads(version_file.read_text())
            return data.get("installed_modules", [])
        except Exception:
            pass
    return []


def migrate(project_path: Path, dry_run: bool = True) -> None:
    print(f"OpenSpec Plugin Migration")
    print(f"=========================")
    print(f"Project : {project_path}")
    print(f"Mode    : {'Dry Run (pass --apply to apply)' if dry_run else 'APPLY'}")
    print()

    if not (project_path / ".claude").exists():
        print("ERROR: .claude/ directory not found. Is this an OpenSpec project?")
        sys.exit(1)

    settings_path = project_path / ".claude" / "settings.json"
    if not settings_path.exists():
        print("ERROR: .claude/settings.json not found.")
        sys.exit(1)

    settings = json.loads(settings_path.read_text())
    wrote_settings = False

    # --- 1. Patch hook commands ---
    print("Scanning hook commands in .claude/settings.json ...")
    changes = _patch_settings(settings, dry_run)
    if changes:
        print(f"Found {len(changes)} plugin hook(s) to remove from settings.json:")
        for event_name, old_cmd, _action in changes:
            short_old = old_cmd if len(old_cmd) <= 80 else old_cmd[:77] + "..."
            print(f"  [{event_name}] {short_old}")
            print(f"           → <removed> (already provided by plugin hooks/hooks.json)")
        wrote_settings = True
    else:
        print("  No plugin hook commands found in settings.json.")

    # --- 2. Add OPENSPEC_ENABLED_MODULES ---
    modules = _read_installed_modules(project_path)
    env_section = settings.get("env", {})
    if modules and "OPENSPEC_ENABLED_MODULES" not in env_section:
        value = ",".join(modules)
        print(f"\nWill add env.OPENSPEC_ENABLED_MODULES = '{value}'")
        if not dry_run:
            settings.setdefault("env", {})[" OPENSPEC_ENABLED_MODULES"] = value
            settings["env"] = {k.strip(): v for k, v in settings["env"].items()}
        wrote_settings = True
    elif "OPENSPEC_ENABLED_MODULES" in env_section:
        print(f"\nenv.OPENSPEC_ENABLED_MODULES already set: {env_section['OPENSPEC_ENABLED_MODULES']}")

    # --- 3. Write settings.json ---
    if not dry_run and wrote_settings:
        settings_path.write_text(json.dumps(settings, indent=2))
        print(f"\nWritten: .claude/settings.json")

    # --- 4. Mark framework_version.json as plugin_mode ---
    version_file = project_path / ".claude" / "framework_version.json"
    if version_file.exists():
        try:
            version_data = json.loads(version_file.read_text())
            if not version_data.get("plugin_mode"):
                print("\nWill mark framework_version.json as plugin_mode=true")
                if not dry_run:
                    version_data["plugin_mode"] = True
                    version_file.write_text(json.dumps(version_data, indent=2))
                    print("  Written: .claude/framework_version.json")
        except Exception:
            pass

    # --- 5. Remove plugin hook files ---
    removable = _find_removable_hook_files(project_path)
    if removable:
        print(f"\n{len(removable)} plugin hook file(s) in .claude/hooks/ can be removed:")
        for f in removable:
            print(f"  {f.relative_to(project_path)}")
        if not dry_run:
            for f in removable:
                f.unlink()
                print(f"  Removed: {f.relative_to(project_path)}")
        else:
            print("  (will be removed with --apply)")
    else:
        print("\nNo plugin hook files found in .claude/hooks/ to remove.")

    print()
    if dry_run:
        print("Dry run complete. Use --apply to apply changes.")
    else:
        print("Migration complete.")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    project_path = Path(sys.argv[1]).resolve()

    if not project_path.exists():
        print(f"ERROR: Path does not exist: {project_path}")
        sys.exit(1)

    apply = "--apply" in sys.argv
    migrate(project_path, dry_run=not apply)


if __name__ == "__main__":
    main()
