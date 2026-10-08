"""TDD RED — Issue #345 (Scheibe 1): `qa_gate.py --run "<Befehl>"` fuehrt den
Testbefehl selbst aus, wertet den echten Exit-Code ("rot gewinnt") und legt
Artefaktdatei plus gesperrten Stempel `qa_run_stamp` ab.

Spec: docs/specs/feat-345-qa-gate-selbst-ausfuehren.md (AC-1 bis AC-11).

Alle Tests laufen von aussen ueber echte Prozesse: `core/hooks/qa_gate.py`,
`workflow.py` und `bash_gate.py` DIESES Arbeitsbaums als Subprozess gegen eine
Wegwerf-Sandbox in tmp_path (Muster: test_bash_gate_erkennung_299.py,
test_adversary_evidence_gate_253.py). Das `.claude/` dieses Repos wird nie
beruehrt, kein Netz, keine Wartezeit ueber wenige Sekunden.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

WF = "wf-345"
STAMP = "qa_run_stamp"
DEFAULT_OUT = f"docs/artifacts/{WF}/test-run-output.txt"
GREEN_CMD = "echo '3 passed in 0.1s'"
UNREADABLE = "Exit 0, Ausgabe nicht auswertbar"


# --- Sandbox + Aufrufe ------------------------------------------------------

def _env(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK",
                        "CLAUDE_TOOL_INPUT", "PYTHONPATH")
           and not k.startswith("GIT_")}
    env["CLAUDE_PROJECT_DIR"] = str(root)
    return env


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Haupt-Repo-Sandbox (kein Worktree) mit aktivem Workflow in phase6."""
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    claude = root / ".claude"
    (claude / "workflows").mkdir(parents=True)
    (claude / "active_workflow").write_text(WF + "\n")
    (claude / "workflows" / f"{WF}.json").write_text(json.dumps({
        "name": WF, "workflow_type": "feature", "current_phase": "phase6_implement",
        "adversary_verdict": None, "test_artifacts": [], "phase_log": [],
    }, indent=2))
    return root


def _hook(root: Path, script: str, args: list, timeout: int = 60, extra_env=None):
    env = _env(root)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script), *args],
        capture_output=True, text=True, cwd=str(root), env=env,
        stdin=subprocess.DEVNULL, timeout=timeout,
    )


def _qa_run(root: Path, cmd: str, *extra: str):
    return _hook(root, "qa_gate.py", ["--run", cmd, *extra])


def _state(root: Path) -> dict:
    return json.loads((root / ".claude" / "workflows" / f"{WF}.json").read_text())


def _verdict(root: Path) -> str:
    return _state(root).get("adversary_verdict") or ""


