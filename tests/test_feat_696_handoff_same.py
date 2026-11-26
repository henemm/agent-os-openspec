"""Frische Sitzung am Phasenwechsel innerhalb eines Issues (Issue #696, Epic #649).

Spec: docs/specs/feat-696-handoff-phasenwechsel.md (AC-1 bis AC-16).

Vertraege aus der Spec (Implementation Details), gegen die diese Tests pruefen:
- `workflow.py context` gibt vor der weiterhin letzten Zeile `CONTEXT_STOP=` die Zeile
  `CONTEXT_HANDOFF=on|off` aus; `on` nur bei Budget an, Messung der EIGENEN Sitzung >=
  wirksamer Schwelle, Autonomie `auto`, nicht Cloud, Herdr-Pane und `claude` im PATH.
- `workflow.py handoff --same [--start]`: `HANDOFF=herdr|none`, `NEXT=<Folgebefehl inkl. #N>|none`,
  bei `--start` `STARTED=yes|no|already` (+ `REASON=` bei no) und der Startauftrag zwischen
  `PROMPT_BEGIN`/`PROMPT_END`. cwd der neuen Sitzung ist `git rev-parse --show-toplevel`.
  Vermerk `handoff_same = {phase, next, at}` und `waiting_on` im Workflow-State nach Erfolg.
  `--same --mark` ist ein Usage-Fehler (Exit 1).

Kein Netz: `herdr` ist das Fake-Binary aus tests/test_handoff_tab_694.py, das jeden Aufruf
protokolliert. workflow.py laeuft als Subprozess aus einer Hook-Kopie im tmp-Projekt.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_handoff_667 import (  # noqa: E402
    COMMANDS_DIR, HOOKS_DIR, NEW_PANE, PANE, REPO_ROOT, SKILLS_DIR, WF,
    _assert_iso, _auftrag_file, _calls, _env, _git, _handoff, _kv, _of, _parse, _project,
    _queue_add_tokens,
)
from test_handoff_tab_694 import ENV_KEY, WS, _briefs, _fake, _opt  # noqa: E402

BUDGET = "context_budget:\n  enabled: true\n  clear_threshold_tokens: 100000\n"
BUDGET_OFF = "context_budget:\n  enabled: false\n  clear_threshold_tokens: 100000\n"
OVER = 150_000
UNDER = 50_000
BASELINE = 20_000
SID = "sid-696"
NEXT = "/50-implement #547"
STATE_RED_DONE = {"current_phase": "phase5_tdd_red", "red_test_done": True}
HANDOFF_NOTE_696 = "Diese Sitzung setzt den Workflow mit frischem Kontext fort (#696)"


# --- Helpers ---------------------------------------------------------------

def _state_file(proj: Path) -> Path:
    return proj / ".claude" / "workflows" / f"{WF}.json"


def _state(proj: Path) -> dict:
    return json.loads(_state_file(proj).read_text())


def _set_state(proj: Path, **fields) -> None:
    data = _state(proj)
    data.update(fields)
    _state_file(proj).write_text(json.dumps(data))


def _wf_project(root: Path, *, auftrag: bool = False, config: "str | None" = None,
                **state) -> Path:
    """tmp-Projekt mit aktivem Workflow #547; Default: RED fertig -> Folgebefehl /50-implement."""
    proj = _project(root, auftrag=auftrag, config=config, phase="phase5_tdd_red")
    _set_state(proj, **(state or STATE_RED_DONE))
    return proj


def _ctx_env(proj: Path, *, session: "str | None" = SID, **kw) -> dict:
    env = _env(proj, **kw)
    env.pop("CLAUDE_CONFIG_DIR", None)
    if session is not None:
        env["CLAUDE_CODE_SESSION_ID"] = session
    return env


def _write_usage(proj: Path, tokens: int, session: str = SID) -> Path:
    path = proj / ".claude" / "context_usage" / f"{session}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"session_id": session, "tokens": tokens,
                                "baseline_tokens": BASELINE,
                                "at": "2026-11-26T10:00:00", "announced_bucket": 0}))
    return path


