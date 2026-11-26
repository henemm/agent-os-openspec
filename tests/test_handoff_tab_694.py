"""Übergabe im eigenen Herdr-Tab, Nachfolgerin räumt auf (Issue #694, Epic #649).

Spec: docs/specs/feat-694-handoff-tab.md (AC-1 bis AC-14; AC-15 in tests/test_handoff_667.py).

Schnittstellen, gegen die diese Tests prüfen (Spec, Implementation Details):
- `workflow.py handoff --start` im Weg herdr: `tab create --workspace <W> --cwd <root>
  --label <label> --env OPENSPEC_HANDOFF_PREV_PANE=<eigenes Pane> --no-focus` (Reihenfolge der
  Optionen egal, Werte per Index hinter dem Flag), dann `pane run <root_pane> "exec claude
  <shlex-quoted prompt>"`. Rückfall: `pane split <eigen> --direction right --cwd <root>
  --no-focus --env OPENSPEC_HANDOFF_PREV_PANE=<eigen>`.
- Label `#M <Titel>` aus `.claude/issue_briefs.json`, sonst `#M`; höchstens 40 Zeichen,
  keine Steuerzeichen (< 0x20, 0x7f), Leerraum zusammengezogen (black-box über `--label`).
- `herdr_bridge.start_predecessor_cleanup()` (ohne Argumente; liest `OPENSPEC_HANDOFF_PREV_PANE`,
  `HERDR_PANE_ID`, `HERDR_ENV`, `HERDR_BIN_PATH`) startet detacht
  `herdr_bridge.py handoff-cleanup <prev>`.
- Runner `herdr_bridge.py handoff-cleanup <prev> [--timeout-ms N] [--grace S]`: `agent wait` ->
  `pane get` (idle/done) -> `pane read --source recent-unwrapped` (letzte Marke ⏳) ->
  `pane list --workspace W` -> `tab close <tab>` bzw. einzelne `pane close`. Exit 0, stumm.
- Annahme Sperre (AC-11): Datei `.claude/herdr_handoff_cleanup_<pane>.lock` im Projekt, das
  Pane bereinigt wie in `_pp_pane_lock` (`[^A-Za-z0-9_-]` -> `_`), Inhalt PID, frisch
  (Muster `_pp_take_lock`: O_EXCL + Alter). Für `pane-prev` bleibt der Name unverändert.

Kein Netz: `herdr` ist ein Fake-Binary, das jeden Aufruf als JSON-Zeile in `FAKE_HERDR_LOG`
protokolliert und per Env gesteuert wird.
"""

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_handoff_667 import (  # noqa: E402
    COMMANDS_DIR, PANE, NEW_PANE, REPO_ROOT, SKILLS_DIR, WF,
    _assert_iso, _auftrag, _auftrag_file, _calls, _env, _handoff, _kv, _of, _parse, _project,
)

WS = "w9"
PREV = "pane-prev"
PREV_TAB = "w9:t1"
NEW_TAB = "w9:t2"
OWN_TAB = "w9:t3"
PLAN = "pane-plan"
SHELL = "pane-shell"
ENV_KEY = "OPENSPEC_HANDOFF_PREV_PANE"

WAIT = "⏳ Läuft noch: Claude startet #548 aus deinem Auftrag. Du musst nichts tun."
YOU = "❗ Du: /60-validate — Tests rot"
DONE = "✅ Erledigt: #547 ausgeliefert."
ALERT = "‼️ Störung: Gate blockiert"

