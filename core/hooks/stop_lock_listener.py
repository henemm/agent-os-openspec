#!/usr/bin/env python3
"""
OpenSpec Framework - Stop Lock Listener (UserPromptSubmit)

Listens for stop/resume keywords in user messages.

"stop"/"stopp"/"halt" -> creates .claude/stop.lock
"resume"/"weiter"/"continue" -> removes .claude/stop.lock

Configuration (in openspec.yaml):
  stop_lock:
    enabled: true
    stop_keywords:
      - "stop"
      - "stopp"
      - "halt"
    resume_keywords:
      - "resume"
      - "weiter"
      - "continue"
      - "weitermachen"

Exit Codes:
- 0: Always (listener never blocks)
"""

import json
import os
import re
import sys
import time
from pathlib import Path

# Import config loader
try:
    from config_loader import load_config, find_project_root
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from config_loader import load_config, find_project_root
    except ImportError:
        def load_config():
            return {}
        def find_project_root():
            cwd = Path.cwd()
            for parent in [cwd] + list(cwd.parents):
                if (parent / ".git").exists():
                    return parent
            return cwd


DEFAULT_STOP_KEYWORDS = ["stop", "stopp", "halt"]
DEFAULT_RESUME_KEYWORDS = ["resume", "weiter", "continue", "weitermachen"]


def get_lock_file() -> Path:
    """Get path to stop lock file."""
    return find_project_root() / ".claude" / "stop.lock"


def get_config() -> dict:
    """Get stop lock configuration."""
    config = load_config()
    sl = config.get("stop_lock", {})
    return {
        "enabled": sl.get("enabled", True),
        "stop_keywords": sl.get("stop_keywords", DEFAULT_STOP_KEYWORDS),
        "resume_keywords": sl.get("resume_keywords", DEFAULT_RESUME_KEYWORDS),
    }


def get_user_message() -> str:
    """Extract user message from hook input."""
    # UserPromptSubmit receives the user's message
    input_str = os.environ.get("CLAUDE_USER_PROMPT", "")
    if input_str:
        return input_str.strip().lower()

    try:
        data = json.load(sys.stdin)
        return data.get("user_prompt", data.get("content", "")).strip().lower()
    except (json.JSONDecodeError, EOFError, Exception):
        return ""


def is_stop_message(message: str, keywords: list) -> bool:
    """Check if message is a stop command."""
    # Must be a short message (just the keyword, not a sentence containing it)
    words = message.split()
    if len(words) > 3:
        return False

    for kw in keywords:
        if re.search(rf"\b{re.escape(kw)}\b", message, re.IGNORECASE):
            return True
    return False


def is_resume_message(message: str, keywords: list) -> bool:
    """Check if message is a resume command."""
    words = message.split()
    if len(words) > 3:
        return False

    for kw in keywords:
        if re.search(rf"\b{re.escape(kw)}\b", message, re.IGNORECASE):
            return True
    return False


def main():
    config = get_config()

    if not config["enabled"]:
        sys.exit(0)

    message = get_user_message()
    if not message:
        sys.exit(0)

    lock_file = get_lock_file()

    if is_stop_message(message, config["stop_keywords"]):
        # Create lock file
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_data = {
            "reason": "User requested stop",
            "timestamp": time.time(),
            "message": message,
        }
        lock_file.write_text(json.dumps(lock_data, indent=2))
        print(
            "STOP LOCK activated. All Edit/Write/Bash operations are paused.\n"
            "Say 'resume', 'weiter', or 'continue' to unlock.",
            file=sys.stderr,
        )

    elif is_resume_message(message, config["resume_keywords"]):
        if lock_file.exists():
            lock_file.unlink()
            print("STOP LOCK released. Operations resumed.", file=sys.stderr)
        else:
            print("No active stop lock.", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
