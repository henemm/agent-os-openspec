#!/usr/bin/env python3
"""
Edit Verify — PostToolUse Edit|Write|MultiEdit

Prüft nach jedem Edit/Write, dass der neue Inhalt tatsächlich auf Disk
gelandet ist. Gibt bei stiller Fehlfunktion eine Warnung aus.

Fail-open: Jede Exception → exit(0). Blockiert nie.
"""

import json
import sys


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    try:
        tool_input = payload.get("tool_input", {})
        if not isinstance(tool_input, dict):
            sys.exit(0)

        file_path = tool_input.get("file_path")
        if not file_path:
            sys.exit(0)

        tool_name = payload.get("tool_name", "")
        if tool_name == "Write":
            search_string = tool_input.get("content")
        else:
            search_string = tool_input.get("new_string")

        if not search_string:
            sys.exit(0)

        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                file_content = fh.read()
        except (OSError, UnicodeDecodeError):
            sys.exit(0)  # Binärdateien oder fehlende Rechte → kein Problem

        if search_string[:200] not in file_content:
            print(
                f"WARNUNG [edit_verify]: Inhalt nach Edit NICHT in {file_path} gefunden.\n"
                f"  Erwartet: {repr(search_string[:80])}",
                file=sys.stderr,
            )

    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
