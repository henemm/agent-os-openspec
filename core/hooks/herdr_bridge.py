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
        nxt = "approved"  # Freitext-Schritt = Freigabe-Phrase
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
    """Strikter Opt-in: nur `herdr.auto_clear.enabled is True`; sonst None.

    Bewusst NICHT `_enabled()` (Opt-out) — ein fehlender Abschnitt oder ein
    anderer Wert als das Literal True bedeutet aus. Liefert die Werte mit
    Defaults fuer fehlende/unbrauchbare Eintraege.
    """
    try:
        _hooks_on_path()
        from config_loader import load_config
        section = (load_config() or {}).get("herdr")
        auto = section.get("auto_clear") if isinstance(section, dict) else None
        if not isinstance(auto, dict) or auto.get("enabled") is not True:
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
    """True nur bei `herdr.auto_clear.enabled: true` (Literal)."""
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

    Fail-open: jede nicht erfuellte Bedingung oder Ausnahme = kein Spawn.
    """
    try:
        pane = _pane()
        if pane is None:
            return False
        cfg = _auto_clear_config()
        if cfg is None:
            return False
        if isinstance(payload, dict) and payload.get("stop_hook_active") is True:
            return False
        if not isinstance(data, dict) or not isinstance(message, str):
            return False
        _hooks_on_path()
        import workflow
        command = workflow.expected_footer_command(data)
        if not isinstance(command, str) or not command.startswith("/"):
            return False  # Freitext-Schritt (Freigabe) loest nie aus
        first = command.split()[0]
        if first == "/clear":
            return False
        _, footer_commands = _footer_parts()
        if first not in footer_commands(message):
            return False
        if not has_clear_marker(message):
            return False
        name = str(data.get("name") or "")
        phase = str(data.get("current_phase") or "")
        if not name or not phase:
            return False
        key = f"{name}|{phase}|{command}"
        if not _acquire_lock(key):
            return False
        if not spawn_auto_clear(pane, name, phase, command, cfg):
            _release_lock(key)
            return False
        return True
    except Exception:
        return False


# --- Runner (eigener Prozess) ---

class _Abort(Exception):
    """Runner-Abbruch mit Grund; nach Abbruch wird nichts mehr gesendet."""


def _ac_log(line: str) -> None:
    """Zeile mit Zeitstempel an `.claude/herdr_auto_clear.log` haengen; fail-open."""
    try:
        from hook_utils import atomic_write_text, read_state_text
        path = _ac_base() / ".claude" / AC_LOG_FILE
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
        try:
            status = json.loads(res.stdout)["result"]["agent"]["status"]
        except Exception:
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


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "auto-clear":
            run_auto_clear(sys.argv[2:])
    except BaseException:
        pass
    sys.exit(0)
