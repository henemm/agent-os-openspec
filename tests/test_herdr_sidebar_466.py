"""Herdr-Sidebar-Fortschritt (Issue #466) — Tests gegen ein Stub-Binary.

Spec: docs/specs/feat-466-herdr-sidebar.md (AC-1 bis AC-16).

Das Stub-Binary (Shell-Skript) schreibt pro Aufruf eine Zeile in eine Log-Datei
(Argumente NUL-getrennt). Die Bridge startet es detached, deshalb wird das Log
mit kurzem Poll gelesen; Negativ-Tests warten kurz und pruefen auf ein leeres Log.

Vertrag, den die Tests fuer `herdr_bridge.build_report(data)` festlegen (die Spec
nennt nur Eingabe und Abbildung): Rueckgabe `None` = Clear statt Report, sonst
ein dict `{"title": str, "tokens": {name: wert}}` mit den Tokens workflow, issue,
phase, step, next.

Import-Fehler (Modul fehlt) erscheinen pro Test als FAIL: das Modul wird erst in
`_bridge()` im Testkoerper importiert.
"""

import json
import os
import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
PHASE_LISTENER = HOOKS_DIR / "phase_listener.py"
SESSION_BANNER = HOOKS_DIR / "session_banner.py"

TOKEN_NAMES = ["workflow", "issue", "phase", "step", "next"]
PANE = "pane-466"

STUB_SCRIPT = r"""#!/bin/bash
{ for a in "$@"; do printf '%s\0' "$a"; done; printf '\n'; } >> "$STUB_LOG"
if [ -n "$STUB_META" ]; then
  {
    echo "SID=$(awk '{print $6}' /proc/$$/stat)"
    echo "FD0=$(readlink /proc/$$/fd/0)"
    echo "FD1=$(readlink /proc/$$/fd/1)"
    echo "FD2=$(readlink /proc/$$/fd/2)"
  } > "$STUB_META"
fi
if [ -n "$STUB_STDOUT" ]; then
  echo "stub-stdout-noise"
  echo "stub-stderr-noise" >&2
fi
if [ -n "$STUB_SLEEP" ]; then sleep "$STUB_SLEEP"; fi
exit "${STUB_EXIT:-0}"
"""


# --- Helpers ---------------------------------------------------------------

def _bridge():
    sys.path.insert(0, str(HOOKS_DIR))
    import herdr_bridge  # noqa: PLC0415
    return herdr_bridge


def _make_stub(tmp_path: Path, name: str = "herdr-stub") -> Path:
    stub = tmp_path / name
    stub.write_text(STUB_SCRIPT)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    return proj


def _write_wf(proj: Path, name: str, phase: str, *, active: bool = True, **fields) -> Path:
    data = {"name": name, "workflow_type": "feature", "current_phase": phase,
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    wf = proj / ".claude" / "workflows" / f"{name}.json"
    wf.write_text(json.dumps(data))
    if active:
        (proj / ".claude" / "active_workflow").write_text(name)
    return wf


def _env(proj: Path, log: Path, stub, *, herdr: bool = True, active: str = "",
         **extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "STUB_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    if active:
        env["OPENSPEC_ACTIVE_WORKFLOW"] = active
    if herdr:
        env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": PANE,
                    "HERDR_BIN_PATH": str(stub), "STUB_LOG": str(log)})
    env.update(extra)
    return env


def _run(argv, env, cwd, *, stdin: str = "", timeout: float = 30):
    return subprocess.run(argv, input=stdin, capture_output=True, text=True,
                          env=env, cwd=str(cwd), timeout=timeout)


def _workflow(args, env, cwd, **kw):
    return _run([sys.executable, str(WORKFLOW_PY), *args], env, cwd, **kw)


def _calls(log: Path) -> list:
    if not log.exists():
        return []
    out = []
    for line in log.read_bytes().decode("utf-8", "replace").split("\n"):
        if line:
            out.append(line.split("\0")[:-1] if line.endswith("\0") else line.split("\0"))
    return out


def _wait_calls(log: Path, n: int = 1, timeout: float = 3.0) -> list:
    deadline = time.monotonic() + timeout
    calls = _calls(log)
    while len(calls) < n and time.monotonic() < deadline:
        time.sleep(0.05)
        calls = _calls(log)
    return calls


