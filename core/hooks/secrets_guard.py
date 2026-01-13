#!/usr/bin/env python3
"""
OpenSpec Framework - Secrets Guard Hook

Prevents accidental exposure of sensitive files.

Blocks commands/reads that would expose:
- .env files (unless staging mode)
- credentials.json, service accounts
- Private keys (.pem, .key, _key, _secret)

STAGING MODE:
Allows .env file access during development. Enable via:
1. Create .claude/staging file (touch .claude/staging)
2. Or set environment: OPENSPEC_ENV=staging

Staging mode NEVER allows: credentials.json, keys, secrets

Configuration (in config.yaml):
  secrets_guard:
    enabled: true
    staging_mode: false  # Or use marker file / env var
    sensitive_patterns:
      - "\\.env"
      - "credentials\\.json"
      - "service[_-]?account.*\\.json"
      - "_key"
      - "_secret"
      - "\\.pem$"
      - "\\.key$"
    always_blocked:  # Even in staging mode
      - "credentials\\.json"
      - "service[_-]?account.*\\.json"
      - "_key"
      - "_secret"
      - "\\.pem$"
      - "\\.key$"

Exit Codes:
- 0: Allowed
- 2: Blocked (sensitive file access)
"""

import json
import os
import re
import sys
from pathlib import Path

# Try to import config loader
try:
    from config_loader import load_config, get_project_root
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from config_loader import load_config, get_project_root
    except ImportError:
        def load_config():
            return {}
        def get_project_root():
            cwd = Path.cwd()
            for parent in [cwd] + list(cwd.parents):
                if (parent / ".git").exists():
                    return parent
            return cwd


# Default patterns
DEFAULT_SENSITIVE_PATTERNS = [
    r'\.env',
    r'credentials\.json',
    r'service[_-]?account.*\.json',
    r'_key',
    r'_secret',
    r'\.pem$',
    r'\.key$',
]

# Patterns that are ALWAYS blocked (even in staging)
DEFAULT_ALWAYS_BLOCKED = [
    r'credentials\.json',
    r'service[_-]?account.*\.json',
    r'_key',
    r'_secret',
    r'\.pem$',
    r'\.key$',
]

# Commands that output file contents
DANGEROUS_COMMANDS = [
    r'\bcat\b',
    r'\bhead\b',
    r'\btail\b',
    r'\bless\b',
    r'\bmore\b',
    r'\bsed\b.*-n.*p',
    r'\bawk\b.*print',
    r'\bgrep\b(?!.*-l)',  # grep without -l shows content
]


def get_secrets_config() -> dict:
    """Get secrets guard configuration with defaults."""
    config = load_config()
    secrets_config = config.get("secrets_guard", {})

    return {
        "enabled": secrets_config.get("enabled", True),
        "staging_mode": secrets_config.get("staging_mode", False),
        "sensitive_patterns": secrets_config.get("sensitive_patterns", DEFAULT_SENSITIVE_PATTERNS),
        "always_blocked": secrets_config.get("always_blocked", DEFAULT_ALWAYS_BLOCKED),
    }


def is_staging_mode() -> bool:
    """
    Check if we're in staging/development mode.

    Checks (in order):
    1. .claude/staging marker file exists
    2. OPENSPEC_ENV environment variable
    3. Config file setting
    """
    project_root = get_project_root()

    # Method 1: Check for .claude/staging marker file
    staging_file = project_root / ".claude" / "staging"
    if staging_file.exists():
        return True

    # Method 2: Check environment variable
    env = os.environ.get("OPENSPEC_ENV", "").lower()
    if env in ("staging", "development", "dev"):
        return True

    # Method 3: Check config
    config = get_secrets_config()
    return config.get("staging_mode", False)


def is_sensitive_file(path: str, patterns: list) -> bool:
    """Check if path matches any sensitive pattern."""
    for pattern in patterns:
        if re.search(pattern, path, re.IGNORECASE):
            return True
    return False


