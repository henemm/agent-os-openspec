#!/usr/bin/env python3
"""
OpenSpec Framework - Configuration Loader

Shared module for loading and accessing framework configuration.
All hooks import this to get consistent config access.

Supports:
- openspec.yaml / config.yaml - Main configuration
- settings.local.json - Local overrides (NOT in git, for credentials etc.)
"""

import os
import json
import yaml
from pathlib import Path
from functools import lru_cache

# Config file search order
CONFIG_NAMES = ["openspec.yaml", "config.yaml", ".openspec.yaml"]

# Local override file (should be in .gitignore)
LOCAL_OVERRIDE_NAMES = ["settings.local.json", ".settings.local.json"]


@lru_cache(maxsize=1)
def find_project_root() -> Path:
    """Find project root by looking for config file or .git directory."""
    current = Path.cwd()

    while current != current.parent:
        # Check for config files
        for config_name in CONFIG_NAMES:
            if (current / config_name).exists():
                return current
            if (current / ".claude" / config_name).exists():
                return current

        # Check for .git as fallback
        if (current / ".git").exists():
            return current

        current = current.parent

    return Path.cwd()


@lru_cache(maxsize=1)
def load_config() -> dict:
    """
    Load configuration from project root.

    Load order (later overrides earlier):
    1. Default config (built-in)
    2. openspec.yaml / config.yaml (project config)
    3. settings.local.json (local overrides, NOT in git)
    """
    root = find_project_root()

    # Search for main config file
    config_path = None
    for config_name in CONFIG_NAMES:
        candidate = root / config_name
        if candidate.exists():
            config_path = candidate
            break
        candidate = root / ".claude" / config_name
        if candidate.exists():
            config_path = candidate
            break

    # Start with defaults
    config = get_default_config()

    # Merge main config if found
    if config_path:
        with open(config_path, 'r') as f:
            file_config = yaml.safe_load(f) or {}
        config = deep_merge(config, file_config)

    # Load local overrides (settings.local.json)
    local_config = load_local_overrides(root)
    if local_config:
        config = deep_merge(config, local_config)

    return config


def load_local_overrides(root: Path) -> dict | None:
    """
    Load local override settings.

    These are for:
    - API keys and credentials
    - Local paths
    - Developer-specific preferences

    Should be in .gitignore!
    """
    for override_name in LOCAL_OVERRIDE_NAMES:
        # Check in .claude/
        candidate = root / ".claude" / override_name
        if candidate.exists():
            try:
                with open(candidate, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception):
                pass

        # Check in root
        candidate = root / override_name
        if candidate.exists():
            try:
                with open(candidate, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception):
                pass

    return None


def get_default_config() -> dict:
    """Return default configuration."""
    return {
        "project": {
            "name": "Unnamed Project",
            "base_path": str(find_project_root()),
        },
        "workflow": {
            "phases": [
                "idle",
                "analyse_done",
                "spec_written",
                "spec_approved",
                "implemented",
                "validated"
            ],
            "approval_phrases": [
                "approved", "freigabe", "spec ok", "lgtm", "looks good"
            ],
        },
        "protected_paths": [],
        "always_allowed": [
            r"\.claude/",
            r"docs/",
            r"\.md$",
            r"\.gitignore",
        ],
        "specs": {
            "base_path": "docs/specs",
            "template_file": "docs/specs/_template.md",
            "categories": {},
        },
        "claude_md": {
            "max_lines": 600,
            "forbidden_patterns": [],
        },
        "modules": {
            "core": {
                "workflow_gate": True,
                "spec_enforcement": True,
                "claude_md_protection": True,
                "notification": True,
            },
            "generic": {
                "bug_fix_blocker": False,
                "test_before_commit": False,
                "scope_drift_guard": False,
            },
        },
        "hooks": {
            "timeout": 5,
        },
    }


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_project_root() -> Path:
    """Get the project root path."""
    config = load_config()
    return Path(config["project"].get("base_path", find_project_root()))


def get_workflow_phases() -> list:
    """Get configured workflow phases."""
    return load_config()["workflow"]["phases"]


def get_approval_phrases() -> list:
    """Get phrases that trigger spec approval."""
    return load_config()["workflow"]["approval_phrases"]


def get_protected_paths() -> list:
    """Get protected path patterns."""
    return load_config().get("protected_paths", [])


def get_always_allowed() -> list:
    """Get always-allowed path patterns."""
    return load_config().get("always_allowed", [])


def get_specs_config() -> dict:
    """Get specs configuration."""
    return load_config().get("specs", {})


def is_module_enabled(category: str, module: str) -> bool:
    """Check if a module is enabled."""
    modules = load_config().get("modules", {})
    return modules.get(category, {}).get(module, False)


def get_state_file_path() -> Path:
    """Get path to workflow state file."""
    return get_project_root() / ".claude" / "workflow_state.json"


if __name__ == "__main__":
    # Test: Print loaded config
    import json
    config = load_config()
    print(json.dumps(config, indent=2, default=str))
