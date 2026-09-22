"""Statusvermerk des UserPromptSubmit-Hooks (3.25.0).

Fundfall (gregor_zwanzig #1761, 2026-09-20): Der Workflow stand in Phase 7 von
8, die Abschlussnachricht las sich wie „Arbeit erledigt“ und nannte den offenen
Pflicht-Schritt als Option („bei Bedarf /60-validate #1761“). Der Satz stand in
einer frei formulierten Nachricht NACH dem Ende der Phase — dort greift keine
Phasen-Anleitung mehr. Seit 3.25.0 haengt `phase_listener.py` bei jeder
Nutzer-Nachricht einen kurzen Vermerk an den Kontext.

Geprueft wird der Hook als Subprozess (so startet Claude Code ihn) plus die
reine Textfunktion `workflow.status_note`.

- AC-1: aktiver Workflow vor Phase 8 -> Name, Phase (x von 8), naechster Schritt
- AC-2: Phase 8 oder kein Workflow -> stdout leer
- AC-5: State fehlt/defekt -> still, Exit 0, keine Blockade
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import workflow  # noqa: E402

LISTENER = HOOKS_DIR / "phase_listener.py"


# --- Helpers ---------------------------------------------------------------

def _project(tmp_path: Path, name: str = "fix-1761-statusvermerk",
             phase: str = "phase7_validate", **fields) -> Path:
    """Main-Repo (.git als Verzeichnis -> kein Worktree) mit einem Workflow."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    data = {"name": name, "workflow_type": "feature", "current_phase": phase}
    data.update(fields)
    (wf_dir / f"{name}.json").write_text(json.dumps(data))
    return tmp_path