FAKE_HERDR = """#!{py}
import json, os, sys, time
args = sys.argv[1:]
with open(os.environ["FAKE_HERDR_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
kind = args[:2]
if kind == ["tab", "create"]:
    time.sleep(float(os.environ.get("FAKE_TAB_SLEEP", "0")))
    out = os.environ.get("FAKE_TAB_OUT") or json.dumps(
        {{"result": {{"tab": {{"tab_id": "{new_tab}"}}, "root_pane": {{"pane_id": "{new}"}}}}}})
    print(out)
    sys.exit(int(os.environ.get("FAKE_TAB_EXIT", "0")))
if kind == ["pane", "split"]:
    out = os.environ.get("FAKE_SPLIT_OUT") or json.dumps(
        {{"result": {{"pane": {{"pane_id": "{new}"}}}}}})
    print(out)
    sys.exit(int(os.environ.get("FAKE_SPLIT_EXIT", "0")))
if kind == ["pane", "run"]:
    sys.exit(int(os.environ.get("FAKE_RUN_EXIT", "0")))
if kind == ["agent", "wait"]:
    time.sleep(float(os.environ.get("FAKE_WAIT_SLEEP", "0")))
    sys.exit(int(os.environ.get("FAKE_WAIT_EXIT", "0")))
if kind == ["pane", "get"]:
    time.sleep(float(os.environ.get("FAKE_GET_SLEEP", "0")))
    pid = args[2] if len(args) > 2 else ""
    out = os.environ.get("FAKE_GET_OUT") or json.dumps({{"result": {{"pane": {{
        "pane_id": pid, "tab_id": os.environ.get("FAKE_PREV_TAB", "{prev_tab}"),
        "workspace_id": "{ws}", "agent": "claude",
        "agent_status": os.environ.get("FAKE_PREV_STATUS", "idle")}}}}}})
    print(out)
    sys.exit(int(os.environ.get("FAKE_GET_EXIT", "0")))
if kind == ["pane", "read"]:
    sys.stdout.write(os.environ.get("FAKE_SCREEN", ""))
    sys.exit(int(os.environ.get("FAKE_READ_EXIT", "0")))
if kind == ["pane", "list"]:
    print(os.environ.get("FAKE_PANES") or json.dumps({{"result": {{"panes": []}}}}))
    sys.exit(int(os.environ.get("FAKE_LIST_EXIT", "0")))
sys.exit(0)
"""


# --- Helpers ---------------------------------------------------------------

def _fake(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    exe = root / "herdr-fake-694"
    exe.write_text(FAKE_HERDR.format(py=sys.executable, new=NEW_PANE, new_tab=NEW_TAB,
                                     prev_tab=PREV_TAB, ws=WS))
    exe.chmod(0o755)
    return exe


def _hooks(proj: Path) -> Path:
    return proj / ".claude" / "hooks"


def _start_env(proj: Path, herdr: Path, **extra) -> dict:
    extra.setdefault("HERDR_WORKSPACE_ID", WS)
    return _env(proj, claude=True, herdr=herdr, **extra)


def _briefs(proj: Path, entries: dict) -> None:
    data = {str(n): {"title": t, "problem": "", "goal": "", "source": "issue"}
            for n, t in entries.items()}
    (proj / ".claude" / "issue_briefs.json").write_text(json.dumps(data))


def _opt(call: list, flag: str):
    assert flag in call, (flag, call)
    return call[call.index(flag) + 1]


def _label_of(proj: Path) -> str:
    tabs = _of(_calls(proj), "tab create")
    assert len(tabs) == 1, _calls(proj)
    return _opt(tabs[0], "--label")


def _assert_clean_label(label: str) -> None:
    assert len(label) <= 40, (len(label), label)
    assert not any(ord(c) < 0x20 or ord(c) == 0x7f for c in label), repr(label)
    assert "  " not in label and label == label.strip(), repr(label)


def _pane_entry(pid: str, tab: str, *, owner: str = "", label: str = "",
                agent: str = "") -> dict:
    entry = {"pane_id": pid, "tab_id": tab, "workspace_id": WS, "label": label,
             "tokens": {"owner": owner, "workflow": WF, "version": "4.26.5"} if owner else {}}
    if agent:
        entry["agent"] = agent
    return entry


def _panes(*entries) -> str:
    return json.dumps({"result": {"panes": list(entries)}})


def _pure_tab() -> str:
    """Vorgängerin + eigenes Plan-Pane in PREV_TAB, Nachfolgerin in OWN_TAB."""
    return _panes(_pane_entry(PREV, PREV_TAB, agent="claude"),
                  _pane_entry(PLAN, PREV_TAB, owner=PREV, label="Workflow"),
                  _pane_entry(PANE, OWN_TAB, agent="claude"))


def _runner_env(proj: Path, herdr: Path, **extra) -> dict:
    env = _env(proj, herdr=herdr, HERDR_WORKSPACE_ID=WS)
    env.setdefault("FAKE_PANES", _pure_tab())
    env.setdefault("FAKE_SCREEN", f"Fertig.\n\n{WAIT}\n")
    env.update(extra)
    return env


def _runner(proj: Path, env: dict, *extra: str, prev: str = PREV, timeout: float = 60):
    return subprocess.run(
        [sys.executable, str(_hooks(proj) / "herdr_bridge.py"), "handoff-cleanup", prev,
         "--grace", "0", *extra],
        capture_output=True, text=True, env=env, cwd=str(proj), timeout=timeout)


def _closes(proj: Path) -> list:
    calls = _calls(proj)
    return _of(calls, "tab close") + _of(calls, "pane close")


def _assert_silent_ok(res, label="") -> None:
    assert res.returncode == 0, (label, res.returncode, res.stdout, res.stderr)
    assert res.stdout == "" and res.stderr == "", (label, res.stdout, res.stderr)


def _starter(proj: Path, env: dict):
    code = ("import sys; sys.path.insert(0, %r); import herdr_bridge; "
            "herdr_bridge.start_predecessor_cleanup()" % str(_hooks(proj)))
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env=env, cwd=str(proj), timeout=30)


