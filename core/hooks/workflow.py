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
    python3 workflow.py set-affected-files [--replace] <f1> <f2> ...
    python3 workflow.py add-artifact <type> <path> <desc> <phase>
    python3 workflow.py mark-red <result>
    python3 workflow.py mark-ui-red <result>
    python3 workflow.py write-log [outcome]
    python3 workflow.py override-ambiguous <reason>
    python3 workflow.py complete
    python3 workflow.py list
"""

from hook_utils import setup_path, find_project_root
setup_path()

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

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

# Phases where user keywords ("approved", "go", "deployed") are expected.
# Switching away from these without updating OPENSPEC_ACTIVE_WORKFLOW causes
# the next keyword to land on the wrong workflow.
KEYWORD_SENSITIVE_PHASES = {"phase3_spec", "phase6_implement", "phase7_validate"}

VALID_ARTIFACT_TYPES = [
    "screenshot", "email", "api_response", "log", "file", "test_output", "video", "audio",
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

    Lookup order:
    1. OPENSPEC_ACTIVE_WORKFLOW env var (set by Claude Code from settings.local.json at startup)
    2. settings.local.json direct read (when workflow.py start/switch was called in the
       current session — Claude Code only reads settings files at startup, not live)
    The .active symlink fallback is intentionally removed (causes cross-session drift).
    """
    env_name = _active_name_from_env()

    # Fallback: read settings.local.json directly if env var absent
    if not env_name:
        try:
            settings_path = find_project_root() / ".claude" / "settings.local.json"
            if settings_path.exists():
                settings = json.loads(settings_path.read_text())
                env_name = settings.get("env", {}).get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    if env_name:
        wf_file = _workflow_file(env_name)
        if wf_file.exists():
            data = _read_workflow(wf_file)
            return data, data.get("name", wf_file.stem)
        print(
            f"FATAL: OPENSPEC_ACTIVE_WORKFLOW='{env_name}' is set but no matching workflow file exists.\n"
            f"  Run: python3 .claude/hooks/workflow.py list",
            file=sys.stderr,
        )
        sys.exit(1)

    # Symlink fallback is DISABLED. If a stale .active symlink exists, tell the user
    # what to do instead of silently using it.
    link = _active_link()
    if link.is_symlink():
        target = Path(os.readlink(str(link)))
        name = target.stem
        print(
            f"FATAL: No active workflow found.\n"
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
    """
    env_name = _active_name_from_env()
    if env_name:
        wf_file = _workflow_file(env_name)
        if wf_file.exists():
            data = _read_workflow(wf_file)
            return data.get("name", wf_file.stem), data
        return None
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
    """Write (or remove) OPENSPEC_ACTIVE_WORKFLOW in ALL settings.local.json files.

    Hook subprocesses inherit Claude Code's process environment, not individual Bash
    exports. Worktrees each have their own .claude/settings.local.json, so we must
    update the main project file AND every worktree's file.
    """
    project_root = find_project_root()
    targets = [project_root / ".claude" / "settings.local.json"]

    # Also update all worktrees: .claude/worktrees/*/.claude/settings.local.json
    worktrees_dir = project_root / ".claude" / "worktrees"
    if worktrees_dir.is_dir():
        for wt in worktrees_dir.iterdir():
            if wt.is_dir():
                targets.append(wt / ".claude" / "settings.local.json")

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


# --- Phase Transition Validation ---

def _validate_transition(data: dict, target: str) -> str | None:
    """Validate phase transition prerequisites. Returns error message or None."""
    # Bug fast-track: no prerequisites enforced
    if data.get("workflow_type") == "bug":
        return None

    current = data.get("current_phase", "phase0_idle")
    cur_idx = PHASES.index(current) if current in PHASES else 0
    tgt_idx = PHASES.index(target) if target in PHASES else -1

    if tgt_idx < 0:
        return f"Unknown phase: {target}"

    # Allow backward transitions (reset) and same-phase
    if tgt_idx <= cur_idx:
        return None

    if tgt_idx >= PHASES.index("phase2_analyse"):
        if not data.get("context_file"):
            return "context_file not set — run /context first"

    if tgt_idx >= PHASES.index("phase4_approved"):
        if not data.get("spec_file"):
            return "spec_file not set — run /write-spec first"
        if not data.get("spec_approved"):
            return "Spec not approved — user must say 'approved'"

    if tgt_idx >= PHASES.index("phase6_implement"):
        red_artifacts = [a for a in data.get("test_artifacts", [])
                        if a.get("phase") == "phase5_tdd_red"]
        if not red_artifacts and not data.get("red_test_done"):
            return "No RED test artifacts — run /tdd-red first"

    if tgt_idx >= PHASES.index("phase8_complete"):
        verdict = data.get("adversary_verdict", "")
        if not verdict or not str(verdict).startswith("VERIFIED"):
            return "Adversary verdict missing or not VERIFIED"

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
        print("Usage: workflow.py start <name> [--type feature|bug]", file=sys.stderr)
        sys.exit(1)
    if workflow_type not in ("feature", "bug"):
        print(f"Unknown workflow type: {workflow_type!r}. Valid: feature, bug", file=sys.stderr)
        sys.exit(1)
    name = name_args[0]
    wf_file = _workflow_file(name)
    if wf_file.exists():
        print(f"Workflow {name} already exists. Use 'switch' to activate.", file=sys.stderr)
        sys.exit(1)
    data = _new_workflow(name)
    data["workflow_type"] = workflow_type
    if workflow_type == "bug":
        # Fast-track: start at phase6, bypass spec and TDD gates
        data["current_phase"] = "phase6_implement"
        data["spec_approved"] = True
        data["red_test_done"] = True
        _log_phase_transition(data, "phase6_implement")
    else:
        _log_phase_transition(data, "phase1_context")
    _atomic_write(wf_file, data)
    _set_active(name)
    type_note = " [BUG fast-track → phase6_implement]" if workflow_type == "bug" else ""
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
    env_name = _active_name_from_env()
    source_label = f"env:OPENSPEC_ACTIVE_WORKFLOW={env_name}" if env_name == name else ".active symlink"
    print(f"Workflow: {name}  [{source_label}]")
    print(f"Phase: {phase_name}")
    print(f"Spec: {spec}")
    print(f"Approved: {approved}")
    print(f"GREEN Approved: {green_ok}")
    print(f"Test Artifacts: {artifacts}")
    print(f"Fix-Loop Iterations: {fix_loops}")
    print(f"Phase Transitions: {transitions}")
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
    data.setdefault("phase_transitions", []).append({
        "from": current,
        "to": target,
        "at": datetime.now().isoformat(),
        "trigger": trigger,
    })
    _log_phase_transition(data, target)
    # Fix-loop counter: re-entering phase6_implement from phase6b_adversary
    if target == "phase6_implement" and current == "phase6b_adversary":
        data["fix_loop_iterations"] = data.get("fix_loop_iterations", 0) + 1
    data["current_phase"] = target
    _save_active(data)
    print(f"Set phase to: {target}")


def cmd_set_field(args: list[str]) -> None:
    if len(args) < 2:
        print("Usage: workflow.py set-field <key> <value>", file=sys.stderr)
        sys.exit(1)
    key, value = args[0], " ".join(args[1:])
    if value.lower() in ("true", "yes"):
        value = True
    elif value.lower() in ("false", "no"):
        value = False
    data, name = _read_active()
    data[key] = value
    _save_active(data)
    print(f"Set {key} = {value} on workflow {name}")


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
    transitions = data.get("phase_transitions", [])
    phases_visited = {t["to"] for t in transitions}
    phases_visited.add(data.get("current_phase", "phase0_idle"))
    phases_completed = [p for p in PHASES if p in phases_visited and p != "phase0_idle"]
    impl_idx = PHASES.index("phase6_implement")
    expected = PHASES[1:impl_idx + 1]
    phases_skipped = [p for p in expected if p not in phases_visited]
    outcome = args[0] if args else "success"
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
        f"adversary_findings_total: {data.get('adversary_findings_total', 0)}",
        f"adversary_fix_loop_iterations: {data.get('fix_loop_iterations', 0)}",
        f"scope_files_changed: {len(data.get('affected_files', []))}",
        f"scope_loc_delta: {data.get('loc_delta_current', '+0')}",
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
    data["current_phase"] = "phase8_complete"
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
    active_name = _active_name_from_env()
    if not active_name:
        link = _active_link()
        if link.is_symlink():
            target = os.readlink(str(link))
            active_name = Path(target).stem
    for f in sorted(wf_dir.glob("*.json")):
        data = _read_workflow(f)
        name = data.get("name", f.stem)
        phase = data.get("current_phase", "?")
        marker = " *" if name == active_name else ""
        print(f"  {name}: {PHASE_NAMES.get(phase, phase)}{marker}")


COMMANDS = {
    "start": cmd_start,
    "switch": cmd_switch,
    "status": cmd_status,
    "phase": cmd_phase,
    "phase-log": cmd_phase_log,
    "set-field": cmd_set_field,
    "set-affected-files": cmd_set_affected_files,
    "add-artifact": cmd_add_artifact,
    "mark-red": cmd_mark_red,
    "mark-ui-red": cmd_mark_ui_red,
    "write-log": cmd_write_log,
    "override-ambiguous": cmd_override_ambiguous,
    "complete": cmd_complete,
    "list": cmd_list,
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
