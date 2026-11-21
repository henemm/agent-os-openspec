"""Anzeige-Zeitzone der Zeitschätzung (Issue #637, Befund 1).

Spec: docs/specs/fast/fix-637-anzeige-zeitzone.md (AC-1 bis AC-4).
Der Prozess läuft in der Systemzone UTC (`TZ=UTC` + `time.tzset()`), die
Anzeige soll in `time_estimate.display_timezone` erfolgen (Standard
`Europe/Berlin`, `local` = Systemzone, Ungültiges = Systemzone).

#642: Eine Ende-Spanne gibt es nur mit sauberer Vergleichsgruppe (Archiv plus
Aktivitätsdatei, `_write_history`); sie ist in der Anzeigezone auf
Viertelstunden gerundet.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
BERLIN = ZoneInfo("Europe/Berlin")

CONFIG_BASE = """time_estimate:
  enabled: true
  min_samples: 3
  quantiles: [0.25, 0.75]
  defaults:
    feature: [60, 240]
    feature-fast: [20, 60]
"""

# Start 16:46 (Systemzeit = UTC), jetzt 17:00 UTC, beides im November (CET = UTC+1)
START = datetime(2026, 11, 21, 16, 46)
NOW = datetime(2026, 11, 21, 17, 0)


def _config(zone=None) -> str:
    return CONFIG_BASE + (f"  display_timezone: {zone}\n" if zone is not None else "")


def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _reset_config_cache():
    sys.path.insert(0, str(HOOKS_DIR))
    import config_loader  # noqa: PLC0415
    for fn in (config_loader.find_project_root, config_loader.load_config):
        clear = getattr(fn, "cache_clear", None)
        if clear:
            clear()


def _project(root: Path, config: str) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_archive").mkdir(parents=True)
    (proj / "_home").mkdir()
    (proj / "openspec.yaml").write_text(config)
    return proj


@pytest.fixture
def utc_proc(tmp_path, monkeypatch):
    """Prozess in Systemzone UTC, eigenes tmp-Projekt; danach alles zurück."""
    for k in list(os.environ):
        if k.startswith(("OPENSPEC_", "HERDR_", "GH_")):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    root = tmp_path / "inproc"
    root.mkdir()
    proj = _project(root, _config())
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.setenv("HOME", str(proj / "_home"))
    monkeypatch.chdir(proj)
    _reset_config_cache()
    yield proj
    monkeypatch.undo()
    time.tzset()
    _reset_config_cache()


def _write_history(proj: Path) -> None:
    """Drei saubere Archiv-Workflows (#642): Restarbeit ab phase6 (seit 5 min)
    45, 75, 105 min -> Quantile 0.25/0.75 = 60/90 min, also eine echte Spanne."""
    act_dir = proj / ".claude" / "workflows" / "_activity"
    act_dir.mkdir(parents=True, exist_ok=True)
    for i, p6 in enumerate((30, 60, 90)):
        name = f"zone-hist-{i}"
        phases = {"phase1_context": 10.0, "phase6_implement": float(p6),
                  "phase7_validate": 20.0}
        archived = {"name": name, "workflow_type": "feature",
                    "current_phase": "phase8_complete", "created": "2026-11-01T09:00:00",
                    "phase_transitions": [], "phase_log": []}
        (proj / ".claude" / "workflows" / "_archive" / f"{name}.json").write_text(
            json.dumps(archived))
        (act_dir / f"{name}.json").write_text(json.dumps(
            {"last": "2026-11-01T18:00:00", "phases": phases}))


def _set_config(proj: Path, text: str) -> None:
    (proj / "openspec.yaml").write_text(text)
    _reset_config_cache()


def _state(created, now=NOW) -> dict:
    created_iso = created if isinstance(created, str) else created.isoformat()
    entered = now - timedelta(minutes=5)
    return {"name": "zone-637", "workflow_type": "feature", "current_phase": "phase6_implement",
            "created": created_iso, "last_updated": entered.isoformat(),
            "phase_transitions": [],
            "phase_log": [{"phase": "phase1_context", "entered_at": created_iso,
                           "exited_at": entered.isoformat(), "duration_min": 9.0},
                          {"phase": "phase6_implement", "entered_at": entered.isoformat(),
                           "exited_at": None, "duration_min": None}]}


def _render(wf, monkeypatch, data, now=NOW) -> list:
    monkeypatch.setattr(wf, "_estimate_now", lambda: now)
    est = wf.current_estimate(dict(data))
    assert isinstance(est, dict), est
    return wf.render_plan(data, estimate=est).splitlines()


def _start_line(lines: list) -> str:
    return next(ln for ln in lines if ln.startswith("Start  "))


# =============================================================================
# AC-1: Standard Europe/Berlin
# =============================================================================

def test_ac1_default_shows_german_time(utc_proc, monkeypatch):
    wf = _wf()
    assert datetime(2026, 11, 21, 12, 0).astimezone().utcoffset() == timedelta(0)
    lines = _render(wf, monkeypatch, _state(START))
    assert _start_line(lines) == "Start  17:46", lines


def test_ac1_aware_timestamp_converted(utc_proc, monkeypatch):
    wf = _wf()
    lines = _render(wf, monkeypatch, _state("2026-11-21T16:46:00+00:00"))
    assert _start_line(lines) == "Start  17:46", lines


def test_ac1_end_in_german_time(utc_proc, monkeypatch):
    wf = _wf()
    _write_history(utc_proc)
    monkeypatch.setattr(wf, "_estimate_now", lambda: NOW)
    est = wf.current_estimate(_state(START))
    lines = wf.render_plan(_state(START), estimate=est)
    end_low = (est["end_low"].replace(tzinfo=timezone.utc).astimezone(BERLIN))
    end_line = next(ln for ln in lines.splitlines() if ln.startswith("Ende  "))
    assert end_line.startswith(f"Ende  ca. {end_low:%H:%M}–"), end_line
    assert end_line == "Ende  ca. 19:00–19:30", end_line  # #642: 18:00/18:30 UTC


def test_ac1_today_is_decided_in_display_zone(utc_proc, monkeypatch):
    """23:30 UTC am 21.11. ist 00:30 am 22.11. in Berlin; jetzt 00:10 UTC am
    22.11. = 01:10 Berlin, also derselbe Tag -> ohne Datum."""
    wf = _wf()
    now = datetime(2026, 11, 22, 0, 10)
    lines = _render(wf, monkeypatch, _state(datetime(2026, 11, 21, 23, 30), now=now), now=now)
    assert _start_line(lines) == "Start  00:30", lines


def test_ac1_stored_timestamps_unchanged(utc_proc, monkeypatch):
    wf = _wf()
    data = _state(START)
    monkeypatch.setattr(wf, "_estimate_now", lambda: NOW)
    est = wf.current_estimate(dict(data))
    assert est["start"] == START
    assert est["now"] == NOW
    assert data["created"] == START.isoformat()


# =============================================================================
# AC-2: local = Systemzone wie bisher
# =============================================================================

def test_ac2_local_keeps_system_time(utc_proc, monkeypatch):
    wf = _wf()
    _set_config(utc_proc, _config("local"))
    lines = _render(wf, monkeypatch, _state(START))
    assert _start_line(lines) == "Start  16:46", lines


# =============================================================================
# AC-3: ungültiger Name -> Systemzone, keine Ausnahme
# =============================================================================

@pytest.mark.parametrize("zone", ["Mond/Rueckseite", "'../../etc/passwd'", "''"])
def test_ac3_invalid_zone_falls_back_to_system(utc_proc, monkeypatch, zone):
    wf = _wf()
    _set_config(utc_proc, _config(zone))
    lines = _render(wf, monkeypatch, _state(START))
    assert _start_line(lines) == "Start  16:46", lines


def test_ac3_non_string_zone_uses_default(utc_proc, monkeypatch):
    wf = _wf()
    _set_config(utc_proc, _config("5"))
    cfg = wf.time_estimate_config()
    assert cfg is not None and cfg["display_timezone"] == "Europe/Berlin", cfg
    lines = _render(wf, monkeypatch, _state(START))
    assert _start_line(lines) == "Start  17:46", lines


def test_ac3_default_config_value(utc_proc):
    wf = _wf()
    assert wf.TIME_ESTIMATE_DEFAULTS["display_timezone"] == "Europe/Berlin"
    assert wf.time_estimate_config()["display_timezone"] == "Europe/Berlin"


# =============================================================================
# CLI `estimate` (AC-3, AC-4) im Unterprozess mit TZ=UTC
# =============================================================================

def _case(tmp_path: Path, label: str, config: str):
    root = tmp_path / label
    root.mkdir()
    proj = _project(root, config)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "GH_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["TZ"] = "UTC"
    return proj, env


def _estimate_cli(tmp_path, label, config):
    proj, env = _case(tmp_path, label, config)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None, second=0, microsecond=0)
    created = now_utc - timedelta(minutes=60)
    data = _state(created, now=now_utc)
    _write_history(proj)  # #642: ohne saubere Vergleichsgruppe keine Ende-Spanne
    (proj / ".claude" / "workflows" / f"{data['name']}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(data["name"])
    res = subprocess.run([sys.executable, str(WORKFLOW_PY), "estimate"], capture_output=True,
                         text=True, env=env, cwd=str(proj), timeout=30)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    kv = dict(ln.split("=", 1) for ln in res.stdout.splitlines() if "=" in ln)
    assert kv.get("ESTIMATE") == "on", res.stdout
    return kv, created


def test_ac4_estimate_cli_in_german_time(tmp_path):
    kv, created = _estimate_cli(tmp_path, "de", _config())
    start_be = created.replace(tzinfo=timezone.utc).astimezone(BERLIN)
    start = datetime.fromisoformat(kv["ESTIMATE_START"])
    assert start.tzinfo is not None, kv["ESTIMATE_START"]
    assert start.utcoffset() == start_be.utcoffset(), kv["ESTIMATE_START"]
    assert start.strftime("%H:%M") == start_be.strftime("%H:%M"), kv["ESTIMATE_START"]
    now_be = datetime.now(BERLIN)
    for key in ("ESTIMATE_END_LOW", "ESTIMATE_END_HIGH"):
        end = datetime.fromisoformat(kv[key])
        assert end.tzinfo is not None, (key, kv[key])
        assert end.utcoffset() == end.astimezone(BERLIN).utcoffset(), (key, kv[key])
        assert end.minute % 15 == 0, (key, kv[key])  # #642: Viertelstunde
    end_low = datetime.fromisoformat(kv["ESTIMATE_END_LOW"])
    clock = (end_low.strftime("%H:%M") if end_low.date() == now_be.date()
             else end_low.strftime("%d.%m. %H:%M"))
    assert f"Ende ca. {clock}–" in kv["LINE"], kv["LINE"]


def test_ac3_estimate_cli_invalid_zone_falls_back(tmp_path):
    kv, created = _estimate_cli(tmp_path, "bad", _config("Mond/Rueckseite"))
    assert kv["ESTIMATE_START"] == created.isoformat(timespec="minutes"), kv
