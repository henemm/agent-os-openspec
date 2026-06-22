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

from hook_utils import setup_path, find_project_root, get_tool_input, block, allow, get_active_workflow_name, gate_diagnostics
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

# Credential patterns to detect hardcoded secrets in bash commands
HARDCODED_CREDENTIAL_PATTERNS = [
    (r"sk-[A-Za-z0-9]{20,}", "API key (sk- prefix)"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub Personal Access Token"),
    (r"xoxb-[A-Za-z0-9-]{20,}", "Slack Bot token"),
    (r"Bearer\s+(?!\$|\{|<)[A-Za-z0-9._~+/=-]{40,}", "hardcoded Bearer token"),
    (r"(?:password|passwd)\s*=\s*['\"][^'\"\$\{<]{8,}['\"]", "hardcoded password"),
    (r"(?:api_key|apikey|api-key)\s*=\s*['\"][^'\"\$\{<]{8,}['\"]", "hardcoded API key"),
]

# E2E scope detection patterns (configurable via config.yaml → e2e_scope)
E2E_DOCS_PATTERNS = [r'^docs/', r'\.md$', r'^\.claude/']
E2E_FRONTEND_PATTERNS = [r'^(frontend|ui|client)/', r'^src/.*\.(svelte|vue|tsx|jsx|css|scss|html)$']
E2E_BACKEND_PATTERNS = [r'^(src|api|internal|cmd|backend|server)/']


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
    config = _load_config_values()
    project_whitelist = config.get("bash_gate", {}).get("whitelist", [])
    return any(allowed in command for allowed in WHITELIST_COMMANDS + project_whitelist)


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
    """Read active workflow via OPENSPEC_ACTIVE_WORKFLOW env var or settings.local.json fallback.

    Resolution is env/settings only — the .active symlink is intentionally
    not used (single source of truth, matching workflow.py).
    """
    name = get_active_workflow_name()
    if not name:
        return None
    wf_file = _root / ".claude" / "workflows" / f"{name}.json"
    if wf_file.exists():
        try:
            return json.loads(wf_file.read_text())
        except (OSError, json.JSONDecodeError):
            pass
    return None


def _contains_hardcoded_credentials(command: str, config: dict) -> str | None:
    """Return credential type if command contains a hardcoded secret, else None."""
    patterns = config.get("credentials_guard", {}).get("patterns", HARDCODED_CREDENTIAL_PATTERNS)
    for pattern, cred_type in patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return cred_type
    return None


def _detect_e2e_scope(staged_files: list, config: dict) -> str:
    """Determine E2E test scope from staged file paths."""
    docs = config.get("e2e_scope", {}).get("docs_patterns", E2E_DOCS_PATTERNS)
    front = config.get("e2e_scope", {}).get("frontend_patterns", E2E_FRONTEND_PATTERNS)
    back = config.get("e2e_scope", {}).get("backend_patterns", E2E_BACKEND_PATTERNS)
    non_doc = [f for f in staged_files if not any(re.search(p, f) for p in docs)]
    if not non_doc:
        return "docs-only"
    has_front = any(any(re.search(p, f) for p in front) for f in non_doc)
    has_back = any(any(re.search(p, f) for p in back) for f in non_doc)
    if has_front and has_back:
        return "full-stack"
    if has_front:
        return "frontend-only"
    if has_back:
        return "backend"
    return "full-stack"


def _write_e2e_scope(wf: dict, scope: str) -> None:
    """Write e2e_scope to the active workflow JSON atomically (never raises)."""
    import tempfile
    name = wf.get("name", "")
    if not name:
        return
    wf_file = _root / ".claude" / "workflows" / f"{name}.json"
    if not wf_file.exists():
        return
    try:
        data = json.loads(wf_file.read_text())
        data["e2e_scope"] = scope
        fd, tmp = tempfile.mkstemp(dir=str(wf_file.parent), suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp, str(wf_file))
    except (OSError, json.JSONDecodeError):
        pass


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

    # 4b. Hardcoded credentials in command
    if not _is_whitelisted(command):
        cred_type = _contains_hardcoded_credentials(command, config)
        if cred_type:
            block(f"BLOCKED: Hardcoded {cred_type} detected. Use env vars or secrets.env instead.")

    # 5. Git commit gates
    if "git commit" in command:
        import subprocess

        # Get staged files (reused across 5a, 5b, 5c)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=_root, capture_output=True, text=True
        )
        staged_list = staged.stdout.strip().splitlines()

        # 5a. Configurable required staged files
        required_files = config.get("pre_commit", {}).get("required_staged_files", [])
        for req_file in required_files:
            if req_file not in staged_list:
                diff = subprocess.run(
                    ["git", "diff", "--name-only", "--", req_file],
                    cwd=_root, capture_output=True, text=True
                )
                if diff.stdout.strip():
                    block(f"BLOCKED: {req_file} has unstaged changes. Stage it first.")

        # 5b. Rebase-Pflicht: Branch darf nicht hinter origin/main zurückliegen
        wf = _read_active_workflow()
        if wf:
            try:
                fetch = subprocess.run(
                    ["git", "fetch", "origin", "main", "--quiet"],
                    cwd=_root, capture_output=True, timeout=10
                )
                if fetch.returncode == 0:
                    behind_result = subprocess.run(
                        ["git", "rev-list", "--count", "HEAD..origin/main"],
                        cwd=_root, capture_output=True, text=True, timeout=5
                    )
                    behind = int(behind_result.stdout.strip() or "0")
                    if behind > 0:
                        block(
                            f"BLOCKED — Branch ist {behind} Commit(s) hinter origin/main.\n"
                            "Bitte erst: git fetch origin && git rebase origin/main"
                        )
                # fetch returncode != 0 → kein Netz → silent skip
            except (subprocess.TimeoutExpired, OSError, ValueError):
                pass  # Netzwerk nicht erreichbar → kein Block

        # 5c. Adversary verdict check (if in phase6+)
        if wf:
            phase = wf.get("current_phase", "")
            if phase in ("phase6_implement", "phase6b_adversary", "phase7_validate"):
                # Bug + Feature fast-track: no adversary verdict required
                if wf.get("workflow_type") in ("bug", "feature-fast"):
                    pass
                else:
                    verdict = str(wf.get("adversary_verdict", "") or "")
                    if verdict.startswith("VERIFIED"):
                        pass  # green
                    elif verdict.startswith("AMBIGUOUS"):
                        if not wf.get("adversary_ambiguous_override"):
                            block("BLOCKED: Adversary verdict is AMBIGUOUS. "
                                  "Review findings, then: workflow.py override-ambiguous '<reason>' "
                                  + gate_diagnostics(wf, verdict="AMBIGUOUS"))
                    else:
                        has_override = False
                        try:
                            from override_token import has_valid_token
                            has_override = has_valid_token(wf.get("name"))
                        except ImportError:
                            pass
                        if not has_override:
                            block("BLOCKED: Adversary verdict missing or not VERIFIED. Run adversary validation first. "
                                  + gate_diagnostics(wf, verdict=(verdict or "keins")))

            # 5d. E2E scope detection (informational — never blocks)
            scope = _detect_e2e_scope(staged_list, config)
            _write_e2e_scope(wf, scope)
            print(f"E2E scope: {scope}", file=sys.stderr)

    # 6. Allow
    allow()


if __name__ == "__main__":
    main()