def is_always_blocked(path: str, patterns: list) -> bool:
    """Check if path matches always-blocked patterns (even in staging)."""
    for pattern in patterns:
        if re.search(pattern, path, re.IGNORECASE):
            return True
    return False


def outputs_content(command: str) -> bool:
    """Check if command would output file contents."""
    for pattern in DANGEROUS_COMMANDS:
        if re.search(pattern, command):
            return True
    return False


def get_tool_input() -> tuple[str, dict]:
    """Get tool name and input from stdin or environment."""
    tool_input_str = os.environ.get("CLAUDE_TOOL_INPUT", "")
    tool_name = os.environ.get("CLAUDE_TOOL_NAME", "")

    if tool_input_str:
        try:
            return tool_name, json.loads(tool_input_str)
        except json.JSONDecodeError:
            return tool_name, {}

    try:
        data = json.load(sys.stdin)
        return data.get("tool_name", ""), data.get("tool_input", {})
    except (json.JSONDecodeError, EOFError, Exception):
        return "", {}


def main():
    config = get_secrets_config()

    # Check if enabled
    if not config["enabled"]:
        sys.exit(0)

    tool_name, tool_input = get_tool_input()
    staging = is_staging_mode()

    sensitive_patterns = config["sensitive_patterns"]
    always_blocked = config["always_blocked"]

    # Check Bash commands
    if tool_name == "Bash":
        command = tool_input.get("command", "")

        if is_sensitive_file(command, sensitive_patterns) and outputs_content(command):
            # Check if always blocked (even in staging)
            if is_always_blocked(command, always_blocked):
                print("=" * 70, file=sys.stderr)
                print("BLOCKED - Secrets Guard", file=sys.stderr)
                print("=" * 70, file=sys.stderr)
                print(file=sys.stderr)
                print("Command would expose sensitive credentials/keys.", file=sys.stderr)
                print("These files are ALWAYS protected (even in staging).", file=sys.stderr)
                print(file=sys.stderr)
                print("Use 'grep -l' to find files or check existence", file=sys.stderr)
                print("without reading contents.", file=sys.stderr)
                print("=" * 70, file=sys.stderr)
                sys.exit(2)

            # In staging mode, allow .env files
            if staging:
                sys.exit(0)

            print("=" * 70, file=sys.stderr)
            print("BLOCKED - Secrets Guard", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            print(file=sys.stderr)
            print("Command would expose sensitive file contents.", file=sys.stderr)
            print(file=sys.stderr)
            print("Options:", file=sys.stderr)
            print("  1. Use 'grep -l' to find files without reading", file=sys.stderr)
            print("  2. Enable staging mode:", file=sys.stderr)
            print("     touch .claude/staging", file=sys.stderr)
            print("     # or: export OPENSPEC_ENV=staging", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            sys.exit(2)

    # Check Read tool
    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "")

        if is_sensitive_file(file_path, sensitive_patterns):
            # Check if always blocked
            if is_always_blocked(file_path, always_blocked):
                print("=" * 70, file=sys.stderr)
                print("BLOCKED - Secrets Guard", file=sys.stderr)
                print("=" * 70, file=sys.stderr)
                print(file=sys.stderr)
                print(f"Cannot read: {Path(file_path).name}", file=sys.stderr)
                print("This file contains credentials/keys that must stay protected.", file=sys.stderr)
                print("=" * 70, file=sys.stderr)
                sys.exit(2)

            # In staging mode, allow .env files
            if staging:
                sys.exit(0)

            print("=" * 70, file=sys.stderr)
            print("BLOCKED - Secrets Guard", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            print(file=sys.stderr)
            print(f"Cannot read sensitive file: {Path(file_path).name}", file=sys.stderr)
            print(file=sys.stderr)
            print("Enable staging mode to allow .env access:", file=sys.stderr)
            print("  touch .claude/staging", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
