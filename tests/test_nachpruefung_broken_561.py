"""Tests fuer Issue #561: fachlicher Befund nach Phase 8 nimmt den BROKEN-Pfad.

Spec: docs/specs/fix-561-nachpruefung-broken.md (AC-1 bis AC-9).
Ruecksprung vor Phase 8 verwirft den Deploy-Zustand, `deploy-status --note`
schreibt `deploy_note`, `/70-deploy` und `/60-validate` beschreiben den Pfad.
Funktionen werden erst im Testkoerper importiert, die CLI laeuft als Subprozess.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
DEPLOY_CMD = REPO_ROOT / "core" / "commands" / "70-deploy.md"
VALIDATE_CMD = REPO_ROOT / "core" / "commands" / "60-validate.md"

WF = "fix-561-nachpruefung-broken"
DEPLOY_CFG = ("herdr:\n  enabled: true\n"
              "deploy:\n  command: \"echo deploy\"\n  verify: \"echo verify\"\n")
DEPLOY_FIELDS = ("deploy_status", "deploy_at", "deploy_note")


def _wf_data(phase: str = "phase8_complete", **fields) -> dict:
    data = {"name": WF, "workflow_type": "bugfix", "current_phase": phase,
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    return data


def _failed_data(**fields) -> dict:
    return _wf_data(deploy_status="failed", deploy_at="2026-11-10T10:00:00+00:00",
                    deploy_note="AC-3 verletzt", **fields)


def _wfmod():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _project(root: Path, data: dict, config: str = DEPLOY_CFG) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    wf_dir = proj / ".claude" / "workflows"
    (wf_dir / "_log").mkdir(parents=True)
    (wf_dir / "_archive").mkdir()
    (proj / "_home").mkdir()
    (proj / "config.yaml").write_text(config)
    (wf_dir / f"{data['name']}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(data["name"])
    return proj


def _env(proj: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    return env


def _cli(proj: Path, *args: str):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args], capture_output=True,
                          text=True, env=_env(proj), cwd=str(proj), timeout=30)


def _state(proj: Path) -> dict:
    return json.loads((proj / ".claude" / "workflows" / f"{WF}.json").read_text())


# --- AC-1 -------------------------------------------------------------------

def test_backstep_before_phase8_clears_deploy_fields():
    wf = _wfmod()
    for target in ("phase6_implement", "phase6b_adversary", "phase3_spec"):
        data = _failed_data()
        wf._reset_approvals_on_backstep(data, "phase8_complete", target)
        for key in DEPLOY_FIELDS:
            assert key not in data, (target, key, data)


# --- AC-2 -------------------------------------------------------------------

def test_forward_and_same_phase_keep_deploy_fields():
    wf = _wfmod()
    cases = [
        ("phase6_implement", "phase7_validate"),   # vorwaerts
        ("phase7_validate", "phase8_complete"),    # vorwaerts auf Phase 8
        ("phase8_complete", "phase8_complete"),    # gleiche Phase
    ]
    for current, target in cases:
        data = _failed_data()
        wf._reset_approvals_on_backstep(data, current, target)
        assert data["deploy_status"] == "failed", (current, target)
        assert data["deploy_at"] == "2026-11-10T10:00:00+00:00", (current, target)
        assert data["deploy_note"] == "AC-3 verletzt", (current, target)
    # Rueckwaertswechsel, der nicht vor phase8_complete endet: nichts verwerfen.
    # Heute ist phase8_complete die letzte Phase; dieser Fall ist dann genau
    # "gleiche Phase" (oben abgedeckt). Kommt eine spaetere Phase hinzu, prueft
    # die Schleife sie automatisch mit.
    phases = wf.PHASES
    assert "phase8_complete" in phases
    later = [p for p in phases if phases.index(p) > phases.index("phase8_complete")]
    for current in later:
        data = _failed_data()
        wf._reset_approvals_on_backstep(data, current, "phase8_complete")
        assert data.get("deploy_status") == "failed", current


# --- AC-3 -------------------------------------------------------------------

def test_plan_after_backstep_and_second_phase8_shows_open_deploy():
    wf = _wfmod()
    data = _failed_data()
    before = wf.render_plan(data, deploy="configured")
    assert "✘ Deploy  (fehlgeschlagen)" in before, before

    wf._reset_approvals_on_backstep(data, "phase8_complete", "phase6_implement")
    data["current_phase"] = "phase6_implement"
    mid = wf.render_plan(data, deploy="configured")
    assert "▶ 6 Implement  (läuft)" in mid, mid
    assert "Deploy  (fehlgeschlagen)" not in mid, mid
    assert "fehlgeschlagen" not in mid, mid

    data["current_phase"] = "phase8_complete"
    after = wf.render_plan(data, deploy="configured")
    assert "▶ Deploy  (offen)" in after, after
    assert "fehlgeschlagen" not in after, after
    assert "AC-3 verletzt" not in after, after


# --- AC-4 -------------------------------------------------------------------

def test_deploy_status_note_sets_single_line_note(tmp_path):
    proj = _project(tmp_path, _wf_data())
    res = _cli(proj, "deploy-status", "failed", "--note", "AC-3 verletzt")
    assert res.returncode == 0, res.stderr
    st = _state(proj)
    assert st["deploy_status"] == "failed", st
    assert st["deploy_note"] == "AC-3 verletzt", st
    es = _cli(proj, "plan").stdout
    assert "AC-3 verletzt" in es, es

    # --note vor dem Wert
    res = _cli(proj, "deploy-status", "--note", "AC-4 kaputt", "failed")
    assert res.returncode == 0, res.stderr
    assert _state(proj)["deploy_note"] == "AC-4 kaputt"

    # Zeilenumbrueche -> Leerzeichen, getrimmt
    res = _cli(proj, "deploy-status", "failed", "--note", "  Zeile eins\nZeile zwei\n ")
    assert res.returncode == 0, res.stderr
    assert _state(proj)["deploy_note"] == "Zeile eins Zeile zwei"

    # leerer Text -> kein Feld
    res = _cli(proj, "deploy-status", "failed", "--note", "")
    assert res.returncode == 0, res.stderr
    assert "deploy_note" not in _state(proj)


# --- AC-5 -------------------------------------------------------------------

def test_deploy_status_without_note_removes_old_note(tmp_path):
    for value in ("running", "done"):
        proj = _project(tmp_path / value, _failed_data())
        assert _state(proj)["deploy_note"] == "AC-3 verletzt"
        res = _cli(proj, "deploy-status", value)
        assert res.returncode == 0, res.stderr
        st = _state(proj)
        assert st["deploy_status"] == value, st
        assert "deploy_note" not in st, st


# --- AC-6 -------------------------------------------------------------------

def test_deploy_status_note_without_text_exits_1(tmp_path):
    proj = _project(tmp_path, _failed_data())
    before = _state(proj)
    res = _cli(proj, "deploy-status", "failed", "--note")
    assert res.returncode == 1, (res.returncode, res.stdout, res.stderr)
    assert "Usage" in res.stderr and "--note" in res.stderr, res.stderr
    assert _state(proj) == before


# --- AC-7 -------------------------------------------------------------------

def test_deploy_command_describes_broken_path():
    text = DEPLOY_CMD.read_text(encoding="utf-8")
    for needle in ("BROKEN", "deploy-status failed", "--note",
                   "workflow.py phase phase6_implement", "/50-implement",
                   "Adversary", "Kontingent", "Korrektur-PR", "archiviert",
                   "derselben Issue-Nummer"):
        assert needle in text, needle
    assert "am Workflow vorbei" in text, "Korrektur-PR am Workflow vorbei muss verboten sein"


# --- AC-8 -------------------------------------------------------------------

def test_validate_command_describes_broken_path():
    text = VALIDATE_CMD.read_text(encoding="utf-8")
    for needle in ("Phase 8", "BROKEN", "phase6_implement", "Kontingent", "/70-deploy"):
        assert needle in text, needle
    assert "Nachprüfung" in text or "Nachpruefung" in text, "Nachpruefung nach Phase 8"


# --- AC-9 -------------------------------------------------------------------

def test_skills_in_sync_with_commands():
    res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"),
                          "--check"], capture_output=True, text=True, cwd=str(REPO_ROOT),
                         timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr
    deploy_skill = (REPO_ROOT / "skills" / "70-deploy" / "SKILL.md").read_text(encoding="utf-8")
    validate_skill = (REPO_ROOT / "skills" / "60-validate" / "SKILL.md").read_text(encoding="utf-8")
    assert "Korrektur-PR" in deploy_skill and "--note" in deploy_skill
    assert "Kontingent" in validate_skill and "/70-deploy" in validate_skill
