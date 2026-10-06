#!/usr/bin/env python3
"""
Workflow v3 — Isolated State Manager

Each workflow gets its own JSON file in .claude/workflows/.
Active workflow tracked ONLY via OPENSPEC_ACTIVE_WORKFLOW env var.
The .active symlink fallback is intentionally disabled — using it causes
cross-session drift. Always set: export OPENSPEC_ACTIVE_WORKFLOW=<name>
Atomic writes via tempfile + rename (no file locks).

Usage:
    python3 workflow.py start <name> [--type feature|bug]
    python3 workflow.py switch <name>
    python3 workflow.py status
    python3 workflow.py phase <phase>
    python3 workflow.py phase-log
    python3 workflow.py set-field <key> <value>
    python3 workflow.py set-briefing <pfad-zum-po-briefing>
    python3 workflow.py set-affected-files [--replace] <f1> <f2> ...
    python3 workflow.py add-artifact <type> <path> <desc> <phase>
    python3 workflow.py mark-red <result>
    python3 workflow.py mark-ui-red <result>
    python3 workflow.py write-log [outcome]
    python3 workflow.py override-ambiguous <reason>
    python3 workflow.py finish
    python3 workflow.py abandon --reason "<warum kein Abschluss>"
    python3 workflow.py list
    python3 workflow.py sessions [--json]
    python3 workflow.py observable-surface
"""

from hook_utils import setup_path, find_project_root
setup_path()

import hashlib as _hashlib
import json
import os
import re as _re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

_NAME_RE = _re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

# Platzhalter fuer fehlende optionale Felder in Tabellenausgaben.
SESSIONS_PLACEHOLDER = "–"


def _worktree_root_if_any() -> "Path | None":
    """If CWD is inside a git worktree, return the worktree root (dir with .git FILE).

    Used to keep workflow state worktree-local and prevent cross-session contamination.
    Returns None if in the main repo (where .git is a directory, not a file).
    """
    current = Path.cwd()
    while current != current.parent:
        git_marker = current / ".git"
        if git_marker.is_file():
            return current
        if git_marker.is_dir():
            return None
        current = current.parent
    return None


def _worktree_first_root(rel: str) -> Path:
    """Root für versionierte Repo-Inhalte (Spec/Briefing): Worktree vor Hauptrepo.

    Anders als find_project_root() (Quelle für geteilten Workflow-State) muss
    hier der tatsächliche Arbeitsbaum gewinnen, wenn die Datei dort existiert
    (Vorbild: edit_gate.py:254). Existiert `rel` in keinem Worktree, bleibt
    find_project_root() der Fallback (Hauptrepo-Sessions, Regressionsfreiheit).
    """
    wt = _worktree_root_if_any()
    if wt is not None and (wt / rel).exists():
        return wt
    return find_project_root()


def _worktree_first_path(rel: str) -> Path:
    return _worktree_first_root(rel) / rel


def _validate_name(name: str) -> None:
    """Reject names that would escape the workflows dir or corrupt glob patterns."""
    if not _NAME_RE.fullmatch(name):
        print(
            f"INVALID workflow name: {name!r}\n"
            "Allowed: letters, digits, hyphens, underscores (1–64 chars).\n"
            "Rejected: / .. * ? [ ] { }",
            file=sys.stderr,
        )
        sys.exit(1)

PHASES = [
    "phase0_idle",
    "phase1_context",
    "phase2_analyse",
    "phase3_spec",
    "phase4_approved",
    "phase5_tdd_red",
    "phase6_implement",
    "phase6b_adversary",
    "phase7_validate",
    "phase8_complete",
]

PHASE_NAMES = {
    "phase0_idle": "Idle",
    "phase1_context": "Context Generation",
    "phase2_analyse": "Analysis",
    "phase3_spec": "Specification Writing",
    "phase4_approved": "Spec Approved",
    "phase5_tdd_red": "TDD RED - Write Failing Tests",
    "phase6_implement": "Implementation (TDD GREEN)",
    "phase6b_adversary": "Adversary Verification",
    "phase7_validate": "Validation",
    "phase8_complete": "Complete",
}

# Phasennummer fuer die PO-Anzeige ("Phase 7 von 8"). Bewusst eine eigene
# Tabelle statt PHASES.index(): die Liste enthaelt phase0_idle UND
# phase6b_adversary — index() wuerde phase7_validate als "Phase 8 von 8"
# ausweisen, also ausgerechnet den Zustand, der 3.25.0 ausgeloest hat, als
# fertig darstellen.
PHASE_NUMBERS = {
    "phase0_idle": 0,
    "phase1_context": 1,
    "phase2_analyse": 2,
    "phase3_spec": 3,
    "phase4_approved": 4,
    "phase5_tdd_red": 5,
    "phase6_implement": 6,
    "phase6b_adversary": 6,
    "phase7_validate": 7,
    "phase8_complete": 8,
}

TOTAL_PHASES = 8

# Der Befehl, der die jeweilige Phase weitertreibt. Quelle ist nicht das
# Diagramm, sondern wer die Folgephase schreibt
# (`grep "workflow.py phase phase" core/commands/*.md`): 40-tdd-red setzt am
# Ende phase6_implement, 50-implement am Ende phase7_validate, 60-validate am
# Ende phase8_complete. Wer in Phase X steht, hat also den Befehl offen, der
# X verlaesst.
NEXT_STEP = {
    "phase0_idle": "/00-intake",
    "phase1_context": "/10-context",
    "phase2_analyse": "/20-analyse",
    "phase3_spec": "/30-write-spec",
    "phase4_approved": "/40-tdd-red",
    "phase5_tdd_red": "/40-tdd-red",
    "phase6_implement": "/50-implement",
    "phase6b_adversary": "/50-implement",
    "phase7_validate": "/60-validate",
    "phase8_complete": None,
}

STATUS_NOTE_PREFIX = "[agent-os-openspec]"


def next_step(data: dict) -> "str | None":
    """Naechster Pflicht-Schritt fuer den Zustand, oder None (Phase 8 / unklar).

    Zwei Phasen sind nicht allein aus `current_phase` bestimmt:
    - phase3_spec deckt Spec schreiben UND auf Freigabe warten ab; liegt eine
      Spec-Datei vor, ist der offene Schritt das Freigabewort, kein Befehl.
    - phase5_tdd_red bleibt stehen, bis /40-tdd-red am Ende phase6_implement
      setzt; sind die RED-Tests laut State fertig, ist /50-implement faellig.
    """
    if not isinstance(data, dict):
        return None
    phase = data.get("current_phase")
    if not isinstance(phase, str) or phase not in NEXT_STEP:
        return None
    if phase == "phase3_spec" and data.get("spec_file"):
        return "Freigabe der Spec (Stichwort: approved)"
    if phase == "phase5_tdd_red" and (
        data.get("red_test_done") or data.get("ui_test_red_done")
    ):
        return "/50-implement"
    return NEXT_STEP[phase]


def issue_number(workflow_name: str) -> "str | None":
    """Erste Ziffernfolge im Workflow-Namen (fix-1761-xyz -> '1761')."""
    match = _re.search(r"\d+", workflow_name or "")
    return match.group(0) if match else None


def expected_footer_command(data: dict) -> "str | None":
    """Erwarteter Fusszeilen-Befehl — dieselbe Quelle wie status_note() (#234).

    Duenne Huelle um next_step() + issue_number(), damit footer_gate.py die
    Fusszeile gegen genau den Wert prueft, den status_note() ansagt. Keine
    eigene Logik: None und Freitext-Schritte werden unveraendert
    durchgereicht.
    """
    step = next_step(data)
    if not step or not step.startswith("/"):
        return step  # None oder Freitext-Schritt (z.B. "Freigabe der Spec ...")
    issue = issue_number((data or {}).get("name", ""))
    return f"{step} #{issue}" if issue else step


def status_note(data: dict) -> "str | None":
    """Statusvermerk fuer den UserPromptSubmit-Hook, oder None.

    None heisst: nichts anhaengen — kein Workflow, Phase 8, oder State
    unbrauchbar. Der Vermerk ist die einzige Stelle, die Claude auch in frei
    formulierten Nachrichten NACH dem Ende einer Phase (Loop-Aufwachen,
    Zwischenfragen) daran erinnert, dass ein Pflicht-Schritt offen ist.
    """
    if not isinstance(data, dict):
        return None
    name = data.get("name")
    if not isinstance(name, str) or not name:
        return None
    phase = data.get("current_phase")
    if not isinstance(phase, str) or phase not in PHASE_NUMBERS:
        return None
    if phase == "phase8_complete":
        return None
    step = next_step(data)
    if not step:
        return None
    if step.startswith("/"):
        issue = issue_number(name)
        if issue:
            step = f"{step} #{issue}"
    return (
        f"{STATUS_NOTE_PREFIX} AKTIVER WORKFLOW {name} · "
        f"Phase {PHASE_NUMBERS[phase]} von {TOTAL_PHASES} ({phase}) · "
        f"Nächster Pflicht-Schritt: {step}\n"
        "Nenne diesen Schritt in jeder Arbeitsstandsmeldung als Pflicht — nie als "
        "„bei Bedarf“ oder „optional“; Empfehlungen zu /clear oder Token-Kosten "
        "stehen nie darüber.\n"
        "Kennzeichne für den PO, wer am Zug ist, mit GENAU EINER Zeile ganz am Ende "
        "der Nachricht — nie zusätzlich mitten im Fließtext: „❗ Du: <Schritt>“, "
        "wenn der PO ihn tippen oder entscheiden muss. Das gilt AUCH, wenn du "
        "selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl "
        "des PO wartest — das ist niemals „nichts zu tun“. „ℹ️ Nichts zu tun: "
        "<du arbeitest gerade selbst / wartest auf ein Ergebnis, z. B. einen "
        "Hintergrund-Agenten> — danach: <Schritt>“ gilt ausschließlich, wenn du "
        "auf etwas ANDERES als den PO wartest.\n"
        "Hast DU SELBST in dieser Nachricht per `workflow.py phase <x>` (oder "
        "`complete`) die Phase gewechselt, ist dieser Hinweis hier noch der ALTE "
        "Stand von Turn-Beginn — nutze für Schritt und Phase in der Fußzeile "
        "trotzdem den NEUEN, von dir selbst herbeigeführten Stand. Die "
        "Marker-Zeilen entfallen NIE aus diesem Grund.\n"
        "❗/ℹ️/⚙ erscheinen AUSSCHLIESSLICH in den hier und in den "
        "Command-Vorlagen fest vorgeschriebenen Zeilen. Erfinde keine "
        "weiteren Zeilen mit diesen oder anderen Emojis (z. B. eine eigene "
        "„ℹ️ Status: ...“-Zusammenfassung) — Statusrekaps im Fließtext bleiben "
        "Emoji-frei.\n"
        "„fertig“/„abgeschlossen“/„erledigt“ gilt für den Workflow erst ab "
        "phase8_complete."
    )


