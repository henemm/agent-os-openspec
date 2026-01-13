#!/usr/bin/env python3
"""
OpenSpec Framework - Multi-Workflow State Manager

Supports multiple parallel workflows in a single project.
Each workflow tracks its own phase independently.

State File Format (.claude/workflow_state.json):
{
  "version": "2.0",
  "workflows": {
    "feature-login-oauth": {
      "current_phase": "phase2_spec",
      "created": "2025-01-12T10:00:00Z",
      "last_updated": "2025-01-12T11:30:00Z",
      "spec_file": "docs/specs/auth/login-oauth.md",
      "spec_approved": false,
      "context_file": "docs/context/feature-login-oauth.md",
      "test_artifacts": [],
      "affected_files": []
    },
    "bugfix-crash-on-start": {
      "current_phase": "phase4_implement",
      ...
    }
  },
  "active_workflow": "feature-login-oauth"
}

Phases (in order):
- phase0_idle        : No workflow started
- phase1_context     : Gathering relevant context (NEW!)
- phase2_analyse     : Analysing requirements and codebase
- phase3_spec        : Writing specification
- phase4_approved    : Spec approved by user (gate)
- phase5_tdd_red     : Writing failing tests (TDD RED)
- phase6_implement   : Implementation (TDD GREEN)
- phase7_validate    : Validation and manual testing
- phase8_complete    : Workflow complete, ready for commit
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# Phase definitions with order
PHASES = [
    "phase0_idle",
    "phase1_context",
    "phase2_analyse",
    "phase3_spec",
    "phase4_approved",
    "phase5_tdd_red",
    "phase6_implement",
    "phase7_validate",
    "phase8_complete",
]

# Human-readable phase names
PHASE_NAMES = {
    "phase0_idle": "Idle - No workflow started",
    "phase1_context": "Context Generation",
    "phase2_analyse": "Analysis",
    "phase3_spec": "Specification Writing",
    "phase4_approved": "Spec Approved",
    "phase5_tdd_red": "TDD RED - Write Failing Tests",
    "phase6_implement": "Implementation (TDD GREEN)",
    "phase7_validate": "Validation",
    "phase8_complete": "Complete",
}

# Backlog status options
BACKLOG_STATUSES = ["open", "spec_ready", "in_progress", "done", "blocked"]

# Human-readable backlog status names
BACKLOG_STATUS_NAMES = {
    "open": "Open",
    "spec_ready": "Spec Ready",
    "in_progress": "In Progress",
    "done": "Done",
    "blocked": "Blocked",
}

# Automatic mapping: Phase -> Backlog Status
PHASE_TO_BACKLOG_STATUS = {
    "phase0_idle": "open",
    "phase1_context": "open",
    "phase2_analyse": "open",
    "phase3_spec": "open",
    "phase4_approved": "spec_ready",
    "phase5_tdd_red": "in_progress",
    "phase6_implement": "in_progress",
    "phase7_validate": "in_progress",
    "phase8_complete": "done",
}

# Phrases that indicate user wants to pause (not complete)
PAUSE_PHRASES = [
    "ich höre hier auf",
    "das reicht für heute",
    "implementation später",
    "nur die spec",
    "pause",
    "später weitermachen",
    "für heute fertig",
    "rest später",
    "spec reicht erstmal",
    "stop here",
    "pause workflow",
    "continue later",
]

# Phases that allow code modification
CODE_MODIFY_PHASES = ["phase6_implement", "phase7_validate", "phase8_complete"]

# Phases that require test artifacts
TEST_REQUIRED_PHASES = ["phase6_implement", "phase7_validate"]


def get_state_file() -> Path:
    """Get the path to the workflow state file."""
    # Try to find project root via .git
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists():
            return parent / ".claude" / "workflow_state.json"
    return cwd / ".claude" / "workflow_state.json"


def load_state() -> dict:
    """Load the multi-workflow state file."""
    state_file = get_state_file()

    if not state_file.exists():
        return {
            "version": "2.0",
            "workflows": {},
            "active_workflow": None
        }

    with open(state_file, 'r') as f:
        state = json.load(f)

    # Migrate from v1 format if needed
    if "version" not in state:
        state = migrate_v1_to_v2(state)

    return state


def save_state(state: dict) -> None:
    """Save the workflow state."""
    state_file = get_state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)

    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)


def migrate_v1_to_v2(v1_state: dict) -> dict:
    """Migrate from single-workflow (v1) to multi-workflow (v2) format."""
    # Map old phase names to new
    phase_mapping = {
        "idle": "phase0_idle",
        "analyse_done": "phase2_analyse",
        "spec_written": "phase3_spec",
        "spec_approved": "phase4_approved",
        "implemented": "phase6_implement",
        "validated": "phase7_validate",
    }

    old_phase = v1_state.get("current_phase", "idle")
    new_phase = phase_mapping.get(old_phase, "phase0_idle")

    feature_name = v1_state.get("feature_name")
    if not feature_name:
        return {
            "version": "2.0",
            "workflows": {},
            "active_workflow": None
        }

    # Create workflow entry from v1 data
    workflow = {
        "current_phase": new_phase,
        "created": v1_state.get("last_updated", datetime.now().isoformat()),
        "last_updated": v1_state.get("last_updated", datetime.now().isoformat()),
        "spec_file": v1_state.get("spec_file"),
        "spec_approved": v1_state.get("spec_approved", False),
        "context_file": None,
        "test_artifacts": [],
        "affected_files": [],
    }

    return {
        "version": "2.0",
        "workflows": {feature_name: workflow},
        "active_workflow": feature_name
    }


def create_workflow(name: str) -> dict:
    """Create a new workflow entry."""
    return {
        "current_phase": "phase1_context",
        "created": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "spec_file": None,
        "spec_approved": False,
        "context_file": None,
        "test_artifacts": [],
        "affected_files": [],
        # Separate RED/GREEN tracking (v2.0)
        "red_test_done": False,
        "red_test_result": None,  # Description of the failing test
        "green_test_done": False,
        "green_test_result": None,  # Description of passing tests
        # Analysis findings
        "analysis_findings": None,
        # Phases completed history
        "phases_completed": [],
        # Backlog status (v2.1) - separate from phase
        # open | spec_ready | in_progress | done | blocked
        "backlog_status": "open",
    }


def start_workflow(name: str, make_active: bool = True) -> dict:
    """Start a new workflow or resume existing one."""
    state = load_state()

    if name not in state["workflows"]:
        state["workflows"][name] = create_workflow(name)

    if make_active:
        state["active_workflow"] = name

    save_state(state)
    return state


def get_active_workflow() -> Optional[dict]:
    """Get the currently active workflow."""
    state = load_state()
    active_name = state.get("active_workflow")

    if not active_name or active_name not in state["workflows"]:
        return None

    workflow = state["workflows"][active_name]
    workflow["name"] = active_name
    return workflow


def set_active_workflow(name: str) -> bool:
    """Switch to a different workflow."""
    state = load_state()

    if name not in state["workflows"]:
        return False

    state["active_workflow"] = name
    save_state(state)
    return True


def advance_phase(workflow_name: str = None) -> Optional[str]:
    """Advance the workflow to the next phase."""
    state = load_state()

    name = workflow_name or state.get("active_workflow")
    if not name or name not in state["workflows"]:
        return None

    workflow = state["workflows"][name]
    current_phase = workflow["current_phase"]

    try:
        current_index = PHASES.index(current_phase)
        if current_index < len(PHASES) - 1:
            new_phase = PHASES[current_index + 1]
            workflow["current_phase"] = new_phase
            workflow["last_updated"] = datetime.now().isoformat()
            save_state(state)
            return new_phase
    except ValueError:
        pass

    return None


def set_phase(workflow_name: str, phase: str) -> bool:
    """Set a specific phase for a workflow."""
    if phase not in PHASES:
        return False

    state = load_state()

    if workflow_name not in state["workflows"]:
        return False

    state["workflows"][workflow_name]["current_phase"] = phase
    state["workflows"][workflow_name]["last_updated"] = datetime.now().isoformat()
    save_state(state)
    return True


def add_test_artifact(workflow_name: str, artifact: dict) -> bool:
    """
    Add a test artifact to a workflow.

    Artifact format:
    {
        "type": "screenshot" | "email" | "api_response" | "log" | "file",
        "path": "/path/to/artifact",
        "description": "What this artifact proves",
        "created": "ISO timestamp",
        "phase": "phase5_tdd_red" | "phase7_validate"
    }
    """
    state = load_state()

    if workflow_name not in state["workflows"]:
        return False

    artifact["created"] = datetime.now().isoformat()
    state["workflows"][workflow_name]["test_artifacts"].append(artifact)
    state["workflows"][workflow_name]["last_updated"] = datetime.now().isoformat()
    save_state(state)
    return True


def get_workflow_status(name: str = None) -> str:
    """Get a human-readable status for a workflow."""
    state = load_state()

    workflow_name = name or state.get("active_workflow")
    if not workflow_name or workflow_name not in state["workflows"]:
        return "No active workflow"

    workflow = state["workflows"][workflow_name]
    phase = workflow["current_phase"]
    phase_name = PHASE_NAMES.get(phase, phase)

    # Get backlog status (explicit or derived)
    backlog = workflow.get("backlog_status") or derive_backlog_status(phase)
    backlog_name = BACKLOG_STATUS_NAMES.get(backlog, backlog)

    lines = [
        f"Workflow: {workflow_name}",
        f"Phase: {phase_name}",
        f"Backlog Status: {backlog_name}",
        f"Spec: {workflow.get('spec_file') or 'Not created'}",
        f"Approved: {'Yes' if workflow.get('spec_approved') else 'No'}",
        f"Test Artifacts: {len(workflow.get('test_artifacts', []))}",
    ]

    return "\n".join(lines)


def list_workflows() -> list:
    """List all workflows with their current phase and backlog status."""
    state = load_state()
    active = state.get("active_workflow")

    result = []
    for name, workflow in state.get("workflows", {}).items():
        # Get backlog status (explicit or derived from phase)
        backlog = workflow.get("backlog_status") or derive_backlog_status(workflow["current_phase"])

        result.append({
            "name": name,
            "phase": workflow["current_phase"],
            "phase_name": PHASE_NAMES.get(workflow["current_phase"], "Unknown"),
            "backlog_status": backlog,
            "backlog_status_name": BACKLOG_STATUS_NAMES.get(backlog, backlog),
            "is_active": name == active,
            "last_updated": workflow.get("last_updated"),
        })

    return sorted(result, key=lambda x: x["last_updated"] or "", reverse=True)


def can_modify_code(workflow_name: str = None) -> tuple[bool, str]:
    """
    Check if code modification is allowed for a workflow.
    Returns (allowed, reason).
    """
    state = load_state()

    name = workflow_name or state.get("active_workflow")
    if not name:
        return False, "No active workflow. Start with /context or /analyse."

    if name not in state["workflows"]:
        return False, f"Workflow '{name}' not found."

    workflow = state["workflows"][name]
    phase = workflow["current_phase"]

    if phase not in CODE_MODIFY_PHASES:
        return False, f"Current phase is {PHASE_NAMES.get(phase, phase)}. Code modification requires phase6_implement or later."

    # Check for test artifacts in TDD phases
    if phase in TEST_REQUIRED_PHASES:
        artifacts = workflow.get("test_artifacts", [])
        red_artifacts = [a for a in artifacts if a.get("phase") == "phase5_tdd_red"]

        if not red_artifacts:
            return False, "TDD RED phase incomplete. You must write and run failing tests with REAL test data first."

    return True, "OK"


def complete_workflow(name: str) -> bool:
    """Mark a workflow as complete and archive it."""
    state = load_state()

    if name not in state["workflows"]:
        return False

    state["workflows"][name]["current_phase"] = "phase8_complete"
    state["workflows"][name]["backlog_status"] = "done"  # Explicitly set to done
    state["workflows"][name]["last_updated"] = datetime.now().isoformat()

    # If this was the active workflow, clear it
    if state.get("active_workflow") == name:
        # Find next active or clear
        remaining = [n for n in state["workflows"] if n != name and
                    state["workflows"][n]["current_phase"] != "phase8_complete"]
        state["active_workflow"] = remaining[0] if remaining else None

    save_state(state)
    return True


def mark_red_test_done(workflow_name: str = None, result: str = None) -> bool:
    """
    Mark RED test as done for a workflow.

    Args:
        workflow_name: Name of workflow (uses active if None)
        result: Description of the failing test result
    """
    state = load_state()

    name = workflow_name or state.get("active_workflow")
    if not name or name not in state["workflows"]:
        return False

    workflow = state["workflows"][name]
    workflow["red_test_done"] = True
    workflow["red_test_result"] = result
    workflow["last_updated"] = datetime.now().isoformat()

    # Auto-advance to phase5 if in phase4
    if workflow["current_phase"] == "phase4_approved":
        workflow["current_phase"] = "phase5_tdd_red"
        if "phase5_tdd_red" not in workflow.get("phases_completed", []):
            workflow.setdefault("phases_completed", []).append("phase5_tdd_red")

    save_state(state)
    return True


def mark_green_test_done(workflow_name: str = None, result: str = None) -> bool:
    """
    Mark GREEN test as done for a workflow.

    Args:
        workflow_name: Name of workflow (uses active if None)
        result: Description of passing tests
    """
    state = load_state()

    name = workflow_name or state.get("active_workflow")
    if not name or name not in state["workflows"]:
        return False

    workflow = state["workflows"][name]
    workflow["green_test_done"] = True
    workflow["green_test_result"] = result
    workflow["last_updated"] = datetime.now().isoformat()

    # Auto-advance to phase7 if in phase6
    if workflow["current_phase"] == "phase6_implement":
        workflow["current_phase"] = "phase7_validate"
        if "phase7_validate" not in workflow.get("phases_completed", []):
            workflow.setdefault("phases_completed", []).append("phase7_validate")

    save_state(state)
    return True


def get_tdd_status(workflow_name: str = None) -> dict:
    """
    Get TDD status for a workflow.

    Returns dict with:
        red_done: bool
        red_result: str or None
        green_done: bool
        green_result: str or None
        artifacts: list of test artifacts
    """
    workflow = get_active_workflow() if not workflow_name else None

    if workflow_name:
        state = load_state()
        workflow = state["workflows"].get(workflow_name)

    if not workflow:
        return {
            "red_done": False,
            "red_result": None,
            "green_done": False,
            "green_result": None,
            "artifacts": [],
        }

    return {
        "red_done": workflow.get("red_test_done", False),
        "red_result": workflow.get("red_test_result"),
        "green_done": workflow.get("green_test_done", False),
        "green_result": workflow.get("green_test_result"),
        "artifacts": workflow.get("test_artifacts", []),
    }


def derive_backlog_status(phase: str) -> str:
    """
    Derive the appropriate backlog status from a workflow phase.

    Returns the backlog status that corresponds to the given phase.
    """
    return PHASE_TO_BACKLOG_STATUS.get(phase, "open")


def get_backlog_status(workflow_name: str = None) -> str:
    """
    Get the backlog status for a workflow.

    Returns the explicit backlog_status if set, otherwise derives from phase.
    """
    state = load_state()

    name = workflow_name or state.get("active_workflow")
    if not name or name not in state["workflows"]:
        return "open"

    workflow = state["workflows"][name]

    # Return explicit status if set
    if workflow.get("backlog_status"):
        return workflow["backlog_status"]

    # Otherwise derive from phase
    return derive_backlog_status(workflow["current_phase"])


def set_backlog_status(status: str, workflow_name: str = None) -> bool:
    """
    Explicitly set the backlog status for a workflow.

    Args:
        status: One of: open, spec_ready, in_progress, done, blocked
        workflow_name: Name of workflow (uses active if None)

    Returns:
        True if successful, False otherwise.
    """
    if status not in BACKLOG_STATUSES:
        return False

    state = load_state()

    name = workflow_name or state.get("active_workflow")
    if not name or name not in state["workflows"]:
        return False

    state["workflows"][name]["backlog_status"] = status
    state["workflows"][name]["last_updated"] = datetime.now().isoformat()
    save_state(state)
    return True


def is_pause_message(message: str) -> bool:
    """
    Check if a message indicates the user wants to pause the workflow.

    Returns True if pause intent detected.
    """
    message_lower = message.lower().strip()

    for phrase in PAUSE_PHRASES:
        if phrase in message_lower:
            return True

    return False


def pause_workflow(workflow_name: str = None) -> tuple[bool, str]:
    """
    Pause a workflow and set appropriate backlog status.

    If the workflow is in phase4_approved or later (but not complete),
    sets status to 'spec_ready'. Otherwise keeps current status.

    Returns:
        (success, message) tuple
    """
    state = load_state()

    name = workflow_name or state.get("active_workflow")
    if not name or name not in state["workflows"]:
        return False, "No active workflow to pause."

    workflow = state["workflows"][name]
    phase = workflow["current_phase"]
    phase_index = PHASES.index(phase) if phase in PHASES else 0

    # Determine appropriate backlog status based on progress
    if phase == "phase8_complete":
        return False, "Workflow already complete."
    elif phase_index >= PHASES.index("phase4_approved"):
        # Spec is approved but not implemented -> spec_ready
        workflow["backlog_status"] = "spec_ready"
        status_msg = "spec_ready"
    else:
        # Still in early phases -> open
        workflow["backlog_status"] = "open"
        status_msg = "open"

    workflow["last_updated"] = datetime.now().isoformat()
    save_state(state)

    return True, f"Workflow '{name}' paused. Backlog status: {status_msg}"


def sync_backlog_status_from_phase(workflow_name: str = None) -> bool:
    """
    Synchronize backlog status based on current phase.

    Call this when phase changes to keep backlog status in sync
    (unless manually overridden).
    """
    state = load_state()

    name = workflow_name or state.get("active_workflow")
    if not name or name not in state["workflows"]:
        return False

    workflow = state["workflows"][name]
    phase = workflow["current_phase"]

    # Only auto-sync if not manually set to blocked
    if workflow.get("backlog_status") != "blocked":
        workflow["backlog_status"] = derive_backlog_status(phase)
        workflow["last_updated"] = datetime.now().isoformat()
        save_state(state)

    return True


if __name__ == "__main__":
    # CLI interface for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage: workflow_state_multi.py <command> [args]")
        print("Commands: status, list, start <name>, switch <name>, advance, phase <phase>, backlog <status>, pause")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "status":
        print(get_workflow_status())
    elif cmd == "list":
        for w in list_workflows():
            marker = "→ " if w["is_active"] else "  "
            print(f"{marker}{w['name']}: {w['phase_name']} [{w['backlog_status_name']}]")
    elif cmd == "start" and len(sys.argv) > 2:
        start_workflow(sys.argv[2])
        print(f"Started workflow: {sys.argv[2]}")
    elif cmd == "switch" and len(sys.argv) > 2:
        if set_active_workflow(sys.argv[2]):
            print(f"Switched to: {sys.argv[2]}")
        else:
            print(f"Workflow not found: {sys.argv[2]}")
    elif cmd == "advance":
        new_phase = advance_phase()
        if new_phase:
            print(f"Advanced to: {PHASE_NAMES.get(new_phase, new_phase)}")
        else:
            print("Cannot advance further")
    elif cmd == "phase" and len(sys.argv) > 2:
        state = load_state()
        active = state.get("active_workflow")
        if active and set_phase(active, sys.argv[2]):
            # Sync backlog status when phase changes
            sync_backlog_status_from_phase(active)
            print(f"Set phase to: {sys.argv[2]}")
        else:
            print(f"Failed to set phase: {sys.argv[2]}")
    elif cmd == "backlog" and len(sys.argv) > 2:
        status = sys.argv[2]
        if set_backlog_status(status):
            print(f"Set backlog status to: {BACKLOG_STATUS_NAMES.get(status, status)}")
        else:
            print(f"Failed to set backlog status: {status}")
            print(f"Valid options: {', '.join(BACKLOG_STATUSES)}")
    elif cmd == "pause":
        success, message = pause_workflow()
        print(message)
    else:
        print(f"Unknown command: {cmd}")
