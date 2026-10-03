#!/usr/bin/env python3
"""
Post-Implementation Gate — PreToolUse Edit|Write|MultiEdit

Stellt sicher, dass der User die Implementierungsergebnisse begutachtet
bevor weitere Code-Änderungen erlaubt werden.

Ablauf:
1. Erster Code-Edit in phase6_implement → Lock-Datei erstellen (mit Timestamp)
2. Innerhalb von 15 Minuten → weitere Edits erlaubt (Batch-Fenster)
3. Nach 15 Minuten → BLOCKIERT bis User-Freigabe
4. User sagt eine GREEN-Phrase (Default "go", Config `workflow.green_phrases`)
   → phase_listener erstellt Approval-Marker
5. Approval-Marker vorhanden → entsperren + Lock löschen

Bypasses:
- Adversary-Phase (phase6b_adversary) → immer erlaubt
- Workflow abgeschlossen (phase7+) → immer erlaubt
- User-Override-Token → immer erlaubt (wird von edit_gate.py geprüft)
- Docs/Specs/Config-Dateien → immer erlaubt

Lock-Dateien:
  .claude/pending_validation_<workflow>.json
  .claude/user_approved_validation_<workflow>   (Marker, Inhalt = `created`-Zeitstempel
                                                 des Locks zum Zeitpunkt der Freigabe, #134)
"""

import json
import os
import re
import sys
import time
from pathlib import Path


def _setup():
    hooks_dir = str(Path(__file__).parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


_setup()

from hook_utils import get_tool_input, find_project_root, block, allow, get_active_workflow_name, framework_disabled  # noqa: E402
from hook_utils import (  # noqa: E402
    pending_validation_lock_path as _lock_path,
    read_pending_validation_lock as _read_lock,
    approval_marker_path as _approval_path,
    log_gate_event,
)

# Batch-Fenster: innerhalb dieser Zeit nach dem ersten Edit kein Gate
_DEFAULT_BATCH_WINDOW_S = 15 * 60  # 15 Minuten


def _batch_window_s(workflow: dict) -> int:
    """Fenster je Stufe aus `effort_budget.<Stufe>.batch_window_min` (#250 Teil B).

    Ohne Config, bei Kill-Switch oder Fehler: 15 Minuten (bisheriges Verhalten).
    """
    try:
        from config_loader import get_effort_budget
        budget = get_effort_budget((workflow or {}).get("workflow_type", "feature"))
        if budget:
            return int(float(budget["batch_window_min"]) * 60)
    except Exception:
        pass
    return _DEFAULT_BATCH_WINDOW_S

# Phasen in denen das Gate gilt
_GATED_PHASES = {"phase6_implement"}

# Phasen in denen das Gate explizit NICHT gilt (Adversary + alles danach)
_BYPASS_PHASES = {"phase6b_adversary", "phase7_validate", "phase8_complete", "phase0_idle"}

# Pfade die immer erlaubt sind
_ALWAYS_ALLOWED = re.compile(
    r"(\.claude[/\\]|[/\\]docs[/\\]|\.md$|\.gitignore|\.txt$|[/\\]specs[/\\]"
    r"|[/\\]\.claude[/\\])"
)


def _write_lock(lock_path: Path, wf_name: str, workflow_created) -> None:
    # workflow_created bindet den Lock an die Lauf-Instanz, nicht nur an den Namen (#134)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({
        "workflow": wf_name,
        "workflow_created": workflow_created,
        "created": time.time(),
        "created_iso": __import__("datetime").datetime.now().isoformat(),
    }, indent=2))


def _green_text() -> str:
    """Wirksame GREEN-Phrasen aus der Config (#268) — nie 'freigabe'/'approved',
    die in phase6 nicht wirken. Fallback hält das Gate auch bei Importfehler zu."""
    try:
        from phase_listener import green_phrases_text
        return green_phrases_text()
    except (Exception, SystemExit):
        return "'go'"


