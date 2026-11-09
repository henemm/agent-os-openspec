"""Genau drei eindeutige Endzustaende (Issue #550, umfasst #547).

Spec: docs/specs/fix-550-endzustand.md (AC-1 bis AC-12).

Vertraege, die diese Tests festlegen (aus der Spec, Abschnitt Implementation Details):
- `workflow.end_state(data, archived=False, deploy="off", autonomous=False)` ->
  `{"kind": "done"|"waiting"|"you", "line": str, "cmd": str|None}`; rein (kein I/O).
- Feste Wortlaute:
    `✅ Erledigt: <was>. Du kannst /clear ausführen und das nächste Issue starten.`
    `⏳ Läuft noch: <worauf>. Du musst nichts tun, ich melde mich.`
    `❗ Du: <Schritt> — <warum>`
- `workflow._plan_deploy_mode`: True/"configured" -> "configured", sonst "off".
- `workflow.NEXT_WHY`: Warum-Texte fuer Phasen < 8.
- `workflow.render_plan(..., deploy=..., autonomous=...)`: Schlusszeile = end_state line.
  (`autonomous` als Schluesselwort ist die Annahme dieses Tests; die Spec verlangt nur,
  dass Plan und Chat dieselbe Zeile zeigen, und AC-2 unterscheidet autonomous true/false.)
- CLI `workflow.py endstate [#N|name]` -> stdout `ENDSTATE=<kind>` und `FOOTER=<line>`;
  Exit 1 ohne Treffer. CLI `workflow.py waiting "<text>"` / `waiting --clear`
  (State-Feld `waiting_on`), jeder Phasenwechsel leert das Feld.
- `herdr_bridge.build_report`: Token `state` in {erledigt, läuft, du} fuer Phasen 1-7.

workflow.py/herdr_bridge.py werden erst im Testkoerper importiert, die CLI laeuft als
Subprozess: fehlende Funktionen erscheinen als Test-FAIL, nicht als Collection-Error.
AC-11 (footer_gate) besteht voraussichtlich schon vor der Umsetzung: die Spec laesst
footer_gate.py bewusst unveraendert, der Test sichert nur ab, dass ✅/⏳ nicht blocken.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
FOOTER_GATE = HOOKS_DIR / "footer_gate.py"
COMMANDS_DIR = REPO_ROOT / "core" / "commands"
SKILLS_DIR = REPO_ROOT / "skills"

WF = "fix-550-endzustand-demo"
ISSUE = "550"

DONE_TAIL = ". Du kannst /clear ausführen und das nächste Issue starten."
WAIT_TAIL = ". Du musst nichts tun, ich melde mich."
LINE_RE = re.compile(r"^(✅ Erledigt|⏳ Läuft noch|❗ Du):")
KIND_PREFIX = {"done": "✅ Erledigt: ", "waiting": "⏳ Läuft noch: ", "you": "❗ Du: "}
STATE_TOKEN = {"done": "erledigt", "waiting": "läuft", "you": "du"}
STEP_MARKS = ("✔", "▶", "○", "✘")

HERDR = "herdr:\n  enabled: true\n"
DEPLOY_CFG = HERDR + "deploy:\n  command: \"echo deploy\"\n  verify: \"echo verify\"\n"
DEPLOY_AUTO_CFG = DEPLOY_CFG + "  autonomous: true\n"
NO_DEPLOY_CFG = HERDR

EARLY_PHASES = ("phase1_context", "phase2_analyse", "phase3_spec", "phase4_approved",
                "phase5_tdd_red", "phase6_implement", "phase6b_adversary",
                "phase7_validate")


# --- Helpers ---------------------------------------------------------------

def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _bridge():
    sys.path.insert(0, str(HOOKS_DIR))
    import herdr_bridge  # noqa: PLC0415
    return herdr_bridge


def _data(name: str = WF, phase: str = "phase8_complete", wtype: str = "feature",
          **fields) -> dict:
    data = {"name": name, "workflow_type": wtype, "current_phase": phase,
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    return data


def _last(text: str) -> str:
    return text.splitlines()[-1]


def _step_lines(text: str) -> list:
    return [ln for ln in text.splitlines() if ln[:1] in STEP_MARKS]


def _assert_form(line: str, kind: str):
    assert LINE_RE.match(line), line
    assert line.startswith(KIND_PREFIX[kind]), (kind, line)
    if kind == "done":
        assert line.endswith(DONE_TAIL), line
    elif kind == "waiting":
        assert line.endswith(WAIT_TAIL), line
    else:
        assert " — " in line, line


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


def _kv(stdout: str, key: str) -> "str | None":
    for line in stdout.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


# --- AC-1 -------------------------------------------------------------------

def test_no_fachliche_abnahme():
    files = sorted(COMMANDS_DIR.glob("*.md")) + sorted(SKILLS_DIR.glob("*/SKILL.md"))
    assert files, "keine Befehls-/Skill-Dateien gefunden"
    hits = [str(f.relative_to(REPO_ROOT)) for f in files
            if "fachliche abnahme" in f.read_text(encoding="utf-8").lower()]
    assert hits == [], f"„fachliche Abnahme“ kommt noch vor in: {hits}"


# --- AC-2 -------------------------------------------------------------------

def test_render_plan_tail_is_one_of_three():
    wf = _wf()
    cases = [
        # (deploy, autonomous, extra fields, erwartete Art)
        ("off", False, {}, "done"),
        ("unconfigured", False, {}, "done"),
        ("configured", True, {}, "waiting"),
        ("configured", False, {}, "you"),
        ("configured", False, {"deploy_status": "running"}, "waiting"),
        ("configured", False, {"deploy_status": "done"}, "done"),
        ("configured", False, {"deploy_status": "failed"}, "you"),
    ]
    for archived in (False, True):
        for deploy, autonomous, fields, kind in cases:
            data = _data(**fields)
            ctx = (archived, deploy, autonomous, fields)
            out = wf.render_plan(data, archived=archived, deploy=deploy,
                                 autonomous=autonomous)
            tail = _last(out)
            _assert_form(tail, kind)
            es = wf.end_state(data, archived=archived, deploy=deploy,
                              autonomous=autonomous)
            assert es["kind"] == kind, (ctx, es)
            assert es["line"] == tail, (ctx, es, out)
            assert "abgeschlossen" not in tail, (ctx, out)
            if fields.get("deploy_status") == "running" or deploy != "configured":
                assert "Nächster: /70-deploy" not in out, (ctx, out)
            if kind == "you":
                assert tail.startswith(f"❗ Du: /70-deploy #{ISSUE}"), (ctx, tail)
                assert (es.get("cmd") or "").startswith("/70-deploy"), (ctx, es)


# --- AC-3 -------------------------------------------------------------------

def test_archived_without_deploy_is_done():
    wf = _wf()
    for value in (True, "configured"):
        assert wf._plan_deploy_mode(value) == "configured", value
    for value in (False, "off", "unconfigured", None):
        assert wf._plan_deploy_mode(value) == "off", value

    for deploy in ("off", "unconfigured", False):
        out = wf.render_plan(_data(), archived=True, deploy=deploy)
        tail = _last(out)
        _assert_form(tail, "done")
        assert not [ln for ln in _step_lines(out) if "Deploy" in ln], (deploy, out)
        assert "Nächster: /70-deploy" not in out, (deploy, out)
        assert "nicht eingerichtet" not in out, (deploy, out)


# --- AC-4 -------------------------------------------------------------------

def test_failed_autonomous_is_you():
    wf = _wf()
    for archived in (False, True):
        es = wf.end_state(_data(deploy_status="failed"), archived=archived,
                          deploy="configured", autonomous=True)
        assert es["kind"] == "you", es
        assert es["line"].startswith(f"❗ Du: /70-deploy #{ISSUE} — Deploy fehlgeschlagen"), es
        assert (es.get("cmd") or "").startswith("/70-deploy"), es

    # Grund aus deploy_note, falls vorhanden
    es = wf.end_state(_data(deploy_status="failed", deploy_note="Healthcheck 502"),
                      archived=True, deploy="configured", autonomous=True)
    assert es["kind"] == "you", es
    assert "Healthcheck 502" in es["line"], es

    # Ohne Issue-Nummer: /70-deploy ohne #N
    es = wf.end_state(_data(name="demo-endstate", deploy_status="failed"),
                      archived=True, deploy="configured", autonomous=True)
    assert es["kind"] == "you", es
    assert es["line"].startswith("❗ Du: /70-deploy — Deploy fehlgeschlagen"), es


# --- AC-5 -------------------------------------------------------------------

def test_endstate_cli_matches_plan(tmp_path):
    cases = [
        ("p8-auto", DEPLOY_AUTO_CFG, _data(), "waiting"),
        ("p8-manual", DEPLOY_CFG, _data(), "you"),
        ("p8-running", DEPLOY_CFG, _data(deploy_status="running"), "waiting"),
        ("p8-nodeploy", NO_DEPLOY_CFG, _data(), "done"),
        ("p6", NO_DEPLOY_CFG, _data(phase="phase6_implement"), "you"),
    ]
    for label, cfg, data, kind in cases:
        root = tmp_path / label
        root.mkdir()
        proj = _project(root, cfg, active=data)
        es = _cli(proj, "endstate")
        assert es.returncode == 0, (label, es.stdout, es.stderr)
        assert _kv(es.stdout, "ENDSTATE") == kind, (label, es.stdout)
        footer = _kv(es.stdout, "FOOTER")
        assert footer, (label, es.stdout)
        _assert_form(footer, kind)

        plan = _cli(proj, "plan")
        assert plan.returncode == 0, (label, plan.stdout, plan.stderr)
        assert _last(plan.stdout.rstrip("\n")) == footer, (label, plan.stdout, footer)

    # In-Process: Plan-Schluss und end_state stimmen auch fuer fruehe Phasen ueberein
    wf = _wf()
    for phase in EARLY_PHASES:
        data = _data(phase=phase)
        assert _last(wf.render_plan(data, deploy="off")) == \
            wf.end_state(data, deploy="off")["line"], phase


# --- AC-6 -------------------------------------------------------------------

def test_endstate_finds_archived(tmp_path):
    proj = _project(tmp_path, NO_DEPLOY_CFG, archived=_data(name="fix-550-x"))
    res = _cli(proj, "endstate", "#550")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "ENDSTATE") == "done", res.stdout
    footer = _kv(res.stdout, "FOOTER")
    assert footer, res.stdout
    _assert_form(footer, "done")

    # Auch ohne '#'
    res = _cli(proj, "endstate", "550")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "ENDSTATE") == "done", res.stdout

    bad = _cli(proj, "endstate", "#999")
    assert bad.returncode == 1, (bad.stdout, bad.stderr)
    assert _kv(bad.stdout, "ENDSTATE") is None, bad.stdout
    assert bad.stderr.strip(), "Meldung auf stderr erwartet"


# --- AC-7 -------------------------------------------------------------------

def _assert_rule_text(text: str, where: str):
    for form in ("✅ Erledigt", "⏳ Läuft noch", "❗ Du"):
        assert form in text, (where, form)
    assert "ℹ️ Nichts zu tun" not in text, where
    assert "Nichts zu tun" not in text, where
    assert "workflow.py waiting" in text, where


def test_rule_text_has_three_forms():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import sync_skills  # noqa: PLC0415
    _assert_rule_text(sync_skills.marker_block("50-implement", "9.9.9"), "marker_block")

    wf = _wf()
    note = wf.status_note(_data(phase="phase6_implement"))
    assert note, "status_note liefert fuer phase6_implement einen Vermerk"
    _assert_rule_text(note, "status_note")

    # Generierte Skills und Befehlsdateien tragen den alten Wortlaut nicht mehr
    files = sorted(COMMANDS_DIR.glob("*.md")) + sorted(SKILLS_DIR.glob("*/SKILL.md"))
    hits = [str(f.relative_to(REPO_ROOT)) for f in files
            if "ℹ️ Nichts zu tun" in f.read_text(encoding="utf-8")
            or "Nichts-zu-tun" in f.read_text(encoding="utf-8")]
    assert hits == [], f"„ℹ️ Nichts zu tun“ kommt noch vor in: {hits}"


# --- AC-8 -------------------------------------------------------------------

def test_commands_call_endstate():
    for name in ("60-validate.md", "70-deploy.md"):
        text = (COMMANDS_DIR / name).read_text(encoding="utf-8")
        assert "workflow.py endstate" in text, name
        assert "Offen beim PO" not in text, name


# --- AC-9 -------------------------------------------------------------------

def test_herdr_state_token(monkeypatch):
    hb = _bridge()
    wf = _wf()
    assert "state" in hb.TOKEN_NAMES, hb.TOKEN_NAMES  # clear() raeumt es mit ab

    samples = [_data(phase=p) for p in EARLY_PHASES]
    samples.append(_data(phase="phase3_spec", spec_file="docs/specs/x.md"))
    for data in samples:
        rep = hb.build_report(data)
        assert rep is not None, data["current_phase"]
        kind = wf.end_state(data)["kind"]
        assert rep["tokens"].get("state") == STATE_TOKEN[kind], (data, rep)
        assert rep["tokens"]["state"] in ("erledigt", "läuft", "du"), rep

    # Auto-Freigabe laeuft -> läuft
    monkeypatch.setattr(wf, "_auto_approval_pending", lambda _d: True)
    data = _data(phase="phase3_spec", spec_file="docs/specs/x.md")
    assert wf.end_state(data)["kind"] == "waiting"
    assert hb.build_report(data)["tokens"].get("state") == "läuft"

    # Phase 8 leert die Leiste weiterhin
    assert hb.build_report(_data(phase="phase8_complete")) is None


# --- AC-10 ------------------------------------------------------------------

def test_early_phase_you_line_has_command_and_why(monkeypatch):
    wf = _wf()
    assert isinstance(wf.NEXT_WHY, dict) and wf.NEXT_WHY, "NEXT_WHY fehlt/leer"
    whys = {str(v) for v in wf.NEXT_WHY.values()}

    samples = [_data(phase=p) for p in EARLY_PHASES]
    samples.append(_data(phase="phase3_spec", spec_file="docs/specs/x.md"))
    for data in samples:
        step = wf.next_step(data)
        assert step, data
        es = wf.end_state(data)
        assert es["kind"] == "you", (data["current_phase"], es)
        line = es["line"]
        assert line.startswith("❗ Du: "), line
        head, sep, why = line[len("❗ Du: "):].partition(" — ")
        assert sep, line
        assert step in head, (step, line)
        assert why.strip(), line
        assert why in whys, (why, line)
        if step.startswith("/"):
            assert (es.get("cmd") or "").startswith(step), (step, es)

    # Konkret phase3_spec mit Spec: Freigabe-Wort, Warum aus NEXT_WHY
    es = wf.end_state(_data(phase="phase3_spec", spec_file="docs/specs/x.md"))
    assert "approved" in es["line"], es

    # Auto-Freigabe -> waiting, kein ❗
    monkeypatch.setattr(wf, "_auto_approval_pending", lambda _d: True)
    es = wf.end_state(_data(phase="phase3_spec", spec_file="docs/specs/x.md"))
    assert es["kind"] == "waiting", es
    _assert_form(es["line"], "waiting")
    assert "Auto-Freigabe der Spec läuft" in es["line"], es


# --- AC-11 ------------------------------------------------------------------

def _footer_project(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir(parents=True, exist_ok=True)
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{WF}.json").write_text(json.dumps(_data(phase="phase6_implement")))
    (tmp_path / ".claude" / "active_workflow").write_text(WF)
    return tmp_path


def _run_footer_gate(project: Path, message: str, prompt_id: str):
    payload = {"session_id": "sess-550", "hook_event_name": "Stop",
               "cwd": str(project), "last_assistant_message": message,
               "prompt_id": prompt_id}
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env.pop("OPENSPEC_FRAMEWORK", None)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    return subprocess.run([sys.executable, str(FOOTER_GATE)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, cwd=str(project),
                          timeout=30)


def test_footer_gate_accepts_done_and_waiting(tmp_path):
    lines = [
        f"✅ Erledigt: Fix für #{ISSUE} ist gemergt{DONE_TAIL}",
        f"⏳ Läuft noch: CI von PR 12{WAIT_TAIL}",
    ]
    for i, line in enumerate(lines):
        proj = _footer_project(tmp_path / f"case{i}")
        msg = f"Arbeit beendet.\n\n{line}\n⚙ /60-validate · agent-os-openspec 9.9.9"
        res = _run_footer_gate(proj, msg, f"00000000-0000-0000-0000-00000000055{i}")
        assert res.returncode == 0, (line, res.stderr)
        assert "Traceback" not in res.stderr, res.stderr


# --- AC-12 ------------------------------------------------------------------

def test_waiting_on_ci_or_agent_gives_waiting_everywhere(tmp_path):
    wf = _wf()
    hb = _bridge()
    expected = f"⏳ Läuft noch: CI von PR 12{WAIT_TAIL}"

    # In-Process: Phase vor 8 und archiviert ohne Deploy
    for data, archived in ((_data(phase="phase6_implement", waiting_on="CI von PR 12"), False),
                           (_data(waiting_on="CI von PR 12"), True)):
        es = wf.end_state(data, archived=archived, deploy="off")
        assert es["kind"] == "waiting", es
        assert es["line"] == expected, es
    rep = hb.build_report(_data(phase="phase6_implement", waiting_on="CI von PR 12"))
    assert rep["tokens"].get("state") == "läuft", rep

    # Ausnahme: failed bleibt ❗
    es = wf.end_state(_data(deploy_status="failed", waiting_on="CI von PR 12"),
                      archived=True, deploy="configured", autonomous=True)
    assert es["kind"] == "you", es

    # CLI: waiting setzt, endstate zeigt ⏳, --clear stellt den alten Zustand her
    name = "fix-550-wait"
    active = _data(name=name, phase="phase1_context", context_file="docs/context.md")
    proj = _project(tmp_path, NO_DEPLOY_CFG, active=active)
    wf_file = proj / ".claude" / "workflows" / f"{name}.json"

    before = _cli(proj, "endstate")
    assert before.returncode == 0, (before.stdout, before.stderr)
    assert _kv(before.stdout, "ENDSTATE") == "you", before.stdout
    before_footer = _kv(before.stdout, "FOOTER")

    res = _cli(proj, "waiting", "CI von PR 12")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert json.loads(wf_file.read_text()).get("waiting_on") == "CI von PR 12"
    res = _cli(proj, "endstate")
    assert _kv(res.stdout, "ENDSTATE") == "waiting", res.stdout
    assert _kv(res.stdout, "FOOTER") == expected, res.stdout
    rep = hb.build_report(json.loads(wf_file.read_text()))
    assert rep["tokens"].get("state") == "läuft", rep

    res = _cli(proj, "waiting", "--clear")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert not json.loads(wf_file.read_text()).get("waiting_on")
    res = _cli(proj, "endstate")
    assert _kv(res.stdout, "ENDSTATE") == "you", res.stdout
    assert _kv(res.stdout, "FOOTER") == before_footer, res.stdout

    # Phasenwechsel leert waiting_on
    res = _cli(proj, "waiting", "Hintergrund-Agent")
    assert res.returncode == 0, (res.stdout, res.stderr)
    res = _cli(proj, "phase", "phase2_analyse")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert not json.loads(wf_file.read_text()).get("waiting_on")
    res = _cli(proj, "endstate")
    assert _kv(res.stdout, "ENDSTATE") == "you", res.stdout
