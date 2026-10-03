"""TDD RED — Issue #253: Commit-Gate und Phase 8 verlangen einen gültigen
Adversary-Dialog-Nachweis.

Bisher setzte `post_bash.py` nach JEDEM grünen Testlauf
`adversary_verdict = "VERIFIED:<framework>"`; Commit-Gate (`bash_gate.py` 5c)
und der Übergang nach `phase8_complete` (`workflow.py`) prüften nur den
String-Präfix. Ein grüner `pytest`-Lauf öffnete so den Commit, ohne dass der
Adversary-Dialog je lief.

Belegt AC-1 … AC-11 aus docs/specs/fix-253-adversary-evidence-gate.md —
ausschließlich über die echten Hook-Skripte als Subprozess (Muster:
test_verdict_pipeline_77.py, test_gate_fixes_26_38_34.py,
test_adversary_dialog_hash_binding_131.py). Jeder Test baut ein eigenes
Git-Projekt in tmp_path; das `.claude/` dieses Repos wird nie berührt, kein Netz
(Fixture-Repos haben keinen Remote → der Rebase-Check 5b überspringt still).
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

WF = "wf-253"
DEFAULT_ART = f"docs/artifacts/{WF}/adversary-dialog.md"  # Standardpfad laut Spec
EXAMINED = "src/checked_module.py"  # im Dialog per 'Code reference:' zitiert
IMPL_PHASES = ("phase6_implement", "phase6b_adversary", "phase7_validate")
VERIFIED = "VERIFIED:Tests PASSED: 5 passed"
AMBIGUOUS = "AMBIGUOUS:Tests PASSED: 5 passed — User review recommended"

DIALOG_MISSING = "Dialog-Nachweis"
GREEN_SENTENCE = "Ein grüner Testlauf ersetzt den Adversary-Dialog nicht"


# --- Subprozess-Umgebung (hermetisch) ---

_SCRUBBED = {"CLAUDE_TOOL_INPUT", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT",
             "OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK", "PYTHONPATH"}


def _base_env() -> dict:
    # GIT_* raus: ein geerbtes GIT_DIR würde Fixture-Befehle aufs echte Repo lenken
    env = {k: v for k, v in os.environ.items()
           if k not in _SCRUBBED and not k.startswith("GIT_")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _env(project_dir: Path, active: str = WF) -> dict:
    env = _base_env()
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = active
    return env


def _run(script: str, args: list, cwd: Path, env: dict, stdin: "str | None" = None):
    io = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script), *args],
        capture_output=True, text=True, cwd=str(cwd), env=env, timeout=60, **io,
    )


def _git(args: list, cwd: Path) -> None:
    res = subprocess.run(
        ["git", "-c", "user.email=t@t.invalid", "-c", "user.name=Test",
         "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
        cwd=str(cwd), capture_output=True, text=True, env=_base_env(),
    )
    assert res.returncode == 0, f"git {args} failed: {res.stderr}"


def _commit_gate(cwd: Path, env: dict, command: str = "git commit -m wip"):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return _run("bash_gate.py", [], cwd, env, stdin=payload)


def _post_bash(root: Path, command: str, stdout: str, source: str = "tool_response"):
    if source == "tool_response":
        payload = {"tool_name": "Bash", "tool_input": {"command": command},
                   "tool_response": {"stdout": stdout, "stderr": ""}}
    else:  # Legacy: stdout in tool_input
        payload = {"tool_name": "Bash",
                   "tool_input": {"command": command, "stdout": stdout}}
    return _run("post_bash.py", [], root, _env(root), stdin=json.dumps(payload))


# --- Fixtures: Projekt, Workflow-State, Dialog-Artefakt ---

def _make_project(tmp_path: Path) -> Path:
    """Leeres Git-Projekt ohne Remote (Reproduktion aus dem Issue)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    _git(["init", "-q"], proj)
    (proj / ".claude" / "workflows").mkdir(parents=True)
    return proj


