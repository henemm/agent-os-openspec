#!/usr/bin/env python3
"""Herdr-Bridge: meldet den Workflow-Stand an die Herdr-Sidebar (Issue #466).

Kein Hook (nur `plan-pane-close` steht in hooks.json) — ein Utility, das workflow.py, phase_listener.py
und session_banner.py an ihren Schreibstellen aufrufen. Rein anzeigend: die
Bridge schreibt keinen State und uebernimmt nicht die State-Autoritaet der
offiziellen Herdr-Claude-Integration.

Aktiv nur, wenn ALLE Bedingungen gelten (sonst No-op ohne Seiteneffekt):
- `HERDR_ENV == "1"` und `HERDR_PANE_ID` nicht leer
- `HERDR_BIN_PATH` ist ein absoluter Pfad auf eine ausfuehrbare regulaere Datei
- `config.yaml` -> `herdr.enabled` ist nicht `false` (Opt-out, Default an)

Fail-open ist die tragende Anforderung: jede oeffentliche Funktion faengt alle
Ausnahmen, schreibt nie auf stdout/stderr und aendert keinen Exit-Code. Der
Herdr-Prozess laeuft detached (eigene Session, alle Streams DEVNULL), damit ein
haengendes Binary keinen Hook ausbremst.

Das Auto-/clear (#467) ist mit #663 entfernt: kein Code-Pfad tippt mehr in
einen Herdr-Pane. `herdr.auto_clear` und `OPENSPEC_HERDR_AUTO_CLEAR` werden
nicht mehr gelesen; alte CLI-Aufrufe (`signal ...`, `auto-clear ...`) enden
still mit Exit 0.

Plan-Pane (#476, Opt-out `herdr.plan_pane.enabled: false`): `workflow.py start`
ruft `open_plan_pane`, das den Runner `herdr_bridge.py plan-pane ...` detached
startet. Der Runner splittet den Claude-Pane nach rechts (`pane split`), benennt
den neuen Pane `Workflow` und tippt `workflow.py plan --watch` hinein. Lock
`.claude/herdr_plan_pane.lock`, gemerkte ID `.claude/herdr_plan_pane.json`,
Log `.claude/herdr_plan_pane.log`; immer Exit 0.

#478: session_banner ruft `open_plan_pane_for_active` (Pane nur bei aktivem
Workflow).

#496 Lebenszyklus: Besitz steht als Token am Pane (`owner`, `workflow`,
`version`), nicht mehr in der ID-Datei (die nur noch das cwd fuer
`plan --watch --target` cached). Der Runner raeumt vor dem Oeffnen im EIGENEN
Workspace auf (`pane list --workspace $HERDR_WORKSPACE_ID`, `_pp_sweep`) und
fasst nie ein Pane an, dessen Owner ein anderes lebendes Claude-Pane ist. Der
SessionEnd-Hook `herdr_bridge.py plan-pane-close` schliesst das eigene Pane.

#667: `start_session` (aufgerufen von `workflow.py handoff --start`) startet das
naechste Issue eines autarken Auftrags in einem NEUEN Pane (`pane split`, dann
`pane run <neu> "exec claude <Startauftrag>"`). Es startet nur einen Prozess und
tippt nie in ein laufendes Claude-Pane.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent

SOURCE = "user:openspec"
AGENT = "claude"
TOKEN_NAMES = ("workflow", "issue", "phase", "step", "next", "state", "spur")
# Endzustand (#550) als Seitenleisten-Token: dieselbe Quelle wie Chat und Plan.
STATE_TOKENS = {"done": "erledigt", "waiting": "läuft", "you": "du"}
MAX_LEN = 80  # Herdr kappt Titel/Token-Werte ohnehin bei 80 Zeichen

# Kurzlabels der Sidebar. phase0_idle, phase8_complete und Unbekanntes fehlen
# bewusst: dort gibt es keinen laufenden Stand anzuzeigen -> Clear.
STEP_LABELS = {
    "phase1_context": "CONTEXT",
    "phase2_analyse": "ANALYSE",
    "phase3_spec": "SPEC",
    "phase4_approved": "APPROVED",
    "phase5_tdd_red": "TDD-RED",
    "phase6_implement": "IMPLEMENT",
    "phase6b_adversary": "ADVERSARY",
    "phase7_validate": "VALIDATE",
}

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_last_seq = 0


def _clean(value) -> str:
    """Control-Chars entfernen, auf MAX_LEN kuerzen."""
    return _CONTROL_RE.sub("", str(value or ""))[:MAX_LEN]


def _binary() -> "str | None":
    """HERDR_BIN_PATH nur als absolute, ausfuehrbare regulaere Datei."""
    path = os.environ.get("HERDR_BIN_PATH", "")
    if not path or not os.path.isabs(path):
        return None
    if not os.path.isfile(path) or not os.access(path, os.X_OK):
        return None
    return path


def _enabled() -> bool:
    """Kill-Switch `herdr.enabled: false` in config.yaml (Default: an)."""
    try:
        if str(_HOOK_DIR) not in sys.path:
            sys.path.insert(0, str(_HOOK_DIR))
        from config_loader import load_config
        section = (load_config() or {}).get("herdr")
        if isinstance(section, dict) and section.get("enabled") is False:
            return False
    except Exception:
        pass
    return True


def _pane() -> "str | None":
    """Pane-ID, wenn die Bridge aktiv ist; sonst None."""
    if os.environ.get("HERDR_ENV") != "1":
        return None
    pane = os.environ.get("HERDR_PANE_ID", "").strip()
    if not pane or _binary() is None or not _enabled():
        return None
    return pane


def _next_seq() -> int:
    """Millisekunden-Zeitstempel, im Prozess streng monoton (Herdr verwirft aeltere Reports)."""
    global _last_seq
    _last_seq = max(int(time.time() * 1000), _last_seq + 1)
    return _last_seq


def _launch(binary: str, args, wait: bool, timeout: float):
    """Popen ohne Shell, detached, alle Streams DEVNULL; fail-open."""
    try:
        proc = subprocess.Popen(
            [binary, *[str(a) for a in args]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        if not wait:
            return None
        try:
            return proc.wait(timeout=timeout)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=1)
            except Exception:
                pass
            return None
    except Exception:
        return None


def run_herdr(args, wait: bool = False, timeout: float = 2.0):
    """Startet `[HERDR_BIN_PATH, *args]` ohne Shell, detached; fail-open.

    wait=False kehrt sofort zurueck (None). wait=True wartet hoechstens
    `timeout` Sekunden, danach Kill; Rueckgabe ist der Exit-Code oder None.
    """
    try:
        if _pane() is None:
            return None
        return _launch(_binary(), args, wait, timeout)
    except Exception:
        return None


def _spur_token(workflow) -> str:
    """Spur (#591) aus dem Auftrag, nur lesend; "" ohne Spur oder bei Fehlern."""
    try:
        auftrag = workflow.read_auftrag()
        return _clean((auftrag or {}).get("spur") or "")
    except Exception:
        return ""


_HASH_NUM_RE = re.compile(r"#(\d+)(?!\d)")
SCOPE_TIMEOUT_S = 3.0


def parse_session_scope(payload, workspace: str) -> dict:
    """Sitzungs-Epic und belegte Issues aus `herdr workspace list` (#610). Pure, wirft nie.

    `epic`: erste `#N` im Label des eigenen Workspaces (`workspace_id == workspace`),
    sonst None. `busy`: alle `#N` im Token `wf` der ANDEREN Workspaces (dort
    bearbeitet gerade eine andere Sitzung), aufsteigend.
    """
    out = {"workspace": workspace, "epic": None, "busy": []}
    try:
        spaces = payload["result"]["workspaces"]
        if not isinstance(spaces, list):
            return out
        busy = set()
        for space in spaces:
            if not isinstance(space, dict):
                continue
            if space.get("workspace_id") == workspace:
                match = _HASH_NUM_RE.search(str(space.get("label") or ""))
                out["epic"] = int(match.group(1)) if match else None
                continue
            tokens = space.get("tokens")
            wf = tokens.get("wf") if isinstance(tokens, dict) else None
            if isinstance(wf, str):
                busy.update(int(n) for n in _HASH_NUM_RE.findall(wf))
        out["busy"] = sorted(n for n in busy if n > 0)
    except Exception:
        pass
    return out


def session_scope(timeout: float = SCOPE_TIMEOUT_S) -> "dict | None":
    """`parse_session_scope` fuer den eigenen Workspace per `herdr workspace list` (#610).

    Nur in einer aktiven herdr-Sitzung (`_pane`, `HERDR_WORKSPACE_ID`); sonst und bei
    jedem Fehler None. Wirft nie, schreibt nichts.
    """
    try:
        workspace = os.environ.get("HERDR_WORKSPACE_ID", "").strip()
        if not workspace or _pane() is None:
            return None
        res = _pp_quick(_binary(), ["workspace", "list"], timeout)
        if res is None or res[0] != 0:
            return None
        return parse_session_scope(json.loads(res[1]), workspace)
    except Exception:
        return None


def build_report(data) -> "dict | None":
    """Titel + Tokens fuer den Workflow-Stand; None = Clear statt Report."""
    if not isinstance(data, dict):
        return None
    phase = data.get("current_phase")
    step = STEP_LABELS.get(phase) if isinstance(phase, str) else None
    if str(_HOOK_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOK_DIR))
    import workflow  # Lazy: workflow.py importiert diese Datei (zirkulaer vermeiden)

    if step is None and phase == "phase8_complete" and workflow._ship_pending(data):
        step = "SHIP"  # #612: Code fertig, Auslieferung laeuft noch -> kein Clear
    if step is None:
        return None

    name = str(data.get("name") or "")
    issue = workflow.workflow_issue_number(data) or ""  # #513: State-Feld vor Name
    phase_nr = f"{workflow.PHASE_NUMBERS[phase]}/{workflow.TOTAL_PHASES}"
    nxt = workflow.expected_footer_command(data) or ""
    if nxt and not nxt.startswith("/"):
        # Freitext-Schritt: "Auto-..." fuehrt Claude selbst aus (#470),
        # sonst ist es die Freigabe-Phrase des PO.
        nxt = "auto" if nxt.startswith("Auto-") else "approved"
    head = f"#{issue}" if issue else name
    return {
        "title": _clean(f"{head} {phase_nr} {step}"),
        "tokens": {
            "workflow": _clean(name),
            "issue": _clean(issue),
            "phase": _clean(phase_nr),
            "step": _clean(step),
            "next": _clean(nxt),
            # #555: dieselben Auftrags-Argumente wie `endstate` und Plan
            "state": STATE_TOKENS.get(
                workflow.end_state(data, **workflow.queue_end_args(data))["kind"], "du"),
            # #591: nur Anzeige, die Hoheit ueber die Spur liegt beim Framework
            "spur": _spur_token(workflow),
        },
    }