def _wait_for(proj: Path, kind: str, limit: float = 10.0) -> list:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        found = _of(_calls(proj), kind)
        if found:
            return found
        time.sleep(0.1)
    return _of(_calls(proj), kind)


# --- AC-1 -------------------------------------------------------------------

def test_tab_create_with_env_label_no_focus(tmp_path):
    """AC-1: tab create mit Workspace, cwd, Label, Env, --no-focus; dann pane run; kein split."""
    proj = _project(tmp_path / "p")
    _briefs(proj, {548: "Tab statt Pane"})
    herdr = _fake(tmp_path / "p")
    res = _handoff(proj, "--start", env=_start_env(proj, herdr))
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, prompt = _parse(res.stdout)
    assert _kv(lines, "HANDOFF") == "herdr", res.stdout
    assert _kv(lines, "STARTED") == "yes", (res.stdout, res.stderr)
    assert prompt, res.stdout

    calls = _calls(proj)
    tabs, runs = _of(calls, "tab create"), _of(calls, "pane run")
    assert len(tabs) == 1 and len(runs) == 1, calls
    assert _of(calls, "pane split") == [], calls
    tab = tabs[0]
    assert _opt(tab, "--workspace") == WS, tab
    assert os.path.realpath(_opt(tab, "--cwd")) == os.path.realpath(proj), tab
    assert _opt(tab, "--label") == "#548 Tab statt Pane", tab
    assert _opt(tab, "--env") == f"{ENV_KEY}={PANE}", tab
    assert "--no-focus" in tab, tab
    assert calls.index(tab) < calls.index(runs[0]), calls
    run = runs[0]
    assert run[:3] == ["pane", "run", NEW_PANE], run
    assert run[3].startswith("exec claude "), run
    assert shlex.split(run[3]) == ["exec", "claude", prompt], run

    mark = _auftrag(proj).get("handoff")
    assert isinstance(mark, dict), _auftrag(proj)
    assert mark.get("issue") == 548 and mark.get("mode") == "herdr", mark
    _assert_iso(mark.get("at"))


# --- AC-2 -------------------------------------------------------------------

