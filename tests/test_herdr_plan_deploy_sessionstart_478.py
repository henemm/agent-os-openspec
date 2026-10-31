"""Herdr-Plan: Deploy-Schritt, Plan-Pane beim Sitzungsstart, Skip-Log, agent_status (Issue #478).

Spec: docs/specs/feat-478-plan-deploy-sessionstart.md (AC-1 bis AC-9).

Vertraege, die diese Tests festlegen (zusaetzlich zur Spec):
- Schrittzeilen des Renderers exakt `▶ Deploy  (offen)` / `✔ Deploy` / `○ Deploy`
  (zwei Leerzeichen vor `(offen)`), direkt nach der Zeile `<✔|▶|○> 8 Fertig`.
- Letzte Renderer-Zeile in Phase 8 mit Deploy: `Nächster: /70-deploy #<N>`.
- `workflow.deploy_configured() -> bool` (Config aus CLAUDE_PROJECT_DIR/config.yaml);
  eine Root-config.yaml nur mit `deploy:` gilt als App-Config (#372), die Test-Configs
  enthalten deshalb zusaetzlich `herdr:`.
- Skip-Log: Zeilen mit `skip:` in `.claude/herdr_auto_clear.log`; Phase 8 enthaelt
  „kein Slash-Befehl“, fehlender Positivmarker enthaelt „Marker“.
- Stub-Binary: `pane split` liefert `{"result":{"pane":{"pane_id":"pane-new"}}}`,
  `agent wait` liefert Herdr-0.9.5-Format mit nur `agent_status` (Status aus
  $STUB_STATUS, Default idle; seit #506 darf der Runner es nicht mehr aufrufen),
  `agent prompt` wird bei STUB_STATUS=blocked abgelehnt; `pane send-text <pane> /clear`
  + `pane send-keys <pane> enter` schreibt den SessionStart(clear)-Marker (#506).

Importfehler/fehlende Funktionen erscheinen als Test-FAIL: Module werden erst im
Testkoerper importiert, Hooks/CLI/Runner laufen als Subprozess.
"""

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
BRIDGE = HOOKS_DIR / "herdr_bridge.py"
SESSION_BANNER = HOOKS_DIR / "session_banner.py"
FOOTER_GATE = HOOKS_DIR / "footer_gate.py"

PANE = "pane-478"
WF = "feat-478-plan-deploy-sessionstart"
DEPLOY_CFG = ("herdr:\n  enabled: true\n"
              "deploy:\n  command: \"echo deploy\"\n  verify: \"echo verify\"\n")
AUTO_ON = ("herdr:\n  auto_clear:\n    enabled: true\n    grace_s: 0\n"
           "    idle_timeout_s: 5\n    announce: true\n")

STUB_SCRIPT = r"""#!/bin/bash
{ for a in "$@"; do printf '%s\0' "$a"; done; printf '\n'; } >> "$STUB_LOG"
if [ "$1 $2" = "pane process-info" ]; then printf '{"result":{"process_info":{"foreground_processes":[{"pid":%s}]}}}\n' "${STUB_FG_PID:-${CLAUDE_PID:-0}}"; exit 0; fi  # #496 R2: eigene Session = Vordergrund
if [ "$1 $2" = "pane split" ]; then
  printf '%s\n' '{"result":{"pane":{"pane_id":"pane-new"}}}'
  exit 0
fi
if [ "$1 $2" = "agent wait" ]; then
  printf '{"id":"cli:agent:wait","result":{"agent":{"terminal_id":"t1","agent_status":"%s","pane_id":"P","workspace_id":"w1","tab_id":"t","focused":true}}}\n' "${STUB_STATUS:-idle}"
  exit 0
fi
if [ "$1 $2" = "agent prompt" ] && [ "${STUB_STATUS:-idle}" = blocked ]; then
  exit 1  # Herdr 0.9.5 lehnt bei `blocked` ab (agent_blocked, #506)
fi
if [ "$1 $2" = "pane send-text" ]; then printf '%s' "$4" > "$STUB_LOG.pending"; exit 0; fi
typed=""
if [ "$1 $2" = "pane send-keys" ] && [ -f "$STUB_LOG.pending" ]; then
  typed="$(cat "$STUB_LOG.pending")"; rm -f "$STUB_LOG.pending"
fi
if [ "$1 $2 $4" = "pane send-keys enter" ] && [ "$typed" = "/clear" ]; then  # #506: SessionStart(clear)-Marker wie der Hook
  python3 - "$CLAUDE_PROJECT_DIR/.claude/herdr_signals/$3.session.json" <<'EOF'
import json, os, sys, time
os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
with open(sys.argv[1] + ".tmp", "w") as fh:
    json.dump({"source": "clear", "at": time.time()}, fh)
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
EOF
fi
exit 0
"""