def _context(proj: Path, env: dict, cwd: "Path | None" = None):
    return subprocess.run([sys.executable, str(proj / ".claude" / "hooks" / "workflow.py"),
                           "context"], cwd=str(cwd or proj), env=env, capture_output=True,
                          text=True, timeout=60)


def _ctx_lines(proj: Path, env: dict) -> "list[str]":
    res = _context(proj, env)
    assert res.returncode == 0, (res.stdout, res.stderr)
    assert "Traceback" not in res.stderr, res.stderr
    return [l for l in res.stdout.splitlines() if l.strip()]


def _full_env(proj: Path, herdr: Path, **extra) -> dict:
    """Alle Voraussetzungen fuer den Weg herdr: auto, nicht Cloud, Pane, claude, Workspace."""
    extra.setdefault("HERDR_WORKSPACE_ID", WS)
    return _ctx_env(proj, claude=True, herdr=herdr, **extra)


def _same(proj: Path, *args: str, env: dict, cwd: "Path | None" = None):
    return subprocess.run(
        [sys.executable, str(proj / ".claude" / "hooks" / "workflow.py"), "handoff", "--same",
         *args], capture_output=True, text=True, env=env, cwd=str(cwd or proj), timeout=60)


def _no_start(proj: Path, label="") -> None:
    calls = _calls(proj)
    for kind in ("tab create", "pane split", "pane run"):
        assert _of(calls, kind) == [], (label, kind, calls)


# --- AC-1 -------------------------------------------------------------------

def test_context_handoff_on_when_all_conditions_hold(tmp_path):
    """AC-1: alle Bedingungen erfuellt -> CONTEXT_HANDOFF=on direkt vor CONTEXT_STOP=."""
    proj = _wf_project(tmp_path / "p", config=BUDGET)
    herdr = _fake(tmp_path / "p")
    _write_usage(proj, OVER)
    lines = _ctx_lines(proj, _full_env(proj, herdr))
    assert lines[-1].startswith("CONTEXT_STOP="), lines
    assert "CONTEXT_HANDOFF=on" in lines, lines
    assert lines[-2] == "CONTEXT_HANDOFF=on", lines
    # bisherige Zeilen unveraendert (Auto-Modus, Schnitt an, kein Halt)
    rest = [l for l in lines if not l.startswith("CONTEXT_HANDOFF=")]
    assert [l.split("=", 1)[0] for l in rest] == [
        "CONTEXT_TOKENS", "CONTEXT_CUT", "CONTEXT_THRESHOLD", "CONTEXT_REASON",
        "CONTEXT_STOP"], rest
    assert _kv(rest, "CONTEXT_TOKENS") == str(OVER), rest
    assert _kv(rest, "CONTEXT_CUT") == "on", rest
    assert re.fullmatch(r"\d+", _kv(rest, "CONTEXT_THRESHOLD") or ""), rest
    assert int(_kv(rest, "CONTEXT_THRESHOLD")) <= OVER, rest
    assert _kv(rest, "CONTEXT_REASON") == "AUTO_NO_CLEAR", rest
    assert _kv(rest, "CONTEXT_STOP") == "off", rest
    assert sum(1 for l in lines if l.startswith("CONTEXT_HANDOFF=")) == 1, lines


# --- AC-2 -------------------------------------------------------------------

def test_context_handoff_off_matrix(tmp_path):
    """AC-2: je eine Abweichung -> CONTEXT_HANDOFF=off, Exit 0, CONTEXT_STOP= bleibt letzte Zeile."""
    cases = ("under", "budget_off", "manual", "remote", "no_pane", "no_claude", "measure_error")
    for name in cases:
        proj = _wf_project(tmp_path / name, config=BUDGET_OFF if name == "budget_off" else BUDGET)
        herdr = _fake(tmp_path / name)
        if name == "measure_error":
            path = _write_usage(proj, OVER)
            path.write_text("{kaputt")
        else:
            _write_usage(proj, UNDER if name == "under" else OVER)
        kw = dict(claude=name != "no_claude", herdr=None if name == "no_pane" else herdr,
                  autonomy="manual" if name == "manual" else "auto", remote=name == "remote")
        env = _ctx_env(proj, HERDR_WORKSPACE_ID=WS, **kw)
        res = _context(proj, env)
        assert res.returncode == 0, (name, res.stdout, res.stderr)
        assert "Traceback" not in res.stderr, (name, res.stderr)
        lines = [l for l in res.stdout.splitlines() if l.strip()]
        assert lines and lines[-1].startswith("CONTEXT_STOP="), (name, lines)
        assert _kv(lines, "CONTEXT_HANDOFF") == "off", (name, lines)
        assert lines[-2] == "CONTEXT_HANDOFF=off", (name, lines)