def test_tab_label_cache_fallback_truncate_sanitize(tmp_path):
    """AC-2: Label `#M Titel` bzw. `#M`, höchstens 40 Zeichen, keine Steuerzeichen."""
    long_title = "Sehr langer Titel für die Übergabe an eine frische Sitzung im Tab"
    cases = {
        "cached": {548: "Kurzer Titel"},
        "missing": {549: "Anderes Issue"},
        "long": {548: long_title},
        "control": {548: "Zeile\neins\tzwei\x1bdrei\x7fvier"},
    }
    labels = {}
    for name, entries in cases.items():
        proj = _project(tmp_path / name)
        _briefs(proj, entries)
        herdr = _fake(tmp_path / name)
        res = _handoff(proj, "--start", env=_start_env(proj, herdr))
        assert res.returncode == 0, (name, res.stdout, res.stderr)
        labels[name] = _label_of(proj)
        _assert_clean_label(labels[name])

    assert labels["cached"] == "#548 Kurzer Titel", labels
    assert labels["missing"] == "#548", labels
    assert labels["long"].startswith("#548 Sehr langer Titel"), labels
    assert ("#548 " + long_title).startswith(labels["long"].rstrip()), labels
    assert len(labels["long"]) >= 35, labels  # gekappt, nicht verworfen
    ctl = labels["control"]
    assert ctl.startswith("#548 Zeile"), repr(ctl)
    for word in ("eins", "zwei", "drei", "vier"):
        assert word in ctl, repr(ctl)


# --- AC-3 -------------------------------------------------------------------

def test_tab_failure_falls_back_to_split_with_env(tmp_path):
    """AC-3: tab create scheitert (Exit, kein JSON, ohne pane_id, eigenes Pane, Zeitlimit)
    oder kein Workspace -> pane split mit --env, dann pane run, STARTED=yes."""
    cases = {
        "exit": dict(FAKE_TAB_EXIT="1"),
        "garbage": dict(FAKE_TAB_OUT="kein json"),
        "no_pane_id": dict(FAKE_TAB_OUT=json.dumps({"result": {"tab": {"tab_id": NEW_TAB}}})),
        "own_pane": dict(FAKE_TAB_OUT=json.dumps(
            {"result": {"tab": {"tab_id": NEW_TAB}, "root_pane": {"pane_id": PANE}}})),
        "hang": dict(FAKE_TAB_SLEEP="20"),
        "no_workspace": dict(HERDR_WORKSPACE_ID=""),
    }
    for name, extra in cases.items():
        proj = _project(tmp_path / name)
        herdr = _fake(tmp_path / name)
        env = _start_env(proj, herdr, **extra)
        if name == "no_workspace":
            env.pop("HERDR_WORKSPACE_ID", None)
        res = _handoff(proj, "--start", env=env)
        assert res.returncode == 0, (name, res.stdout, res.stderr)
        lines, _ = _parse(res.stdout)
        assert _kv(lines, "STARTED") == "yes", (name, res.stdout, res.stderr)

        calls = _calls(proj)
        if name == "no_workspace":
            assert _of(calls, "tab create") == [], (name, calls)
        else:
            assert len(_of(calls, "tab create")) == 1, (name, calls)
        splits, runs = _of(calls, "pane split"), _of(calls, "pane run")
        assert len(splits) == 1, (name, calls)
        split = splits[0]
        assert split[:3] == ["pane", "split", PANE], (name, split)
        assert _opt(split, "--direction") == "right", (name, split)
        assert os.path.realpath(_opt(split, "--cwd")) == os.path.realpath(proj), (name, split)
        assert "--no-focus" in split, (name, split)
        assert _opt(split, "--env") == f"{ENV_KEY}={PANE}", (name, split)
        assert runs and runs[-1][:3] == ["pane", "run", NEW_PANE], (name, calls)
        assert calls.index(split) < calls.index(runs[-1]), (name, calls)
        assert all(r[2] != PANE for r in runs), (name, calls)


# --- AC-4 -------------------------------------------------------------------

