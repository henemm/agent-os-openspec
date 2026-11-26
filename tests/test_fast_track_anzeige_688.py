"""Fast Track: Anzeige nach der Freigabe (Issue #688).

Spec: docs/specs/infra/fix-688-fast-track-anzeige.md (AC-1 bis AC-6).

Vertraege aus der Spec:
- `next_step`: `phase4_approved` + `workflow_type == "feature-fast"` -> `/50-implement`;
  voller Prozess bleibt `/40-tdd-red`.
- `end_state`: in `phase4_approved` nach Auto-Freigabe (juengster `approvals`-Eintrag mit
  `gate == "spec"` hat `by == "auto"`) -> `waiting`,
  `⏳ Läuft noch: Claude führt <cmd> selbst aus. Du musst nichts tun, ich melde mich.`;
  manuelle Freigabe oder fehlende `approvals` -> unveraendert `you` (❗ Du).

workflow.py/herdr_bridge.py werden erst im Testkoerper importiert; Fußzeilen-Gate und
Seitenleiste laufen als Subprozess.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
FOOTER_GATE = HOOKS_DIR / "footer_gate.py"

WF = "fix-688-demo"
ISSUE = 688
WAIT_TAIL = ". Du musst nichts tun, ich melde mich."


def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _approval(by: str, gate: str = "spec") -> dict:
    return {"gate": gate, "by": by, "mode": "auto", "at": "2026-11-26T10:00:00",
            "reason": "test", "evidence": None}


def _data(wtype: str = "feature-fast", phase: str = "phase4_approved",
          approvals=None, **fields) -> dict:
    data = {"name": WF, "workflow_type": wtype, "current_phase": phase,
            "spec_file": "docs/specs/x.md", "spec_approved": True,
            "phase_transitions": [], "phase_log": []}
    if approvals is not None:
        data["approvals"] = approvals
    data.update(fields)
    return data


def _self_line(cmd: str) -> str:
    return f"⏳ Läuft noch: Claude führt {cmd} selbst aus{WAIT_TAIL}"


def _project(root: Path, active: dict) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    wf_dir = proj / ".claude" / "workflows"
    (wf_dir / "_log").mkdir(parents=True)
    (wf_dir / "_archive").mkdir()
    (proj / "_home").mkdir()
    (wf_dir / f"{active['name']}.json").write_text(json.dumps(active))
    (proj / ".claude" / "active_workflow").write_text(active["name"])
    return proj


def _env(proj: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_"))
           and k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PLUGIN_ROOT")}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    return env


# --- AC-1 -------------------------------------------------------------------

def test_fast_track_phase4_next_is_implement():
    wf = _wf()
    for approvals in (None, [_approval("auto")], [_approval("po")]):
        data = _data(approvals=approvals)
        assert wf.next_step(data) == "/50-implement", approvals
        assert wf.expected_footer_command(data) == f"/50-implement #{ISSUE}", approvals
        note = wf._status_note_base(data)
        assert note and f"Nächster Pflicht-Schritt: /50-implement #{ISSUE}" in note, note
        assert "/40-tdd-red" not in note, note


# --- AC-2 -------------------------------------------------------------------

def test_full_process_phase4_unchanged():
    wf = _wf()
    for approvals in (None, [_approval("auto")], [_approval("po")]):
        data = _data(wtype="feature", approvals=approvals)
        assert wf.next_step(data) == "/40-tdd-red", approvals
        assert wf.expected_footer_command(data) == f"/40-tdd-red #{ISSUE}", approvals


# --- AC-3 -------------------------------------------------------------------

def test_auto_approved_phase4_is_waiting():
    wf = _wf()
    for wtype, step in (("feature-fast", "/50-implement"), ("feature", "/40-tdd-red")):
        cmd = f"{step} #{ISSUE}"
        # juengster Spec-Eintrag zaehlt: erst po, dann auto
        for approvals in ([_approval("auto")],
                          [_approval("po"), _approval("auto")],
                          [_approval("auto"), _approval("auto", gate="green")]):
            data = _data(wtype=wtype, approvals=approvals)
            es = wf.end_state(data)
            assert es["kind"] == "waiting", (wtype, approvals, es)
            assert es["cmd"] == cmd, (wtype, es)
            assert es["line"] == _self_line(cmd), (wtype, es)
            assert "❗" not in es["line"], es
            plan = wf.render_plan(data)
            assert plan.rstrip("\n").splitlines()[-1] == es["line"], plan
            assert "❗" not in plan, plan


# --- AC-4 -------------------------------------------------------------------

def test_manual_approval_stays_you():
    wf = _wf()
    cases = (None, [], [_approval("po")], [_approval("auto"), _approval("po")],
             "kaputt", [None, 3, "x"])
    for approvals in cases:
        data = _data(approvals=approvals)
        es = wf.end_state(data)
        assert es["kind"] == "you", (approvals, es)
        assert es["line"].startswith(f"❗ Du: /50-implement #{ISSUE} — "), es
    # Auto-Freigabe wirkt nur in phase4_approved
    data = _data(phase="phase6_implement", approvals=[_approval("auto")])
    es = wf.end_state(data)
    assert es["kind"] == "you", es


# --- AC-5 -------------------------------------------------------------------

def _run_footer_gate(project: Path, message: str, prompt_id: str):
    payload = {"session_id": "sess-688", "hook_event_name": "Stop",
               "cwd": str(project), "last_assistant_message": message,
               "prompt_id": prompt_id}
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env.pop("OPENSPEC_FRAMEWORK", None)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    return subprocess.run([sys.executable, str(FOOTER_GATE)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, cwd=str(project),
                          timeout=30)


def _sidebar(proj: Path, data: dict) -> dict:
    code = ("import json, sys\n"
            f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            "import herdr_bridge\n"
            "data = json.loads(sys.stdin.read())\n"
            "rep = herdr_bridge.build_report(data)\n"
            "print(json.dumps(rep['tokens']))\n")
    res = subprocess.run([sys.executable, "-c", code], input=json.dumps(data),
                         capture_output=True, text=True, env=_env(proj),
                         cwd=str(proj), timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def test_footer_gate_and_sidebar_agree(tmp_path):
    data = _data(approvals=[_approval("auto")])
    proj = _project(tmp_path, data)
    cmd = f"/50-implement #{ISSUE}"

    ok = f"Spec freigegeben, Umsetzung startet.\n\n{_self_line(cmd)}"
    res = _run_footer_gate(proj, ok, "00000000-0000-0000-0000-000000006881")
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr

    wrong = ("Spec freigegeben.\n\n❗ Du: `/40-tdd-red #688` — als Nächstes entstehen "
             "die fehlschlagenden Tests")
    res = _run_footer_gate(proj, wrong, "00000000-0000-0000-0000-000000006882")
    assert res.returncode == 2, (res.returncode, res.stderr)

    tokens = _sidebar(proj, data)
    assert tokens["next"] == cmd, tokens
    assert tokens["state"] == "läuft", tokens