# --- AC-3 -------------------------------------------------------------------

def test_context_handoff_off_for_foreign_measurement(tmp_path):
    """AC-3: nur die Messdatei einer fremden Sitzung ueber der Schwelle -> CONTEXT_HANDOFF=off."""
    proj = _wf_project(tmp_path / "p", config=BUDGET)
    herdr = _fake(tmp_path / "p")
    _write_usage(proj, OVER, session="fremde-sitzung")
    lines = _ctx_lines(proj, _full_env(proj, herdr))
    # Rueckfall auf die juengste Messdatei greift fuer CONTEXT_TOKENS/CUT weiterhin
    assert _kv(lines, "CONTEXT_TOKENS") == str(OVER), lines
    assert _kv(lines, "CONTEXT_CUT") == "on", lines
    assert _kv(lines, "CONTEXT_HANDOFF") == "off", lines
    assert lines[-1].startswith("CONTEXT_STOP="), lines

    # Gegenprobe: dieselbe Lage mit eigener Messdatei -> on
    _write_usage(proj, OVER)
    assert _kv(_ctx_lines(proj, _full_env(proj, herdr)), "CONTEXT_HANDOFF") == "on"


# --- AC-4 -------------------------------------------------------------------

def test_context_handoff_on_with_autark_auftrag_keeps_cut_off(tmp_path):
    """AC-4: offener autarker Auftrag -> HANDOFF=on, CUT=off und REASON=AUTARK unveraendert."""
    proj = _wf_project(tmp_path / "p", config=BUDGET, auftrag=True)
    herdr = _fake(tmp_path / "p")
    _write_usage(proj, OVER)
    lines = _ctx_lines(proj, _ctx_env(proj, claude=True, herdr=herdr))
    assert _kv(lines, "CONTEXT_CUT") == "off", lines
    assert _kv(lines, "CONTEXT_REASON") == "AUTARK", lines
    assert _kv(lines, "CONTEXT_THRESHOLD") is None, lines
    assert _kv(lines, "CONTEXT_HANDOFF") == "on", lines
    assert lines[-2] == "CONTEXT_HANDOFF=on" and lines[-1].startswith("CONTEXT_STOP="), lines


# --- AC-5 -------------------------------------------------------------------

def test_same_without_start_only_reports(tmp_path):
    """AC-5: `handoff --same` ohne --start -> HANDOFF=herdr, NEXT, kein Herdr-Aufruf, kein Vermerk."""
    proj = _wf_project(tmp_path / "p")
    herdr = _fake(tmp_path / "p")
    before = _state_file(proj).read_bytes()
    res = _same(proj, env=_full_env(proj, herdr))
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, _ = _parse(res.stdout)
    assert _kv(lines, "HANDOFF") == "herdr", res.stdout
    assert _kv(lines, "NEXT") == NEXT, res.stdout
    assert _kv(lines, "STARTED") is None, res.stdout
    assert _calls(proj) == [], _calls(proj)
    assert "handoff_same" not in _state(proj), _state(proj)
    assert _state_file(proj).read_bytes() == before


# --- AC-6 -------------------------------------------------------------------

PLAIN_NONE = ["HANDOFF=none", "NEXT=none"]
PLAIN_NONE_START = PLAIN_NONE + ["STARTED=no", "REASON=Weg none"]


