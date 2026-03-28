#!/usr/bin/env python3
"""
OpenSpec Framework - Workflow Cleanup (UserPromptSubmit)

Auto-cleans workflow_state_multi.json:
- Removes phase8_complete workflows
- Removes stale workflows (inactive for configurable days)
- Rate-limited: max once per hour

Configuration (in openspec.yaml):
  workflow_cleanup:
    enabled: true
    stale_days: 7
    interval_hours: 1

Exit Codes:
- 0: Always (never blocks)
"""

import json
import os
import sys
import time
from pathlib import Path

# Import helpers
try:
    from config_loader import load_config
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from config_loader import load_config
    except ImportError:
        def load_config():
            return {}

try:
    from workflow_state_multi import load_state, save_state
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from workflow_state_multi import load_state, save_state
    except ImportError:
        def load_state():
            return {"version": "2.0", "workflows": {}, "active_workflow": None}
        def save_state(s):
            pass


def find_project_root() -> Path:
    """Find project root."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists():
            return parent
    return cwd


def get_cleanup_config() -> dict:
    """Get cleanup configuration."""
    config = load_config()
    wc = config.get("workflow_cleanup", {})
    return {
        "enabled": wc.get("enabled", True),
        "stale_days": wc.get("stale_days", 7),
        "interval_hours": wc.get("interval_hours", 1),
    }


def get_last_cleanup_file() -> Path:
    """Get path to last cleanup timestamp file."""
    return find_project_root() / ".claude" / "last_cleanup.json"


def should_run_cleanup(interval_hours: int) -> bool:
    """Check if enough time has passed since last cleanup."""
    ts_file = get_last_cleanup_file()
    if not ts_file.exists():
        return True

    try:
        data = json.loads(ts_file.read_text())
        last_run = data.get("timestamp", 0)
        hours_since = (time.time() - last_run) / 3600
        return hours_since >= interval_hours
    except (json.JSONDecodeError, Exception):
        return True


def record_cleanup():
    """Record cleanup timestamp."""
    ts_file = get_last_cleanup_file()
    ts_file.parent.mkdir(parents=True, exist_ok=True)
    ts_file.write_text(json.dumps({"timestamp": time.time()}))


def main():
    config = get_cleanup_config()

    if not config["enabled"]:
        sys.exit(0)

    if not should_run_cleanup(config["interval_hours"]):
        sys.exit(0)

    state = load_state()
    workflows = state.get("workflows", {})

    if not workflows:
        sys.exit(0)

    removed = []
    stale_threshold = time.time() - (config["stale_days"] * 86400)

    for name in list(workflows.keys()):
        wf = workflows[name]

        # Remove completed workflows
        if wf.get("current_phase") == "phase8_complete":
            removed.append(f"{name} (completed)")
            del workflows[name]
            continue

        # Remove stale workflows
        last_updated = wf.get("last_updated", "")
        if last_updated:
            try:
                from datetime import datetime
                updated_time = datetime.fromisoformat(last_updated).timestamp()
                if updated_time < stale_threshold:
                    removed.append(f"{name} (stale, inactive {config['stale_days']}+ days)")
                    del workflows[name]
                    continue
            except (ValueError, TypeError):
                pass

    if removed:
        # Fix active_workflow if it was removed
        active = state.get("active_workflow")
        if active and active not in workflows:
            state["active_workflow"] = next(iter(workflows), None)

        state["workflows"] = workflows
        save_state(state)

        print(
            f"Workflow cleanup: Removed {len(removed)} workflow(s):\n"
            + "\n".join(f"  - {r}" for r in removed),
            file=sys.stderr,
        )

    record_cleanup()
    sys.exit(0)


if __name__ == "__main__":
    main()
