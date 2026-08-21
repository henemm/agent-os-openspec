#!/usr/bin/env python3
"""
Session Singleton Guard — Erzwingt Worktree-Isolation für alle Sessions.

Drei Modi (argv[1]):
- register (SessionStart):  Sitzungseintrag anlegen / erneuern (für Diagnostik).
- guard    (PreToolUse):    Schreibende Tools im Haupt-Repo blockieren.
                            Rescue: EnterWorktree aufrufen.
- cleanup  (Stop):          Eigenen Eintrag löschen.

Kernregel: Jede Session muss im eigenen Worktree laufen.
- Lesende Tools (Read, Grep, ToolSearch, …) sind immer erlaubt.
- Schreibende Tools (_BLOCKING_TOOLS) sind im Hauptverzeichnis blockiert.
- Worktree-Sessions (.claude/worktrees/<name>/) sind uneingeschränkt.
- Override-Token: Notausgang für Ausnahmefälle.

Fail-safe: Jede unerwartete Exception → exit(0). Der Guard darf niemals
fälschlich blockieren.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

_STALE_SECONDS = int(os.environ.get("OPENSPEC_SESSION_STALE", "900"))

# Heartbeat-Throttle: last_seen/cwd/branch/workflow/phase/issue werden hoechstens
# alle N Sekunden neu geschrieben (PreToolUse-Hot-Path, I/O-Schutz).
_HEARTBEAT_THROTTLE_SECONDS = int(os.environ.get("OPENSPEC_HEARTBEAT_THROTTLE", "60"))

# Zeitdeckel fuer den lazy agent_name-Lookup: liefert der Harness den Namen in
# der ersten Session-Minute nicht, kommt er nicht mehr — danach kein Scan mehr.
_AGENT_NAME_LOOKUP_WINDOW_SECONDS = 60

_SHELL_METACHARS = (";", "&&", "||", "|", "$(", "`", "\n", ">", "<", "&")

# Nur schreibende/ausführende Tools werden blockiert. Lesende Tools (Read,
# Glob, Grep, WebFetch, ToolSearch, …) bleiben immer erlaubt — sonst führt
# ein Lockout dazu, dass auch der Notausgang (EnterWorktree laden via
# ToolSearch) nicht mehr erreichbar ist.
_BLOCKING_TOOLS = {"Edit", "Write", "MultiEdit", "Bash", "Task", "Agent"}


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
        if _pid_alive(pid):
            return True
        # PID dead: fall back to last_seen. Hooks are invoked via a transient shell
        # subprocess, so os.getppid() returns the shell's PID (not Claude's). The
        # shell exits immediately after the hook, making the stored PID dead on the
        # very next guard call — without this fallback, every live session's lock
        # file would be reaped on its first PreToolUse, breaking isolation entirely.
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


def _has_override_token() -> bool:
    """Prüft ob ein gültiger Override-Token existiert (Notausgang)."""
    try:
        from override_token import has_valid_token
        return has_valid_token()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Anreicherung des Registereintrags (alle Quellen einzeln fail-safe, EB-1)
# ---------------------------------------------------------------------------

def _extract_worktree(cwd: str) -> "str | None":
    """Worktree-Name aus einem .claude/worktrees/<name>/-Pfad."""
    try:
        m = re.search(r"/\.claude/worktrees/([^/]+)", cwd or "")
        return m.group(1) if m else None
    except Exception:
        return None


def _read_branch(cwd: str) -> "str | None":
    """Branchname aus .git/HEAD — reines Dateilesen, kein Subprozess (EB-2)."""
    try:
        git = Path(cwd) / ".git"
        if git.is_file():
            line = git.read_text().strip()
            if not line.startswith("gitdir:"):
                return None
            gitdir = Path(line.split(":", 1)[1].strip())
            if not gitdir.is_absolute():
                gitdir = (Path(cwd) / gitdir).resolve()
            head = gitdir / "HEAD"
        elif git.is_dir():
            head = git / "HEAD"
        else:
            return None
        content = head.read_text().strip()
        prefix = "ref: refs/heads/"
        if content.startswith(prefix):
            return content[len(prefix):].strip() or None
        return None
    except Exception:
        return None


def _extract_issue_number(workflow_name: str) -> "str | None":
    """Erste Ziffernfolge im Workflow-Namen (feat-106-... -> '106')."""
    try:
        m = re.search(r"\d+", workflow_name or "")
        return m.group(0) if m else None
    except Exception:
        return None


def _read_workflow_phase(workflow_name: str) -> "str | None":
    """current_phase aus .claude/workflows/<name>.json."""
    try:
        from hook_utils import find_project_root
        path = (find_project_root() / ".claude" / "workflows"
                / f"{workflow_name}.json")
        data = json.loads(path.read_text())
        phase = data.get("current_phase")
        return phase if isinstance(phase, str) and phase else None
    except Exception:
        return None


def _harness_agent_name(session_id: str) -> "str | None":
    """agent_name aus dem Harness-Register ~/.claude/sessions/*.json.

    Undokumentiertes Harness-Internal — nur .get()-Zugriffe, keine
    Formatpruefung. Jeder Fehler degradiert still auf None (EB-4).
    """
    try:
        sessions = Path.home() / ".claude" / "sessions"
        if not sessions.is_dir():
            return None
        for f in sessions.glob("*.json"):
            try:
                data = json.loads(f.read_text())
            except Exception:
                continue  # kaputte Einzeldatei bricht den Scan nicht ab
            if not isinstance(data, dict):
                continue
            if data.get("sessionId") != session_id:
                continue
            name = data.get("name")
            if isinstance(name, str) and name.strip():
                return name
        return None
    except Exception:
        return None


_CONTEXT_FIELDS = ("worktree", "branch", "workflow", "issue", "phase")


def _context_fields(cwd: str) -> dict:
    """Alle ableitbaren Kontextfelder; fehlende Quellen fehlen im Ergebnis."""
    out: dict = {}
    try:
        wt = _extract_worktree(cwd)
        if wt:
            out["worktree"] = wt
    except Exception:
        pass
    try:
        branch = _read_branch(cwd)
        if branch:
            out["branch"] = branch
    except Exception:
        pass
    try:
        from hook_utils import resolve_active_workflow
        resolved = resolve_active_workflow()
        name = (resolved[0] or "") if resolved else ""
    except Exception:
        name = ""
    if name:
        out["workflow"] = name
        issue = _extract_issue_number(name)
        if issue:
            out["issue"] = issue
        phase = _read_workflow_phase(name)
        if phase:
            out["phase"] = phase
    return out


def _apply_context_fields(entry: dict, cwd: str) -> None:
    """Kontextfelder neu ermitteln; nicht mehr aufloesbare Felder entfernen."""
    fields = _context_fields(cwd)
    for key in _CONTEXT_FIELDS:
        if key in fields:
            entry[key] = fields[key]
        else:
            entry.pop(key, None)


def _heartbeat(session_id: str, cwd: str) -> None:
    """Throttled Heartbeat + lazy agent_name-Nachfuehrung.

    Hoechstens EIN Datei-Write pro Aufruf. Legt niemals einen Eintrag an
    (AC-11) und wirft niemals nach aussen (EB-1).
    """
    try:
        own_file = _locks_dir() / f"{_safe_sid(session_id)}.json"
        if not own_file.exists():
            return
        try:
            entry = json.loads(own_file.read_text())
        except Exception:
            return
        if not isinstance(entry, dict):
            return

        now = time.time()
        changed = False

        # (1) agent_name: unabhaengig vom Throttle, aber nur solange das Feld
        #     fehlt UND die Session juenger als der Zeitdeckel ist (EB-3/AC-16).
        if not entry.get("agent_name"):
            started_at = entry.get("started_at")
            in_window = (
                isinstance(started_at, (int, float))
                and not isinstance(started_at, bool)
                and (now - started_at) < _AGENT_NAME_LOOKUP_WINDOW_SECONDS
            )
            if in_window:
                try:
                    name = _harness_agent_name(session_id)
                except Exception:
                    name = None
                if name:
                    entry["agent_name"] = name
                    changed = True

        # (2) Restliche Felder: Throttle-Fenster.
        last_seen = entry.get("last_seen")
        due = (
            not isinstance(last_seen, (int, float))
            or isinstance(last_seen, bool)
            or (now - last_seen) >= _HEARTBEAT_THROTTLE_SECONDS
        )
        if due:
            entry["last_seen"] = now
            entry["cwd"] = cwd
            _apply_context_fields(entry, cwd)
            changed = True

        # Ein gemeinsamer Schreibvorgang fuer beide Zweige.
        if changed:
            own_file.write_text(json.dumps(entry))
    except Exception:
        pass


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

    # Additive Anreicherung — jede Quelle einzeln fail-safe (EB-1). Ein Fehler
    # darf den Bestandseintrag niemals verhindern (AC-8).
    try:
        agent_name = _harness_agent_name(session_id)
        if agent_name:
            entry["agent_name"] = agent_name
    except Exception:
        pass
    try:
        entry.update(_context_fields(cwd))
    except Exception:
        pass

    own_file.write_text(json.dumps(entry))
    sys.exit(0)


def _do_guard(payload: dict) -> None:
    session_id = (payload.get("session_id") or "").strip()
    cwd = (payload.get("cwd") or "").strip()
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}

    if not session_id or not cwd:
        sys.exit(0)

    # Heartbeat VOR allen Ausstiegspfaden — sonst erreichen Worktree-Sessions
    # und rein lesende Tools den Heartbeat nie und verfallen nach
    # _STALE_SECONDS (AC-2/AC-4/AC-5).
    _heartbeat(session_id, cwd)

    # Lesende Tools niemals blockieren — sonst ist auch EnterWorktree
    # via ToolSearch nicht mehr ladbar (kompletter Deadlock).
    if tool_name not in _BLOCKING_TOOLS:
        sys.exit(0)

    # Worktree-Sitzungen haben eigene Isolation — kein weiterer Check.
    if _is_worktree_cwd(cwd):
        sys.exit(0)

    # EnterWorktree ist der einzige Rettungsweg aus dem Hauptverzeichnis.
    if _is_rescue_command(tool_name, tool_input):
        sys.exit(0)

    # Override-Token: expliziter Notausgang für Ausnahmefälle.
    if _has_override_token():
        sys.exit(0)

    print(
        "============================================================\n"
        "BLOCKIERT — Alle Sessions müssen im Worktree laufen!\n"
        "============================================================\n"
        "CLAUDE: Du befindest dich im Haupt-Repo. Schreibende Tools\n"
        "sind hier gesperrt. Rufe SOFORT EnterWorktree auf (ohne\n"
        "Parameter). Das Tool erstellt einen eigenen Worktree für\n"
        "diese Sitzung. Danach kannst du normal weiterarbeiten.\n"
        "\n"
        "(Nur EnterWorktree und lesende Tools sind jetzt erlaubt.)\n",
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