def _make_worktree(tmp_path: Path) -> "tuple[Path, Path]":
    """Hauptrepo + echter `git worktree`; aktiver Workflow worktree-lokal (#58)."""
    main = tmp_path / "main"
    main.mkdir()
    _git(["init", "-q"], main)
    (main / "README.md").write_text("x\n")
    _git(["add", "-A"], main)
    _git(["commit", "-q", "-m", "init"], main)
    wt = tmp_path / "worktrees" / "feat-253"
    _git(["worktree", "add", "-b", "feat-253", str(wt)], main)
    (main / ".claude" / "workflows").mkdir(parents=True)
    (wt / ".claude").mkdir()
    (wt / ".claude" / "active_workflow").write_text(WF)
    return main, wt


def _registered(path: str, art_type: str = "adversary_dialog",
                phase: str = "phase6b_adversary",
                created: str = "2026-09-26T10:00:00") -> dict:
    """test_artifacts-Element exakt wie `workflow.py add-artifact` es schreibt."""
    return {"type": art_type, "path": path, "description": f"{art_type} fixture",
            "phase": phase, "created": created}


def _red_artifact() -> dict:
    return _registered(f"docs/artifacts/{WF}/test-red-output.txt", "test_output",
                       "phase5_tdd_red", "2026-09-26T09:00:00")


def _write_workflow(root: Path, *, verdict=None, phase="phase6_implement",
                    wf_type="feature", artifacts=(), ambiguous_override=False,
                    **extra) -> Path:
    data = {
        "name": WF,
        "workflow_type": wf_type,
        "current_phase": phase,
        "context_file": "docs/context.md",
        "spec_file": "docs/specs/s.md",
        "spec_approved": True,
        "red_test_done": True,
        "test_artifacts": [dict(a) for a in artifacts],
        "adversary_verdict": verdict,
        "phase_transitions": [],
        "phase_log": [],
    }
    if ambiguous_override:
        data["adversary_ambiguous_override"] = {"reason": "User-Review ok",
                                                "at": "2026-09-26T11:00:00"}
    data.update(extra)
    path = root / ".claude" / "workflows" / f"{WF}.json"
    path.write_text(json.dumps(data, indent=2))
    return path


def _state(root: Path) -> dict:
    return json.loads((root / ".claude" / "workflows" / f"{WF}.json").read_text())


def _add_artifact(root: Path, art_type: str, rel: str, phase: str) -> None:
    """Registrierung über die echte CLI (dokumentierter Weg, /50-implement 8c)."""
    r = _run("workflow.py", ["add-artifact", art_type, rel, f"{art_type} fixture", phase],
             root, _env(root))
    assert r.returncode == 0, r.stderr


def _dialog_text(verdict: str) -> str:
    return (
        f"# Adversary Dialog — {WF}\nSpec: docs/specs/s.md\n\n"
        "## Checkliste\n"
        "- [x] AC-1: Commit-Gate verlangt den Nachweis — Beweis: Testlauf\n"
        f"  Code reference: {EXAMINED}:1\n"
        "- [x] AC-2: Phase 8 verlangt den Nachweis — Beweis: Testlauf\n"
        f"  Code reference: {EXAMINED}:2\n\n"
        "## Dialog\n\n"
        "### Runde 1\n**Adversary:** Angriff 1\n**Implementierer:** Beweis 1\n\n"
        "### Runde 2\n**Adversary:** Angriff 2\n**Implementierer:** Beweis 2\n\n"
        f"VERDICT: {verdict}\n"
    )


def _make_dialog(root: Path, rel: str = DEFAULT_ART, verdict: str = "VERIFIED",
                 stamp: bool = True) -> Path:
    """Dialog-Artefakt im Fixture-Projekt, per `adversary_dialog.py stamp` gestempelt."""
    examined = root / EXAMINED
    if not examined.exists():
        examined.parent.mkdir(parents=True, exist_ok=True)
        examined.write_text("VALUE = 1\n")
    art = root / rel
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(_dialog_text(verdict))
    if stamp:
        r = _run("adversary_dialog.py", ["stamp", str(art)], root, _env(root))
        assert r.returncode == 0, r.stdout + r.stderr
        if verdict != "BROKEN":  # Fixture-Kontrolle: das Artefakt ist heute schon gültig
            v = _run("adversary_dialog.py", ["validate", str(art)], root, _env(root))
            assert v.returncode == 0, v.stdout + v.stderr
    return art


def _green_test_output(root: Path) -> Path:
    out = root / "docs" / "artifacts" / WF / "test-green-output.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "============================= test session starts ==============================\n"
        "collected 5 items\n\ntests/test_gate.py .....\n\n"
        "============================== 5 passed in 0.12s ===============================\n"
    )
    return out