def _base_args(pane: str) -> list:
    return ["pane", "report-metadata", pane, "--source", SOURCE,
            "--agent", AGENT, "--seq", str(_next_seq())]


def clear() -> None:
    """Titel und alle Tokens raeumen (complete/abandon/phase8/kein Workflow)."""
    try:
        pane = _pane()
        if pane is None:
            return
        args = _base_args(pane) + ["--clear-title"]
        for token in TOKEN_NAMES:
            args += ["--clear-token", token]
        _launch(_binary(), args, False, 0)
    except Exception:
        pass


def report_workflow(data) -> None:
    """Stand des Workflows melden; ohne anzeigbaren Stand -> Clear."""
    try:
        pane = _pane()
        if pane is None:
            return
        report = build_report(data)
        if report is None:
            clear()  # prueft das Gate erneut; nur im seltenen Clear-Fall
            return
        args = _base_args(pane) + ["--title", report["title"]]
        for token in TOKEN_NAMES:
            args += ["--token", f"{token}={report['tokens'][token]}"]
        _launch(_binary(), args, False, 0)
    except Exception:
        pass


def report_active() -> None:
    """Aktiven Workflow melden bzw. Clear, wenn keiner aufloesbar ist (SessionStart)."""
    try:
        if _pane() is None:
            return
        if str(_HOOK_DIR) not in sys.path:
            sys.path.insert(0, str(_HOOK_DIR))
        import workflow
        found = workflow.read_active_workflow_fast()
        data = None
        if found:
            data = dict(found[1])
            data.setdefault("name", found[0])
        report_workflow(data)
    except Exception:
        pass


