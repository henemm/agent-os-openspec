#!/usr/bin/env python3
"""
OpenSpec Framework - Override Token Guard (PreToolUse Edit/Write)

Protects the override token file from direct manipulation by Claude.
Only the override_token_listener (UserPromptSubmit) may create/modify tokens.

Exit Codes:
- 0: Allowed
- 2: Blocked (attempt to manipulate token file)
"""

from hook_utils import setup_path, get_file_path, block, allow
setup_path()


def main():
    file_path = get_file_path()

    if "override_token" in file_path:
        block(
            "BLOCKED: Direct manipulation of override tokens is not allowed.\n"
            "Override tokens are created by the user saying 'override'."
        )

    allow()


if __name__ == "__main__":
    main()
