"""Nacharbeit zu den Endzustaenden und zur Auftragsliste (Issue #555, zu #550/#551).

Spec: docs/specs/fix-555-nacharbeit-endzustand.md (AC-1 bis AC-9).

Vertraege aus der Spec (Implementation Details), die diese Tests festlegen:
- Die zweite `_one_line` (Auskunft `observable-surface`) heisst `_flat_line`
  (ohne `rstrip(".")`); `_one_line` schneidet den Schlusspunkt ab.
- `cmd_waiting` ruft nach dem Schreiben `_herdr("report", ...)`, fail-open.
- `deploy_note` zaehlt nur als `str`.
- `end_state(data, ..., self_driven=False)`: mit `self_driven` und Slash-Schritt in
  Phasen < 8 -> `waiting`, `cmd` = Befehl, Zeile
  `⏳ Läuft noch: Claude führt <Befehl> selbst aus. Du musst nichts tun, ich melde mich.`
- `queue_end_args(data)` liefert zusaetzlich `self_driven`
  (= Autonomie `auto` UND offener autarker Auftrag; Kill-Switch -> False);
  `herdr_bridge.build_report` nutzt `queue_end_args`.
- `end_state` ignoriert `queue_next` gleich der eigenen Issue-Nummer.

workflow.py/herdr_bridge.py werden erst im Testkoerper importiert; CLI und Config-
abhaengige Aufrufe laufen als Subprozess (frischer Config-Cache je Aufruf).
AC-9 (footer_gate) ist voraussichtlich schon vor der Umsetzung gruen: footer_gate.py
bleibt laut Spec unveraendert, der Test sichert nur das fail-open ohne ❗-Zeile ab.
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
SYNC_SKILLS = REPO_ROOT / "scripts" / "sync_skills.py"

WF = "fix-555-demo"
ISSUE = 555
WAIT_TAIL = ". Du musst nichts tun, ich melde mich."
AUTO_CFG = "autonomy:\n  mode: auto\n"
MANUAL_CFG = "autonomy:\n  mode: manual\n"
KILL_CFG = AUTO_CFG + "auftrag:\n  enabled: false\n"

EARLY_SLASH = {
    # Phase -> zusaetzliche Felder, damit next_step() einen Slash-Befehl liefert
    "phase1_context": {},
    "phase2_analyse": {},
    "phase3_spec": {},
    "phase4_approved": {},
    "phase5_tdd_red": {},
    "phase6_implement": {},
    "phase6b_adversary": {},
    "phase7_validate": {},
}


# --- Helpers ---------------------------------------------------------------

def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _data(name: str = WF, phase: str = "phase8_complete", **fields) -> dict:
    data = {"name": name, "workflow_type": "feature", "current_phase": phase,
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    return data


def _self_line(cmd: str) -> str:
    return f"⏳ Läuft noch: Claude führt {cmd} selbst aus{WAIT_TAIL}"


def _project(root: Path, config: "str | None", active: "dict | None" = None) -> Path:
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
    return proj


def _write_auftrag(proj: Path, issues, autark: bool) -> None:
    path = proj / ".claude" / "auftrag.json"
    path.write_text(json.dumps({
        "issues": [{"n": n, "status": s} for n, s in issues],
        "autark": autark, "note": "",
        "created": "2026-11-09T10:00:00Z", "updated": "2026-11-09T10:00:00Z",
    }))


def _env(proj: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_"))
           and k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PLUGIN_ROOT")}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    return env


def _cli(proj: Path, *args: str):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args], capture_output=True,
                          text=True, env=_env(proj), cwd=str(proj), timeout=60)


def _kv(stdout: str, key: str) -> "str | None":
    for line in stdout.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _last(text: str) -> str:
    return text.rstrip("\n").splitlines()[-1]


def _sidebar(proj: Path, data: dict) -> dict:
    """`herdr_bridge.build_report` und `queue_end_args` im frischen Prozess."""
    code = ("import json, sys\n"
            f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            "import herdr_bridge, workflow\n"
            "data = json.loads(sys.stdin.read())\n"
            "rep = herdr_bridge.build_report(data)\n"
            "print(json.dumps({'state': rep['tokens']['state'],\n"
            "                  'args': workflow.queue_end_args(data)}))\n")
    res = subprocess.run([sys.executable, "-c", code], input=json.dumps(data),
                         capture_output=True, text=True, env=_env(proj),
                         cwd=str(proj), timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


# --- AC-1 -------------------------------------------------------------------

def test_waiting_trailing_dot_and_observable_surface_unchanged(tmp_path):
    wf = _wf()
    # Endzeilen-Helfer schneidet den Schlusspunkt ab; die Auskunft hat ihren eigenen
    assert wf._one_line("CI.") == "CI", wf._one_line("CI.")
    assert hasattr(wf, "_flat_line"), "zweite _one_line soll _flat_line heissen"
    assert wf._flat_line("a.\n  b.") == "a. b.", wf._flat_line("a.\n  b.")

    # In-Process: waiting_on mit Schlusspunkt -> kein doppelter Punkt
    es = wf.end_state(_data(phase="phase6_implement", waiting_on="CI."))
    assert es["line"] == f"⏳ Läuft noch: CI{WAIT_TAIL}", es
    assert ".." not in es["line"], es

    # CLI: waiting "CI." -> endstate FOOTER ohne doppelten Punkt
    proj = _project(tmp_path, None, active=_data(phase="phase6_implement"))
    res = _cli(proj, "waiting", "CI.")
    assert res.returncode == 0, (res.stdout, res.stderr)
    res = _cli(proj, "endstate")
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert _kv(res.stdout, "ENDSTATE") == "waiting", res.stdout
    footer = _kv(res.stdout, "FOOTER")
    assert footer == f"⏳ Läuft noch: CI{WAIT_TAIL}", footer
    assert ".." not in footer, footer

    # observable-surface liefert unveraendert genau fuenf Zeilen
    subprocess.run(["git", "init", "-q", "."], cwd=proj, check=True)
    res = _cli(proj, "observable-surface")
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines = res.stdout.rstrip("\n").split("\n")
    assert len(lines) == 5, lines
    keys = [ln.split("=", 1)[0] for ln in lines]
    assert keys == ["OBSERVABLE_SURFACE", "REASON", "FILES", "ROOT", "CONFIG"], lines


# --- AC-2 -------------------------------------------------------------------

def test_cmd_waiting_triggers_sidebar_report(tmp_path, monkeypatch):
    wf = _wf()
    proj = _project(tmp_path, None, active=_data(phase="phase6_implement"))
    wf_file = proj / ".claude" / "workflows" / f"{WF}.json"
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    monkeypatch.chdir(proj)

    calls = []
    monkeypatch.setattr(wf, "_herdr", lambda action, data=None: calls.append(action))
    wf.cmd_waiting(["CI von PR 12", WF])
    assert json.loads(wf_file.read_text()).get("waiting_on") == "CI von PR 12"
    assert "report" in calls, f"_herdr('report') fehlt nach waiting: {calls}"

    calls.clear()
    wf.cmd_waiting(["--clear", WF])
    assert not json.loads(wf_file.read_text()).get("waiting_on")
    assert "report" in calls, f"_herdr('report') fehlt nach --clear: {calls}"

    # fail-open: ein werfender Stub bricht cmd_waiting nicht ab
    def boom(action, data=None):
        raise RuntimeError("herdr kaputt")

    monkeypatch.setattr(wf, "_herdr", boom)
    wf.cmd_waiting(["Hintergrund-Agent", WF])
    assert json.loads(wf_file.read_text()).get("waiting_on") == "Hintergrund-Agent"
    wf.cmd_waiting(["--clear", WF])
    assert not json.loads(wf_file.read_text()).get("waiting_on")


# --- AC-3 -------------------------------------------------------------------

def test_non_string_deploy_note_ignored():
    wf = _wf()
    expected = f"❗ Du: /70-deploy #{ISSUE} — Deploy fehlgeschlagen, bitte neu anstoßen"
    for note in (["timeout", "ssh"], 42, {"reason": "x"}, 3.5, True):
        es = wf.end_state(_data(deploy_status="failed", deploy_note=note),
                          deploy="configured")
        line = es["line"]
        assert es["kind"] == "you", (note, es)
        assert line == expected, (note, line)
        assert "[" not in line and "{" not in line and "(" not in line, (note, line)

    # Ein String bleibt erlaubt
    es = wf.end_state(_data(deploy_status="failed", deploy_note="timeout"),
                      deploy="configured")
    assert "Deploy fehlgeschlagen (timeout), bitte neu anstoßen" in es["line"], es


# --- AC-4 -------------------------------------------------------------------

def test_self_driven_open_step_is_waiting():
    wf = _wf()
    for phase, extra in EARLY_SLASH.items():
        data = _data(phase=phase, **extra)
        step = wf.next_step(data)
        assert step and step.startswith("/"), (phase, step)
        cmd = wf.expected_footer_command(data)

        es = wf.end_state(data, self_driven=True)
        assert es["kind"] == "waiting", (phase, es)
        assert es["cmd"] == cmd, (phase, es)
        assert es["line"] == _self_line(cmd), (phase, es)
        assert "❗" not in es["line"], (phase, es)

        # Ohne autarken Auftrag bzw. manual: unveraendert ❗ wie in #550
        es = wf.end_state(data, self_driven=False)
        assert es["kind"] == "you", (phase, es)
        assert es["line"].startswith(f"❗ Du: {cmd} — "), (phase, es)
        assert wf.end_state(data) == es, phase

    # Freigabe-Wort bleibt ❗ auch mit self_driven
    data = _data(phase="phase3_spec", spec_file="docs/specs/x.md")
    es = wf.end_state(data, self_driven=True)
    assert es["kind"] == "you", es
    assert es["line"].startswith("❗ Du: "), es
    assert "approved" in es["line"], es

    # Phase 8 (ohne Deploy) bleibt ✅ — self_driven betrifft nur Phasen < 8
    es = wf.end_state(_data(), deploy="off", self_driven=True)
    assert es["kind"] == "done", es
    es = wf.end_state(_data(phase="phase6_implement"), archived=True, deploy="off",
                      self_driven=True)
    assert es["kind"] == "done", es


# --- AC-5 -------------------------------------------------------------------

def test_plan_endstate_sidebar_agree_with_self_driven(tmp_path):
    cmd = f"/50-implement #{ISSUE}"
    cases = [
        # label, config, autark, erwartete Art, erwartete Zeile (None = nur Art pruefen)
        ("auto-autark", AUTO_CFG, True, "waiting", _self_line(cmd)),
        ("auto-not-autark", AUTO_CFG, False, "you", None),
        ("manual-autark", MANUAL_CFG, True, "you", None),
        ("kill-switch", KILL_CFG, True, "you", None),
    ]
    token = {"waiting": "läuft", "you": "du", "done": "erledigt"}
    for label, cfg, autark, kind, line in cases:
        root = tmp_path / label
        root.mkdir()
        data = _data(phase="phase6_implement")
        proj = _project(root, cfg, active=data)
        _write_auftrag(proj, [(ISSUE, "open"), (556, "open")], autark=autark)

        es = _cli(proj, "endstate")
        assert es.returncode == 0, (label, es.stdout, es.stderr)
        assert _kv(es.stdout, "ENDSTATE") == kind, (label, es.stdout)
        footer = _kv(es.stdout, "FOOTER")
        assert footer, (label, es.stdout)
        if line is not None:
            assert footer == line, (label, footer)
        else:
            assert footer.startswith(f"❗ Du: {cmd} — "), (label, footer)

        plan = _cli(proj, "plan")
        assert plan.returncode == 0, (label, plan.stdout, plan.stderr)
        assert _last(plan.stdout) == footer, (label, plan.stdout, footer)

        side = _sidebar(proj, data)
        assert side["state"] == token[kind], (label, side)
        assert "self_driven" in side["args"], (label, side)
        assert side["args"]["self_driven"] is (kind == "waiting"), (label, side)


# --- AC-6 -------------------------------------------------------------------

def test_end_state_ignores_own_issue_in_queue_next():
    wf = _wf()
    data = _data()
    for autark in (True, False):
        for own in (ISSUE, str(ISSUE)):
            for archived in (False, True):
                es = wf.end_state(data, archived=archived, deploy="off",
                                  queue_next=own, autark=autark)
                assert es["kind"] == "done", (autark, own, archived, es)
                assert es["line"].startswith("✅ Erledigt: "), es
                assert f"#{ISSUE} aus deinem Auftrag" not in es["line"], es
                assert f"/00-intake #{ISSUE}" not in es["line"], es
                assert es["cmd"] is None, es

    # Fremde Nummer bleibt die Auftragszeile
    es = wf.end_state(data, deploy="off", queue_next=556, autark=True)
    assert es["kind"] == "waiting", es
    assert es["line"] == f"⏳ Läuft noch: Claude startet #556 aus deinem Auftrag{WAIT_TAIL}", es
    es = wf.end_state(data, deploy="off", queue_next=556, autark=False)
    assert es["kind"] == "you", es
    assert es["line"] == "❗ Du: /00-intake #556 — nächstes Issue aus deinem Auftrag", es


# --- AC-7 -------------------------------------------------------------------

def _chain_paragraphs(text: str) -> list:
    return [p for p in re.split(r"\n\s*\n", text) if "Kette bei offenem Auftrag" in p]


def test_command_texts_chain_only_on_auftrag_and_skills_synced():
    files = {
        "core/commands/60-validate.md": COMMANDS_DIR / "60-validate.md",
        "core/commands/70-deploy.md": COMMANDS_DIR / "70-deploy.md",
        "skills/60-validate/SKILL.md": SKILLS_DIR / "60-validate" / "SKILL.md",
        "skills/70-deploy/SKILL.md": SKILLS_DIR / "70-deploy" / "SKILL.md",
    }
    for label, path in files.items():
        text = path.read_text(encoding="utf-8")
        paras = _chain_paragraphs(text)
        assert paras, f"{label}: Absatz „Kette bei offenem Auftrag“ fehlt"
        for para in paras:
            assert "FOOTER" in para, (label, para)
            assert "aus deinem Auftrag" in para, (label, para)
            assert "/00-intake #M" in para, (label, para)

    for label in ("core/commands/70-deploy.md", "skills/70-deploy/SKILL.md"):
        text = files[label].read_text(encoding="utf-8")
        assert "endstate <name>" in text, label
        assert "Issue-Nummer entfällt" not in text, label
        assert "entfällt ohne Issue-Nummer" not in text, label

    res = subprocess.run([sys.executable, str(SYNC_SKILLS), "--check"],
                         capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120)
    assert res.returncode == 0, (res.stdout, res.stderr)


# --- AC-8 -------------------------------------------------------------------

def test_config_has_auftrag_block_and_no_stale_deploy_text():
    sys.path.insert(0, str(HOOKS_DIR))
    import config_loader  # noqa: PLC0415
    import hook_utils  # noqa: PLC0415
    import yaml  # noqa: PLC0415

    path = REPO_ROOT / "config.yaml"
    text = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, dict), type(loaded)
    assert isinstance(loaded.get("auftrag"), dict), loaded.get("auftrag")
    assert loaded["auftrag"].get("enabled") is True, loaded["auftrag"]
    assert hook_utils.auftrag_settings(loaded) == {"enabled": True}
    assert "Deploy (nicht eingerichtet)" not in text
    assert "endet mit ✅" in text, "Kommentar zu enabled: false nennt das Verhalten nach #550"

    # Wie tests/test_app_config_yaml_372.py::test_ac7_template_keys_classified
    keys = set(re.findall(r"^([A-Za-z_][\w-]*)\s*:", text, re.MULTILINE))
    known = config_loader.PLUGIN_CONFIG_KEYS | config_loader.GENERIC_CONFIG_KEYS
    assert "auftrag" in keys, sorted(keys)
    assert keys <= known, f"nicht eingeordnet: {sorted(keys - known)}"
    assert config_loader.is_plugin_config(path) is True


# --- AC-9 -------------------------------------------------------------------

def _run_footer_gate(project: Path, message: str, prompt_id: str):
    payload = {"session_id": "sess-555", "hook_event_name": "Stop",
               "cwd": str(project), "last_assistant_message": message,
               "prompt_id": prompt_id}
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env.pop("OPENSPEC_FRAMEWORK", None)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    return subprocess.run([sys.executable, str(FOOTER_GATE)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, cwd=str(project),
                          timeout=30)


def test_footer_gate_accepts_self_driven_waiting_line(tmp_path):
    proj = _project(tmp_path, None, active=_data(phase="phase6_implement"))
    line = _self_line(f"/50-implement #{ISSUE}")
    messages = [
        f"Tests sind rot, Umsetzung startet.\n\n{line}",
        f"Tests sind rot, Umsetzung startet.\n\n{line}\n⚙ /50-implement · agent-os-openspec 9.9.9",
    ]
    for i, msg in enumerate(messages):
        assert "❗" not in msg
        res = _run_footer_gate(proj, msg, f"00000000-0000-0000-0000-00000000555{i}")
        assert res.returncode == 0, (msg, res.stderr)
        assert "Traceback" not in res.stderr, res.stderr
