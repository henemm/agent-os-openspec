#!/usr/bin/env python3
"""
OpenSpec Framework - UI Screenshot Gate

Enforces before/after screenshots for UI-related file changes.

Use Case:
- Dashboard changes (Lovelace, React components, SwiftUI views)
- CSS/styling changes
- Layout modifications

This hook:
1. Detects UI file modifications
2. Requires a BEFORE screenshot exists before allowing edit
3. Stores lock for AFTER screenshot comparison

Screenshot Directory: docs/artifacts/{workflow}/screenshots/
Lock File: .claude/ui_screenshot_lock.json

Exit Codes:
- 0: Allowed (not UI file, or screenshot exists)
- 2: Blocked (UI file without before screenshot)

Configuration (in config.yaml):
  ui_screenshot:
    enabled: true
    paths:
      - "lovelace/"
      - "components/"
      - "views/"
    extensions:
      - ".yaml"
      - ".tsx"
      - ".vue"
      - ".swift"
    screenshot_max_age_minutes: 30
"""

import json
import sys
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

# Try to import config loader
try:
    from config_loader import get_project_root, load_config
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from config_loader import get_project_root, load_config
    except ImportError:
        def get_project_root():
            cwd = Path.cwd()
            for parent in [cwd] + list(cwd.parents):
                if (parent / ".git").exists():
                    return parent
            return cwd
        def load_config():
            return {}


def get_lock_file() -> Path:
    """Get path to screenshot lock file."""
    return get_project_root() / ".claude" / "ui_screenshot_lock.json"


# Default UI paths (override in config.yaml)
DEFAULT_UI_PATHS = [
    r"lovelace/",
    r"components/",
    r"views/",
    r"pages/",
    r"screens/",
    r"dashboard",
    r"ui/",
]

# Default UI extensions
DEFAULT_UI_EXTENSIONS = [
    r"\.yaml$",
    r"\.tsx$",
    r"\.jsx$",
    r"\.vue$",
    r"\.svelte$",
    r"\.swift$",
    r"\.css$",
    r"\.scss$",
]

# Screenshot file extensions
SCREENSHOT_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]


def get_ui_config() -> dict:
    """Get UI screenshot configuration."""
    config = load_config()
    return config.get("ui_screenshot", {})


def is_ui_file(file_path: str) -> bool:
    """Check if file is a UI-related file."""
    ui_config = get_ui_config()

    # Check if feature is enabled
    if not ui_config.get("enabled", True):
        return False

    ui_paths = ui_config.get("paths", DEFAULT_UI_PATHS)
    ui_extensions = ui_config.get("extensions", DEFAULT_UI_EXTENSIONS)

    # Check path patterns
    path_match = any(re.search(p, file_path, re.IGNORECASE) for p in ui_paths)
    ext_match = any(re.search(e, file_path, re.IGNORECASE) for e in ui_extensions)

    return path_match and ext_match


def find_recent_screenshot(workflow_name: str, file_path: str) -> Path | None:
    """Find a recent screenshot for the given file/workflow."""
    project_root = get_project_root()
    screenshot_dir = project_root / "docs" / "artifacts" / workflow_name / "screenshots"

    if not screenshot_dir.exists():
        return None

    ui_config = get_ui_config()
    max_age_minutes = ui_config.get("screenshot_max_age_minutes", 30)

    # Look for screenshots
    for ext in SCREENSHOT_EXTENSIONS:
        for screenshot in screenshot_dir.glob(f"*{ext}"):
            # Check age
            mtime = datetime.fromtimestamp(screenshot.stat().st_mtime)
            if datetime.now() - mtime < timedelta(minutes=max_age_minutes):
                return screenshot

    return None


def load_lock() -> dict | None:
    """Load screenshot lock if exists."""
    lock_file = get_lock_file()
    if not lock_file.exists():
        return None
    try:
        with open(lock_file, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def save_lock(lock_data: dict):
    """Save screenshot lock."""
    lock_file = get_lock_file()
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_file, 'w') as f:
        json.dump(lock_data, f, indent=2)


def get_active_workflow_name() -> str:
    """Get name of active workflow."""
    try:
        from workflow_state_multi import get_active_workflow
        workflow = get_active_workflow()
        if workflow:
            return workflow.get("name", "default")
    except ImportError:
        pass
    return "default"


def main():
    # Get tool input
    tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")

    if not tool_input:
        try:
            data = json.load(sys.stdin)
            tool_input = json.dumps(data.get("tool_input", {}))
        except (json.JSONDecodeError, Exception):
            sys.exit(0)

    try:
        data = json.loads(tool_input) if isinstance(tool_input, str) else tool_input
        file_path = data.get("file_path", "")
    except json.JSONDecodeError:
        file_path = ""

    if not file_path:
        sys.exit(0)

    # Check if UI file
    if not is_ui_file(file_path):
        sys.exit(0)

    # Get workflow name
    workflow_name = get_active_workflow_name()

    # Check for recent screenshot
    screenshot = find_recent_screenshot(workflow_name, file_path)

    if screenshot:
        # Screenshot exists - allow and update lock for AFTER comparison
        lock = {
            'file': file_path,
            'before_screenshot': str(screenshot),
            'timestamp': datetime.now().isoformat(),
            'workflow': workflow_name,
            'awaiting_after': True,
        }
        save_lock(lock)
        sys.exit(0)

    # No screenshot - BLOCK
    project_root = get_project_root()
    screenshot_dir = project_root / "docs" / "artifacts" / workflow_name / "screenshots"
    ui_config = get_ui_config()
    max_age = ui_config.get("screenshot_max_age_minutes", 30)

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  BLOCKED: UI Screenshot Required!                                ║
╠══════════════════════════════════════════════════════════════════╣
║  You're modifying a UI file without a BEFORE screenshot.         ║
║                                                                  ║
║  File: {file_path[:56]:<56}║
║  Workflow: {workflow_name:<52}║
║                                                                  ║
║  Before changing UI files:                                       ║
║  1. Take a screenshot of the CURRENT state                       ║
║  2. Save it to:                                                  ║
║     {str(screenshot_dir)[:56]:<56}║
║  3. Then retry this edit                                         ║
║                                                                  ║
║  Screenshot requirements:                                        ║
║  - Format: PNG, JPG, or GIF                                      ║
║  - Max age: {max_age} minutes                                         ║
║  - Shows the area being modified                                 ║
║                                                                  ║
║  After implementation, take an AFTER screenshot to compare!      ║
╚══════════════════════════════════════════════════════════════════╝
""", file=sys.stderr)
    sys.exit(2)


if __name__ == '__main__':
    main()
