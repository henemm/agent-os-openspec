#!/usr/bin/env python3
"""
Post-Implementation Gate — PreToolUse Edit|Write|MultiEdit

Stellt sicher, dass der User die Implementierungsergebnisse begutachtet
bevor weitere Code-Änderungen erlaubt werden.

Ablauf:
1. Erster Code-Edit in phase6_implement → Lock-Datei erstellen (mit Timestamp)
2. Innerhalb von 15 Minuten → weitere Edits erlaubt (Batch-Fenster)
3. Nach 15 Minuten → BLOCKIERT bis User-Freigabe
4. User sagt "go" / "freigabe" / "approved" → phase_listener erstellt Approval-Marker
5. Approval-Marker vorhanden → entsperren + Lock löschen

Bypasses:
- Adversary-Phase (phase6b_adversary) → immer erlaubt
- Workflow abgeschlossen (phase7+) → immer erlaubt
- User-Override-Token → immer erlaubt (wird von edit_gate.py geprüft)
- Docs/Specs/Config-Dateien → immer erlaubt

Lock-Dateien:
  .claude/pending_validation_<workflow>.json
  .claude/user_approved_validation_<workflow>   (Marker, leer)
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

from hook_utils import get_tool_input, find_project_root, block, allow, get_active_workflow_name  # noqa: E402

# Batch-Fenster: innerhalb dieser Zeit nach dem ersten Edit kein Gate
_BATCH_WINDOW_S = 15 * 60  # 15 Minuten

# Phasen in denen das Gate gilt
_GATED_PHASES = {"phase6_implement"}

# Phasen in denen das Gate explizit NICHT gilt (Adversary + alles danach)
_BYPASS_PHASES = {"phase6b_adversary", "phase7_validate", "phase8_complete", "phase0_idle"}

# Pfade die immer erlaubt sind
_ALWAYS_ALLOWED = re.compile(
    r"(\.claude[/\\]|[/\\]docs[/\\]|\.md$|\.gitignore|\.txt$|[/\\]specs[/\\]"
    r"|[/\\]\.claude[/\\])"
)


def _lock_path(project_root: Path, wf_name: str) -> Path:
    return project_root / ".claude" / f"pending_validation_{wf_name}.json"


def _approval_path(project_root: Path, wf_name: str) -> Path:
    return project_root / ".claude" / f"user_approved_validation_{wf_name}"


def _read_lock(lock_path: Path) -> "dict | None":
    if not lock_path.exists():
        return None
    try:
        return json.loads(lock_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _write_lock(lock_path: Path, wf_name: str) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({
        "workflow": wf_name,
        "created": time.time(),
        "created_iso": __import__("datetime").datetime.now().isoformat(),
    }, indent=2))


def _clear_lock(lock_path: Path, approval_path: Path) -> None:
    for p in (lock_path, approval_path):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> None:
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

    # User-Freigabe vorhanden → entsperren + Locks löschen
    if approval_path.exists():
        _clear_lock(lock_path, approval_path)
        allow()

    lock = _read_lock(lock_path)

    if lock is None:
        # Erster Code-Edit in dieser Phase → Lock anlegen, Batch-Fenster starten
        _write_lock(lock_path, wf_name)
        allow()

    # Lock existiert → prüfen ob Batch-Fenster noch offen
    age_s = time.time() - lock.get("created", 0)

    if age_s <= _BATCH_WINDOW_S:
        # Noch im 15-Minuten-Fenster → erlauben
        remaining_min = (_BATCH_WINDOW_S - age_s) / 60
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
        f"  Bitte prüfe die bisherigen Änderungen bevor du weiterschreibst.\n"
        f"\n"
        f"  Freigabe-Optionen:\n"
        f"  A) Sage 'go', 'freigabe' oder 'approved' → Freigabe per Chat\n"
        f"  B) Bash: touch .claude/user_approved_validation_{wf_name}\n"
        f"\n"
        f"  Danach ist der nächste Edit automatisch erlaubt."
    )


if __name__ == "__main__":
    main()