# --- Gemeinsame Helfer (Basisordner, Log) -----------------------------------

LOG_MAX_LINES = 200


def _hooks_on_path() -> None:
    if str(_HOOK_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOK_DIR))


def _base_dir(cwd=None) -> Path:
    """Worktree-lokale Basis (Vorbild: footer_gate._state_path).

    Mit `cwd` wird dieselbe Aufloesung fuer dieses Verzeichnis gerechnet, ohne
    den Prozess-cwd zu aendern; fehlt es oder existiert es nicht, gilt der
    Prozess-cwd.
    """
    if isinstance(cwd, str) and cwd.strip() and os.path.isdir(cwd):
        return _base_dir_for(Path(cwd))
    _hooks_on_path()
    from hook_utils import _find_worktree_root, find_project_root
    try:
        wt = _find_worktree_root()
        if wt is not None:
            return wt
    except Exception:
        pass
    return find_project_root()


def _base_dir_for(start: Path) -> Path:
    """`_base_dir` fuer ein gegebenes Verzeichnis (Worktree, sonst Projekt-Root)."""
    _hooks_on_path()
    from hook_utils import find_project_root
    current = start.absolute()
    for parent in [current, *current.parents]:
        marker = parent / ".git"
        if marker.is_file():
            return parent
        if marker.is_dir():
            break
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return find_project_root()
    for parent in [current, *current.parents]:
        if (parent / ".git").is_dir():
            return parent
    return current


def _log(line: str, log_file: str) -> None:
    """Zeile mit Zeitstempel an `.claude/<log_file>` haengen (rotierend); fail-open."""
    try:
        from hook_utils import atomic_write_text, read_state_text
        path = _base_dir() / ".claude" / log_file
        root = path.parent.parent
        try:
            old = read_state_text(path, root).splitlines()
        except Exception:
            old = []
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        lines = old[-(LOG_MAX_LINES - 1):] +[f"{stamp} {_CONTROL_RE.sub(' ', line)}"]
        atomic_write_text(path, "\n".join(lines) + "\n", root=root)
    except Exception:
        pass


# --- Plan-Pane rechts neben Claude (#476) -----------------------------------

PP_LOG_FILE = "herdr_plan_pane.log"
PP_LOCK_FILE = "herdr_plan_pane.lock"
PP_ID_FILE = "herdr_plan_pane.json"
PP_LOCK_STALE_S = 30
PP_DEFAULTS = {"enabled": True, "ratio": 0.75}
PP_LABEL = "Workflow"
PP_VERSION_UNKNOWN = "unbekannt-0"  # passt nie zu einer echten Version (#496)


