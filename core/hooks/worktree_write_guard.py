#!/usr/bin/env python3
"""
Worktree Write Guard — PreToolUse Edit|Write|MultiEdit

Verhindert Split-Brain: Blockiert Schreibzugriffe auf das Main-Repo wenn
Claude in einem Worktree-Kontext läuft. Schreibzugriffe IN den Worktree
selbst sind immer erlaubt.

Fail-safe: Jede unerwartete Exception → exit(0), nie blockieren.
"""

import json
import os
import re
import sys
from pathlib import Path

# Worktrees liegen nach Plugin-Konvention unter .claude/worktrees/<name>/
_WORKTREE_RE = re.compile(r"^(?P<main>.*)/\.claude/worktrees/(?P<name>[^/]+)")


def _read_payload() -> tuple[str, str]:
    """Gibt (cwd, file_path) zurück. Liest stdin ODER env vars."""
    # Wenn CLAUDE_TOOL_INPUT gesetzt ist, hat Claude Code das Tool-Input
    # schon extrahiert — stdin enthält in dem Fall noch das volle Payload.
    # Wir brauchen cwd aus dem äußeren Payload, deshalb stdin bevorzugen.
    raw_stdin = os.environ.get("CLAUDE_HOOK_STDIN", "")
    if raw_stdin:
        payload = json.loads(raw_stdin)
    else:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            payload = {}

    cwd = payload.get("cwd", os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))

    tool_input = payload.get("tool_input", {})
    # Fallback: CLAUDE_TOOL_INPUT enthält nur tool_input-Teil
    if not tool_input:
        ti_raw = os.environ.get("CLAUDE_TOOL_INPUT", "")
        if ti_raw:
            try:
                tool_input = json.loads(ti_raw)
            except Exception:
                pass

    file_path = tool_input.get("file_path", "")
    return str(cwd), str(file_path)


def main() -> None:
    try:
        cwd, file_path = _read_payload()
    except Exception:
        sys.exit(0)

    if not file_path:
        sys.exit(0)

    m = _WORKTREE_RE.match(cwd)
    if not m:
        sys.exit(0)  # Kein Worktree-Kontext → nichts zu tun

    main_repo = m.group("main")
    wt_name = m.group("name")
    wt_path = f"{main_repo}/.claude/worktrees/{wt_name}"

    # Absolute Pfade für zuverlässigen Vergleich
    try:
        abs_file = str(Path(file_path).resolve()) if os.path.isabs(file_path) \
            else str(Path(os.path.join(cwd, file_path)).resolve())
        abs_main = str(Path(main_repo).resolve())
        abs_wt = str(Path(wt_path).resolve())
    except Exception:
        sys.exit(0)

    sep = os.sep

    # Schreibzugriff IN den Worktree → immer erlaubt
    if abs_file.startswith(abs_wt + sep) or abs_file == abs_wt:
        sys.exit(0)

    # Schreibzugriff in Main-Repo aus Worktree-Kontext → BLOCKIEREN
    if abs_file.startswith(abs_main + sep) or abs_file == abs_main:
        print(
            f"BLOCKED [worktree_write_guard]: Worktree '{wt_name}' darf nicht direkt"
            f" ins Main-Repo schreiben.\n"
            f"  Main-Repo: {abs_main}\n"
            f"  Worktree:  {abs_wt}\n"
            f"  Datei:     {abs_file}\n"
            f"→ Änderungen gehören in den Worktree-Branch. Merge nach Abschluss.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
