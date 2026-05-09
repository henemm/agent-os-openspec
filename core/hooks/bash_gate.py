#!/usr/bin/env python3
"""
Bash Gate v3 — Consolidated PreToolUse Hook for Bash

Replaces 15 separate hooks with 1. Sequential logic:

1. Stop-Lock → BLOCK
2. Git commands → ALLOW (fast path)
3. State-Integrity: protected file + write indicator → BLOCK (whitelist)
4. Secrets: sensitive file + content output → BLOCK
5. Git Commit gates (configurable required staged files, adversary verdict)
6. ALLOW

Project-specific gates (sim_enforcer, build_lock) belong in module hooks.

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

SENSITIVE_PATTERNS = [
    r"\.env", r"credentials\.json", r"service[_-]?account.*\.json",
    r"_key", r"_secret", r"\.pem$", r"\.key$",
]

ALWAYS_BLOCKED_SECRETS = [
    r"credentials\.json", r"service[_-]?account.*\.json",
    r"_key", r"_secret", r"\.pem$", r"\.key$",
]

CONTENT_OUTPUT_COMMANDS = [
    r"\bcat\b", r"\bhead\b", r"\btail\b", r"\bless\b", r"\bmore\b",
    r"\bsed\b.*-n.*p", r"\bawk\b.*print",
]

PROTECTED_FILE_PATTERNS = [
    r"\.claude/workflows/[^\s]*\.json",
    r"workflow_state\.json",
    r"user_override_token\.json",
    r"\.claude/hooks/[^\s]*\.py",
    r"\.claude/settings\.json",
]

WRITE_INDICATORS = [
    r"json\.dump", r"open\(", r"write\(", r"sed\s+-i", r"mv\s", r"cp\s",
    r"echo\s", r"printf\s", r"python3?\s+-c", r"tee\s", r"rm\s",
    r"touch\s", r"cat\s*<<", r"unlink", r"truncate",
]

WHITELIST_COMMANDS = [
    "workflow.py", "qa_gate.py",
    "git add", "git commit", "git diff",
    "git status", "git log", "git push",
]


# --- Config loading ---

def _load_config_values() -> dict:
    try:
        from config_loader import load_config
        return load_config()
    except Exception:
        return {}


# --- Helpers ---

_root = find_project_root()


def _is_stop_locked() -> bool:
    lock = _root / ".claude" / "stop_lock.json"
    if not lock.exists():
        return False
    try:
        return json.loads(lock.read_text()).get("enabled", False)
    except (json.JSONDecodeError, OSError):
        return False


def _is_whitelisted(command: str) -> bool:
    return any(allowed in command for allowed in WHITELIST_COMMANDS)


def _references_protected(command: str) -> bool:
    return any(re.search(p, command) for p in PROTECTED_FILE_PATTERNS)


def _has_write_indicator(command: str) -> bool:
    for p in WRITE_INDICATORS:
        if re.search(p, command):
            return True
    for m in re.finditer(r"(?<!\d)>{1,2}\s*(\S+)", command):
        if m.group(1) != "/dev/null":
            return True
    return False


def _is_sensitive(path: str, patterns: list) -> bool:
    return any(re.search(p, path, re.IGNORECASE) for p in patterns)


def _outputs_content(command: str) -> bool:
    return any(re.search(p, command) for p in CONTENT_OUTPUT_COMMANDS)


def _read_active_workflow() -> dict | None:
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


# --- Main ---

def main():
    tool_input = get_tool_input()
    command = tool_input.get("command", "")
    if not command:
        allow()

    config = _load_config_values()

    # 1. Stop-lock
    if _is_stop_locked():
        block("BLOCKED: Stop-lock active.")

    # 2. Git commands fast path
    if command.lstrip().startswith("git ") and "git commit" not in command:
        allow()

    # 3. State-integrity: protected file + write indicator
    if _references_protected(command):
        if _is_whitelisted(command):
            allow()
        if _has_write_indicator(command):
            block("BLOCKED: Direct state file manipulation. Use workflow.py CLI.")

    # 4. Secrets guard
    sensitive_patterns = config.get("secrets_guard", {}).get("sensitive_patterns", SENSITIVE_PATTERNS)
    always_blocked = config.get("secrets_guard", {}).get("always_blocked", ALWAYS_BLOCKED_SECRETS)

    if _is_sensitive(command, sensitive_patterns) and _outputs_content(command):
        if _is_sensitive(command, always_blocked):
            block("BLOCKED: Secrets guard — sensitive credentials/keys.")
        staging = (_root / ".claude" / "staging").exists()
        if not staging:
            block("BLOCKED: Secrets guard — .env file. Enable staging mode with: touch .claude/staging")

    # 5. Git commit gates
    if "git commit" in command:
        import subprocess

        # 5a. Configurable required staged files
        required_files = config.get("pre_commit", {}).get("required_staged_files", [])
        if required_files:
            staged = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=_root, capture_output=True, text=True
            )
            staged_list = staged.stdout.strip().splitlines()
            for req_file in required_files:
                if req_file not in staged_list:
                    # Check if file has changes
                    diff = subprocess.run(
                        ["git", "diff", "--name-only", "--", req_file],
                        cwd=_root, capture_output=True, text=True
                    )
                    if diff.stdout.strip():
                        block(f"BLOCKED: {req_file} has unstaged changes. Stage it first.")

        # 5b. Adversary verdict check (if in phase6+)
        wf = _read_active_workflow()
        if wf:
            phase = wf.get("current_phase", "")
            if phase in ("phase6_implement", "phase6b_adversary", "phase7_validate"):
                verdict = str(wf.get("adversary_verdict", "") or "")
                if verdict.startswith("VERIFIED"):
                    pass  # green
                elif verdict.startswith("AMBIGUOUS"):
                    # AMBIGUOUS requires explicit override-ambiguous (S4)
                    if not wf.get("adversary_ambiguous_override"):
                        block("BLOCKED: Adversary verdict is AMBIGUOUS. "
                              "Review findings, then: workflow.py override-ambiguous '<reason>'")
                else:
                    has_override = False
                    try:
                        from override_token import has_valid_token
                        has_override = has_valid_token(wf.get("name"))
                    except ImportError:
                        pass
                    if not has_override:
                        block("BLOCKED: Adversary verdict missing or not VERIFIED. Run adversary validation first.")

    # 6. Allow
    allow()


if __name__ == "__main__":
    main()