def test_same_none_matrix_and_plain_handoff_unchanged(tmp_path):
    """AC-6: Freitext-Folgebefehl, kein Workflow, manual, Cloud, kein Pane, kein claude
    -> `--same --start` meldet HANDOFF=none ohne Start; `handoff` ohne --same wie bisher."""
    cases = ("approval", "no_workflow", "manual", "remote", "no_pane", "no_claude")
    for name in cases:
        if name == "approval":
            proj = _wf_project(tmp_path / name, current_phase="phase3_spec",
                               spec_file="docs/specs/feat-547-x.md")
        else:
            proj = _wf_project(tmp_path / name)
        if name == "no_workflow":
            (proj / ".claude" / "active_workflow").unlink()
        herdr = _fake(tmp_path / name)
        kw = dict(claude=name != "no_claude", herdr=None if name == "no_pane" else herdr,
                  autonomy="manual" if name == "manual" else "auto", remote=name == "remote")
        env = _ctx_env(proj, HERDR_WORKSPACE_ID=WS, **kw)
        before = _state_file(proj).read_bytes()

        res = _same(proj, "--start", env=env)
        assert res.returncode == 0, (name, res.stdout, res.stderr)
        lines, _ = _parse(res.stdout)
        assert _kv(lines, "HANDOFF") == "none", (name, res.stdout, res.stderr)
        assert _kv(lines, "STARTED") in ("no", None), (name, res.stdout)
        _no_start(proj, name)
        assert _state_file(proj).read_bytes() == before, (name, "kein Vermerk ohne Start")

        # Ohne --same: Verhalten wie vor der Aenderung (kein Auftrag -> none)
        plain = _handoff(proj, env=env)
        assert plain.returncode == 0, (name, plain.stdout, plain.stderr)
        assert [l for l in plain.stdout.splitlines() if l.strip()] == PLAIN_NONE, (
            name, plain.stdout)
        plain = _handoff(proj, "--start", env=env)
        assert plain.returncode == 0, (name, plain.stdout, plain.stderr)
        assert [l for l in plain.stdout.splitlines() if l.strip()] == PLAIN_NONE_START, (
            name, plain.stdout)
        _no_start(proj, name)


# --- AC-7 -------------------------------------------------------------------

def test_same_with_mark_is_usage_error(tmp_path):
    """AC-7: `--same --mark` -> Exit 1, Usage, kein Start, keine Zustandsaenderung;
    Gegenprobe: `--same` allein ist gueltig."""
    proj = _wf_project(tmp_path / "p", auftrag=True)
    herdr = _fake(tmp_path / "p")
    env = _full_env(proj, herdr)
    ok = _same(proj, env=env)
    assert ok.returncode == 0, ("`--same` allein muss gueltig sein", ok.stdout, ok.stderr)

    state_before = _state_file(proj).read_bytes()
    auftrag_before = _auftrag_file(proj).read_bytes()
    for args in (("--mark", "herdr"), ("--start", "--mark", "herdr"), ("--mark", "cloud")):
        res = _same(proj, *args, env=env)
        assert res.returncode == 1, (args, res.stdout, res.stderr)
        assert "usage" in res.stderr.lower(), (args, res.stderr)
        assert "STARTED=" not in res.stdout and "MARKED=" not in res.stdout, (args, res.stdout)
    _no_start(proj)
    assert _state_file(proj).read_bytes() == state_before
    assert _auftrag_file(proj).read_bytes() == auftrag_before


# --- AC-8 -------------------------------------------------------------------

def _git_commit(repo: Path) -> None:
    _git(repo, "-c", "user.email=t@example.invalid", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "init")