# Phases where user keywords ("approved", "go", "deployed") are expected.
# Switching away from these without updating OPENSPEC_ACTIVE_WORKFLOW causes
# the next keyword to land on the wrong workflow.
KEYWORD_SENSITIVE_PHASES = {"phase3_spec", "phase6_implement", "phase7_validate"}

VALID_ARTIFACT_TYPES = [
    "screenshot", "email", "api_response", "log", "file", "test_output", "video", "audio",
    "adversary_dialog",
]


def _workflows_dir() -> Path:
    return find_project_root() / ".claude" / "workflows"


def _active_link() -> Path:
    return _workflows_dir() / ".active"


def _workflow_file(name: str) -> Path:
    return _workflows_dir() / f"{name}.json"


def _archive_dir() -> Path:
    return _workflows_dir() / "_archive"


# Compatibility aliases for project hooks that used the old project-local workflow.py API
_get_workflows_root = _workflows_dir


def _archive_file(name: str) -> Path:
    return _archive_dir() / f"{name}.json"


def _read_workflow_file(path: "Path") -> dict:
    return _read_workflow(path)


def _active_name() -> "str | None":
    """Return active workflow name from env var, or None (non-fatal).

    Compatibility alias: old project-local workflow.py returned None instead
    of calling sys.exit(1) when no workflow was active.
    """
    name = _active_name_from_env()
    return name if name else None


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically via tempfile + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_workflow(path: Path) -> dict:
    return json.loads(path.read_text())


def _active_name_from_env() -> str:
    """Return workflow name from OPENSPEC_ACTIVE_WORKFLOW env var, or empty string."""
    return os.environ.get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()


def _read_active() -> tuple[dict, str]:
    """Read the active workflow. Returns (data, name).

    Workflow-name resolution is delegated to hook_utils.resolve_active_workflow()
    — the single source of truth with worktree-aware priority (worktree-local
    active_workflow file > worktree settings.local.json > OPENSPEC_ACTIVE_WORKFLOW
    env var, each validated where applicable). This fixes the live bug (Issue #13)
    where the old FATAL path read the env var first and crashed when a stale env
    value pointed at a non-existent workflow, even though the worktree-local file
    and settings.local.json correctly pointed at a valid workflow.

    The resolved name is validated against the concrete workflows/<name>.json.
    The .active symlink fallback is intentionally removed (causes cross-session drift).
    """
    from hook_utils import resolve_active_workflow

    name, source = resolve_active_workflow()

    if name:
        wf_file = _workflow_file(name)
        if wf_file.exists():
            data = _read_workflow(wf_file)
            return data, data.get("name", wf_file.stem)
        print(
            f"FATAL: Resolved active workflow '{name}' (source={source}) but no "
            f"matching workflow file exists.\n"
            f"  The name may come from the worktree active_workflow file, "
            f"settings.local.json, or the OPENSPEC_ACTIVE_WORKFLOW env var.\n"
            f"  Run: python3 .claude/hooks/workflow.py list",
            file=sys.stderr,
        )
        sys.exit(1)

    # Symlink fallback is DISABLED. If a stale .active symlink exists, tell the user
    # what to do instead of silently using it — but ONLY if the target still
    # exists as an active workflow. After complete/abandon is "no active
    # workflow" the WANTED state (Issue #82): no FATAL, and never suggest
    # re-activating the workflow that was just archived.
    link = _active_link()
    if link.is_symlink():
        target = Path(os.readlink(str(link)))
        name = target.stem
        if _workflow_file(name).exists():
            print(
                f"No active workflow set.\n"
                f"  A .active symlink points to '{name}', but symlink fallback is disabled.\n"
                f"  Run: python3 .claude/hooks/workflow.py switch {name}",
                file=sys.stderr,
            )
            sys.exit(1)

    print("No active workflow. Run: python3 .claude/hooks/workflow.py start <name>", file=sys.stderr)
    sys.exit(1)


def read_active_workflow_fast() -> "tuple[str, dict] | None":
    """Return (name, data) for the active workflow, or None if no workflow is active.

    Unlike _read_active(), this never calls sys.exit(). Intended for hooks that
    should silently skip when no workflow is running.

    Thin wrapper around hook_utils.resolve_active_workflow() (the single source of
    truth for worktree-aware name resolution) plus the workflows/<name>.json
    existence check. Return contract is unchanged: (name, data) or None.
    """
    from hook_utils import resolve_active_workflow

    name, _source = resolve_active_workflow()
    if name:
        wf_file = _workflow_file(name)
        if wf_file.exists():
            data = _read_workflow(wf_file)
            return data.get("name", wf_file.stem), data
    return None


def _set_active(name: str) -> None:
    """Set .active symlink and persist OPENSPEC_ACTIVE_WORKFLOW in settings.local.json.

    Hook subprocesses inherit Claude Code's process environment, not individual Bash
    exports. Writing to settings.local.json ensures all hooks see the correct workflow.
    """
    link = _active_link()
    target = f"{name}.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    os.symlink(target, str(link))
    _persist_env(name)