POSITIVE = "✅ **`/clear` ist jetzt gefahrlos** — alles auf Platte gesichert."


# --- Helpers ---------------------------------------------------------------

def _make_stub(root: Path) -> Path:
    stub = root / "herdr-stub"
    stub.write_text(STUB_SCRIPT)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _wf_data(name: str = WF, phase: str = "phase8_complete", wtype: str = "feature",
             **fields) -> dict:
    data = {"name": name, "workflow_type": wtype, "current_phase": phase,
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    return data


def _project(root: Path, config: "str | None", data: "dict | None") -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    if config is not None:
        (proj / "config.yaml").write_text(config)
    if data is not None:
        (proj / ".claude" / "workflows" / f"{data['name']}.json").write_text(json.dumps(data))
        (proj / ".claude" / "active_workflow").write_text(data["name"])
    return proj


def _env(proj: Path, log: Path, stub, *, herdr: bool = True, **extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    if herdr:
        env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": PANE,
                    "HERDR_BIN_PATH": str(stub), "STUB_LOG": str(log),
                    "CLAUDE_PID": "4242"})  # #496 R2: Stub meldet sie als Vordergrund
    env.update(extra)
    return env


def _case(tmp_path: Path, label: str, config: "str | None", data: "dict | None",
          herdr: bool = True, **env_extra):
    root = tmp_path / label
    root.mkdir()
    proj = _project(root, config, data)
    log = root / "stub.log"
    env = _env(proj, log, _make_stub(root), herdr=herdr, **env_extra)
    return proj, log, env


def _run(argv, env, cwd, stdin=None, timeout: float = 30):
    return subprocess.run(argv, capture_output=True, text=True, env=env, cwd=str(cwd),
                          input=stdin, timeout=timeout)


def _calls(log: Path) -> list:
    if not log.exists():
        return []
    out = []
    for line in log.read_bytes().decode("utf-8", "replace").split("\n"):
        if line:
            out.append(line.split("\0")[:-1] if line.endswith("\0") else line.split("\0"))
    return out


def _kind(args: list) -> str:
    return " ".join(args[:2])


def _of(calls: list, kind: str) -> list:
    return [c for c in calls if _kind(c) == kind]


def _wait_kind(log: Path, kind: str, timeout: float = 5.0) -> list:
    deadline = time.monotonic() + timeout
    found = _of(_calls(log), kind)
    while not found and time.monotonic() < deadline:
        time.sleep(0.05)
        found = _of(_calls(log), kind)
    return found


def _flag(args: list, flag: str) -> "str | None":
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            return args[i + 1]
    return None


def _render(*args, **kwargs) -> str:
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow.render_plan(*args, **kwargs)


def _step_lines(text: str) -> list:
    return [ln for ln in text.splitlines() if ln[:1] in ("✔", "▶", "○")]


def _banner(proj: Path, env: dict, source: str = "startup"):
    return _run([sys.executable, str(SESSION_BANNER)], env, proj,
                stdin=json.dumps({"source": source, "cwd": str(proj)}))


def _norm(res, proj: Path, root: Path) -> str:
    return res.stdout.replace(str(proj), "<P>").replace(str(root), "<R>")


# --- AC-1 -------------------------------------------------------------------

def test_render_phase8_with_deploy_shows_open_deploy():
    out = _render(_wf_data(), deploy=True)
    lines = out.splitlines()
    steps = _step_lines(out)
    assert "✔ 8 Fertig" in steps, steps
    assert steps.index("✔ 8 Fertig") + 1 == steps.index("▶ Deploy  (offen)"), steps
    assert steps[-1] == "▶ Deploy  (offen)", steps
    assert lines[-1] == "Nächster: /70-deploy #478", lines
    assert "abgeschlossen" not in out, out


# --- AC-2 -------------------------------------------------------------------

def test_render_deploy_archived_and_early_phase():
    out = _render(_wf_data(), archived=True, deploy=True)
    steps = _step_lines(out)
    assert steps.index("✔ 8 Fertig") + 1 == steps.index("✔ Deploy"), steps
    assert "▶" not in out, out
    assert out.splitlines()[-1] == "abgeschlossen", out

    early = _render(_wf_data(phase="phase5_tdd_red"), deploy=True)
    esteps = _step_lines(early)
    assert esteps[-1] == "○ Deploy", esteps
    assert "▶ 5 TDD-RED  (läuft)" in esteps, esteps


# --- AC-3 -------------------------------------------------------------------

