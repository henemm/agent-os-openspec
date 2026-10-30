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
(`herdr_bridge.py auto-clear ...`), der per `agent wait`/`agent prompt` erst
`/clear` und dann den naechsten Workflow-Befehl in den Pane tippt. Der Runner
bricht bei jedem Zweifel ab, protokolliert den Grund in
`.claude/herdr_auto_clear.log` und endet immer mit Exit 0.

Plan-Pane (#476, Opt-out `herdr.plan_pane.enabled: false`): `workflow.py start`
ruft `open_plan_pane`, das den Runner `herdr_bridge.py plan-pane ...` detached
startet. Der Runner splittet den Claude-Pane nach rechts (`pane split`), benennt
den neuen Pane `Workflow` und tippt `workflow.py plan --watch` hinein. Lock
`.claude/herdr_plan_pane.lock`, gemerkte ID `.claude/herdr_plan_pane.json`,
Log `.claude/herdr_plan_pane.log`; immer Exit 0.

#478: session_banner ruft `open_plan_pane_for_active` (Pane nur bei aktivem
Workflow). `maybe_auto_clear` loggt bei aktivem Opt-in jeden Skip-Grund
(`skip: <grund>`, gleiche Zeile in Folge nur einmal); `_wait_ready` liest
`agent_status` (Herdr 0.9.5), Fallback `status`.
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
AC_DEFAULTS = {"grace_s": 3, "idle_timeout_s": 120, "announce": True}
AC_SETTLE_S = 2.0       # Wartezeit vor State-Recheck bzw. nach /clear
AC_PROMPT_TIMEOUT = 15  # Sekunden fuer `agent prompt`/`notification show`
AC_LOG_MAX_LINES = 200

POSITIVE_MARKER = "`/clear` ist jetzt gefahrlos"
NEGATIVE_MARKER = "`/clear` jetzt NICHT"
READY_STATES = ("idle", "done")


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


def _ac_base() -> Path:
    """Worktree-lokale Basis (Vorbild: footer_gate._state_path)."""
    _hooks_on_path()
    from hook_utils import _find_worktree_root, find_project_root
    try:
        wt = _find_worktree_root()
        if wt is not None:
            return wt
    except Exception:
        pass
    return find_project_root()


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
                     cfg: dict) -> bool:
    """Runner detached starten (kein Shell, eigene Session, DEVNULL); sofort zurueck."""
    try:
        argv = [sys.executable, str(Path(__file__).resolve()), "auto-clear",
                "--pane", pane, "--workflow", workflow_name, "--phase", phase,
                "--command", command,
                "--grace", str(cfg.get("grace_s", AC_DEFAULTS["grace_s"])),
                "--idle-timeout", str(cfg.get("idle_timeout_s", AC_DEFAULTS["idle_timeout_s"])),
                "--announce", "1" if cfg.get("announce", True) else "0"]
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


def maybe_auto_clear(payload, message, data) -> bool:
    """Trigger-Bedingungen (#467) in Spec-Reihenfolge; True = Runner gespawnt.

    Ausloeser ist der Grenz-Vermerk `auto_clear_boundary` (#495), nicht mehr der
    Positiv-Satz; der Negativ-Satz bleibt Veto.

    Fail-open: jede nicht erfuellte Bedingung oder Ausnahme = kein Spawn.
    """
    try:
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
        if not spawn_auto_clear(pane, name, phase, command, cfg):
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


