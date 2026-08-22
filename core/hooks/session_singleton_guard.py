#!/usr/bin/env python3
"""
Session Singleton Guard — Erzwingt Worktree-Isolation für alle Sessions.

Vier Modi (argv[1]):
- register (SessionStart):  Sitzungseintrag anlegen / erneuern (für Diagnostik).
- guard    (PreToolUse):    Schreibende Tools im Haupt-Repo blockieren.
                            Rescue: EnterWorktree aufrufen.
- cleanup  (Stop):          Eigenen Eintrag löschen.
- claim    (CLI):           Issue-Nummer(n) explizit ins Register eintragen
                            (aus /00-intake, kein stdin-Payload).

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
    """True, wenn der Prozess existiert — plattformneutral via os.kill(pid, 0).

    Die PID-Validierung (int, kein bool, > 0) liegt beim Aufrufer (_is_alive):
    os.kill(0, 0) adressiert die GESAMTE Prozessgruppe des Aufrufers, negative
    Werte eine fremde Prozessgruppe. Beides darf hier nie ankommen.
    """
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False          # Prozess existiert nicht
    except PermissionError:
        return True           # Prozess existiert, gehört fremdem User
    except Exception:
        return False          # fail-safe wie im Bestand


def _read_boot_id() -> "str | None":
    """Boot-ID des laufenden Kernels; None auf Plattformen ohne /proc."""
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        return value or None
    except Exception:
        return None


def _boot_id_matches(entry: dict) -> bool:
    """False nur, wenn gespeicherte und aktuelle boot_id sicher abweichen.

    Nach einem Reboot kann die gespeicherte PID von einem fremden Prozess
    recycelt worden sein — dann beweist eine 'lebende' PID nichts. Fehlt eine
    der beiden Boot-IDs, gibt es nichts zu misstrauen (Rückwärtskompatibilität
    für Lock-Dateien ohne das Feld).
    """
    stored = entry.get("boot_id")
    if not isinstance(stored, str) or not stored:
        return True
    try:
        current = _read_boot_id()
    except Exception:
        return True
    if not current:
        return True
    return stored == current


def _resolve_register_pid() -> int:
    """Stabile PID-Quelle: CLAUDE_PID, sonst os.getppid() (Bestandsverhalten).

    os.getppid() ist in einem Hook die transiente Shell, die sofort nach dem
    Hook stirbt — Wurzelursache von #120.
    """
    try:
        value = int(str(os.environ.get("CLAUDE_PID", "")).strip())
        if value > 0:
            return value
    except Exception:
        pass
    return os.getppid()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _is_alive(entry: dict, now: float) -> bool:
    pid = entry.get("pid")
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
        if _boot_id_matches(entry) and _pid_alive(pid):
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


def _current_workflow_name() -> str:
    """Aktiver Workflow-Name; "" wenn keiner aufloesbar (fail-safe)."""
    try:
        from hook_utils import resolve_active_workflow
        resolved = resolve_active_workflow()
        return (resolved[0] or "") if resolved else ""
    except Exception:
        return ""


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
    name = _current_workflow_name()
    if name:
        out["workflow"] = name
        issue = _extract_issue_number(name)
        if issue:
            out["issue"] = issue
        phase = _read_workflow_phase(name)
        if phase:
            out["phase"] = phase
    return out


def _claim_holds(entry: dict, fields: dict) -> bool:
    """Claim-Erhalt/-Verfall (B2). True = 'issue' ist geclaimt und bleibt.

    Faelle laut Spec: 1 (kein Workflow, bleibt), 2a/2b (Adoption durch den
    erstmals aufloesbaren Workflow), 2c (fremde Nummer -> Verfall), 3 (gleicher
    Workflow, bleibt), 4 (Abweichung -> Verfall).
    """
    if entry.get("issue_source") != "claim":
        return False                       # kein Claim: Bestandsverhalten

    current = fields.get("workflow") or ""
    claim_wf = entry.get("issue_claim_workflow")
    if not isinstance(claim_wf, str):
        claim_wf = ""

    if claim_wf == current:
        return True                        # Fall 1 + Fall 3

    if not claim_wf and current:           # Fall 2 — Adoption nur bei Passung
        number = _extract_issue_number(current)
        claimed = [p.strip() for p in str(entry.get("issue") or "").split(",")]
        if number is None or number in claimed:
            entry["issue_claim_workflow"] = current      # Fall 2a / 2b
            return True

    # Fall 2c + Fall 4 — Claim verfaellt, Regex-Ableitung uebernimmt.
    entry.pop("issue", None)
    entry.pop("issue_source", None)
    entry.pop("issue_claim_workflow", None)
    return False


def _apply_context_fields(entry: dict, cwd: str) -> None:
    """Kontextfelder neu ermitteln; nicht mehr aufloesbare Felder entfernen."""
    fields = _context_fields(cwd)
    keep_issue = _claim_holds(entry, fields)
    for key in _CONTEXT_FIELDS:
        if key == "issue" and keep_issue:
            continue                       # geclaimter Wert schlaegt Regex
        if key in fields:
            entry[key] = fields[key]
        else:
            entry.pop(key, None)


def _build_entry(session_id: str, cwd: str, started_at: float,
                 *, reregistered: bool = False) -> dict:
    """Basis-Registereintrag — einziger Entstehungsweg (register/heartbeat/claim)."""
    entry = {
        "session_id": session_id,
        "cwd": cwd,
        "pid": _resolve_register_pid(),
        "started_at": started_at,
        "last_seen": time.time(),
    }
    try:
        boot_id = _read_boot_id()
    except Exception:
        boot_id = None
    if boot_id:
        entry["boot_id"] = boot_id
    if reregistered:
        entry["reregistered"] = True
    return entry


def _enrich_entry(entry: dict, session_id: str, cwd: str) -> None:
    """agent_name + Kontextfelder — jede Quelle einzeln fail-safe (EB-1)."""
    try:
        agent_name = _harness_agent_name(session_id)
        if agent_name:
            entry["agent_name"] = agent_name
    except Exception:
        pass
    try:
        _apply_context_fields(entry, cwd)
    except Exception:
        pass


def _lock_dir_writable(own_file: Path) -> bool:
    """HEURISTIK auf Verzeichnisrechte — KEINE Schreibgarantie.

    Geprueft wird ausschliesslich das Schreibrecht am Verzeichnis. Ein `True`
    bedeutet also nur "einen Versuch wert", nicht "der Write wird gelingen":
    volle Platte, Quota, schreibgeschuetzte Einzeldatei, NFS-Fehler und TOCTOU
    (Rechte aendern sich zwischen Pruefung und Write) bleiben unentdeckt. Der
    Aufrufer muss den Write daher trotzdem einzeln absichern (F006).

    Zweck ist die Kostenersparnis im Hot-Path: ist das Verzeichnis dauerhaft
    nicht beschreibbar (read-only Mount, Rechtefehler), spart der Vorabtest bei
    JEDEM Guard-Aufruf den kompletten Bau- und Schreibversuch samt
    Exception-Pfad — anders als ein prozesslokaler Cooldown wirkt er auch ueber
    Prozessgrenzen hinweg (jeder Hook-Aufruf ist ein eigener Prozess).
    """
    try:
        own_file.parent.mkdir(parents=True, exist_ok=True)
        return os.access(own_file.parent, os.W_OK)
    except Exception:
        return False


def _reregister(own_file: Path, session_id: str, cwd: str) -> None:
    """A2-Sicherheitsnetz: verlorene Lock-Datei neu anlegen (genau EIN Write).

    started_at ist nach einem Reap nicht rekonstruierbar -> now; reregistered
    haelt fest, dass es kein echter Sessionstart war.

    Bewusst OHNE _harness_agent_name(): dieser Zweig laeuft, solange die Datei
    fehlt, bei JEDEM Guard-Aufruf erneut — der Verzeichnis-Scan ueber
    ~/.claude/sessions/ wuerde sich dabei endlos wiederholen, weil der
    60s-Zeitdeckel ihn nicht bremst (started_at wird hier jedes Mal auf now
    zurueckgesetzt, die Session sieht also dauerhaft "juenger als 60s" aus).
    agent_name holt der regulaere Lazy-Zweig beim naechsten Aufruf nach, sobald
    die Datei wieder existiert — dort ist der Scan durch den Deckel begrenzt.
    """
    if not _lock_dir_writable(own_file):
        return
    entry = _build_entry(session_id, cwd, time.time(), reregistered=True)
    try:
        _apply_context_fields(entry, cwd)
    except Exception:
        pass
    # Eigener Fangarm um den Write (F006): _lock_dir_writable() ist nur eine
    # Heuristik auf Verzeichnisrechte. Volle Platte, Quota, schreibgeschuetzte
    # Datei, NFS- oder TOCTOU-Fehler schlagen erst hier zu. Ohne diese Kapselung
    # verschwimmt so ein Fehler mit dem Sammel-except in _heartbeat() und die
    # Session bliebe dauerhaft unregistriert, ohne unterscheidbare Ursache.
    # Ein Hook darf hier NICHT auf stdout/stderr schreiben (AC-25) — der Fehler
    # wird daher bewusst und lokal verschluckt, nicht global.
    try:
        own_file.write_text(json.dumps(entry))
    except Exception:
        return


def _heartbeat(session_id: str, cwd: str) -> None:
    """Throttled Heartbeat + lazy agent_name-Nachfuehrung.

    Hoechstens EIN Datei-Write pro Aufruf. Fehlt die eigene Lock-Datei, legt
    der Heartbeat sie neu an (A2, ersetzt feat-106 AC-11) und steigt sofort
    aus. Wirft niemals nach aussen (EB-1).
    """
    try:
        own_file = _locks_dir() / f"{_safe_sid(session_id)}.json"
        if not own_file.exists():
            _reregister(own_file, session_id, cwd)
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

    # Gemeinsamer Helper mit dem Re-Register-Zweig (A2) — keine Feld-Drift.
    # Additive Anreicherung: ein Fehler darf den Eintrag nie verhindern (AC-8).
    entry = _build_entry(session_id, cwd, started_at)
    _enrich_entry(entry, session_id, cwd)

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


_MAX_ISSUE_ARG_LEN = 64


def _validate_issue_arg(raw: str) -> "str | None":
    """Nur kommagetrennte Ziffern, hoechstens _MAX_ISSUE_ARG_LEN Zeichen.

    Der Wert landet in der Lock-JSON und in einem tmux-Kommando — ohne
    Laengendeckel koennte ein beliebig langer Wert den Registereintrag
    aufblaehen.
    """
    try:
        value = str(raw)
    except Exception:
        return None
    if len(value) > _MAX_ISSUE_ARG_LEN:
        return None
    return value if re.fullmatch(r"[0-9,]+", value) else None


def _find_claim_target(locks: Path) -> "tuple | None":
    """(session_id, path, entry|None) der claimenden Session, sonst None."""
    try:
        sid = (os.environ.get("CLAUDE_CODE_SESSION_ID") or "").strip()
    except Exception:
        sid = ""

    if sid:
        path = locks / f"{_safe_sid(sid)}.json"
        entry = None
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                entry = data
        except Exception:
            entry = None
        return (sid, path, entry)

    # Fallback: genau EIN Eintrag mit dem aktuellen Arbeitsverzeichnis.
    try:
        cwd = os.getcwd()
        matches = [
            (esid, path, data)
            for esid, (path, data) in _read_entries(locks).items()
            if data.get("cwd") == cwd
        ]
    except Exception:
        return None
    return matches[0] if len(matches) == 1 else None


def _tmux_rename_enabled() -> bool:
    """session_register.tmux_rename; Default true bei jedem Ladefehler."""
    try:
        import config_loader
        section = (config_loader.load_config() or {}).get("session_register") or {}
        return bool(section.get("tmux_rename", True))
    except Exception:
        return True


def _maybe_rename_tmux_window(issue_value: str) -> None:
    """Fenstername auf '#<issues>' setzen — strikt optional, strikt fail-safe."""
    try:
        if not os.environ.get("TMUX"):
            return
        if not _tmux_rename_enabled():
            return
        import shutil
        import subprocess
        if shutil.which("tmux") is None:
            return
        subprocess.run(["tmux", "rename-window", f"#{issue_value}"], timeout=2)
    except Exception:
        pass


def _do_claim(argv: list) -> None:
    """CLI-Modus: Issue-Nummer(n) explizit ins Register eintragen (#121).

    Wrapper um _claim_impl(): JEDER Fehler endet in einer verstaendlichen
    Meldung auf stdout und Exit 0 (F007). Ohne diese Klammer koennte z.B. ein
    Fehler in find_project_root() dazu fuehren, dass claim gar nichts ausgibt
    und trotzdem mit 0 endet — genau die stille Fehlschlagsklasse, gegen die
    schon die Write-Kapselung (F003) gebaut wurde.

    Anders als die Hook-Modi gibt claim Meldungen auf stdout aus — er wird
    direkt aufgerufen, nicht als Hook.
    """
    try:
        _claim_impl(argv)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"claim: interner Fehler ({type(exc).__name__}) — nichts geaendert.")
    sys.exit(0)


def _claim_impl(argv: list) -> None:
    """Eigentliche claim-Logik; steigt per `return` aus, nie per sys.exit()."""
    issue = None
    try:
        idx = argv.index("--issue")
        if idx + 1 < len(argv):
            issue = _validate_issue_arg(argv[idx + 1])
    except Exception:
        issue = None

    if not issue:
        print("claim: --issue erwartet kommagetrennte Ziffern "
              "(z.B. --issue 120,121) — nichts geaendert.")
        return

    locks = _locks_dir()
    target = _find_claim_target(locks)
    if target is None:
        print("claim: keine eindeutige Session gefunden (CLAUDE_CODE_SESSION_ID "
              "fehlt und kein eindeutiger cwd-Treffer) — nichts geaendert.")
        return

    session_id, path, entry = target
    if entry is None:
        # Noch kein Eintrag: ueber denselben A2-Helper anlegen (AC-22).
        try:
            cwd = os.getcwd()
        except Exception:
            cwd = ""
        entry = _build_entry(session_id, cwd, time.time(), reregistered=True)
        _enrich_entry(entry, session_id, cwd)

    entry["issue"] = issue
    entry["issue_source"] = "claim"
    entry["issue_claim_workflow"] = _current_workflow_name()

    # Schreibfehler (read-only Verzeichnis, volle Platte, Rechtefehler) darf
    # nicht still bleiben: sonst sieht der Operator Exit 0 und gar nichts.
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry))
    except Exception as exc:
        print(f"claim: Schreibfehler ({type(exc).__name__}) — nichts geaendert.")
        return
    print(f"claim: Issue #{issue} fuer Session {session_id} eingetragen.")

    _maybe_rename_tmux_window(issue)


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
    if mode == "claim":
        # Direkter CLI-Aufruf ohne stdin-Payload — nicht auf stdin warten.
        _do_claim(sys.argv[2:])
        return
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