def test_pane_run_failure_closes_new_tab(tmp_path):
    """AC-4: pane run im neuen Tab scheitert -> tab close <neu>, STARTED=no, kein Vermerk."""
    proj = _project(tmp_path / "p")
    herdr = _fake(tmp_path / "p")
    before = _auftrag_file(proj).read_bytes()
    res = _handoff(proj, "--start", env=_start_env(proj, herdr, FAKE_RUN_EXIT="1"))
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, _ = _parse(res.stdout)
    assert _kv(lines, "STARTED") == "no", (res.stdout, res.stderr)
    reason = _kv(lines, "REASON")
    assert reason and reason.strip(), res.stdout

    calls = _calls(proj)
    assert len(_of(calls, "tab create")) == 1, calls
    closes = _of(calls, "tab close")
    assert closes == [["tab", "close", NEW_TAB]], calls
    assert calls.index(_of(calls, "pane run")[0]) < calls.index(closes[0]), calls
    assert _of(calls, "pane split") == [], calls
    assert _auftrag_file(proj).read_bytes() == before, "kein handoff-Vermerk"
    assert "handoff" not in _auftrag(proj)


# --- AC-5 -------------------------------------------------------------------

def test_never_targets_own_pane(tmp_path):
    """AC-5: neues Pane = eigenes Pane -> weder pane run noch tab close auf das eigene Pane."""
    own = json.dumps({"result": {"tab": {"tab_id": OWN_TAB}, "root_pane": {"pane_id": PANE}}})
    split_own = json.dumps({"result": {"pane": {"pane_id": PANE}}})
    for name, extra in (("tab_own", dict(FAKE_TAB_OUT=own)),
                        ("both_own", dict(FAKE_TAB_OUT=own, FAKE_SPLIT_OUT=split_own))):
        proj = _project(tmp_path / name)
        herdr = _fake(tmp_path / name)
        res = _handoff(proj, "--start", env=_start_env(proj, herdr, **extra))
        assert res.returncode == 0, (name, res.stdout, res.stderr)
        calls = _calls(proj)
        assert len(_of(calls, "tab create")) == 1, (name, calls)
        assert all(c[2] != PANE for c in _of(calls, "pane run")), (name, calls)
        assert all(c[2] not in (PANE, OWN_TAB) for c in _of(calls, "tab close")), (name, calls)
        lines, _ = _parse(res.stdout)
        if name == "both_own":
            assert _kv(lines, "STARTED") == "no", (name, res.stdout)
            assert _of(calls, "pane run") == [], (name, calls)
        else:
            assert _kv(lines, "STARTED") == "yes", (name, res.stdout)
            assert _of(calls, "pane split"), (name, calls)


# --- AC-6 -------------------------------------------------------------------

def test_cleanup_starter_only_with_foreign_prev_env(tmp_path):
    """AC-6: Env fehlt/leer/eigenes Pane -> kein Runner, stumm; fremd -> genau ein Runner."""
    negatives = {"unset": None, "empty": "", "own": PANE}
    projs = {}
    for name, value in negatives.items():
        proj = _project(tmp_path / name)
        herdr = _fake(tmp_path / name)
        env = _runner_env(proj, herdr, FAKE_WAIT_EXIT="1")
        if value is not None:
            env[ENV_KEY] = value
        res = _starter(proj, env)
        _assert_silent_ok(res, name)
        projs[name] = proj
    time.sleep(2.0)
    for name, proj in projs.items():
        assert _calls(proj) == [], (name, _calls(proj))

    proj = _project(tmp_path / "foreign")
    herdr = _fake(tmp_path / "foreign")
    env = _runner_env(proj, herdr, FAKE_WAIT_EXIT="1", **{ENV_KEY: PREV})
    res = _starter(proj, env)
    _assert_silent_ok(res, "foreign")
    waits = _wait_for(proj, "agent wait")
    assert len(waits) == 1, _calls(proj)
    assert waits[0][2] == PREV, waits
    time.sleep(1.0)
    assert len(_of(_calls(proj), "agent wait")) == 1, _calls(proj)
    assert _closes(proj) == [], _calls(proj)


# --- AC-7 -------------------------------------------------------------------

