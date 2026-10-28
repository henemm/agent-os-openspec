"""Autonomie D: Workflow-Kette, Intake und Commit+Push (Issue #472, Teil D von #468).

Textassertions auf core/commands/*.md UND die generierten skills/*/SKILL.md
(beide muessen dasselbe sagen — sync_skills.py erzeugt die Skills aus den
Befehlen), plus CLI-Tests fuer `workflow.py approvals` (nur Anzeige, Exit 0).

Festgelegte Vertraege:
- Jede Verzweigung nennt den Schalter woertlich als `AUTONOMY=auto` und die
  Abfrage `workflow.py autonomy`.
- Eine Zeile mit "Immer menschlich" nennt AMBIGUOUS, zweites BROKEN, Circuit
  Breaker, Override, Deploy und Stop-Lock (in 00/10/20/40/60).
- `workflow.py approvals [--auto]`: erste Zeile `APPROVALS=<n>`, danach je
  Eintrag `- <gate> | <by> | <at> | <reason>`; ohne aktiven Workflow
  `APPROVALS=0`. Exit immer 0.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS = REPO_ROOT / "core" / "commands"
SKILLS = REPO_ROOT / "skills"
WORKFLOW_PY = REPO_ROOT / "core" / "hooks" / "workflow.py"

HUMAN_TERMS = ["AMBIGUOUS", "zweites BROKEN", "Circuit Breaker", "Override",
               "Deploy", "Stop-Lock"]


def _sources(name: str):
    return [COMMANDS / f"{name}.md", SKILLS / name / "SKILL.md"]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _has_cmd(text: str, sub: str) -> bool:
    """Befehle stehen als `workflow.py <sub>`; sync_skills schreibt sie als `$WF <sub>`."""
    return f"workflow.py {sub}" in text or f"$WF {sub}" in text


def _cmd_index(text: str, sub: str) -> int:
    hits = [text.index(f) for f in (f"workflow.py {sub}", f"$WF {sub}") if f in text]
    if not hits:
        raise AssertionError(f"Befehl {sub!r} fehlt")
    return min(hits)


def _params(*names):
    return [pytest.param(p, id=f"{p.parent.name}/{p.name}")
            for n in names for p in _sources(n)]


# --- Gemeinsam: Verzweigung + menschliche Gates -----------------------------

@pytest.mark.parametrize("path", _params("00-intake", "10-context", "20-analyse",
                                         "60-validate"))
def test_auto_branch_present(path):
    text = _text(path)
    assert "AUTONOMY=auto" in text
    assert _has_cmd(text, "autonomy")


@pytest.mark.parametrize("path", _params("00-intake", "10-context", "20-analyse",
                                         "40-tdd-red", "60-validate"))
def test_human_gates_named(path):
    lines = [l for l in _text(path).splitlines() if "Immer menschlich" in l]
    assert lines, "Zeile 'Immer menschlich …' fehlt"
    line = lines[0]
    missing = [t for t in HUMAN_TERMS if t not in line]
    assert not missing, f"fehlt in Immer-menschlich-Zeile: {missing}"


# --- 00-intake ---------------------------------------------------------------

@pytest.mark.parametrize("path", _params("00-intake"))
def test_intake_auto_starts_without_question(path):
    text = _text(path)
    assert "ohne Rückfrage" in text
    assert "sofort" in text and _has_cmd(text, "start")
    assert "Fast Track nur bei Summe 0" in text


@pytest.mark.parametrize("path", _params("00-intake"))
def test_intake_auto_keeps_bug_stop(path):
    text = _text(path)
    idx = text.index("AUTONOMY=auto")
    block = text[idx:idx + 2500]
    assert "STOP" in block and "Ursache unklar" in block


# --- 10/20: Kette selbst weiter, /clear-Checkpoint bleibt -----------------------

@pytest.mark.parametrize("path,nxt", [
    *[(p, "20-analyse") for p in _sources("10-context")],
    *[(p, "30-write-spec") for p in _sources("20-analyse")],
])
def test_context_analyse_chain_self_invokes(path, nxt):
    text = _text(path)
    assert f"Rufe den Skill `{nxt}` jetzt sofort selbst auf" in text
    assert f"/{nxt} #<N>" in text
    assert "`/clear` ist jetzt gefahrlos" in text  # Checkpoint bleibt (#467)


@pytest.mark.parametrize("path", _params("20-analyse"))
def test_analyse_open_questions_still_stop(path):
    text = _text(path)
    assert "offene Fragen" in text
    idx = text.index("Rufe den Skill `30-write-spec` jetzt sofort selbst auf")
    assert "offene Frage" in text[max(0, idx - 1500):idx + 800]


# --- 40: Kette besteht schon -------------------------------------------------------

@pytest.mark.parametrize("path", _params("40-tdd-red"))
def test_tdd_red_chain_exists(path):
    text = _text(path)
    assert "Rufe den Skill `50-implement` jetzt sofort selbst" in text


# --- 60-validate ----------------------------------------------------------------

@pytest.mark.parametrize("path", _params("60-validate"))
def test_validate_auto_commit_and_push_feature_branch(path):
    text = _text(path)
    idx = text.index("AUTONOMY=auto")
    block = text[idx:idx + 4000]
    assert "ohne Rückfrage" in block
    assert "git push" in block
    assert "Feature-Branch" in block
    assert "`main`" in block and "`master`" in block
    assert "nie" in block


@pytest.mark.parametrize("path", _params("60-validate"))
def test_validate_auto_push_skips_remote_default_branch(path):
    text = _text(path)
    idx = text.index("AUTONOMY=auto")
    block = text[idx:idx + 4000]
    assert "git symbolic-ref --short refs/remotes/origin/HEAD" in block
    assert "Default-Branch des Remotes" in block
    assert "nicht gepusht" in block


@pytest.mark.parametrize("path", _params("60-validate"))
def test_validate_auto_never_deploys(path):
    text = _text(path)
    idx = text.index("AUTONOMY=auto")
    block = text[idx:idx + 4000]
    assert "löst nie ein Deploy aus" in block
    assert "deploy.autonomous" in block
    assert "Merge" in block and "PR" in block


@pytest.mark.parametrize("path", _params("60-validate"))
def test_validate_lists_auto_approvals(path):
    text = _text(path)
    idx = _cmd_index(text, "approvals --auto")
    block = text[idx:idx + 1500]
    assert "Gate" in block and "Zeit" in block and "Grund" in block


# --- CLI: workflow.py approvals ----------------------------------------------------

def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    return proj


def _cli(args, proj: Path):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args],
                          capture_output=True, text=True, env=env,
                          cwd=str(proj), timeout=60)


def _write_wf(proj: Path, name: str, approvals):
    data = {"name": name, "workflow_type": "feature",
            "current_phase": "phase7_validate", "phase_transitions": [],
            "phase_log": [], "spec_approved": True, "approvals": approvals}
    (proj / ".claude" / "workflows" / f"{name}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(name)


ENTRIES = [
    {"gate": "spec", "by": "auto", "mode": "auto", "at": "2026-10-28T10:00:00",
     "reason": "Ampel gruen im PO-Briefing", "evidence": {}},
    {"gate": "green", "by": "user", "mode": "auto", "at": "2026-10-28T11:00:00",
     "reason": "go", "evidence": None},
]


def test_cli_approvals_lists_entries(tmp_path):
    proj = _project(tmp_path)
    _write_wf(proj, "feat-1", ENTRIES)
    r = _cli(["approvals"], proj)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == "APPROVALS=2"
    assert "- spec | auto | 2026-10-28T10:00:00 | Ampel gruen im PO-Briefing" in lines
    assert "- green | user | 2026-10-28T11:00:00 | go" in lines


def test_cli_approvals_auto_filter(tmp_path):
    proj = _project(tmp_path)
    _write_wf(proj, "feat-1", ENTRIES)
    r = _cli(["approvals", "--auto"], proj)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == "APPROVALS=1"
    assert any(l.startswith("- spec | auto |") for l in lines)
    assert not any("| user |" in l for l in lines)


def test_cli_approvals_empty(tmp_path):
    proj = _project(tmp_path)
    _write_wf(proj, "feat-1", [])
    r = _cli(["approvals"], proj)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0] == "APPROVALS=0"
    assert not any(l.startswith("- ") for l in r.stdout.splitlines())


def test_cli_approvals_without_field_or_garbage(tmp_path):
    proj = _project(tmp_path)
    _write_wf(proj, "feat-1", ["kaputt", {"gate": "spec", "by": "auto",
                                          "at": "x", "reason": "a\nb"}])
    r = _cli(["approvals"], proj)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == "APPROVALS=1"
    assert "- spec | auto | x | a b" in lines


def test_cli_approvals_no_active_workflow(tmp_path):
    proj = _project(tmp_path)
    r = _cli(["approvals"], proj)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0] == "APPROVALS=0"