def _persist_env(name: "str | None") -> None:
    """Write (or remove) OPENSPEC_ACTIVE_WORKFLOW to session-local storage.

    Worktree-aware: when called from a worktree session, writes ONLY to the worktree's
    own .claude/settings.local.json and active_workflow file. This prevents one session's
    workflow from contaminating new sessions that open in the main repo — each session
    starts with a clean slate and only inherits workflows from its own worktree.

    When called from the main repo (not a worktree), writes to the main repo's
    settings.local.json (backward compat for single-session projects).

    On completion (name=None) from a worktree: also clears the main repo's settings to
    avoid stale state if the main settings.local.json was set before isolation was in place.
    """
    project_root = find_project_root()
    worktree_root = _worktree_root_if_any()

    if worktree_root is not None:
        # Worktree session: write ONLY to this worktree's own .claude/
        targets = [worktree_root / ".claude" / "settings.local.json"]
        active_file = worktree_root / ".claude" / "active_workflow"

        if not name:
            # On complete: also clear the shared main repo locations so future
            # main-repo sessions start clean (handles pre-isolation contamination).
            _clear_shared_env(project_root)
    else:
        # Main repo: write to main locations (single-session backward compat)
        targets = [project_root / ".claude" / "settings.local.json"]
        active_file = project_root / ".claude" / "active_workflow"

    for settings_path in targets:
        try:
            settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
        except (json.JSONDecodeError, OSError):
            settings = {}

        env = settings.setdefault("env", {})
        if name:
            env["OPENSPEC_ACTIVE_WORKFLOW"] = name
        else:
            env.pop("OPENSPEC_ACTIVE_WORKFLOW", None)
            if not env:
                settings.pop("env", None)

        settings_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(settings_path, settings)

    if name:
        active_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(active_file.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(name)
            os.rename(tmp, str(active_file))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    else:
        try:
            active_file.unlink(missing_ok=True)
        except OSError:
            pass


def _clear_shared_env(project_root: Path) -> None:
    """Remove OPENSPEC_ACTIVE_WORKFLOW from the main repo's shared locations.

    Called by _persist_env(None) from a worktree to ensure cleanup propagates
    to the main repo's settings.local.json (handles pre-isolation contamination).
    """
    settings_path = project_root / ".claude" / "settings.local.json"
    try:
        settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
        env = settings.get("env", {})
        if "OPENSPEC_ACTIVE_WORKFLOW" in env:
            env.pop("OPENSPEC_ACTIVE_WORKFLOW")
            if not env:
                settings.pop("env", None)
            _atomic_write(settings_path, settings)
    except (OSError, json.JSONDecodeError):
        pass
    active_file = project_root / ".claude" / "active_workflow"
    try:
        active_file.unlink(missing_ok=True)
    except OSError:
        pass


def _save_active(data: dict) -> None:
    name = data["name"]
    data["last_updated"] = datetime.now().isoformat()
    _atomic_write(_workflow_file(name), data)


def _new_workflow(name: str) -> dict:
    return {
        "name": name,
        "workflow_type": "feature",
        "current_phase": "phase1_context",
        "created": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "spec_file": None,
        "spec_approved": False,
        "context_file": None,
        "affected_files": [],
        "test_artifacts": [],
        "is_new_ui": False,
        "red_test_done": False,
        "ui_test_red_done": False,
        "green_approved": False,
        "adversary_verdict": None,
        "phase_transitions": [],
        "fix_loop_iterations": 0,
        "phase_log": [],
    }


def _log_phase_transition(data: dict, new_phase: str) -> None:
    """Record phase transition timestamp in phase_log.

    Call BEFORE setting data['current_phase']. Closes the current log entry
    (sets exited_at + duration_min) and opens a new one for new_phase.
    """
    now = datetime.now().isoformat()
    log = data.setdefault("phase_log", [])
    if log:
        last = log[-1]
        if last.get("exited_at") is None:
            last["exited_at"] = now
            try:
                entered = datetime.fromisoformat(last["entered_at"])
                exited = datetime.fromisoformat(now)
                last["duration_min"] = round((exited - entered).total_seconds() / 60, 1)
            except (ValueError, KeyError):
                pass
    log.append({"phase": new_phase, "entered_at": now, "exited_at": None, "duration_min": None})


def effort_budget_exceeded(data: dict, budget: "dict | None") -> list:
    """Ueberschrittene Metriken des Stufen-Budgets (Issue #250, Teil B). Reine Funktion.

    `fix_loops` = `fix_loop_iterations`; `phase_reentries` = hoechster Wiedereintritts-
    zaehler je Phase (Eintraege in `phase_transitions` mit `to == Phase`, minus 1).
    Ueberschritten heisst strikt groesser als die Grenze.
    """
    if not budget:
        return []
    entries: dict = {}
    for t in data.get("phase_transitions", []) or []:
        to = t.get("to") if isinstance(t, dict) else None
        if to:
            entries[to] = entries.get(to, 0) + 1
    values = {
        "fix_loops": int(data.get("fix_loop_iterations", 0) or 0),
        "phase_reentries": max([n - 1 for n in entries.values()] or [0]),
    }
    exceeded = []
    for metric, key in (("fix_loops", "max_fix_loops"), ("phase_reentries", "max_phase_reentries")):
        limit = budget.get(key)
        if isinstance(limit, int) and values[metric] > limit:
            exceeded.append({"metric": metric, "value": values[metric], "limit": limit})
    return exceeded


def _record_budget_events(data: dict) -> list:
    """Neue Budget-Ueberschreitungen (je Metrik+Wert einmal) ablegen und protokollieren."""
    try:
        from config_loader import get_effort_budget
        stage = data.get("workflow_type") or "feature"
        exceeded = effort_budget_exceeded(data, get_effort_budget(stage))
    except Exception:
        return []  # Budget darf einen Phasenwechsel nie stoeren
    known = {(e.get("metric"), e.get("value")) for e in data.get("budget_events", [])}
    new = [e for e in exceeded if (e["metric"], e["value"]) not in known]
    for event in new:
        event["stage"] = stage
        event["at"] = datetime.now().isoformat()
        data.setdefault("budget_events", []).append(event)
        try:
            from hook_utils import log_gate_event
            log_gate_event(
                "effort_budget", "workflow",
                f"Stufe {stage}: {event['metric']} {event['value']} > Grenze {event['limit']}",
            )
        except Exception:
            pass
    return new


def record_transition(data: dict, target: str, trigger: str = "command") -> list:
    """Einen Phasenwechsel vollstaendig protokollieren: `phase_transitions` UND `phase_log`.

    Die EINZIGE Stelle, die einen Phasen-WECHSEL aufzeichnet — jeder Aufrufer muss sie
    benutzen (Issue #111). Ausnahme ist `cmd_start`: die Startphase wird nicht betreten,
    sie ist der Ausgangspunkt und hat kein `from`; dort ist der direkte
    `_log_phase_transition()`-Aufruf korrekt.

    Vorher haengte nur `cmd_phase` an `phase_transitions` an, waehrend der Freigabe-Pfad im
    `phase_listener` ausschliesslich `_log_phase_transition()` rief. `phase_transitions` war
    dadurch je nach Uebergangsart unterschiedlich vollstaendig.

    Aufruf BEVOR `data['current_phase']` gesetzt wird — die Ausgangsphase wird von hier
    gelesen. Setzt `current_phase` bewusst NICHT selbst, damit Aufrufer mit Zusatzlogik
    (Fix-Loop-Zaehler, Gate-Pruefungen) die Reihenfolge behalten.

    Gibt neue Ueberschreitungen des Stufen-Budgets zurueck (Issue #250, Teil B); der
    Wechsel wird dadurch nie verweigert.
    """
    data.setdefault("phase_transitions", []).append({
        "from": data.get("current_phase", "phase0_idle"),
        "to": target,
        "at": datetime.now().isoformat(),
        "trigger": trigger,
    })
    _log_phase_transition(data, target)
    return _record_budget_events(data)


# --- ADR Reflection Gate ---

def _check_adr(data: dict) -> "str | None":
    """Enforce a filled '## Architektur-Entscheidung (ADR)' section at spec approval.

    Returns an error message if the spec has an ADR section that is not filled
    (no ADR number and no justified 'keine'/'none'), otherwise None. Lenient by
    design: the hook must never break — missing config, missing/unreadable spec,
    or a missing ADR section all return None (grandfathering).
    """
    # 1. Kill-switch — only an explicit enabled: False disables the gate.
    try:
        from config_loader import load_config
        config = load_config()
        adr_cfg = config.get("adr_gate", {}) if isinstance(config, dict) else {}
        if isinstance(adr_cfg, dict) and adr_cfg.get("enabled") is False:
            return None
    except Exception:
        pass  # Config load failure → feature stays ON (lenient)

    # 2. Spec path
    spec_file = data.get("spec_file")
    if not spec_file:
        return None
    spec_path = _worktree_first_path(spec_file)

    # 3. Read
    try:
        content = spec_path.read_text()
    except Exception:
        return None

    return check_adr_content(content)


def check_adr_content(content: str) -> "str | None":
    """Prüft den Spec-TEXT auf eine ausgefüllte ADR-Sektion. Meldung oder None.

    Aus `_check_adr` herausgelöst, damit das CI-Gate (scripts/ci_spec_gate.py)
    exakt dieselbe Regel anwendet wie der lokale Hook — eine Regel, zwei Aufrufer.
    Grandfathering (keine ADR-Sektion → None) bleibt Teil dieser Funktion.
    """
    # 4. Extract the ADR section body (case-insensitive heading match).
    #    Accept ## or ### headings; body reaches up to the next heading of ANY
    #    rank 1-3 (#, ## or ###) or end of file. The end-lookahead must stop at
    #    #-level H1 too, otherwise an unrelated '**ADR-Nr.:**' line under a later
    #    H1 heading (e.g. '# Anhang') leaks into the section and falsely passes
    #    the gate even though the real ADR section is empty (F003).
    match = _re.search(
        r"^#{2,3}\s*Architektur-Entscheidung\s*\(ADR\)\s*$(.*?)(?=^#{1,3}\s|\Z)",
        content,
        _re.IGNORECASE | _re.MULTILINE | _re.DOTALL,
    )
    if not match:
        return None  # Grandfathering: no ADR section → not blocked
    body = match.group(1)

    # 5. Extract ONLY the value of the '**ADR-Nr.:**' bullet line (tolerate small
    #    format variants: bullet/dash optional, colon inside or outside the **).
    #    Intra-line whitespace only ([ \t]*, never \s*): a \s* after the closing
    #    ** would eat the newline and capture the following Rationale line when the
    #    value is empty (F001).
    nr_match = _re.search(
        r"(?im)^[ \t]*[-*]?[ \t]*\*\*[ \t]*ADR-Nr\.?[ \t]*:?[ \t]*\*\*[ \t]*:?[ \t]*(.*)$",
        body,
    )
    if not nr_match:
        # Section present but without the canonical '**ADR-Nr.:**' field →
        # treat as not filled (the canonical template always emits this line).
        return (
            "Spec ohne ausgefülltes ADR-Feld — Sektion "
            "'## Architektur-Entscheidung (ADR)' braucht ADR-Nr. oder begründetes 'keine'."
        )
    value = nr_match.group(1)

    # 6. Strip bracket placeholders from the value, then apply the criterion ONLY
    #    to that value (never to the free-form Rationale prose).
    v = _re.sub(r"\[[^\]]*\]", "", value).lower()
    if _re.search(r"adr-\d+", v) or _re.search(r"\bkeine\b|\bnone\b", v):
        return None

    # 7. Not filled
    return (
        "Spec ohne ausgefülltes ADR-Feld — Sektion "
        "'## Architektur-Entscheidung (ADR)' braucht ADR-Nr. oder begründetes 'keine'."
    )


# --- PO-Briefing-Gate (unabhängiges Freigabe-Briefing vor Phase 4) ---------

# Pflicht-Abschnitte des Briefings. Die Freigabe-Frage "passt das so?" ist nur
# beantwortbar, wenn alle vier beantwortet sind — was gebaut wird, wann es
# fertig ist, wie das geprüft wird, und was daran fragwürdig ist.
# Je Eintrag: (kanonischer Name für Meldungen, Regex für die Überschrift).
# Umlaute bewusst tolerant ('geprüft'/'geprueft'): ein Gate, das an der
# Schreibweise eines Umlauts scheitert, blockt den Nutzer aus einem Grund, der
# mit der Sache nichts zu tun hat.
PO_BRIEFING_SECTIONS = (
    ("Was gebaut wird", r"Was\s+gebaut\s+wird"),
    ("Definition of Done", r"(?:Definition\s+of\s+Done|DoD)"),
    ("Wie geprüft wird", r"Wie\s+gepr(?:ü|ue)ft\s+wird"),
    ("Kritische Anmerkungen", r"Kritische\s+Anmerkungen"),
)

# Mindest-Textlänge je Abschnitt (Zeichen, ohne Rahmen). Ein Abschnitt darunter
# ist eine Überschrift ohne Aussage.
_PO_BRIEFING_MIN_BODY = 20

_PO_BRIEFING_PLACEHOLDERS = ("[todo", "[tbd", "todo:", "fixme:", "xxx:", "<platzhalter")

# Obergrenze für die Wortzahl (Pflicht-Abschnitte + Freigabe-Frage). Der
# po-briefer zielt auf ≤ 120 Wörter; 150 lässt Puffer, damit das Gate nicht an
# einem Wort zu viel scheitert. Konfigurierbar: po_briefing_gate.max_words.
_PO_BRIEFING_MAX_WORDS = 150

# Optionaler Abschnitt, der mitgezählt wird, wenn vorhanden. Fehlt er, zählt er
# 0 Wörter — Vollständigkeit prüfen die Pflicht-Abschnitte, nicht dieser.
_PO_BRIEFING_QUESTION = r"Freigabe-?\s*Frage"


def spec_sha256(content: str) -> str:
    """SHA-256 des Spec-Inhalts — bindet ein Briefing an genau diese Spec-Fassung."""
    return _hashlib.sha256(content.encode("utf-8")).hexdigest()


def _read_spec_content(data: dict) -> "str | None":
    spec_file = data.get("spec_file")
    if not spec_file:
        return None
    try:
        return _worktree_first_path(spec_file).read_text()
    except Exception:
        return None


def _briefing_section_body(content: str, pattern: str) -> "str | None":
    """Rohtext eines Briefing-Abschnitts oder None, wenn die Überschrift fehlt.

    Überschrift ## oder ###, Zusatztext dahinter erlaubt ("## Definition of
    Done (DoD)"). Body reicht bis zur nächsten Überschrift Rang 1-3 oder EOF.
    """
    match = _re.search(
        r"^#{2,3}\s*" + pattern + r"[^\n]*$(.*?)(?=^#{1,3}\s|\Z)",
        content,
        _re.IGNORECASE | _re.MULTILINE | _re.DOTALL,
    )
    return match.group(1) if match else None


def count_briefing_words(content: str) -> int:
    """Wörter in den Pflicht-Abschnitten + Freigabe-Frage (falls vorhanden).

    Titel, Meta-Zeilen (Spec/Issue/Datum) und Frontmatter zählen nicht — der
    PO liest sie nicht als Inhalt. Als Wort gilt jedes Leerzeichen-getrennte
    Token mit mindestens einem Buchstaben oder einer Ziffer; Aufzählungszeichen
    und Gedankenstriche zählen also nicht.
    """
    patterns = [pattern for _, pattern in PO_BRIEFING_SECTIONS] + [_PO_BRIEFING_QUESTION]
    total = 0
    for pattern in patterns:
        body = _briefing_section_body(content, pattern)
        if body:
            total += sum(1 for tok in body.split() if _re.search(r"\w", tok))
    return total


def check_briefing_content(content: str, max_words: "int | None" = None) -> "str | None":
    """Prüft den Briefing-TEXT auf Vollständigkeit und Länge. Fehlermeldung oder None.

    Bewusst rein textuell und ohne Workflow-Bezug, damit `set-briefing` (bei der
    Registrierung) und das Gate (bei der Freigabe) exakt dasselbe prüfen.
    `max_words` kommt von konfigurationskundigen Aufrufern
    (po_briefing_gate.max_words); ohne Angabe gilt `_PO_BRIEFING_MAX_WORDS`.
    """
    lowered = content.lower()
    for marker in _PO_BRIEFING_PLACEHOLDERS:
        if marker in lowered:
            return f"PO-Briefing enthält noch einen Platzhalter ('{marker}') — nicht fertig."

    for section, pattern in PO_BRIEFING_SECTIONS:
        raw = _briefing_section_body(content, pattern)
        if raw is None:
            return f"PO-Briefing ohne Abschnitt '## {section}'."
        body = _re.sub(r"[\s\-*>]+", " ", raw).strip()
        if len(body) < _PO_BRIEFING_MIN_BODY:
            return f"PO-Briefing: Abschnitt '## {section}' ist leer bzw. zu dünn."

    limit = _PO_BRIEFING_MAX_WORDS if max_words is None else max_words
    words = count_briefing_words(content)
    if words > limit:
        return (
            f"Briefing zu lang ({words} Wörter, max {limit}) — "
            "po-briefer erneut dispatchen."
        )

    return None


def po_briefing_max_words(cfg: "dict | None" = None) -> int:
    """Konfigurierte Wortgrenze (po_briefing_gate.max_words) oder Default.

    Lenient: fehlende/kaputte Konfiguration oder ein unbrauchbarer Wert → Default.
    """
    if cfg is None:
        try:
            from config_loader import load_config
            config = load_config()
            cfg = config.get("po_briefing_gate", {}) if isinstance(config, dict) else {}
        except Exception:
            cfg = {}
    value = cfg.get("max_words") if isinstance(cfg, dict) else None
    if isinstance(value, bool):
        return _PO_BRIEFING_MAX_WORDS
    try:
        value = int(value)
    except (TypeError, ValueError):
        return _PO_BRIEFING_MAX_WORDS
    return value if value > 0 else _PO_BRIEFING_MAX_WORDS


def parse_briefing_frontmatter(content: str) -> dict:
    """Liest den YAML-Frontmatter-Block eines Briefings als flaches dict.

    Bewusst ein Mini-Parser statt PyYAML: Das CI-Gate soll ohne zusätzliche
    Abhängigkeit laufen, und der Block enthält nur `key: value`-Zeilen.
    """
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end < 0:
        return {}
    out = {}
    for line in content[3:end].splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def stamp_briefing_frontmatter(content: str, spec_rel: str, sha: str) -> str:
    """Schreibe `spec_file`/`spec_sha256` in den Frontmatter des Briefings.

    Vorhandener Frontmatter wird ergänzt bzw. der alte Stempel ersetzt (nie
    gedoppelt); fehlt er, wird einer vorangestellt. Der übrige Inhalt bleibt
    unangetastet.
    """
    stamp = {"spec_file": spec_rel, "spec_sha256": sha}
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end >= 0:
            head = content[3:end]
            rest = content[end + 4:]
            kept = [
                line for line in head.splitlines()
                if line.partition(":")[0].strip() not in stamp
            ]
            lines = [l for l in kept if l.strip()] + [f"{k}: {v}" for k, v in stamp.items()]
            return "---\n" + "\n".join(lines) + "\n---" + rest
    front = "\n".join(f"{k}: {v}" for k, v in stamp.items())
    return f"---\n{front}\n---\n\n{content.lstrip()}"


def _check_po_briefing(data: dict) -> "str | None":
    """Enforce an independent PO briefing at spec approval (Phase 3→4).

    Returns an error message if no current, complete briefing is registered,
    otherwise None. Lenient in the same spirit as `_check_adr`: missing config,
    missing/unreadable spec or a disabled gate all return None.
    """
    # 1. Kill-switch — only an explicit enabled: False disables the gate.
    cfg = {}
    try:
        from config_loader import load_config
        config = load_config()
        if isinstance(config, dict):
            cfg = config.get("po_briefing_gate", {}) or {}
        if isinstance(cfg, dict) and cfg.get("enabled") is False:
            return None
    except Exception:
        cfg = {}  # Config load failure → feature stays ON (lenient)

    # 2. Fast-Track: per Default kein Briefing (dort gibt es weder spec-writer
    #    noch Validator-Agenten). Abschaltbar via skip_fast_track: false.
    skip_fast = True
    if isinstance(cfg, dict) and cfg.get("skip_fast_track") is False:
        skip_fast = False
    if skip_fast and data.get("workflow_type") == "feature-fast":
        return None

    # 3. Ohne Spec kein Briefing-Gate (ein anderes Gate greift dann zuerst).
    spec_content = _read_spec_content(data)
    if spec_content is None:
        return None

    hint = (
        " → po-briefer-Agent laufen lassen (/30-write-spec Step 3b), "
        "danach: workflow.py set-briefing <pfad>"
    )

    # 4. Registrierung im State
    entry = data.get("po_briefing")
    if not isinstance(entry, dict) or not entry.get("file"):
        return "Kein unabhängiges PO-Briefing registriert" + hint
    try:
        briefing = _worktree_first_path(entry["file"]).read_text()
    except Exception:
        return f"PO-Briefing '{entry['file']}' nicht lesbar oder nicht vorhanden" + hint

    # 5. Inhalt + Länge
    content_err = check_briefing_content(briefing, po_briefing_max_words(cfg))
    if content_err:
        return content_err + hint

    # 6. Aktualität: das Briefing muss zu DIESER Spec-Fassung gehören. Sonst
    #    gibt der PO ein Briefing frei, das eine zwischenzeitlich umgeschriebene
    #    Spec beschreibt — das Gate wäre eine Attrappe.
    stored = entry.get("spec_sha256")
    if stored and stored != spec_sha256(spec_content):
        return (
            "PO-Briefing ist veraltet — die Spec wurde nach dem Briefing geändert."
            + hint
        )

    return None


# --- Phase Transition Validation ---

def _not_approved_msg() -> str:
    """Blockade-Meldung mit den TATSAECHLICH konfigurierten Freigabe-Phrasen.

    Die Meldung nannte fest verdrahtet 'approved' (Issue #90). `approval_phrases`
    ist über openspec.yaml konfigurierbar, und Projekte nutzen das — die Meldung
    nannte dort also ein Wort, das gar nicht das vereinbarte war, und verschwieg
    das vereinbarte. Zusammen mit der Phasenbindung, der eigentlichen Falle, ist
    der Nutzer sonst auf Raten angewiesen und greift zu
    `set-field spec_approved true` — genau dem Anti-Pattern, das das Gate
    verhindern soll.
    """
    base = "Spec not approved"
    try:
        from config_loader import get_approval_phrases
        phrases = [str(p).strip() for p in get_approval_phrases() if str(p).strip()]
    except Exception:
        phrases = []
    if phrases:
        base += " — user must say one of: " + ", ".join(phrases)
    else:
        base += " — user must say one of the configured approval phrases"
    return base + " (wirkt nur in phase3_spec)"



def _validate_transition(data: dict, target: str) -> str | None:
    """Validate phase transition prerequisites. Returns error message or None."""
    # Feature fast-track: only spec approval gate enforced
    if data.get("workflow_type") == "feature-fast":
        tgt_idx_ff = PHASES.index(target) if target in PHASES else -1
        if tgt_idx_ff < 0:
            return f"Unknown phase: {target}"
        if tgt_idx_ff >= PHASES.index("phase4_approved"):
            if not data.get("spec_file"):
                return "spec_file not set — run /30-write-spec first"
            if not data.get("spec_approved"):
                return _not_approved_msg()
            adr_err = _check_adr(data)
            if adr_err:
                return adr_err
            briefing_err = _check_po_briefing(data)
            if briefing_err:
                return briefing_err
        return None

    current = data.get("current_phase", "phase0_idle")
    cur_idx = PHASES.index(current) if current in PHASES else 0
    tgt_idx = PHASES.index(target) if target in PHASES else -1

    if tgt_idx < 0:
        return f"Unknown phase: {target}"

    # Allow backward transitions (reset) and same-phase — ausser Phase 8: der
    # Abschluss (`complete`/`finish`) prueft immer voll, auch wenn der State schon
    # auf phase8_complete steht (#337: sonst archivierte er ohne jede Pruefung).
    if tgt_idx < cur_idx or (tgt_idx == cur_idx and target != "phase8_complete"):
        return None

    if tgt_idx >= PHASES.index("phase2_analyse"):
        if not data.get("context_file"):
            return "context_file not set — run /context first"

    if tgt_idx >= PHASES.index("phase4_approved"):
        if not data.get("spec_file"):
            return "spec_file not set — run /write-spec first"
        if not data.get("spec_approved"):
            return _not_approved_msg()
        adr_err = _check_adr(data)
        if adr_err:
            return adr_err
        briefing_err = _check_po_briefing(data)
        if briefing_err:
            return briefing_err

    if tgt_idx >= PHASES.index("phase6_implement"):
        red_artifacts = [a for a in data.get("test_artifacts", [])
                        if a.get("phase") == "phase5_tdd_red"]
        if (not red_artifacts and not data.get("red_test_done")
                and not data.get("ui_test_red_done")):
            return "No RED test artifacts — run /tdd-red first"

    if tgt_idx >= PHASES.index("phase8_complete"):
        verdict = str(data.get("adversary_verdict", "") or "")
        if verdict.startswith("VERIFIED"):
            pass
        elif verdict.startswith("AMBIGUOUS") and data.get("adversary_ambiguous_override"):
            pass
        else:
            return "Adversary verdict missing or not VERIFIED"
        # #253: das Verdict zaehlt nur mit gueltigem, gestempeltem Dialog-Artefakt —
        # dieselbe Regel wie im Commit-Gate (bash_gate.py 5c), kein Override-Pfad.
        # #259: das Artefakt muss zudem jede seit der Basis geaenderte Code-Datei binden.
        try:
            import adversary_dialog as ad
            files, info = None, ""
            if ad.coverage_gate_enabled():
                try:
                    files, info = ad.phase8_code_files(data)
                except ad.ChangeSetError as exc:
                    return f"Adversary verdict ohne gültigen Dialog-Nachweis — {exc}"
            reason = ad.check_dialog_evidence(data, changed_files=files)
            if reason and info == ad.DEGRADED_BASE_NOTE:
                reason = f"{reason} ({info})"
        except Exception as exc:
            reason = f"Nachweis-Prüfung nicht verfügbar ({type(exc).__name__}: {exc})"
        if reason:
            return f"Adversary verdict ohne gültigen Dialog-Nachweis — {reason}"

    return None


def _start_base_commit() -> "str | None":
    """HEAD des Mess-Roots bei `start` (#259 §14): Worktree vor Hauptrepo; None ohne HEAD."""
    try:
        from adversary_dialog import git_toplevel, run_git
        top = git_toplevel(_worktree_root_if_any() or find_project_root())
        head = run_git(["rev-parse", "--verify", "-q", "HEAD"], top, probe=True) if top else None
    except Exception:
        return None
    return (head.strip() or None) if head else None


def _parse_numstat_z(output: str) -> "list[tuple[int, str]]":
    """`git diff --numstat -z` in (hinzugefuegt, pfad) zerlegen (#341).

    Eintrag `added\\tdeleted\\tpfad`; leeres drittes Feld = Umbenennung, die
    beiden folgenden NUL-Tokens sind Vorher/Nachher, der Nachher-Pfad zaehlt.
    Binaer (`-`) zaehlt 0.
    """
    tokens = output.split("\0")
    entries: "list[tuple[int, str]]" = []
    i = 0
    while i < len(tokens):
        parts = tokens[i].split("\t")
        i += 1
        if len(parts) < 3:
            continue
        path = parts[2]
        if not path:
            if i + 1 >= len(tokens):
                break
            path = tokens[i + 1]
            i += 2
        entries.append((int(parts[0]) if parts[0].isdigit() else 0, path))
    return entries


def _final_loc(data: dict) -> "tuple[int, int] | None":
    """Hinzugefuegte Zeilen seit der Phase-8-Basis als (prod, test) (#250 B, #341).

    Gleiche Ausschluesse und Testmuster wie edit_gate._check_loc_delta. Basis wie
    adversary_dialog._phase8_base (base_commit bzw. merge-base gegen origin/main,
    rebase-fest). None ohne aufloesbare Basis oder bei jedem Fehler.
    """
    try:
        import subprocess
        from adversary_dialog import _phase8_base, git_toplevel
        from config_loader import get_scope_loc_config, get_scope_test_loc_config
        top = git_toplevel(_worktree_root_if_any() or find_project_root())
        if not top:
            return None
        base, _ = _phase8_base(data, top)
        if not base or base == "HEAD":
            return None
        _, exclude_patterns = get_scope_loc_config()
        _, test_patterns = get_scope_test_loc_config()
        result = subprocess.run(
            ["git", "diff", str(base), "--numstat", "-z"],
            cwd=str(top), capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        prod_total = 0
        test_total = 0
        for added, file_name in _parse_numstat_z(result.stdout):
            if any(_re.search(p, file_name) for p in exclude_patterns):
                continue
            if any(_re.search(p, file_name) for p in test_patterns):
                test_total += added
            else:
                prod_total += added
        return (prod_total, test_total)
    except Exception:
        return None


# --- Commands ---

def cmd_start(args: list[str]) -> None:
    workflow_type = "feature"
    name_args = []
    i = 0
    while i < len(args):
        if args[i] == "--type" and i + 1 < len(args):
            workflow_type = args[i + 1]
            i += 2
        else:
            name_args.append(args[i])
            i += 1
    if not name_args:
        print("Usage: workflow.py start <name> [--type feature|feature-fast]", file=sys.stderr)
        sys.exit(1)
    if workflow_type == "bug":
        print("Typ `bug` wurde entfernt (#333). Fehler laufen über /00-intake; "
              "Kleinkram über `--type feature-fast`.", file=sys.stderr)
        sys.exit(1)
    if workflow_type not in ("feature", "feature-fast"):
        print(f"Unknown workflow type: {workflow_type!r}. Valid: feature, feature-fast", file=sys.stderr)
        sys.exit(1)
    name = name_args[0]
    _validate_name(name)
    wf_file = _workflow_file(name)
    if wf_file.exists():
        print(f"Workflow {name} already exists. Use 'switch' to activate.", file=sys.stderr)
        sys.exit(1)
    data = _new_workflow(name)
    data["workflow_type"] = workflow_type
    data["base_commit"] = _start_base_commit()  # #259: Basis-Kandidat fuer Phase 8
    if workflow_type == "feature-fast":
        # Fast-track for small features: skip context/analyse, start at spec
        data["current_phase"] = "phase3_spec"
        data["red_test_done"] = True  # inline TDD during implementation
        _log_phase_transition(data, "phase3_spec")
    else:
        _log_phase_transition(data, "phase1_context")
    _atomic_write(wf_file, data)
    _set_active(name)
    if workflow_type == "feature-fast":
        type_note = " [FEATURE fast-track → phase3_spec]"
    else:
        type_note = ""
    print(f"Started workflow: {name}{type_note}")
    print(
        f"\nOPENSPEC_ACTIVE_WORKFLOW={name} written to all settings.local.json files.\n"
        f"Hooks read this directly — no session restart required.\n"
        f"Shell (for manual workflow.py calls in terminal):\n"
        f"  export OPENSPEC_ACTIVE_WORKFLOW={name}\n"
        f"Agent spawns:\n"
        f'  Agent(prompt="... ## Required\\nexport OPENSPEC_ACTIVE_WORKFLOW={name}\\n...")',
    )


def cmd_switch(args: list[str]) -> None:
    if not args:
        print("Usage: workflow.py switch <name>", file=sys.stderr)
        sys.exit(1)
    name = args[0]
    _validate_name(name)
    wf_file = _workflow_file(name)
    if not wf_file.exists():
        print(f"Workflow {name} not found.", file=sys.stderr)
        sys.exit(1)

    # Warn if current active workflow is in a keyword-sensitive phase.
    # Switching here means the next "approved" / "go" will target the new workflow.
    try:
        current_data, current_name = _read_active()
        if current_name != name:
            cur_phase = current_data.get("current_phase", "")
            if cur_phase in KEYWORD_SENSITIVE_PHASES:
                print(
                    f"WARNING: Switching away from '{current_name}' which is in {cur_phase}.\n"
                    f"  User keywords ('approved', 'go') will now target '{name}'.\n"
                    f"  Switch back with: workflow.py switch {current_name}",
                    file=sys.stderr,
                )
    except SystemExit:
        pass  # no current active workflow — that's fine

    _set_active(name)

    env_name = _active_name_from_env()
    if env_name and env_name != name:
        print(
            f"Switched to workflow: {name}\n"
            f"  settings.local.json updated — hooks will use '{name}' on next invocation.\n"
            f"WARNING: Shell still has OPENSPEC_ACTIVE_WORKFLOW={env_name!r}.\n"
            f"  Update shell: export OPENSPEC_ACTIVE_WORKFLOW={name}",
            file=sys.stderr,
        )
    print(f"Switched to workflow: {name}")


def cmd_status(args: list[str]) -> None:
    data, name = _read_active()
    phase = data.get("current_phase", "phase0_idle")
    phase_name = PHASE_NAMES.get(phase, phase)
    spec = data.get("spec_file") or "Not created"
    approved = "Yes" if data.get("spec_approved") else "No"
    green_ok = "Yes" if data.get("green_approved") else "No"
    artifacts = len(data.get("test_artifacts", []))
    fix_loops = data.get("fix_loop_iterations", 0)
    transitions = len(data.get("phase_transitions", []))
    loc_delta = data.get("loc_delta_current", "+0")
    log_dir = find_project_root() / ".claude" / "workflows" / "_log"
    log_written = log_dir.exists() and any(log_dir.glob(f"*_{name}.yaml"))
    from hook_utils import resolve_active_workflow
    _resolved_name, source = resolve_active_workflow()
    if source == "env":
        source_label = f"env:OPENSPEC_ACTIVE_WORKFLOW={name}"
    else:
        source_label = source  # 'file', 'settings', ...
    print(f"Workflow: {name}  [{source_label}]")
    print(f"Phase: {phase_name}")
    print(f"Spec: {spec}")
    print(f"Approved: {approved}")
    print(f"GREEN Approved: {green_ok}")
    print(f"Test Artifacts: {artifacts}")
    print(f"Fix-Loop Iterations: {fix_loops}")
    print(f"Phase Transitions: {transitions}")
    loc_override = data.get("loc_limit_override")
    if loc_override:
        print(f"LoC Delta: {loc_delta}/{loc_override} (override)")
    else:
        print(f"LoC Delta: {loc_delta}")
    print(f"Execution Log: {'Written' if log_written else 'Pending — run write-log before complete'}")


def cmd_phase(args: list[str]) -> None:
    if not args:
        print("Usage: workflow.py phase <phase>", file=sys.stderr)
        sys.exit(1)
    trigger = "command"
    filtered = [a for a in args if not a.startswith("--trigger=")]
    for a in args:
        if a.startswith("--trigger="):
            trigger = a.split("=", 1)[1]
    target = filtered[0]
    data, name = _read_active()
    error = _validate_transition(data, target)
    if error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        sys.exit(1)
    current = data.get("current_phase", "phase0_idle")
    # Fix-loop counter: re-entering phase6_implement from phase6b_adversary.
    # Vor record_transition, damit die Budget-Pruefung den neuen Stand sieht (#250).
    if target == "phase6_implement" and current == "phase6b_adversary":
        data["fix_loop_iterations"] = data.get("fix_loop_iterations", 0) + 1
    exceeded = record_transition(data, target, trigger)
    data["current_phase"] = target
    _save_active(data)
    print(f"Set phase to: {target}")
    _print_budget_question(exceeded)


def format_budget_question(exceeded: list) -> str:
    """Rueckfrage-Text zu Budget-Ueberschreitungen; leer ohne Ereignisse (#250, #341)."""
    return "\n".join(
        f"RÜCKFRAGE AN DEN PO: Stufe {event.get('stage')}: {event['metric']} "
        f"steht bei {event['value']}, Grenze {event['limit']}.\n"
        f"  Lege dem PO jetzt den Stand vor und frage: weiter, kleiner schneiden "
        f"oder abbrechen?"
        for event in exceeded or []
    )


def _print_budget_question(exceeded: list) -> None:
    """Budget-Ueberschreitung als Anweisung an Claude ausgeben, keine Sperre (#250)."""
    text = format_budget_question(exceeded)
    if text:
        print(text)


# Schluessel, die ein Gate steuern und einen eigenen, geprueften Befehl haben.
# `set-field` wuerde sie ohne jede Pruefung setzen (#379).
_SET_FIELD_PROTECTED = {
    "current_phase": "workflow.py phase <phase>",
    "spec_approved": "Freigabe-Phrase des Users in phase3_spec",
    "red_test_done": "workflow.py mark-red <ergebnis>",
    "ui_test_red_done": "workflow.py mark-ui-red <ergebnis>",
    "test_artifacts": "workflow.py add-artifact ...",
    "po_briefing": "workflow.py set-briefing <pfad>",
    "adversary_ambiguous_override": "workflow.py override-ambiguous <grund>",
    "affected_files": "workflow.py set-affected-files ...",
    "phase_log": "wird von workflow.py phase gefuehrt",
    "status": "workflow.py finish / abandon",
    "name": "workflow.py start <name>",
}


def _check_set_field_type(data: dict, name: str, value: str) -> str | None:
    """`workflow_type` per set-field: Herabstufung auf feature-fast ab Phase 4
    nur mit Override-Token des Users (#379).

    Der feature-fast-Zweig von `_validate_transition` prueft beim Abschluss kein
    Adversary-Verdict — ein freigegebener `feature`-Workflow verloere durch die
    Umklassifizierung sonst jeden Pruefnachweis. Vor der Freigabe bleibt der
    Wechsel frei: dann greift das Freigabe-Gate noch. Rueckfall-Rezept fuer
    Alt-Workflows vom Typ `bug` (#333) bleibt ueber `override` moeglich.
    """
    if value not in ("feature", "feature-fast"):
        return f"Unbekannter workflow_type {value!r}. Gueltig: feature, feature-fast"
    if value != "feature-fast" or data.get("workflow_type") == "feature-fast":
        return None
    phase = data.get("current_phase", "phase0_idle")
    idx = PHASES.index(phase) if phase in PHASES else len(PHASES)
    if idx < PHASES.index("phase4_approved"):
        return None
    try:
        from override_token import has_valid_token
        if has_valid_token(name):
            return None
    except Exception:
        pass
    return (
        f"workflow_type -> feature-fast in {phase} entzieht den Workflow dem "
        "Adversary-Gate beim Abschluss. Nach der Freigabe nur mit Override: "
        "der User tippt \"override\" (gilt 1 h), dann erneut ausfuehren. "
        "Ohne Abschluss beenden: workflow.py abandon --reason \"...\""
    )


def cmd_set_field(args: list[str]) -> None:
    if len(args) < 2:
        print("Usage: workflow.py set-field <key> <value>", file=sys.stderr)
        sys.exit(1)
    key, value = args[0], " ".join(args[1:])
    if key in _SET_FIELD_PROTECTED:
        print(
            f"BLOCKED: `{key}` steuert ein Gate und ist per set-field gesperrt (#379). "
            f"Stattdessen: {_SET_FIELD_PROTECTED[key]}",
            file=sys.stderr,
        )
        sys.exit(1)
    if key == "workflow_type":
        data, name = _read_active()
        err = _check_set_field_type(data, name, value)
        if err:
            print(f"BLOCKED: {err}", file=sys.stderr)
            sys.exit(1)
    if value.lower() in ("true", "yes"):
        value = True
    elif value.lower() in ("false", "no"):
        value = False
    elif key == "adversary_findings_total" and value.isdigit():
        value = int(value)  # Kennzahl als Zahl, nicht als String (#278)
    data, name = _read_active()
    data[key] = value
    _save_active(data)
    print(f"Set {key} = {value} on workflow {name}")


def cmd_set_briefing(args: list[str]) -> None:
    """Registriere das unabhängige PO-Briefing für die anstehende Freigabe.

    Bindet es über den SHA-256 der Spec an genau die Fassung, die der Briefer
    gelesen hat. Prüft denselben Inhalts-Kontrakt wie das Gate — ein
    unvollständiges Briefing fällt hier auf, nicht erst beim `approved`.
    """
    if not args:
        print("Usage: workflow.py set-briefing <pfad-zum-po-briefing>", file=sys.stderr)
        sys.exit(1)
    rel = args[0]
    root = _worktree_first_root(rel)
    path = Path(rel)
    if path.is_absolute():
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            print(f"BLOCKED: Briefing liegt ausserhalb des Projekts: {rel}", file=sys.stderr)
            sys.exit(1)
    briefing_path = root / rel

    try:
        briefing = briefing_path.read_text()
    except Exception:
        print(f"BLOCKED: PO-Briefing nicht lesbar: {rel}", file=sys.stderr)
        sys.exit(1)

    content_err = check_briefing_content(briefing, po_briefing_max_words())
    if content_err:
        print(f"BLOCKED: {content_err}", file=sys.stderr)
        sys.exit(1)

    data, name = _read_active()
    spec_content = _read_spec_content(data)
    if spec_content is None:
        print(
            "BLOCKED: Keine lesbare Spec im Workflow (Feld 'spec_file') — "
            "das Briefing kann an keine Spec-Fassung gebunden werden.",
            file=sys.stderr,
        )
        sys.exit(1)

    sha = spec_sha256(spec_content)
    data["po_briefing"] = {
        "file": rel,
        "spec_sha256": sha,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    _save_active(data)

    # Bindung zusätzlich IN die Briefing-Datei stempeln. Der Workflow-State
    # liegt unter .claude/workflows/ und ist gitignored — er erreicht die CI
    # nie. Nur ein Stempel in der committeten Datei macht ein veraltetes
    # Briefing serverseitig erkennbar (scripts/ci_spec_gate.py).
    try:
        briefing_path.write_text(
            stamp_briefing_frontmatter(briefing, str(data.get("spec_file", "")), sha)
        )
    except Exception as exc:
        print(
            f"WARNUNG: Briefing registriert, aber Frontmatter-Stempel fehlgeschlagen ({exc}). "
            "Das CI-Gate kann die Aktualität dann nicht prüfen.",
            file=sys.stderr,
        )

    print(f"PO-Briefing registriert für Workflow {name}: {rel}")


def cmd_set_affected_files(args: list[str]) -> None:
    replace = "--replace" in args
    files = [a for a in args if a != "--replace"]
    data, name = _read_active()
    if replace:
        data["affected_files"] = files
    else:
        existing = set(data.get("affected_files", []))
        existing.update(files)
        data["affected_files"] = sorted(existing)
    _save_active(data)
    print(f"Set affected_files on workflow {name}: {len(data['affected_files'])} files")


def cmd_add_artifact(args: list[str]) -> None:
    if len(args) < 4:
        print("Usage: workflow.py add-artifact <type> <path> <desc> <phase>", file=sys.stderr)
        sys.exit(1)
    art_type, art_path, desc, phase = args[0], args[1], args[2], args[3]
    if art_type not in VALID_ARTIFACT_TYPES:
        print(
            f"Invalid artifact type: '{art_type}'\n"
            f"Valid types: {', '.join(sorted(VALID_ARTIFACT_TYPES))}",
            file=sys.stderr,
        )
        sys.exit(1)
    data, _ = _read_active()
    data.setdefault("test_artifacts", []).append({
        "type": art_type,
        "path": art_path,
        "description": desc,
        "phase": phase,
        "created": datetime.now().isoformat(),
    })
    _save_active(data)
    print(f"Artifact added to {data['name']}: {art_type} ({desc})")


def cmd_mark_red(args: list[str]) -> None:
    result = " ".join(args) if args else "failed"
    data, name = _read_active()
    data["red_test_done"] = True
    data["red_test_result"] = result
    _save_active(data)
    print(f"RED unit test marked done: {result}")


def cmd_mark_ui_red(args: list[str]) -> None:
    result = " ".join(args) if args else "failed"
    data, name = _read_active()
    data["ui_test_red_done"] = True
    data["ui_test_red_result"] = result
    _save_active(data)
    print(f"RED UI test marked done: {result}")


def cmd_write_log(args: list[str]) -> None:
    data, name = _read_active()
    log_dir = find_project_root() / ".claude" / "workflows" / "_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"{date_str}_{name}.yaml"
    # `phase_log` ist die verlaessliche Quelle fuer besuchte Phasen (Issue #111):
    # Die Startphase eines Workflows taucht in `phase_transitions` nur als `from` auf,
    # nie als `to` — aus dem `to`-Feld gebaut galt `phase1_context` systematisch als
    # uebersprungen. `_log_phase_transition()` wird dagegen von jedem Codepfad gerufen.
    phases_visited = {
        e.get("phase") for e in data.get("phase_log", []) if isinstance(e, dict)
    }
    phases_visited.discard(None)
    phases_visited.add(data.get("current_phase", "phase0_idle"))
    phases_completed = [p for p in PHASES if p in phases_visited and p != "phase0_idle"]
    impl_idx = PHASES.index("phase6_implement")
    expected = PHASES[1:impl_idx + 1]
    phases_skipped = [p for p in expected if p not in phases_visited]
    outcome = args[0] if args else "success"
    # "nie gesetzt" != "explizit 0" (#278): beide Kennzahlen schreibt erst `stamp`.
    persisted = "adversary_findings_total" in data
    findings_total = data["adversary_findings_total"] if persisted else "unbekannt"
    files_changed = len(data.get("affected_files", [])) if persisted else "unbekannt"
    final = _final_loc(data)
    loc_delta = f"+{final[0]}" if final else data.get("loc_delta_current", "+0")
    lines = [
        f"workflow_id: {name}",
        f"project: {find_project_root().name}",
        f"completed_at: {datetime.now().isoformat()}",
        "phases_completed:",
    ] + [f"  - {p}" for p in phases_completed] + [
        "phases_skipped:",
    ] + [f"  - {p}" for p in phases_skipped] + [
        f"override_used: {bool(data.get('adversary_ambiguous_override'))}",
        f"tdd_red_confirmed: {bool(data.get('red_test_done') or data.get('ui_test_red_done'))}",
        f"adversary_verdict: {data.get('adversary_verdict') or 'none'}",
        f"adversary_findings_total: {findings_total}",
        f"adversary_fix_loop_iterations: {data.get('fix_loop_iterations', 0)}",
        f"scope_files_changed: {files_changed}",
        f"scope_loc_delta: {loc_delta}",
        f"effort_budget_exceeded: {len(data.get('budget_events', []))}",
        f"outcome: {outcome}",
    ]
    log_file.write_text("\n".join(lines) + "\n")
    print(f"Execution log written: {log_file}")


def cmd_override_ambiguous(args: list[str]) -> None:
    if not args:
        print("Usage: workflow.py override-ambiguous <reason>", file=sys.stderr)
        sys.exit(1)
    reason = " ".join(args)
    data, name = _read_active()
    data["adversary_ambiguous_override"] = {
        "reason": reason,
        "at": datetime.now().isoformat(),
    }
    _save_active(data)
    print(f"AMBIGUOUS override set for {name}: {reason}")


def cmd_complete(args: list[str]) -> None:
    data, name = _read_active()
    log_dir = find_project_root() / ".claude" / "workflows" / "_log"
    if not (log_dir.exists() and any(log_dir.glob(f"*_{name}.yaml"))):
        print(f"BLOCKED: No execution log for '{name}'. Run: workflow.py write-log [outcome]",
              file=sys.stderr)
        sys.exit(1)
    # Must run the same prerequisite/adversary-verdict check as an explicit
    # `phase phase8_complete` transition — this is the only completion path
    # actually used in practice (write-log → complete), so skipping this
    # check here silently defeats the adversary gate. See issue #960.
    error = _validate_transition(data, "phase8_complete")
    if error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        sys.exit(1)
    data["current_phase"] = "phase8_complete"
    try:  # #250 B: Messung blockiert den Abschluss nie
        final = _final_loc(data)
        if final is not None:
            data["loc_delta_final"], data["loc_delta_test_final"] = final
    except Exception:
        pass
    archive = _archive_dir()
    archive.mkdir(parents=True, exist_ok=True)
    _atomic_write(archive / f"{name}.json", data)
    wf_file = _workflow_file(name)
    if wf_file.exists():
        wf_file.unlink()
    link = _active_link()
    if link.is_symlink():
        link.unlink()
    _persist_env(None)
    print(f"Workflow {name} completed and archived.")


def cmd_abandon(args: list[str]) -> None:
    """Bricht den aktiven Workflow ehrlich ab — ohne Abschluss-Gates.

    Fuer Workflows OHNE Pruefgegenstand (reine Analyse-/Kontext-Arbeit, nie
    in phase6_implement): `complete` verlangt ein Adversary-Verdict, das es
    hier nie geben kann; der bisher einzige Ausweg war eine Typ-
    Umklassifizierung — genau das Gaming-Muster, das die Gates verhindern
    sollen (Issue #82). `abandon` archiviert stattdessen mit status
    'abandoned' + Pflicht-Begruendung: sichtbar bleibt, dass hier KEIN
    Nachweis gefuehrt wurde.
    """
    reason = ""
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--reason" and i + 1 < len(args):
            reason = args[i + 1]
            i += 2
        else:
            rest.append(args[i])
            i += 1
    if not reason:
        reason = " ".join(rest).strip()
    if not reason:
        print("Usage: workflow.py abandon --reason \"<warum kein Abschluss>\"", file=sys.stderr)
        print("  Die Begruendung ist Pflicht — sie ersetzt den fehlenden Nachweis.", file=sys.stderr)
        sys.exit(1)

    data, name = _read_active()
    data["status"] = "abandoned"
    data["abandon_reason"] = reason
    data["abandoned_at"] = datetime.now().isoformat()
    archive = _archive_dir()
    archive.mkdir(parents=True, exist_ok=True)
    _atomic_write(archive / f"{name}.json", data)
    wf_file = _workflow_file(name)
    if wf_file.exists():
        wf_file.unlink()
    link = _active_link()
    if link.is_symlink():
        link.unlink()
    _persist_env(None)
    print(f"Workflow {name} abgebrochen (abandoned) und archiviert — NICHT abgeschlossen.")
    print(f"  Grund: {reason}")


def cmd_phase_log(args: list[str]) -> None:
    data, name = _read_active()
    log = data.get("phase_log", [])
    if not log:
        print("Kein Phase-Log vorhanden (Workflow vor v3.2 gestartet oder noch keine Phase-Transitions).")
        return
    SEP = "─" * 52
    print(f"Workflow: {name}")
    print(SEP)
    print(f"  {'Phase':<26} {'Dauer':>9}  Status")
    total_min = 0.0
    longest_phase = None
    longest_dur = 0.0
    for entry in log:
        phase = entry.get("phase", "?")
        dur = entry.get("duration_min")
        exited = entry.get("exited_at")
        if exited is None:
            status = "[aktiv]"
            dur_str = "–"
        else:
            dur_val = dur if dur is not None else 0.0
            total_min += dur_val
            dur_str = f"{dur_val:.1f} min"
            status = "✓"
            if dur_val > longest_dur:
                longest_dur = dur_val
                longest_phase = phase
        print(f"  {phase:<26} {dur_str:>9}  {status}")
    print(SEP)
    print(f"  Gesamt (abgeschlossen): {total_min:.1f} min")
    if longest_phase:
        print(f"  Längste Phase: {longest_phase} ({longest_dur:.1f} min) ▲")


def cmd_list(args: list[str]) -> None:
    wf_dir = _workflows_dir()
    if not wf_dir.exists():
        print("No workflows.")
        return
    from hook_utils import resolve_active_workflow
    active_name, _source = resolve_active_workflow()
    for f in sorted(wf_dir.glob("*.json")):
        data = _read_workflow(f)
        name = data.get("name", f.stem)
        phase = data.get("current_phase", "?")
        marker = " *" if name == active_name else ""
        print(f"  {name}: {PHASE_NAMES.get(phase, phase)}{marker}")


def _deploy_steps(value) -> "list[str]":
    """`deploy.<feld>` als Liste von Befehlen (String oder Liste von Strings)."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def cmd_deploy_config(args: list[str]) -> None:
    """Deploy-Ablauf des Projekts aus `deploy:` in der Projekt-Config (#81). Rein lesend.

    Ausgabe immer mit Rueckgabecode 0; `DEPLOY_CONFIGURED=yes` nur, wenn
    `command` UND `verify` gesetzt sind — ohne Nachpruefung gilt ein Deploy
    nicht als beschrieben. `/70-deploy` verzweigt auf dieser Zeile.
    """
    try:
        from config_loader import load_config
        block = load_config().get("deploy") or {}
    except Exception:
        block = {}
    if not isinstance(block, dict):
        block = {}
    steps = {k: _deploy_steps(block.get(k)) for k in ("command", "verify", "rollback")}
    configured = bool(steps["command"] and steps["verify"])
    print(f"DEPLOY_CONFIGURED={'yes' if configured else 'no'}")
    for key in ("command", "verify", "rollback"):
        if steps[key]:
            for line in steps[key]:
                print(f"{key}: {line}")
        else:
            print(f"{key}: (nicht gesetzt)")
    print(f"autonomous: {'true' if block.get('autonomous') is True else 'false'}")
    if not configured:
        # #372: eine Root-config.yaml nur mit `deploy:` gilt als App-Config und
        # wird uebergangen — sonst traegt /70-deploy dort ein und dreht sich im Kreis.
        try:
            from config_loader import skipped_app_config_note
            note = skipped_app_config_note()
        except Exception:
            note = ""
        if note:
            print(f"HINWEIS: {note}")

def cmd_find(args: list[str]) -> None:
    """Laufende Workflows zu einer Issue-Nummer (Wiedereinstieg nach /clear, #276).

    Rein lesend. Ersetzt den frueheren Python-Heredoc in /50-implement Step 0,
    den bash_gate als Marker-Manipulation blockte (Feldname + State-Pfad).
    """
    if not args:
        print("Usage: workflow.py find <issue-nummer>", file=sys.stderr)
        sys.exit(1)
    issue = args[0].lstrip("#")
    pat = _re.compile(rf"(^|[-_]){_re.escape(issue)}([-_]|$)")
    wf_dir = _workflows_dir()
    hits = []
    for f in sorted(wf_dir.glob("*.json")) if wf_dir.exists() else []:
        if not pat.search(f.stem):
            continue
        d = _read_workflow(f)
        hits.append((f.stem, d.get("current_phase"), d.get("spec_file") or "Not created",
                     d.get("adversary_verdict"), d.get("affected_files") or []))
    if not hits:
        print(f"KEIN laufender Workflow fuer #{issue} "
              "(evtl. abgeschlossen -> .claude/workflows/_archive/).")
        return
    for name, ph, spec, verd, aff in hits:
        print(f"GEFUNDEN: {name} | Phase={ph} | Spec={spec} | Verdict={verd}")
        if aff:
            print(f"  affected_files: {', '.join(aff)}")
    print("\nNAME=" + hits[0][0])

def _retro_load_log(name: str) -> dict:
    """Load execution log YAML for a workflow by name. Returns {} if not found."""
    log_dir = find_project_root() / ".claude" / "workflows" / "_log"
    if not log_dir.exists():
        return {}
    matches = sorted(log_dir.glob(f"*_{name}.yaml"))
    if not matches:
        return {}
    lines = matches[-1].read_text().splitlines()
    result: dict = {}
    for line in lines:
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def cmd_retro_list(args: list[str]) -> None:
    """List all archived workflows with basic stats."""
    archive = _archive_dir()
    if not archive.exists() or not list(archive.glob("*.json")):
        print("Keine abgeschlossenen Workflows im Archiv.")
        return
    SEP = "─" * 68
    print(SEP)
    print(f"  {'Name':<28} {'Typ':<14} {'Datum':<12} {'Zeit':>7}  Ergebnis")
    print(SEP)
    files = sorted(archive.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files:
        data = _read_workflow(f)
        name = data.get("name", f.stem)
        wf_type = data.get("workflow_type", "feature")
        created = data.get("created", "")[:10]
        log = _retro_load_log(name)
        if data.get("status") == "abandoned":
            outcome = "abgebrochen"
        else:
            outcome = log.get("outcome", "–")
        total_min = sum(
            e.get("duration_min") or 0.0
            for e in data.get("phase_log", [])
            if e.get("exited_at") is not None
        )
        time_str = f"{total_min:.0f} min" if total_min > 0 else "–"
        print(f"  {name:<28} {wf_type:<14} {created:<12} {time_str:>7}  {outcome}")
    print(SEP)
    print(f"  {len(files)} Workflow(s) archiviert.")


def _retro_hints(data: dict, log: dict, total_min: float, longest_phase: str,
                 longest_dur: float, phases_skipped: list) -> list[str]:
    hints = []
    fix_loops = data.get("fix_loop_iterations", 0)
    if fix_loops > 0:
        hints.append(
            f"  ⚠  {fix_loops}x Fix-Loop in phase6b_adversary — deutet auf "
            "unvollstaendige Spec oder fehlende Edge Cases hin."
        )
    if longest_phase and total_min > 0 and longest_dur / total_min > 0.35:
        pct = round(longest_dur / total_min * 100)
        hints.append(
            f"  ⚠  {longest_phase} war mit {longest_dur:.1f} min die laengste "
            f"Phase ({pct}% der Gesamtzeit)."
        )
    if data.get("adversary_ambiguous_override"):
        reason = data["adversary_ambiguous_override"].get("reason", "–")
        hints.append(f"  ⚠  AMBIGUOUS-Override genutzt: \"{reason}\"")
    if phases_skipped:
        hints.append(f"  ℹ  Uebersprungene Phasen: {', '.join(phases_skipped)}")
    if not data.get("red_test_done") and not data.get("ui_test_red_done"):
        if data.get("workflow_type") != "feature-fast":
            hints.append("  ⚠  Kein TDD-RED-Artefakt registriert — "
                         "TDD-Disziplin nicht nachweisbar.")
    if not hints:
        hints.append("  ✓  Keine Optimierungshinweise — Workflow lief reibungslos.")
    return hints


def cmd_retro(args: list[str]) -> None:
    """Analyze an archived workflow. Uses most recent if no name given."""
    archive = _archive_dir()
    if not archive.exists():
        print("Kein Archiv gefunden — noch keine abgeschlossenen Workflows.")
        return

    if args:
        name = args[0]
        path = archive / f"{name}.json"
        if not path.exists():
            print(f"Workflow '{name}' nicht im Archiv gefunden.", file=sys.stderr)
            print("Verfuegbare Workflows: workflow.py retro-list", file=sys.stderr)
            sys.exit(1)
    else:
        files = sorted(archive.glob("*.json"), key=lambda f: f.stat().st_mtime)
        if not files:
            print("Kein abgeschlossener Workflow im Archiv.")
            return
        path = files[-1]
        name = path.stem

    data = _read_workflow(path)
    log = _retro_load_log(name)
    wf_type = data.get("workflow_type", "feature")
    created = data.get("created", "")[:10]

    SEP = "═" * 52
    sep = "─" * 52
    print(SEP)
    print(f"  RETRO: {name}")
    print(f"  Typ: {wf_type}  |  Gestartet: {created}")
    print(SEP)

    # Phase timeline
    phase_log = data.get("phase_log", [])
    total_min = 0.0
    longest_phase = None
    longest_dur = 0.0
    print()
    print("PHASEN-TIMELINE")
    print(sep)
    print(f"  {'Phase':<28} {'Dauer':>8}  Status")
    print(sep)
    for entry in phase_log:
        phase = entry.get("phase", "?")
        dur = entry.get("duration_min")
        exited = entry.get("exited_at")
        if exited is None:
            status = "[unterbrochen]"
            dur_str = "–"
        else:
            dur_val = dur if dur is not None else 0.0
            total_min += dur_val
            dur_str = f"{dur_val:.1f} min"
            status = "✓"
            if dur_val > longest_dur:
                longest_dur = dur_val
                longest_phase = phase
        print(f"  {phase:<28} {dur_str:>8}  {status}")
    print(sep)
    total_str = f"{total_min:.1f} min" if total_min > 0 else "–"
    print(f"  Gesamt: {total_str}", end="")
    if longest_phase:
        print(f"  |  Laengste Phase: {longest_phase} ({longest_dur:.1f} min) ▲")
    else:
        print()

    # Quality signals
    verdict = data.get("adversary_verdict") or log.get("adversary_verdict") or "–"
    fix_loops = data.get("fix_loop_iterations", 0)
    findings = data.get("adversary_findings_total", 0)
    tdd_ok = data.get("red_test_done") or data.get("ui_test_red_done")
    override_used = bool(data.get("adversary_ambiguous_override"))
    affected = len(data.get("affected_files", []))
    loc_delta = data.get("loc_delta_current") or log.get("scope_loc_delta") or "–"
    outcome = log.get("outcome", "–")

    print()
    print("QUALITAETS-SIGNALE")
    print(sep)
    tdd_str = "✓ bestaetigt" if tdd_ok else ("– (fast-track)" if wf_type == "feature-fast" else "✗ fehlend")
    print(f"  TDD RED Artefakte:     {tdd_str}")
    print(f"  Adversary-Verdict:     {verdict}")
    print(f"  Fix-Loop-Iterationen:  {fix_loops}")
    print(f"  Adversary-Findings:    {findings}")
    print(f"  Override genutzt:      {'Ja' if override_used else 'Nein'}")
    print(f"  Scope:                 {affected} Datei(en), {loc_delta} LoC")
    print(f"  Ergebnis:              {outcome}")

    # Phases skipped
    phases_skipped_raw = log.get("phases_skipped", "")
    phases_skipped = [p.strip("- ") for p in phases_skipped_raw.split(",") if p.strip("- ")]

    # Optimization hints
    hints = _retro_hints(data, log, total_min, longest_phase, longest_dur, phases_skipped)
    print()
    print("OPTIMIERUNGS-HINWEISE")
    print(sep)
    for h in hints:
        print(h)
    print()


def cmd_cleanup_stale_locks(args: list[str]) -> None:
    """Remove pending_validation locks and approval markers of finished workflows.

    Ueber die Workflow-NAMEN, nicht ueber die Lock-Dateien: vorher iterierte
    das hier nur ueber `pending_validation_*.json` und loeschte den passenden
    Freigabe-Marker mit. Ein Freigabe-Marker OHNE gleichnamigen Lock war damit
    durch keinen Befehl erreichbar — im Framework-Repo selbst betraf das 6 von
    9 (Issue #135). Und liegenbleiben ist bei genau dieser Familie keine
    Kosmetik: das post_implementation_gate erkennt eine Freigabe allein an der
    Existenz einer nach dem Workflow benannten Datei (#134).
    """
    claude_dir = find_project_root() / ".claude"
    wf_dir = _workflows_dir()
    removed = []
    skipped = []

    names = {p.stem.replace("pending_validation_", "", 1)
             for p in claude_dir.glob("pending_validation_*.json")}
    names |= {p.name.replace("user_approved_validation_", "", 1)
              for p in claude_dir.glob("user_approved_validation_*")}

    for wf_name in sorted(n for n in names if n):
        # Active workflow still in progress?
        active_file = wf_dir / f"{wf_name}.json"
        if active_file.exists():
            try:
                data = _read_workflow(active_file)
                phase = data.get("current_phase", "")
                if phase == "phase6_implement":
                    skipped.append(f"  SKIPPED {wf_name} (aktiv in {phase})")
                    continue
            except Exception:
                pass
        # Archived or past phase6 → safe to remove
        for marker in (claude_dir / f"pending_validation_{wf_name}.json",
                       claude_dir / f"user_approved_validation_{wf_name}"):
            if marker.exists():
                marker.unlink(missing_ok=True)
                removed.append(f"  Removed: {marker.name}")
    if removed:
        print("\n".join(removed))
    if skipped:
        print("\n".join(skipped))
    if not removed and not skipped:
        print("Keine verwaisten Lock-Dateien gefunden.")


def _sessions_age(last_seen) -> str:
    """Alter von last_seen als kompakter Text."""
    if not isinstance(last_seen, (int, float)) or isinstance(last_seen, bool):
        return SESSIONS_PLACEHOLDER
    delta = max(0, int(time.time() - last_seen))
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    return f"{delta // 3600}h"


def _read_session_entries() -> list:
    """Registereintraege aus .claude/session-locks/*.json des eigenen Projekts."""
    locks = find_project_root() / ".claude" / "session-locks"
    entries: list = []
    if not locks.is_dir():
        return entries
    for f in sorted(locks.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        if isinstance(data, dict) and data.get("session_id"):
            entries.append(data)
    entries.sort(key=lambda e: e.get("started_at") or 0)
    return entries


def _one_line(value) -> str:
    """Zeilenumbrueche platt machen — die Auskunft hat genau fuenf Zeilen."""
    return " ".join(str(value).split())


def cmd_observable_surface(args: list[str]) -> None:
    """Auskunft, kein Gate: hat der Arbeitsstand eine beobachtbare Oberflaeche?

    Genau fuenf Zeilen auf stdout, Rueckgabecode IMMER 0 — `/60-validate` liest
    daraus nur, ob die Schlussfrage entfallen darf. Bewusst OHNE aktiven
    Workflow (kein `_read_active()`): gelesen wird der Arbeitsbaum, nicht der
    State. `ROOT=`/`CONFIG=` machen die Diskrepanz aus #153 sichtbar — Config
    aus dem Hauptrepo, Messung im Worktree.
    """
    try:
        from hook_utils import observable_surface_report
        report = observable_surface_report()
        surface = "no" if report.get("surface") is False else "yes"
        reason = _one_line(report.get("reason") or "") or "unbekannt"
        files = int(report.get("files") or 0)
        root = _one_line(report.get("root") or "")
    except Exception as exc:
        # Ein Absturz darf keine Rueckfrage unterdruecken: yes + sprechender Grund.
        surface, reason, files, root = "yes", f"internal-error {type(exc).__name__}", 0, ""
    try:
        from config_loader import config_source_note
        note = _one_line(config_source_note() or "")
    except Exception:
        note = ""
    print(f"OBSERVABLE_SURFACE={surface}\nREASON={reason}\nFILES={files}\n"
          f"ROOT={root}\nCONFIG={note}")


def cmd_sessions(args: list[str]) -> None:
    """List registered Claude sessions of this project (session-locks)."""
    entries = _read_session_entries()

    if "--json" in args:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return

    if not entries:
        print("Keine registrierten Sessions in .claude/session-locks/.")
        return

    def col(entry, key):
        """Wert der Spalte, ungekuerzt — die Breiten unten fassen die
        Namenskonvention `typ-NNN[-MMM]-beschreibung` vollstaendig."""
        value = entry.get(key)
        if value is None or value == "":
            return SESSIONS_PLACEHOLDER
        return str(value)

    def issue_col(entry):
        """Einzige gekuerzte Spalte (B5): ein Claim kann mehrere Nummern halten
        (`120,121`), und ein kaputter oder manipulierter Wert darf die Tabelle
        nicht sprengen."""
        value = col(entry, "issue")
        return value if len(value) <= ISSUE_W else value[:ISSUE_W - 1] + "…"

    # Breiten aus den realen Werten dieses Projekts abgeleitet (laengste:
    # session_id 36 = UUID, agent_name 20, branch 23, workflow 28, phase 17).
    # worktree 21, weil branch = "worktree-" (9 Zeichen) + Worktree-Name ist:
    # was in branch passt, passt damit garantiert auch in worktree.
    ISSUE_W = 9
    SEP = "─" * 178
    print(SEP)
    print(
        f"  {'Session':<36} {'Agent':<20} {'Worktree':<21} {'Branch':<30} "
        f"{'Workflow':<30} {'Phase':<18} {'Issue':<{ISSUE_W}} {'Alter':>5}"
    )
    print(SEP)
    for entry in entries:
        print(
            f"  {col(entry, 'session_id'):<36} {col(entry, 'agent_name'):<20} "
            f"{col(entry, 'worktree'):<21} {col(entry, 'branch'):<30} "
            f"{col(entry, 'workflow'):<30} {col(entry, 'phase'):<18} "
            f"{issue_col(entry):<{ISSUE_W}} {_sessions_age(entry.get('last_seen')):>5}"
        )
    print(SEP)
    print(f"  {len(entries)} Session(s) registriert.")


COMMANDS = {
    "start": cmd_start,
    "switch": cmd_switch,
    "status": cmd_status,
    "phase": cmd_phase,
    "phase-log": cmd_phase_log,
    "set-field": cmd_set_field,
    "set-briefing": cmd_set_briefing,
    "set-affected-files": cmd_set_affected_files,
    "add-artifact": cmd_add_artifact,
    "mark-red": cmd_mark_red,
    "mark-ui-red": cmd_mark_ui_red,
    "write-log": cmd_write_log,
    "override-ambiguous": cmd_override_ambiguous,
    "complete": cmd_complete,
    # Alias: der Worktree-Waechter des Harness liest "complete" als bash-Builtin
    # und blockiert die ganze Kommandozeile (gregor_zwanzig#1478).
    "finish": cmd_complete,
    "abandon": cmd_abandon,
    "list": cmd_list,
    "find": cmd_find,
    "deploy-config": cmd_deploy_config,
    "retro-list": cmd_retro_list,
    "sessions": cmd_sessions,
    "observable-surface": cmd_observable_surface,
    "retro": cmd_retro,
    "cleanup-stale-locks": cmd_cleanup_stale_locks,
}


def main():
    if len(sys.argv) < 2:
        print("Usage: workflow.py <command> [args...]", file=sys.stderr)
        print(f"Commands: {', '.join(COMMANDS.keys())}", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)

    COMMANDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
