#!/usr/bin/env python3
"""Herdr-Bridge: meldet den Workflow-Stand an die Herdr-Sidebar (Issue #466).

Kein Hook (nicht in hooks.json) — ein Utility, das workflow.py, phase_listener.py
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

`run_herdr` ist bewusst generisch gehalten — Basis fuer #467 (Auto-/clear).

Auto-/clear (#467, Opt-in `herdr.auto_clear.enabled: true`): footer_gate ruft
auf dem Pfad "Fusszeile korrekt" `maybe_auto_clear` auf. Sind alle Bedingungen
erfuellt, startet `spawn_auto_clear` diesen Script detached als Runner
(`herdr_bridge.py auto-clear ...`), der per `pane send-text` + `pane send-keys
enter` erst `/clear` und dann den naechsten Workflow-Befehl in den Pane tippt. Der Runner bricht bei
jedem Zweifel ab, protokolliert den Grund in `.claude/herdr_auto_clear.log` und
endet immer mit Exit 0.

#506: Herdrs Agent-Status (`agent wait`) entscheidet nicht mehr — lokale
Erkennungsregeln koennen ihn beliebig verschieben. Der Runner liest eigene
Plugin-Signale je Pane aus `.claude/herdr_signals/` (`record_signal`):
`<pane>.input.json` schreibt phase_listener bei jedem abgeschickten Prompt
(neue Eingabe seit dem Stop-Hook-Zeitpunkt `--since` -> Abbruch), `<pane>.session.json` schreibt
session_banner bei jedem SessionStart (nach `/clear` wird auf `source=clear`
gewartet). Herdr dient nur noch als Tastatur (`agent prompt` lehnt bei `blocked`
mit `agent_blocked` ab). Ein Stop ist nicht zwingend das Turn-Ende (ein fremder
Stop-Hook kann den Turn per `decision: block` fortsetzen); deshalb schreiben
zusaetzlich session_singleton_guard (PreToolUse, `<pane>.activity.json`), der
CLI-Modus `signal activity` (Notification `permission_prompt`, PermissionRequest)
und footer_gate (jeder Stop, `<pane>.stop.json`) eigene Marker. Der Runner tippt
nur, wenn seit dem Stop (bzw. nach dem eigenen `/clear` + Toleranz) keines
dieser Signale eintraf (`_check_activity`), sonst "Claude arbeitet weiter".
Adversary R2: Default-grace 10 s (fremde Stop-Hooks laufen ohne Signal), erneute
Pruefung zwischen `send-text` und Enter (bei Abbruch Zeile per `ctrl+u` loeschen),
SessionEnd (`signal activity`, `kind=session_end`) und ein SessionStart mit
`source != clear` nach der Referenz zaehlen als Abbruch.

Plan-Pane (#476, Opt-out `herdr.plan_pane.enabled: false`): `workflow.py start`
ruft `open_plan_pane`, das den Runner `herdr_bridge.py plan-pane ...` detached
startet. Der Runner splittet den Claude-Pane nach rechts (`pane split`), benennt
den neuen Pane `Workflow` und tippt `workflow.py plan --watch` hinein. Lock
`.claude/herdr_plan_pane.lock`, gemerkte ID `.claude/herdr_plan_pane.json`,
Log `.claude/herdr_plan_pane.log`; immer Exit 0.

#478: session_banner ruft `open_plan_pane_for_active` (Pane nur bei aktivem
Workflow). `maybe_auto_clear` loggt bei aktivem Opt-in jeden Skip-Grund
(`skip: <grund>`, gleiche Zeile in Folge nur einmal).

#496 Lebenszyklus: Besitz steht als Token am Pane (`owner`, `workflow`,
`version`), nicht mehr in der ID-Datei (die nur noch das cwd fuer
`plan --watch --target` cached). Der Runner raeumt vor dem Oeffnen im EIGENEN
Workspace auf (`pane list --workspace $HERDR_WORKSPACE_ID`, `_pp_sweep`) und
fasst nie ein Pane an, dessen Owner ein anderes lebendes Claude-Pane ist. Der
SessionEnd-Hook `herdr_bridge.py plan-pane-close` schliesst das eigene Pane.
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
TOKEN_NAMES = ("workflow", "issue", "phase", "step", "next")
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


def build_report(data) -> "dict | None":
    """Titel + Tokens fuer den Workflow-Stand; None = Clear statt Report."""
    if not isinstance(data, dict):
        return None
    phase = data.get("current_phase")
    step = STEP_LABELS.get(phase) if isinstance(phase, str) else None
    if step is None:
        return None
    if str(_HOOK_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOK_DIR))
    import workflow  # Lazy: workflow.py importiert diese Datei (zirkulaer vermeiden)

    name = str(data.get("name") or "")
    issue = workflow.issue_number(name) or ""
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
        },
    }


def _base_args(pane: str) -> list:
    return ["pane", "report-metadata", pane, "--source", SOURCE,
            "--agent", AGENT, "--seq", str(_next_seq())]


def clear() -> None:
    """Titel und alle fuenf Tokens raeumen (complete/abandon/phase8/kein Workflow)."""
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


# --- Auto-/clear an Phasengrenzen (#467) ------------------------------------

AC_STATE_FILE = "herdr_auto_clear_state.json"
AC_LOG_FILE = "herdr_auto_clear.log"
AC_LOCK_SECONDS = 600  # Once-Lock: identischer Schluessel loest 10 min nicht erneut aus
AC_BOUNDARY_MAX_AGE_S = 900  # Grenz-Vermerk (#495) gilt hoechstens 15 min
# grace_s 10 (#506 R2): fremde Stop-Hooks laufen ohne Signal; blockt einer nach
# laengerer Laufzeit, kommt die Fortsetzung (PreToolUse/Stop) erst danach
AC_DEFAULTS = {"grace_s": 10, "idle_timeout_s": 120, "announce": True}
AC_SETTLE_S = 2.0       # Wartezeit vor State-Recheck bzw. nach /clear
AC_PROMPT_TIMEOUT = 15  # Sekunden je `pane send-text`/`send-keys`/`notification show`
AC_LOG_MAX_LINES = 200

POSITIVE_MARKER = "`/clear` ist jetzt gefahrlos"
NEGATIVE_MARKER = "`/clear` jetzt NICHT"
AC_SIGNAL_DIR = "herdr_signals"  # eigene Hook-Signale je Pane (#506)
AC_SIGNAL_POLL_S = 0.2
AC_CLEAR_TOLERANCE_S = 2.0  # Signale bis t_clear + 2 s gehoeren zum eigenen /clear (#506)
AC_SINCE_FUTURE_S = 5.0     # `--since` hoechstens so weit in der Zukunft (#506)
AC_CONTINUE_KINDS = ("input", "activity", "stop")  # Fortsetzungs-Signale (#506)
AC_CLEAR_KEY = "ctrl+u"  # Eingabezeile loeschen (Herdr 0.9.5: `pane send-keys <p> ctrl+u`)
_PANE_FILE_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _hooks_on_path() -> None:
    if str(_HOOK_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOK_DIR))


def _auto_clear_config() -> "dict | None":
    """Opt-in mit Vorrang: Projekt `false` > Projekt `true` > Umgebung > aus (#480).

    Bewusst NICHT `_enabled()` (Opt-out). Nur das Literal `enabled: false`/`true`
    im Projekt entscheidet; fehlt es (oder ist es kein bool), schaltet die
    Umgebungsvariable `OPENSPEC_HERDR_AUTO_CLEAR` (1/true/yes/on) benutzerweit
    ein. Werte aus dem Projektabschnitt gelten mit Defaults fuer fehlende/
    unbrauchbare Eintraege. Jede Ausnahme -> None (aus).
    """
    try:
        _hooks_on_path()
        from config_loader import load_config
        section = (load_config() or {}).get("herdr")
        auto = section.get("auto_clear") if isinstance(section, dict) else None
        auto = auto if isinstance(auto, dict) else {}
        enabled = auto.get("enabled")
        if enabled is False:
            return None
        if enabled is not True:
            switch = os.environ.get("OPENSPEC_HERDR_AUTO_CLEAR", "").strip().lower()
            if switch not in ("1", "true", "yes", "on"):
                return None
        cfg = dict(AC_DEFAULTS)
        for key in ("grace_s", "idle_timeout_s"):
            val = auto.get(key)
            if isinstance(val, (int, float)) and not isinstance(val, bool) and val >= 0:
                cfg[key] = val
        if isinstance(auto.get("announce"), bool):
            cfg["announce"] = auto["announce"]
        return cfg
    except Exception:
        return None


def auto_clear_enabled() -> bool:
    """True bei Projekt `enabled: true` oder (ohne Projektwert) Env-Schalter (#480)."""
    return _auto_clear_config() is not None


def _footer_parts():
    """DU_LINE_RE und _footer_commands aus footer_gate (eine Quelle, Lazy-Import)."""
    _hooks_on_path()
    import footer_gate
    return footer_gate.DU_LINE_RE, footer_gate._footer_commands


def has_clear_marker(message) -> bool:
    """Positivmarker ausserhalb von Code-Fences vor der letzten ❗Du-Zeile,
    und der Negativmarker nirgends in der Nachricht (auch nicht in Fences)."""
    try:
        if not isinstance(message, str) or not message:
            return False
        if NEGATIVE_MARKER in message.replace("**", ""):
            return False
        du_re, _ = _footer_parts()
        lines = message.splitlines()
        last_du = None
        for i, line in enumerate(lines):
            if du_re.match(line):
                last_du = i
        if last_du is None:
            return False
        in_fence = False
        for line in lines[:last_du]:
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence and POSITIVE_MARKER in line.replace("**", ""):
                return True
        return False
    except Exception:
        return False


def _ac_base(cwd=None) -> Path:
    """Worktree-lokale Basis (Vorbild: footer_gate._state_path).

    Mit `cwd` (Payload-`cwd` eines Hooks, #506) wird dieselbe Aufloesung fuer
    dieses Verzeichnis gerechnet, ohne den Prozess-cwd zu aendern; fehlt es oder
    existiert es nicht, gilt der Prozess-cwd.
    """
    if isinstance(cwd, str) and cwd.strip() and os.path.isdir(cwd):
        return _ac_base_for(Path(cwd))
    _hooks_on_path()
    from hook_utils import _find_worktree_root, find_project_root
    try:
        wt = _find_worktree_root()
        if wt is not None:
            return wt
    except Exception:
        pass
    return find_project_root()


def _ac_base_for(start: Path) -> Path:
    """`_ac_base` fuer ein gegebenes Verzeichnis (Worktree, sonst Projekt-Root)."""
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


def _lock_active(stamp, now: float) -> bool:
    return (isinstance(stamp, (int, float)) and not isinstance(stamp, bool)
            and 0 <= now - stamp < AC_LOCK_SECONDS)


def _read_lock_state(path: Path) -> dict:
    from hook_utils import read_state_json
    try:
        data = read_state_json(path, path.parent.parent)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _acquire_lock(key: str) -> bool:
    """Once-Lock setzen; False, wenn der Schluessel noch gesperrt ist."""
    from hook_utils import atomic_write_json
    path = _ac_base() / ".claude" / AC_STATE_FILE
    now = time.time()
    state = {k: v for k, v in _read_lock_state(path).items() if _lock_active(v, now)}
    if key in state:
        return False
    state[key] = now
    atomic_write_json(path, state, root=path.parent.parent)
    return True


def _release_lock(key: str) -> None:
    try:
        from hook_utils import atomic_write_json
        path = _ac_base() / ".claude" / AC_STATE_FILE
        state = _read_lock_state(path)
        if state.pop(key, None) is not None:
            atomic_write_json(path, state, root=path.parent.parent)
    except Exception:
        pass


def spawn_auto_clear(pane: str, workflow_name: str, phase: str, command: str,
                     cfg: dict, since: "float | None" = None) -> bool:
    """Runner detached starten (kein Shell, eigene Session, DEVNULL); sofort zurueck.

    `since` (Epoch-Sekunden, Default jetzt) ist der Stop-Hook-Zeitpunkt (#506):
    Eingaben danach gelten fuer den Runner als "Nutzer hat weitergeschrieben".
    """
    try:
        since = time.time() if since is None else float(since)
        argv = [sys.executable, str(Path(__file__).resolve()), "auto-clear",
                "--pane", pane, "--workflow", workflow_name, "--phase", phase,
                "--command", command,
                "--grace", str(cfg.get("grace_s", AC_DEFAULTS["grace_s"])),
                "--idle-timeout", str(cfg.get("idle_timeout_s", AC_DEFAULTS["idle_timeout_s"])),
                "--announce", "1" if cfg.get("announce", True) else "0",
                "--since", repr(since)]
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            cwd=str(_ac_base()),
        )
        return True
    except Exception:
        return False


PLUGIN_NAMESPACE = "agent-os-openspec"
MANUAL_COMMANDS = ("99-reset",)  # Workflow-Abschluss bleibt menschlich (#499)


def _command_name(command) -> str:
    """Befehlsname ohne fuehrenden `/` (erster Token); leer bei Unbrauchbarem."""
    parts = str(command or "").split()
    return parts[0].lstrip("/") if parts else ""


def resolve_command_form(command: str) -> str:
    """Tatsaechlich getippte Form des Folgebefehls (#499). Pure bis auf Dateipruefung.

    Kurzform, wenn ein Alias an einem der Orte liegt, die Claude Code aufloest
    (Worktree/Projekt/Home je `commands/<name>.md` und `skills/<name>/SKILL.md`);
    sonst Plugin-Form. Qualifizierte Befehle (`:` im Namen) bleiben unveraendert,
    Argumente werden angehaengt. Jede Ausnahme ergibt die Plugin-Form.
    """
    parts = str(command).split(maxsplit=1)
    name = _command_name(command)
    if not name or ":" in name:
        return command
    rest = f" {parts[1]}" if len(parts) > 1 else ""
    try:
        _hooks_on_path()
        from hook_utils import find_project_root
        # Worktree (Session-Ordner) und Haupt-Repo; find_project_root loest Worktrees auf
        for base in (_ac_base(), find_project_root(), Path.home()):
            claude = Path(base) / ".claude"
            if ((claude / "commands" / f"{name}.md").is_file()
                    or (claude / "skills" / name / "SKILL.md").is_file()):
                return f"/{name}{rest}"
    except (Exception, SystemExit):
        pass
    return f"/{PLUGIN_NAMESPACE}:{name}{rest}"


def maybe_auto_clear(payload, message, data) -> bool:
    """Trigger-Bedingungen (#467) in Spec-Reihenfolge; True = Runner gespawnt.

    Ausloeser ist der Grenz-Vermerk `auto_clear_boundary` (#495), nicht mehr der
    Positiv-Satz; der Negativ-Satz bleibt Veto.

    Fail-open: jede nicht erfuellte Bedingung oder Ausnahme = kein Spawn.
    """
    try:
        since = time.time()  # Stop-Hook-Zeitpunkt: Referenz fuer neue Eingaben (#506)
        pane = _pane()
        if pane is None:
            return False
        cfg = _auto_clear_config()
        if cfg is None:
            return False
        # Ab hier Opt-in aktiv: jeder Abbruch landet als `skip:` im Log (#478)
        if isinstance(payload, dict) and payload.get("stop_hook_active") is True:
            # Folge-Stop nach Fusszeilen-Korrektur: kein Auto-/clear, Vermerk verwerfen,
            # damit kein spaeterer Turn derselben Phase ausloest (#495)
            if isinstance(data, dict) and isinstance(data.get("auto_clear_boundary"), dict):
                _consume_boundary(data, data["auto_clear_boundary"])
            return _ac_skip("stop_hook_active")
        if not isinstance(data, dict) or not isinstance(message, str):
            return _ac_skip("Workflow ohne Name/Phase")
        _hooks_on_path()
        import workflow
        command = workflow.expected_footer_command(data)
        if not isinstance(command, str) or not command.startswith("/"):
            # Freitext-Schritt (Freigabe) loest nie aus
            return _ac_skip(f"kein Slash-Befehl als naechster Schritt ({command})")
        first = command.split()[0]
        if first == "/clear":
            return _ac_skip("/clear als Befehl")
        if _command_name(command) in MANUAL_COMMANDS:
            return _ac_skip("Workflow-Abschluss bleibt manuell")
        _, footer_commands = _footer_parts()
        if first not in footer_commands(message):
            return _ac_skip(f"Fusszeile nennt {command} nicht")
        # Ab hier wird der Vermerk ausgewertet: Einmal-Signal, also verbrauchen (#495)
        boundary = data.get("auto_clear_boundary")
        if not isinstance(boundary, dict):
            return _ac_skip("keine Grenze vermerkt")
        _consume_boundary(data, boundary)
        if NEGATIVE_MARKER in message.replace("**", ""):
            return _ac_skip("Negativmarker")
        if not _boundary_matches(data, command):
            return _ac_skip("keine Grenze vermerkt")
        if not _boundary_fresh(boundary):
            return _ac_skip("Grenze veraltet")
        name = str(data.get("name") or "")
        phase = str(data.get("current_phase") or "")
        if not name or not phase:
            return _ac_skip("Workflow ohne Name/Phase")
        key = f"{name}|{phase}|{command}"
        if not _acquire_lock(key):
            return _ac_skip("Once-Lock aktiv")
        if not spawn_auto_clear(pane, name, phase, command, cfg, since=since):
            _release_lock(key)
            return _ac_skip("Spawn fehlgeschlagen")
        return True
    except Exception:
        return False


def _boundary_matches(data: dict, command: str) -> bool:
    """Grenz-Vermerk von `workflow.py autoclear` passt zu Phase und Befehl (#495)."""
    boundary = data.get("auto_clear_boundary")
    if not isinstance(boundary, dict):
        return False
    return (boundary.get("phase") == data.get("current_phase")
            and boundary.get("command") == command)


def _boundary_fresh(boundary: dict) -> bool:
    """Vermerk hoechstens AC_BOUNDARY_MAX_AGE_S alt (Sicherheitsnetz, #495)."""
    try:
        from datetime import datetime
        at = datetime.fromisoformat(str(boundary.get("at")))
        if at.tzinfo is not None:
            at = at.astimezone().replace(tzinfo=None)
        age = (datetime.now() - at).total_seconds()
    except Exception:
        return False
    return -60 <= age <= AC_BOUNDARY_MAX_AGE_S


def _consume_boundary(data: dict, boundary: dict) -> None:
    """Ausgewerteten Vermerk aus dem Workflow-State entfernen (#495); fail-open.

    Read-Modify-Write auf dieselbe Datei, die footer_gate liest; entfernt wird
    nur der ausgewertete Vermerk, nie ein inzwischen neuerer. Kein Herdr-Report.
    """
    try:
        name = str(data.get("name") or "")
        if not name or "/" in name or name.startswith("."):
            return
        _hooks_on_path()
        from hook_utils import atomic_write_json, find_project_root, read_state_json
        root = find_project_root()
        path = root / ".claude" / "workflows" / f"{name}.json"
        state = read_state_json(path, root)
        if not isinstance(state, dict) or state.get("auto_clear_boundary") != boundary:
            return
        del state["auto_clear_boundary"]
        atomic_write_json(path, state, root=root)
    except Exception:
        pass


def _ac_skip(reason: str) -> bool:
    """Skip-Grund loggen (#478), gleiche Zeile in Folge nur einmal; immer False."""
    try:
        line = f"skip: {_CONTROL_RE.sub(' ', reason)}"
        _hooks_on_path()
        from hook_utils import read_state_text
        path = _ac_base() / ".claude" / AC_LOG_FILE
        try:
            old = read_state_text(path, path.parent.parent).splitlines()
        except Exception:
            old = []
        last = old[-1].split(" ", 1)[1] if old and " " in old[-1] else None
        if last != line:
            _ac_log(line)
    except Exception:
        pass
    return False


# --- Runner (eigener Prozess) ---

class _Abort(Exception):
    """Runner-Abbruch mit Grund; nach Abbruch wird nichts mehr gesendet."""


def _ac_log(line: str, log_file: str = AC_LOG_FILE) -> None:
    """Zeile mit Zeitstempel an `.claude/<log_file>` haengen (rotierend); fail-open."""
    try:
        from hook_utils import atomic_write_text, read_state_text
        path = _ac_base() / ".claude" / log_file
        root = path.parent.parent
        try:
            old = read_state_text(path, root).splitlines()
        except Exception:
            old = []
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        lines = old[-(AC_LOG_MAX_LINES - 1):] + [f"{stamp} {_CONTROL_RE.sub(' ', line)}"]
        atomic_write_text(path, "\n".join(lines) + "\n", root=root)
    except Exception:
        pass


def _signal_path(pane, kind: str, cwd=None) -> "tuple[Path, Path] | None":
    """(Marker-Pfad, Wurzel) je Pane; Dateiname nur aus `[A-Za-z0-9_.-]` (#506)."""
    safe = _PANE_FILE_RE.sub("", str(pane or ""))
    if not safe.strip("."):
        return None
    base = _ac_base(cwd)
    return base / ".claude" / AC_SIGNAL_DIR / f"{safe}.{kind}.json", base


def record_signal(kind: str, source=None, cwd=None, reason=None) -> None:
    """Hook-Signal fuer das eigene Herdr-Pane vermerken (#506).

    `input` (Prompt), `session` (`source` = SessionStart-Quelle), `activity`
    (`source` = pretooluse/notification/permission/session_end, als Feld `kind`;
    bei session_end zusaetzlich `reason` aus dem SessionEnd-Payload), `stop`.
    Basis aus `cwd` (Payload-`cwd`), sonst Prozess-cwd. Nur mit `HERDR_ENV == "1"`
    und gesetzter `HERDR_PANE_ID`; ohne Config-Zugriff, Subprozess oder Ausgabe.
    Jede Ausnahme wird verschluckt (fail-open).
    """
    try:
        if os.environ.get("HERDR_ENV") != "1":
            return
        located = _signal_path(os.environ.get("HERDR_PANE_ID", "").strip(), kind, cwd)
        if located is None:
            return
        data = {"at": time.time()}
        if kind == "session":
            data["source"] = source if isinstance(source, str) else None
        elif kind == "activity":
            data["kind"] = source if isinstance(source, str) else None
            if isinstance(reason, str):
                data["reason"] = reason[:40]
        from hook_utils import atomic_write_json
        atomic_write_json(located[0], data, root=located[1])
    except Exception:
        pass


SIGNAL_ACTIVITY_KINDS = {"Notification": "notification", "PermissionRequest": "permission",
                         "SessionEnd": "session_end"}


def run_signal(argv) -> int:
    """CLI `signal activity` (Notification/PermissionRequest/SessionEnd, #506); immer 0, still.

    Liest den Payload von stdin, Basis aus dessen `cwd`; `kind` aus
    `hook_event_name` (SessionEnd: `reason` mit, damit der Runner das Ende durch
    das eigene `/clear` erkennt). Ungueltiger Payload oder fehlende Pane-Id: nichts.
    """
    try:
        if list(argv) != ["activity"]:
            return 0
        if os.environ.get("HERDR_ENV") != "1" or not os.environ.get("HERDR_PANE_ID"):
            return 0
        payload = json.loads(sys.stdin.read() or "null")
        if not isinstance(payload, dict):
            return 0
        kind = SIGNAL_ACTIVITY_KINDS.get(payload.get("hook_event_name"), "notification")
        cwd = payload.get("cwd")
        reason = payload.get("reason") if kind == "session_end" else None
        record_signal("activity", kind, cwd=cwd if isinstance(cwd, str) else None,
                      reason=reason)
    except Exception:
        pass
    return 0


def read_signal(pane, kind: str) -> dict:
    """Marker lesen; fehlend, unlesbar oder kein Objekt -> {}."""
    try:
        located = _signal_path(pane, kind)
        if located is None:
            return {}
        from hook_utils import read_state_json
        data = read_state_json(located[0], located[1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _signal_at(data: dict) -> "float | None":
    at = data.get("at")
    if isinstance(at, (int, float)) and not isinstance(at, bool):
        return float(at)
    return None


def _parse_since(value, now: float) -> "float | None":
    """`--since` nur endlich, > 0 und hoechstens AC_SINCE_FUTURE_S in der Zukunft (#506).

    Sonst None (Runner-Start gilt): `nan` machte jeden Vergleich falsch, ein
    Zukunftswert jeden echten Marker "zu alt" — beides hebelte die Pruefung aus.
    """
    import math
    try:
        since = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(since) or since <= 0 or since > now + AC_SINCE_FUTURE_S:
        return None
    return since


class _Runner:
    def __init__(self, args):
        self.args = args
        self.binary = _binary()
        self.idle_timeout = max(0.0, float(args.idle_timeout))
        self.settle = max(0.0, float(args.settle))
        grace = max(0.0, float(args.grace))
        self.grace = grace
        # Referenz fuer "weitergemacht seit": Stop-Hook-Zeitpunkt `--since`, sonst
        # Runner-Start (#506); unbrauchbare Werte werden verworfen (Vermerk im Log)
        now = time.time()
        raw = getattr(args, "since", None)
        since = _parse_since(raw, now)
        self.since_note = None
        if since is None:
            self.since_note = ("--since fehlt" if raw is None
                               else f"--since {str(raw)[:40]!r} verworfen") + \
                ", Referenz ist der Runner-Start"
        self.since = since if since is not None else now
        # Gesamt-Deadline: eine Wartephase (SessionStart nach /clear), Delays, Prompts, Puffer
        budget = grace + 2 * self.settle + self.idle_timeout + 5 * AC_PROMPT_TIMEOUT + 20
        self.deadline = time.monotonic() + budget

    def _remaining(self) -> float:
        rest = self.deadline - time.monotonic()
        if rest <= 0:
            raise _Abort("Gesamt-Deadline ueberschritten")
        return rest

    def _sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(min(seconds, self._remaining()))

    def _call(self, argv, timeout: float):
        if self.binary is None:
            raise _Abort("HERDR_BIN_PATH ungueltig")
        try:
            return subprocess.run(
                [self.binary, *argv], stdin=subprocess.DEVNULL, capture_output=True,
                text=True, timeout=min(timeout, self._remaining()), close_fds=True)
        except subprocess.TimeoutExpired:
            raise _Abort(f"`{' '.join(argv[:2])}` Zeitlimit")

    def _announce(self) -> None:
        try:
            self._call(["notification", "show", "OpenSpec Auto-/clear",
                        "--body", f"In {self.grace:g}s: /clear, dann {self.args.command}"],
                       AC_PROMPT_TIMEOUT)
        except _Abort:
            raise
        except Exception:
            pass  # Vorankuendigung ist nur Hinweis

    def _check_activity(self, ref: float, label: str, own_clear: bool = False) -> None:
        """Eingabe, Aktivitaet oder weiterer Stop im eigenen Pane nach `ref` -> Abbruch.

        Ein Stop ist nicht zwingend das Turn-Ende (fremder Stop-Hook mit
        `decision: block`); jedes Hook-Signal danach heisst: nicht tippen (#506).
        Ebenso Sitzungsende (`activity` kind=session_end) und ein SessionStart mit
        `source != clear` (Claude im Pane neu gestartet/fortgesetzt, R2-F003).
        `own_clear`: nach dem eigenen `/clear` gehoert SessionEnd(reason=clear) dazu.
        """
        for kind in AC_CONTINUE_KINDS:
            data = read_signal(self.args.pane, kind)
            at = _signal_at(data)
            if at is None or at <= ref:
                continue
            if kind == "activity" and data.get("kind") == "session_end":
                if own_clear and data.get("reason") == "clear":
                    continue
                raise _Abort(f"{label}: Sitzung beendet (session_end {at - ref:+.1f}s)")
            why = "Nutzer hat weitergeschrieben" if kind == "input" else "Claude arbeitet weiter"
            raise _Abort(f"{label}: {why} ({kind} {at - ref:+.1f}s)")
        data = read_signal(self.args.pane, "session")
        at = _signal_at(data)
        if at is not None and at > ref and data.get("source") != "clear":
            raise _Abort(f"{label}: Sitzung neu gestartet "
                         f"(session {str(data.get('source'))[:20]} {at - ref:+.1f}s)")

    def _wait_session_clear(self, t_clear: float) -> None:
        """Bis `idle_timeout` auf SessionStart(clear) nach dem eigenen /clear warten.

        Je Poll auch Fortsetzungs-Signale nach `t_clear` + Toleranz pruefen (#506).
        """
        end = time.monotonic() + self.idle_timeout
        while True:
            self._check_activity(t_clear + AC_CLEAR_TOLERANCE_S, "nach /clear", own_clear=True)
            data = read_signal(self.args.pane, "session")
            at = _signal_at(data)
            if data.get("source") == "clear" and at is not None and at >= t_clear:
                return
            rest = end - time.monotonic()
            if rest <= 0:
                raise _Abort("nach /clear: kein SessionStart(clear)")
            self._sleep(min(AC_SIGNAL_POLL_S, rest))

    def _recheck(self, label: str) -> None:
        """Workflow noch in derselben Phase mit demselben erwarteten Befehl?"""
        _hooks_on_path()
        from hook_utils import find_project_root, read_state_json
        import workflow
        name = self.args.workflow
        try:
            root = find_project_root()
            data = read_state_json(root / ".claude" / "workflows" / f"{name}.json", root)
        except Exception as exc:
            raise _Abort(f"{label}: Workflow-State nicht lesbar ({type(exc).__name__})")
        if not isinstance(data, dict):
            raise _Abort(f"{label}: Workflow-State unbrauchbar")
        data.setdefault("name", name)
        if data.get("current_phase") != self.args.phase:
            raise _Abort(f"{label}: Phase gewechselt ({data.get('current_phase')})")
        if workflow.expected_footer_command(data) != self.args.command:
            raise _Abort(f"{label}: erwarteter Befehl geaendert")

    def _prompt(self, text: str, ref: float, label: str, own_clear: bool = False) -> None:
        """Text tippen und abschicken; Herdr nur als Tastatur (#506), ohne Retry.

        Kein `agent prompt`: das lehnt Herdr ab, sobald der Pane `blocked` ist.
        Zwischen Text und Enter erneut pruefen (R2-F002): kam inzwischen ein Signal,
        wird die Zeile per `ctrl+u` geloescht und nichts abgeschickt.
        """
        res = self._call(["pane", "send-text", self.args.pane, text], AC_PROMPT_TIMEOUT)
        if res.returncode != 0:
            raise _Abort(f"pane send-text {text!r} Exit {res.returncode}")
        try:
            self._check_activity(ref, label, own_clear=own_clear)
        except _Abort as exc:
            try:
                res = self._call(["pane", "send-keys", self.args.pane, AC_CLEAR_KEY],
                                 AC_PROMPT_TIMEOUT)
                note = "Zeile geloescht" if res.returncode == 0 else \
                    f"Zeile loeschen Exit {res.returncode}"
            except _Abort as inner:
                note = f"Zeile loeschen: {inner}"
            raise _Abort(f"{exc} [zwischen Text und Enter, {note}]")
        res = self._call(["pane", "send-keys", self.args.pane, "enter"], AC_PROMPT_TIMEOUT)
        if res.returncode != 0:
            raise _Abort(f"pane send-keys enter ({text!r}) Exit {res.returncode}")

    def run(self) -> None:
        if _command_name(self.args.command) in MANUAL_COMMANDS:
            raise _Abort("Workflow-Abschluss bleibt manuell")
        if str(self.args.announce).strip() not in ("0", "false", "False", ""):
            self._announce()
        if self.since_note:
            _ac_log(f"{self.args.workflow}|{self.args.phase}|{self.args.command}: "
                    f"Hinweis: {self.since_note}")
        self._sleep(self.grace)
        self._check_activity(self.since, "vor /clear")
        self._sleep(self.settle)
        self._recheck("vor /clear")
        self._check_activity(self.since, "vor /clear")  # unmittelbar vor dem Tippen
        t_clear = time.time()
        self._prompt("/clear", self.since, "vor /clear")
        self._wait_session_clear(t_clear)
        self._sleep(self.settle)
        self._recheck("vor Folgebefehl")
        after = t_clear + AC_CLEAR_TOLERANCE_S
        self._check_activity(after, "vor Folgebefehl", own_clear=True)
        # Vermerk/Log/Lock bleiben in Kurzform; nur der getippte Text folgt der Form (#499)
        self._prompt(resolve_command_form(self.args.command), after, "vor Folgebefehl",
                     own_clear=True)


def run_auto_clear(argv) -> int:
    """CLI `auto-clear`: Runner ausfuehren; immer 0, Abbruchgruende ins Log."""
    tag = "auto-clear"
    try:
        parser = argparse.ArgumentParser(prog="herdr_bridge.py auto-clear")
        parser.add_argument("--pane", required=True)
        parser.add_argument("--workflow", required=True)
        parser.add_argument("--phase", required=True)
        parser.add_argument("--command", required=True)
        parser.add_argument("--grace", type=float, default=AC_DEFAULTS["grace_s"])
        parser.add_argument("--settle", type=float, default=AC_SETTLE_S)
        parser.add_argument("--idle-timeout", type=float,
                            default=AC_DEFAULTS["idle_timeout_s"])
        parser.add_argument("--announce", default="1")
        # Stop-Hook-Epoch (#506); roh als Text, `_parse_since` prueft
        parser.add_argument("--since", default=None)
        try:
            args = parser.parse_args(argv)
        except SystemExit:
            _ac_log(f"{tag}: ABBRUCH: ungueltige Argumente")
            return 0
        tag = f"{args.workflow}|{args.phase}|{args.command}"
        _Runner(args).run()
        _ac_log(f"{tag}: OK: /clear und Folgebefehl gesendet")
    except _Abort as exc:
        _ac_log(f"{tag}: ABBRUCH: {exc}")
    except Exception as exc:
        _ac_log(f"{tag}: ABBRUCH: Fehler {type(exc).__name__}")
    return 0


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
        base = str(_ac_base())
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
    _ac_log(line, PP_LOG_FILE)


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
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "auto-clear":
            run_auto_clear(sys.argv[2:])
        elif len(sys.argv) > 1 and sys.argv[1] == "plan-pane":
            run_plan_pane(sys.argv[2:])
        elif len(sys.argv) > 1 and sys.argv[1] == "plan-pane-close":
            run_plan_pane_close()
        elif len(sys.argv) > 1 and sys.argv[1] == "signal":
            run_signal(sys.argv[2:])
    except BaseException:
        pass
    sys.exit(0)