def test_start_uses_worktree_toplevel_as_cwd(tmp_path):
    """AC-8: Start im Git-Worktree -> `tab create --cwd` ist die Worktree-Wurzel, nicht das Hauptrepo."""
    main = _wf_project(tmp_path / "m")
    _git_commit(main)
    wt = tmp_path / "wt-696"
    _git(main, "worktree", "add", "-q", str(wt))
    (wt / ".claude").mkdir(exist_ok=True)
    (wt / ".claude" / "active_workflow").write_text(WF)
    herdr = _fake(tmp_path / "m")
    env = _full_env(main, herdr)
    env.pop("CLAUDE_PROJECT_DIR", None)

    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(wt),
                         capture_output=True, text=True, check=True).stdout.strip()
    assert os.path.realpath(top) == os.path.realpath(wt)
    assert os.path.realpath(top) != os.path.realpath(main)

    res = _same(main, "--start", env=env, cwd=wt)
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, _ = _parse(res.stdout)
    assert _kv(lines, "HANDOFF") == "herdr", (res.stdout, res.stderr)
    assert _kv(lines, "STARTED") == "yes", (res.stdout, res.stderr)
    tabs = _of(_calls(main), "tab create")
    assert len(tabs) == 1, _calls(main)
    assert os.path.realpath(_opt(tabs[0], "--cwd")) == os.path.realpath(top), tabs[0]
    assert os.path.realpath(_opt(tabs[0], "--cwd")) != os.path.realpath(main), tabs[0]


# --- AC-9 -------------------------------------------------------------------

def test_toplevel_failure_means_no_start(tmp_path):
    """AC-9: cwd ausserhalb jedes Git-Repos -> STARTED=no mit REASON, Exit 0, kein Herdr, kein Vermerk."""
    proj = _wf_project(tmp_path / "p")
    herdr = _fake(tmp_path / "p")
    nogit = tmp_path / "nogit"
    nogit.mkdir()
    env = _full_env(proj, herdr, GIT_CEILING_DIRECTORIES=str(tmp_path))
    probe = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(nogit), env=env,
                           capture_output=True, text=True)
    assert probe.returncode != 0, probe.stdout
    before = _state_file(proj).read_bytes()

    res = _same(proj, "--start", env=env, cwd=nogit)
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, _ = _parse(res.stdout)
    assert _kv(lines, "HANDOFF") == "herdr", (res.stdout, res.stderr)
    assert _kv(lines, "STARTED") == "no", (res.stdout, res.stderr)
    reason = _kv(lines, "REASON") or ""
    assert re.search(r"worktree|wurzel|toplevel|rev-parse", reason, re.I), res.stdout
    assert _calls(proj) == [], _calls(proj)
    assert _state_file(proj).read_bytes() == before
    assert "handoff_same" not in _state(proj)


# --- AC-10 ------------------------------------------------------------------

def test_start_goes_through_start_session_in_tab(tmp_path):
    """AC-10: tab create mit Label `#547 Titel` und Env Vorgaenger-Pane, dann pane run exec claude."""
    proj = _wf_project(tmp_path / "p")
    _briefs(proj, {547: "Phasenwechsel frisch"})
    herdr = _fake(tmp_path / "p")
    res = _same(proj, "--start", env=_full_env(proj, herdr))
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, prompt = _parse(res.stdout)
    assert _kv(lines, "HANDOFF") == "herdr", res.stdout
    assert _kv(lines, "NEXT") == NEXT, res.stdout
    assert _kv(lines, "STARTED") == "yes", (res.stdout, res.stderr)
    assert prompt, res.stdout

    calls = _calls(proj)
    tabs, runs = _of(calls, "tab create"), _of(calls, "pane run")
    assert len(tabs) == 1 and len(runs) == 1, calls
    tab = tabs[0]
    assert _opt(tab, "--workspace") == WS, tab
    assert _opt(tab, "--label") == "#547 Phasenwechsel frisch", tab
    assert _opt(tab, "--env") == f"{ENV_KEY}={PANE}", tab
    assert "--no-focus" in tab, tab
    assert calls.index(tab) < calls.index(runs[0]), calls
    assert runs[0][:3] == ["pane", "run", NEW_PANE], runs
    assert shlex.split(runs[0][3]) == ["exec", "claude", prompt], runs


# --- AC-11 ------------------------------------------------------------------