def _valid_ratio(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and 0.1 <= value <= 0.9)


def plan_pane_settings() -> dict:
    """`herdr.plan_pane` mit Defaults: Opt-out (nur Literal `false` schaltet ab),
    Ratio nur als Zahl 0.1–0.9, sonst 0.75. Wirft nie."""
    cfg = dict(PP_DEFAULTS)
    try:
        _hooks_on_path()
        from config_loader import load_config
        section = (load_config() or {}).get("herdr")
        pp = section.get("plan_pane") if isinstance(section, dict) else None
        if isinstance(pp, dict):
            if pp.get("enabled") is False:
                cfg["enabled"] = False
            if _valid_ratio(pp.get("ratio")):
                cfg["ratio"] = float(pp["ratio"])
    except Exception:
        pass
    return cfg


def plan_pane_enabled() -> bool:
    """True, solange `herdr.plan_pane.enabled` nicht `false` ist."""
    return plan_pane_settings()["enabled"]


def open_plan_pane(force: bool = False) -> bool:
    """Runner detached starten; True = gespawnt. force ignoriert plan_pane.enabled,
    nie aber `herdr.enabled`/Herdr-Env (ueber `_pane()`)."""
    try:
        pane = _pane()
        if pane is None:
            return False
        settings = plan_pane_settings()
        if not force and not settings["enabled"]:
            return False
        base = str(_base_dir())
        argv = [sys.executable, str(Path(__file__).resolve()), "plan-pane",
                "--pane", pane, "--cwd", base, "--ratio", str(settings["ratio"])]
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            cwd=base,
        )
        return True
    except Exception:
        return False


def open_plan_pane_for_active() -> bool:
    """SessionStart (#478/#496): Runner immer anstossen — er raeumt im eigenen
    Workspace auf (Sweep) und oeffnet nur bei aktivem Workflow; fail-open."""
    try:
        return open_plan_pane()
    except (Exception, SystemExit):
        return False


def _pp_log(line: str) -> None:
    _log(line, PP_LOG_FILE)


def _pp_call(binary: str, argv, timeout: float):
    """Herdr-Aufruf mit Timeout; None bei Fehler/Zeitlimit."""
    try:
        return subprocess.run([binary, *argv], stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout,
                              close_fds=True)
    except Exception:
        return None


def _pp_take_lock(path: Path) -> bool:
    """Lock per O_EXCL; ein Lock aelter als PP_LOCK_STALE_S wird ersetzt."""
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime < PP_LOCK_STALE_S:
                    return False
                path.unlink()
            except FileNotFoundError:
                pass
    return False


def _pp_pane_lock(claude_pane: str) -> Path:
    """Lock je Claude-Pane: `.claude/herdr_plan_pane.lock/<pane>` (#493 F002)."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", claude_pane)[:80] or "_"
    return _pp_store() / PP_LOCK_FILE / safe


def _pp_take_pane_lock(lock: Path) -> bool:
    """Ordner anlegen (F003) und Pane-Lock nehmen; frischer Alt-Lock (Datei) blockt."""
    folder = lock.parent
    for _ in range(3):
        try:
            if folder.is_file():  # globaler Lock einer aelteren Fassung
                if time.time() - folder.stat().st_mtime < PP_LOCK_STALE_S:
                    return False
                folder.unlink()
            folder.mkdir(parents=True, exist_ok=True)
            return _pp_take_lock(lock)
        except (FileNotFoundError, FileExistsError, NotADirectoryError):
            continue  # Wettlauf mit rmdir/unlink eines anderen Runners
    return False


def _pp_release_lock(lock: Path) -> None:
    for step in (lock.unlink, lock.parent.rmdir):  # rmdir scheitert, wenn andere halten
        try:
            step()
        except Exception:
            pass


def _pp_store() -> Path:
    """`.claude/` im Haupt-Repo: alle Worktrees teilen ID-Datei und Lock (#493)."""
    _hooks_on_path()
    from hook_utils import find_project_root
    return find_project_root() / ".claude"


def _pp_entries(path: Path) -> dict:
    """Eintraege `{claude_pane: {pane_id, cwd}}`; {} bei Fehler/altem Format."""
    from hook_utils import read_state_json
    try:
        data = read_state_json(path, path.parent.parent)
        panes = data.get("panes") if isinstance(data, dict) else None
        return dict(panes) if isinstance(panes, dict) else {}
    except Exception:
        return {}


def _pp_flock(path: Path):
    """Exklusive Sperre `<path>.lock` (max ~2 s); None = ohne Sperre weiter (fail-open)."""
    try:
        import fcntl
        fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o644)
    except Exception:
        return None  # kein fcntl (Windows) oder Datei nicht anlegbar
    deadline = time.monotonic() + 2.0
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        except Exception:
            break
    os.close(fd)
    return None


