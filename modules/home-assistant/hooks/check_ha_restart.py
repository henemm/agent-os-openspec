#!/usr/bin/env python3
"""
Home Assistant Module - Config Validation Hook

Blocks `docker restart homeassistant` unless:
1. `docker exec homeassistant ... check_config` was run recently
2. The validation passed (lockfile exists and is fresh)

Mechanism:
- On check_config: Write lockfile with timestamp
- On restart: Check lockfile exists and < 10 min old

Exit Codes:
- 0: Allowed
- 2: Blocked (stderr shown to Claude)
"""

import json
import sys
import os
import time
import re
from pathlib import Path

# Try to import config loader
try:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "core" / "hooks"))
    from config_loader import get_project_root, load_config
except ImportError:
    def get_project_root():
        return Path.cwd()
    def load_config():
        return {}


def get_lockfile_path() -> Path:
    """Get path to validation lockfile."""
    return get_project_root() / ".config_validated"


def get_max_age() -> int:
    """Get max age for validation lock in seconds."""
    config = load_config()
    ha_config = config.get("modules", {}).get("home_assistant", {})
    return ha_config.get("validation", {}).get("config_lock_timeout", 600)


def get_container_name() -> str:
    """Get Home Assistant container name."""
    config = load_config()
    ha_config = config.get("modules", {}).get("home_assistant", {})
    return ha_config.get("container_name", "homeassistant")


def is_check_config_command(command: str) -> bool:
    """Check if command is a config validation."""
    container = get_container_name()
    patterns = [
        rf'docker exec.*{container}.*check_config',
        rf'docker exec.*{container}.*--script\s+check',
    ]
    for pattern in patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def is_restart_command(command: str) -> bool:
    """Check if command is an HA restart."""
    container = get_container_name()
    patterns = [
        rf'docker restart\s+{container}',
        rf'docker restart\s+.*{container}',
    ]
    for pattern in patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def set_validation_lock():
    """Set lockfile with current timestamp."""
    lockfile = get_lockfile_path()
    try:
        lockfile.write_text(str(time.time()))
    except Exception:
        pass


def check_validation_lock() -> tuple[bool, str]:
    """Check if lockfile exists and is current."""
    lockfile = get_lockfile_path()
    max_age = get_max_age()

    if not lockfile.exists():
        return False, "No config validation found!"

    try:
        timestamp = float(lockfile.read_text().strip())
        age = time.time() - timestamp

        if age > max_age:
            mins = int(age / 60)
            return False, f"Config validation is {mins} minutes old (max: {max_age // 60} min)!"

        return True, ""
    except Exception as e:
        return False, f"Error reading lockfile: {e}"


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = data.get('tool_input', {})
    command = tool_input.get('command', '')

    if not command:
        sys.exit(0)

    container = get_container_name()

    # Case 1: check_config -> set lockfile
    if is_check_config_command(command):
        set_validation_lock()
        sys.exit(0)

    # Case 2: restart -> check lockfile
    if is_restart_command(command):
        valid, message = check_validation_lock()
        if not valid:
            print("=" * 60, file=sys.stderr)
            print("RESTART BLOCKED - Config not validated!", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            print(message, file=sys.stderr)
            print("", file=sys.stderr)
            print("Required before restart:", file=sys.stderr)
            print(f"  docker exec {container} python -m homeassistant \\", file=sys.stderr)
            print("    --script check_config --config /config", file=sys.stderr)
            print("", file=sys.stderr)
            print("Only then is restart allowed.", file=sys.stderr)
            sys.exit(2)

        sys.exit(0)

    # Other commands pass through
    sys.exit(0)


if __name__ == '__main__':
    main()