def _stamp(root: Path) -> dict:
    state = _state(root)
    assert STAMP in state, f"kein {STAMP} im Workflow-State: {sorted(state)}"
    return state[STAMP]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _out(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


# --- AC-1 bis AC-5: Urteilsregel "rot gewinnt" ------------------------------

def test_nonzero_exit_is_broken_regardless_of_text(project):
    """AC-1: Exit 1 mit '5 passed' im Text -> BROKEN, Gate-Exit 1."""
    r = _qa_run(project, "echo '5 passed in 0.1s'; exit 1")
    assert r.returncode == 1, _out(r)
    assert _verdict(project).startswith("BROKEN:"), _out(r)
    assert _stamp(project)["exit_code"] == 1


def test_exit_zero_green_output_is_verified(project):
    """AC-2: Exit 0 mit pytest-Ausgabe '3 passed in 0.1s' -> VERIFIED."""
    r = _qa_run(project, GREEN_CMD)
    assert r.returncode == 0, _out(r)
    assert _verdict(project).startswith("VERIFIED:"), _out(r)
    assert "3 passed" in _out(r), "Testausgabe wird auf stdout gespiegelt"


def test_exit_zero_only_skipped_is_not_verified(project):
    """AC-3: Exit 0, '0 passed, 4 skipped' -> gesetzt, aber nicht VERIFIED (#275)."""
    r = _qa_run(project, "echo '0 passed, 4 skipped in 0.1s'")
    stamp = _stamp(project)
    assert stamp["exit_code"] == 0 and stamp["source"] == "run", stamp
    verdict = _verdict(project)
    assert verdict, f"Verdict muss gesetzt sein: {_out(r)}"
    assert not verdict.startswith("VERIFIED"), verdict


def test_exit_zero_unknown_format_is_ambiguous(project):
    """AC-4: Exit 0, unbekanntes Format (< 100 Byte) -> AMBIGUOUS, kein Groessenfilter."""
    r = _qa_run(project, "echo hallo")
    assert r.returncode == 0, _out(r)
    verdict = _verdict(project)
    assert verdict.startswith("AMBIGUOUS:"), _out(r)
    assert UNREADABLE in verdict
    assert "too small" not in _out(r) and "fabricated" not in _out(r)


def test_pipefail_makes_failing_pipe_broken(project):
    """AC-5: `false | true` -> BROKEN, weil mit pipefail ausgefuehrt wird."""
    r = _qa_run(project, "echo '3 passed in 0.1s'; false | true")
    assert r.returncode == 1, _out(r)
    assert _verdict(project).startswith("BROKEN:"), _out(r)
    assert _stamp(project)["exit_code"] != 0


# --- AC-6: Timeout beendet die ganze Prozessgruppe --------------------------

def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_timeout_is_broken_and_process_group_killed(project):
    """AC-6: Lauf ueber --timeout 1 -> BROKEN mit Timeout-Meldung, Kind tot."""
    pidfile = project / "child.pid"
    cmd = f"sleep 30 & echo $! > {pidfile}; wait"
    start = time.monotonic()
    r = _qa_run(project, cmd, "--timeout", "1")
    assert time.monotonic() - start < 20, "Timeout griff nicht"
    assert r.returncode == 1, _out(r)
    verdict = _verdict(project)
    assert verdict.startswith("BROKEN:") and "Timeout" in verdict, _out(r)
    assert _stamp(project)["exit_code"] != 0
    pid = int(pidfile.read_text().strip())
    deadline = time.monotonic() + 3
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _alive(pid), f"Kindprozess {pid} lebt nach dem Timeout noch"


# --- AC-7 / AC-8: Artefakt und Stempel --------------------------------------

def test_artifact_written_and_stamp_sha_matches(project):
    """AC-7: --out-Datei mit stdout+stderr, Stempel source/exit_code/sha passen."""
    out_rel = "docs/artifacts/eigen/neu/run.txt"  # Verzeichnisse existieren noch nicht
    cmd = "echo '3 passed in 0.1s'; echo STDERR_LINE_345 >&2"
    r = _qa_run(project, cmd, "--out", out_rel)
    out_file = project / out_rel
    assert out_file.exists(), _out(r)
    content = out_file.read_text()
    assert "3 passed in 0.1s" in content and "STDERR_LINE_345" in content, content
    stamp = _stamp(project)
    assert stamp["source"] == "run"
    assert stamp["exit_code"] == 0
    assert stamp["output_sha256"] == _sha256_file(out_file)
    assert Path(stamp["output_path"]).name == "run.txt"
    assert stamp.get("timestamp"), stamp


def test_stamp_stores_command_hash_never_plaintext(project):
    """AC-8: nur SHA-256 des Befehls im Stempel, Klartext nirgends im State."""
    cmd = "echo secret-token-123 MARKER_345_XYZ >/dev/null; echo '3 passed in 0.1s'"
    r = _qa_run(project, cmd)
    stamp = _stamp(project)
    assert stamp["command_sha256"] == hashlib.sha256(cmd.encode()).hexdigest(), _out(r)
    raw = (project / ".claude" / "workflows" / f"{WF}.json").read_text()
    assert "MARKER_345_XYZ" not in raw
    assert "secret-token-123" not in raw
    assert (project / DEFAULT_OUT).exists(), "Default-Artefaktpfad fehlt"


# --- AC-9: Stempel per set-field gesperrt -----------------------------------

def test_set_field_on_stamp_key_is_blocked(project):
    """AC-9: `workflow.py set-field qa_run_stamp …` -> BLOCKED, Exit 1, unveraendert."""
    path = project / ".claude" / "workflows" / f"{WF}.json"
    data = json.loads(path.read_text())
    original = {"source": "run", "exit_code": 0, "output_sha256": "a" * 64}
    data[STAMP] = original
    path.write_text(json.dumps(data, indent=2))
    forged = json.dumps({"source": "run", "exit_code": 0, "output_sha256": "b" * 64})
    r = _hook(project, "workflow.py", ["set-field", STAMP, forged])
    assert r.returncode == 1, _out(r)
    assert "BLOCKED" in _out(r)
    assert _state(project)[STAMP] == original


# --- AC-10: bash_gate stellt --run nicht per Whitelist frei -----------------

def _bash_gate(root: Path, command: str):
    payload = json.dumps({"command": command})
    return _hook(root, "bash_gate.py", [], extra_env={"CLAUDE_TOOL_INPUT": payload})


def test_bash_gate_does_not_whitelist_qa_gate_run(project):
    """AC-10: --run mit Schreibzugriff auf State -> 3b blockt; Datei-Modus frei."""
    run_cmd = 'python3 .claude/hooks/qa_gate.py --run "echo x > .claude/workflows/a.json"'
    r = _bash_gate(project, run_cmd)
    assert r.returncode == 2, f"--run rutscht durch die Whitelist: {_out(r)}"
    assert "Direct state file manipulation" in _out(r)
    file_cmd = f"python3 .claude/hooks/qa_gate.py docs/artifacts/{WF}/test-output.txt"
    r = _bash_gate(project, file_cmd)
    assert r.returncode == 0, f"Datei-Modus muss erlaubt bleiben: {_out(r)}"


# --- AC-11: Datei-Modus unveraendert, vermerkt source "file" ----------------

def test_file_mode_unchanged_and_marks_source_file(project):
    """AC-11: Datei-Modus: gleiches Verdict/Meldung, Altersgrenze, Stempel 'file'."""
    out = project / "test-output.txt"
    out.write_text("test session starts\n5 passed in 1.2s\n" * 3)
    r = _hook(project, "qa_gate.py", [str(out)])
    assert r.returncode == 0, _out(r)
    assert _verdict(project).startswith("VERIFIED:Tests PASSED"), _out(r)
    stamp = _stamp(project)
    assert stamp["source"] == "file"
    assert stamp["output_sha256"] == _sha256_file(out)
    assert "command_sha256" not in stamp and "exit_code" not in stamp, stamp
    old = project / "old-output.txt"
    old.write_text("test session starts\n5 passed in 1.2s\n" * 3)
    past = time.time() - 31 * 60
    os.utime(old, (past, past))
    r = _hook(project, "qa_gate.py", [str(old)])
    assert r.returncode == 1 and "min old" in _out(r), _out(r)