def _write_override_token(root: Path, name: str = WF) -> None:
    """Gültiger User-Override-Token (Format v2, override_token.py)."""
    (root / ".claude" / "user_override_token.json").write_text(json.dumps({
        "version": 2,
        "tokens": {name: {"created": datetime.now().isoformat(),
                          "granted_by": "user_prompt"}},
    }))


def _assert_iso(value) -> None:
    assert isinstance(value, str) and value, f"'at' fehlt: {value!r}"
    datetime.fromisoformat(value)


# --------------------------------------------------------------------------
# AC-1: grüner Testlauf → nur last_test_run, adversary_verdict byte-gleich
# --------------------------------------------------------------------------

GREEN_RUNS = [
    pytest.param("python3 -m pytest -q tests/", "===== 5 passed in 0.12s =====\n",
                 "pytest", id="pytest"),
    pytest.param("npx jest --ci", "Tests:       5 passed, 5 total\n", "jest", id="jest"),
    pytest.param("xcodebuild test -scheme App", "** TEST SUCCEEDED **\n",
                 "xcodebuild", id="xcodebuild"),
    pytest.param("go test ./...", "ok  \texample.com/app\t0.012s\n", "go test",
                 id="go-test"),
    # 'cargo test' enthält 'go test' als Teilstring — runner muss 'cargo test' sein
    pytest.param("cargo test --all", "test result: ok. 5 passed; 0 failed; 0 ignored\n",
                 "cargo test", id="cargo-test"),
]


@pytest.mark.parametrize("start_verdict", [None, "BROKEN:2 Findings offen"],
                         ids=["verdict-null", "verdict-broken"])
@pytest.mark.parametrize("source", ["tool_response", "legacy_tool_input"])
@pytest.mark.parametrize("command,stdout,runner", GREEN_RUNS)
def test_ac1_green_run_records_last_test_run_keeps_verdict(
        tmp_path, command, stdout, runner, source, start_verdict):
    proj = _make_project(tmp_path)
    _write_workflow(proj, verdict=start_verdict)
    before = _state(proj)

    r = _post_bash(proj, command, stdout, source)

    assert r.returncode == 0, r.stderr
    after = _state(proj)
    assert json.dumps(after["adversary_verdict"]) == json.dumps(start_verdict), (
        "post_bash.py darf adversary_verdict nicht mehr schreiben")
    run = after.get("last_test_run")
    assert isinstance(run, dict), "last_test_run fehlt"
    assert run.get("result") == "passed"
    assert run.get("runner") == runner
    _assert_iso(run.get("at"))
    rest = {k: v for k, v in after.items() if k != "last_test_run"}
    assert rest == before, "post_bash.py schreibt last_test_run und sonst nichts"


def test_ac1_runner_is_indicator_not_command(tmp_path):
    """`runner` ist der Indikator, nie der Befehl (der Inline-Credentials tragen kann)."""
    proj = _make_project(tmp_path)
    state_file = _write_workflow(proj)

    r = _post_bash(proj, "DB_PASSWORD=geheim-253 python3 -m pytest -q",
                   "== 3 passed in 0.5s ==\n")

    assert r.returncode == 0, r.stderr
    run = _state(proj).get("last_test_run")
    assert isinstance(run, dict), "last_test_run fehlt"
    assert run.get("runner") == "pytest"
    assert "geheim-253" not in state_file.read_text()


# --------------------------------------------------------------------------
# AC-2: Fehler-Evidenz → last_test_run 'failed'; sonst State unberührt
# --------------------------------------------------------------------------

RED_RUNS = [
    pytest.param("pytest -q", "== 2 failed, 3 passed in 1.2s ==\n", "pytest", id="pytest"),
    pytest.param("npx jest", "Tests:       1 failed, 4 passed, 5 total\n", "jest",
                 id="jest"),
    pytest.param("xcodebuild test -scheme App", "** TEST FAILED **\n", "xcodebuild",
                 id="xcodebuild"),
    pytest.param("go test ./...",
                 "--- FAIL: TestGate (0.00s)\nFAIL\nFAIL\texample.com/app\t0.01s\n",
                 "go test", id="go-test"),
    pytest.param("cargo test", "test result: FAILED. 4 passed; 1 failed; 0 ignored\n",
                 "cargo test", id="cargo-test"),
]


