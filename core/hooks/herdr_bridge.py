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
"""

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
