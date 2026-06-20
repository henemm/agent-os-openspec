#!/usr/bin/env python3
"""
CLAUDE.md Protection — PreToolUse Edit|Write

Schützt CLAUDE.md vor:
- Verbotenen Patterns (konfigurierbar via openspec.yaml)
- Aufblähen mit Inhalt der in /docs/ gehört

Warnt wenn CLAUDE.md die konfigurierte Zeilenzahl überschreitet.

Konfigurierbar via openspec.yaml:
  claude_md:
    max_lines: 600
    forbidden_patterns:
      - pattern: "## Solution Attempts"
        message: "Lösungsversuche gehören nach docs/project/solution_attempts.md"

Exit-Codes: 0 = erlaubt (mit möglicher Warnung), 2 = blockiert
"""

import json
import os
import re
import sys
from pathlib import Path


def _setup():
    hooks_dir = str(Path(__file__).parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


_setup()

from hook_utils import find_project_root  # noqa: E402

try:
    from config_loader import load_config
except ImportError:
    def load_config():
        return {}


def _check_length() -> None:
    cfg = load_config().get("claude_md", {})
    max_lines = cfg.get("max_lines", 600)
    claude_md = find_project_root() / "CLAUDE.md"
    if not claude_md.exists():
        return
    try:
        lines = claude_md.read_text().splitlines()
        if len(lines) > max_lines:
            print(
                f"WARNUNG [claude_md_protection]: CLAUDE.md hat {len(lines)} Zeilen "
                f"(Limit: {max_lines}).\n"
                f"  Detaillierter Inhalt gehört nach /docs/",
                file=sys.stderr,
            )
    except OSError:
        pass


def _check_patterns(content: str) -> "tuple[bool, str]":
    patterns = load_config().get("claude_md", {}).get("forbidden_patterns", [])
    for item in patterns:
        pattern = item.get("pattern", "")
        message = item.get("message", "Inhalt gehört nach /docs/")
        if pattern and re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
            return False, message
    return True, ""


def main() -> None:
    _check_length()

    try:
        ti_env = os.environ.get("CLAUDE_TOOL_INPUT", "")
        if ti_env:
            tool_input = json.loads(ti_env)
        else:
            data = json.load(sys.stdin)
            tool_input = data.get("tool_input", {})
    except Exception:
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if "CLAUDE.md" not in file_path:
        sys.exit(0)

    content = tool_input.get("content", "") or tool_input.get("new_string", "")
    if not content:
        sys.exit(0)

    ok, message = _check_patterns(content)
    if not ok:
        print(
            f"BLOCKED [claude_md_protection]: {message}\n"
            f"  Schreibe diesen Inhalt stattdessen in die passende /docs/-Datei.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
