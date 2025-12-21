#!/usr/bin/env python3
"""
Home Assistant Module - Lovelace Screenshot Gate

Enforces screenshot-based QA for dashboard changes:
1. BEFORE change: Requires "before" screenshot exists
2. AFTER change: Creates lock for comparison

Exit Codes:
- 0: Allowed
- 2: Blocked (no before screenshot)
"""

import json
import sys
import os
import glob
from pathlib import Path
from datetime import datetime

# Try to import config loader
try:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "core" / "hooks"))
    from config_loader import get_project_root, load_config
except ImportError:
    def get_project_root():
        return Path.cwd()
    def load_config():
        return {}


def get_ha_config() -> dict:
    """Get Home Assistant module config."""
    config = load_config()
    return config.get("modules", {}).get("home_assistant", {})


def get_screenshot_dir() -> str:
    """Get directory for screenshots."""
    ha_config = get_ha_config()
    return ha_config.get("lovelace", {}).get("before_dir", "/tmp")


def get_max_age_minutes() -> int:
    """Get max age for screenshots in minutes."""
    ha_config = get_ha_config()
    return ha_config.get("lovelace", {}).get("max_screenshot_age_minutes", 30)


def get_lock_file() -> Path:
    """Get path to screenshot lock file."""
    return get_project_root() / ".claude" / "lovelace_screenshot.json"


def get_recent_before_screenshot() -> str | None:
    """Find a recent before screenshot."""
    screenshot_dir = get_screenshot_dir()
    max_age = get_max_age_minutes()

    pattern = f"{screenshot_dir}/lovelace_before_*.png"
    files = glob.glob(pattern)

    if not files:
        return None

    # Find newest file
    newest = max(files, key=os.path.getmtime)
    age = datetime.now().timestamp() - os.path.getmtime(newest)

    if age > max_age * 60:
        return None  # Too old

    return newest


def is_lovelace_file(file_path: str) -> bool:
    """Check if this is a Lovelace file."""
    return 'lovelace/' in file_path and file_path.endswith('.yaml')


def load_lock() -> dict | None:
    """Load lock file."""
    lock_file = get_lock_file()
    if not lock_file.exists():
        return None
    try:
        return json.loads(lock_file.read_text())
    except Exception:
        return None


def save_lock(lock_data: dict):
    """Save lock file."""
    lock_file = get_lock_file()
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(json.dumps(lock_data, indent=2))


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')

    # Only check Lovelace files
    if not is_lovelace_file(file_path):
        sys.exit(0)

    # Check if before screenshot exists
    before_screenshot = get_recent_before_screenshot()

    if before_screenshot is None:
        # Derive dashboard path from file
        parts = file_path.split('lovelace/')
        if len(parts) > 1:
            dashboard = parts[1].split('/')[0].replace('_tabs', '')
        else:
            dashboard = 'default'

        ha_config = get_ha_config()
        screenshot_tool = ha_config.get("lovelace", {}).get("screenshot_tool", "tools/lovelace_screenshot.py")

        print(f"""
+======================================================================+
|  BEFORE SCREENSHOT REQUIRED!                                         |
+======================================================================+
|  You want to modify a Lovelace file:
|  {file_path[-50:]}
|
|  BEFORE making changes - create screenshot:
|
|  python3 {screenshot_tool} \\
|    /lovelace/{dashboard} /tmp/lovelace_before_$(date +%H%M).png
|
|  AFTER the change: Make NEW screenshot and COMPARE!
+======================================================================+
""", file=sys.stderr)
        sys.exit(2)

    # Before screenshot exists - update lock and allow
    lock = load_lock() or {}
    lock['before_screenshot'] = before_screenshot
    lock['lovelace_file'] = file_path
    lock['timestamp'] = datetime.now().isoformat()
    lock['screenshot_compared'] = False
    save_lock(lock)

    sys.exit(0)


if __name__ == '__main__':
    main()