def test_cleanup_closes_whole_tab_after_waiting_marker(tmp_path):
    """AC-7: idle/done bestätigt, letzte Marke ⏳, Tab nur Vorgängerin + Plan-Pane -> tab close."""
    for status in ("idle", "done"):
        proj = _project(tmp_path / status)
        herdr = _fake(tmp_path / status)
        res = _runner(proj, _runner_env(proj, herdr, FAKE_PREV_STATUS=status))
        _assert_silent_ok(res, status)
        calls = _calls(proj)
        wait = _of(calls, "agent wait")
        assert len(wait) == 1 and wait[0][2] == PREV, (status, calls)
        assert "idle" in wait[0] and "done" in wait[0] and "--timeout" in wait[0], wait
        assert [c[2] for c in _of(calls, "pane get")][:1] == [PREV], (status, calls)
        reads = _of(calls, "pane read")
        assert reads and reads[0][2] == PREV, (status, calls)
        assert _opt(reads[0], "--source") == "recent-unwrapped", reads
        lists = _of(calls, "pane list")
        assert lists and _opt(lists[0], "--workspace") == WS, (status, calls)
        assert _of(calls, "tab close") == [["tab", "close", PREV_TAB]], (status, calls)
        assert _of(calls, "pane close") == [], (status, calls)


# --- AC-8 -------------------------------------------------------------------

def test_cleanup_closes_only_own_panes_in_shared_tab(tmp_path):
    """AC-8: Tab mit fremdem Pane oder der Nachfolgerin -> kein tab close, nur Vorgängerin
    und ihre Plan-Panes einzeln per pane close."""
    cases = {
        "shell": _panes(_pane_entry(PREV, PREV_TAB, agent="claude"),
                        _pane_entry(PLAN, PREV_TAB, owner=PREV, label="Workflow"),
                        _pane_entry(SHELL, PREV_TAB),
                        _pane_entry("pane-otherplan", PREV_TAB, owner="pane-x",
                                    label="Workflow"),
                        _pane_entry(PANE, OWN_TAB, agent="claude")),
        "successor": _panes(_pane_entry(PREV, PREV_TAB, agent="claude"),
                            _pane_entry(PLAN, PREV_TAB, owner=PREV, label="Workflow"),
                            _pane_entry(PANE, PREV_TAB, agent="claude")),
    }
    for name, panes in cases.items():
        proj = _project(tmp_path / name)
        herdr = _fake(tmp_path / name)
        res = _runner(proj, _runner_env(proj, herdr, FAKE_PANES=panes))
        _assert_silent_ok(res, name)
        calls = _calls(proj)
        assert _of(calls, "tab close") == [], (name, calls)
        closed = sorted(c[2] for c in _of(calls, "pane close"))
        assert closed == sorted([PREV, PLAN]), (name, calls)


# --- AC-9 -------------------------------------------------------------------

def test_cleanup_marker_matrix_last_wins(tmp_path):
    """AC-9: Schließen nur, wenn die zuletzt vorkommende Endzustandsmarke ⏳ ist."""
    cases = {
        "you": (dict(FAKE_SCREEN=f"x\n{YOU}\n"), False),
        "done": (dict(FAKE_SCREEN=f"x\n{DONE}\n"), False),
        "alert": (dict(FAKE_SCREEN=f"x\n{ALERT}\n"), False),
        "none": (dict(FAKE_SCREEN="Fertig, keine Marke.\n"), False),
        "unreadable": (dict(FAKE_SCREEN=WAIT, FAKE_READ_EXIT="1"), False),
        "you_then_wait": (dict(FAKE_SCREEN=f"{YOU}\nweiter\n{WAIT}\n"), True),
        "wait_then_you": (dict(FAKE_SCREEN=f"{WAIT}\nweiter\n{YOU}\n"), False),
        "wait_then_alert": (dict(FAKE_SCREEN=f"{WAIT}\n{ALERT}\n"), False),
        "done_then_wait": (dict(FAKE_SCREEN=f"{DONE}\n{WAIT}\nNachlauf"), True),
    }
    for name, (extra, closes) in cases.items():
        proj = _project(tmp_path / name)
        herdr = _fake(tmp_path / name)
        res = _runner(proj, _runner_env(proj, herdr, **extra))
        _assert_silent_ok(res, name)
        calls = _calls(proj)
        assert _of(calls, "pane read"), (name, "Runner hat den Bildschirm nicht gelesen", calls)
        if closes:
            assert _of(calls, "tab close") == [["tab", "close", PREV_TAB]], (name, calls)
        else:
            assert _closes(proj) == [], (name, calls)


