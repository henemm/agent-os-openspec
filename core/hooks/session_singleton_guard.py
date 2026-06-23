#!/usr/bin/env python3
"""
Session Singleton Guard — Blockiert parallele Claude-Sitzungen im selben Repo.

Drei Modi (argv[1]):
- register (SessionStart):  Sitzungseintrag anlegen / erneuern.
- guard    (PreToolUse):    Nicht-Inhaber blockieren; Rescue via EnterWorktree.
- cleanup  (Stop):          Eigenen Eintrag löschen.

Fail-safe: Jede unerwartete Exception → exit(0). Der Guard darf niemals
fälschlich blockieren.

Inhaberschaft: Die Sitzung mit dem frühesten started_at ist Inhaber.
Nur der Inhaber darf Tools ausführen — andere müssen via EnterWorktree in
einen eigenen Worktree wechseln.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

_STALE_SECONDS = int(os.environ.get("OPENSPEC_SESSION_STALE", "900"))

_SHELL_METACHARS = (";", "&&", "||", "|", "$(", "`", "\n", ">", "<", "&")


# ---------------------------------------------------------------------------
# Payload lesen
# ---------------------------------------------------------------------------

def _read_payload() -> dict:
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Pfade
# ---------------------------------------------------------------------------

def _locks_dir() -> Path:
    """Lock-Verzeichnis im Haupt-Repo (worktree-transparent)."""
    from hook_utils import find_project_root
    return find_project_root() / ".claude" / "session-locks"


def _safe_sid(session_id: str) -> str:
    """Dateiname-sicherer Slug der session_id."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", session_id) or "_"


# ---------------------------------------------------------------------------
# PID-Prüfung
# ---------------------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    try:
        return Path(f"/proc/{int(pid)}").exists()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _is_alive(entry: dict, now: float) -> bool:
    pid = entry.get("pid")
    if isinstance(pid, int) and not isinstance(pid, bool):
        return _pid_alive(pid)
    last_seen = entry.get("last_seen")
    return isinstance(last_seen, (int, float)) and (now - last_seen) < _STALE_SECONDS


def _read_entries(locks: Path) -> dict:
    """Alle Registry-Einträge als {session_id: (path, dict)}."""
    out: dict = {}
    if not locks.exists():
        return out
    for f in locks.glob("*.json"):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        sid = data.get("session_id")
        if sid:
            out[sid] = (f, data)
    return out


def _reap_dead(entries: dict, now: float) -> dict:
    """Tote Einträge löschen; gibt lebende zurück."""
    alive: dict = {}
    for sid, (path, data) in entries.items():
        if _is_alive(data, now):
            alive[sid] = (path, data)
        else:
            try:
                path.unlink()
            except Exception:
                pass
    return alive


def _owner_sid(alive: dict) -> "str | None":
    """Inhaber = frühestes started_at; Tie-Break: session_id lexikografisch."""
    if not alive:
        return None

    def sort_key(item):
        sid, (_p, data) = item
        t = data.get("started_at")
        if not isinstance(t, (int, float)):
            t = float("inf")
        return (t, sid)

    return min(alive.items(), key=sort_key)[0]


# ---------------------------------------------------------------------------
# Rescue-Erkennung
# ---------------------------------------------------------------------------

def _has_shell_metachars(command: str) -> bool:
    return any(tok in command for tok in _SHELL_METACHARS)


def _is_worktree_cwd(cwd: str) -> bool:
    """True, wenn cwd in einem .claude/worktrees/<name>/ liegt."""
    return bool(re.search(r"/\.claude/worktrees/[^/]+", cwd or ""))


def _is_rescue_command(tool_name: str, tool_input: dict) -> bool:
    """EnterWorktree ist der einzige erlaubte Rettungsweg."""
    return tool_name == "EnterWorktree"


# ---------------------------------------------------------------------------
# Modi
# ---------------------------------------------------------------------------

def _do_register(payload: dict) -> None:
    session_id = (payload.get("session_id") or "").strip()
    cwd = (payload.get("cwd") or "").strip()
    if not session_id or not cwd:
        sys.exit(0)

    locks = _locks_dir()
    locks.mkdir(parents=True, exist_ok=True)

    now = time.time()
    own_file = locks / f"{_safe_sid(session_id)}.json"

    # started_at bewahren: erneutes register (z.B. nach /clear) verliert
    # keine Inhaberschaft.
    started_at = now
    if own_file.exists():
        try:
            prev = json.loads(own_file.read_text())
            if isinstance(prev.get("started_at"), (int, float)):
                started_at = prev["started_at"]
        except Exception:
            pass

    _reap_dead(_read_entries(locks), now)

    entry = {
        "session_id": session_id,
        "cwd": cwd,
        "pid": os.getppid(),
        "started_at": started_at,
        "last_seen": now,
    }
    own_file.write_text(json.dumps(entry))
    sys.exit(0)


def _do_guard(payload: dict) -> None:
    session_id = (payload.get("session_id") or "").strip()
    cwd = (payload.get("cwd") or "").strip()
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}

    if not session_id or not cwd:
        sys.exit(0)

    # Worktree-Sitzungen niemals blockieren.
    if _is_worktree_cwd(cwd):
        sys.exit(0)

    locks = _locks_dir()
    own_file = locks / f"{_safe_sid(session_id)}.json"

    # Kein eigener Eintrag (Bestands-Sitzung vor der Migration) → erlauben.
    if not own_file.exists():
        sys.exit(0)

    now = time.time()

    # Heartbeat aktualisieren.
    try:
        own = json.loads(own_file.read_text())
        own["last_seen"] = now
        own_file.write_text(json.dumps(own))
    except Exception:
        pass

    alive = _reap_dead(_read_entries(locks), now)
    owner = _owner_sid(alive)

    if owner is None or owner == session_id:
        sys.exit(0)

    if _is_rescue_command(tool_name, tool_input):
        sys.exit(0)

    print(
        "============================================================\n"
        "BLOCKIERT — Parallele Sitzung im selben Repo erkannt!\n"
        "============================================================\n"
        "CLAUDE: In diesem Arbeitsverzeichnis ist bereits eine andere\n"
        "Sitzung aktiv. Isoliere dich SOFORT selbst, indem du das\n"
        "Werkzeug EnterWorktree aufrufst (ohne Parameter genügt).\n"
        "Danach kannst du normal weiterarbeiten — der Nutzer muss\n"
        "nichts tun.\n"
        "\n"
        "(Nur EnterWorktree ist als nächste Aktion erlaubt.)\n",
        file=sys.stderr,
    )
    sys.exit(2)


def _do_cleanup(payload: dict) -> None:
    session_id = (payload.get("session_id") or "").strip()
    if not session_id:
        sys.exit(0)
    locks = _locks_dir()
    own_file = locks / f"{_safe_sid(session_id)}.json"
    try:
        own_file.unlink(missing_ok=True)
    except Exception:
        pass
    sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    payload = _read_payload()
    if mode == "register":
        _do_register(payload)
    elif mode == "guard":
        _do_guard(payload)
    elif mode == "cleanup":
        _do_cleanup(payload)
    else:
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