def _run(project: Path, wf_name: str, prompt: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({
        "CLAUDE_PROJECT_DIR": str(project),
        "OPENSPEC_ACTIVE_WORKFLOW": wf_name,
    })
    return subprocess.run(
        [sys.executable, str(LISTENER)],
        input=json.dumps({"prompt": prompt}),
        capture_output=True, text=True, env=env, cwd=str(project),
    )


def _state(project: Path, wf_name: str) -> dict:
    return json.loads(
        (project / ".claude" / "workflows" / f"{wf_name}.json").read_text()
    )


# --- AC-1: der Vermerk erscheint ------------------------------------------

def test_note_names_workflow_phase_and_next_mandatory_step(tmp_path):
    project = _project(tmp_path)
    res = _run(project, "fix-1761-statusvermerk", "Wie ist der Stand?")
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "fix-1761-statusvermerk" in out
    assert "Phase 7 von 8" in out
    assert "phase7_validate" in out
    assert "/60-validate #1761" in out


def test_note_forbids_optional_wording_and_premature_done(tmp_path):
    project = _project(tmp_path)
    out = _run(project, "fix-1761-statusvermerk", "kurze Zwischenfrage").stdout
    assert "bei Bedarf" in out and "optional" in out
    assert "fertig" in out and "phase8_complete" in out
    assert "/clear" in out


def test_note_tells_claude_to_mark_who_is_on_turn(tmp_path):
    """#174: ❗ = der PO muss etwas tun, ℹ️ = Claude arbeitet, nichts zu tun."""
    project = _project(tmp_path)
    out = _run(project, "fix-1761-statusvermerk", "Wie ist der Stand?").stdout
    assert "❗ Du:" in out
    assert "ℹ️ Nichts zu tun:" in out


def test_note_also_appears_on_harness_injected_turns(tmp_path):
    """Der Fundfall war ein Loop-Aufwacher, kein getippter Satz. Solche Turns
    verlassen den Hook frueh (Issue #46) — ohne den Vermerk dort waere genau
    der beobachtete Fall weiter ungedeckt. Keyword-Erkennung bleibt aus."""
    project = _project(tmp_path, phase="phase3_spec")
    res = _run(project, "fix-1761-statusvermerk",
               "<system-reminder>approved</system-reminder>")
    assert res.returncode == 0, res.stderr
    assert "Phase 3 von 8" in res.stdout
    assert _state(project, "fix-1761-statusvermerk").get("spec_approved") is not True


def test_note_is_silent_on_a_stop_message(tmp_path):
    """Not-Aus: der Stop-Lock-Turn bleibt ohne Zusatzkontext."""
    project = _project(tmp_path)
    res = _run(project, "fix-1761-statusvermerk", "stop")
    assert res.returncode == 0
    assert res.stdout == ""


def test_note_follows_an_approval_within_the_same_turn(tmp_path):
    """Nach der Freigabe steht der Workflow in phase4_approved — der Vermerk
    nennt den dann faelligen Schritt, nicht den alten."""
    project = _project(tmp_path, phase="phase3_spec", spec_approved=False)
    res = _run(project, "fix-1761-statusvermerk", "approved")
    assert res.returncode == 0, res.stderr
    assert "Phase 4 von 8" in res.stdout
    assert "/40-tdd-red #1761" in res.stdout


# --- AC-1 im Produktionszustand: Worktree-Sitzung --------------------------

def _git(args: list, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def test_note_appears_in_a_real_worktree_session(tmp_path):
    """Das Framework erzwingt Worktree-Pflicht — jede echte Sitzung (auch der
    Fundfall gregor #1761) laeuft in einem Worktree. Dort liegen die
    Workflow-JSONs im HAUPTREPO, die Workflow-Identitaet dagegen worktree-lokal
    in `.claude/active_workflow`; die eingefrorene Env-Var wird bewusst
    ignoriert (Issue #58). Der Vermerk muss genau in dieser Konstellation
    erscheinen.
    """
    main = tmp_path / "main_repo"
    main.mkdir()
    _git(["init", "-b", "main"], main)
    _git(["config", "user.email", "test@example.invalid"], main)
    _git(["config", "user.name", "Test"], main)
    _git(["config", "commit.gpgsign", "false"], main)
    (main / "README.md").write_text("# x\n")
    _git(["add", "-A"], main)
    _git(["commit", "-m", "init"], main)

    wf_name = "fix-1761-statusvermerk"
    wf_dir = main / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{wf_name}.json").write_text(json.dumps({
        "name": wf_name, "current_phase": "phase7_validate",
    }))

    worktree = tmp_path / "worktrees" / wf_name
    _git(["worktree", "add", str(worktree), "-b", wf_name], main)
    (worktree / ".claude").mkdir(parents=True, exist_ok=True)
    (worktree / ".claude" / "active_workflow").write_text(wf_name)

    env = dict(os.environ)
    env.pop("OPENSPEC_ACTIVE_WORKFLOW", None)
    env["CLAUDE_PROJECT_DIR"] = str(worktree)
    res = subprocess.run(
        [sys.executable, str(LISTENER)],
        input=json.dumps({"prompt": "Wie ist der Stand?"}),
        capture_output=True, text=True, env=env, cwd=str(worktree),
    )
    assert res.returncode == 0, res.stderr
    assert "Phase 7 von 8" in res.stdout, res.stdout
    assert "/60-validate #1761" in res.stdout


# --- AC-2: kein Vermerk, wo keiner hingehoert ------------------------------

def test_no_note_in_phase8(tmp_path):
    project = _project(tmp_path, phase="phase8_complete")
    res = _run(project, "fix-1761-statusvermerk", "Wie ist der Stand?")
    assert res.returncode == 0
    assert res.stdout == ""


