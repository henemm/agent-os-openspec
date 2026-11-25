"""Plan-Seitenleiste: grober Countdown der verbleibenden Zeit (Issue #655).

Spec: docs/specs/feat-655-countdown.md (AC-1 bis AC-12; AC-13 ist der
Regressionslauf der bestehenden Zeit-Tests).

Der Zeit-Block bekommt unter der Mittelzeile eine Zeile „Noch …“:
- nach der Freigabe eine Spanne aus `end_low`/`end_high` minus `now`
  (L auf 5 Minuten ab-, H auf 5 Minuten aufgerundet; ab H5 >= 120 Stunden in
  halben Stunden mit deutschem Komma; L5 <= 0 < H „bis ca.“; H <= 0 keine Zeile)
- vor der Freigabe „Noch  ca. N Min bis Freigabe“ (kaufmännisch auf 5 gerundet,
  mindestens 5; Freigabe erreicht: keine Zeile)
- keine Zeile bei „wartet auf dich“, „Ende  offen“, ohne Vergleichsdaten, im
  Ist-Block und bei abgebrochenem Workflow.

Alle Tests rufen `_plan_time_lines` / `render_plan` pure mit handgebauten
Schätzungs-Wörterbüchern und festem `now` auf; keine Wanduhr. Der Chat-Test
(AC-12) setzt `_estimate_now` auf eine feste Zeit wie die bestehenden
Zeit-Tests (#642, #637).
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

P3 = "phase3_spec"
P6 = "phase6_implement"
P8 = "phase8_complete"

CONFIG = """time_estimate:
  enabled: true
  min_samples: 3
  quantiles: [0.25, 0.75]
  display_timezone: local