@pytest.mark.parametrize("command,stdout,runner", RED_RUNS)
def test_ac2_failure_evidence_records_failed_run(tmp_path, command, stdout, runner):
    """Ein roter Lauf überschreibt einen alten grünen Hinweis; das Verdict bleibt."""
    proj = _make_project(tmp_path)
    _write_workflow(proj, verdict=VERIFIED, last_test_run={
        "result": "passed", "runner": runner, "at": "2026-09-26T09:00:00"})

    r = _post_bash(proj, command, stdout)

    assert r.returncode == 0, r.stderr
    after = _state(proj)
    assert after["adversary_verdict"] == VERIFIED
    run = after.get("last_test_run")
    assert isinstance(run, dict), "last_test_run fehlt"
    assert run.get("result") == "failed", "roter Lauf nicht als 'failed' vermerkt"
    assert run.get("runner") == runner
    _assert_iso(run.get("at"))


def test_ac2_non_test_command_leaves_state_file_untouched(tmp_path):
    proj = _make_project(tmp_path)
    state_file = _write_workflow(proj, verdict="BROKEN:offen")
    before = state_file.read_bytes()

    r = _post_bash(proj, "ls -la", "5 passed in 1.2s\n")

    assert r.returncode == 0, r.stderr
    assert state_file.read_bytes() == before


@pytest.mark.parametrize("stdout", [
    "",
    "collected 0 items\n\n===== no tests ran in 0.01s =====\n",
], ids=["empty", "no-tests-ran"])
def test_ac2_undeterminable_test_output_leaves_state_file_untouched(tmp_path, stdout):
    proj = _make_project(tmp_path)
    state_file = _write_workflow(proj)
    before = state_file.read_bytes()

    r = _post_bash(proj, "pytest -q", stdout)

    assert r.returncode == 0, r.stderr
    assert state_file.read_bytes() == before


# --------------------------------------------------------------------------
# AC-3: VERIFIED ohne Artefakt → Commit blockiert, Meldung nennt den Weg
# --------------------------------------------------------------------------

@pytest.mark.parametrize("phase", IMPL_PHASES)
def test_ac3_verified_without_artifact_blocks_commit(tmp_path, phase):
    proj = _make_project(tmp_path)
    _write_workflow(proj, verdict="VERIFIED:pytest", phase=phase,
                    artifacts=[_red_artifact()])
    assert not (proj / DEFAULT_ART).exists()

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 2, f"Commit ohne Dialog-Nachweis erlaubt: {r.stderr}"
    assert DIALOG_MISSING in r.stderr
    assert GREEN_SENTENCE in r.stderr
    assert "stamp" in r.stderr
    assert "add-artifact adversary_dialog" in r.stderr
    # Error Handling: der Grund nennt beide Wege — auch den Standardpfad
    assert "adversary-dialog.md" in r.stderr


# --------------------------------------------------------------------------
# AC-4: registriertes, gestempeltes, gültiges Artefakt → Commit erlaubt
# --------------------------------------------------------------------------

@pytest.mark.parametrize("phase", IMPL_PHASES)
def test_ac4_registered_valid_artifact_allows_commit(tmp_path, phase):
    proj = _make_project(tmp_path)
    _write_workflow(proj, verdict="VERIFIED:pytest", phase=phase,
                    artifacts=[_red_artifact()])
    rel = f"docs/artifacts/{WF}/dialog-final.md"  # bewusst nicht der Standardpfad
    _make_dialog(proj, rel)
    _add_artifact(proj, "adversary_dialog", rel, "phase6b_adversary")
    # jüngeres Nicht-Dialog-Artefakt: zählt nicht als Dialog
    _add_artifact(proj, "test_output", f"docs/artifacts/{WF}/test-green-output.txt", phase)

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 0, r.stderr
    assert "E2E scope:" in r.stderr  # Gate lief mit aufgelöstem Workflow durch 5c


