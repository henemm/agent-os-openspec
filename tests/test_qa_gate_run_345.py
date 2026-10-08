"""TDD RED — Issue #345 (Scheibe 1, Spec v2.0): `qa_gate.py --run` fuehrt den in
der Projekt-Config hinterlegten Testbefehl (`qa_gate.test_command`) selbst aus,
wertet den echten Exit-Code ("rot gewinnt") und legt die Artefaktdatei am
festen Pfad plus den gesperrten Stempel `qa_run_stamp` ab. Im `--run`-Modus
nimmt die Kommandozeile keinen Befehl und kein `--out` an.

Spec: docs/specs/feat-345-qa-gate-selbst-ausfuehren.md (AC-1 bis AC-13).

Alle Tests laufen von aussen ueber echte Prozesse: `core/hooks/qa_gate.py`,
`workflow.py` und `bash_gate.py` DIESES Arbeitsbaums als Subprozess gegen eine
Wegwerf-Sandbox in tmp_path (Muster: test_bash_gate_erkennung_299.py,
test_adversary_evidence_gate_253.py). Der Testbefehl steht in der
Sandbox-`.claude/config.yaml`: config_loader nimmt sie ungeprueft, eine
Root-`config.yaml` dagegen nur mit Plugin-Block (#372). Das `.claude/` dieses
Repos wird nie beruehrt, kein Netz, keine Wartezeit ueber wenige Sekunden.
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
FIXED_OUT = f"docs/artifacts/{WF}/test-run-output.txt"
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


def _configure(root: Path, cmd: "str | None", **extra) -> None:
    """Sandbox-Config mit `qa_gate.test_command` (JSON-Quoting ist gueltiges YAML)."""
    lines = ["qa_gate:"]
    if cmd is not None:
        lines.append(f"  test_command: {json.dumps(cmd)}")
    for key, value in extra.items():
        lines.append(f"  {key}: {json.dumps(value)}")
    (root / ".claude" / "config.yaml").write_text("\n".join(lines) + "\n")


def _hook(root: Path, script: str, args: list, timeout: int = 60, extra_env=None):
    env = _env(root)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script), *args],
        capture_output=True, text=True, cwd=str(root), env=env,
        stdin=subprocess.DEVNULL, timeout=timeout,
    )


def _qa_run(root: Path, cmd: str, *extra: str):
    """Befehl in die Sandbox-Config schreiben, dann `qa_gate.py --run` ohne Befehlstext."""
    _configure(root, cmd)
    return _hook(root, "qa_gate.py", ["--run", *extra])


def _state_path(root: Path) -> Path:
    return root / ".claude" / "workflows" / f"{WF}.json"


def _state(root: Path) -> dict:
    return json.loads(_state_path(root).read_text())


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
    """AC-7: Datei am festen Pfad mit stdout+stderr, Stempel source/exit_code/sha passen."""
    cmd = "echo '3 passed in 0.1s'; echo STDERR_LINE_345 >&2"
    r = _qa_run(project, cmd)
    out_file = project / FIXED_OUT  # docs/artifacts/<wf>/ existierte vorher nicht
    assert out_file.exists(), _out(r)
    content = out_file.read_text()
    assert "3 passed in 0.1s" in content and "STDERR_LINE_345" in content, content
    stamp = _stamp(project)
    assert stamp["source"] == "run"
    assert stamp["exit_code"] == 0
    assert stamp["output_sha256"] == _sha256_file(out_file)
    assert str(stamp["output_path"]).endswith(FIXED_OUT), stamp
    assert stamp.get("timestamp"), stamp


def test_stamp_stores_command_hash_never_plaintext(project):
    """AC-8: nur SHA-256 des konfigurierten Befehls im Stempel, Klartext nirgends im State."""
    cmd = "echo secret-token-123 MARKER_345_XYZ >/dev/null; echo '3 passed in 0.1s'"
    r = _qa_run(project, cmd)
    stamp = _stamp(project)
    assert stamp["command_sha256"] == hashlib.sha256(cmd.encode()).hexdigest(), _out(r)
    raw = _state_path(project).read_text()
    assert "MARKER_345_XYZ" not in raw
    assert "secret-token-123" not in raw


# --- AC-9: Stempel per set-field gesperrt -----------------------------------

def test_set_field_on_stamp_key_is_blocked(project):
    """AC-9: `workflow.py set-field qa_run_stamp …` -> BLOCKED, Exit 1, unveraendert."""
    path = _state_path(project)
    data = json.loads(path.read_text())
    original = {"source": "run", "exit_code": 0, "output_sha256": "a" * 64}
    data[STAMP] = original
    path.write_text(json.dumps(data, indent=2))
    forged = json.dumps({"source": "run", "exit_code": 0, "output_sha256": "b" * 64})
    r = _hook(project, "workflow.py", ["set-field", STAMP, forged])
    assert r.returncode == 1, _out(r)
    assert "BLOCKED" in _out(r)
    assert _state(project)[STAMP] == original


# --- AC-10 / AC-11: Fehlbedienung wird vor jeder Ausfuehrung abgewiesen ------

_REJECTED_ARGS = [
    ["--run", "echo x > .claude/workflows/a.json"],  # Befehlstext als Argument
    ["--run", "--out", f".claude/workflows/{WF}.json"],  # frei gewaehlter Ausgabepfad
    ["--run", "--bogus"],  # unbekannte Option
    ["--run", "--timeout", "0"],  # nicht positive Sekundenzahl
    ["--run", "--timeout", "abc"],  # nicht ganzzahlig
]


def test_run_rejects_command_argument_and_out_option(project):
    """AC-10: Befehlstext/--out/Unbekanntes -> Exit 1, nichts ausgefuehrt, State
    byte-identisch; --infra mit --checklist und --no-visual wird angenommen."""
    marker = project / "ran.marker"
    _configure(project, f"touch {marker}; {GREEN_CMD}")
    before = _state_path(project).read_bytes()
    for args in _REJECTED_ARGS:
        r = _hook(project, "qa_gate.py", args)
        assert r.returncode == 1, f"{args}: {_out(r)}"
        assert not marker.exists(), f"{args}: konfigurierter Befehl lief trotzdem"
        assert not (project / ".claude" / "workflows" / "a.json").exists(), args
        assert _state_path(project).read_bytes() == before, f"{args}: State veraendert"
        assert not (project / FIXED_OUT).exists(), f"{args}: Artefakt geschrieben"
    accepted = ["--run", "--infra", "--checklist", f"docs/artifacts/{WF}/checklist.md",
                "--no-visual", "Infra-Ticket"]
    r = _hook(project, "qa_gate.py", accepted)
    assert marker.exists(), f"--infra-Aufruf wurde abgewiesen: {_out(r)}"
    assert _stamp(project)["source"] == "run", _out(r)


@pytest.mark.parametrize("config_text", [
    None,  # keine Config-Datei
    "qa_gate:\n  run_timeout: 5\n",  # Abschnitt ohne test_command
    'qa_gate:\n  test_command: ""\n',  # leerer Befehl
])
def test_missing_test_command_is_usage_error(project, config_text):
    """AC-11: kein/leerer qa_gate.test_command -> Exit 1 mit Schluesselhinweis,
    weder Artefakt noch Stempel noch Verdict."""
    if config_text is not None:
        (project / ".claude" / "config.yaml").write_text(config_text)
    before = _state_path(project).read_bytes()
    r = _hook(project, "qa_gate.py", ["--run"])
    assert r.returncode == 1, _out(r)
    assert "qa_gate.test_command" in _out(r), _out(r)
    assert not (project / FIXED_OUT).exists(), "Artefakt trotz fehlendem Befehl"
    assert _state_path(project).read_bytes() == before, "State veraendert"


# --- AC-12: Datei-Modus unveraendert, vermerkt source "file" ----------------

def test_file_mode_unchanged_and_marks_source_file(project):
    """AC-12: Datei-Modus: gleiches Verdict/Meldung, Altersgrenze, Stempel 'file'."""
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


# --- AC-13: bash_gate unveraendert, beide qa_gate-Aufrufe frei ---------------

def _bash_gate(root: Path, command: str):
    payload = json.dumps({"command": command})
    return _hook(root, "bash_gate.py", [], extra_env={"CLAUDE_TOOL_INPUT": payload})


def _main_bash_gate() -> "str | None":
    """bash_gate.py auf origin/main, None wenn die Referenz fehlt (flacher CI-Checkout)."""
    r = subprocess.run(
        ["git", "show", "origin/main:core/hooks/bash_gate.py"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    )
    return r.stdout if r.returncode == 0 else None


def test_bash_gate_unchanged_and_qa_gate_calls_pass(project):
    """AC-13: bash_gate.py == main; Datei-Modus und `--run` passieren bash_gate (Exit 0)."""
    main_text = _main_bash_gate()
    if main_text is not None:
        current = (HOOKS_DIR / "bash_gate.py").read_text()
        assert current == main_text, "core/hooks/bash_gate.py weicht von origin/main ab"
    for command in (
        f"python3 .claude/hooks/qa_gate.py docs/artifacts/{WF}/test-output.txt",
        "python3 .claude/hooks/qa_gate.py --run",
        f"python3 .claude/hooks/qa_gate.py --run --infra "
        f"--checklist docs/artifacts/{WF}/checklist.md --no-visual \"Infra-Ticket\"",
    ):
        r = _bash_gate(project, command)
        assert r.returncode == 0, f"bash_gate blockt {command!r}: {_out(r)}"