def _clear_lock(lock_path: Path, approval_path: Path) -> None:
    for p in (lock_path, approval_path):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> None:
    # Ohne Workflow gibt es keine Implementierungsphase, deren Ende ein
    # Review verlangen koennte (#132).
    if framework_disabled():
        allow()

    try:
        tool_input = get_tool_input()
    except Exception:
        allow()

    file_path = tool_input.get("file_path", "")

    # Docs, Configs, Specs immer erlaubt
    if _ALWAYS_ALLOWED.search(file_path):
        allow()

    # Workflow laden
    try:
        import workflow as _wf
        result = _wf.read_active_workflow_fast()
    except Exception:
        allow()

    if result is None:
        allow()

    wf_name, workflow = result
    current_phase = workflow.get("current_phase", "")

    # Bypass-Phasen: Gate gilt nicht
    if current_phase in _BYPASS_PHASES:
        allow()

    # Nicht in einer Gated-Phase → erlauben
    if current_phase not in _GATED_PHASES:
        allow()

    project_root = find_project_root()
    lock_path = _lock_path(project_root, wf_name)
    approval_path = _approval_path(project_root, wf_name)

    # Lock VOR der Marker-Prüfung lesen: der Marker gilt nur für genau diesen Lauf (#134)
    lock = _read_lock(lock_path)

    # Lock einer frueheren Lebensdauer eines gleichnamigen Workflows zaehlt nicht (#134)
    if lock is not None and lock.get("workflow_created") != workflow.get("created"):
        lock = None
        lock_path.unlink(missing_ok=True)
        log_gate_event(
            "post_implementation_gate", "Edit",
            f"Verworfener Lock einer fremden Workflow-Instanz "
            f"(Workflow-Name wiederverwendet: {wf_name}).",
        )

    if approval_path.exists():
        try:
            marker_content = approval_path.read_text().strip()
        except OSError:
            marker_content = None

        if lock is not None and marker_content == str(lock.get("created")):
            # Freigabe passt exakt zum aktuell lebenden Prüflauf
            _clear_lock(lock_path, approval_path)
            allow()
        elif lock is None:
            # Marker überlebte seinen Workflow — verwerfen, NICHT als Freigabe werten.
            # Fällt unten in den "kein Lock"-Zweig.
            approval_path.unlink(missing_ok=True)
            log_gate_event(
                "post_implementation_gate", "Edit",
                f"Verworfener Freigabe-Marker ohne aktiven Pruflauf-Lock (Workflow: {wf_name}).",
            )
        else:
            # Marker existiert, passt aber zu einem anderen (älteren) Lauf
            approval_path.unlink(missing_ok=True)
            block(
                f"BLOCKED [post_implementation_gate]: Freigabe-Marker passt nicht zum aktuellen "
                f"Pruflauf (Workflow: {wf_name}).\n"
                f"  Der Marker stammt von einem frueheren Lauf und gilt nicht mehr.\n"
                f"  Neue Freigabe noetig: User tippt {_green_text()}."
            )

    if lock is None:
        # Erster Code-Edit in dieser Phase → Lock anlegen, Batch-Fenster starten
        _write_lock(lock_path, wf_name, workflow.get("created"))
        allow()

    # Lock existiert → prüfen ob Batch-Fenster noch offen
    age_s = time.time() - lock.get("created", 0)
    window_s = _batch_window_s(workflow)

    if age_s <= window_s:
        # Noch im Batch-Fenster → erlauben
        remaining_min = (window_s - age_s) / 60
        # Optional: kurze Info-Nachricht (kein block, nur stderr-Info)
        print(
            f"[post_implementation_gate] Batch-Fenster: noch {remaining_min:.0f} Min.",
            file=sys.stderr,
        )
        allow()

    # Batch-Fenster abgelaufen → auf User-Freigabe warten
    elapsed_min = age_s / 60
    block(
        f"BLOCKED [post_implementation_gate]: Implementierung läuft seit {elapsed_min:.0f} Min.\n"
        f"  Workflow: {wf_name} · Phase: {current_phase}\n"
        f"\n"
        f"  Lege dem User jetzt die bisherigen Änderungen vor und WARTE.\n"
        f"\n"
        f"  Freigabe — und zwar AUSSCHLIESSLICH durch den User:\n"
        f"  Der User tippt {_green_text()}. Der phase_listener-Hook\n"
        f"  setzt den Freigabe-Marker dann selbst und legitim.\n"
        f"\n"
        f"  Du kannst dieses Gate NICHT selbst öffnen. Erzeuge den Marker niemals\n"
        f"  per Bash (touch/echo/…) — das ist eine blockierte Verifier-Manipulation.\n"
        f"  Danach ist der nächste Edit automatisch erlaubt."
    )


if __name__ == "__main__":
    main()
