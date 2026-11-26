"""TDD RED — Issue #404: `qa_gate.py --run` ausrollen und per `qa_gate.require_run`
durchsetzen (Teil A/B) plus Haertungen F002, F004 und #403.

Spec: docs/specs/feat-404-qa-run-durchsetzen.md (AC-1 bis AC-20).

Alle Gate-Tests laufen von aussen ueber echte Prozesse (`bash_gate.py`, `workflow.py`,
`qa_gate.py`, `post_bash.py` DIESES Arbeitsbaums) gegen Wegwerf-Repos in tmp_path
(Muster: test_adversary_coverage_gate_259.py, test_qa_gate_run_345.py). Gueltige Stempel
entstehen nur ueber einen echten `qa_gate.py --run`-Lauf (F003 sperrt Handschrift);
Manipulationen danach schreibt der Test direkt ins Workflow-JSON bzw. in die Dateien.
Hermetik: cwd/CLAUDE_PROJECT_DIR im tmp-Projekt, ohne Sitzungs-/GIT_*-Variablen und
globale Git-Config; der aktive Workflow steht nur in `.claude/active_workflow`.

Regressionswaechter (heute schon gruen, bleiben gruen): AC-1 (require_run false aendert
nichts) und die Sync-Teilpruefung von AC-20 (dort zusaetzlich `require_run: false`, rot).
"""

import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

WF = "wf-404"
STAMP = "qa_run_stamp"
DIALOG = f"docs/artifacts/{WF}/adversary-dialog.md"
RUN_OUT = f"docs/artifacts/{WF}/test-run-output.txt"
MOD_A, MOD_B = "src_A/module_a.py", "src/module_b.py"
VERIFIED = "VERIFIED:Tests PASSED: 5 passed"
GREEN_CMD = "echo '3 passed in 0.1s'"
RED_CMD = "echo '1 failed, 2 passed in 0.1s'; exit 1"
_SCRUBBED = {"CLAUDE_TOOL_INPUT", "CLAUDE_TOOL_NAME", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT",
             "CLAUDE_CODE_SESSION_ID", "OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK",
             "PYTHONPATH"}


# --- Sandbox ----------------------------------------------------------------

