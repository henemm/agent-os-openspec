#!/usr/bin/env python3
"""
Phase Listener v3 — Consolidated UserPromptSubmit Hook

Replaces 6 separate hooks with 1. Listens for keywords in user messages:

- "approved"/"freigabe"/"lgtm" → spec_approved = true
- "stop"/"stopp" → stop-lock enable
- "weiter"/"continue" → stop-lock disable
- "override"/"ich genehmige" → override token
- "neues ui" → is_new_ui = true
- "go"/"green ok"/"tests ok" → green_approved = true

Exit Codes: 0 always (never blocks, only updates state)
"""

from hook_utils import setup_path, find_project_root, get_user_message, get_active_workflow_name, gate_diagnostics, resolve_active_workflow
setup_path()

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

_root = find_project_root()

# --- Defaults (overridable via config.yaml) ---

APPROVAL_PHRASES = [
    "approved", "freigabe", "lgtm", "spec ok", "genehmigt",
    "abgenommen", "passt", "sieht gut aus",
]

STOP_PHRASES = ["stop", "stopp", "halt", "anhalten"]
CONTINUE_PHRASES = ["weiter", "continue", "weitermachen", "fortfahren", "resume"]
OVERRIDE_PHRASES = ["override", "ich genehmige", "genehmige", "ueberschreiben"]
GREEN_PHRASES = ["go", "green ok", "tests ok", "gruen ok"]

# Marker die AUSSCHLIESSLICH in harness-injizierten Turns vorkommen
# (Task-Notifications von Background-Agenten, System-Reminder, Bash-Input etc.),
# nie in echten User-Eingaben. Enthält ein Prompt einen dieser Marker, wird die
# gesamte Keyword-Erkennung für diesen Turn übersprungen (Issue #46,
# sicherheitsrelevant). Verhindert, dass eine bloße Erwähnung einer Freigabe-
# Phrase im Ergebnistext eines Agenten die Freigabe setzt.
NOTIFICATION_MARKERS = [
    "<task-notification>",
    "[SYSTEM NOTIFICATION",
    "<system-reminder>",
    "<bash-input>",
    "<local-command-caveat>",
]

# Position innerhalb derer freigabe-relevante Phrasen (approval/GREEN/override)
# stehen müssen: erste Zeile UND erste 120 Zeichen.
LEADING_CHARS = 120


# --- Config loading ---

def _load_phrases() -> dict:
    """Load configurable phrase lists from config.yaml."""
    try:
        from config_loader import load_config
        config = load_config()
        return {
            "approval": config.get("workflow", {}).get("approval_phrases", APPROVAL_PHRASES),
            "stop": config.get("stop_lock", {}).get("stop_keywords", STOP_PHRASES),
            "continue": config.get("stop_lock", {}).get("resume_keywords", CONTINUE_PHRASES),
            "override": config.get("override_token", {}).get("keywords", OVERRIDE_PHRASES),
        }
    except Exception:
        return {}


# --- Helpers ---

def _is_notification_turn(message: str) -> bool:
    """True, wenn der Prompt einen harness-injizierten Notification-Marker enthält.

    Diese Marker kommen nur in vom Harness erzeugten Turns vor (Task-Notifications,
    System-Reminder, Bash-Input). In solchen Turns wird JEGLICHE Keyword-Erkennung
    übersprungen — eine zitierte Freigabe-Phrase im Agenten-Ergebnistext darf keine
    echte User-Freigabe auslösen (Issue #46).
    """
    lower = message.lower()
    return any(marker.lower() in lower for marker in NOTIFICATION_MARKERS)


def _matches(message: str, phrases: list[str], leading_only: bool = False) -> bool:
    """Prüft, ob eine der Phrasen im Prompt vorkommt (mit Wortgrenzen).

    leading_only=True (für freigabe-relevante Sets approval/GREEN/override):
    Die Phrase muss innerhalb der ersten Zeile UND der ersten 120 Zeichen stehen.
    Echte User-Freigaben führen mit dem Stichwort; zitierte Erwähnungen in Agenten-/
    Meta-Texten stehen typischerweise tief im Text. Stop-Lock-Phrasen bleiben bewusst
    ohne diese Einschränkung (Not-Aus darf großzügig greifen).
    """
    msg = message.lower().strip()
    if leading_only:
        msg = msg.split("\n", 1)[0][:LEADING_CHARS]
    for phrase in phrases:
        # Require phrase not preceded or followed by a letter, digit, underscore, or
        # hyphen. Plain \b would match "stop" inside "stop-lock" because "-" is a
        # non-word character — that causes false positives when discussing the stop-lock
        # mechanism itself.
        pat = r"(?<![a-zA-Z0-9_\-])" + re.escape(phrase.lower()) + r"(?![a-zA-Z0-9_\-])"
        if re.search(pat, msg):
            return True
    return False


