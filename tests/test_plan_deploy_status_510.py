"""Plan-Pane: Deploy erst abgehakt, wenn wirklich deployt (Issue #510).

Spec: docs/specs/feat-510-plan-deploy-status.md (AC-1 bis AC-9).

Vertraege, die diese Tests festlegen:
- `render_plan(data, archived=False, width=None, deploy=...)`; `deploy` akzeptiert
  True/False und "configured"/"unconfigured"/"off".
- Schrittzeilen exakt `✔ 8 Code fertig`, `▶ Deploy  (offen)`, `▶ Deploy  (läuft)`,
  `✘ Deploy  (fehlgeschlagen)`, `▶ Deploy  (nicht eingerichtet)`, `✔ Deploy`, `○ Deploy`
  (zwei Leerzeichen vor der Klammer).
- CLI `workflow.py deploy-status <running|done|failed> [<issue-nr|name>]` -> stdout
  `DEPLOY_STATUS=<wert> (...)`, schreibt `deploy_status`/`deploy_at`; Exit 1 bei
  unbekanntem Wert oder ohne Treffer.
- Config-Opt-out `deploy: {enabled: false}`. Eine Root-config.yaml nur mit `deploy:`
  gilt als App-Config (#372), die Test-Configs enthalten deshalb `herdr:`.

Importfehler/fehlende Funktionen erscheinen als Test-FAIL: workflow.py wird erst im
Testkoerper importiert, die CLI laeuft als Subprozess.
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

WF = "feat-510-plan-deploy-status"
DEPLOY_CFG = ("herdr:\n  enabled: true\n"
              "deploy:\n  command: \"echo deploy\"\n  verify: \"echo verify\"\n")
NO_DEPLOY_CFG = "herdr:\n  enabled: true\n"
DEPLOY_OFF_CFG = "herdr:\n  enabled: true\ndeploy:\n  enabled: false\n"

STEP_MARKS = ("✔", "▶", "○", "✘")


# --- Helpers ---------------------------------------------------------------

def _wf_data(name: str = WF, phase: str = "phase8_complete", wtype: str = "feature",
             **fields) -> dict:
    data = {"name": name, "workflow_type": wtype, "current_phase": phase,
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    return data


def _render(*args, **kwargs) -> str:
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow.render_plan(*args, **kwargs)


def _step_lines(text: str) -> list:
    return [ln for ln in text.splitlines() if ln[:1] in STEP_MARKS]


def _last(text: str) -> str:
    return text.splitlines()[-1]


def _project(root: Path, config: "str | None", active: "dict | None" = None,
             archived: "dict | None" = None) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    wf_dir = proj / ".claude" / "workflows"
    (wf_dir / "_log").mkdir(parents=True)
    (wf_dir / "_archive").mkdir()
    (proj / "_home").mkdir()
    if config is not None:
        (proj / "config.yaml").write_text(config)
    if active is not None:
        (wf_dir / f"{active['name']}.json").write_text(json.dumps(active))
        (proj / ".claude" / "active_workflow").write_text(active["name"])
    if archived is not None:
        (wf_dir / "_archive" / f"{archived['name']}.json").write_text(json.dumps(archived))
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


# --- AC-1 -------------------------------------------------------------------

def test_phase8_deploy_open():
    out = _render(_wf_data(), deploy="configured")
    steps = _step_lines(out)
    assert "✔ 8 Code fertig" in steps, steps
    assert steps.index("✔ 8 Code fertig") + 1 == steps.index("▶ Deploy  (offen)"), steps
    assert steps[-1] == "▶ Deploy  (offen)", steps
    assert _last(out) == "Nächster: /70-deploy #510", out
    assert "abgeschlossen" not in out, out
    assert "8 Fertig" not in out, out
    # True ist gleichbedeutend mit "configured"
    assert _render(_wf_data(), deploy=True) == out


# --- AC-2 -------------------------------------------------------------------

def test_archived_needs_done_marker():
    out = _render(_wf_data(), archived=True, deploy="configured")
    steps = _step_lines(out)
    assert steps[-1] == "▶ Deploy  (offen)", steps
    assert "✔ 8 Code fertig" in steps, steps
    assert _last(out) == "Nächster: /70-deploy #510", out
    assert "abgeschlossen" not in out, out

    done = _render(_wf_data(deploy_status="done"), archived=True, deploy="configured")
    dsteps = _step_lines(done)
    assert dsteps[-1] == "✔ Deploy", dsteps
    assert dsteps.index("✔ 8 Code fertig") + 1 == dsteps.index("✔ Deploy"), dsteps
    assert _last(done) == "abgeschlossen", done
    assert "Nächster" not in done, done


# --- AC-3 -------------------------------------------------------------------

def test_running_and_failed():
    for archived in (False, True):
        run = _render(_wf_data(deploy_status="running"), archived=archived,
                      deploy="configured")
        assert _step_lines(run)[-1] == "▶ Deploy  (läuft)", (archived, run)
        assert _last(run) == "Nächster: /70-deploy #510", (archived, run)
        assert "abgeschlossen" not in run, (archived, run)

        fail = _render(_wf_data(deploy_status="failed"), archived=archived,
                       deploy="configured")
        assert _step_lines(fail)[-1] == "✘ Deploy  (fehlgeschlagen)", (archived, fail)
        assert _last(fail) == "Nächster: /70-deploy #510", (archived, fail)
        assert "abgeschlossen" not in fail, (archived, fail)


# --- AC-4 -------------------------------------------------------------------

def test_unconfigured_and_off():
    out = _render(_wf_data(), deploy="unconfigured")
    steps = _step_lines(out)
    assert steps[-1] == "▶ Deploy  (nicht eingerichtet)", steps
    assert "✔ 8 Code fertig" in steps, steps
    assert _last(out) == "Nächster: /70-deploy #510", out

    for value in ("off", False):
        for archived in (False, True):
            off = _render(_wf_data(), archived=archived, deploy=value)
            assert "Deploy" not in off, (value, archived, off)
            assert _step_lines(off)[-1] == "✔ 8 Fertig", (value, archived, off)
            assert _last(off) == "abgeschlossen", (value, archived, off)


# --- AC-5 -------------------------------------------------------------------

def test_abandoned_has_no_deploy():
    for data in (_wf_data(status="abandoned"),
                 _wf_data(no_build_reason="nur Doku, kein Build")):
        out = _render(data, archived=True, deploy="configured")
        assert "Deploy" not in out, (data, out)
        assert _last(out) == "abgeschlossen", (data, out)


# --- AC-6 -------------------------------------------------------------------

def test_cli_deploy_status(tmp_path):
    # Archivierter Workflow, per Issue-Nummer gefunden
    root = tmp_path / "archived"
    root.mkdir()
    proj = _project(root, DEPLOY_CFG, archived=_wf_data(name="feat-510-x"))
    res = _cli(proj, "deploy-status", "done", "510")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "DEPLOY_STATUS=done" in res.stdout, res.stdout
    stored = json.loads((proj / ".claude" / "workflows" / "_archive" /
                         "feat-510-x.json").read_text())
    assert stored.get("deploy_status") == "done", stored
    assert stored.get("deploy_at"), stored

    # Aktiver Workflow, ohne Nummer
    root = tmp_path / "active"
    root.mkdir()
    proj = _project(root, DEPLOY_CFG, active=_wf_data())
    res = _cli(proj, "deploy-status", "running")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "DEPLOY_STATUS=running" in res.stdout, res.stdout
    stored = json.loads((proj / ".claude" / "workflows" / f"{WF}.json").read_text())
    assert stored.get("deploy_status") == "running", stored
    assert stored.get("deploy_at"), stored

    # Unbekannter Wert / unbekannte Nummer -> Exit 1, nichts geschrieben
    bad = _cli(proj, "deploy-status", "xyz")
    assert bad.returncode == 1, (bad.stdout, bad.stderr)
    missing = _cli(proj, "deploy-status", "done", "99999")
    assert missing.returncode == 1, (missing.stdout, missing.stderr)
    stored = json.loads((proj / ".claude" / "workflows" / f"{WF}.json").read_text())
    assert stored.get("deploy_status") == "running", stored


# --- AC-7 -------------------------------------------------------------------

def test_cli_plan_deploy_mode(tmp_path):
    root = tmp_path / "unconfigured"
    root.mkdir()
    proj = _project(root, NO_DEPLOY_CFG, active=_wf_data())
    res = _cli(proj, "plan")
    assert res.returncode == 0, res.stderr
    assert "▶ Deploy  (nicht eingerichtet)" in res.stdout, res.stdout
    assert "Nächster: /70-deploy #510" in res.stdout, res.stdout

    root = tmp_path / "off"
    root.mkdir()
    proj = _project(root, DEPLOY_OFF_CFG, active=_wf_data())
    res = _cli(proj, "plan")
    assert res.returncode == 0, res.stderr
    assert "Deploy" not in res.stdout, res.stdout
    assert "abgeschlossen" in res.stdout, res.stdout

    # deploy_mode() als Funktion
    code = ("import sys; sys.path.insert(0, %r); import workflow; "
            "print(workflow.deploy_mode())" % str(HOOKS_DIR))
    for label, cfg, want in (("m-conf", DEPLOY_CFG, "configured"),
                             ("m-unconf", NO_DEPLOY_CFG, "unconfigured"),
                             ("m-off", DEPLOY_OFF_CFG, "off")):
        root = tmp_path / label
        root.mkdir()
        proj = _project(root, cfg)
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env=_env(proj), cwd=str(proj), timeout=30)
        assert res.returncode == 0, (label, res.stderr)
        assert res.stdout.strip() == want, (label, res.stdout)


# --- AC-8 -------------------------------------------------------------------

def test_early_phase():
    data = _wf_data(phase="phase5_tdd_red")
    out = _render(data, deploy="configured")
    steps = _step_lines(out)
    assert steps[-1] == "○ Deploy", steps
    assert "○ 8 Code fertig" in steps, steps
    assert "▶ 5 TDD-RED  (läuft)" in steps, steps
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    nxt = workflow.expected_footer_command(data)
    assert nxt, nxt
    assert _last(out) == f"Nächster: {nxt}", out


# --- AC-9 -------------------------------------------------------------------

def test_deploy_command_sets_markers():
    text = DEPLOY_CMD.read_text(encoding="utf-8")
    for value in ("running", "done", "failed"):
        assert f"deploy-status {value}" in text, value
    step4 = text.find("## Step 4")
    assert step4 >= 0, "Step 4 (Nachpruefung) fehlt"
    assert text.find("deploy-status done") > step4, \
        "deploy-status done muss nach dem verify-Schritt (Step 4) stehen"
    assert text.find("deploy-status running") < text.find("deploy-status done")
