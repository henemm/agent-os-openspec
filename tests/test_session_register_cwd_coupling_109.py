"""Charakterisierungstests fuer Issue #109 — cwd-Kopplung des Session-Registers.

`session_singleton_guard._context_fields(cwd)` speist nur `worktree` und `branch`
aus dem uebergebenen `cwd`. Die Felder `workflow`, `issue` und `phase` stammen aus
`hook_utils.resolve_active_workflow()`, das den Worktree ueber `Path.cwd()` — also
das ambiente OS-Arbeitsverzeichnis des Hook-Subprozesses — aufloest. Ein
Registereintrag hat damit zwei Quellen.

Im Realbetrieb sind beide identisch: der Claude-Code-Harness startet jeden
Hook-Subprozess mit OS-cwd == Session-cwd == Payload-`cwd`. Die Kopplung an dieses
Harness-Verhalten ist bewusst akzeptiert (Entscheidung zu #109: Option B —
dokumentieren und testen statt `resolve_active_workflow()` umzubauen, die laut
ihrem eigenen Docstring alleinige Wahrheitsquelle der Workflow-Aufloesung bleiben
soll).

Diese Datei nagelt die Annahme fest. Sie ist der einzige Test, der das ECHTE,
UNGEMOCKTE `resolve_active_workflow()` durchlaeuft: alle Bestandstests in
tests/test_session_singleton_guard.py monkeypatchen die Funktion ueber
`_patch_active_workflow()` weg und umgehen die `Path.cwd()`-Abhaengigkeit
vollstaendig.

Hermetisch: Fake-Projekt im Worktree-Layout unter tmp_path (`.git`-DATEI mit
`gitdir:`-Zeile, kein `git`-Subprozess), Aufruf des Hooks als Subprozess mit
explizitem `cwd=` und eigenem `CLAUDE_PROJECT_DIR`/`HOME`. Das echte Repo und
insbesondere `.claude/active_workflow` werden nicht beruehrt.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD = REPO_ROOT / "core" / "hooks" / "session_singleton_guard.py"

# Payload-Worktree: der cwd, den der Hook explizit uebergeben bekommt.
PAYLOAD_WT = "wt-payload"
PAYLOAD_WORKFLOW = "feat-777-payload-workflow"
PAYLOAD_PHASE = "phase3_spec"

# Prozess-Worktree: das OS-Arbeitsverzeichnis des Hook-Subprozesses.
PROCESS_WT = "wt-process"
PROCESS_WORKFLOW = "feat-888-process-workflow"
PROCESS_PHASE = "phase6_implement"


# ---------------------------------------------------------------------------
# Fake-Projekt (kein echter git-Subprozess)
# ---------------------------------------------------------------------------

def _make_worktree(main: Path, name: str, workflow: str) -> Path:
    """Legt einen Fake-Worktree im echten Layout an.

    - `.git` ist eine DATEI mit `gitdir:`-Zeile (so erkennen
      `_find_worktree_root` und `_read_branch` einen Worktree)
    - `<gitdir>/HEAD` liefert den Branchnamen
    - `.claude/active_workflow` ist die worktree-lokale Workflow-Quelle
    """
    wt = main / ".claude" / "worktrees" / name
    (wt / ".claude").mkdir(parents=True)

    gitdir = main / ".git" / "worktrees" / name
    gitdir.mkdir(parents=True)
    (gitdir / "HEAD").write_text(f"ref: refs/heads/{workflow}\n")

    (wt / ".git").write_text(f"gitdir: {gitdir}\n")
    (wt / ".claude" / "active_workflow").write_text(f"{workflow}\n")
    return wt


def _write_workflow_state(main: Path, workflow: str, phase: str) -> None:
    wf_dir = main / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{workflow}.json").write_text(
        json.dumps({"name": workflow, "current_phase": phase})
    )


@pytest.fixture
def fake_project(tmp_path):
    """Haupt-Repo mit zwei unterscheidbaren Fake-Worktrees.

    Returns (main, payload_worktree, process_worktree).
    """
    main = tmp_path / "main_repo"
    (main / ".git").mkdir(parents=True)  # Haupt-Repo: .git ist ein VERZEICHNIS

    payload_wt = _make_worktree(main, PAYLOAD_WT, PAYLOAD_WORKFLOW)
    process_wt = _make_worktree(main, PROCESS_WT, PROCESS_WORKFLOW)

    _write_workflow_state(main, PAYLOAD_WORKFLOW, PAYLOAD_PHASE)
    _write_workflow_state(main, PROCESS_WORKFLOW, PROCESS_PHASE)

    return main, payload_wt, process_wt


def _run_register(main: Path, home: Path, payload_cwd: Path,
                  process_cwd: Path, session_id: str) -> dict:
    """Ruft den echten Hook als Subprozess auf und liefert den Registereintrag.

    `resolve_active_workflow()` wird NICHT gemockt — genau darum geht es hier.
    """
    (home / ".claude" / "sessions").mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(main)
    env["HOME"] = str(home)
    env.pop("USERPROFILE", None)
    env.pop("OPENSPEC_ACTIVE_WORKFLOW", None)

    payload = json.dumps({"session_id": session_id, "cwd": str(payload_cwd)})
    result = subprocess.run(
        [sys.executable, str(GUARD), "register"],
        input=payload, text=True, capture_output=True,
        cwd=str(process_cwd), env=env,
    )
    assert result.returncode == 0, result.stderr

    lock = main / ".claude" / "session-locks" / f"{session_id}.json"
    assert lock.exists(), f"Kein Registereintrag geschrieben: {result.stderr}"
    return json.loads(lock.read_text())


# ---------------------------------------------------------------------------
# Fall 1 — uebereinstimmender cwd (der Realbetrieb)
# ---------------------------------------------------------------------------

def test_register_matching_cwd_derives_all_context_fields(fake_project, tmp_path):
    """Prozess-cwd == Payload-cwd: alle sechs Kontextfelder sind korrekt.

    Der Normalfall unter dem Harness. Schuetzt, dass die Ableitung von
    `workflow`/`issue`/`phase` ueber das echte `resolve_active_workflow()`
    ueberhaupt funktioniert — diese Naht ist sonst von keinem Test gedeckt.
    """
    main, payload_wt, _process_wt = fake_project

    entry = _run_register(
        main, tmp_path / "home",
        payload_cwd=payload_wt, process_cwd=payload_wt,
        session_id="sess-match",
    )

    assert entry["cwd"] == str(payload_wt)
    assert entry["worktree"] == PAYLOAD_WT
    assert entry["branch"] == PAYLOAD_WORKFLOW
    assert entry["workflow"] == PAYLOAD_WORKFLOW
    assert entry["issue"] == "777"
    assert entry["phase"] == PAYLOAD_PHASE


# ---------------------------------------------------------------------------
# Fall 2 — divergenter cwd (die dokumentierte Kopplungsannahme)
# ---------------------------------------------------------------------------

def test_register_divergent_cwd_pins_documented_split_source(fake_project, tmp_path):
    """Prozess-cwd != Payload-cwd: zwei Quellen in EINEM Registereintrag.

    ABSICHTLICH das IST-Verhalten festgenagelt (Issue #109, Option B):
    `worktree`/`branch` stammen aus dem Payload-`cwd`, `workflow`/`issue`/`phase`
    aus dem Prozess-cwd. Unter dem Harness faellt das nicht auf, weil beide
    identisch sind; der Test macht die Kopplung sichtbar.

    Bricht dieser Test, hat sich die Aufloesung geaendert — dann ist zu
    entscheiden, ob das die gewollte Vereinheitlichung (Option A: `cwd` an
    `resolve_active_workflow()` durchreichen) ist. In dem Fall diesen Test
    umschreiben statt die Erwartung stillschweigend anzupassen und
    `docs/specs/session-singleton-guard.md` (Known Limitations) mitziehen.
    """
    main, payload_wt, process_wt = fake_project

    entry = _run_register(
        main, tmp_path / "home",
        payload_cwd=payload_wt, process_cwd=process_wt,
        session_id="sess-divergent",
    )

    # Aus dem Payload-cwd:
    assert entry["cwd"] == str(payload_wt)
    assert entry["worktree"] == PAYLOAD_WT
    assert entry["branch"] == PAYLOAD_WORKFLOW

    # Aus dem Prozess-cwd (die dokumentierte Kopplung):
    assert entry["workflow"] == PROCESS_WORKFLOW
    assert entry["issue"] == "888"
    assert entry["phase"] == PROCESS_PHASE

    # Explizit: NICHT der Workflow des Payload-Worktrees.
    assert entry["workflow"] != PAYLOAD_WORKFLOW
    assert entry["phase"] != PAYLOAD_PHASE