def _settled_calls(log: Path, n: int = 1) -> list:
    """Wartet auf n Aufrufe, dann kurz, um ein ueberzaehliges Extra zu sehen."""
    _wait_calls(log, n)
    time.sleep(0.3)
    return _calls(log)


def _assert_no_calls(log: Path):
    time.sleep(0.5)
    assert _calls(log) == [], f"Stub wurde unerwartet aufgerufen: {_calls(log)}"


def _flag_values(args: list, flag: str) -> list:
    vals = []
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            vals.append(args[i + 1])
        elif a.startswith(flag + "="):
            vals.append(a[len(flag) + 1:])
    return vals


def _tokens(args: list) -> dict:
    out = {}
    for item in _flag_values(args, "--token"):
        k, _, v = item.partition("=")
        out[k] = v
    return out


def _is_clear(args: list) -> bool:
    return "--clear-title" in args and \
        set(_flag_values(args, "--clear-token")) >= set(TOKEN_NAMES)


def _is_report(args: list) -> bool:
    return args[:2] == ["pane", "report-metadata"] and "--title" in args


def _ready_context_wf(proj: Path, name: str = "feat-466-demo", phase="phase1_context"):
    """Workflow, der ohne weitere Gates nach phase2_analyse wechseln darf."""
    return _write_wf(proj, name, phase, context_file="docs/context.md")


PO_BRIEFING_BODY = (
    "# PO-Briefing\n\n"
    "## Was gebaut wird\n\nEine kleine, klar umrissene Änderung am Modul.\n\n"
    "## Definition of Done\n\nFertig, wenn das beschriebene Verhalten sichtbar eintritt.\n\n"
    "## Wie geprüft wird\n\nEin automatischer Test prüft genau dieses Verhalten.\n\n"
    "## Kritische Anmerkungen\n\n- Keine offenen Punkte erkennbar.\n"
)


def _spec_and_briefing(proj: Path) -> dict:
    spec = proj / "docs" / "specs" / "m" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# Test Spec\n\n## Purpose\n\nBeliebiger Inhalt.\n")
    brief = proj / "docs" / "briefings" / "b.md"
    brief.parent.mkdir(parents=True)
    brief.write_text(PO_BRIEFING_BODY)
    return {"spec_file": "docs/specs/m/spec.md",
            "po_briefing": {"file": "docs/briefings/b.md", "created": "2026-01-01T00:00:00"}}


@pytest.fixture
def setup(tmp_path):
    proj = _project(tmp_path)
    log = tmp_path / "stub.log"
    stub = _make_stub(tmp_path)
    return proj, log, stub


# --- AC-1 -------------------------------------------------------------------

def test_start_reports_workflow_state(setup):
    proj, log, stub = setup
    res = _workflow(["start", "feat-466-demo"], _env(proj, log, stub), proj)
    assert res.returncode == 0, res.stderr
    calls = _settled_calls(log, 1)
    assert len(calls) == 1, calls
    args = calls[0]
    assert args[:3] == ["pane", "report-metadata", PANE], args
    assert _flag_values(args, "--source") == ["user:openspec"], args
    assert _flag_values(args, "--agent") == ["claude"], args
    seq = _flag_values(args, "--seq")
    assert len(seq) == 1 and seq[0].isdigit(), args
    title = _flag_values(args, "--title")
    assert len(title) == 1 and ("feat-466-demo" in title[0] or "#466" in title[0]), args
    tokens = _tokens(args)
    assert set(tokens) == set(TOKEN_NAMES), tokens
    assert tokens["workflow"] == "feat-466-demo"
    assert tokens["issue"] == "466"
    assert tokens["phase"] == "1/8"
    assert tokens["step"] == "CONTEXT"


# --- AC-2 -------------------------------------------------------------------

def test_phase_change_reports_title_and_tokens(setup):
    proj, log, stub = setup
    extra = _spec_and_briefing(proj)
    _write_wf(proj, "feat-466-demo", "phase4_approved", context_file="docs/context.md",
              spec_approved=True, red_test_done=True, **extra)
    res = _workflow(["phase", "phase5_tdd_red"],
                    _env(proj, log, stub, active="feat-466-demo"), proj)
    assert res.returncode == 0, res.stderr
    calls = _settled_calls(log, 1)
    assert len(calls) == 1, calls
    assert _flag_values(calls[0], "--title") == ["#466 5/8 TDD-RED"], calls[0]
    tokens = _tokens(calls[0])
    assert tokens.get("phase") == "5/8"
    assert tokens.get("step") == "TDD-RED"