def test_ac4_documented_dialog_path_opens_commit_and_phase8(tmp_path):
    """DoD: Dialog → stamp → add-artifact → qa_gate --checklist, ohne Zusatzschritt."""
    proj = _make_project(tmp_path)
    _write_workflow(proj, verdict=None, phase="phase6b_adversary",
                    artifacts=[_red_artifact()])
    art = _make_dialog(proj)
    _add_artifact(proj, "adversary_dialog", DEFAULT_ART, "phase6b_adversary")

    qa = _run("qa_gate.py", [str(_green_test_output(proj)), "--checklist", str(art)],
              proj, _env(proj))
    assert qa.returncode == 0, qa.stdout + qa.stderr
    assert str(_state(proj)["adversary_verdict"]).startswith("VERIFIED")

    r = _commit_gate(proj, _env(proj))
    assert r.returncode == 0, r.stderr

    for target in ("phase7_validate", "phase8_complete"):
        p = _run("workflow.py", ["phase", target], proj, _env(proj))
        assert p.returncode == 0, p.stderr
    assert _state(proj)["current_phase"] == "phase8_complete"


# --------------------------------------------------------------------------
# AC-5: VERIFIED + ungültiges registriertes Artefakt → Block mit Grund
# --------------------------------------------------------------------------

def test_ac5a_changed_file_since_stamp_blocks(tmp_path):
    proj = _make_project(tmp_path)
    _make_dialog(proj)
    _write_workflow(proj, verdict=VERIFIED,
                    artifacts=[_red_artifact(), _registered(DEFAULT_ART)])
    (proj / EXAMINED).write_text("VALUE = 2  # nach dem Dialog geaendert\n")

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 2, f"geänderter Prüfling nicht erkannt: {r.stderr}"
    assert DIALOG_MISSING in r.stderr
    assert "Prüfling seit dem Dialog geändert" in r.stderr
    assert "checked_module.py" in r.stderr


def test_ac5b_missing_hash_block_blocks(tmp_path):
    proj = _make_project(tmp_path)
    _make_dialog(proj, stamp=False)
    _write_workflow(proj, verdict=VERIFIED, artifacts=[_registered(DEFAULT_ART)])

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 2, f"ungestempeltes Artefakt akzeptiert: {r.stderr}"
    assert DIALOG_MISSING in r.stderr
    assert "Hash-Block" in r.stderr


def test_ac5c_broken_artifact_blocks(tmp_path):
    proj = _make_project(tmp_path)
    _make_dialog(proj, verdict="BROKEN")
    _write_workflow(proj, verdict=VERIFIED, artifacts=[_registered(DEFAULT_ART)])

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 2, f"BROKEN-Artefakt akzeptiert: {r.stderr}"
    assert DIALOG_MISSING in r.stderr
    assert "BROKEN" in r.stderr


def test_ac5d_registered_path_missing_blocks_without_fallback(tmp_path):
    """Die ausdrückliche Registrierung gewinnt — kein stiller Rückfall auf den
    (hier gültigen) Standardpfad."""
    proj = _make_project(tmp_path)
    _make_dialog(proj)  # gültig am Standardpfad …
    gone = f"docs/artifacts/{WF}/verschoben.md"  # … registriert ist aber dieser Pfad
    _write_workflow(proj, verdict=VERIFIED, artifacts=[_registered(gone)])

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 2, f"fehlender Registrierungspfad nicht erkannt: {r.stderr}"
    assert DIALOG_MISSING in r.stderr
    assert gone in r.stderr


def test_ac5e_ambiguous_artifact_contradicts_verified_state_blocks(tmp_path):
    proj = _make_project(tmp_path)
    _make_dialog(proj, verdict="AMBIGUOUS")
    _write_workflow(proj, verdict=VERIFIED, artifacts=[_registered(DEFAULT_ART)])

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 2, f"VERIFIED/AMBIGUOUS-Widerspruch nicht erkannt: {r.stderr}"
    assert DIALOG_MISSING in r.stderr
    assert "AMBIGUOUS" in r.stderr


# --------------------------------------------------------------------------
# AC-6: AMBIGUOUS + Override braucht ebenfalls ein gültiges Artefakt
# --------------------------------------------------------------------------

@pytest.mark.parametrize("artifact_verdict", ["VERIFIED", "AMBIGUOUS"])
def test_ac6_ambiguous_override_with_valid_artifact_allows(tmp_path, artifact_verdict):
    proj = _make_project(tmp_path)
    _make_dialog(proj, verdict=artifact_verdict)
    _write_workflow(proj, verdict=AMBIGUOUS, phase="phase7_validate",
                    ambiguous_override=True, artifacts=[_registered(DEFAULT_ART)])

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 0, r.stderr
    assert "E2E scope:" in r.stderr


