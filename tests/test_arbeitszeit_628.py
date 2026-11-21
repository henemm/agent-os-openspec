"""Zeitschätzung zeigt nur Arbeitszeit (Issue #628).

Ergänzt #620 (`tests/test_zeitschaetzung_620.py`): Wartezeit auf die
Spec-Freigabe des PO und Leerlauf zählen nicht als Arbeitszeit.

Schnittstellen (Spec docs/specs/feat-628-schaetzung-arbeitszeit.md):
- `po_wait_minutes(data)`: Überschneidung [po_briefing.created, Freigabe mit
  trigger "approval"] mit den `phase_log`-Segmenten
- `note_activity(workflow, phase, now)`: schreibt
  `.claude/workflows/_activity/<workflow>.json` atomar, `{"last", "phases"}`
- `load_activity(workflow)`: liest diese Datei (fail-open)
- `awaiting_human_approval(data)`: Zusatz „ + Wartezeit auf dich“ /
  `ESTIMATE_WAITING=po`
- `session_singleton_guard._heartbeat` ruft `note_activity` nur im fälligen
  Throttle-Zweig, fail-open
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"

P1 = "phase1_context"
P2 = "phase2_analyse"
P3 = "phase3_spec"
P4 = "phase4_approved"
P5 = "phase5_tdd_red"
P6 = "phase6_implement"
P6B = "phase6b_adversary"
P7 = "phase7_validate"
P8 = "phase8_complete"

CONFIG_ON = """time_estimate:
  enabled: true
  min_samples: 3
  quantiles: [0.25, 0.75]
  defaults:
    feature: [60, 240]
    feature-fast: [20, 60]