def test_started_writes_handoff_same_note(tmp_path):
    """AC-11: Erfolg -> handoff_same {phase, next, at}; Misserfolg -> kein Vermerk."""
    proj = _wf_project(tmp_path / "ok")
    herdr = _fake(tmp_path / "ok")
    res = _same(proj, "--start", env=_full_env(proj, herdr))
    lines, _ = _parse(res.stdout)
    assert _kv(lines, "STARTED") == "yes", (res.stdout, res.stderr)
    note = _state(proj).get("handoff_same")
    assert isinstance(note, dict), _state(proj)
    assert note.get("phase") == "phase5_tdd_red", note
    assert note.get("next") == _kv(lines, "NEXT") == NEXT, note
    _assert_iso(note.get("at"))
    at = note["at"]
    assert at.endswith("Z") or at.endswith("+00:00"), at

    proj = _wf_project(tmp_path / "fail")
    herdr = _fake(tmp_path / "fail")
    before = _state_file(proj).read_bytes()
    res = _same(proj, "--start", env=_full_env(proj, herdr, FAKE_RUN_EXIT="1"))
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, _ = _parse(res.stdout)
    assert _kv(lines, "HANDOFF") == "herdr", res.stdout
    assert _kv(lines, "STARTED") == "no", (res.stdout, res.stderr)
    assert (_kv(lines, "REASON") or "").strip(), res.stdout
    assert "handoff_same" not in _state(proj), _state(proj)
    assert "waiting_on" not in _state(proj), _state(proj)
    assert _state_file(proj).read_bytes() == before


# --- AC-12 ------------------------------------------------------------------

def test_second_start_same_phase_is_already(tmp_path):
    """AC-12: Vermerk mit gleicher Phase und NEXT -> already, kein zweiter Tab, State unveraendert;
    andere Phase oder anderer NEXT -> neuer Start."""
    note = {"phase": "phase5_tdd_red", "next": NEXT, "at": "2026-11-26T09:00:00Z"}
    proj = _wf_project(tmp_path / "same", **STATE_RED_DONE, handoff_same=note,
                       waiting_on="alter Wartegrund")
    herdr = _fake(tmp_path / "same")
    res = _same(proj, "--start", env=_full_env(proj, herdr))
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, _ = _parse(res.stdout)
    assert _kv(lines, "HANDOFF") == "herdr", res.stdout
    assert _kv(lines, "STARTED") == "already", (res.stdout, res.stderr)
    _no_start(proj, "same")
    st = _state(proj)
    assert st.get("handoff_same") == note, st
    assert st.get("waiting_on") == "alter Wartegrund", st

    # Zweiter Lauf nach echtem Start: already, genau ein tab create
    proj = _wf_project(tmp_path / "twice")
    herdr = _fake(tmp_path / "twice")
    env = _full_env(proj, herdr)
    first = _same(proj, "--start", env=env)
    assert _kv(_parse(first.stdout)[0], "STARTED") == "yes", (first.stdout, first.stderr)
    snap = _state(proj)
    second = _same(proj, "--start", env=env)
    assert _kv(_parse(second.stdout)[0], "STARTED") == "already", second.stdout
    assert len(_of(_calls(proj), "tab create")) == 1, _calls(proj)
    assert _state(proj).get("handoff_same") == snap.get("handoff_same")
    assert _state(proj).get("waiting_on") == snap.get("waiting_on")

    for name, other in (("other_phase", dict(note, phase="phase4_approved")),
                        ("other_next", dict(note, next="/40-tdd-red #547"))):
        proj = _wf_project(tmp_path / name, **STATE_RED_DONE, handoff_same=other)
        herdr = _fake(tmp_path / name)
        res = _same(proj, "--start", env=_full_env(proj, herdr))
        lines, _ = _parse(res.stdout)
        assert _kv(lines, "STARTED") == "yes", (name, res.stdout, res.stderr)
        assert len(_of(_calls(proj), "tab create")) == 1, (name, _calls(proj))
        assert _state(proj)["handoff_same"]["phase"] == "phase5_tdd_red", name
        assert _state(proj)["handoff_same"]["next"] == NEXT, name


# --- AC-13 ------------------------------------------------------------------