def _pp_set_entry(path: Path, claude_pane: str, entry: dict) -> None:
    """Eintrag fuer `claude_pane` setzen, andere erhalten (atomar + flock, #493 R2)."""
    from hook_utils import atomic_write_json
    fd = _pp_flock(path)
    try:
        panes = _pp_entries(path)
        panes[claude_pane] = entry
        atomic_write_json(path, {"panes": panes}, root=path.parent.parent)
    finally:
        if fd is not None:
            os.close(fd)  # gibt die Sperre frei


def plugin_version() -> str:
    """Version aus `.claude-plugin/plugin.json` des Plugins (#496); Ersatzwert sonst."""
    try:
        path = _HOOK_DIR.parent.parent / ".claude-plugin" / "plugin.json"
        version = json.loads(path.read_text(encoding="utf-8")).get("version")
        if isinstance(version, str) and version.strip():
            return _clean(version.strip())
    except Exception:
        pass
    return PP_VERSION_UNKNOWN


def _pp_quick(binary: str, argv, timeout: float):
    """Herdr-Aufruf mit hartem Zeitlimit (eigene Prozessgruppe, Kill der Gruppe).

    Rueckgabe (returncode, stdout) oder None bei Fehler/Zeitlimit; wirft nie.
    """
    try:
        proc = subprocess.Popen([binary, *argv], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, close_fds=True, start_new_session=True)
    except Exception:
        return None
    try:
        out, _ = proc.communicate(timeout=max(0.05, timeout))
        return proc.returncode, out or ""
    except Exception:
        try:
            os.killpg(proc.pid, 9)
        except Exception:
            pass
        try:
            proc.kill()
            proc.wait(timeout=0.2)
        except Exception:
            pass
        return None


def _pp_list(binary: str, workspace: str, timeout: float = 3.0) -> "list | None":
    """`pane list --workspace W` — IMMER mit Workspace (#496); None bei jedem Fehler."""
    if not workspace:
        return None
    res = _pp_quick(binary, ["pane", "list", "--workspace", workspace], timeout)
    if res is None or res[0] != 0:
        return None
    try:
        panes = json.loads(res[1])["result"]["panes"]
    except Exception:
        return None
    if not isinstance(panes, list):
        return None
    return [p for p in panes if isinstance(p, dict) and p.get("workspace_id") == workspace]


def _pp_tokens(pane: dict) -> dict:
    tokens = pane.get("tokens")
    return tokens if isinstance(tokens, dict) else {}


PP_WHY_ORPHAN = "ohne owner-Token (Altlast)"
PP_ORPHAN_GRACE_S = 2.0  # zweiter Blick auf ownerlose Panes (#496 R1 F002, Guertel)


def _pp_own_unlabelled(pane: dict, me: str) -> bool:
    """Eigenes Plan-Pane ohne Label (#496 R2 F002): owner == ich plus workflow- und
    version-Token, wie sie nur `_pp_spawn_watcher` setzt (Rename danach gescheitert)."""
    tokens = _pp_tokens(pane)
    return (tokens.get("owner") == me and bool(tokens.get("workflow"))
            and bool(tokens.get("version")))


def _pp_candidate(pane: dict, me: str) -> bool:
    """Plan-Pane-Kandidat: Label „Workflow“ (oder eigenes ohne Label, R2 F002), nicht ich,
    KEIN Agent-Pane (#496 R1 F001)."""
    return ((pane.get("label") == PP_LABEL or _pp_own_unlabelled(pane, me))
            and pane.get("pane_id") != me and not pane.get("agent"))


def _pp_owns_pane(binary: str, me: str, timeout: float) -> bool:
    """#496 R2 F001: True nur, wenn DIESE Claude-Session Vordergrundprozess von `me` ist.

    Ein verschachteltes Kind (`claude -p` aus dem Bash-Werkzeug oder einem Skript der
    Eltern-Session) erbt `HERDR_PANE_ID`, aber nicht den Vordergrund: Herdr meldet per
    `pane process-info` nur den Eltern-Prozess, waehrend `CLAUDE_PID` (setzt Claude Code
    fuer Hooks und Werkzeuge auf den eigenen Prozess) die PID des Kindes ist. Beleg:
    docs/artifacts/fix-496-plan-pane-lebenszyklus/nested-detection.txt.
    Im Zweifel (kein CLAUDE_PID, Fehler, kaputtes JSON) False: lieber nichts tun.
    """
    try:
        own = int(str(os.environ.get("CLAUDE_PID", "")).strip())
    except Exception:
        return False
    if own <= 0:
        return False
    res = _pp_quick(binary, ["pane", "process-info", "--pane", me], timeout)
    if res is None or res[0] != 0:
        return False
    try:
        info = json.loads(res[1])["result"]["process_info"]
        fg = info["foreground_processes"]
        if info.get("pane_id", me) != me or not isinstance(fg, list):
            return False
        return any(isinstance(p, dict) and type(p.get("pid")) is int and p["pid"] == own
                   for p in fg)
    except Exception:
        return False