def test_no_note_without_an_active_workflow(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude" / "workflows").mkdir(parents=True)
    res = _run(tmp_path, "", "Wie ist der Stand?")
    assert res.returncode == 0
    assert res.stdout == ""


# --- AC-5: Robustheit ------------------------------------------------------

def test_broken_state_file_stays_silent_and_does_not_block(tmp_path):
    project = _project(tmp_path)
    (project / ".claude" / "workflows" / "fix-1761-statusvermerk.json").write_text(
        "{kaputt"
    )
    res = _run(project, "fix-1761-statusvermerk", "Wie ist der Stand?")
    assert res.returncode == 0
    assert res.stdout == ""


def test_missing_state_file_stays_silent(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude" / "workflows").mkdir(parents=True)
    res = _run(tmp_path, "gibt-es-nicht", "Wie ist der Stand?")
    assert res.returncode == 0
    assert res.stdout == ""


def test_status_note_tolerates_nonsense_state():
    for data in ({}, {"name": 5, "current_phase": "phase6_implement"},
                 {"name": "x", "current_phase": 7},
                 {"name": "x", "current_phase": "phase_unbekannt"},
                 {"name": "x"}, None, "kein dict"):
        assert workflow.status_note(data) is None, data


# --- Phasen-Tabelle --------------------------------------------------------

def test_phase_numbers_never_claim_completion_too_early():
    """Der Kern des Fundfalls: phase7_validate ist Phase 7, nicht 8. Der
    Listen-Index von PHASES wuerde 8 liefern (phase0_idle + phase6b)."""
    assert workflow.PHASE_NUMBERS["phase7_validate"] == 7
    assert workflow.PHASE_NUMBERS["phase6b_adversary"] == 6
    assert workflow.PHASE_NUMBERS["phase8_complete"] == workflow.TOTAL_PHASES
    assert set(workflow.PHASE_NUMBERS) == set(workflow.PHASES)


def test_next_step_covers_every_phase_exactly_once():
    assert set(workflow.NEXT_STEP) == set(workflow.PHASES)
    assert workflow.NEXT_STEP["phase8_complete"] is None


def test_next_step_distinguishes_writing_a_spec_from_waiting_for_approval():
    writing = {"name": "w", "current_phase": "phase3_spec"}
    waiting = {"name": "w", "current_phase": "phase3_spec",
               "spec_file": "docs/specs/x.md"}
    assert workflow.next_step(writing) == "/30-write-spec"
    assert workflow.next_step(waiting).startswith("Freigabe")
    # Ein Freigabewort ist kein Befehl -> keine Issue-Nummer anhaengen.
    assert "#" not in workflow.status_note(waiting)


def test_next_step_moves_on_when_red_tests_are_done():
    red_open = {"name": "w-7", "current_phase": "phase5_tdd_red"}
    red_done = {"name": "w-7", "current_phase": "phase5_tdd_red",
                "red_test_done": True}
    assert workflow.next_step(red_open) == "/40-tdd-red"
    assert workflow.next_step(red_done) == "/50-implement"


def test_next_step_accepts_a_ui_only_red_marker():
    """`mark-ui-red` setzt `ui_test_red_done`, nicht `red_test_done`. Ein
    UI-Workflow ist damit genauso RED-fertig — sonst nennt der Vermerk
    faelschlich `/40-tdd-red`, obwohl `/50-implement` faellig ist."""
    ui_only = {"name": "w-7", "current_phase": "phase5_tdd_red",
               "ui_test_red_done": True}
    nothing_marked = {"name": "w-7", "current_phase": "phase5_tdd_red",
                      "red_test_done": False, "ui_test_red_done": False}
    assert workflow.next_step(ui_only) == "/50-implement"
    assert "/50-implement" in workflow.status_note(ui_only)
    assert workflow.next_step(nothing_marked) == "/40-tdd-red"


def test_issue_number_only_when_the_name_carries_one():
    assert workflow.issue_number("fix-1761-statusvermerk") == "1761"
    assert workflow.issue_number("feature-login") is None
    note = workflow.status_note({"name": "feature-login",
                                 "current_phase": "phase7_validate"})
    assert "/60-validate" in note and "#" not in note