"""
WAIT_SUFFIX = " + Wartezeit auf dich"
TIME_PREFIXES = ("Start  ", "Dauer  ", "Ende  ")
NOW = datetime(2026, 11, 21, 14, 0, 0)


# --- Helpers ---------------------------------------------------------------

def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _ssg():
    sys.path.insert(0, str(HOOKS_DIR))
    import session_singleton_guard  # noqa: PLC0415
    return session_singleton_guard


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _reset_config_cache():
    sys.path.insert(0, str(HOOKS_DIR))
    import config_loader  # noqa: PLC0415
    for fn in (config_loader.find_project_root, config_loader.load_config):
        clear = getattr(fn, "cache_clear", None)
        if clear:
            clear()


def _project(root: Path, config: "str | None" = CONFIG_ON) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_archive").mkdir(parents=True)
    (proj / "_home").mkdir()
    if config is not None:
        (proj / "openspec.yaml").write_text(config)
    return proj


def _set_config(proj: Path, text: str) -> None:
    (proj / "openspec.yaml").write_text(text)
    _reset_config_cache()


@pytest.fixture(autouse=True)
def proj(tmp_path, monkeypatch):
    """Jeder Test läuft in einem eigenen tmp-Projekt: nie im echten
    `.claude/workflows/_activity/` oder `_archive/` des Repos."""
    for k in list(os.environ):
        if k.startswith(("OPENSPEC_", "HERDR_", "GH_")):
            monkeypatch.delenv(k, raising=False)
    root = tmp_path / "inproc"
    root.mkdir()
    project = _project(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.setenv("HOME", str(project / "_home"))
    monkeypatch.chdir(project)
    _reset_config_cache()
    yield project
    monkeypatch.undo()
    _reset_config_cache()


def _case(tmp_path: Path, label: str, config: "str | None" = CONFIG_ON):
    root = tmp_path / label
    root.mkdir()
    project = _project(root, config)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "GH_"))}
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env["HOME"] = str(project / "_home")
    return project, env


def _workflows(project: Path) -> Path:
    return project / ".claude" / "workflows"


def _archive(project: Path) -> Path:
    return _workflows(project) / "_archive"


def _activity_file(project: Path, name: str) -> Path:
    return _workflows(project) / "_activity" / f"{name}.json"


def _write_active(project: Path, data: dict) -> Path:
    path = _workflows(project) / f"{data['name']}.json"
    path.write_text(json.dumps(data))
    (project / ".claude" / "active_workflow").write_text(data["name"])
    return path


def _workflow(args, env, cwd, timeout: float = 30):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args], capture_output=True,
                          text=True, env=env, cwd=str(cwd), timeout=timeout)


def _kv(stdout: str, key: str) -> "str | None":
    for line in stdout.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _time_lines(text: str) -> list:
    return [ln for ln in text.splitlines() if ln.startswith(TIME_PREFIXES)]


def _dauer(text: str) -> "str | None":
    return next((ln for ln in text.splitlines() if ln.startswith("Dauer  ")), None)


def _close(a: datetime, b: datetime, seconds: float = 60.0) -> bool:
    return abs((a - b).total_seconds()) <= seconds


def _total(value) -> float:
    """`po_wait_minutes` darf je Phase (dict) oder gesamt (Zahl) liefern."""
    if isinstance(value, dict):
        return float(sum(float(v) for v in value.values()))
    return float(value)


def _seg(phase: str, start: datetime, end: "datetime | None", dur=None) -> dict:
    if end is None:
        return {"phase": phase, "entered_at": _iso(start), "exited_at": None,
                "duration_min": None}
    minutes = round((end - start).total_seconds() / 60, 1) if dur is None else dur
    return {"phase": phase, "entered_at": _iso(start), "exited_at": _iso(end),
            "duration_min": float(minutes)}


def _approval(at: datetime, trigger: str = "approval") -> dict:
    return {"from": P3, "to": P4, "at": _iso(at), "trigger": trigger}


def _archived(name: str, phases: dict, start: datetime = datetime(2026, 11, 1, 9, 0),
              **fields) -> dict:
    log, t = [], start
    for phase, minutes in phases.items():
        end = t + timedelta(minutes=minutes)
        log.append(_seg(phase, t, end, float(minutes)))
        t = end
    data = {"name": name, "workflow_type": "feature", "current_phase": P8,
            "created": _iso(start), "phase_transitions": [], "phase_log": log}
    data.update(fields)
    return data


def _write_archived(project: Path, data: dict) -> Path:
    path = _archive(project) / f"{data['name']}.json"
    path.write_text(json.dumps(data))
    return path


# =============================================================================
# Fixture: über Nacht wartende Spec (AC-1, AC-4)
#   P1 20, P2 10, P3 15 | Briefing 21:45 | P3 480 (Warten) | Freigabe 05:45
#   P4 2, P5 10, P6 30, P7 3
# =============================================================================

T0 = datetime(2026, 11, 9, 21, 0)
BRIEF = T0 + timedelta(minutes=45)
APPROVE = BRIEF + timedelta(minutes=480)


def _overnight(trigger: str = "approval", briefing_at: "datetime | None" = BRIEF,
               seg2_dur=None, **fields) -> dict:
    m = lambda k: T0 + timedelta(minutes=k)  # noqa: E731
    log = [_seg(P1, m(0), m(20)), _seg(P2, m(20), m(30)), _seg(P3, m(30), m(45)),
           _seg(P3, m(45), APPROVE, seg2_dur)]
    t = APPROVE
    for phase, minutes in ((P4, 2), (P5, 10), (P6, 30), (P7, 3)):
        log.append(_seg(phase, t, t + timedelta(minutes=minutes)))
        t += timedelta(minutes=minutes)
    log.append(_seg(P8, t, None))
    data = {"name": "wf-nacht", "workflow_type": "feature", "current_phase": P8,
            "created": _iso(T0), "phase_log": log,
            "phase_transitions": [{"from": P2, "to": P3, "at": _iso(m(30)),
                                   "trigger": "command"},
                                  _approval(APPROVE, trigger)]}
    if briefing_at is not None:
        data["po_briefing"] = {"created": briefing_at.isoformat(timespec="seconds"),
                               "ampel": "red", "file": "docs/briefings/wf-nacht.md"}
    data.update(fields)
    return data


# =============================================================================
# AC-1: PO-Wartezeit wird abgezogen, bei "auto" nicht
# =============================================================================

def test_po_wartezeit_wird_abgezogen_und_auto_nicht():
    wf = _wf()

    # Freigabe per "approval": 480 min Warten im zweiten P3-Segment
    data = _overnight()
    assert _total(wf.po_wait_minutes(data)) == pytest.approx(480.0, abs=0.1)
    entry = wf._archive_phase_entry(data)
    assert entry["phases"][P3] == pytest.approx(15.0, abs=0.1), entry
    for phase, minutes in ((P1, 20), (P2, 10), (P4, 2), (P5, 10), (P6, 30), (P7, 3)):
        assert entry["phases"][phase] == pytest.approx(minutes, abs=0.1), (phase, entry)

    # Briefing schon 5 min im ersten Segment: Überschneidung je Segment
    early = _overnight(briefing_at=BRIEF - timedelta(minutes=5))
    assert _total(wf.po_wait_minutes(early)) == pytest.approx(485.0, abs=0.1)
    assert wf._archive_phase_entry(early)["phases"][P3] == pytest.approx(10.0, abs=0.1)

    # Nie unter 0: Segmentdauer (470) kleiner als die Überschneidung (480)
    short = _overnight(seg2_dur=470.0)
    assert wf._archive_phase_entry(short)["phases"][P3] == pytest.approx(15.0, abs=0.1)

    # trigger "auto": nichts abgezogen
    auto = _overnight(trigger="auto")
    assert _total(wf.po_wait_minutes(auto)) == pytest.approx(0.0, abs=0.01)
    assert wf._archive_phase_entry(auto)["phases"][P3] == pytest.approx(495.0, abs=0.1)

    # ohne Briefing: nichts abgezogen
    bare = _overnight(briefing_at=None)
    assert _total(wf.po_wait_minutes(bare)) == pytest.approx(0.0, abs=0.01)
    assert wf._archive_phase_entry(bare)["phases"][P3] == pytest.approx(495.0, abs=0.1)

    # ohne Freigabe-Übergang bzw. mit ungültigem Zeitstempel: nichts abgezogen
    no_tr = _overnight(phase_transitions=[])
    assert _total(wf.po_wait_minutes(no_tr)) == pytest.approx(0.0, abs=0.01)
    bad_at = _overnight()
    bad_at["phase_transitions"][-1]["at"] = "kaputt"
    assert _total(wf.po_wait_minutes(bad_at)) == pytest.approx(0.0, abs=0.01)
    assert wf._archive_phase_entry(bad_at)["phases"][P3] == pytest.approx(495.0, abs=0.1)


# =============================================================================
# AC-2: Heartbeat schreibt Aktivität nur im fälligen Throttle-Zweig
# =============================================================================

def _guard_env(monkeypatch, project: Path, name: str, phase: str):
    ssg = _ssg()
    import hook_utils  # noqa: PLC0415
    locks = project / ".claude" / "session-locks"
    locks.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ssg, "_locks_dir", lambda: locks)
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: project)
    monkeypatch.setattr(ssg, "find_project_root", lambda: project, raising=False)
    monkeypatch.setattr(hook_utils, "resolve_active_workflow", lambda: (name, "file"))
    monkeypatch.setattr(ssg, "resolve_active_workflow", lambda: (name, "file"),
                        raising=False)
    state = _workflows(project) / f"{name}.json"
    state.write_text(json.dumps({"name": name, "current_phase": phase,
                                 "workflow_type": "feature"}))
    return ssg, locks, state


def _lock(ssg, locks: Path, sid: str, last_seen: float, **extra) -> Path:
    path = locks / f"{ssg._safe_sid(sid)}.json"
    path.write_text(json.dumps({"session_id": sid, "cwd": "/x", "pid": 999999999,
                                "started_at": last_seen, "last_seen": last_seen,
                                "agent_name": "agent-628", **extra}))
    return path


def test_heartbeat_schreibt_aktivitaet_nur_im_faelligen_zweig(proj, monkeypatch):
    name = "feat-628-hb"
    ssg, locks, state = _guard_env(monkeypatch, proj, name, P6)
    state_before = state.read_bytes()
    activity = _activity_file(proj, name)

    replaced = []
    real_replace = os.replace

    def spy_replace(src, dst, *a, **k):
        replaced.append(str(dst))
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", spy_replace)

    # Innerhalb des Throttle-Fensters: kein Schreiben der Aktivität. Der Eintrag
    # trägt schon workflow/phase, sonst wäre `_note_activity` ohnehin ein No-op (F001).
    now = time.time()
    _lock(ssg, locks, "sess-throttled", now - 10, workflow=name, phase=P6)
    ssg._heartbeat("sess-throttled", str(proj))
    assert not activity.exists(), "Aktivität außerhalb des fälligen Zweigs geschrieben"

    # Fälliger Zweig: Aktivitätsdatei mit last und phases
    lock = _lock(ssg, locks, "sess-due", now - 120)
    ssg._heartbeat("sess-due", str(proj))
    assert json.loads(lock.read_text())["last_seen"] >= now, "Heartbeat lief nicht"
    assert activity.is_file(), "Heartbeat hat keine Aktivitätsdatei geschrieben"
    data = json.loads(activity.read_text())
    assert "last" in data and data["last"] is not None, data
    assert isinstance(data.get("phases"), dict), data

    # Atomar: über os.replace auf die Zieldatei, keine Temp-Reste
    assert str(activity) in replaced, replaced
    assert sorted(p.name for p in activity.parent.iterdir()) == [f"{name}.json"]

    # Workflow-JSON bleibt unverändert
    assert state.read_bytes() == state_before


# =============================================================================
# AC-3: note_activity und idle_gap_min
# =============================================================================

def _phases(project: Path, name: str) -> dict:
    return json.loads(_activity_file(project, name).read_text()).get("phases") or {}


def test_note_activity_idle_gap(proj):
    wf = _wf()
    name = "wf-idle"
    t0 = datetime(2026, 11, 21, 9, 0)
    wf.note_activity(name, P3, t0)
    assert _activity_file(proj, name).is_file()
    assert float(_phases(proj, name).get(P3, 0)) == pytest.approx(0.0, abs=0.01)

    # 5 min später (< 15 Standard): Gutschrift 5 min
    wf.note_activity(name, P3, t0 + timedelta(minutes=5))
    assert float(_phases(proj, name)[P3]) == pytest.approx(5.0, abs=0.05)

    # 40 min Lücke (> 15): keine Gutschrift, aber last neu gesetzt
    last_before = json.loads(_activity_file(proj, name).read_text())["last"]
    wf.note_activity(name, P3, t0 + timedelta(minutes=45))
    after = json.loads(_activity_file(proj, name).read_text())
    assert float(after["phases"][P3]) == pytest.approx(5.0, abs=0.05), after
    assert after["last"] != last_before, after

    # Belegt, dass last gesetzt wurde: 5 min später in P6 -> 5 min für P6
    wf.note_activity(name, P6, t0 + timedelta(minutes=50))
    phases = _phases(proj, name)
    assert float(phases[P6]) == pytest.approx(5.0, abs=0.05), phases
    assert float(phases[P3]) == pytest.approx(5.0, abs=0.05), phases

    # idle_gap_min aus der Config: 60 -> 40 min Lücke wird gutgeschrieben
    _set_config(proj, CONFIG_ON + "  idle_gap_min: 60\n")
    other = "wf-idle-60"
    wf.note_activity(other, P6, t0)
    wf.note_activity(other, P6, t0 + timedelta(minutes=40))
    assert float(_phases(proj, other)[P6]) == pytest.approx(40.0, abs=0.05)


# =============================================================================
# AC-4: Archiv nutzt Aktivität, sonst phase_log minus Wartezeit
# =============================================================================

def _norm(phases: dict) -> dict:
    return {k: round(float(v), 1) for k, v in phases.items()}


def test_archiv_nutzt_aktivitaet_sonst_phase_log_minus_wartezeit(proj):
    wf = _wf()
    archive = _archive(proj)
    with_act = _overnight(name="wf-mit-aktivitaet")
    without = _overnight(name="wf-ohne-aktivitaet")
    empty_act = _overnight(name="wf-leere-aktivitaet")
    paths = [_write_archived(proj, d) for d in (with_act, without, empty_act)]
    before = {p: p.read_bytes() for p in paths}

    act_dir = _workflows(proj) / "_activity"
    act_dir.mkdir()
    (act_dir / "wf-mit-aktivitaet.json").write_text(json.dumps(
        {"last": "2026-11-10T06:30:00", "phases": {P1: 12.0, P3: 9.0, P6: 25.0}}))
    (act_dir / "wf-leere-aktivitaet.json").write_text(json.dumps(
        {"last": "2026-11-10T06:30:00", "phases": {}}))

    history = wf.load_archive_phase_durations(archive)
    assert len(history) == 3, history
    got = [_norm(h["phases"]) for h in history]

    from_activity = {P1: 12.0, P3: 9.0, P6: 25.0}
    from_log = {P1: 20.0, P2: 10.0, P3: 15.0, P4: 2.0, P5: 10.0, P6: 30.0, P7: 3.0}
    assert got.count(from_activity) == 1, got
    assert got.count(from_log) == 2, got  # ohne Datei und mit leerer Datei

    # Archivdateien unverändert
    assert {p: p.read_bytes() for p in paths} == before


# =============================================================================
# AC-5: laufender Workflow nutzt Arbeitszeit
# =============================================================================

HIST_PHASES = {P1: 10, P2: 10, P3: 30, P4: 1, P5: 10, P6: 30, P6B: 10, P7: 5}


def test_laufender_workflow_nutzt_arbeitszeit(proj, monkeypatch):
    wf = _wf()
    for i in range(3):
        _write_archived(proj, _archived(f"wf-hist-{i}", HIST_PHASES))
    cfg = wf.time_estimate_config()
    assert cfg is not None
    history = wf.load_archive_phase_durations(_archive(proj))
    assert len(history) == 3

    # (a) Seit 3,5 h in phase3_spec, Briefing wartet; Aktivität: 12 + 6 + 20 min
    created = NOW - timedelta(minutes=240)
    entered = created + timedelta(minutes=30)
    waiting = {"name": "wf-wartet", "workflow_type": "feature", "current_phase": P3,
               "created": _iso(created), "last_updated": _iso(entered),
               "phase_transitions": [],
               "phase_log": [_seg(P1, created, created + timedelta(minutes=20)),
                             _seg(P2, created + timedelta(minutes=20), entered),
                             _seg(P3, entered, None)],
               "po_briefing": {"created": _iso(entered + timedelta(minutes=15)),
                               "ampel": "red", "file": "docs/briefings/wf-wartet.md"}}
    act = _activity_file(proj, "wf-wartet")
    act.parent.mkdir(parents=True, exist_ok=True)
    act.write_text(json.dumps({"last": _iso(NOW - timedelta(minutes=200)),
                               "phases": {P1: 12.0, P2: 6.0, P3: 20.0}}))
    monkeypatch.setattr(wf, "_estimate_now", lambda: NOW)

    est = wf.current_estimate(dict(waiting))
    assert isinstance(est, dict), est
    # verstrichen = Aktivminuten 38; laufende Phase 20 -> Rest 10 + 56 = 66
    assert est["elapsed_min"] == pytest.approx(38.0, abs=0.5), est
    assert est["low_min"] == pytest.approx(66.0, abs=0.5), est
    assert est["high_min"] == pytest.approx(66.0, abs=0.5), est
    assert est["total_low_min"] == pytest.approx(104.0, abs=1.0), est
    assert _close(est["end_low"], NOW + timedelta(minutes=66)), est["end_low"]
    assert _close(est["end_high"], NOW + timedelta(minutes=66)), est["end_high"]

    # (b) Ohne Aktivitätsdatei: Wanduhr minus PO-Wartezeit (Freigabe per approval)
    start = datetime(2026, 11, 20, 21, 0)
    brief = start + timedelta(minutes=45)
    approve = brief + timedelta(minutes=480)
    now_b = approve + timedelta(minutes=15)
    running = {"name": "wf-nach-freigabe", "workflow_type": "feature",
               "current_phase": P5, "created": _iso(start),
               "last_updated": _iso(approve + timedelta(minutes=2)),
               "phase_transitions": [_approval(approve)],
               "phase_log": [_seg(P1, start, start + timedelta(minutes=20)),
                             _seg(P2, start + timedelta(minutes=20),
                                  start + timedelta(minutes=30)),
                             _seg(P3, start + timedelta(minutes=30), approve),
                             _seg(P4, approve, approve + timedelta(minutes=2)),
                             _seg(P5, approve + timedelta(minutes=2), None)],
               "po_briefing": {"created": brief.isoformat(timespec="seconds"),
                               "ampel": "red", "file": "docs/briefings/x.md"}}
    # Wanduhr 540 min, Wartezeit 480 -> 60 min Arbeitszeit
    pure = wf.estimate_remaining(dict(running), history, cfg, now_b)
    assert isinstance(pure, dict), pure
    assert pure["elapsed_min"] == pytest.approx(60.0, abs=0.5), pure
    # Rest in P5 (seit 13 min): max(0, 10-13) + 30 + 10 + 5 = 45; Ende = jetzt + Rest
    assert pure["low_min"] == pytest.approx(45.0, abs=0.5), pure
    assert pure["total_low_min"] == pytest.approx(105.0, abs=1.0), pure
    assert _close(pure["end_low"], now_b + timedelta(minutes=45)), pure["end_low"]

    monkeypatch.setattr(wf, "_estimate_now", lambda: now_b)
    via_cli = wf.current_estimate(dict(running))
    assert via_cli["elapsed_min"] == pytest.approx(60.0, abs=0.5), via_cli


# =============================================================================
# AC-6: „+ Wartezeit auf dich“ nur bei ausstehender menschlicher Freigabe
# =============================================================================

BRIEF_GREEN = "# Briefing\n\n## Ampel\n\nAmpel: grün\n"
BRIEF_RED = "# Briefing\n\n## Ampel\n\nAmpel: rot\n"


def _briefing(project: Path, ampel: str) -> dict:
    text = BRIEF_GREEN if ampel == "green" else BRIEF_RED
    rel = "docs/briefings/wf-wait.md"
    (project / "docs" / "briefings").mkdir(parents=True, exist_ok=True)
    (project / rel).write_text(text)
    return {"file": rel, "briefing_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "ampel": ampel, "created": _iso(datetime.now() - timedelta(minutes=20))}


def _running(phase: str, **fields) -> dict:
    now = datetime.now()
    created = now - timedelta(minutes=60)
    entered = now - timedelta(minutes=30)
    data = {"name": "wf-wait", "workflow_type": "feature", "current_phase": phase,
            "created": _iso(created), "last_updated": _iso(entered),
            "phase_transitions": [],
            "phase_log": [_seg(P1, created, entered), _seg(phase, entered, None)],
            "spec_file": "docs/specs/wf-wait.md"}
    data.update(fields)
    return data


WAIT_CASES = [
    # (label, mode, phase, ampel or None, extra, erwartet)
    ("ampel-rot-auto", "auto", P3, "red", {}, True),
    ("gruen-manual", "manual", P3, "green", {}, True),
    ("gruen-auto", "auto", P3, "green", {}, False),
    ("ohne-briefing", "manual", P3, None, {}, False),
    ("andere-phase", "manual", P5, "red", {}, False),
    ("p6-gruen-manual", "manual", P6, None,
     {"last_test_run": {"result": "passed", "runner": "pytest", "at": "x"},
      "green_approved": False}, True),
    ("p6-gruen-auto", "auto", P6, None,
     {"last_test_run": {"result": "passed", "runner": "pytest", "at": "x"},
      "green_approved": False}, False),
    # „go“ schon erteilt: wartet nicht mehr (F004, M6c)
    ("p6-go-erteilt-manual", "manual", P6, None,
     {"last_test_run": {"result": "passed", "runner": "pytest", "at": "x"},
      "green_approved": True}, False),
]


def test_wartezeit_zusatz_nur_bei_ausstehender_menschlicher_freigabe(tmp_path, monkeypatch):
    wf = _wf()
    failures = []
    for label, mode, phase, ampel, extra, expected in WAIT_CASES:
        project, env = _case(tmp_path, label,
                             config=CONFIG_ON + f"autonomy:\n  mode: {mode}\n")
        fields = dict(extra)
        if ampel is not None:
            fields["po_briefing"] = _briefing(project, ampel)
        data = _running(phase, **fields)
        _write_active(project, data)

        # In-Process: awaiting_human_approval mit der Config dieses Projekts
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
        monkeypatch.chdir(project)
        _reset_config_cache()
        if label == "gruen-auto":
            # Vorbedingung: Auto-Freigabe greift hier tatsächlich
            assert wf._auto_approval_pending(data) is True, label
        awaiting = getattr(wf, "awaiting_human_approval", None)
        if awaiting is None:
            failures.append((label, "awaiting_human_approval fehlt"))
        elif bool(awaiting(data)) is not expected:
            failures.append((label, "awaiting_human_approval", expected))

        plan = _workflow(["plan"], env, project)
        assert plan.returncode == 0, (label, plan.stderr)
        dauer = _dauer(plan.stdout)
        assert dauer is not None, (label, plan.stdout)
        est = _workflow(["estimate"], env, project)
        assert est.returncode == 0, (label, est.stderr)
        line = _kv(est.stdout, "LINE") or ""
        waiting = _kv(est.stdout, "ESTIMATE_WAITING")
        if expected:
            ok = (dauer.endswith(WAIT_SUFFIX) and line.endswith(WAIT_SUFFIX)
                  and waiting == "po")
        else:
            ok = ("Wartezeit auf dich" not in plan.stdout
                  and "Wartezeit auf dich" not in est.stdout and waiting is None)
        if not ok:
            failures.append((label, dauer, line, waiting, expected))
    assert not failures, failures


# =============================================================================
# AC-7: Ist-Block zeigt Arbeitszeit und Gesamtzeit
# =============================================================================

def test_ist_block_arbeitszeit_mit_gesamtzeit():
    wf = _wf()
    # Arbeitszeit 70 min, Wartezeit 472 min, gesamt 542 min = 9 h 2 min
    start = datetime(2026, 11, 20, 21, 0)
    m = lambda k: start + timedelta(minutes=k)  # noqa: E731
    approve = m(40) + timedelta(minutes=472)
    log = [_seg(P1, m(0), m(20)), _seg(P2, m(20), m(30)), _seg(P3, m(30), m(40)),
           _seg(P3, m(40), approve)]
    t = approve
    for phase, minutes in ((P4, 2), (P5, 10), (P6, 10), (P7, 8)):
        log.append(_seg(phase, t, t + timedelta(minutes=minutes)))
        t += timedelta(minutes=minutes)
    data = {"name": "wf-ist", "workflow_type": "feature", "current_phase": P8,
            "created": _iso(start), "phase_log": log, "ship_status": "done",
            "phase_transitions": [_approval(approve)],
            "po_briefing": {"created": m(40).isoformat(timespec="seconds"),
                            "ampel": "red", "file": "docs/briefings/wf-ist.md"}}
    actual = {"actual": True, "now": datetime(2026, 11, 21, 12, 0)}
    out = wf.render_plan(data, archived=True, estimate=dict(actual))
    assert _dauer(out) == "Dauer  1 h 10 min (gesamt 9 h 2 min)", out
    assert [ln.split("  ")[0] for ln in _time_lines(out)] == ["Start", "Dauer", "Ende"]

    # Gleiche Arbeits- und Gesamtzeit: ohne Klammer
    plain = _archived("wf-ist-gleich", {P1: 15, P2: 30, P3: 60}, ship_status="done",
                      start=datetime(2026, 11, 20, 9, 0))
    out2 = wf.render_plan(plain, archived=True,
                          estimate={"actual": True, "now": datetime(2026, 11, 20, 12, 0)})
    assert _dauer(out2) == "Dauer  1 h 45 min", out2


# =============================================================================
# AC-8: fail-open und Rückfall auf #620
# =============================================================================

def test_fail_open_und_rueckfall(proj, monkeypatch, tmp_path):
    wf = _wf()
    for i in range(3):
        _write_archived(proj, _archived(f"wf-hist-{i}", HIST_PHASES))
    monkeypatch.setattr(wf, "_estimate_now", lambda: NOW)
    created = NOW - timedelta(minutes=90)
    entered = NOW - timedelta(minutes=20)
    base = {"name": "wf-kaputt", "workflow_type": "feature", "current_phase": P6,
            "created": _iso(created), "last_updated": _iso(entered),
            "phase_transitions": [],
            "phase_log": [_seg(P1, created, entered), _seg(P6, entered, None)]}
    reference = wf.current_estimate(dict(base))
    assert isinstance(reference, dict)

    act = _activity_file(proj, "wf-kaputt")
    act.parent.mkdir(parents=True, exist_ok=True)

    # Kaputte bzw. unsinnige Aktivitätsdatei -> Weg aus #620
    for content in ("{kaputt", json.dumps([1, 2]), json.dumps({"phases": {P1: "x"}}),
                    json.dumps({"last": "kaputt", "phases": "nein"})):
        act.write_text(content)
        res = wf.load_activity("wf-kaputt")
        if isinstance(res, dict):
            assert not res.get("phases"), (content, res)
        else:
            assert not res, (content, res)
        est = wf.current_estimate(dict(base))
        assert isinstance(est, dict), content
        assert est["elapsed_min"] == pytest.approx(reference["elapsed_min"], abs=0.01)
        assert est["low_min"] == pytest.approx(reference["low_min"], abs=0.01)

    # note_activity auf kaputter Datei wirft nie
    act.write_text("{kaputt")
    wf.note_activity("wf-kaputt", P6, NOW)
    wf.note_activity("wf-kaputt", P6, "kein-zeitstempel")

    # Ungültige Zeitstempel im Briefing/Übergang -> keine Ausnahme, Weg aus #620
    act.unlink()
    broken_ts = dict(base, po_briefing={"created": "kaputt", "ampel": "red"},
                     phase_transitions=[{"from": P3, "to": P4, "at": "kaputt",
                                         "trigger": "approval"}])
    est = wf.current_estimate(broken_ts)
    assert isinstance(est, dict)
    assert est["elapsed_min"] == pytest.approx(reference["elapsed_min"], abs=0.01)

    # Ungültiges idle_gap_min -> Standard 15
    for bad in ("x", "0", "-5", "true"):
        _set_config(proj, CONFIG_ON + f"  idle_gap_min: {bad}\n")
        name = f"wf-gap-{bad.strip('-')}"
        t0 = datetime(2026, 11, 21, 9, 0)
        wf.note_activity(name, P3, t0)
        wf.note_activity(name, P3, t0 + timedelta(minutes=10))
        assert float(_phases(proj, name)[P3]) == pytest.approx(10.0, abs=0.05), bad
        wf.note_activity(name, P3, t0 + timedelta(minutes=30))
        assert float(_phases(proj, name)[P3]) == pytest.approx(10.0, abs=0.05), bad
        assert wf.current_estimate(dict(base)) is not None, bad
    _set_config(proj, CONFIG_ON)

    # Guard: kaputte Aktivitätsdatei und werfendes note_activity blocken nie
    name = "feat-628-guard"
    ssg, locks, state = _guard_env(monkeypatch, proj, name, P6)
    bad_act = _activity_file(proj, name)
    bad_act.write_text("{kaputt")
    lock = _lock(ssg, locks, "sess-broken", time.time() - 120)
    ssg._heartbeat("sess-broken", str(proj))
    assert json.loads(lock.read_text())["last_seen"] >= time.time() - 5

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(wf, "note_activity", boom)
    lock2 = _lock(ssg, locks, "sess-boom", time.time() - 120)
    ssg._heartbeat("sess-boom", str(proj))
    assert json.loads(lock2.read_text())["last_seen"] >= time.time() - 5

    # CLI plan/estimate mit kaputter Aktivitätsdatei: Rückfall, kein Traceback
    project, env = _case(tmp_path, "cli-kaputt")
    data = dict(base, created=_iso(datetime.now() - timedelta(minutes=90)),
                phase_log=[_seg(P1, datetime.now() - timedelta(minutes=90),
                                datetime.now() - timedelta(minutes=20)),
                           _seg(P6, datetime.now() - timedelta(minutes=20), None)])
    _write_active(project, data)
    cli_act = _activity_file(project, "wf-kaputt")
    cli_act.parent.mkdir(parents=True, exist_ok=True)
    cli_act.write_text("{kaputt")
    plan = _workflow(["plan"], env, project)
    assert plan.returncode == 0 and "Traceback" not in plan.stderr, plan.stderr
    assert [ln.split("  ")[0] for ln in _time_lines(plan.stdout)] == \
        ["Start", "Dauer", "Ende"], plan.stdout
    est = _workflow(["estimate"], env, project)
    assert est.returncode == 0 and "Traceback" not in est.stderr, est.stderr
    assert _kv(est.stdout, "ESTIMATE") == "on", est.stdout

    # Die Tests aus #620 bleiben grün
    res = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          str(REPO_ROOT / "tests" / "test_zeitschaetzung_620.py")],
                         capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300)
    assert res.returncode == 0, res.stdout[-2000:] + res.stderr[-2000:]


# =============================================================================
# Nachschärfung nach Adversary-Runde 1 (F002, F003, F004, F005)
# =============================================================================

def test_laufende_wartezeit_auf_freigabe_zaehlt_nicht(proj, monkeypatch):
    """F002/AC-5: ohne Aktivitätsdatei und ohne Freigabe wartet phase3_spec seit
    6 h auf „approved“: verstrichen ≈ Zeit bis zum Briefing, nicht 6 h mehr."""
    wf = _wf()
    for i in range(3):
        _write_archived(proj, _archived(f"wf-hist-{i}", HIST_PHASES))
    cfg = wf.time_estimate_config()
    history = wf.load_archive_phase_durations(_archive(proj))
    created = NOW - timedelta(minutes=400)
    entered = created + timedelta(minutes=30)
    brief = created + timedelta(minutes=40)       # 6 h vor NOW
    waiting = {"name": "wf-wartet-jetzt", "workflow_type": "feature",
               "current_phase": P3, "created": _iso(created),
               "last_updated": _iso(brief), "phase_transitions": [],
               "phase_log": [_seg(P1, created, created + timedelta(minutes=20)),
                             _seg(P2, created + timedelta(minutes=20), entered),
                             _seg(P3, entered, None)],
               "po_briefing": {"created": brief.isoformat(timespec="seconds"),
                               "ampel": "red", "file": "docs/briefings/x.md"}}
    assert wf.awaiting_human_approval(waiting) is True
    est = wf.estimate_remaining(dict(waiting), history, cfg, NOW)
    assert isinstance(est, dict), est
    assert est["elapsed_min"] == pytest.approx(40.0, abs=0.5), est
    # laufende Phase: 10 min Arbeit -> Rest 20 + 56 = 76, Ende = jetzt + Rest
    assert est["low_min"] == pytest.approx(76.0, abs=0.5), est
    assert _close(est["end_low"], NOW + timedelta(minutes=76)), est["end_low"]
    assert wf._minutes_in_phase(waiting, P3, NOW) == pytest.approx(10.0, abs=0.5)
    monkeypatch.setattr(wf, "_estimate_now", lambda: NOW)
    assert wf.current_estimate(dict(waiting))["elapsed_min"] == \
        pytest.approx(40.0, abs=0.5)

    # Gegenprobe: in phase5 (keine Freigabe offen) zählt die Wanduhr voll
    other = dict(waiting, current_phase=P5,
                 phase_log=waiting["phase_log"][:2] + [_seg(P5, entered, None)])
    assert wf.awaiting_human_approval(other) is False
    est5 = wf.estimate_remaining(other, history, cfg, NOW)
    assert est5["elapsed_min"] == pytest.approx(400.0, abs=0.5), est5


def test_start_setzt_aktivitaet_zurueck(tmp_path):
    """F003: `start <name>` erbt keine Aktivminuten eines früheren Laufs."""
    project, env = _case(tmp_path, "neustart")
    act = _activity_file(project, "wf-neu")
    act.parent.mkdir(parents=True, exist_ok=True)
    act.write_text(json.dumps({"last": "2026-11-01T09:00:00",
                               "phases": {P1: 300.0, P6: 120.0}}))
    res = _workflow(["start", "wf-neu"], env, project)
    assert res.returncode == 0, res.stderr
    assert (_workflows(project) / "wf-neu.json").is_file()
    left = json.loads(act.read_text()).get("phases") if act.exists() else {}
    assert not left, left


def test_note_activity_uhr_rueckwaerts_und_unsinnige_minuten(proj, monkeypatch):
    """F005/F004 (M21): Rücksprung der Uhr schreibt nichts gut; negative und
    nicht-endliche Minuten aus der Datei gehen nie in die Schätzung ein."""
    wf = _wf()
    name = "wf-uhr"
    t0 = datetime(2026, 11, 21, 9, 0)
    wf.note_activity(name, P6, t0)
    wf.note_activity(name, P6, t0 + timedelta(minutes=5))
    wf.note_activity(name, P6, t0 - timedelta(minutes=3))  # Uhr springt zurück
    data = json.loads(_activity_file(proj, name).read_text())
    assert float(data["phases"][P6]) == pytest.approx(5.0, abs=0.05), data
    assert wf._parse_time(data["last"]) == t0 - timedelta(minutes=3), data

    act = _activity_file(proj, "wf-unsinn")
    act.write_text('{"last": "2026-11-21T09:00:00", "phases": {"%s": -50, '
                   '"%s": Infinity, "%s": NaN, "%s": 10}}' % (P1, P2, P5, P6))
    res = wf.load_activity("wf-unsinn")
    assert res["phases"] == {P6: 10.0}, res
    wf.note_activity("wf-unsinn", P6, datetime(2026, 11, 21, 9, 4))
    assert _phases(proj, "wf-unsinn") == {P6: 14.0}

    for i in range(3):
        _write_archived(proj, _archived(f"wf-hist-{i}", HIST_PHASES))
    monkeypatch.setattr(wf, "_estimate_now", lambda: NOW)
    created = NOW - timedelta(minutes=90)
    base = {"name": "wf-unsinn", "workflow_type": "feature", "current_phase": P6,
            "created": _iso(created), "phase_transitions": [],
            "phase_log": [_seg(P1, created, NOW - timedelta(minutes=20)),
                          _seg(P6, NOW - timedelta(minutes=20), None)]}
    est = wf.current_estimate(base)
    assert est["elapsed_min"] == pytest.approx(14.0, abs=0.01), est


def test_ist_block_nutzt_aktivitaet(proj):
    """F004 (M7): fertiger Workflow mit Aktivitätsdatei zeigt deren Minuten."""
    wf = _wf()
    data = _archived("wf-ist-akt", {P1: 60, P3: 60, P6: 60}, ship_status="done",
                     start=datetime(2026, 11, 20, 9, 0),
                     last_updated=_iso(datetime(2026, 11, 20, 12, 40)))
    # offenes Schluss-Segment: mit Aktivitätsdatei kommt keine Wanduhr dazu
    data["phase_log"].append(_seg(P8, datetime(2026, 11, 20, 12, 0), None))
    act = _activity_file(proj, "wf-ist-akt")
    act.parent.mkdir(parents=True, exist_ok=True)
    act.write_text(json.dumps({"last": "2026-11-20T12:00:00",
                               "phases": {P1: 20.0, P3: 15.0, P6: 35.0}}))
    out = wf.render_plan(data, archived=True,
                         estimate={"actual": True, "now": datetime(2026, 11, 20, 13, 0)})
    assert _dauer(out) == "Dauer  1 h 10 min (gesamt 3 h 40 min)", out


def test_guard_schluckt_systemexit(proj, monkeypatch):
    """F004 (M18): ein SystemExit aus note_activity bricht den Guard nie ab."""
    wf = _wf()
    name = "feat-628-exit"
    ssg, locks, _state = _guard_env(monkeypatch, proj, name, P6)

    def leave(*_a, **_k):
        raise SystemExit(2)

    monkeypatch.setattr(wf, "note_activity", leave)
    lock = _lock(ssg, locks, "sess-exit", time.time() - 120)
    ssg._heartbeat("sess-exit", str(proj))
    assert json.loads(lock.read_text())["last_seen"] >= time.time() - 5


# =============================================================================
# AC-9: Archiv-Nachrechnung, 75-%-Grenze unter 2 h
# =============================================================================

_PHASE_CODE = {"1": P1, "2": P2, "3": P3, "4": P4, "5": P5, "6": P6, "6b": P6B,
               "7": P7, "8": P8}

# Minimale Kopien von .claude/workflows/_archive/*.json (Stand 2026-11-21, rechnerlokal
# und gitignored): Name, Status, Start, Briefing (created, ampel), Übergang nach
# phase4_approved (at, trigger), phase_log (Phase, entered, exited, duration_min).
ARCHIVE_FIXTURES = [
    ('feat-522-cloud-plugin-gates', None, '2026-11-09T19:39:15', '2026-11-09T19:39:23', 'green',
     '2026-11-09T19:39:29', 'auto', [
         ('1', '2026-11-09T19:39:15', '2026-11-09T19:39:23', 0.1),
         ('2', '2026-11-09T19:39:23', '2026-11-09T19:39:23', 0.0),
         ('3', '2026-11-09T19:39:23', '2026-11-09T19:39:29', 0.1),
         ('4', '2026-11-09T19:39:29', '2026-11-09T19:39:47', 0.3),
         ('5', '2026-11-09T19:39:47', '2026-11-09T19:39:47', 0.0),
         ('6', '2026-11-09T19:39:47', '2026-11-09T20:16:13', 36.4),
         ('6b', '2026-11-09T20:16:13', '2026-11-09T20:41:23', 25.2),
         ('7', '2026-11-09T20:41:23', '2026-11-09T20:59:46', 18.4),
         ('8', '2026-11-09T20:59:46', None, None),
     ]),
    ('feat-535-token-analyse', None, '2026-11-12T21:02:25', '2026-11-12T21:05:31', 'green',
     '2026-11-12T21:05:31', 'auto', [
         ('1', '2026-11-12T21:02:25', '2026-11-12T21:03:08', 0.7),
         ('2', '2026-11-12T21:03:08', '2026-11-12T21:03:26', 0.3),
         ('3', '2026-11-12T21:03:26', '2026-11-12T21:05:31', 2.1),
         ('4', '2026-11-12T21:05:31', '2026-11-12T21:44:03', 38.5),
         ('5', '2026-11-12T21:44:03', '2026-11-12T21:49:37', 5.6),
         ('6', '2026-11-12T21:49:37', '2026-11-12T22:00:13', 10.6),
         ('6b', '2026-11-12T22:00:13', '2026-11-12T22:01:39', 1.4),
         ('6', '2026-11-12T22:01:39', '2026-11-12T22:03:06', 1.4),
         ('6b', '2026-11-12T22:03:06', '2026-11-12T22:04:19', 1.2),
         ('7', '2026-11-12T22:04:19', '2026-11-12T22:04:37', 0.3),
         ('8', '2026-11-12T22:04:37', None, None),
     ]),
    ('feat-562-cloud-cache-finder', None, '2026-11-09T21:12:22', '2026-11-09T21:47:06', 'red',
     '2026-11-10T05:49:07', 'approval', [
         ('1', '2026-11-09T21:12:22', '2026-11-09T21:31:25', 19.1),
         ('2', '2026-11-09T21:31:25', '2026-11-09T21:34:31', 3.1),
         ('3', '2026-11-09T21:34:31', '2026-11-09T21:47:06', 12.6),
         ('3', '2026-11-09T21:47:06', '2026-11-10T05:49:07', 482.0),
         ('4', '2026-11-10T05:49:07', '2026-11-10T05:50:39', 1.5),
         ('5', '2026-11-10T05:50:39', '2026-11-10T05:56:58', 6.3),
         ('6', '2026-11-10T05:56:58', '2026-11-10T05:57:07', 0.2),
         ('5', '2026-11-10T05:57:07', '2026-11-10T05:57:18', 0.2),
         ('6', '2026-11-10T05:57:18', '2026-11-10T06:22:27', 25.2),
         ('6b', '2026-11-10T06:22:27', '2026-11-10T06:34:08', 11.7),
         ('7', '2026-11-10T06:34:08', '2026-11-10T06:34:27', 0.3),
         ('8', '2026-11-10T06:34:27', None, None),
     ]),
    ('feat-589-naechster-vorschlag', None, '2026-11-12T22:16:30', '2026-11-12T22:23:27', 'red',
     '2026-11-13T06:05:53', 'approval', [
         ('1', '2026-11-12T22:16:30', '2026-11-12T22:19:15', 2.7),
         ('2', '2026-11-12T22:19:15', '2026-11-12T22:21:08', 1.9),
         ('3', '2026-11-12T22:21:08', '2026-11-13T06:05:53', 464.8),
         ('4', '2026-11-13T06:05:53', '2026-11-13T06:06:02', 0.1),
         ('5', '2026-11-13T06:06:02', '2026-11-13T06:13:56', 7.9),
         ('6', '2026-11-13T06:13:56', '2026-11-13T06:31:38', 17.7),
         ('6b', '2026-11-13T06:31:38', '2026-11-13T06:42:27', 10.8),
         ('7', '2026-11-13T06:42:27', '2026-11-13T06:42:27', 0.0),
         ('8', '2026-11-13T06:42:27', None, None),
     ]),
    ('feat-591-spur', None, '2026-11-13T06:51:25', '2026-11-13T06:54:33', 'green',
     '2026-11-13T06:54:34', 'auto', [
         ('1', '2026-11-13T06:51:25', '2026-11-13T06:52:47', 1.4),
         ('2', '2026-11-13T06:52:47', '2026-11-13T06:52:47', 0.0),
         ('3', '2026-11-13T06:52:47', '2026-11-13T06:54:34', 1.8),
         ('4', '2026-11-13T06:54:34', '2026-11-13T06:54:36', 0.0),
         ('5', '2026-11-13T06:54:36', '2026-11-13T07:01:50', 7.2),
         ('6', '2026-11-13T07:01:50', '2026-11-13T07:15:21', 13.5),
         ('6b', '2026-11-13T07:15:21', '2026-11-13T07:29:41', 14.3),
         ('6', '2026-11-13T07:29:41', '2026-11-13T07:32:14', 2.5),
         ('6b', '2026-11-13T07:32:14', '2026-11-13T07:43:59', 11.8),
         ('7', '2026-11-13T07:43:59', '2026-11-13T07:44:00', 0.0),
         ('8', '2026-11-13T07:44:00', None, None),
     ]),
    ('feat-620-zeitschaetzung', None, '2026-11-21T13:06:51', '2026-11-21T13:11:02', 'green',
     '2026-11-21T13:11:02', 'auto', [
         ('1', '2026-11-21T13:06:51', '2026-11-21T13:07:54', 1.1),
         ('2', '2026-11-21T13:07:54', '2026-11-21T13:08:35', 0.7),
         ('3', '2026-11-21T13:08:35', '2026-11-21T13:11:02', 2.5),
         ('4', '2026-11-21T13:11:02', '2026-11-21T13:11:25', 0.4),
         ('5', '2026-11-21T13:11:25', '2026-11-21T13:18:47', 7.4),
         ('6', '2026-11-21T13:18:47', '2026-11-21T14:03:38', 44.9),
         ('6b', '2026-11-21T14:03:38', '2026-11-21T14:07:42', 4.1),
         ('7', '2026-11-21T14:07:42', '2026-11-21T14:08:22', 0.7),
         ('8', '2026-11-21T14:08:22', None, None),
     ]),
    ('feat-622-config-additiv', None, '2026-11-21T14:21:43', '2026-11-21T14:27:19', 'green',
     '2026-11-21T14:27:19', 'auto', [
         ('1', '2026-11-21T14:21:43', '2026-11-21T14:23:51', 2.1),
         ('2', '2026-11-21T14:23:51', '2026-11-21T14:23:51', 0.0),
         ('3', '2026-11-21T14:23:51', '2026-11-21T14:27:19', 3.5),
         ('4', '2026-11-21T14:27:19', '2026-11-21T14:27:48', 0.5),
         ('5', '2026-11-21T14:27:48', '2026-11-21T14:31:05', 3.3),
         ('6', '2026-11-21T14:31:05', '2026-11-21T14:47:25', 16.3),
         ('6b', '2026-11-21T14:47:25', '2026-11-21T15:01:58', 14.6),
         ('7', '2026-11-21T15:01:58', '2026-11-21T15:02:12', 0.2),
         ('8', '2026-11-21T15:02:12', None, None),
     ]),
    ('fix-561-nachpruefung-broken', None, '2026-11-10T07:21:23', '2026-11-10T07:24:03', 'green',
     '2026-11-10T07:24:04', 'auto', [
         ('1', '2026-11-10T07:21:23', '2026-11-10T07:21:48', 0.4),
         ('2', '2026-11-10T07:21:48', '2026-11-10T07:22:09', 0.3),
         ('3', '2026-11-10T07:22:09', '2026-11-10T07:24:04', 1.9),
         ('4', '2026-11-10T07:24:04', '2026-11-10T07:24:18', 0.2),
         ('5', '2026-11-10T07:24:18', '2026-11-10T07:25:36', 1.3),
         ('6', '2026-11-10T07:25:36', '2026-11-10T07:38:33', 12.9),
         ('6b', '2026-11-10T07:38:33', '2026-11-10T07:41:01', 2.5),
         ('7', '2026-11-10T07:41:01', '2026-11-10T07:57:52', 16.8),
         ('8', '2026-11-10T07:57:52', None, None),
     ]),
    ('fix-563-foreign-repo-commit', 'abandoned', '2026-11-10T15:12:00', '2026-11-10T15:15:30',
     'green', '2026-11-10T15:15:30', 'auto', [
         ('1', '2026-11-10T15:12:00', '2026-11-10T15:12:48', 0.8),
         ('2', '2026-11-10T15:12:48', '2026-11-10T15:13:37', 0.8),
         ('3', '2026-11-10T15:13:37', '2026-11-10T15:15:30', 1.9),
         ('4', '2026-11-10T15:15:30', '2026-11-10T15:15:41', 0.2),
         ('5', '2026-11-10T15:15:41', '2026-11-10T15:17:23', 1.7),
         ('6', '2026-11-10T15:17:23', '2026-11-10T15:17:34', 0.2),
         ('5', '2026-11-10T15:17:34', '2026-11-10T15:17:45', 0.2),
         ('6', '2026-11-10T15:17:45', '2026-11-10T15:54:07', 36.4),
         ('6b', '2026-11-10T15:54:07', '2026-11-10T16:01:48', 7.7),
         ('6', '2026-11-10T16:01:48', '2026-11-10T16:17:33', 15.8),
         ('6b', '2026-11-10T16:17:33', '2026-11-10T16:41:45', 24.2),
         ('6', '2026-11-10T16:41:45', None, None),
     ]),
    ('fix-566-plugin-update-sync', None, '2026-11-10T09:40:54', '2026-11-10T09:44:49', 'green',
     '2026-11-10T09:44:49', 'auto', [
         ('1', '2026-11-10T09:40:54', '2026-11-10T09:41:50', 0.9),
         ('2', '2026-11-10T09:41:50', '2026-11-10T09:42:30', 0.7),
         ('3', '2026-11-10T09:42:30', '2026-11-10T09:44:49', 2.3),
         ('4', '2026-11-10T09:44:49', '2026-11-10T12:18:19', 153.5),
         ('5', '2026-11-10T12:18:19', '2026-11-10T12:19:51', 1.5),
         ('6', '2026-11-10T12:19:51', '2026-11-10T12:19:59', 0.1),
         ('5', '2026-11-10T12:19:59', '2026-11-10T12:20:09', 0.2),
         ('6', '2026-11-10T12:20:09', '2026-11-10T12:31:30', 11.4),
         ('6b', '2026-11-10T12:31:30', '2026-11-10T12:36:43', 5.2),
         ('7', '2026-11-10T12:36:43', '2026-11-10T12:37:18', 0.6),
         ('8', '2026-11-10T12:37:18', None, None),
     ]),
    ('fix-572-git-lex-escapes', None, '2026-11-10T18:38:58', '2026-11-10T18:45:47', 'green',
     '2026-11-10T18:45:47', 'auto', [
         ('1', '2026-11-10T18:38:58', '2026-11-10T18:40:42', 1.7),
         ('2', '2026-11-10T18:40:42', '2026-11-10T18:43:45', 3.0),
         ('3', '2026-11-10T18:43:45', '2026-11-10T18:45:47', 2.0),
         ('4', '2026-11-10T18:45:47', '2026-11-10T19:18:21', 32.6),
         ('5', '2026-11-10T19:18:21', '2026-11-10T19:19:49', 1.5),
         ('6', '2026-11-10T19:19:49', '2026-11-10T19:33:23', 13.6),
         ('6b', '2026-11-10T19:33:23', '2026-11-10T19:42:17', 8.9),
         ('6', '2026-11-10T19:42:17', '2026-11-10T19:57:46', 15.5),
         ('6b', '2026-11-10T19:57:46', '2026-11-10T20:00:37', 2.8),
         ('7', '2026-11-10T20:00:37', '2026-11-10T20:16:16', 15.6),
         ('8', '2026-11-10T20:16:16', None, None),
     ]),
]


def _fixture_json(item) -> dict:
    name, status, created, brief, ampel, at, trigger, log = item
    data = {"name": name, "workflow_type": "feature", "created": created,
            "current_phase": _PHASE_CODE[log[-1][0]],
            "po_briefing": {"created": brief, "ampel": ampel},
            "phase_transitions": [{"from": P3, "to": P4, "at": at, "trigger": trigger}],
            "phase_log": [{"phase": _PHASE_CODE[p], "entered_at": e, "exited_at": x,
                           "duration_min": d} for p, e, x, d in log]}
    if status:
        data["status"] = status
    return data


def _q(values: list, q: float) -> float:
    values = sorted(values)
    pos = (len(values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def test_archiv_nachrechnung_75_prozent_unter_zwei_stunden(proj):
    wf = _wf()
    archive = _archive(proj)
    assert len(ARCHIVE_FIXTURES) == 11
    for item in ARCHIVE_FIXTURES:
        (archive / f"{item[0]}.json").write_text(json.dumps(_fixture_json(item)))

    history = wf.load_archive_phase_durations(archive)
    totals = [sum(float(v) for v in h["phases"].values())
              for h in history if h.get("type") == "feature"]
    assert len(totals) == 10, totals  # fix-563 abgebrochen, zählt nicht
    # Die beiden über Nacht wartenden Specs zählen nur noch ihre Arbeitszeit
    assert max(totals) < 200, sorted(totals)
    q75 = _q(totals, 0.75)
    assert q75 < 120, (q75, sorted(totals))