def test_render_without_deploy_unchanged():
    for data, kwargs in ((_wf_data(), {}),
                         (_wf_data(), {"archived": True}),
                         (_wf_data(phase="phase5_tdd_red"), {})):
        base = _render(data, **kwargs)
        assert "Deploy" not in base, base
        assert _render(data, deploy=False, **kwargs) == base
    out = _render(_wf_data())
    assert out.splitlines()[-1] == "abgeschlossen", out
    assert _step_lines(out)[-1] == "✔ 8 Fertig", out


# --- AC-4 -------------------------------------------------------------------

def test_cli_plan_uses_deploy_config(tmp_path):
    proj, log, env = _case(tmp_path, "full", DEPLOY_CFG, _wf_data(), herdr=False)
    res = _run([sys.executable, str(WORKFLOW_PY), "plan"], env, proj)
    assert res.returncode == 0, res.stderr
    assert "▶ Deploy  (offen)" in res.stdout, res.stdout
    assert "Nächster: /70-deploy #478" in res.stdout, res.stdout

    for label, cfg in (("only-command",
                        "herdr:\n  enabled: true\ndeploy:\n  command: \"echo x\"\n"),
                       ("no-deploy", "herdr:\n  enabled: true\n")):
        proj, log, env = _case(tmp_path, label, cfg, _wf_data(), herdr=False)
        res = _run([sys.executable, str(WORKFLOW_PY), "plan"], env, proj)
        assert res.returncode == 0, (label, res.stderr)
        assert "Deploy" not in res.stdout, (label, res.stdout)
        assert "abgeschlossen" in res.stdout, (label, res.stdout)

    # deploy_configured() folgt derselben Regel (command UND verify)
    code = ("import sys; sys.path.insert(0, %r); import workflow; "
            "print(workflow.deploy_configured())" % str(HOOKS_DIR))
    proj, log, env = _case(tmp_path, "fn", DEPLOY_CFG, None, herdr=False)
    res = _run([sys.executable, "-c", code], env, proj)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "True", res.stdout


# --- AC-5 -------------------------------------------------------------------

def test_next_step_phase8_unchanged(tmp_path):
    proj, log, env = _case(tmp_path, "p8", DEPLOY_CFG, None, herdr=False)
    code = ("import sys; sys.path.insert(0, %r); import workflow; "
            "d = {'name': %r, 'workflow_type': 'feature', "
            "'current_phase': 'phase8_complete', 'phase_transitions': [], 'phase_log': []}; "
            "print(repr(workflow.next_step(d)), repr(workflow.expected_footer_command(d)), "
            "workflow.deploy_configured())" % (str(HOOKS_DIR), WF))
    res = _run([sys.executable, "-c", code], env, proj)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "None None True", res.stdout


# --- AC-6 -------------------------------------------------------------------

def test_session_start_opens_pane_for_active_workflow(tmp_path):
    cfg = "herdr:\n  enabled: true\n"
    for source in ("startup", "clear"):
        proj, log, env = _case(tmp_path, source, cfg, _wf_data(phase="phase5_tdd_red"))
        res = _banner(proj, env, source)
        assert res.returncode == 0, res.stderr
        splits = _wait_kind(log, "pane split")
        assert splits, f"{source}: kein pane split: {_calls(log)}"
        assert splits[0][2] == PANE, splits[0]
        assert _flag(splits[0], "--direction") == "right", splits[0]

        base_proj, _, base_env = _case(tmp_path, f"{source}-plain", cfg,
                                       _wf_data(phase="phase5_tdd_red"), herdr=False)
        base = _banner(base_proj, base_env, source)
        assert base.returncode == 0, base.stderr
        assert _norm(res, proj, tmp_path / source) == \
            _norm(base, base_proj, tmp_path / f"{source}-plain")
        assert res.stderr == base.stderr == "" or res.stderr == base.stderr


# --- AC-7 -------------------------------------------------------------------

def test_session_start_no_pane_without_workflow_or_disabled(tmp_path):
    # Positiv-Kontrolle
    proj, log, env = _case(tmp_path, "control", "herdr:\n  enabled: true\n",
                           _wf_data(phase="phase5_tdd_red"))
    assert _banner(proj, env).returncode == 0
    assert _wait_kind(log, "pane split"), "Kontrolle: SessionStart oeffnet keinen Pane"

    cases = (
        ("no-workflow", "herdr:\n  enabled: true\n", None),
        ("plan-off", "herdr:\n  plan_pane:\n    enabled: false\n",
         _wf_data(phase="phase5_tdd_red")),
    )
    for label, cfg, data in cases:
        proj, log, env = _case(tmp_path, label, cfg, data)
        res = _banner(proj, env)
        assert res.returncode == 0, (label, res.stderr)
        time.sleep(1.5)
        assert _of(_calls(log), "pane split") == [], (label, _calls(log))


# --- AC-8 -------------------------------------------------------------------