def test_ac6_ambiguous_override_without_artifact_blocks(tmp_path):
    proj = _make_project(tmp_path)
    _write_workflow(proj, verdict=AMBIGUOUS, phase="phase7_validate",
                    ambiguous_override=True, artifacts=[_red_artifact()])

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 2, f"AMBIGUOUS+Override ohne Dialog erlaubt: {r.stderr}"
    assert DIALOG_MISSING in r.stderr


@pytest.mark.parametrize("with_artifact", [True, False],
                         ids=["with-artifact", "without-artifact"])
def test_ac6_ambiguous_without_override_still_blocks(tmp_path, with_artifact):
    proj = _make_project(tmp_path)
    artifacts = []
    if with_artifact:
        _make_dialog(proj, verdict="AMBIGUOUS")
        artifacts = [_registered(DEFAULT_ART)]
    _write_workflow(proj, verdict=AMBIGUOUS, phase="phase7_validate",
                    artifacts=artifacts)

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 2, r.stderr
    assert "override-ambiguous" in r.stderr


# --------------------------------------------------------------------------
# AC-7: Notbremse (Override-Token) und Fast-Track-Ausnahme bleiben wirksam
# --------------------------------------------------------------------------

def test_ac7_override_token_lifts_evidence_block(tmp_path):
    proj = _make_project(tmp_path)
    _write_workflow(proj, verdict="VERIFIED:pytest", artifacts=[_red_artifact()])
    _write_override_token(proj)

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 0, r.stderr
    assert "E2E scope:" in r.stderr


@pytest.mark.parametrize("wf_type", ["feature-fast"])
def test_ac7_fast_track_types_exempt_without_token(tmp_path, wf_type):
    proj = _make_project(tmp_path)
    _write_workflow(proj, verdict="VERIFIED:pytest", wf_type=wf_type)
    assert not (proj / ".claude" / "user_override_token.json").exists()

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 0, r.stderr
    assert "E2E scope:" in r.stderr


# --------------------------------------------------------------------------
# AC-8: Artefakt-Suche — neuestes Registrat, Standardpfad, Worktree zuerst
# --------------------------------------------------------------------------

@pytest.mark.parametrize("older,newer,expected_rc", [
    ("VERIFIED", "BROKEN", 2),
    ("BROKEN", "VERIFIED", 0),  # Spiegelfall: das neueste zählt auch zugunsten
], ids=["older-valid-newer-broken", "older-broken-newer-valid"])
def test_ac8a_newest_registered_artifact_counts(tmp_path, older, newer, expected_rc):
    proj = _make_project(tmp_path)
    newer_rel = f"docs/artifacts/{WF}/adversary-dialog-runde2.md"
    _make_dialog(proj, DEFAULT_ART, verdict=older)
    _make_dialog(proj, newer_rel, verdict=newer)
    _write_workflow(proj, verdict=VERIFIED, artifacts=[
        _registered(DEFAULT_ART, created="2026-09-26T10:00:00"),
        _registered(newer_rel, created="2026-09-26T12:00:00"),
    ])

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == expected_rc, r.stderr
    if expected_rc == 2:
        assert DIALOG_MISSING in r.stderr
        assert "BROKEN" in r.stderr
    else:
        assert "E2E scope:" in r.stderr


def test_ac8b_default_path_used_when_nothing_registered(tmp_path):
    proj = _make_project(tmp_path)
    _make_dialog(proj)  # Standardpfad, nicht registriert
    _write_workflow(proj, verdict=VERIFIED, artifacts=[_red_artifact()])

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 0, r.stderr
    assert "E2E scope:" in r.stderr


def test_ac8c_worktree_relative_artifact_found(tmp_path):
    main, wt = _make_worktree(tmp_path)
    _make_dialog(wt)  # Artefakt UND Prüfling nur im Worktree
    _write_workflow(main, verdict=VERIFIED,
                    artifacts=[_red_artifact(), _registered(DEFAULT_ART)])
    assert not (main / DEFAULT_ART).exists()
    assert not (main / EXAMINED).exists()

    r = _commit_gate(wt, _env(wt, active=""))

    assert r.returncode == 0, r.stderr
    assert "E2E scope:" in r.stderr  # Workflow über die worktree-lokale Datei aufgelöst