def test_started_sets_waiting_on_for_hourglass_end_state(tmp_path):
    """AC-13: STARTED=yes -> waiting_on nennt Fortsetzung durch frische Sitzung, Endzustand ⏳."""
    proj = _wf_project(tmp_path / "p")
    herdr = _fake(tmp_path / "p")
    env = _full_env(proj, herdr)
    res = _same(proj, "--start", env=env)
    lines, _ = _parse(res.stdout)
    assert _kv(lines, "STARTED") == "yes", (res.stdout, res.stderr)
    waiting = _state(proj).get("waiting_on") or ""
    assert NEXT in waiting, waiting
    assert "frisch" in waiting.lower(), waiting

    end = subprocess.run([sys.executable, str(proj / ".claude" / "hooks" / "workflow.py"),
                          "endstate"], capture_output=True, text=True, env=env, cwd=str(proj),
                         timeout=60)
    assert end.returncode == 0, (end.stdout, end.stderr)
    out = end.stdout.splitlines()
    assert _kv(out, "ENDSTATE") == "waiting", end.stdout
    assert (_kv(out, "FOOTER") or "").startswith("⏳"), end.stdout


# --- AC-14 ------------------------------------------------------------------

def _expected_queue_add(auftrag: dict, open_issues: list) -> list:
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    ref = workflow.handoff_prompt(open_issues[0], open_issues, auftrag, ".claude/hooks")
    return _queue_add_tokens(ref)


def test_prompt_contains_all_building_blocks(tmp_path):
    """AC-14: Startauftrag mit Workflow, Issue, queue add (inkl. laufendem Issue), waiting --clear,
    Folgebefehl samt Fallback, #696-Hinweis, autark-Zeile, Bitte um Stand; ohne Auftrag ohne
    queue add und autark-Zeile."""
    note = 'Sag "hallo"; danach $HOME nicht anfassen'
    proj = _project(tmp_path / "with", issues=((547, "open"), (548, "open"), (549, "done")),
                    note=note, spur="kontext", phase="phase5_tdd_red")
    _set_state(proj, **STATE_RED_DONE)
    herdr = _fake(tmp_path / "with")
    res = _same(proj, "--start", env=_full_env(proj, herdr))
    assert res.returncode == 0, (res.stdout, res.stderr)
    lines, prompt = _parse(res.stdout)
    assert _kv(lines, "STARTED") == "yes", (res.stdout, res.stderr)
    assert prompt, res.stdout

    assert WF in prompt and "#547" in prompt, prompt
    tokens = _queue_add_tokens(prompt)
    assert tokens[:5] == [".claude/hooks/workflow.py", "queue", "add", "547", "548"], tokens
    assert "549" not in tokens and "--autark" in tokens, tokens
    assert tokens[tokens.index("--note") + 1] == note, tokens
    assert tokens[tokens.index("--spur") + 1] == "kontext", tokens
    auftrag = {"issues": [{"n": 547, "status": "open"}, {"n": 548, "status": "open"},
                          {"n": 549, "status": "done"}], "autark": True, "note": note,
               "spur": "kontext"}
    assert tokens == _expected_queue_add(auftrag, [547, 548]), tokens

    clear = "python3 .claude/hooks/workflow.py waiting --clear"
    follow = "Kurzbefehl `50-implement` mit Argument `#547`"
    assert clear in prompt, prompt
    assert follow in prompt, prompt
    assert "skills/50-implement/SKILL.md" in prompt, prompt
    assert prompt.index("queue add") < prompt.index(clear) < prompt.index(follow), prompt
    assert HANDOFF_NOTE_696 in prompt, prompt
    assert "Autarker Auftrag" in prompt and "PO-Punkten" in prompt, prompt
    assert "AskUserQuestion" in prompt, prompt
    stand = [l for l in prompt.splitlines() if "ersten Meldung" in l]
    assert len(stand) == 1, prompt
    assert "einem Satz" in stand[0] and "Stand" in stand[0], stand
    assert "00-intake" not in prompt, prompt

    # Ohne Auftrag: keine queue-add- und keine autark-Zeile
    proj = _wf_project(tmp_path / "without")
    herdr = _fake(tmp_path / "without")
    res = _same(proj, "--start", env=_full_env(proj, herdr))
    lines, prompt = _parse(res.stdout)
    assert _kv(lines, "STARTED") == "yes", (res.stdout, res.stderr)
    assert prompt, res.stdout
    assert "queue add" not in prompt and "Autarker Auftrag" not in prompt, prompt
    assert "PO-Punkten" not in prompt, prompt
    assert clear in prompt and follow in prompt and HANDOFF_NOTE_696 in prompt, prompt
    assert WF in prompt and "#547" in prompt, prompt