def _env(project_dir=None, **extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _SCRUBBED and not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return {**env, **extra}


def _run(script, args: list, cwd: Path, env=None, stdin=None, check=False, timeout=60):
    io_kw = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
    r = subprocess.run([sys.executable, str(HOOKS_DIR / script), *args], capture_output=True,
                       text=True, cwd=str(cwd), env=env or _env(cwd), timeout=timeout, **io_kw)
    assert not check or r.returncode == 0, f"{script} {args}: {r.stdout}{r.stderr}"
    return r


def _git(args: list, cwd: Path) -> str:
    r = subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=Test",
                        "-c", "commit.gpgsign=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, env=_env())
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


def _write(root: Path, rel: str, text: "str | None" = None) -> Path:
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {rel}\nVALUE = 1\n" if text is None else text)
    return path


def _out(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


def _state_path(root: Path) -> Path:
    return root / ".claude" / "workflows" / f"{WF}.json"


def _state(root: Path) -> dict:
    return json.loads(_state_path(root).read_text())


def _patch_state(root: Path, **fields) -> None:
    data = _state(root)
    data.update(fields)
    _state_path(root).write_text(json.dumps(data, indent=2))


def _configure(root: Path, cmd="__default__", require_run=None, coverage=True) -> None:
    """Sandbox-`.claude/config.yaml` (JSON-Quoting ist gueltiges YAML)."""
    lines = ["qa_gate:"]
    if cmd == "__default__":
        cmd = GREEN_CMD
    if cmd is not None:
        lines.append(f"  test_command: {json.dumps(cmd)}")
    if require_run is not None:
        lines.append(f"  require_run: {json.dumps(require_run)}")
    if len(lines) == 1:
        lines.append("  run_timeout: 60")
    if not coverage:
        lines += ["adversary_coverage_gate:", "  enabled: false"]
    _write(root, ".claude/config.yaml", "\n".join(lines) + "\n")


def _make_dialog(root: Path, cited=(MOD_A, MOD_B)) -> Path:
    """Gestempeltes, gueltiges Adversary-Protokoll, das alle Code-Dateien zitiert (#253/#259)."""
    refs = "".join(f"  Code reference: {c}:1\n" for c in cited)
    art = _write(root, DIALOG, (
        "# Adversary Dialog\n\n## Checkliste\n- [x] AC-1: deckt die Änderung ab — Beweis: Test\n"
        f"{refs}\n## Dialog\n\n### Runde 1\n**Adversary:** A1\n**Implementierer:** B1\n\n"
        "### Runde 2\n**Adversary:** A2\n**Implementierer:** B2\n\nVERDICT: VERIFIED\n"))
    _run("adversary_dialog.py", ["stamp", str(art)], root, check=True)
    _run("adversary_dialog.py", ["validate", str(art)], root, check=True)
    return art


def _project(tmp_path: Path, name="proj", *, phase="phase7_validate", wf_type="feature",
             cmd="__default__", require_run=True, coverage=True) -> Path:
    """Git-Repo: C0 = MOD_A; MOD_B gestagt; gueltiger Dialog; VERIFIED; base_commit = C0.

    Ohne Stempel-Pflicht oeffnet dieser Stand heute Commit und Phase 8 (Fixture-Kontrolle
    in AC-1)."""
    proj = tmp_path / name
    proj.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], proj)
    _write(proj, ".gitignore", ".claude/\n")
    _write(proj, "README.md")
    _write(proj, MOD_A)
    _git(["add", "-A"], proj)
    _git(["commit", "-q", "-m", "init"], proj)
    base = _git(["rev-parse", "HEAD"], proj)
    _write(proj, ".claude/active_workflow", WF)
    _write(proj, MOD_B)
    _git(["add", "--", MOD_B], proj)
    _make_dialog(proj)
    arts = [("test_output", f"docs/artifacts/{WF}/red.txt", "phase5_tdd_red"),
            ("adversary_dialog", DIALOG, "phase6b_adversary")]
    data = {"name": WF, "workflow_type": wf_type, "current_phase": phase,
            "context_file": "docs/context.md", "spec_file": "docs/specs/s.md",
            "spec_approved": True, "red_test_done": True, "adversary_verdict": VERIFIED,
            "base_commit": base, "phase_transitions": [], "phase_log": [],
            "test_artifacts": [{"type": t, "path": p, "description": "fixture", "phase": ph,
                                "created": "2026-11-26T10:00:00"} for t, p, ph in arts]}
    _write(proj, f".claude/workflows/{WF}.json", json.dumps(data, indent=2))
    _configure(proj, cmd, require_run, coverage)
    return proj


def _qa_run(root: Path, check=True, env=None):
    """Echter `qa_gate.py --run`-Lauf: schreibt Stempel und Verdict."""
    r = _run("qa_gate.py", ["--run"], root, env=env)
    assert not check or r.returncode == 0, f"qa_gate --run: {_out(r)}"
    return r


def _stamped(tmp_path: Path, name="proj", **kw) -> Path:
    proj = _project(tmp_path, name, **kw)
    _qa_run(proj)
    assert _state(proj)[STAMP]["source"] == "run"
    return proj


def _commit(root: Path, env=None, command="git commit -m wip"):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return _run("bash_gate.py", [], root, env, stdin=payload)


def _phase8(root: Path, cmd=("phase", "phase8_complete"), env=None):
    return _run("workflow.py", list(cmd), root, env)


def _stamp_hint(text: str) -> bool:
    return STAMP in text or "--run" in text


def _blocked_line(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.startswith("BLOCKED:")]
    assert lines, f"keine BLOCKED-Zeile: {text}"
    return lines[0]


# --- AC-1: Schalter aus = unveraendert (Regressionswaechter) -----------------

def test_require_run_false_changes_nothing(tmp_path):
    """AC-1 (heute gruen): require_run false bzw. fehlend, kein Stempel -> Commit und
    Phase 8 wie bisher erlaubt."""
    for i, require_run in enumerate((False, None)):
        proj = _project(tmp_path, f"p{i}", require_run=require_run)
        assert STAMP not in _state(proj)
        r = _commit(proj)
        assert r.returncode == 0, f"require_run={require_run}: {_out(r)}"
        p = _phase8(proj)
        assert p.returncode == 0, f"require_run={require_run}: {_out(p)}"
        assert _state(proj)["current_phase"] == "phase8_complete"


# --- AC-2 bis AC-7: Commit-Gate ---------------------------------------------

