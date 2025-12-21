#!/usr/bin/env python3
"""
OpenSpec Framework - Workflow State Updater Hook

Listens for user approval phrases in UserPromptSubmit events.
When detected, updates workflow_state.json to mark spec as approved.

This enables the transition: spec_written -> spec_approved

Exit Codes:
- 0: Always (this hook never blocks, only updates state)
"""

import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime

try:
    from config_loader import (
        load_config, get_state_file_path, get_approval_phrases
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from config_loader import (
        load_config, get_state_file_path, get_approval_phrases
    )


def load_state() -> dict:
    """Load current workflow state."""
    state_file = get_state_file_path()

    if not state_file.exists():
        return {
            "current_phase": "idle",
            "feature_name": None,
            "spec_file": None,
            "spec_approved": False,
            "tasks_created": False,
            "implementation_done": False,
            "validation_done": False,
            "phases_completed": [],
            "last_updated": datetime.now().isoformat(),
        }

    with open(state_file, 'r') as f:
        return json.load(f)


def save_state(state: dict):
    """Save workflow state."""
    state_file = get_state_file_path()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.now().isoformat()

    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)


def is_approval_message(message: str) -> bool:
    """Check if message contains an approval phrase."""
    message_lower = message.lower().strip()
    approval_phrases = get_approval_phrases()

    for phrase in approval_phrases:
        # Check if phrase is in message (word boundary aware)
        pattern = r'\b' + re.escape(phrase.lower()) + r'\b'
        if re.search(pattern, message_lower):
            return True

    return False


def main():
    # Get user input from environment or stdin
    try:
        data = json.load(sys.stdin)
        user_message = data.get("user_prompt", data.get("prompt", ""))
    except (json.JSONDecodeError, Exception):
        user_message = os.environ.get("CLAUDE_USER_PROMPT", "")

    if not user_message:
        sys.exit(0)

    # Check if this is an approval message
    if not is_approval_message(user_message):
        sys.exit(0)

    # Load current state
    state = load_state()

    # Only process if we're in spec_written phase
    if state.get("current_phase") != "spec_written":
        sys.exit(0)

    # Update state to approved
    state["spec_approved"] = True
    state["current_phase"] = "spec_approved"

    if "phases_completed" not in state:
        state["phases_completed"] = []
    if "spec_approved" not in state["phases_completed"]:
        state["phases_completed"].append("spec_approved")

    save_state(state)

    # Output confirmation (shown as hook output)
    print(f"Spec approved! You may now run /implement")

    sys.exit(0)


if __name__ == "__main__":
    main()