# --- AC-3 -------------------------------------------------------------------

def test_approval_via_phase_listener_reports(setup):
    proj, log, stub = setup
    extra = _spec_and_briefing(proj)
    wf = _write_wf(proj, "feat-466-demo", "phase3_spec", context_file="docs/context.md",
                   spec_approved=False, **extra)
    res = _run([sys.executable, str(PHASE_LISTENER)],
               _env(proj, log, stub, active="feat-466-demo"), proj,
               stdin=json.dumps({"prompt": "approved"}))
    assert res.returncode == 0, res.stderr
    assert json.loads(wf.read_text())["current_phase"] == "phase4_approved", \
        "Testaufbau: Freigabe ging nicht durch"
    calls = _settled_calls(log, 1)
    assert len(calls) == 1, calls
    tokens = _tokens(calls[0])
    assert tokens.get("phase") == "4/8", calls[0]
    assert tokens.get("step") == "APPROVED", calls[0]


# --- AC-4 -------------------------------------------------------------------

def test_switch_reports_new_active_workflow(setup):
    proj, log, stub = setup
    _write_wf(proj, "feat-466-alpha", "phase1_context", active=True)
    _write_wf(proj, "feat-467-beta", "phase5_tdd_red", active=False)
    res = _workflow(["switch", "feat-467-beta"],
                    _env(proj, log, stub, active="feat-466-alpha"), proj)
    assert res.returncode == 0, res.stderr
    calls = _settled_calls(log, 1)
    assert len(calls) == 1, calls
    tokens = _tokens(calls[0])
    assert tokens.get("workflow") == "feat-467-beta", calls[0]
    assert tokens.get("phase") == "5/8", calls[0]
    assert _flag_values(calls[0], "--title") == ["#467 5/8 TDD-RED"], calls[0]


# --- AC-5 -------------------------------------------------------------------