def test_commit_blocked_without_stamp(tmp_path):
    """AC-2: require_run true, kein Stempel -> Exit 2 mit Hinweis auf qa_gate.py --run."""
    for phase in ("phase6_implement", "phase6b_adversary", "phase7_validate"):
        proj = _project(tmp_path, phase, phase=phase)
        r = _commit(proj)
        assert r.returncode == 2, f"{phase}: Commit ohne Stempel erlaubt: {_out(r)}"
        assert "--run" in r.stderr, r.stderr


def test_commit_blocked_with_red_stamp(tmp_path):
    """AC-3: Stempel mit exit_code != 0 -> Exit 2, Grund nennt den roten Lauf."""
    proj = _project(tmp_path, cmd=RED_CMD)
    _qa_run(proj, check=False)
    assert _state(proj)[STAMP]["exit_code"] != 0
    _patch_state(proj, adversary_verdict=VERIFIED)  # isoliert die Stempelpruefung vom Verdict
    r = _commit(proj)
    assert r.returncode == 2, f"Commit mit rotem Stempel erlaubt: {_out(r)}"
    assert _stamp_hint(r.stderr), r.stderr
    low = r.stderr.lower()
    assert "exit_code" in low or "exit-code" in low or "exit code" in low or "rot" in low, r.stderr


def test_commit_blocked_with_stale_code(tmp_path):
    """AC-4: gruener Stempel, danach Code-Datei geaendert (Dialog neu gestempelt) ->
    Exit 2, Grund nennt code_sha256."""
    proj = _stamped(tmp_path)
    _write(proj, MOD_B, "# geaendert nach dem Lauf\nVALUE = 2\n")
    _git(["add", "--", MOD_B], proj)
    _run("adversary_dialog.py", ["stamp", str(proj / DIALOG)], proj, check=True)
    r = _commit(proj)
    assert r.returncode == 2, f"Commit mit veraltetem Code-Stand erlaubt: {_out(r)}"
    assert "code_sha256" in r.stderr, r.stderr


def test_commit_blocked_with_tampered_output(tmp_path):
    """AC-5: Ausgabedatei veraendert / durch Symlink ersetzt / ausserhalb des Projekts ->
    Exit 2, Grund nennt die Ausgabedatei."""
    def edited(proj):
        (proj / RUN_OUT).write_text("5 passed in 0.1s\n")

    def symlinked(proj):  # gleicher Inhalt, aber Symlink
        out = proj / RUN_OUT
        copy = proj / "copy.txt"
        shutil.copy(out, copy)
        out.unlink()
        os.symlink(copy, out)

    def outside(proj):  # gleicher Inhalt und sha, aber ausserhalb des Projekts
        ext = tmp_path / f"outside-{proj.name}.txt"
        shutil.copy(proj / RUN_OUT, ext)
        stamp = dict(_state(proj)[STAMP])
        stamp["output_path"] = str(ext)
        _patch_state(proj, **{STAMP: stamp})

    for tamper in (edited, symlinked, outside):
        proj = _stamped(tmp_path, tamper.__name__)
        tamper(proj)
        r = _commit(proj)
        assert r.returncode == 2, f"{tamper.__name__}: Commit erlaubt: {_out(r)}"
        low = r.stderr.lower()
        assert "output" in low or "ausgabedatei" in low, f"{tamper.__name__}: {r.stderr}"


def test_commit_blocked_with_changed_test_command(tmp_path):
    """AC-6: gruener Stempel, danach test_command geaendert -> Exit 2, nennt command_sha256."""
    proj = _stamped(tmp_path)
    _configure(proj, "echo '7 passed in 0.1s'", True)
    r = _commit(proj)
    assert r.returncode == 2, f"Commit nach geaendertem Testbefehl erlaubt: {_out(r)}"
    assert "command_sha256" in r.stderr, r.stderr


def test_commit_passes_with_valid_stamp(tmp_path):
    """AC-7: gueltiger, gruener, passender Stempel (mit code_sha256) -> Commit erlaubt."""
    proj = _stamped(tmp_path)
    stamp = _state(proj)[STAMP]
    assert stamp.get("code_sha256"), f"Stempel ohne code_sha256: {stamp}"
    r = _commit(proj)
    assert r.returncode == 0, _out(r)