# --- AC-10 ------------------------------------------------------------------

def test_cleanup_no_close_when_not_idle_or_timeout_or_resumed(tmp_path):
    """AC-10: blocked, Frist abgelaufen (verkürzt) oder nach Nachprüfung working -> nichts."""
    cases = {
        "timeout": (dict(FAKE_WAIT_EXIT="1"), ("--timeout-ms", "200")),
        "blocked_wait": (dict(FAKE_WAIT_EXIT="1", FAKE_PREV_STATUS="blocked"), ()),
        "blocked_get": (dict(FAKE_PREV_STATUS="blocked"), ()),
        "resumed": (dict(FAKE_PREV_STATUS="working"), ()),
        "unknown": (dict(FAKE_PREV_STATUS="unknown"), ()),
    }
    for name, (extra, args) in cases.items():
        proj = _project(tmp_path / name)
        herdr = _fake(tmp_path / name)
        res = _runner(proj, _runner_env(proj, herdr, **extra), *args)
        _assert_silent_ok(res, name)
        calls = _calls(proj)
        waits = _of(calls, "agent wait")
        assert len(waits) == 1 and waits[0][2] == PREV, (name, calls)
        if name == "timeout":
            assert _opt(waits[0], "--timeout") == "200", waits
        if name in ("blocked_get", "resumed", "unknown"):
            assert _of(calls, "pane get"), (name, "Nachprüfung fehlt", calls)
        assert _closes(proj) == [], (name, calls)

    # Default-Frist 30 Minuten
    proj = _project(tmp_path / "default")
    herdr = _fake(tmp_path / "default")
    res = _runner(proj, _runner_env(proj, herdr, FAKE_WAIT_EXIT="1"))
    _assert_silent_ok(res, "default")
    waits = _of(_calls(proj), "agent wait")
    assert waits and _opt(waits[0], "--timeout") == "1800000", _calls(proj)


# --- AC-11 ------------------------------------------------------------------

def _lock_file(proj: Path, pane: str) -> Path:
    return proj / ".claude" / f"herdr_handoff_cleanup_{pane}.lock"


def test_cleanup_lock_per_predecessor_pane(tmp_path):
    """AC-11: frische Sperre für dasselbe Vorgänger-Pane -> kein Herdr-Aufruf; Sperre für ein
    anderes Pane -> Runner läuft normal. Annahme: `.claude/herdr_handoff_cleanup_<pane>.lock`."""
    proj = _project(tmp_path / "same")
    herdr = _fake(tmp_path / "same")
    _lock_file(proj, PREV).write_text(str(os.getpid()))
    res = _runner(proj, _runner_env(proj, herdr))
    _assert_silent_ok(res, "same")
    assert _calls(proj) == [], _calls(proj)
    assert _lock_file(proj, PREV).exists(), "fremde Sperre darf nicht entfernt werden"

    proj = _project(tmp_path / "other")
    herdr = _fake(tmp_path / "other")
    _lock_file(proj, "pane-other").write_text(str(os.getpid()))
    res = _runner(proj, _runner_env(proj, herdr))
    _assert_silent_ok(res, "other")
    calls = _calls(proj)
    assert _of(calls, "agent wait"), calls
    assert _of(calls, "tab close") == [["tab", "close", PREV_TAB]], calls


# --- AC-12 ------------------------------------------------------------------