class _Runner:
    def __init__(self, args):
        self.args = args
        self.binary = _binary()
        self.idle_timeout = max(0.0, float(args.idle_timeout))
        self.settle = max(0.0, float(args.settle))
        grace = max(0.0, float(args.grace))
        self.grace = grace
        # Gesamt-Deadline: zwei Wartephasen, Delays und Prompts plus Puffer
        budget = grace + 2 * self.settle + 2 * (self.idle_timeout + 10) + 3 * AC_PROMPT_TIMEOUT + 10
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

    def _wait_ready(self, label: str) -> None:
        timeout_ms = int(self.idle_timeout * 1000)
        res = self._call(["agent", "wait", self.args.pane, "--until", "idle",
                          "--until", "done", "--timeout", str(timeout_ms)],
                         self.idle_timeout + 10)
        if res.returncode != 0:
            raise _Abort(f"{label}: agent wait Exit {res.returncode} "
                         f"{(res.stderr or '').strip()[:200]}")
        # Herdr 0.9.5 liefert `agent_status`; `status` nur als Fallback (#478)
        try:
            agent = json.loads(res.stdout)["result"]["agent"]
            status = agent.get("agent_status")
            if not isinstance(status, str):
                status = agent.get("status")
        except Exception:
            status = None
        if not isinstance(status, str):
            raise _Abort(f"{label}: agent wait Ausgabe nicht parsbar")
        if status not in READY_STATES:
            raise _Abort(f"{label}: Agent-Status {status!r}")

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

    def _prompt(self, text: str) -> None:
        # Bewusst ohne --wait (sonst agent_prompt_stalled bei /clear) und ohne Retry.
        res = self._call(["agent", "prompt", self.args.pane, text], AC_PROMPT_TIMEOUT)
        if res.returncode != 0:
            raise _Abort(f"agent prompt {text!r} Exit {res.returncode}")

    def run(self) -> None:
        if str(self.args.announce).strip() not in ("0", "false", "False", ""):
            self._announce()
        self._sleep(self.grace)
        self._wait_ready("wait 1")
        self._sleep(self.settle)
        self._recheck("vor /clear")
        self._prompt("/clear")
        self._sleep(self.settle)
        self._wait_ready("wait 2")
        self._recheck("vor Folgebefehl")
        self._prompt(self.args.command)


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
    """SessionStart (#478): Plan-Pane nur bei aktivem Workflow oeffnen; fail-open."""
    try:
        if _pane() is None:
            return False
        _hooks_on_path()
        import workflow
        if not workflow.read_active_workflow_fast():
            return False
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


def _pp_known_pane(path: Path, claude_pane: str) -> "str | None":
    entry = _pp_entries(path).get(claude_pane)
    pane = entry.get("pane_id") if isinstance(entry, dict) else None
    return pane if isinstance(pane, str) and pane else None


def _pp_open(args) -> None:
    """Schritte 2–6 des Runners (Spec #476); Ergebnis jeweils ins Log."""
    import shlex
    binary = _binary()
    if binary is None:
        _pp_log("plan-pane: ABBRUCH: HERDR_BIN_PATH ungueltig")
        return
    id_file = _pp_store() / PP_ID_FILE
    known = _pp_known_pane(id_file, args.pane)
    if known:
        res = _pp_call(binary, ["pane", "get", known], 3)
        if res is not None and res.returncode == 0:
            # #493: Watcher folgt per --target der Basis der neuen Session
            _pp_set_entry(id_file, args.pane, {"pane_id": known, "cwd": args.cwd})
            _pp_log(f"plan-pane: {known} vorhanden")
            return
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
    _pp_call(binary, ["pane", "rename", new, PP_LABEL], 3)  # Fehler egal
    if args.delay > 0:
        time.sleep(args.delay)
    workflow_py = Path(__file__).resolve().parent / "workflow.py"
    command = (f"exec {shlex.quote(sys.executable)} "
               f"{shlex.quote(str(workflow_py))} plan --watch "
               f"--target {shlex.quote(args.pane)}")
    run = _pp_call(binary, ["pane", "run", new, command], 5)
    _pp_set_entry(id_file, args.pane, {"pane_id": new, "cwd": args.cwd})
    ok = run is not None and run.returncode == 0
    _pp_log(f"plan-pane: {new} geoeffnet, pane run {'OK' if ok else 'fehlgeschlagen'}")


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
    except BaseException:
        pass
    sys.exit(0)