def test_feature_fast_commit_blocked_without_stamp(tmp_path):
    """AC-8: feature-fast ab Phase 6 ohne Stempel -> Exit 2; mit gueltigem Stempel erlaubt."""
    proj = _project(tmp_path, "nostamp", wf_type="feature-fast", phase="phase6_implement")
    r = _commit(proj)
    assert r.returncode == 2, f"feature-fast-Commit ohne Stempel erlaubt: {_out(r)}"
    assert _stamp_hint(r.stderr), r.stderr
    ok = _stamped(tmp_path, "stamped", wf_type="feature-fast", phase="phase6_implement")
    r = _commit(ok)
    assert r.returncode == 0, _out(r)


# --- AC-9 bis AC-11: Phase 8 und complete -----------------------------------

def _phase8_cases(tmp_path: Path, wf_type: str) -> None:
    missing = _project(tmp_path, "missing", wf_type=wf_type)
    p = _phase8(missing)
    assert p.returncode != 0, f"{wf_type}: Phase 8 ohne Stempel erreicht: {_out(p)}"
    assert _stamp_hint(p.stderr), p.stderr
    assert _state(missing)["current_phase"] == "phase7_validate"

    invalid = _stamped(tmp_path, "invalid", wf_type=wf_type)
    (invalid / RUN_OUT).write_text("9 passed in 0.1s\n")
    p = _phase8(invalid)
    assert p.returncode != 0, f"{wf_type}: Phase 8 mit manipulierter Ausgabe: {_out(p)}"
    assert _state(invalid)["current_phase"] == "phase7_validate"

    valid = _stamped(tmp_path, "valid", wf_type=wf_type)
    assert _state(valid)[STAMP].get("code_sha256"), _state(valid)[STAMP]
    p = _phase8(valid)
    assert p.returncode == 0, _out(p)
    assert _state(valid)["current_phase"] == "phase8_complete"


def test_phase8_transition_requires_stamp_feature(tmp_path):
    """AC-9: Feature-Workflow: Phase 8 ohne/mit ungueltigem Stempel abgelehnt, gueltig erlaubt."""
    _phase8_cases(tmp_path, "feature")


def test_phase8_transition_requires_stamp_feature_fast(tmp_path):
    """AC-10: feature-fast: gleiche Pruefung beim Wechsel nach phase8_complete."""
    _phase8_cases(tmp_path, "feature-fast")


def test_complete_requires_stamp(tmp_path):
    """AC-11: `complete` ohne Stempel bricht mit demselben Grund ab wie der Phasenwechsel."""
    proj = _project(tmp_path)
    _write(proj, f".claude/workflows/_log/2026-11-26_{WF}.yaml", f"workflow_id: {WF}\n")
    p = _phase8(proj)
    c = _phase8(proj, cmd=("complete",))
    assert p.returncode != 0 and c.returncode != 0, f"{_out(p)}\n---\n{_out(c)}"
    assert _stamp_hint(c.stderr), c.stderr
    assert _blocked_line(c.stderr) == _blocked_line(p.stderr)
    assert _state_path(proj).exists(), "Workflow trotz fehlendem Stempel archiviert"


# --- AC-12 / AC-13: Fehlkonfiguration und ChangeSetError --------------------

def test_require_run_without_test_command_blocks_clearly(tmp_path):
    """AC-12: require_run true ohne test_command -> Commit und Phase 8 blocken mit Hinweis."""
    proj = _project(tmp_path, cmd=None)
    r = _commit(proj)
    assert r.returncode == 2, f"Commit ohne test_command erlaubt: {_out(r)}"
    assert "test_command" in r.stderr, r.stderr
    p = _phase8(proj)
    assert p.returncode != 0, _out(p)
    assert "test_command" in p.stderr, p.stderr


def _failing_git_env(tmp_path: Path, proj: Path, fail="diff") -> dict:
    """`git`-Wrapper vorn im PATH: Unterbefehl `fail` scheitert, der Rest laeuft echt."""
    real = shutil.which("git")
    assert real, "git nicht im PATH"
    wrapper = _write(tmp_path, "fakebin/git", f"""#!/bin/sh
skip=0; sub=""
for a in "$@"; do
  if [ "$skip" = 1 ]; then skip=0; continue; fi
  case "$a" in -C|-c|--git-dir|--work-tree) skip=1 ;; -*) ;; *) sub="$a"; break ;; esac
done
case "$sub" in {fail}) echo "fatal: simulierter Fehler (Test-Wrapper #404)" >&2; exit 128 ;; esac
exec "{real}" "$@"
""")
    wrapper.chmod(0o755)
    return _env(proj, PATH=f"{wrapper.parent}{os.pathsep}{os.environ.get('PATH', '')}")