# --------------------------------------------------------------------------
# AC-9: phase8_complete / complete / finish nutzen dieselbe Regel
# --------------------------------------------------------------------------

PHASE8_CMDS = [
    pytest.param(["phase", "phase8_complete"], id="phase"),
    pytest.param(["complete"], id="complete"),
    pytest.param(["finish"], id="finish"),
]

VERDICT_STATES = [
    pytest.param(VERIFIED, False, "VERIFIED", id="verified"),
    pytest.param(AMBIGUOUS, True, "AMBIGUOUS", id="ambiguous-override"),
]


def _phase7_workflow(root: Path, verdict: str, override: bool, artifacts=()) -> None:
    _write_workflow(root, verdict=verdict, phase="phase7_validate",
                    ambiguous_override=override, artifacts=artifacts)
    log_dir = root / ".claude" / "workflows" / "_log"  # complete verlangt write-log
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"2026-09-26_{WF}.yaml").write_text(f"workflow_id: {WF}\noutcome: success\n")


@pytest.mark.parametrize("verdict,override,_art_verdict", VERDICT_STATES)
@pytest.mark.parametrize("cmd", PHASE8_CMDS)
def test_ac9_phase8_blocked_without_valid_artifact(tmp_path, cmd, verdict, override,
                                                   _art_verdict):
    proj = _make_project(tmp_path)
    _phase7_workflow(proj, verdict, override, artifacts=[_red_artifact()])

    r = _run("workflow.py", cmd, proj, _env(proj))

    assert r.returncode != 0, f"Phase 8 ohne Dialog-Nachweis erreicht: {r.stdout}"
    assert "Adversary verdict" in r.stderr
    assert DIALOG_MISSING in r.stderr
    assert _state(proj)["current_phase"] == "phase7_validate"


@pytest.mark.parametrize("verdict,override,art_verdict", VERDICT_STATES)
@pytest.mark.parametrize("cmd", PHASE8_CMDS)
def test_ac9_phase8_allowed_with_valid_artifact(tmp_path, cmd, verdict, override,
                                                art_verdict):
    proj = _make_project(tmp_path)
    _make_dialog(proj, verdict=art_verdict)
    _phase7_workflow(proj, verdict, override,
                     artifacts=[_red_artifact(), _registered(DEFAULT_ART)])

    r = _run("workflow.py", cmd, proj, _env(proj))

    assert r.returncode == 0, r.stderr
    if cmd[0] == "phase":
        assert _state(proj)["current_phase"] == "phase8_complete"
    else:
        archived = proj / ".claude" / "workflows" / "_archive" / f"{WF}.json"
        assert json.loads(archived.read_text())["current_phase"] == "phase8_complete"


def test_ac9_changed_file_after_dialog_blocks_phase8(tmp_path):
    """Known Limitation, gewollt: ein Auto-Fix nach dem Dialog blockt Phase 8."""
    proj = _make_project(tmp_path)
    _make_dialog(proj)
    _phase7_workflow(proj, VERIFIED, False, artifacts=[_registered(DEFAULT_ART)])
    (proj / EXAMINED).write_text("VALUE = 3  # Auto-Fix in /60-validate\n")

    r = _run("workflow.py", ["phase", "phase8_complete"], proj, _env(proj))

    assert r.returncode != 0, f"veralteter Dialog öffnet Phase 8: {r.stdout}"
    assert "Adversary verdict" in r.stderr
    assert "Prüfling seit dem Dialog geändert" in r.stderr


# --------------------------------------------------------------------------
# AC-10: Reproduktion aus Issue #253, Ende-zu-Ende über die echten Hooks
# --------------------------------------------------------------------------

def test_ac10_issue_253_reproduction_blocked_end_to_end(tmp_path):
    proj = _make_project(tmp_path)
    _write_workflow(proj, verdict=None, phase="phase6_implement",
                    artifacts=[_red_artifact()])

    pb = _post_bash(proj, "pytest -q", "===== 5 passed in 0.12s =====\n")
    assert pb.returncode == 0, pb.stderr
    assert _state(proj)["adversary_verdict"] is None, "grüner Testlauf setzte das Verdict"

    r = _commit_gate(proj, _env(proj))

    assert r.returncode == 2, f"Commit ohne Adversary-Dialog erlaubt: {r.stderr}"
    assert "Adversary verdict" in r.stderr  # unveränderte "verdict missing"-Meldung


