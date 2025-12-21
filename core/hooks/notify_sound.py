#!/usr/bin/env python3
"""
OpenSpec Framework - Notification Hook

Outputs a notification marker when Claude finishes a response.
Can be used with terminal triggers (iTerm2, etc.) for audio/visual alerts.

Exit Codes:
- 0: Always
"""

import sys


def main():
    # Output notification marker
    # Configure your terminal to trigger on this string
    print("CLAUDE_NOTIFY")
    sys.exit(0)


if __name__ == "__main__":
    main()
