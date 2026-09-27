#!/usr/bin/env python3
"""
Post-Bash v3 — PostToolUse Hook for Bash

Extensible post-execution hook. Base implementation is minimal.
Module hooks (e.g., iOS build_lock_release) extend this via config.

Der Test-Output kommt im PostToolUse-Payload unter `tool_response`
(stdout/stderr), NICHT unter `tool_input` — der fruehere Zugriff auf
tool_input["stdout"] war immer leer (gefunden bei der Analyse zu #77/#82).

Beobachtung, kein Urteil (#253): ein erkannter Testlauf landet nur als
Hinweis in `last_test_run`. `adversary_verdict` wird hier nie gelesen oder
geschrieben — ein gruener Testlauf ersetzt den Adversary-Dialog nicht.

Exit Codes: 0 always (never blocks)
"""

from hook_utils import setup_path, find_project_root, get_tool_result, get_active_workflow_name, framework_disabled
setup_path()

import json
import os
import re
import sys
from pathlib import Path

_root = find_project_root()

# Fail-Guard: JEDE Fehler-Evidenz im Output macht den Lauf zu 'failed'.
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
    """Detect test framework output and record it as `last_test_run` (#253)."""
    # Only process test-like commands
    test_indicators = ["pytest", "jest", "xcodebuild", "go test", "cargo test",
                       "npm test", "yarn test", "vitest", "mocha"]
    hits = [t for t in test_indicators if t in command]
    if not hits:
        return
    # Laengster Treffer: 'cargo test' enthaelt 'go test' als Teilstring.
    runner = max(hits, key=len)

    if not stdout:
        return

    if _FAILURE_EVIDENCE_RE.search(stdout):
        _record_test_run("failed", runner)  # alter gruener Hinweis bleibt nicht stehen
        return

    # Check for framework-specific pass patterns (pytest, jest, xcodebuild, go, cargo)
    pass_patterns = [
        r"\b\d+\s+passed\b",
        r"Tests:.*passed",
        r"\*\* TEST SUCCEEDED \*\*",
        r"^ok\s+",
        r"test result: ok",
    ]

    if any(re.search(pattern, stdout, re.MULTILINE) for pattern in pass_patterns):
        _record_test_run("passed", runner)
    # Unbestimmbare Ausgabe: State bleibt unberuehrt.


def _record_test_run(result: str, runner: str) -> None:
    """Write `last_test_run` into the active workflow JSON — and nothing else.

    `runner` is the test indicator, deliberately not the command itself (it
    can carry inline credentials). Resolution is env/settings only (via
    get_active_workflow_name) — the .active symlink is intentionally not used.
    """
    import tempfile
    from datetime import datetime

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
            data["last_test_run"] = {
                "result": result,
                "runner": runner,
                "at": datetime.now().isoformat(timespec="seconds"),
            }
            _atomic_write(wf_file, data)
        except (OSError, json.JSONDecodeError):
            pass


def main():
    # Testlauf-Erkennung gehoert zum Workflow; ohne ihn gibt es keine Phase,
    # in die ein Test-Ergebnis gemeldet werden koennte (#132).
    if framework_disabled():
        sys.exit(0)

    payload = get_tool_result()
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "")
    if not command:
        sys.exit(0)

    _detect_test_output(command, _extract_stdout(payload))

    sys.exit(0)


if __name__ == "__main__":
    main()