def test_complete_and_abandon_clear_all_tokens(tmp_path):
    # abandon
    proj = _project(tmp_path / "a")
    log, stub = tmp_path / "a.log", _make_stub(tmp_path, "stub-a")
    _write_wf(proj, "feat-466-demo", "phase5_tdd_red")
    res = _workflow(["abandon", "--reason", "Test"],
                    _env(proj, log, stub, active="feat-466-demo"), proj)
    assert res.returncode == 0, res.stderr
    calls = _settled_calls(log, 1)
    assert calls and _is_clear(calls[-1]), f"abandon ohne Clear: {calls}"
    assert calls[-1][:3] == ["pane", "report-metadata", PANE]

    # complete (Phase-8-Gates per Prozess-Patch umgangen: hier zaehlt nur das Clear)
    proj2 = _project(tmp_path / "c")
    log2, stub2 = tmp_path / "c.log", _make_stub(tmp_path, "stub-c")
    _write_wf(proj2, "feat-466-demo", "phase7_validate")
    (proj2 / ".claude" / "workflows" / "_log" / "x_feat-466-demo.yaml").write_text("x: 1\n")
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(HOOKS_DIR)!r})
        import workflow
        workflow._validate_transition = lambda data, target: None
        sys.argv = ["workflow.py", "complete"]
        workflow.main()
    """)
    res2 = _run([sys.executable, "-c", code],
                _env(proj2, log2, stub2, active="feat-466-demo"), proj2)
    assert res2.returncode == 0, res2.stderr
    calls2 = _settled_calls(log2, 1)
    assert calls2 and _is_clear(calls2[-1]), f"complete ohne Clear: {calls2}"


# --- AC-6 -------------------------------------------------------------------

@pytest.mark.parametrize("missing", ["HERDR_ENV", "HERDR_PANE_ID"])
def test_noop_without_herdr_env(setup, missing):
    proj, log, stub = setup
    env = _env(proj, log, stub, active="feat-466-demo")
    env.pop(missing)
    res = _workflow(["start", "feat-466-demo"], env, proj)
    assert res.returncode == 0 and "Started workflow: feat-466-demo" in res.stdout, res.stderr
    _ready_context_wf(proj)
    res = _workflow(["phase", "phase2_analyse"], env, proj)
    assert res.returncode == 0 and "Set phase to: phase2_analyse" in res.stdout, res.stderr
    _assert_no_calls(log)


# --- AC-7 -------------------------------------------------------------------

def test_noop_with_invalid_binary_path(setup, tmp_path):
    proj, log, stub = setup
    not_exec = tmp_path / "not-exec"
    not_exec.write_text(STUB_SCRIPT)
    not_exec.chmod(0o644)
    a_dir = tmp_path / "a-dir"
    a_dir.mkdir()
    rel_cwd = tmp_path / "relcwd"
    rel_cwd.mkdir()
    rel = rel_cwd / "rel-stub"
    rel.write_text(STUB_SCRIPT)
    rel.chmod(0o755)
    cases = [
        ("nonexistent", str(tmp_path / "does-not-exist"), proj),
        ("relative", "rel-stub", rel_cwd),
        ("not-executable", str(not_exec), proj),
        ("directory", str(a_dir), proj),
    ]
    for label, bin_path, cwd in cases:
        _ready_context_wf(proj)
        env = _env(proj, log, stub, active="feat-466-demo", HERDR_BIN_PATH=bin_path)
        if label == "relative":
            env["CLAUDE_PROJECT_DIR"] = str(proj)
        res = _workflow(["phase", "phase2_analyse"], env, cwd)
        assert res.returncode == 0, f"{label}: {res.stderr}"
        assert "Traceback" not in res.stderr, f"{label}: {res.stderr}"
    _assert_no_calls(log)
    assert not (rel_cwd / "stub.log").exists()


# --- AC-8 -------------------------------------------------------------------

def test_kill_switch_disables_reporting(setup):
    proj, log, stub = setup
    (proj / "config.yaml").write_text("herdr:\n  enabled: false\n")
    _ready_context_wf(proj)
    res = _workflow(["phase", "phase2_analyse"],
                    _env(proj, log, stub, active="feat-466-demo"), proj)
    assert res.returncode == 0, res.stderr
    _assert_no_calls(log)
    # Gegenprobe: ohne Kill-Switch laeuft die Bridge (sonst waere der Test leer)
    (proj / "config.yaml").write_text("herdr:\n  enabled: true\n")
    _ready_context_wf(proj)
    res = _workflow(["phase", "phase2_analyse"],
                    _env(proj, log, stub, active="feat-466-demo"), proj)
    assert res.returncode == 0, res.stderr
    assert _wait_calls(log, 1), "Ohne Kill-Switch muss die Bridge melden"


# --- AC-9 -------------------------------------------------------------------

def test_hanging_binary_does_not_block(setup):
    proj, log, stub = setup
    wf = _ready_context_wf(proj)
    start = time.monotonic()
    res = _workflow(["phase", "phase2_analyse"],
                    _env(proj, log, stub, active="feat-466-demo", STUB_SLEEP="30"),
                    proj, timeout=20)
    elapsed = time.monotonic() - start
    assert res.returncode == 0, res.stderr
    assert elapsed < 2.0, f"workflow.py wartete auf das Stub: {elapsed:.2f}s"
    assert json.loads(wf.read_text())["current_phase"] == "phase2_analyse"
    assert _wait_calls(log, 1), "Stub wurde nie aufgerufen (Bridge nicht verdrahtet)"


# --- AC-10 ------------------------------------------------------------------

def _scenario(tmp_path: Path, label: str, herdr: bool):
    """Hooks + CLI in einem frischen Projekt; liefert [(rc, stdout)] und Log."""
    root = tmp_path / label
    root.mkdir()
    proj = _project(root)
    log = root / "stub.log"
    stub = _make_stub(root)
    extra = _spec_and_briefing(proj)
    env = _env(proj, log, stub, herdr=herdr, active="feat-466-demo",
               STUB_STDOUT="1", STUB_EXIT="1")
    results = []

    _write_wf(proj, "feat-466-demo", "phase3_spec", context_file="docs/context.md",
              spec_approved=False, **extra)
    r = _run([sys.executable, str(PHASE_LISTENER)], env, proj,
             stdin=json.dumps({"prompt": "approved"}))
    results.append(("listener", r))
    r = _run([sys.executable, str(SESSION_BANNER)], env, proj,
             stdin=json.dumps({"source": "startup", "cwd": str(proj)}))
    results.append(("banner", r))
    r = _workflow(["status"], env, proj)
    results.append(("status", r))
    r = _workflow(["phase", "phase3_spec"], env, proj)
    results.append(("phase", r))
    r = _workflow(["start", "feat-466-other"], env, proj)
    results.append(("start", r))
    norm = [(n, r.returncode, r.stdout.replace(str(proj), "<P>")
             .replace(str(root), "<R>")) for n, r in results]
    return norm, log


def test_stdout_and_exit_code_unchanged(tmp_path):
    base, _ = _scenario(tmp_path, "plain", herdr=False)
    herdr, log = _scenario(tmp_path, "herdr", herdr=True)
    for (n1, rc1, out1), (n2, rc2, out2) in zip(base, herdr):
        assert rc1 == rc2, f"{n1}: Exit-Code {rc1} vs {rc2}"
        assert out1 == out2, f"{n1}: stdout weicht ab:\n{out1!r}\n{out2!r}"
        assert "stub-stdout-noise" not in out2
        if n1 in ("listener", "banner") and out2.strip():
            json.loads(out2)  # Hook-JSON bleibt gueltig
    assert _wait_calls(log, 1), "Bridge war nicht aktiv (Stub nie aufgerufen)"


# --- AC-11 ------------------------------------------------------------------

def test_session_start_republishes_for_all_sources(tmp_path):
    for source in ("startup", "resume", "clear", "compact"):
        root = tmp_path / source
        root.mkdir()
        proj = _project(root)
        log, stub = root / "stub.log", _make_stub(root)
        _write_wf(proj, "feat-466-demo", "phase5_tdd_red")
        env = _env(proj, log, stub, active="feat-466-demo")
        res = _run([sys.executable, str(SESSION_BANNER)], env, proj,
                   stdin=json.dumps({"source": source, "cwd": str(proj)}))
        assert res.returncode == 0, res.stderr
        calls = _settled_calls(log, 1)
        assert len(calls) == 1, f"{source}: {calls}"
        assert _is_report(calls[0]), f"{source}: {calls[0]}"
        assert _tokens(calls[0]).get("workflow") == "feat-466-demo", f"{source}: {calls[0]}"
        assert _tokens(calls[0]).get("phase") == "5/8", f"{source}: {calls[0]}"

    # ohne aktiven Workflow: Clear
    root = tmp_path / "none"
    root.mkdir()
    proj = _project(root)
    log, stub = root / "stub.log", _make_stub(root)
    env = _env(proj, log, stub)
    res = _run([sys.executable, str(SESSION_BANNER)], env, proj,
               stdin=json.dumps({"source": "startup", "cwd": str(proj)}))
    assert res.returncode == 0, res.stderr
    calls = _settled_calls(log, 1)
    assert calls and _is_clear(calls[-1]), f"ohne Workflow kein Clear: {calls}"


# --- AC-12 ------------------------------------------------------------------

def test_phase_mapping_table():
    bridge = _bridge()
    expected = {
        "phase1_context": ("1/8", "CONTEXT"),
        "phase2_analyse": ("2/8", "ANALYSE"),
        "phase3_spec": ("3/8", "SPEC"),
        "phase4_approved": ("4/8", "APPROVED"),
        "phase5_tdd_red": ("5/8", "TDD-RED"),
        "phase6_implement": ("6/8", "IMPLEMENT"),
        "phase6b_adversary": ("6/8", "ADVERSARY"),
        "phase7_validate": ("7/8", "VALIDATE"),
    }
    for phase, (nr, step) in expected.items():
        report = bridge.build_report({"name": "feat-466-demo", "current_phase": phase})
        assert report is not None, phase
        assert report["tokens"]["phase"] == nr, phase
        assert report["tokens"]["step"] == step, phase
        assert report["title"] == f"#466 {nr} {step}", phase
        assert set(report["tokens"]) == set(TOKEN_NAMES), phase
    for phase in ("phase8_complete", "phase0_idle", "phase99_unknown"):
        assert bridge.build_report({"name": "feat-466-demo", "current_phase": phase}) is None, phase


# --- AC-13 ------------------------------------------------------------------

def test_next_token_freetext_and_length_limit():
    bridge = _bridge()
    free = bridge.build_report({"name": "feat-466-demo", "current_phase": "phase3_spec",
                                "spec_file": "docs/specs/x.md"})
    assert free["tokens"]["next"] == "approved"
    slash = bridge.build_report({"name": "feat-466-demo", "current_phase": "phase6_implement"})
    assert slash["tokens"]["next"] == "/50-implement #466"
    long_name = "feat-466-a\x07b" + "x" * 200
    rep = bridge.build_report({"name": long_name, "current_phase": "phase6_implement"})
    assert len(rep["title"]) <= 80
    for key, value in rep["tokens"].items():
        assert len(value) <= 80, (key, len(value))
        assert all(ord(c) >= 0x20 for c in value), (key, value)
    assert all(ord(c) >= 0x20 for c in rep["title"])
    assert rep["tokens"]["workflow"].startswith("feat-466-a")


# --- AC-14 ------------------------------------------------------------------

def test_title_without_issue_uses_workflow_name():
    bridge = _bridge()
    rep = bridge.build_report({"name": "demo-login", "current_phase": "phase5_tdd_red"})
    assert rep["title"] == "demo-login 5/8 TDD-RED"
    assert rep["tokens"]["issue"] == ""


# --- AC-15 ------------------------------------------------------------------

def test_conftest_strips_herdr_env(tmp_path):
    for var in ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_BIN_PATH", "HERDR_SOCKET_PATH"):
        assert var not in os.environ, var
    # Nachweis der Fixture selbst: verschachtelter pytest-Lauf mit gesetzten HERDR_*
    (tmp_path / "conftest.py").write_text(textwrap.dedent(f"""
        import importlib.util
        _spec = importlib.util.spec_from_file_location("_repo_conftest",
                                                       {str(REPO_ROOT / "tests" / "conftest.py")!r})
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        globals().update({{k: v for k, v in vars(_mod).items() if not k.startswith("__")}})
    """))
    (tmp_path / "test_inner.py").write_text(textwrap.dedent("""
        import os
        def test_env_clean():
            for var in ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_BIN_PATH", "HERDR_SOCKET_PATH"):
                assert var not in os.environ, var
    """))
    env = dict(os.environ)
    env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": "x", "HERDR_BIN_PATH": "/bin/true",
                "HERDR_SOCKET_PATH": "/tmp/x.sock"})
    res = _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                str(tmp_path / "test_inner.py")], env, tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr


# --- AC-16 ------------------------------------------------------------------

def test_run_herdr_generic_detached_no_shell(tmp_path, monkeypatch):
    proj = _project(tmp_path)
    log, meta = tmp_path / "stub.log", tmp_path / "meta.txt"
    stub = _make_stub(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", PANE)
    monkeypatch.setenv("HERDR_BIN_PATH", str(stub))
    monkeypatch.setenv("STUB_LOG", str(log))
    monkeypatch.setenv("STUB_META", str(meta))
    monkeypatch.setenv("STUB_SLEEP", "3")
    bridge = _bridge()

    seen = []
    real_popen = subprocess.Popen

    def spy(*a, **kw):
        seen.append((a, kw))
        return real_popen(*a, **kw)

    monkeypatch.setattr(subprocess, "Popen", spy)

    injected = tmp_path / "PWNED"
    start = time.monotonic()
    bridge.run_herdr(["notification", "show", f"x; touch {injected}"], wait=False)
    assert time.monotonic() - start < 1.0, "run_herdr(wait=False) kehrte nicht sofort zurueck"

    calls = _wait_calls(log, 1)
    assert calls == [["notification", "show", f"x; touch {injected}"]], calls
    assert not injected.exists(), "Argumente wurden von einer Shell interpretiert"

    assert len(seen) == 1, seen
    popen_args, kw = seen[0]
    assert popen_args[0] == [str(stub), "notification", "show", f"x; touch {injected}"]
    assert not kw.get("shell")
    assert kw.get("start_new_session") is True
    assert kw.get("close_fds") is True
    for stream in ("stdin", "stdout", "stderr"):
        assert kw.get(stream) == subprocess.DEVNULL, stream

    deadline = time.monotonic() + 3
    while not meta.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    info = dict(l.split("=", 1) for l in meta.read_text().splitlines() if "=" in l)
    assert int(info["SID"]) != os.getsid(0), "Stub laeuft nicht in eigener Session"
    assert info["FD0"] == info["FD1"] == info["FD2"] == "/dev/null", info