def _pp_legacy_protected(by_id: dict, me: str) -> set:
    """Pane-IDs, die die #493-ID-Datei einem ANDEREN lebenden Claude-Pane zuordnet (F004).

    Altbestand laufender Sessions aelterer Plugin-Fassungen (ohne Tokens) bleibt stehen.
    Fehler beim Lesen -> leere Menge.
    """
    try:
        entries = _pp_entries(_pp_store() / PP_ID_FILE)
    except Exception:
        return set()
    out = set()
    for claude, entry in entries.items():
        if claude == me or not isinstance(entry, dict):
            continue
        pid = entry.get("pane_id")
        if isinstance(pid, str) and (by_id.get(claude) or {}).get("agent") == AGENT:
            out.add(pid)
    return out


def _pp_verdict(pane: dict, by_id: dict, me: str, active, version: str,
                kept) -> "str | None":
    """Grund zum Schliessen eines Plan-Panes oder None (behalten / nicht anfassen)."""
    tokens = _pp_tokens(pane)
    owner = tokens.get("owner")
    deleted = str(pane.get("cwd") or "").endswith(" (deleted)")
    if owner == me:
        if deleted:
            return "eigenes, cwd geloescht"
        if not active:
            return "eigenes, kein aktiver Workflow"
        if tokens.get("version") != version:
            return f"eigenes, Version {tokens.get('version')} != {version}"
        return "eigenes, Duplikat" if kept else None
    if owner and (by_id.get(owner) or {}).get("agent") == AGENT:
        return None  # fremder lebender Owner: NIE anfassen (Vorrang vor allem anderen)
    if deleted:
        return "cwd geloescht"
    if not owner:
        return PP_WHY_ORPHAN
    if owner not in by_id:
        return f"Owner {owner} fehlt"
    return f"Owner {owner} ohne {AGENT}"


def _pp_close(binary: str, pid: str, why: str) -> None:
    res = _pp_quick(binary, ["pane", "close", pid], 3)
    ok = res is not None and res[0] == 0
    _pp_log(f"plan-pane: close {pid} ({why}) {'OK' if ok else 'fehlgeschlagen'}")


def _pp_sweep(binary: str, me: str, active, version: str) -> "tuple":
    """Plan-Panes im eigenen Workspace abgleichen.

    Rueckgabe (weiter, behaltenes eigenes Pane | None); weiter=False: nichts oeffnen.
    Grundsatz: lieber ein ueberzaehliges Pane stehen lassen als je ein Pane einer
    lebenden Session schliessen.
    """
    workspace = os.environ.get("HERDR_WORKSPACE_ID", "").strip()
    panes = _pp_list(binary, workspace)
    if not _pp_owns_pane(binary, me, 3):  # R2 F001: gilt auch fuers Oeffnen
        _pp_log(f"plan-pane: nichts angefasst (CLAUDE_PID={os.environ.get('CLAUDE_PID', '')!r} "
                f"nicht Vordergrund von {me}: verschachtelte Session oder unklar)")
        return False, None
    if panes is None:
        _pp_log("plan-pane: Sweep uebersprungen (kein Workspace oder pane list fehlgeschlagen)")
        return True, None
    by_id = {p.get("pane_id"): p for p in panes if isinstance(p.get("pane_id"), str)}
    if me not in by_id:  # F003: Env veraltet (z. B. nach `pane move`) -> nicht unser Workspace
        _pp_log(f"plan-pane: Sweep uebersprungen ({me} nicht in pane list {workspace})")
        return False, None
    legacy = _pp_legacy_protected(by_id, me)
    kept = None
    orphans = []
    for pid, pane in by_id.items():
        if not _pp_candidate(pane, me):
            continue
        if not _pp_tokens(pane).get("owner") and pid in legacy:
            _pp_log(f"plan-pane: {pid} behalten (Altbestand einer lebenden Session)")
            continue
        why = _pp_verdict(pane, by_id, me, active, version, kept)
        if why == PP_WHY_ORPHAN:
            orphans.append(pid)
        elif why:
            _pp_close(binary, pid, why)
        elif _pp_tokens(pane).get("owner") == me:
            kept = pane
    if orphans:
        # Guertel (F002): ownerlos kann auch ein gerade entstehendes Pane sein -> nach
        # PP_ORPHAN_GRACE_S neu lesen und nur schliessen, was dann immer noch ownerlos ist.
        time.sleep(PP_ORPHAN_GRACE_S)
        again = _pp_list(binary, workspace)
        if again is None:
            _pp_log("plan-pane: zweiter Blick fehlgeschlagen, ownerlose Panes bleiben")
            return True, kept
        again_by = {p.get("pane_id"): p for p in again if isinstance(p.get("pane_id"), str)}
        legacy = _pp_legacy_protected(again_by, me)
        for pid in orphans:
            pane = again_by.get(pid)
            if (pane is None or not _pp_candidate(pane, me) or pid in legacy
                    or _pp_tokens(pane).get("owner")):
                continue
            _pp_close(binary, pid, PP_WHY_ORPHAN)
    return True, kept