# --------------------------------------------------------------------------
# AC-11: qa_gate ohne --checklist verspricht keinen Commit mehr
# --------------------------------------------------------------------------

def test_ac11_qa_gate_without_checklist_promises_no_commit(tmp_path):
    proj = _make_project(tmp_path)
    _write_workflow(proj, verdict=None, phase="phase7_validate")

    r = _run("qa_gate.py", [str(_green_test_output(proj))], proj, _env(proj))

    assert r.returncode == 0, r.stdout + r.stderr
    assert str(_state(proj)["adversary_verdict"]).startswith("VERIFIED")  # unverändert
    assert "Commit is now allowed." not in r.stdout
    assert "Dialog-Artefakt" in r.stdout


def test_ac11_qa_gate_with_checklist_keeps_commit_message(tmp_path):
    proj = _make_project(tmp_path)
    _write_workflow(proj, verdict=None, phase="phase6b_adversary")
    art = _make_dialog(proj)

    r = _run("qa_gate.py", [str(_green_test_output(proj)), "--checklist", str(art)],
             proj, _env(proj))

    assert r.returncode == 0, r.stdout + r.stderr
    assert str(_state(proj)["adversary_verdict"]).startswith("VERIFIED")
    assert "Commit is now allowed." in r.stdout


# --------------------------------------------------------------------------
# Error Handling (Spec): fehlendes Modul / interner Fehler → fail-closed
# --------------------------------------------------------------------------

def test_err_missing_adversary_dialog_module_blocks_commit(tmp_path):
    """Spec §3: schlägt der Import von adversary_dialog fehl, gilt der Nachweis
    als nicht erbracht — auch bei gültigem, registriertem Artefakt."""
    proj = _make_project(tmp_path)
    _make_dialog(proj)
    _write_workflow(proj, verdict=VERIFIED, artifacts=[_registered(DEFAULT_ART)])
    fake_hooks = tmp_path / "fake_hooks"  # alles, was bash_gate braucht — außer adversary_dialog
    fake_hooks.mkdir()
    for fname in ("bash_gate.py", "hook_utils.py", "config_loader.py", "override_token.py"):
        shutil.copy(HOOKS_DIR / fname, fake_hooks / fname)

    r = subprocess.run(
        [sys.executable, str(fake_hooks / "bash_gate.py")],
        input=json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": "git commit -m wip"}}),
        capture_output=True, text=True, cwd=str(proj), env=_env(proj), timeout=60,
    )

    assert r.returncode == 2, f"Nachweis trotz fehlendem Modul erbracht: {r.stderr}"
    assert DIALOG_MISSING in r.stderr
    assert re.search(r"(ModuleNotFound|Import)Error", r.stderr), "Fehlerklasse fehlt"
    assert "Traceback" not in r.stderr


@pytest.mark.parametrize("gate", ["commit-gate", "phase8"])
def test_err_internal_error_is_fail_closed(tmp_path, gate):
    """Registrierter Pfad ist ein Verzeichnis → Lesen wirft; die Prüfung wirft
    nie, sondern blockt mit Fehlerklasse im Text."""
    proj = _make_project(tmp_path)
    _make_dialog(proj)  # gültig am Standardpfad — darf nicht einspringen
    dir_rel = f"docs/artifacts/{WF}/dialog-verzeichnis.md"
    (proj / dir_rel).mkdir(parents=True)
    _phase7_workflow(proj, VERIFIED, False, artifacts=[_registered(dir_rel)])

    if gate == "commit-gate":
        r = _commit_gate(proj, _env(proj))
        assert r.returncode == 2, f"interner Fehler ließ den Commit durch: {r.stderr}"
    else:
        r = _run("workflow.py", ["phase", "phase8_complete"], proj, _env(proj))
        assert r.returncode != 0, f"interner Fehler öffnete Phase 8: {r.stdout}"
        assert _state(proj)["current_phase"] == "phase7_validate"
    assert DIALOG_MISSING in r.stderr
    assert re.search(r"(IsADirectory|Permission)Error", r.stderr), "Fehlerklasse fehlt"
    assert "Traceback" not in r.stderr