def _read_active_workflow() -> tuple[dict | None, Path | None]:
    """Read active workflow. Returns (data, file_path).

    Resolution is env/settings only (via get_active_workflow_name), which is
    session-scoped and prevents cross-session collisions when multiple Claude
    Code instances run in parallel. No symlink fallback is used (single source
    of truth, matching workflow.py).
    """
    env_name = get_active_workflow_name()
    if not env_name:
        return None, None
    wf_file = _root / ".claude" / "workflows" / f"{env_name}.json"
    if wf_file.exists():
        try:
            return json.loads(wf_file.read_text()), wf_file
        except (OSError, json.JSONDecodeError):
            pass
    return None, None


def _save_workflow(data: dict, path: Path) -> None:
    data["last_updated"] = datetime.now().isoformat()
    path.write_text(json.dumps(data, indent=2))


def _create_override_token(workflow_name: str) -> None:
    try:
        from override_token import create_token
        create_token(workflow_name)
    except ImportError:
        # Fallback: inline token creation
        token_file = _root / ".claude" / "user_override_token.json"
        tokens = {}
        if token_file.exists():
            try:
                raw = json.loads(token_file.read_text())
                tokens = raw.get("tokens", {}) if raw.get("version") == 2 else {}
            except (json.JSONDecodeError, OSError):
                pass
        tokens[workflow_name] = {
            "created": datetime.now().isoformat(),
            "granted_by": "user_prompt",
        }
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(json.dumps({"version": 2, "tokens": tokens}, indent=2))


def _stop_lock_path() -> Path:
    """Worktree-lokaler oder gemeinsamer Stop-Lock-Pfad."""
    try:
        from hook_utils import _find_worktree_root
        wt = _find_worktree_root()
        if wt is not None:
            return wt / ".claude" / "stop_lock.json"
    except Exception:
        pass
    return _root / ".claude" / "stop_lock.json"


def _set_stop_lock(enabled: bool) -> None:
    lock_file = _stop_lock_path()
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(json.dumps({"enabled": enabled}))


# --- Main ---

def main():
    message = get_user_message()
    if not message:
        sys.exit(0)

    # Verteidigung 1 (Issue #46): harness-injizierte Notification-Turns komplett
    # überspringen — bevor irgendeine Keyword-Verarbeitung stattfindet.
    if _is_notification_turn(message):
        sys.exit(0)

    phrases = _load_phrases()
    approval = phrases.get("approval", APPROVAL_PHRASES)
    stop = phrases.get("stop", STOP_PHRASES)
    cont = phrases.get("continue", CONTINUE_PHRASES)
    override = phrases.get("override", OVERRIDE_PHRASES)

    wf_data, wf_path = _read_active_workflow()

    # Override token (works even without workflow)
    if _matches(message, override, leading_only=True):
        wf_name = wf_data["name"] if wf_data else "__global__"
        _create_override_token(wf_name)
        print(f"Override token created for workflow: {wf_name}", file=sys.stderr)

    # Stop-lock
    if _matches(message, stop) and not _matches(message, cont):
        _set_stop_lock(True)
        print("Stop-lock enabled.", file=sys.stderr)
        sys.exit(0)

    if _matches(message, cont):
        _set_stop_lock(False)

    if not wf_data or not wf_path:
        if _matches(message, approval, leading_only=True) or _matches(message, GREEN_PHRASES, leading_only=True):
            print(
                f"WARNUNG: Stichwort erkannt, aber kein auflösbarer Workflow. {gate_diagnostics()}",
                file=sys.stderr,
            )
        sys.exit(0)

    changed = False

    # Approval
    if _matches(message, approval, leading_only=True):
        phase = wf_data.get("current_phase", "")
        if phase in ("phase3_spec",) and not wf_data.get("spec_approved"):
            wf_data["spec_approved"] = True
            try:
                from workflow import _log_phase_transition
                _log_phase_transition(wf_data, "phase4_approved")
            except Exception:
                pass
            wf_data["current_phase"] = "phase4_approved"
            changed = True
            print(f"Spec approved for '{wf_data['name']}'! You may now run /tdd-red", file=sys.stderr)

    # New UI flag
    if "neues ui" in message.lower() or "new ui" in message.lower():
        wf_data["is_new_ui"] = True
        changed = True

    # GREEN approval
    if _matches(message, GREEN_PHRASES, leading_only=True):
        phase = wf_data.get("current_phase", "")
        if phase in ("phase6_implement", "phase6b_adversary"):
            wf_data["green_approved"] = True
            changed = True
            print("GREEN approved.", file=sys.stderr)
            # Post-Implementation-Gate: Approval-Marker setzen damit post_implementation_gate entsperrt
            try:
                approval_path = _root / ".claude" / f"user_approved_validation_{wf_data['name']}"
                approval_path.parent.mkdir(parents=True, exist_ok=True)
                approval_path.touch()
                print(f"Post-implementation gate entsperrt für '{wf_data['name']}'.", file=sys.stderr)
            except OSError:
                pass

    if changed:
        _save_workflow(wf_data, wf_path)

    sys.exit(0)


if __name__ == "__main__":
    main()