def _pp_spawn_watcher(binary: str, args, active: str, version: str) -> None:
    """split/rename/report-metadata (owner, workflow, version)/run (#476/#496)."""
    import shlex
    ratio = args.ratio if _valid_ratio(args.ratio) else PP_DEFAULTS["ratio"]
    res = _pp_call(binary, ["pane", "split", args.pane, "--direction", "right",
                            "--ratio", str(ratio), "--cwd", args.cwd, "--no-focus"], 5)
    if res is None or res.returncode != 0:
        code = "Zeitlimit/Fehler" if res is None else f"Exit {res.returncode}"
        _pp_log(f"plan-pane: ABBRUCH: pane split {code}")
        return
    try:
        new = json.loads(res.stdout)["result"]["pane"]["pane_id"]
    except Exception:
        new = None
    if not isinstance(new, str) or not new:
        _pp_log("plan-pane: ABBRUCH: pane split ohne pane_id")
        return
    if new == args.pane:  # R2 F003: nie das eigene Claude-Pane anfassen
        _pp_log(f"plan-pane: ABBRUCH: pane split lieferte das eigene Pane {new}")
        return
    # #496 R1 F002: ERST owner-Token, DANN Label. Ein Pane mit Label „Workflow“ hat so
    # immer schon seinen Owner; ohne Label betrachtet kein Sweep es.
    meta = _pp_call(binary, ["pane", "report-metadata", new, "--source", SOURCE,
                             "--token", f"owner={args.pane}",
                             "--token", f"workflow={_clean(active)}",
                             "--token", f"version={version}"], 3)
    if meta is None or meta.returncode != 0:
        _pp_quick(binary, ["pane", "close", new], 3)  # eigenes, gerade gesplittetes Pane
        _pp_log(f"plan-pane: ABBRUCH: report-metadata auf {new} fehlgeschlagen, Pane geschlossen")
        return
    ren = _pp_call(binary, ["pane", "rename", new, PP_LABEL], 3)
    if ren is None or ren.returncode != 0:  # R2 F002: ohne Label kein Watcher, kein Pane
        _pp_quick(binary, ["pane", "close", new], 3)
        _pp_log(f"plan-pane: ABBRUCH: rename auf {new} fehlgeschlagen, Pane geschlossen")
        return
    if args.delay > 0:
        time.sleep(args.delay)
    workflow_py = Path(__file__).resolve().parent / "workflow.py"
    command = (f"exec {shlex.quote(sys.executable)} "
               f"{shlex.quote(str(workflow_py))} plan --watch "
               f"--target {shlex.quote(args.pane)}")
    run = _pp_call(binary, ["pane", "run", new, command], 5)
    _pp_set_entry(_pp_store() / PP_ID_FILE, args.pane, {"pane_id": new, "cwd": args.cwd})
    ok = run is not None and run.returncode == 0
    _pp_log(f"plan-pane: {new} geoeffnet, pane run {'OK' if ok else 'fehlgeschlagen'}")


# --- Frische Sitzung je Auftrags-Issue (#667) --------------------------------

def start_session(prompt: str, cwd) -> "tuple[bool, str]":
    """Neue Claude-Sitzung rechts neben dem eigenen Pane starten (#667). Wirft nie.

    `pane split <eigenes Pane> --direction right --cwd <cwd> --no-focus`, dann
    `pane run <neues Pane> "exec claude <prompt>"`. Nie das eigene Pane als Ziel;
    das alte Pane bleibt stehen. Rueckgabe (ok, Grund); eine Log-Zeile.
    """
    try:
        import shlex
        pane, binary = _pane(), _binary()
        if pane is None or binary is None:
            return _ss_done(False, "kein Herdr-Pane")
        res = _pp_call(binary, ["pane", "split", pane, "--direction", "right",
                                "--cwd", str(cwd), "--no-focus"], 5)
        if res is None or res.returncode != 0:
            code = "Zeitlimit/Fehler" if res is None else f"Exit {res.returncode}"
            return _ss_done(False, f"pane split {code}")
        try:
            new = json.loads(res.stdout)["result"]["pane"]["pane_id"]
        except Exception:
            new = None
        if not isinstance(new, str) or not new:
            return _ss_done(False, "pane split ohne pane_id")
        if new == pane:
            return _ss_done(False, "pane split lieferte das eigene Pane")
        run = _pp_call(binary, ["pane", "run", new, f"exec claude {shlex.quote(prompt)}"], 5)
        if run is None or run.returncode != 0:
            code = "Zeitlimit/Fehler" if run is None else f"Exit {run.returncode}"
            return _ss_done(False, f"pane run {code}")
        return _ss_done(True, f"Sitzung in {new} gestartet")
    except Exception as exc:
        return _ss_done(False, f"Fehler {type(exc).__name__}")


def _ss_done(ok: bool, reason: str) -> "tuple[bool, str]":
    _pp_log(f"handoff: {'OK' if ok else 'ABBRUCH'}: {reason}")
    return ok, reason


