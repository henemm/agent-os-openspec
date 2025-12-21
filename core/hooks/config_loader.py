#!/usr/bin/env python3
"""
OpenSpec Framework - Configuration Loader

Shared module for loading and accessing framework configuration.
All hooks import this to get consistent config access.
"""

import os
import yaml
from pathlib import Path
from functools import lru_cache

# Config file search order
CONFIG_NAMES = ["openspec.yaml", "config.yaml", ".openspec.yaml"]


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
    """Load configuration from project root."""
    root = find_project_root()

    # Search for config file
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

    if not config_path:
        return get_default_config()

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f) or {}

    # Merge with defaults
    defaults = get_default_config()
    return deep_merge(defaults, config)


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
