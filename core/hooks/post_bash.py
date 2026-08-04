#!/usr/bin/env python3
"""
Post-Bash v3 — PostToolUse Hook for Bash

Extensible post-execution hook. Base implementation is minimal.
Module hooks (e.g., iOS build_lock_release) extend this via config.

Der Test-Output kommt im PostToolUse-Payload unter `tool_response`
(stdout/stderr), NICHT unter `tool_input` — der fruehere Zugriff auf
tool_input["stdout"] war immer leer, die dokumentierte automatische
Verdict-Erkennung damit funktionslos (gefunden bei der Analyse zu #77/#82).

Exit Codes: 0 always (never blocks)
"""

from hook_utils import setup_path, find_project_root, get_tool_result, get_active_workflow_name
setup_path()

import json
import os
import re
import sys
from pathlib import Path

_root = find_project_root()

# Fail-Guard: bei JEDER Fehler-Evidenz im Output wird NIE VERIFIED gesetzt.
# Ohne diesen Guard wuerde '2 failed, 3 passed' ueber das 'passed'-Muster
# faelschlich als gruen gewertet (False-Pass-Richtung, ausgeschlossen).
_FAILURE_EVIDENCE_RE = re.compile(
    r"\b[1-9]\d*\s+(?:failed|errors?)\b"
    r"|--- FAIL:"
    r"|^FAIL\b"
    r"|\*\* TEST FAILED \*\*"
    r"|test result: FAILED",
    re.MULTILINE | re.IGNORECASE,
)


def _extract_stdout(payload: dict) -> str:
    """stdout aus dem PostToolUse-Payload (tool_response) lesen.

    tool_response ist bei Bash ein Objekt mit stdout/stderr; aeltere
    Wrapper lieferten teils einen String oder ein 'output'-Feld.
    Legacy-Fallback: manche Test-Harnesse legten stdout in tool_input.
    """
    resp = payload.get("tool_response", {})
    if isinstance(resp, str) and resp:
        return resp
    if isinstance(resp, dict):
        out = resp.get("stdout") or resp.get("output") or ""
        if isinstance(out, str) and out:
            return out
    tool_input = payload.get("tool_input") or {}
    legacy = tool_input.get("stdout", "")
    return legacy if isinstance(legacy, str) else ""


def _detect_test_output(command: str, stdout: str) -> None:
    """Detect test framework output and update adversary_verdict in active workflow."""
    # Only process test-like commands
    test_indicators = ["pytest", "jest", "xcodebuild", "go test", "cargo test",
                       "npm test", "yarn test", "vitest", "mocha"]
    if not any(t in command for t in test_indicators):
        return

    if not stdout:
        return

    if _FAILURE_EVIDENCE_RE.search(stdout):
        return  # Fehler-Evidenz → niemals automatisch VERIFIED

    # Check for framework-specific pass patterns
    pass_patterns = [
        (r"\b\d+\s+passed\b", "pytest"),
        (r"Tests:.*passed", "jest"),
        (r"\*\* TEST SUCCEEDED \*\*", "xcodebuild"),
        (r"^ok\s+", "go_test"),
        (r"test result: ok", "cargo_test"),
    ]

    for pattern, framework in pass_patterns:
        if re.search(pattern, stdout, re.MULTILINE):
            _set_adversary_verdict(f"VERIFIED:{framework}")
            return


def _set_adversary_verdict(verdict: str) -> None:
    """Update adversary_verdict in the active workflow JSON.

    Resolution is env/settings only (via get_active_workflow_name) — the
    .active symlink is intentionally not used (single source of truth).
    """
    import tempfile

    def _atomic_write(wf_file: Path, data: dict) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(wf_file.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.rename(tmp, str(wf_file))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    name = get_active_workflow_name()
    if not name:
        return
    wf_file = _root / ".claude" / "workflows" / f"{name}.json"
    if wf_file.exists():
        try:
            data = json.loads(wf_file.read_text())
            data["adversary_verdict"] = verdict
            _atomic_write(wf_file, data)
        except (OSError, json.JSONDecodeError):
            pass


def main():
    payload = get_tool_result()
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "")
    if not command:
        sys.exit(0)

    _detect_test_output(command, _extract_stdout(payload))

    sys.exit(0)


if __name__ == "__main__":
    main()