# --- AC-15 ------------------------------------------------------------------

CHAIN = [("10-context", "20-analyse"), ("20-analyse", "30-write-spec"),
         ("30-write-spec", "40-tdd-red"), ("40-tdd-red", "50-implement"),
         ("50-implement", "60-validate")]


def test_phase_commands_describe_handoff_and_skills_in_sync():
    """AC-15: Befehlstexte 10-50 (+ Skills) verlangen bei CONTEXT_HANDOFF=on `handoff --same --start`,
    bei yes/already Antwort beenden, bei no Kette wie bisher; CONTEXT_STOP-Regel unveraendert;
    keine Drift."""
    for name, follow in CHAIN:
        for path in (COMMANDS_DIR / f"{name}.md", SKILLS_DIR / name / "SKILL.md"):
            text = path.read_text(encoding="utf-8")
            paras = [p for p in text.split("\n\n") if "CONTEXT_HANDOFF=on" in p]
            assert len(paras) == 1, (str(path), len(paras))
            para = paras[0]
            assert "workflow.py handoff --same --start" in para, (str(path), para)
            assert "STARTED=yes" in para and "already" in para, (str(path), para)
            assert "STARTED=no" in para, (str(path), para)
            assert f"`{follow}`" in para, (str(path), para)
            assert "⏳" in para, (str(path), para)
            # CONTEXT_STOP-Regel (#658) unveraendert
            stop = [p for p in text.split("\n\n")
                    if re.search(r"(?:workflow\.py|\$WF) context`", p) and "Kontext-Haushalt" in p]
            assert len(stop) == 1, (str(path), len(stop))
            assert "CONTEXT_STOP=on" in stop[0] and "CONTEXT_STOP=off" in stop[0], str(path)
            assert f"`{follow}` NICHT selbst aufrufen" in stop[0], str(path)
            assert f"❗Du-Zeile `/{follow} #<N>`" in stop[0], str(path)

    for script in ("sync_skills.py", "sync_cloud_agents.py"):
        res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script), "--check"],
                             capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60)
        assert res.returncode == 0, (script, res.stdout, res.stderr)


# --- AC-16 ------------------------------------------------------------------

def test_docs_changelog_and_version_consistent():
    """AC-16: 80-workflow-Doku beschreibt `handoff --same [--start]` mit HANDOFF/NEXT/STARTED;
    CHANGELOG 4.28.0 mit #696; Versionen in plugin.json, CLAUDE.md, README stimmen ueberein."""
    for path in (COMMANDS_DIR / "80-workflow.md", REPO_ROOT / "docs" / "befehle" / "80-workflow.md"):
        text = path.read_text(encoding="utf-8")
        assert "handoff --same" in text, str(path)
        block = "\n".join(p for p in text.split("\n\n") if "--same" in p)
        assert "--start" in block, (str(path), block)
        for key in ("HANDOFF", "NEXT", "STARTED"):
            assert key in block, (str(path), key, block)

    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## \[4\.28\.0\][^\n]*\n(.*?)(?=^## \[)", changelog, re.M | re.S)
    assert m, "CHANGELOG ohne Abschnitt 4.28.0"
    assert "#696" in m.group(1), m.group(1)

    plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin.get("version") == "4.28.0", plugin.get("version")
    for name in ("CLAUDE.md", "README.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert re.search(r"\*\*Version\*\*: 4\.28\.0\b", text), name