def test_cleanup_fail_open_silent(tmp_path):
    """AC-12: kaputtes Herdr (fehlt, Exit != 0, Müll-JSON, Zeitlimit) -> Starter und Runner
    Exit 0, stumm, nichts geschlossen."""
    proj = _project(tmp_path / "starter_nobin")
    herdr = _fake(tmp_path / "starter_nobin")
    env = _runner_env(proj, herdr, HERDR_BIN_PATH="/nonexistent/herdr-694", **{ENV_KEY: PREV})
    _assert_silent_ok(_starter(proj, env), "starter_nobin")

    cases = {
        "nobin": (dict(HERDR_BIN_PATH="/nonexistent/herdr-694"), (), False),
        "wait_exit": (dict(FAKE_WAIT_EXIT="2"), (), True),
        "get_exit": (dict(FAKE_GET_EXIT="1"), (), True),
        "get_garbage": (dict(FAKE_GET_OUT="kein json"), (), True),
        "list_garbage": (dict(FAKE_PANES="müll"), (), True),
        "list_exit": (dict(FAKE_LIST_EXIT="1"), (), True),
        "hang": (dict(FAKE_WAIT_SLEEP="8"), ("--timeout-ms", "300"), True),
    }
    for name, (extra, args, reached) in cases.items():
        proj = _project(tmp_path / name)
        herdr = _fake(tmp_path / name)
        res = _runner(proj, _runner_env(proj, herdr, **extra), *args, timeout=40)
        _assert_silent_ok(res, name)
        if reached:
            assert _of(_calls(proj), "agent wait"), (name, _calls(proj))
        assert _closes(proj) == [], (name, _calls(proj))
    # der Starter-Fall ohne Binary hat nie etwas aufgerufen
    assert _calls(tmp_path / "starter_nobin" / "proj") == []


# --- AC-13 ------------------------------------------------------------------

def test_prompt_has_predecessor_result_sentence(tmp_path):
    """AC-13: Startauftrag nennt den Ein-Satz-Bericht zu #547 plus alle #667-Bausteine."""
    proj = _project(tmp_path / "p")
    res = _handoff(proj, env=_env(proj, remote=True))
    assert res.returncode == 0, (res.stdout, res.stderr)
    _, prompt = _parse(res.stdout)
    assert prompt, res.stdout
    lines = [l for l in prompt.splitlines() if "ersten Meldung" in l]
    assert len(lines) == 1, prompt
    sentence = lines[0]
    assert "#547" in sentence and "Abschlusskommentar" in sentence, sentence
    assert "einem Satz" in sentence, sentence
    for needle in ("#548", "00-intake", "queue add", "--autark", "PO-Punkten",
                   "AskUserQuestion", "frisch", "#667", "CONTEXT_TOKENS", "workflow.py context"):
        assert needle in prompt, (needle, prompt)


# --- AC-14 ------------------------------------------------------------------

def _herdr_bullet(text: str) -> str:
    start = text.find("- `herdr`:")
    assert start >= 0, "Abschnitt zum Weg herdr fehlt"
    end = text.find("- `inline`", start)
    return text[start:end if end > 0 else start + 600]


def test_command_texts_say_tab_and_skills_in_sync():
    """AC-14: 80-workflow/60-validate (+ Skills) sprechen von „neuem Tab“, nicht „neuem Pane“;
    sync_skills.py --check und sync_cloud_agents.py --check ohne Drift."""
    for name in ("80-workflow", "60-validate"):
        for path in (COMMANDS_DIR / f"{name}.md", SKILLS_DIR / name / "SKILL.md"):
            text = path.read_text(encoding="utf-8")
            for bad in ("neuen Pane", "neuem Pane", "neuer Pane"):
                assert bad not in text, (str(path), bad)
            if name == "80-workflow":
                line = next((l for l in text.splitlines() if "handoff --start" in l), "")
                assert "Tab" in line, (str(path), line)
            else:
                assert "Tab" in _herdr_bullet(text), (str(path), _herdr_bullet(text))

    for script in ("sync_skills.py", "sync_cloud_agents.py"):
        res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script), "--check"],
                             capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60)
        assert res.returncode == 0, (script, res.stdout, res.stderr)
