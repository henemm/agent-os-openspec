#!/usr/bin/env python3
"""
OpenSpec Framework - Override Token Listener (UserPromptSubmit)

When user says "override", creates a one-time token that gates accept as exception.
The token is consumed (deleted) after a single gate pass in pre_commit_gate.

Token File: .claude/override_token.json

Configuration (in openspec.yaml):
  override_token:
    enabled: true
    keywords:
      - "override"
      - "ueberschreiben"

Exit Codes:
- 0: Always (listener never blocks)
"""

import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

# Import config loader
try:
    from config_loader import load_config
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from config_loader import load_config
    except ImportError:
        def load_config():
            return {}


DEFAULT_KEYWORDS = ["override", "ueberschreiben"]


def find_project_root() -> Path:
    """Find project root."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists():
            return parent
    return cwd


def get_token_file() -> Path:
    """Get path to override token file."""
    return find_project_root() / ".claude" / "override_token.json"


def get_config() -> dict:
    """Get override token configuration."""
    config = load_config()
    ot = config.get("override_token", {})
    return {
        "enabled": ot.get("enabled", True),
        "keywords": ot.get("keywords", DEFAULT_KEYWORDS),
    }


def get_user_message() -> str:
    """Extract user message from hook input."""
    input_str = os.environ.get("CLAUDE_USER_PROMPT", "")
    if input_str:
        return input_str.strip().lower()

    try:
        data = json.load(sys.stdin)
        return data.get("user_prompt", data.get("content", "")).strip().lower()
    except (json.JSONDecodeError, EOFError, Exception):
        return ""


def main():
    config = get_config()

    if not config["enabled"]:
        sys.exit(0)

    message = get_user_message()
    if not message:
        sys.exit(0)

    # Check if message contains override keyword (short messages only)
    words = message.split()
    if len(words) > 5:
        sys.exit(0)

    is_override = False
    for kw in config["keywords"]:
        if re.search(rf"\b{re.escape(kw)}\b", message, re.IGNORECASE):
            is_override = True
            break

    if not is_override:
        sys.exit(0)

    # Create one-time override token
    token_file = get_token_file()
    token_file.parent.mkdir(parents=True, exist_ok=True)

    token_data = {
        "token": secrets.token_hex(16),
        "created": time.time(),
        "reason": f"User override: {message}",
        "consumed": False,
    }
    token_file.write_text(json.dumps(token_data, indent=2))

    print(
        "Override token created. The next blocked gate will be bypassed once.\n"
        "Token is single-use and will be consumed automatically.",
        file=sys.stderr,
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
