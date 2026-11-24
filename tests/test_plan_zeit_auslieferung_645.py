"""Plan-Pane: Zeitblock während der Auslieferung (Issue #645).

Der Ist-Block (`render_plan(..., estimate={"actual": True, ...})`) fror bisher
beim Eintritt in `phase8_complete` ein, obwohl die Auslieferung
(`ship_status` open/running/failed) noch lief. Soll (Spec
docs/specs/fix-645-plan-zeit-auslieferung.md):

- laufende Auslieferung: `Start  HH:MM`, `Ausliefern  seit HH:MM (<Dauer>)`,
  `Ende  offen`, keine `Dauer  `-Zeile;
- Auslieferungsbeginn = `entered_at` des letzten `phase8_complete`-Eintrags,
  sonst das Ende aus `_finished_span` (nie `ship_at`);
- `done`/`skipped` mit gültigem `ship_at`: Ende = `ship_at`, Dauer bis dahin;
- Altbestand (ohne `ship_status`, ohne/unlesbares `ship_at`) unverändert;
- fail-open, `_finished_span` und Retro-Zeile unverändert;
- Anzeigezone (#637) und Umbruch bei `width` (#642).

Uhrzeiten sind naiv-lokal (Anzeigezone None), damit das Ergebnis nicht von
der Systemzone abhängt; nur AC-6 nutzt eine IANA-Zone mit tz-bewussten
Zeitstempeln.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

P1 = "phase1_context"
P6 = "phase6_implement"
P7 = "phase7_validate"
P8 = "phase8_complete"

DAY = "2026-11-24"
NOW = datetime(2026, 11, 24, 12, 30)
TIME_PREFIXES = ("Start  ", "Dauer  ", "Ende  ", "Ausliefern  ")


# --- Helpers ---------------------------------------------------------------

def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _t(hhmm: str) -> str:
    return f"{DAY}T{hhmm}:00"


def _entry(phase: str, entered: str, exited: "str | None") -> dict:
    dur = None
    if exited is not None:
        dur = (datetime.fromisoformat(_t(exited))
               - datetime.fromisoformat(_t(entered))).total_seconds() / 60
    return {"phase": phase, "entered_at": _t(entered),
            "exited_at": _t(exited) if exited else None, "duration_min": dur}


def _time_lines(text: str) -> list:
    return [ln for ln in text.splitlines() if ln.startswith(TIME_PREFIXES)]


def _actual(now: datetime = NOW, zone=None) -> dict:
    est = {"actual": True, "now": now}
    if zone is not None:
        est["display_tz"] = zone
    return est


def _shipping(name: str, **fields) -> dict:
    """Workflow in Phase 8: Start 08:07, Phase-8-Eintritt 08:57, offen.

    `last_updated` 09:03 entspricht dem Bild aus dem Issue („Ende 09:03“).
    """
    data = {
        "name": name, "workflow_type": "feature", "current_phase": P8,
        "status": "active", "created": _t("08:07"), "last_updated": _t("09:03"),
        "phase_transitions": [],
        "phase_log": [
            _entry(P1, "08:07", "08:20"),
            _entry(P6, "08:20", "08:50"),
            _entry(P7, "08:50", "08:57"),
            _entry(P8, "08:57", None),
        ],
    }
    data.update(fields)
    return data


@pytest.fixture
def no_activity(monkeypatch):
    """Keine Aktivitäts-/Archivdaten: „Dauer“ = Gesamtzeit (#628-Logik)."""
    wf = _wf()
    monkeypatch.setattr(wf, "_activity_phases", lambda name: {})
    monkeypatch.setattr(wf, "_archive_phase_entry", lambda data: None)
    return wf


# =============================================================================
# AC-1: laufende Auslieferung -> „Ausliefern  seit“ und „Ende  offen“
# =============================================================================

@pytest.mark.parametrize("ship_status", ["open", "running", "failed"])
def test_laufende_auslieferung_zeigt_seit_und_ende_offen(no_activity, ship_status):
    wf = no_activity
    data = _shipping(f"t645-laufend-{ship_status}", ship_status=ship_status,
                     ship_at=_t("09:00"))
    out = wf.render_plan(data, estimate=_actual())
    lines = _time_lines(out)
    assert lines == ["Start  08:07",
                     f"Ausliefern  seit 08:57 ({wf.format_duration(213)})",
                     "Ende  offen"], out
    assert not any(ln.startswith("Dauer  ") for ln in out.splitlines()), out
    assert "Ende  09:03" not in out, out


# =============================================================================
# AC-2: Beginn = letzter phase8-Eintrag, nicht ship_at; sonst _finished_span
# =============================================================================

def test_auslieferungsbeginn_aus_phase_log_nicht_ship_at(no_activity):
    wf = no_activity
    # Zweimal in Phase 8, dazwischen zurück nach Phase 6; ship_at nach mehrfachem running
    data = _shipping("t645-zweimal-p8", ship_status="running", ship_at=_t("11:55"),
                     last_updated=_t("11:55"))
    data["phase_log"] = [
        _entry(P1, "08:07", "08:20"),
        _entry(P8, "08:30", "08:40"),
        _entry(P6, "08:40", "09:00"),
        _entry(P7, "09:00", "09:10"),
        _entry(P8, "09:10", None),
    ]
    out = wf.render_plan(data, estimate=_actual())
    lines = _time_lines(out)
    assert lines == ["Start  08:07",
                     f"Ausliefern  seit 09:10 ({wf.format_duration(200)})",
                     "Ende  offen"], out
    assert not any("11:55" in ln for ln in lines), out

    # Kein phase8-Eintrag im Log: Beginn = Ende aus _finished_span (09:20)
    fallback = _shipping("t645-ohne-p8", ship_status="running", ship_at=_t("11:55"),
                         last_updated=_t("11:55"))
    fallback["phase_log"] = [
        _entry(P1, "08:07", "08:20"),
        _entry(P6, "08:20", "09:00"),
        _entry(P7, "09:00", "09:20"),
    ]
    span = wf._finished_span(fallback)
    assert span is not None and span[1] == datetime(2026, 11, 24, 9, 20), span
    out = wf.render_plan(fallback, estimate=_actual())
    assert _time_lines(out) == ["Start  08:07",
                                f"Ausliefern  seit 09:20 ({wf.format_duration(190)})",
                                "Ende  offen"], out


# =============================================================================
# AC-3: done/skipped mit gültigem ship_at -> Ende = ship_at, Dauer bis dahin
# =============================================================================

@pytest.mark.parametrize("ship_status", ["done", "skipped"])
def test_abgeschlossene_auslieferung_ende_ist_ship_at(no_activity, ship_status):
    wf = no_activity
    data = _shipping(f"t645-fertig-{ship_status}", ship_status=ship_status,
                     ship_at=_t("11:40"))
    out = wf.render_plan(data, estimate=_actual())
    assert _time_lines(out) == ["Start  08:07",
                                f"Dauer  {wf.format_duration(213)}",
                                "Ende  11:40"], out
    # Schrittliste zeigt bei skipped legitim „○ Ausliefern  (entfällt)“ (#612)
    assert "Ausliefern  seit" not in out and "Ende  offen" not in out, out


# =============================================================================
# AC-4: Altbestand unverändert
# =============================================================================

@pytest.mark.parametrize("fields", [
    {},                                          # ohne ship_status
    {"ship_status": "done"},                     # done ohne ship_at
    {"ship_status": "skipped"},                  # skipped ohne ship_at
    {"ship_status": "done", "ship_at": "kaputt"},  # unlesbares ship_at
    {"ship_status": "skipped", "ship_at": None},
], ids=["ohne-ship-status", "done-ohne-ship-at", "skipped-ohne-ship-at",
        "done-ship-at-kaputt", "skipped-ship-at-none"])
def test_altbestand_ohne_ship_at_unveraendert(no_activity, fields):
    wf = no_activity
    data = _shipping("t645-altbestand", **fields)
    span = wf._finished_span(data)
    assert span is not None, data
    start, end = span
    assert end == datetime(2026, 11, 24, 9, 3), span  # last_updated wie bisher
    total = max(0.0, (end - start).total_seconds() / 60)
    out = wf.render_plan(data, estimate=_actual())
    assert _time_lines(out) == [f"Start  {start:%H:%M}",
                                f"Dauer  {wf.format_duration(total)}",
                                f"Ende  {end:%H:%M}"], out
    assert _time_lines(out) == ["Start  08:07", "Dauer  56 min", "Ende  09:03"], out

    # Zeitblock identisch zum selben Workflow ohne jedes ship_*-Feld
    # (die Schrittliste darüber hängt legitim vom Auslieferungsstand ab)
    plain = _shipping("t645-altbestand")
    assert _time_lines(out) == _time_lines(wf.render_plan(plain, estimate=_actual()))
    assert wf._plan_time_lines(data, _actual()) == wf._plan_time_lines(plain, _actual())


# =============================================================================
# AC-5: fail-open, _finished_span und Retro-Zeile unverändert
# =============================================================================

def test_fail_open_und_finished_span_unveraendert(no_activity):
    wf = no_activity
    broken_cases = [
        _shipping("t645-abgebrochen", ship_status="running", status="abandoned"),
        _shipping("t645-log-kaputt", ship_status="running", phase_log="kaputt",
                  last_updated=None),
        {k: v for k, v in _shipping("t645-ohne-created", ship_status="running").items()
         if k != "created"},
        {k: v for k, v in _shipping("t645-ohne-zeit", ship_status="done",
                                    ship_at=_t("11:40")).items()
         if k not in ("created", "last_updated")},
    ]
    for data in broken_cases:
        assert wf._plan_time_lines(data, _actual()) == [], data
        out = wf.render_plan(data, estimate=_actual())
        assert _time_lines(out) == [], out

    # _finished_span misst weiter bis Phase 8, egal welcher Auslieferungsstand
    expected = (datetime(2026, 11, 24, 8, 7), datetime(2026, 11, 24, 9, 3))
    base = _shipping("t645-span")
    assert wf._finished_span(base) == expected
    for status in ("open", "running", "failed", "done", "skipped"):
        variant = _shipping("t645-span", ship_status=status, ship_at=_t("11:40"))
        assert wf._finished_span(variant) == expected, status

    # Retro-Zeile „Schätzung vs. Ist“ unverändert
    init = {"estimate_initial": {"low": 30, "high": 90}}
    retro_plain = wf._retro_estimate_line(_shipping("t645-retro", **init))
    retro_ship = wf._retro_estimate_line(
        _shipping("t645-retro", ship_status="running", ship_at=_t("11:55"), **init))
    assert retro_plain is not None and "tatsächlich 56 min" in retro_plain, retro_plain
    assert retro_ship == retro_plain


# =============================================================================
# AC-6: Anzeigezone (#637) und Umbruch bei width=34 (#642)
# =============================================================================

def test_ausliefern_zeile_anzeigezone_und_umbruch(no_activity):
    wf = no_activity
    data = _shipping("t645-zone", ship_status="running",
                     created="2026-11-24T07:07:00+00:00",
                     last_updated="2026-11-24T08:03:00+00:00",
                     ship_at="2026-11-24T10:55:00+00:00")
    data["phase_log"] = [
        {"phase": P1, "entered_at": "2026-11-24T07:07:00+00:00",
         "exited_at": "2026-11-24T07:20:00+00:00", "duration_min": 13},
        {"phase": P7, "entered_at": "2026-11-24T07:20:00+00:00",
         "exited_at": "2026-11-24T07:57:00+00:00", "duration_min": 37},
        {"phase": P8, "entered_at": "2026-11-24T07:57:00+00:00",
         "exited_at": None, "duration_min": None},
    ]
    # jetzt = 11:30 UTC (12:30 Berlin), als naive Ortszeit wie die übrigen Uhren
    now = datetime(2026, 11, 24, 11, 30, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    est = _actual(now=now, zone="Europe/Berlin")

    wide = wf.render_plan(data, estimate=dict(est))
    assert _time_lines(wide) == ["Start  08:07",
                                 f"Ausliefern  seit 08:57 ({wf.format_duration(213)})",
                                 "Ende  offen"], wide

    out = wf.render_plan(data, width=34, estimate=dict(est))
    lines = out.splitlines()
    assert all(len(ln) <= 34 for ln in lines), [ln for ln in lines if len(ln) > 34]
    assert "Ausliefern  seit 08:57" in out, out
    joined = " ".join(ln.strip() for ln in lines)
    assert f"Ausliefern  seit 08:57 ({wf.format_duration(213)})" in joined, out
    assert "Ende  offen" in lines, out
