"""Regressionstests für die Verdict-Pipeline-Fixes (Issue #77 + post_bash).

Issue #77: Der implementation-validator liefert laut eigener Definition
`VERDICT: HOLDS` und Confirmation-Blöcke (`Status: CONFIRMED`) — das Gate
akzeptierte nur `## Verdict`+`**VERIFIED**` und `- [x]`-Checkboxen. Drei
Abweichungen, ein Fix-Ort: adversary_dialog akzeptiert jetzt
  a) HOLDS als Synonym für VERIFIED,
  b) das Verdict einzeilig ('## Verdict: X') und als 'VERDICT: X'-Zeile,
  c) 'Status: CONFIRMED'-Blöcke als Checklisten-Fallback.
Zusätzlich: qa_gate persistiert bei reinen FORMfehlern kein BROKEN mehr —
ein Formfehler ist kein inhaltliches Urteil.

post_bash: stdout kommt im PostToolUse-Payload unter tool_response, nicht
tool_input — der alte Zugriff war immer leer (tote Auto-Erkennung). Dazu
Fail-Guard: Fehler-Evidenz im Output verhindert automatisches VERIFIED.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

from adversary_dialog import (  # noqa: E402
    validate_dialog_artifact,
    validate_dialog_artifact_ex,
    MIN_ROUNDS,
)

ROUNDS = "".join(
    f"### Runde {i}\n**Adversary:** Angriff {i}\n**Implementierer:** Beweis {i}\n\n"
    for i in range(1, MIN_ROUNDS + 1)
)

CHECKLIST = (
    "## Checkliste\n"
    "- [x] AC-1: Gate akzeptiert HOLDS — Beweis: test_holds\n"
    "- [x] AC-2: Formfehler schreibt kein BROKEN — Beweis: test_format\n\n"
)

HEADER = "# Adversary Dialog — verdict-pipeline\nSpec: docs/specs/x.md\n\n"


def _write(tmp_path: Path, body: str) -> str:
    p = tmp_path / "dialog.md"
    p.write_text(HEADER + body)
    return str(p)


# --- Teil 1a: HOLDS als Synonym für VERIFIED ---

class TestHoldsSynonym:
    def test_bold_holds_verdict_is_valid(self, tmp_path):
        art = _write(tmp_path, CHECKLIST + ROUNDS + "## Verdict\n**HOLDS**\n")
        valid, msg, kind = validate_dialog_artifact_ex(art)
        assert valid is True, msg
        assert kind is None

    def test_broken_still_fails_as_content(self, tmp_path):
        art = _write(tmp_path, CHECKLIST + ROUNDS + "## Verdict\n**BROKEN**\n")
        valid, msg, kind = validate_dialog_artifact_ex(art)
        assert valid is False
        assert kind == "content"

    def test_unknown_verdict_fails_as_format(self, tmp_path):
        art = _write(tmp_path, CHECKLIST + ROUNDS + "## Verdict\n**VIELLEICHT**\n")
        valid, msg, kind = validate_dialog_artifact_ex(art)
        assert valid is False
        assert kind == "format"
        assert "Unbekanntes Verdict" in msg


# --- Teil 1b: Einzeilige Verdict-Formen ---

class TestSingleLineVerdictForms:
    def test_heading_colon_form_is_valid(self, tmp_path):
        art = _write(tmp_path, CHECKLIST + ROUNDS + "## Verdict: VERIFIED\n")
        valid, msg = validate_dialog_artifact(art)
        assert valid is True, msg

    def test_uppercase_heading_colon_holds_is_valid(self, tmp_path):
        art = _write(tmp_path, CHECKLIST + ROUNDS + "## VERDICT: HOLDS\n")
        valid, msg = validate_dialog_artifact(art)
        assert valid is True, msg

    def test_bare_verdict_line_is_valid(self, tmp_path):
        """Das dokumentierte Abschlussformat des implementation-validator."""
        art = _write(
            tmp_path,
            CHECKLIST + ROUNDS
            + "═══════════════════════════════════════\n"
            + "VERDICT: HOLDS\n"
            + "═══════════════════════════════════════\n"
            + "Tests: 12 passed, 0 failed\n",
        )
        valid, msg = validate_dialog_artifact(art)
        assert valid is True, msg

    def test_last_verdict_wins_across_forms(self, tmp_path):
        """Fix-Loop: erst BROKEN (Bold-Form), nach dem Fix VERDICT: VERIFIED
        (Zeilen-Form) — der letzte Block zählt, formunabhängig."""
        art = _write(
            tmp_path,
            CHECKLIST + ROUNDS
            + "## Verdict\n**BROKEN**\n\n"
            + ROUNDS
            + "VERDICT: VERIFIED\n",
        )
        valid, msg = validate_dialog_artifact(art)
        assert valid is True, msg

    def test_verdict_quoted_in_fence_still_ignored(self, tmp_path):
        """Ein in einem Codeblock zitiertes VERIFIED darf ein echtes BROKEN
        nicht überschreiben (bestehende Fence-Regel gilt für alle Formen)."""
        art = _write(
            tmp_path,
            CHECKLIST + ROUNDS
            + "## Verdict\n**BROKEN**\n\n"
            + "```\nVERDICT: VERIFIED\n```\n",
        )
        valid, msg, kind = validate_dialog_artifact_ex(art)
        assert valid is False
        assert kind == "content"


# --- Teil 1c: Confirmation-Blöcke als Checklisten-Fallback ---

class TestConfirmationFallback:
    CONFIRMATIONS = (
        "Confirmation:\n"
        "  AC: AC-1\n"
        "  Code reference: core/hooks/x.py:17\n"
        "  Status: CONFIRMED\n\n"
        "Confirmation:\n"
        "  AC: AC-2\n"
        "  Code reference: core/hooks/x.py:42\n"
        "  Status: CONFIRMED\n\n"
    )

    def test_confirmed_blocks_count_as_checklist(self, tmp_path):
        art = _write(tmp_path, self.CONFIRMATIONS + ROUNDS + "## Verdict\n**VERIFIED**\n")
        valid, msg = validate_dialog_artifact(art)
        assert valid is True, msg
        assert "2 Punkte" in msg

    def test_checkboxes_still_take_precedence(self, tmp_path):
        """Eine offene Checkbox blockt auch dann, wenn daneben CONFIRMED-
        Blöcke stehen — Checkbox-Form bleibt maßgeblich, wenn vorhanden."""
        art = _write(
            tmp_path,
            "## Checkliste\n- [ ] AC-1: offen\n\n"
            + self.CONFIRMATIONS + ROUNDS + "## Verdict\n**VERIFIED**\n",
        )
        valid, msg, kind = validate_dialog_artifact_ex(art)
        assert valid is False
        assert kind == "content"

    def test_no_checklist_at_all_fails_as_format(self, tmp_path):
        art = _write(tmp_path, ROUNDS + "## Verdict\n**VERIFIED**\n")
        valid, msg, kind = validate_dialog_artifact_ex(art)
        assert valid is False
        assert kind == "format"


# --- Teil 2: qa_gate persistiert bei Formfehlern kein BROKEN ---

QA_COPY_FILES = ["qa_gate.py", "workflow.py", "hook_utils.py",
                 "config_loader.py", "override_token.py", "adversary_dialog.py"]


def _setup_fake_project(tmp_path: Path, wf_name: str) -> Path:
    fake_hooks = tmp_path / "fake_hooks"
    fake_hooks.mkdir()
    for fname in QA_COPY_FILES:
        shutil.copy(HOOKS_DIR / fname, fake_hooks / fname)
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{wf_name}.json").write_text(json.dumps({
        "name": wf_name, "current_phase": "phase6_implement",
        "adversary_verdict": None,
    }))
    return fake_hooks


def _run_qa_gate(fake_hooks: Path, tmp_path: Path, wf_name: str, args: list):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "OPENSPEC_ACTIVE_WORKFLOW": wf_name,
           "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, str(fake_hooks / "qa_gate.py")] + args,
        capture_output=True, text=True, cwd=str(fake_hooks), env=env,
    )


def _verdict_of(tmp_path: Path, wf_name: str):
    data = json.loads((tmp_path / ".claude" / "workflows" / f"{wf_name}.json").read_text())
    return data.get("adversary_verdict")


class TestQaGateFormatVsContent:
    def _green_output(self, tmp_path: Path) -> Path:
        out = tmp_path / "test-output.txt"
        out.write_text("test session starts\n5 passed in 1.2s\n" * 3)
        return out

    def test_holds_artifact_yields_verified(self, tmp_path):
        fake_hooks = _setup_fake_project(tmp_path, "wf1")
        art = tmp_path / "dialog.md"
        art.write_text(HEADER + CHECKLIST + ROUNDS + "VERDICT: HOLDS\n")
        result = _run_qa_gate(fake_hooks, tmp_path, "wf1",
                              [str(self._green_output(tmp_path)), "--checklist", str(art)])
        assert result.returncode == 0, result.stdout + result.stderr
        assert str(_verdict_of(tmp_path, "wf1")).startswith("VERIFIED")

    def test_format_error_does_not_persist_broken(self, tmp_path):
        """Vorher: 'Unbekanntes Verdict' schrieb BROKEN in den State —
        ein reiner Formfehler wurde zum inhaltlichen Urteil (Issue #77)."""
        fake_hooks = _setup_fake_project(tmp_path, "wf1")
        art = tmp_path / "dialog.md"
        art.write_text(HEADER + CHECKLIST + ROUNDS + "## Verdict\n**VIELLEICHT**\n")
        result = _run_qa_gate(fake_hooks, tmp_path, "wf1",
                              [str(self._green_output(tmp_path)), "--checklist", str(art)])
        assert result.returncode == 1
        assert _verdict_of(tmp_path, "wf1") is None

    def test_real_broken_artifact_still_persists_broken(self, tmp_path):
        fake_hooks = _setup_fake_project(tmp_path, "wf1")
        art = tmp_path / "dialog.md"
        art.write_text(HEADER + CHECKLIST + ROUNDS + "## Verdict\n**BROKEN**\n")
        result = _run_qa_gate(fake_hooks, tmp_path, "wf1",
                              [str(self._green_output(tmp_path)), "--checklist", str(art)])
        assert result.returncode == 1
        assert str(_verdict_of(tmp_path, "wf1")).startswith("BROKEN")


# --- Teil 3: post_bash liest stdout aus tool_response ---

POST_BASH_COPY = ["post_bash.py", "hook_utils.py", "config_loader.py"]


def _run_post_bash(tmp_path: Path, payload: dict):
    fake_hooks = tmp_path / "pb_hooks"
    if not fake_hooks.exists():
        fake_hooks.mkdir()
        for fname in POST_BASH_COPY:
            shutil.copy(HOOKS_DIR / fname, fake_hooks / fname)
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = "wf1"
    env.pop("CLAUDE_TOOL_INPUT", None)
    return subprocess.run(
        [sys.executable, str(fake_hooks / "post_bash.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env=env, cwd=str(tmp_path),
    )


def _make_workflow(tmp_path: Path):
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "wf1.json").write_text(json.dumps({
        "name": "wf1", "current_phase": "phase6_implement",
        "adversary_verdict": None,
    }))


class TestPostBashStdoutSource:
    def test_green_pytest_via_tool_response_sets_verified(self, tmp_path):
        _make_workflow(tmp_path)
        r = _run_post_bash(tmp_path, {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q"},
            "tool_response": {"stdout": "===== 5 passed in 1.2s =====\n", "stderr": ""},
        })
        assert r.returncode == 0, r.stderr
        assert str(_verdict_of(tmp_path, "wf1")).startswith("VERIFIED")

    def test_red_pytest_does_not_set_verified(self, tmp_path):
        """Fail-Guard: '2 failed, 3 passed' enthält 'passed' — ohne Guard
        würde die Auto-Erkennung false-passen."""
        _make_workflow(tmp_path)
        r = _run_post_bash(tmp_path, {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q"},
            "tool_response": {"stdout": "== 2 failed, 3 passed in 1.2s ==\n", "stderr": ""},
        })
        assert r.returncode == 0, r.stderr
        assert _verdict_of(tmp_path, "wf1") is None

    def test_non_test_command_ignored(self, tmp_path):
        _make_workflow(tmp_path)
        r = _run_post_bash(tmp_path, {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_response": {"stdout": "5 passed in 1.2s\n"},
        })
        assert r.returncode == 0
        assert _verdict_of(tmp_path, "wf1") is None

    def test_legacy_stdout_in_tool_input_still_works(self, tmp_path):
        _make_workflow(tmp_path)
        r = _run_post_bash(tmp_path, {
            "tool_name": "Bash",
            "tool_input": {"command": "cargo test", "stdout": "test result: ok. 8 passed\n"},
        })
        assert r.returncode == 0, r.stderr
        assert str(_verdict_of(tmp_path, "wf1")).startswith("VERIFIED")