def test_change_set_error_fails_closed(tmp_path):
    """AC-13: change_set_hash wirft ChangeSetError (git diff scheitert) -> Commit geblockt.

    Abdeckungs-Gate aus, damit nur die Stempelpruefung die Aenderungsmenge braucht;
    Gegenprobe mit require_run false beweist, dass sonst nichts blockt."""
    proj = _stamped(tmp_path, "on", coverage=False)
    r = _commit(proj, env=_failing_git_env(tmp_path, proj))
    assert r.returncode == 2, f"ChangeSetError durchgelassen (fail-open): {_out(r)}"
    ctrl = _project(tmp_path, "off", require_run=False, coverage=False)
    r = _commit(ctrl, env=_failing_git_env(tmp_path, ctrl))
    assert r.returncode == 0, f"Fixture-Kontrolle: {_out(r)}"


# --- AC-14: Datei-Modus -----------------------------------------------------

def _plain_project(tmp_path: Path, name: str, require_run) -> Path:
    root = tmp_path / name
    (root / ".git").mkdir(parents=True)
    _write(root, ".claude/active_workflow", WF + "\n")
    _write(root, f".claude/workflows/{WF}.json", json.dumps({
        "name": WF, "workflow_type": "feature", "current_phase": "phase6_implement",
        "adversary_verdict": None, "test_artifacts": [], "phase_log": []}, indent=2))
    _configure(root, GREEN_CMD, require_run)
    return root


def test_file_mode_deprecation_and_refusal(tmp_path):
    """AC-14: Datei-Modus: require_run false -> wie bisher plus Hinweis auf --run;
    require_run true -> Exit 1 mit Hinweis, kein Verdict."""
    green = "test session starts\n5 passed in 1.2s\n" * 3
    off = _plain_project(tmp_path, "off", False)
    out = _write(off, "test-output.txt", green)
    r = _run("qa_gate.py", [str(out)], off)
    assert r.returncode == 0, _out(r)
    assert str(_state(off).get("adversary_verdict") or "").startswith("VERIFIED"), _out(r)
    assert "--run" in _out(r), f"kein Hinweis auf --run: {_out(r)}"

    on = _plain_project(tmp_path, "on", True)
    out = _write(on, "test-output.txt", green)
    r = _run("qa_gate.py", [str(out)], on)
    assert r.returncode == 1, _out(r)
    assert "--run" in _out(r), _out(r)
    assert not _state(on).get("adversary_verdict"), _state(on)


# --- AC-15 / AC-16: F002 ----------------------------------------------------

class _ReapedProc:
    """Prozess, dessen Leader bereits gereapt ist (poll()/returncode gesetzt)."""
    pid = 999_999
    returncode = 0

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


def test_kill_group_skips_reaped_leader(monkeypatch):
    """AC-15: _kill_group sendet nach dem Reapen kein Signal an die (evtl. fremde) Gruppe."""
    import qa_gate
    calls = []
    monkeypatch.setattr(qa_gate.os, "killpg", lambda pid, sig: calls.append((pid, sig)))
    qa_gate._kill_group(_ReapedProc())
    assert calls == [], f"killpg trotz gereaptem Leader: {calls}"


def test_kill_group_kills_term_ignoring_background_child(tmp_path, monkeypatch):
    """AC-15 (Regression): Timeout -> auch ein Hintergrundkind, das SIGTERM ignoriert, ist
    danach tot. Der Leader bleibt bis nach dem Gruppen-Kill ungereapt (Zombie), damit
    SIGKILL die Gruppe noch sicher erreicht."""
    import qa_gate
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO()))
    pidfile = tmp_path / "child.pid"
    cmd = f"(trap '' TERM; exec sleep 30) & echo $! > {pidfile}; sleep 30"
    code, timed_out = qa_gate.run_and_capture(cmd, tmp_path / "out.txt", 1)
    assert timed_out and code != 0
    pid = int(pidfile.read_text().strip())
    deadline = time.monotonic() + 3
    alive = True
    while alive and time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            alive = False
    if alive:
        os.kill(pid, 9)
    assert not alive, f"SIGTERM-ignorierendes Hintergrundkind {pid} lebt nach dem Timeout"


class _BrokenFile:
    def write(self, data):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        raise BrokenPipeError(32, "Broken pipe")


