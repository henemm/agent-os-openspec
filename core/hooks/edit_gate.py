#!/usr/bin/env python3
"""
Edit Gate v3 — Consolidated PreToolUse Hook for Edit|Write

Replaces 17 separate hooks with 1. Sequential short-circuit logic:

1. Protected State Files → BLOCK
2. Always-Allowed (docs, tests, scripts, .md, .json) → ALLOW
3. Not code file → ALLOW
4. Infrastructure (.claude/hooks/) → Override token check
5. Stop-Lock → BLOCK
6. Find workflow for file (affected_files)
7. No workflow → BLOCK
8. Phase < phase6_implement → BLOCK
9. Override token → ALLOW (skip TDD check)
10. RED test artifacts → BLOCK if missing
11. ALLOW

Exit Codes: 0 = allowed, 2 = blocked
"""

from hook_utils import setup_path, find_project_root, get_tool_input, block, allow
setup_path()

import json
import os
import re
import sys
from pathlib import Path

# --- Defaults (overridable via config.yaml) ---

CODE_EXTENSIONS = {
    ".swift", ".kt", ".java", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".cpp", ".c", ".h", ".hpp", ".rb", ".php", ".cs",
}

ALWAYS_ALLOWED_DIRS = [
    "Tests/", "UITests/", "Test/", "test/", "__tests__/", "tests/",
    "spec/", "docs/", ".claude/commands/", "scripts/", "tools/",
]

ALWAYS_ALLOWED_PATTERNS = [
    r"\.md$", r"\.txt$", r"\.json$", r"\.yaml$", r"\.yml$",
    r"\.toml$", r"\.gitignore$", r"README", r"CHANGELOG", r"LICENSE",
]

PROTECTED_STATE_FILES = [
    "workflows/", "workflow_state.json", "user_override_token.json",
]

INFRASTRUCTURE_DIRS = [".claude/hooks/", ".claude/agents/"]

IMPL_PHASES = {
    "phase6_implement", "phase6b_adversary", "phase7_validate", "phase8_complete",
}


# --- Config loading (optional, falls back to defaults) ---

def _load_config_values() -> dict:
    """Try to load overrides from config.yaml. Returns empty dict on failure."""
    try:
        from config_loader import load_config
        return load_config()
    except Exception:
        return {}


def _get_config_list(config: dict, section: str, key: str, default: list) -> list:
    return config.get(section, {}).get(key, default)


# --- Helpers ---

_root = find_project_root()


def _read_active_workflow() -> dict | None:
    """Read the active workflow from .claude/workflows/.active symlink."""
    link = _root / ".claude" / "workflows" / ".active"
    if not link.exists():
        return None
    try:
        target = Path(os.readlink(str(link)))
        if not target.is_absolute():
            target = link.parent / target
        if target.exists():
            return json.loads(target.read_text())
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _find_workflow_for_file(file_path: str) -> dict | None:
    """Find workflow that owns a file via affected_files match."""
    wf_dir = _root / ".claude" / "workflows"
    if not wf_dir.exists():
        return None
    rel = file_path
    root_str = str(_root)
    if rel.startswith(root_str):
        rel = rel[len(root_str):].lstrip("/")
    for f in wf_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        phase = data.get("current_phase", "phase0_idle")
        if phase in ("phase8_complete", "phase0_idle"):
            continue
        for af in data.get("affected_files", []):
            if rel == af or rel.endswith("/" + af) or af.endswith("/" + rel):
                return data
    return None


def _has_override_token(workflow_name: str = None) -> bool:
    try:
        from override_token import has_valid_token
        return has_valid_token(workflow_name)
    except ImportError:
        return False


def _is_stop_locked() -> bool:
    lock = _root / ".claude" / "stop_lock.json"
    if not lock.exists():
        return False
    try:
        return json.loads(lock.read_text()).get("enabled", False)
    except (json.JSONDecodeError, OSError):
        return False


# --- Main ---

def main():
    tool_input = get_tool_input()
    file_path = tool_input.get("file_path", "")
    if not file_path:
        allow()

    config = _load_config_values()

    # Configurable lists with defaults
    code_ext = set(_get_config_list(config, "strict_code_gate", "code_extensions", list(CODE_EXTENSIONS)))
    allowed_dirs = _get_config_list(config, "strict_code_gate", "always_allowed_dirs", ALWAYS_ALLOWED_DIRS)
    allowed_patterns = _get_config_list(config, "strict_code_gate", "always_allowed_patterns", ALWAYS_ALLOWED_PATTERNS)

    # 1. Protected state files
    for pf in PROTECTED_STATE_FILES:
        if pf in file_path:
            block(f"BLOCKED: Protected state file: {pf}")

    # 2. Always-allowed directories
    for d in allowed_dirs:
        if d in file_path:
            allow()

    # 2b. Always-allowed patterns
    for p in allowed_patterns:
        if re.search(p, file_path, re.IGNORECASE):
            allow()

    # 3. Not a code file
    ext = Path(file_path).suffix.lower()
    if ext not in code_ext:
        allow()

    # 4. Infrastructure file
    for infra in INFRASTRUCTURE_DIRS:
        if infra in file_path:
            if _has_override_token("__infra__") or _has_override_token():
                allow()
            block("BLOCKED: Infrastructure file — user must type 'override'.")

    # 5. Stop-lock
    if _is_stop_locked():
        block("BLOCKED: Stop-lock active.")

    # 6. Find workflow for file
    workflow = _find_workflow_for_file(file_path)
    if not workflow:
        workflow = _read_active_workflow()

    # 7. No workflow
    if not workflow:
        block(f"BLOCKED: No active workflow for {Path(file_path).name}. Start with /context.")

    phase = workflow.get("current_phase", "phase0_idle")
    wf_name = workflow.get("name", "unknown")

    # 8. Phase check
    if phase not in IMPL_PHASES:
        if not _has_override_token(wf_name):
            block(f"BLOCKED: Phase {phase} does not allow code edits. Need phase6_implement+.")

    # 9. Override token skips TDD check
    if _has_override_token(wf_name):
        allow()

    # 10. RED test artifacts
    if phase in IMPL_PHASES:
        red_done = workflow.get("red_test_done", False) or workflow.get("ui_test_red_done", False)
        if not red_done:
            red_arts = [a for a in workflow.get("test_artifacts", [])
                       if a.get("phase") == "phase5_tdd_red"]
            if not red_arts:
                block("BLOCKED: No RED test artifacts. Run /tdd-red first.")

    # 11. Allow
    allow()


if __name__ == "__main__":
    main()