"""
DAY = (2026, 11, 25)
NOW = datetime(*DAY, 10, 0, 0)
START = datetime(*DAY, 9, 46, 0)
COUNTDOWN = "Noch  "


# --- Helpers ---------------------------------------------------------------

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


@pytest.fixture(autouse=True)
def proj(tmp_path, monkeypatch):
    """Jeder Test läuft in einem eigenen tmp-Projekt, nie im echten Archiv."""
    for k in list(os.environ):
        if k.startswith(("OPENSPEC_", "HERDR_", "GH_")):
            monkeypatch.delenv(k, raising=False)
    project = tmp_path / "proj"
    (project / ".git").mkdir(parents=True)
    for sub in ("_log", "_archive", "_activity"):
        (project / ".claude" / "workflows" / sub).mkdir(parents=True)
    (project / "_home").mkdir()
    (project / "openspec.yaml").write_text(CONFIG)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.setenv("HOME", str(project / "_home"))
    monkeypatch.chdir(project)
    _reset_config_cache()
    yield project
    monkeypatch.undo()
    _reset_config_cache()


def _t(hhmm: str, sec: int = 0) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(*DAY, h, m, sec)


def _data(phase: str = P6, **fields) -> dict:
    data = {"name": "feat-655-test", "workflow_type": "feature",
            "current_phase": phase, "status": "active",
            "created": START.isoformat(), "last_updated": START.isoformat(),
            "phase_transitions": [], "phase_log": []}
    data.update(fields)
    return data


def _after(end_low, end_high, now=NOW, n=3, zone="local") -> dict:
    """Schätzung nach der Freigabe (Form wie `estimate_remaining`)."""
    return {"n": n, "source": "archive" if n else "none", "start": START, "now": now,
            "elapsed_min": 14.0, "approval": None, "end_low": end_low,
            "end_high": end_high, "hit_rate": None, "low_min": 30.0, "mid_min": 50.0,
            "high_min": 75.0, "total_low_min": 44.0, "total_high_min": 89.0,
            "display_tz": zone}


def _before(approval, now=NOW, n=3, zone="local") -> dict:
    """Schätzung vor der Freigabe: nur `approval`, keine Ende-Spanne."""
    return {"n": n, "source": "archive" if n else "none", "start": START, "now": now,
            "elapsed_min": 14.0, "approval": approval, "end_low": None,
            "end_high": None, "hit_rate": None, "low_min": 90.0, "mid_min": 120.0,
            "high_min": 150.0, "total_low_min": 104.0, "total_high_min": 164.0,
            "display_tz": zone}


def _countdown(lines) -> list:
    return [ln for ln in lines if ln.startswith(COUNTDOWN)]


def _one_countdown(lines) -> "str | None":
    found = _countdown(lines)
    assert len(found) <= 1, lines
    return found[0] if found else None


def _after_lines(end_low, end_high, now=NOW) -> list:
    wf = _wf()
    return wf._plan_time_lines(_data(P6), _after(_t(end_low), _t(end_high), now=now))


def _before_lines(approval, now=NOW) -> list:
    wf = _wf()
    return wf._plan_time_lines(_data(P3), _before(_t(approval), now=now))


# =============================================================================
# AC-1: Spanne nach der Freigabe, 5-Minuten-Rundung nach außen
# =============================================================================

@pytest.mark.parametrize("now, end_low, end_high, expected", [
    (NOW, "10:30", "11:15", "Noch  ca. 30–75 Min"),
    (_t("10:07"), "10:30", "11:15", "Noch  ca. 20–70 Min"),   # 23 -> 20, 68 -> 70
    (NOW, "10:45", "10:45", "Noch  ca. 45 Min"),
    (_t("10:02"), "10:30", "11:00", "Noch  ca. 25–60 Min"),   # 28 -> 25, 58 -> 60
    (_t("10:03"), "10:45", "10:45", "Noch  ca. 40–45 Min"),   # 42 -> 40, 42 -> 45
])
def test_spanne_nach_freigabe_rundet_5_min_ab_und_auf(now, end_low, end_high, expected):
    lines = _after_lines(end_low, end_high, now=now)
    assert _one_countdown(lines) == expected, lines
    # Steht direkt unter der Ende-Zeile
    idx = lines.index(expected)
    assert lines[idx - 1].startswith("Ende  ca. "), lines


# =============================================================================
# AC-2: ab H5 >= 120 Minuten Stunden in halben Stunden mit deutschem Komma
# =============================================================================

@pytest.mark.parametrize("end_low, end_high, expected", [
    ("11:00", "13:30", "Noch  ca. 1–3,5 h"),     # L 60, H 210
    ("12:00", "12:00", "Noch  ca. 2 h"),         # L = H = 120: eine Zahl, kein „2,0“
    ("11:40", "12:15", "Noch  ca. 1,5–2,5 h"),   # L 100 -> 1,5; H 135 -> 2,5
    ("10:15", "13:00", "Noch  ca. 0,5–3 h"),     # L 15 -> max(0,5; 0); ganze Stunde ohne Komma
    ("11:00", "11:55", "Noch  ca. 60–115 Min"),  # Grenze: H5 = 115 < 120 bleibt Minuten
])
def test_ab_120_min_stunden_mit_halben_und_komma(end_low, end_high, expected):
    lines = _after_lines(end_low, end_high)
    assert _one_countdown(lines) == expected, lines
    assert ",0" not in expected


# =============================================================================
# AC-3: Untergrenze erreicht/überschritten, Obergrenze in der Zukunft -> „bis ca.“
# =============================================================================

@pytest.mark.parametrize("end_low, end_high, expected", [
    ("10:00", "10:45", "Noch  bis ca. 45 Min"),   # L = 0
    ("09:45", "10:15", "Noch  bis ca. 15 Min"),   # L < 0
    ("09:30", "12:00", "Noch  bis ca. 2 h"),      # ab 120 Min in Stunden
    ("10:00", "12:30", "Noch  bis ca. 2,5 h"),
])
def test_untergrenze_erreicht_zeigt_bis_ca(end_low, end_high, expected):
    lines = _after_lines(end_low, end_high)
    assert _one_countdown(lines) == expected, lines


# =============================================================================
# AC-4: Obergrenze nicht mehr in der Zukunft -> keine Zeile, Ende-Zeile bleibt
# =============================================================================

@pytest.mark.parametrize("end_low, end_high", [
    ("09:00", "09:45"),
    ("09:30", "10:00"),   # H = 0
])
def test_obergrenze_ueberschritten_keine_zeile(end_low, end_high):
    lines = _after_lines(end_low, end_high)
    assert _countdown(lines) == [], lines
    assert f"Ende  ca. {end_low}–{end_high}" in lines, lines
    assert not any("-" in ln and "Min" in ln for ln in lines), lines


# =============================================================================
# AC-5: vor der Freigabe „Noch  ca. N Min bis Freigabe“, N auf 5 gerundet, >= 5
# =============================================================================

@pytest.mark.parametrize("now, approval, expected", [
    (NOW, "10:45", "Noch  ca. 45 Min bis Freigabe"),
    (NOW, "10:02", "Noch  ca. 5 Min bis Freigabe"),      # 2 -> 0 -> mindestens 5
    (_t("10:08"), "10:30", "Noch  ca. 20 Min bis Freigabe"),   # 22 -> 20
    (_t("10:07", 30), "10:30", "Noch  ca. 25 Min bis Freigabe"),  # 22,5 -> 25 (kaufmännisch)
    (_t("10:07"), "10:30", "Noch  ca. 25 Min bis Freigabe"),   # 23 -> 25
    (NOW, "12:00", "Noch  ca. 120 Min bis Freigabe"),
])
def test_vor_freigabe_countdown_bis_freigabe_mind_5(now, approval, expected):
    lines = _before_lines(approval, now=now)
    assert _one_countdown(lines) == expected, lines
    idx = lines.index(expected)
    assert lines[idx - 1].startswith("Freigabe  ca. "), lines


# =============================================================================
# AC-6: Freigabezeitpunkt jetzt oder vorbei -> keine Zeile
# =============================================================================

@pytest.mark.parametrize("approval", ["09:45", "10:00"])
def test_freigabe_erreicht_keine_zeile(approval):
    lines = _before_lines(approval)
    assert _countdown(lines) == [], lines
    assert f"Freigabe  ca. {approval}" in lines, lines


# =============================================================================
# AC-7: „wartet auf dich“, „Ende  offen“, ohne Vergleichsdaten -> keine Zeile
# =============================================================================

def test_wartet_ende_offen_und_ohne_daten_keine_zeile():
    wf = _wf()
    # (a) Freigabe wartet auf den PO (phase3 mit registriertem Briefing, rote Ampel)
    waiting = _data(P3, po_briefing={"created": START.isoformat(), "ampel": "red",
                                     "file": "docs/briefings/feat-655-test.md"})
    lines = wf._plan_time_lines(waiting, _before(_t("10:45")))
    assert "Freigabe  wartet auf dich" in lines, lines
    assert _countdown(lines) == [], lines

    # (b) Ohne Vergleichsdaten (n = 0) nach der Freigabe: „Ende  offen“
    no_data = {"n": 0, "source": "none", "start": START, "now": NOW, "elapsed_min": 14.0,
               "approval": None, "end_low": None, "end_high": None, "hit_rate": None,
               "display_tz": "local"}
    lines = wf._plan_time_lines(_data(P6), no_data)
    assert "Ende  offen" in lines, lines
    assert _countdown(lines) == [], lines

    # (c) n = 0, obwohl Zeitpunkte gesetzt sind: weiterhin keine Zeile
    for est, data in ((_after(_t("10:30"), _t("11:15"), n=0), _data(P6)),
                      (_before(_t("10:45"), n=0), _data(P3))):
        lines = wf._plan_time_lines(data, est)
        assert "Ende  offen" in lines, lines
        assert _countdown(lines) == [], lines


# =============================================================================
# AC-8: Ist-Block (fertig, in Auslieferung) und abgebrochen -> keine Zeile
# =============================================================================

def _finished(**fields) -> dict:
    log = [{"phase": "phase1_context", "entered_at": _t("08:00").isoformat(),
            "exited_at": _t("08:30").isoformat(), "duration_min": 30.0},
           {"phase": P6, "entered_at": _t("08:30").isoformat(),
            "exited_at": _t("09:20").isoformat(), "duration_min": 50.0},
           {"phase": P8, "entered_at": _t("09:20").isoformat(),
            "exited_at": _t("09:30").isoformat(), "duration_min": 10.0}]
    data = {"name": "feat-655-ist", "workflow_type": "feature", "current_phase": P8,
            "status": "active", "created": _t("08:00").isoformat(),
            "last_updated": _t("09:30").isoformat(), "phase_transitions": [],
            "phase_log": log}
    data.update(fields)
    return data


def test_ist_block_und_abbruch_ohne_countdown():
    wf = _wf()
    actual = {"actual": True, "now": NOW, "display_tz": "local"}

    done = wf._plan_time_lines(_finished(ship_status="done", ship_at=_t("09:30").isoformat()),
                               dict(actual))
    assert done == ["", "Start  08:00", "Dauer  1 h 30 min", "Ende  09:30"], done
    assert _countdown(done) == []

    shipping = wf._plan_time_lines(
        _finished(ship_status="running", ship_at=_t("09:25").isoformat()), dict(actual))
    assert shipping == ["", "Start  08:00", "Ausliefern  seit 09:20 (40 min)",
                        "Ende  offen"], shipping
    assert _countdown(shipping) == []

    # Abgebrochen: kein Zeit-Block, auch mit einer Schätzung, die sonst zählte
    aborted_after = wf._plan_time_lines(_data(P6, status="abandoned"),
                                        _after(_t("10:30"), _t("11:15")))
    aborted_before = wf._plan_time_lines(_data(P3, status="abandoned"),
                                         _before(_t("10:45")))
    assert aborted_after == [] and aborted_before == [], (aborted_after, aborted_before)


# =============================================================================
# AC-9: Countdown unter der Mittelzeile, Basiszeile bleibt letzte Zeile
# =============================================================================

def test_basiszeile_bleibt_letzte_zeile():
    wf = _wf()
    after = wf._plan_time_lines(_data(P6), _after(_t("10:30"), _t("11:15")))
    assert after == ["", "Start  09:46", "Ende  ca. 10:30–11:15", "Noch  ca. 30–75 Min",
                     wf.TIME_INDENT + "aus 3 Workflows"], after

    before = wf._plan_time_lines(_data(P3), _before(_t("10:45")))
    assert before == ["", "Start  09:46", "Freigabe  ca. 10:45",
                      "Noch  ca. 45 Min bis Freigabe",
                      wf.TIME_INDENT + "aus 3 Workflows"], before

    # Im gerenderten Plan: Basiszeile direkt nach der Countdown-Zeile, danach Leerzeile
    out = wf.render_plan(_data(P6), estimate=_after(_t("10:30"), _t("11:15"))).splitlines()
    idx = out.index("Noch  ca. 30–75 Min")
    assert out[idx - 1] == "Ende  ca. 10:30–11:15", out
    assert out[idx + 1] == wf.TIME_INDENT + "aus 3 Workflows", out
    assert out[idx + 2] == "", out


# =============================================================================
# AC-10: schmaler Pane (Breite 34): keine abgeschnittene Zahl, keine Zeile > 34
# =============================================================================

@pytest.mark.parametrize("phase, est, expected", [
    (P6, _after(_t("10:30"), _t("11:15")), "Noch  ca. 30–75 Min"),
    (P6, _after(_t("11:40"), _t("12:15")), "Noch  ca. 1,5–2,5 h"),
    (P6, _after(_t("09:30"), _t("12:00")), "Noch  bis ca. 2 h"),
    (P3, _before(_t("12:00")), "Noch  ca. 120 Min bis Freigabe"),
])
def test_schmaler_pane_breite_34_ohne_abgeschnittene_zahl(phase, est, expected):
    wf = _wf()
    out = wf.render_plan(_data(phase), width=34, estimate=dict(est))
    lines = out.splitlines()
    assert all(len(ln) <= 34 for ln in lines), out
    # Unter 34 Zeichen: die Zeile steht vollständig, Zahl und Einheit ungeteilt
    assert len(expected) <= 34
    assert expected in lines, out

    # Noch schmaler (#643): Umbruch am Wortende, die Zahl bleibt unzerschnitten
    narrow = wf.render_plan(_data(phase), width=20, estimate=dict(est)).splitlines()
    assert all(len(ln) <= 20 for ln in narrow), narrow
    number = re.search(r"\d+(?:,\d)?(?:–\d+(?:,\d)?)?", expected).group(0)
    assert any(number in ln for ln in narrow), (number, narrow)


# =============================================================================
# AC-11: Anzeigezone ändert die Countdown-Minuten nicht
# =============================================================================

@pytest.fixture
def utc_proc(monkeypatch):
    """Systemzone UTC, damit naive Zeiten in jeder Anzeigezone eindeutig sind."""
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_anzeigezone_aendert_countdown_minuten_nicht(utc_proc):
    wf = _wf()
    zones = ("local", "UTC", "Europe/Berlin", "Asia/Kolkata", "America/New_York")
    after, ends, before, approvals = set(), set(), set(), set()
    for zone in zones:
        lines = wf._plan_time_lines(_data(P6), _after(_t("10:30"), _t("11:15"), zone=zone))
        after.add(_one_countdown(lines))
        ends.add(next(ln for ln in lines if ln.startswith("Ende  ")))
        lines = wf._plan_time_lines(_data(P3), _before(_t("10:45"), zone=zone))
        before.add(_one_countdown(lines))
        approvals.add(next(ln for ln in lines if ln.startswith("Freigabe  ")))
    assert after == {"Noch  ca. 30–75 Min"}, after
    assert before == {"Noch  ca. 45 Min bis Freigabe"}, before
    # Die Uhrzeiten der anderen Zeilen folgen der Anzeigezone
    assert len(ends) > 1 and len(approvals) > 1, (ends, approvals)
    assert "Ende  ca. 11:30–12:15" in ends, ends   # Europe/Berlin = UTC+1


# =============================================================================
# AC-12: Chat-Ausgabe `workflow.py estimate` unverändert
# =============================================================================

def _write_history(project: Path) -> None:
    """Drei saubere Archiv-Workflows wie #637: Rest ab phase6 45/75/105 min,
    Quantile 0.25/0.75 -> 60/90 min."""
    wfs = project / ".claude" / "workflows"
    for i, p6 in enumerate((30, 60, 90)):
        name = f"cd-hist-{i}"
        archived = {"name": name, "workflow_type": "feature", "current_phase": P8,
                    "created": "2026-11-01T09:00:00", "phase_transitions": [],
                    "phase_log": []}
        (wfs / "_archive" / f"{name}.json").write_text(json.dumps(archived))
        (wfs / "_activity" / f"{name}.json").write_text(json.dumps(
            {"last": "2026-11-01T18:00:00",
             "phases": {"phase1_context": 10.0, P6: float(p6), "phase7_validate": 20.0}}))


def test_chat_ausgabe_estimate_unveraendert(proj, monkeypatch, capsys):
    wf = _wf()
    # (1) `_estimate_kv_lines` mit handgebauter Schätzung: Wortlaut wie vor #655
    after = wf._estimate_kv_lines(_after(_t("10:30"), _t("11:15")))
    assert after == ["ESTIMATE=on", "ESTIMATE_LOW_MIN=44", "ESTIMATE_HIGH_MIN=89",
                     "ESTIMATE_START=2026-11-25T09:46",
                     "ESTIMATE_END_LOW=2026-11-25T10:30",
                     "ESTIMATE_END_HIGH=2026-11-25T11:15", "ESTIMATE_BASIS=3",
                     "LINE=Ende ca. 10:30–11:15 (aus 3 Workflows)"], after

    before = wf._estimate_kv_lines(_before(_t("10:45")))
    assert before == ["ESTIMATE=on", "ESTIMATE_START=2026-11-25T09:46",
                      "ESTIMATE_APPROVAL=2026-11-25T10:45", "ESTIMATE_BASIS=3",
                      "LINE=Start 09:46, Freigabe ca. 10:45 (aus 3 Workflows)"], before

    waiting = wf._estimate_kv_lines(_before(_t("10:45")), waiting=True)
    assert waiting[-1] == "LINE=Start 09:46, Freigabe wartet auf dich (aus 3 Workflows)", \
        waiting

    for out in (after, before, waiting):
        assert not any("Noch" in ln for ln in out), out

    # (2) `cmd_estimate` des aktiven Workflows mit fester Uhr
    _write_history(proj)
    data = _data(P6, last_updated=(NOW - timedelta(minutes=5)).isoformat(),
                 phase_log=[{"phase": "phase1_context", "entered_at": START.isoformat(),
                             "exited_at": (NOW - timedelta(minutes=5)).isoformat(),
                             "duration_min": 9.0},
                            {"phase": P6, "entered_at": (NOW - timedelta(minutes=5)).isoformat(),
                             "exited_at": None, "duration_min": None}])
    (proj / ".claude" / "workflows" / f"{data['name']}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(data["name"])
    monkeypatch.setattr(wf, "_estimate_now", lambda: NOW)
    _reset_config_cache()
    wf.cmd_estimate([])
    printed = capsys.readouterr().out.splitlines()
    assert printed == ["ESTIMATE=on", "ESTIMATE_LOW_MIN=74", "ESTIMATE_HIGH_MIN=104",
                       "ESTIMATE_START=2026-11-25T09:46",
                       "ESTIMATE_END_LOW=2026-11-25T11:00",
                       "ESTIMATE_END_HIGH=2026-11-25T11:30", "ESTIMATE_BASIS=3",
                       "LINE=Ende ca. 11:00–11:30 (aus 3 Workflows)"], printed
    assert not any("Noch" in ln for ln in printed), printed