def test_pump_drains_pipe_on_write_error(monkeypatch):
    """AC-16: Schreibfehler auf die Ausgabedatei -> _pump leert die Pipe weiter, der
    Testprozess (Ausgabe >> Pipe-Puffer) endet ohne Haengen."""
    import qa_gate
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO()))
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys\nfor i in range(40000): sys.stdout.write('x'*60+'\\n')"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    t = threading.Thread(target=lambda: _swallow(qa_gate._pump, proc.stdout, _BrokenFile()),
                         daemon=True)
    start = time.monotonic()
    t.start()
    try:
        code = proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        pytest.fail("Testprozess haengt: _pump leert die Pipe nach dem Schreibfehler nicht")
    t.join(timeout=5)
    assert code == 0
    assert time.monotonic() - start < 15


def _swallow(fn, *args):
    try:
        fn(*args)
    except Exception:
        pass


# --- AC-17: F004 ------------------------------------------------------------

def test_run_refuses_test_command_with_secret_file(tmp_path):
    """AC-17: test_command nennt eine Secret-Datei -> Exit 1, nicht ausgefuehrt;
    harmloser Befehl laeuft."""
    root = _plain_project(tmp_path, "proj", None)
    marker = root / "ran.marker"
    _configure(root, f"touch {marker}; cat .env; {GREEN_CMD}")
    r = _run("qa_gate.py", ["--run"], root)
    assert r.returncode == 1, _out(r)
    assert not marker.exists(), "Testbefehl mit Secret-Datei wurde ausgefuehrt"
    assert not (root / RUN_OUT).exists(), "Artefakt trotz Verweigerung geschrieben"
    _configure(root, f"touch {marker}; {GREEN_CMD}")
    r = _run("qa_gate.py", ["--run"], root)
    assert r.returncode == 0, _out(r)
    assert marker.exists(), "harmloser Testbefehl lief nicht"


# --- AC-18: #403 ------------------------------------------------------------

def test_post_tool_use_failure_records_failed(tmp_path):
    """AC-18: PostToolUseFailure mit `error` -> last_test_run.result failed (ueberschreibt
    ein altes passed); hooks.json registriert post_bash.py dort mit matcher Bash."""
    root = _plain_project(tmp_path, "proj", None)
    _patch_state(root, last_test_run={"result": "passed", "runner": "pytest",
                                      "at": "2026-11-26T09:00:00"})
    payload = {"hook_event_name": "PostToolUseFailure", "tool_name": "Bash",
               "tool_input": {"command": "python3 -m pytest tests/"},
               "error": "Exit code 1\n... 1 failed, 2 passed in 0.1s"}
    r = _run("post_bash.py", [], root, stdin=json.dumps(payload))
    assert r.returncode == 0, _out(r)
    assert (_state(root).get("last_test_run") or {}).get("result") == "failed", _state(root)

    hooks = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    entries = hooks.get("PostToolUseFailure") or []
    assert any(e.get("matcher") == "Bash"
               and any("post_bash.py" in h.get("command", "") for h in e.get("hooks", []))
               for e in entries), f"PostToolUseFailure/Bash -> post_bash.py fehlt: {entries}"


# --- AC-19 / AC-20: Doku, Agenten, generierte Kopien ------------------------

DOCS = ["core/commands/50-implement.md", "core/commands/60-validate.md",
        "core/commands/80-workflow.md", "core/agents/developer-agent.md",
        "core/agents/implementation-validator.md"]


def test_docs_and_agents_use_run_mode():
    """AC-19: kein Datei-Modus-Aufruf, `qa_gate.py --run` genannt, kein pre_commit.test_command."""
    problems = []
    for rel in DOCS:
        text = (REPO_ROOT / rel).read_text()
        if "qa_gate.py docs/artifacts" in text:
            problems.append(f"{rel}: Datei-Modus-Aufruf")
        if "qa_gate.py --run" not in text:
            problems.append(f"{rel}: kein qa_gate.py --run")
        if "pre_commit.test_command" in text:
            problems.append(f"{rel}: pre_commit.test_command")
    assert not problems, "\n".join(problems)


def test_generated_copies_in_sync():
    """AC-20: Sync-Pruefungen ohne Abweichung (Waechter); config.yaml hat require_run: false."""
    for script in ("sync_skills.py", "sync_cloud_agents.py"):
        r = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script), "--check"],
                           capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60)
        assert r.returncode == 0, f"{script} --check: {_out(r)}"
    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())
    section = cfg.get("qa_gate") or {}
    assert "require_run" in section and section["require_run"] is False, section