def _pp_active_name() -> "str | None":
    """Name des aktiven Workflows oder None; wirft nie."""
    try:
        _hooks_on_path()
        import workflow
        found = workflow.read_active_workflow_fast()
        return str(found[0]) if found else None
    except (Exception, SystemExit):
        return None


def _pp_open(args) -> None:
    """Runner (#476/#496): Sweep im eigenen Workspace, dann behalten oder oeffnen."""
    binary = _binary()
    if binary is None:
        _pp_log("plan-pane: ABBRUCH: HERDR_BIN_PATH ungueltig")
        return
    active = _pp_active_name()
    version = plugin_version()
    proceed, kept = _pp_sweep(binary, args.pane, active, version)
    if not proceed:
        return
    if not active:
        _pp_log("plan-pane: kein aktiver Workflow, nichts zu oeffnen")
        return
    if kept is None:
        _pp_spawn_watcher(binary, args, active, version)
        return
    pid = kept["pane_id"]
    if kept.get("label") != PP_LABEL:  # R2 F002: eigenes Pane ohne Label -> Label nachziehen
        _pp_call(binary, ["pane", "rename", pid, PP_LABEL], 3)
    if _pp_tokens(kept).get("workflow") != _clean(active):
        _pp_call(binary, ["pane", "report-metadata", pid, "--source", SOURCE,
                          "--token", f"workflow={_clean(active)}"], 3)
    # #493: Watcher folgt per --target der Basis der neuen Session (cwd-Cache)
    _pp_set_entry(_pp_store() / PP_ID_FILE, args.pane, {"pane_id": pid, "cwd": args.cwd})
    _pp_log(f"plan-pane: {pid} behalten")


PP_CLOSE_BUDGET_S = 1.0  # SessionEnd-Hooks werden nach ~1,25 s abgebrochen


def run_plan_pane_close() -> int:
    """SessionEnd (#496): eigenes Plan-Pane synchron schliessen; schlank, immer 0.

    Kein `config_loader`/`workflow`-Import, Pruefung nur ueber Env und Binary.
    `reason == "clear"` -> nichts tun (der SessionStart `source=clear` uebernimmt).
    """
    try:
        start = time.monotonic()
        raw = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if isinstance(payload, dict) and payload.get("reason") == "clear":
            return 0
        me = os.environ.get("HERDR_PANE_ID", "").strip()
        binary = _binary()
        if os.environ.get("HERDR_ENV") != "1" or not me or binary is None:
            return 0
        workspace = os.environ.get("HERDR_WORKSPACE_ID", "").strip()
        panes = _pp_list(binary, workspace, timeout=0.4) or []
        # Agent-Panes nie (#496 R1 F001); eigene ohne Label mit (R2 F002)
        own = [p for p in panes if _pp_candidate(p, me) and _pp_tokens(p).get("owner") == me
               and isinstance(p.get("pane_id"), str)]
        if not own:
            return 0
        # R2 F001: nur die Session, die Vordergrund des Panes ist; nie ein Kind-Claude
        left = PP_CLOSE_BUDGET_S - (time.monotonic() - start)
        if left <= 0.1 or not _pp_owns_pane(binary, me, min(0.3, left - 0.05)):
            return 0
        for pane in own:
            left = PP_CLOSE_BUDGET_S - (time.monotonic() - start)
            if left <= 0.05:
                break
            _pp_quick(binary, ["pane", "close", pane["pane_id"]], left)
    except BaseException:
        pass
    return 0


def run_plan_pane(argv) -> int:
    """CLI `plan-pane`: Lock, Pane oeffnen bzw. wiederverwenden; immer 0."""
    lock = None
    try:
        parser = argparse.ArgumentParser(prog="herdr_bridge.py plan-pane")
        parser.add_argument("--pane", required=True)
        parser.add_argument("--cwd", required=True)
        parser.add_argument("--ratio", type=float, default=PP_DEFAULTS["ratio"])
        parser.add_argument("--delay", type=float, default=0.5)
        try:
            args = parser.parse_args(argv)
        except SystemExit:
            _pp_log("plan-pane: ABBRUCH: ungueltige Argumente")
            return 0
        path = _pp_pane_lock(args.pane)
        if not _pp_take_pane_lock(path):
            _pp_log("plan-pane: läuft bereits")
            return 0
        lock = path
        _pp_open(args)
    except Exception as exc:
        _pp_log(f"plan-pane: ABBRUCH: Fehler {type(exc).__name__}")
    finally:
        if lock is not None:
            _pp_release_lock(lock)
    return 0


if __name__ == "__main__":
    # Nur `plan-pane` und `plan-pane-close`; jeder andere Modus (auch entfernte
    # aus alten Registrierungen) endet still mit Exit 0 (#663)
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "plan-pane":
            run_plan_pane(sys.argv[2:])
        elif len(sys.argv) > 1 and sys.argv[1] == "plan-pane-close":
            run_plan_pane_close()
    except BaseException:
        pass
    sys.exit(0)