def _hook_message(*blocks: str, du: str = "") -> str:
    parts = ["Phase abgeschlossen.", *blocks]
    if du:
        parts.append(du)
    parts.append("⚙ /40-tdd-red · agent-os-openspec 3.43.1")
    return "\n\n".join(parts)


def _run_footer(proj: Path, env: dict, message: str):
    payload = {"session_id": "sess-478", "hook_event_name": "Stop", "cwd": str(proj),
               "last_assistant_message": message,
               "prompt_id": "11111111-2222-3333-4444-555555555555"}
    return _run([sys.executable, str(FOOTER_GATE)], env, proj, stdin=json.dumps(payload))


def _skip_log(proj: Path) -> str:
    path = proj / ".claude" / "herdr_auto_clear.log"
    return path.read_text() if path.exists() else ""


def test_auto_clear_logs_skip_reason_only_when_enabled(tmp_path):
    scenarios = (
        # (label, phase, message, erwarteter Grund)
        ("phase8", "phase8_complete", _hook_message(POSITIVE, du="❗ Du: `/70-deploy #478`"), "kein Slash-Befehl"),
        ("nomarker", "phase6_implement",
         _hook_message("Alles erledigt, weiter geht es gleich.",
                       du="❗ Du: `/50-implement #478` — der naechste Pflicht-Schritt"),
         "keine Grenze vermerkt"),
    )
    for label, phase, message, reason in scenarios:
        data = _wf_data(phase=phase)
        proj, log, env = _case(tmp_path, f"{label}-on", AUTO_ON, data)
        res = _run_footer(proj, env, message)
        base_proj, _, base_env = _case(tmp_path, f"{label}-base", AUTO_ON, data, herdr=False)
        base = _run_footer(base_proj, base_env, message)
        assert res.returncode == base.returncode, (label, res.stderr, base.stderr)
        assert res.stdout == base.stdout, label
        text = _skip_log(proj)
        skips = [ln for ln in text.splitlines() if "skip:" in ln]
        assert skips, f"{label}: keine skip:-Zeile im Log: {text!r}"
        assert any(reason in ln for ln in skips), f"{label}: {reason!r} fehlt: {skips}"
        time.sleep(0.8)
        assert _calls(log) == [], f"{label}: Runner gestartet: {_calls(log)}"
        assert _skip_log(base_proj) == "", f"{label}: Log ausserhalb Herdr"

        # ohne Opt-in: keine Log-Datei
        proj, log, env = _case(tmp_path, f"{label}-off", "herdr:\n  enabled: true\n", data)
        res = _run_footer(proj, env, message)
        assert res.returncode == base.returncode, (label, res.stderr)
        assert not (proj / ".claude" / "herdr_auto_clear.log").exists(), label
        time.sleep(0.5)
        assert _calls(log) == [], f"{label}-off: Stub aufgerufen: {_calls(log)}"


# --- AC-9 -------------------------------------------------------------------

def _run_runner(proj: Path, env: dict, command: str = "/50-implement #478",
                phase: str = "phase6_implement"):
    argv = [sys.executable, str(BRIDGE), "auto-clear", "--pane", PANE, "--workflow", WF,
            "--phase", phase, "--command", command, "--grace", "0", "--settle", "0",
            "--idle-timeout", "5", "--announce", "0"]
    return _run(argv, env, proj)


def test_runner_ignores_herdr_agent_status(tmp_path):
    # #506 ersetzt test_runner_reads_real_agent_status_field: Herdrs Status (auch
    # `blocked` wie beim PO-Manifest) entscheidet nicht mehr, `agent wait` entfaellt.
    cmd = "/50-implement #478"
    data = _wf_data(phase="phase6_implement")

    for status in ("idle", "blocked"):
        proj, log, env = _case(tmp_path, status, AUTO_ON, data, STUB_STATUS=status)
        # Kurz-Alias im Projekt: der Runner tippt die Kurzform (#499, sonst Plugin-Form)
        alias = proj / ".claude" / "commands" / "50-implement.md"
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias.write_text("Alias\n")
        res = _run_runner(proj, env, cmd)
        assert res.returncode == 0, res.stderr
        assert "Traceback" not in res.stderr, res.stderr
        assert _of(_calls(log), "agent wait") == [], (status, _calls(log))
        assert _of(_calls(log), "agent prompt") == [], (status, _calls(log))
        enter = ["pane", "send-keys", PANE, "enter"]
        typed = [c for c in _calls(log) if c[:1] == ["pane"]]
        assert typed == [["pane", "send-text", PANE, "/clear"], enter,
                         ["pane", "send-text", PANE, cmd], enter], \
            (status, _calls(log), _skip_log(proj))
        assert "OK" in _skip_log(proj), _skip_log(proj)
