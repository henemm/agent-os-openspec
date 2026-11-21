"""Zeitschätzung für Workflows (Issue #620): Intake-Schätzung und Plan-Pane.

Spec: docs/specs/feat-620-zeitschaetzung.md (AC-1 bis AC-12).

Verträge, die diese Tests festlegen (die Spec lässt sie offen, der Test entscheidet):

- `load_archive_phase_durations(archive_dir=None)` liest `<archive_dir>/*.json`
  (ohne Argument `_archive_dir()`) und liefert eine Liste von Dicts
  `{"type": <workflow_type>, "tier": "0"|"1-3"|"4-6"|None, "phases": {phase: minuten}}`
  — ein Eintrag je zählendem Archiv-Workflow. `tier` ist None, wenn der
  Archiv-Workflow kein `intake_score` hat (Altbestand).
- `estimate_remaining(data, history, config, now)`: `history` hat genau diese Form,
  `config` ist der Abschnitt `time_estimate` als Dict
  (`enabled`, `min_samples`, `quantiles`, `defaults`), `now` ein naives `datetime`.
  `start`, `end_low`, `end_high` dürfen `datetime` oder ISO-String sein.
  `elapsed_min` = `now - created`; verstrichen in der aktuellen Phase = `now -
  entered_at` des offenen `phase_log`-Eintrags der aktuellen Phase.
- Startwerte: der laufende Plan-Schritt zählt als offen (zu Beginn gilt also der
  volle Startwert, z.B. feature [60, 240]).
- `render_plan(..., estimate=est)` zeigt den Block nur mit `estimate`; bei
  abgeschlossenen/archivierten Workflows ersetzt der tatsächliche Block die Prognose.
- `plan --watch` lädt das Archiv über `workflow.load_archive_phase_durations`
  (Modul-Attribut, damit patchbar) und rechnet je Runde mit `datetime.now()` des
  Moduls `workflow` neu (`workflow.estimate_remaining`).

Neue Funktionen werden erst im Testkörper angesprochen: Fehlendes erscheint als
Test-FAIL, nicht als Collection-Error.
"""

import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"

CFG = {"enabled": True, "min_samples": 3, "quantiles": [0.25, 0.75],
       "defaults": {"feature": [60, 240], "feature-fast": [20, 60]}}
ON_CFG = ("time_estimate:\n  enabled: true\n  min_samples: 3\n"
          "  quantiles: [0.25, 0.75]\n"
          "  defaults:\n    feature: [60, 240]\n    feature-fast: [20, 60]\n")
KILL_CFG = "time_estimate:\n  enabled: false\n"
BAD_CFG = "time_estimate:\n  enabled: true\n  quantiles: kaputt\n  min_samples: x\n"
NOW = datetime(2026, 11, 21, 12, 0, 0)
WF = "zeit-test"
TIME_PREFIXES = ("Start  ", "Dauer  ", "Ende  ")

GH_STUB = r"""#!/bin/bash
printf '%s\n' "$*" >> "$GH_LOG"
exit 0
"""


# --- Helpers ---------------------------------------------------------------

def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _hist(phases: dict, wtype: str = "feature", tier=None) -> dict:
    return {"type": wtype, "tier": tier, "phases": dict(phases)}


def _entry(phase: str, entered: datetime, minutes=None) -> dict:
    if minutes is None:
        return {"phase": phase, "entered_at": entered.isoformat(),
                "exited_at": None, "duration_min": None}
    exited = entered + timedelta(minutes=minutes)
    return {"phase": phase, "entered_at": entered.isoformat(),
            "exited_at": exited.isoformat(), "duration_min": float(minutes)}


def _state(phase: str, now: datetime = NOW, wtype: str = "feature",
           created_ago: float = 0, phase_ago: float = 0, **fields) -> dict:
    created = now - timedelta(minutes=created_ago)
    data = {"name": WF, "workflow_type": wtype, "current_phase": phase,
            "created": created.isoformat(), "phase_transitions": [],
            "phase_log": [_entry(phase, now - timedelta(minutes=phase_ago))]}
    data.update(fields)
    return data


def _archived(name: str, phases: "list[tuple[str, float]]", wtype: str = "feature",
              score=None, start: datetime = datetime(2026, 11, 1, 9, 0), **fields) -> dict:
    log, t = [], start
    for phase, minutes in phases:
        log.append(_entry(phase, t, minutes))
        t += timedelta(minutes=minutes)
    data = {"name": name, "workflow_type": wtype, "current_phase": "phase8_complete",
            "created": start.isoformat(), "status": "completed", "phase_log": log,
            "phase_transitions": []}
    if score is not None:
        data["intake_score"] = score
    data.update(fields)
    return data


def _lines(text: str) -> "list[str]":
    return text.splitlines()


def _time_lines(text: str) -> "list[str]":
    return [ln for ln in _lines(text) if ln.startswith(TIME_PREFIXES)]


def _kv(stdout: str, key: str) -> "str | None":
    for line in stdout.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _project(root: Path, config: "str | None" = ON_CFG) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_archive").mkdir(parents=True)
    (proj / "_home").mkdir()
    if config is not None:
        (proj / ".claude" / "config.yaml").write_text(config)
    return proj


def _case(tmp_path: Path, label: str, config: "str | None" = ON_CFG, **extra):
    root = tmp_path / label
    root.mkdir()
    proj = _project(root, config)
    bindir = root / "bin"
    bindir.mkdir()
    stub = bindir / "gh"
    stub.write_text(GH_STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "GH_"))
           and k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PLUGIN_ROOT")}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["GH_LOG"] = str(root / "gh.log")
    env["PATH"] = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"
    env.update(extra)
    return proj, env


def _archive_dir(proj: Path) -> Path:
    return proj / ".claude" / "workflows" / "_archive"


def _write_active(proj: Path, data: dict) -> None:
    (proj / ".claude" / "workflows" / f"{data['name']}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(data["name"])


def _write_archived(proj: Path, data: dict) -> Path:
    path = _archive_dir(proj) / f"{data['name']}.json"
    path.write_text(json.dumps(data))
    return path


def _three_archived(proj: Path) -> None:
    for i, extra in enumerate((0, 20, 40)):
        _write_archived(proj, _archived(f"alt-{i}", [
            ("phase1_context", 10), ("phase2_analyse", 10), ("phase3_spec", 20),
            ("phase4_approved", 5), ("phase5_tdd_red", 15),
            ("phase6_implement", 30 + extra), ("phase6b_adversary", 10),
            ("phase7_validate", 10)]))


def _workflow(args, env, cwd, timeout: float = 60):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args], capture_output=True,
                          text=True, env=env, cwd=str(cwd), timeout=timeout)


def _read_state(proj: Path, name: str) -> dict:
    return json.loads((proj / ".claude" / "workflows" / f"{name}.json").read_text())


# =============================================================================
# AC-1: Archiv-Dauern laden
# =============================================================================

def test_ac1_load_archive_skips_abandoned_empty_broken_and_sums_reentries(tmp_path):
    """AC-1: GIVEN Archiv mit abgebrochenem, leerem, kaputtem Workflow und Wiedereintritt
    WHEN load_archive_phase_durations läuft
    THEN zählen nur gültige, Wiedereintritte je Phase werden summiert, kein Fehler."""
    wf = _wf()
    archive = tmp_path / "_archive"
    archive.mkdir()
    ok = _archived("ok", [("phase1_context", 10), ("phase2_analyse", 20),
                          ("phase3_spec", 5), ("phase6_implement", 15),
                          ("phase6b_adversary", 5), ("phase6_implement", 7)], score=5)
    ok["phase_log"].append(_entry("phase8_complete", datetime(2026, 11, 1, 12, 0)))
    abandoned = _archived("weg", [("phase1_context", 99)], status="abandoned")
    empty = _archived("leer", [])
    empty["phase_log"] = [_entry("phase1_context", datetime(2026, 11, 1, 9, 0))]
    legacy = _archived("alt", [("phase3_spec", 4), ("phase6_implement", 8)],
                       wtype="feature-fast")
    for data in (ok, abandoned, empty, legacy):
        (archive / f"{data['name']}.json").write_text(json.dumps(data))
    (archive / "kaputt.json").write_text("{kaputt")

    history = wf.load_archive_phase_durations(archive)

    assert len(history) == 2, history
    by_type = {h["type"]: h for h in history}
    feat = by_type["feature"]
    assert feat["tier"] == "4-6"
    assert feat["phases"]["phase6_implement"] == pytest.approx(22.0)  # 15 + 7
    assert feat["phases"]["phase1_context"] == pytest.approx(10.0)
    assert feat["phases"].get("phase8_complete", 0) == 0  # offener Eintrag zählt nicht
    fast = by_type["feature-fast"]
    assert fast["tier"] is None  # Altbestand ohne intake_score
    assert fast["phases"]["phase6_implement"] == pytest.approx(8.0)


def test_ac1_score_tiers_and_missing_dir(tmp_path):
    """AC-1: GIVEN Scores 0, 3, 4 bzw. kein Archivordner WHEN geladen
    THEN Stufen "0", "1-3", "4-6"; fehlender Ordner ergibt leere Liste."""
    wf = _wf()
    archive = tmp_path / "_archive"
    archive.mkdir()
    for score in (0, 3, 4):
        data = _archived(f"s{score}", [("phase1_context", 5)], score=score)
        (archive / f"s{score}.json").write_text(json.dumps(data))
    tiers = sorted(h["tier"] for h in wf.load_archive_phase_durations(archive))
    assert tiers == ["0", "1-3", "4-6"]
    assert wf.load_archive_phase_durations(tmp_path / "fehlt") == []


# =============================================================================
# AC-2: Restdauer, Quantile, Median, Ende
# =============================================================================

def test_ac2_estimate_remaining_exact_values():
    """AC-2: GIVEN feste Historie, Phase 6 mit 10 min verstrichen, 100 min seit Start
    WHEN estimate_remaining(..., now) läuft
    THEN Rest je Workflow = max(0, Phase - verstrichen) + spätere Phasen,
    Quantile 0.25/0.75 und Median linear interpoliert, Ende = now + Spanne."""
    wf = _wf()
    history = [
        # Rest: 20 + 10 + 20 = 50
        _hist({"phase1_context": 100, "phase6_implement": 30, "phase6b_adversary": 10,
               "phase7_validate": 20}),
        # Rest: max(0, 5 - 10) = 0 + 20 + 15 = 35
        _hist({"phase6_implement": 5, "phase6b_adversary": 20, "phase7_validate": 15}),
        # Rest: 50 + 0 (kein Adversary) + 30 = 80
        _hist({"phase3_spec": 40, "phase6_implement": 60, "phase7_validate": 30}),
        # Rest: 10 + 0 + 10 + 5 = 25
        _hist({"phase6_implement": 20, "phase6b_adversary": 0, "phase7_validate": 10,
               "phase8_complete": 5}),
    ]
    data = _state("phase6_implement", created_ago=100, phase_ago=10)

    est = wf.estimate_remaining(data, history, CFG, NOW)

    # sortiert 25, 35, 50, 80 -> q25 = 32.5, Median = 42.5, q75 = 57.5
    assert est["low_min"] == pytest.approx(32.5)
    assert est["mid_min"] == pytest.approx(42.5)
    assert est["high_min"] == pytest.approx(57.5)
    assert est["elapsed_min"] == pytest.approx(100.0)
    assert est["total_low_min"] == pytest.approx(132.5)
    assert est["total_high_min"] == pytest.approx(157.5)
    assert est["n"] == 4
    assert est["source"] == "archive"
    assert _dt(est["start"]) == NOW - timedelta(minutes=100)
    assert _dt(est["end_low"]) == NOW + timedelta(minutes=32.5)
    assert _dt(est["end_high"]) == NOW + timedelta(minutes=57.5)


def test_ac2_fast_track_uses_plan_steps_fast():
    """AC-2: GIVEN Fast Track in Phase 3 WHEN geschätzt wird
    THEN zählen nur Phasen aus PLAN_STEPS_FAST (kein TDD-RED, kein Adversary)."""
    wf = _wf()
    phases = {"phase3_spec": 10, "phase4_approved": 5, "phase5_tdd_red": 100,
              "phase6_implement": 20, "phase6b_adversary": 100, "phase7_validate": 5}
    history = [_hist(phases, wtype="feature-fast") for _ in range(3)]
    data = _state("phase3_spec", wtype="feature-fast", created_ago=4, phase_ago=4)

    est = wf.estimate_remaining(data, history, CFG, NOW)

    # (10 - 4) + 5 + 20 + 5 = 36 für alle drei
    assert est["low_min"] == pytest.approx(36.0)
    assert est["mid_min"] == pytest.approx(36.0)
    assert est["high_min"] == pytest.approx(36.0)
    assert est["total_low_min"] == pytest.approx(40.0)


def test_ac2_configured_quantiles_are_used():
    """AC-2: GIVEN quantiles [0.0, 1.0] WHEN geschätzt wird THEN Spanne = Min..Max."""
    wf = _wf()
    history = [_hist({"phase7_validate": m}) for m in (10, 20, 30, 70)]
    cfg = dict(CFG, quantiles=[0.0, 1.0])
    est = wf.estimate_remaining(_state("phase7_validate"), history, cfg, NOW)
    assert est["low_min"] == pytest.approx(10.0)
    assert est["high_min"] == pytest.approx(70.0)
    assert est["mid_min"] == pytest.approx(25.0)


# =============================================================================
# AC-3: wird präziser, lernt
# =============================================================================

def _varied_history() -> list:
    rows = [(10, 20, 30, 40, 10, 60, 15, 20), (30, 60, 10, 200, 20, 30, 40, 10),
            (5, 10, 60, 30, 5, 90, 10, 30), (20, 40, 20, 120, 15, 45, 25, 15),
            (15, 15, 45, 10, 30, 20, 5, 25)]
    names = ("phase1_context", "phase2_analyse", "phase3_spec", "phase4_approved",
             "phase5_tdd_red", "phase6_implement", "phase6b_adversary", "phase7_validate")
    return [_hist(dict(zip(names, row))) for row in rows]


def test_ac3_span_narrows_in_later_phase_and_archive_learns():
    """AC-3: GIVEN dieselbe Historie WHEN in Phase 3 und in Phase 7 geschätzt wird
    THEN ist die Spanne in Phase 7 nicht weiter; ein zusätzlicher Archiv-Workflow
    ändert das Ergebnis."""
    wf = _wf()
    history = _varied_history()
    early = wf.estimate_remaining(_state("phase3_spec"), history, CFG, NOW)
    late = wf.estimate_remaining(_state("phase7_validate"), history, CFG, NOW)
    assert late["high_min"] - late["low_min"] <= early["high_min"] - early["low_min"]
    assert late["high_min"] < early["high_min"]

    more = history + [_hist({"phase3_spec": 300, "phase4_approved": 300,
                             "phase6_implement": 300, "phase7_validate": 300})]
    learned = wf.estimate_remaining(_state("phase3_spec"), more, CFG, NOW)
    assert learned["n"] == early["n"] + 1
    assert (learned["low_min"], learned["mid_min"], learned["high_min"]) != \
        (early["low_min"], early["mid_min"], early["high_min"])


# =============================================================================
# AC-4: Vergleichsgruppe Stufe -> Typ -> Startwerte
# =============================================================================

def test_ac4_group_tier_then_type_then_defaults():
    """AC-4: GIVEN genug Workflows gleicher Stufe / nur genug gleichen Typs / zu wenige
    WHEN geschätzt wird THEN greifen Stufe, Typ bzw. skalierte Startwerte."""
    wf = _wf()
    tier_hi = [_hist({"phase7_validate": 10}, tier="4-6") for _ in range(3)]
    legacy = [_hist({"phase7_validate": 100}, tier=None) for _ in range(3)]
    tier_lo = [_hist({"phase7_validate": 50}, tier="1-3")]
    other_type = [_hist({"phase7_validate": 999}, wtype="feature-fast") for _ in range(5)]
    history = tier_hi + legacy + tier_lo + other_type

    # Stufe "4-6" hat 3 (= min_samples): nur diese
    est = wf.estimate_remaining(_state("phase7_validate", intake_score=5), history, CFG, NOW)
    assert est["n"] == 3 and est["source"] == "archive"
    assert est["mid_min"] == pytest.approx(10.0)

    # Stufe "1-3" hat nur 1: alle des Typs feature (3 + 3 + 1 = 7), nie feature-fast
    est = wf.estimate_remaining(_state("phase7_validate", intake_score=2), history, CFG, NOW)
    assert est["n"] == 7 and est["source"] == "archive"
    assert est["high_min"] < 999

    # ohne intake_score: Typ-Gruppe
    est = wf.estimate_remaining(_state("phase7_validate"), history, CFG, NOW)
    assert est["n"] == 7

    # Score 0 -> Stufe "0"
    zero = [_hist({"phase7_validate": 3}, tier="0") for _ in range(3)]
    est = wf.estimate_remaining(_state("phase7_validate", intake_score=0),
                                zero + legacy, CFG, NOW)
    assert est["n"] == 3 and est["mid_min"] == pytest.approx(3.0)


def test_ac4_defaults_scaled_by_open_steps():
    """AC-4: GIVEN weniger als min_samples Workflows des Typs WHEN geschätzt wird
    THEN Startwerte aus defaults, skaliert mit dem Anteil offener Plan-Schritte,
    source == "default", n == 0."""
    wf = _wf()
    history = [_hist({"phase7_validate": 10}) for _ in range(2)] + \
        [_hist({"phase7_validate": 10}, wtype="feature-fast") for _ in range(5)]

    start = wf.estimate_remaining(_state("phase1_context"), history, CFG, NOW)
    assert start["source"] == "default" and start["n"] == 0
    assert start["low_min"] == pytest.approx(60.0)   # 9 von 9 Schritten offen
    assert start["high_min"] == pytest.approx(240.0)
    assert start["low_min"] <= start["mid_min"] <= start["high_min"]

    late = wf.estimate_remaining(_state("phase7_validate"), history, CFG, NOW)
    assert late["source"] == "default" and late["n"] == 0
    assert late["low_min"] == pytest.approx(60.0 * 2 / 9)   # 7 und 8 offen
    assert late["high_min"] == pytest.approx(240.0 * 2 / 9)

    fast = wf.estimate_remaining(_state("phase3_spec", wtype="feature-fast"), [], CFG, NOW)
    assert fast["source"] == "default"
    assert fast["low_min"] == pytest.approx(20.0)
    assert fast["high_min"] == pytest.approx(60.0)

    # min_samples aus der Konfiguration: 2 genügen dann
    est = wf.estimate_remaining(_state("phase7_validate"), history,
                                dict(CFG, min_samples=2), NOW)
    assert est["source"] == "archive" and est["n"] == 2


# =============================================================================
# AC-5: Zeit-Block im Plan
# =============================================================================

def _today(hour: int, minute: int) -> datetime:
    return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)


def _est(start: datetime, low: float, high: float, end_low: datetime, end_high: datetime,
         n: int = 7, source: str = "archive") -> dict:
    return {"low_min": low / 2, "mid_min": (low + high) / 4, "high_min": high / 2,
            "elapsed_min": low / 2, "total_low_min": low, "total_high_min": high,
            "n": n, "source": source, "start": start.isoformat(),
            "end_low": end_low.isoformat(), "end_high": end_high.isoformat()}


def test_ac5_render_plan_time_block_exact():
    """AC-5: GIVEN Schätzungs-Dict WHEN render_plan(..., estimate=est)
    THEN nach der Schrittliste genau Start / Dauer ca. / Ende ca., vor der Schlusszeile."""
    wf = _wf()
    start = _today(9, 5)
    data = _state("phase5_tdd_red", now=start + timedelta(minutes=30))
    data["created"] = start.isoformat()
    est = _est(start, 70, 150, _today(15, 40), _today(17, 0))

    out = wf.render_plan(data, estimate=est)
    lines = _lines(out)

    block = ["Start  09:05", "Dauer  ca. 1 h 10 min–2 h 30 min (aus 7 Workflows)",
             "Ende  ca. 15:40–17:00"]
    assert _time_lines(out) == block, out
    i = lines.index(block[0])
    assert lines[i:i + 3] == block, out
    last_step = max(j for j, ln in enumerate(lines) if ln[:1] in ("✔", "▶", "○", "✘"))
    assert i > last_step, out
    assert i + 2 < len(lines) - 1, out  # Schlusszeile bleibt die letzte
    assert lines[-1] == _lines(wf.render_plan(data))[-1]


def test_ac5_default_label_minutes_full_hours_and_dates():
    """AC-5: GIVEN Startwert-Schätzung, Start gestern, Ende morgen
    WHEN render_plan THEN "(Startwert)", "45 min", "2 h" und Datum DD.MM. bei fremdem Tag."""
    wf = _wf()
    yesterday = _today(22, 15) - timedelta(days=1)
    tomorrow = _today(1, 15) + timedelta(days=1)
    data = _state("phase3_spec", now=_today(10, 0))
    data["created"] = yesterday.isoformat()
    est = _est(yesterday, 45, 120, _today(23, 30), tomorrow, n=0, source="default")

    out = wf.render_plan(data, estimate=est)

    assert _time_lines(out) == [
        f"Start  {yesterday:%d.%m.} 22:15",
        "Dauer  ca. 45 min–2 h (Startwert)",
        f"Ende  ca. 23:30–{tomorrow:%d.%m.} 01:15",
    ], out


def test_ac5_without_estimate_output_unchanged():
    """AC-5: GIVEN kein estimate WHEN render_plan THEN byte-gleich wie bisher, keine Zeit-Zeilen."""
    wf = _wf()
    for phase in ("phase1_context", "phase6_implement", "phase8_complete"):
        data = _state(phase)
        plain = wf.render_plan(data)
        assert wf.render_plan(data, estimate=None) == plain
        assert _time_lines(plain) == []
        assert wf.render_plan(data, width=40, estimate=None) == wf.render_plan(data, width=40)


# =============================================================================
# AC-6: abgeschlossene und archivierte Workflows
# =============================================================================

def test_ac6_finished_workflows_show_actual_times():
    """AC-6: GIVEN archivierter bzw. Phase-8-Workflow WHEN render_plan mit Zeitdaten
    THEN tatsächliches Start, Ende, Dauer ohne "ca." und ohne Prognose."""
    wf = _wf()
    start = _today(8, 0)
    est = _est(start, 33, 77, _today(19, 11), _today(20, 22))

    archived = _archived(WF, [("phase1_context", 60), ("phase7_validate", 90)],
                         start=start, ship_status="done")
    out = wf.render_plan(archived, archived=True, estimate=est)
    times = _time_lines(out)
    assert sorted(times) == sorted(["Start  08:00", "Ende  10:30", "Dauer  2 h 30 min"]), out
    assert not any("ca." in ln for ln in times), out
    assert "19:11" not in out and "20:22" not in out and "Workflows" not in out

    phase8 = _archived(WF, [("phase1_context", 45)], start=start, ship_status="done")
    phase8["phase_log"].append(_entry("phase8_complete", start + timedelta(minutes=45)))
    phase8["updated"] = phase8["last_updated"] = (start + timedelta(minutes=45)).isoformat()
    out = wf.render_plan(phase8, estimate=est)
    times = _time_lines(out)
    assert sorted(times) == sorted(["Start  08:00", "Ende  08:45", "Dauer  45 min"]), out


def test_ac6_abandoned_and_missing_timestamps_no_block():
    """AC-6: GIVEN abgebrochener Workflow bzw. fehlende Zeitstempel WHEN render_plan
    THEN kein Zeit-Block."""
    wf = _wf()
    start = _today(8, 0)
    est = _est(start, 33, 77, _today(19, 11), _today(20, 22))
    abandoned = _archived(WF, [("phase1_context", 60)], start=start, status="abandoned")
    assert _time_lines(wf.render_plan(abandoned, archived=True, estimate=est)) == []

    bare = {"name": WF, "workflow_type": "feature", "current_phase": "phase8_complete",
            "phase_log": [], "phase_transitions": []}
    assert _time_lines(wf.render_plan(bare, archived=True, estimate=est)) == []


# =============================================================================
# AC-7: plan --watch mit Cache
# =============================================================================

def test_ac7_watch_caches_archive_and_recomputes_each_round(tmp_path, monkeypatch, capsys):
    """AC-7: GIVEN plan --watch über drei Runden WHEN das Archiv zwei Runden gleich bleibt
    und dann geändert wird THEN zwei Ladevorgänge, Schätzung je Runde mit neuem now."""
    wf = _wf()
    proj = _project(tmp_path)
    _three_archived(proj)
    real_now = datetime.now()
    # Phase 5 läuft schon 60 min (Archiv: 15 min) -> überzogen, Ende = now + spätere Phasen,
    # rückt also mit der Uhr nach
    data = _state("phase5_tdd_red", now=real_now, created_ago=90, phase_ago=60)
    _write_active(proj, data)
    for key in list(os.environ):
        if key.startswith(("OPENSPEC_", "HERDR_")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.setenv("HOME", str(proj / "_home"))
    monkeypatch.setenv("OPENSPEC_PLAN_WATCH_ROUNDS", "3")
    monkeypatch.setenv("OPENSPEC_PLAN_WATCH_INTERVAL", "0")
    monkeypatch.chdir(proj)
    sys.path.insert(0, str(HOOKS_DIR))
    import config_loader  # noqa: PLC0415
    for fn in (config_loader.load_config, config_loader.find_project_root):
        fn.cache_clear()
    request_cleanup = [config_loader.load_config, config_loader.find_project_root]

    loads = []
    real_load = wf.load_archive_phase_durations

    def counting_load(*args, **kwargs):
        loads.append(1)
        return real_load(*args, **kwargs)

    calls = []
    real_est = wf.estimate_remaining

    def recording_est(data, history, config, now):
        res = real_est(data, history, config, now)
        calls.append((now, res))
        return res

    ticks = [0]

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            ticks[0] += 1
            return real_now + timedelta(minutes=5 * ticks[0])

    sleeps = [0]

    def fake_sleep(_seconds):
        sleeps[0] += 1
        if sleeps[0] == 2:  # nach Runde 2: Archiv ändert sich
            _write_archived(proj, _archived("neu", [("phase6_implement", 500)]))
            new_mtime = os.stat(_archive_dir(proj)).st_mtime + 5
            os.utime(_archive_dir(proj), (new_mtime, new_mtime))

    monkeypatch.setattr(wf, "load_archive_phase_durations", counting_load)
    monkeypatch.setattr(wf, "estimate_remaining", recording_est)
    monkeypatch.setattr(wf, "datetime", FakeDT)
    monkeypatch.setattr(wf.time, "sleep", fake_sleep)

    try:
        wf._plan_watch()
    finally:
        for fn in request_cleanup:
            fn.cache_clear()

    out = capsys.readouterr().out
    assert len(loads) == 2, loads
    assert len(calls) == 3, calls
    nows = [_dt(c[0]) for c in calls]
    assert nows[0] < nows[1] < nows[2], nows
    ends = [_dt(c[1]["end_low"]) for c in calls]
    assert ends[0] != ends[1], ends
    assert calls[2][1]["n"] == 4  # neuer Archiv-Workflow zählt nach dem Neuladen
    assert "Ende  ca. " in out, out


# =============================================================================
# AC-8: start --score
# =============================================================================

def test_ac8_start_with_score_stamps_state(tmp_path):
    """AC-8: GIVEN start --score 5 WHEN ausgeführt THEN intake_score und estimate_initial
    (low, mid, high, n, source, at) im State."""
    proj, env = _case(tmp_path, "score")
    res = _workflow(["start", WF, "--score", "5"], env, proj)
    assert res.returncode == 0, res.stderr
    state = _read_state(proj, WF)
    assert state["intake_score"] == 5
    init = state["estimate_initial"]
    assert set(init) >= {"low", "mid", "high", "n", "source", "at"}, init
    assert init["source"] == "default" and init["n"] == 0
    assert init["low"] == pytest.approx(60, abs=1)
    assert init["high"] == pytest.approx(240, abs=1)
    assert init["low"] <= init["mid"] <= init["high"]
    _dt(init["at"])

    proj2, env2 = _case(tmp_path, "fast")
    res = _workflow(["start", WF, "--type", "feature-fast", "--score", "0"], env2, proj2)
    assert res.returncode == 0, res.stderr
    state = _read_state(proj2, WF)
    assert state["intake_score"] == 0
    assert state["estimate_initial"]["high"] == pytest.approx(60, abs=1)


def test_ac8_start_score_from_archive(tmp_path):
    """AC-8: GIVEN drei Archiv-Workflows WHEN start --score 2 THEN Schätzung aus dem Archiv."""
    proj, env = _case(tmp_path, "archive")
    _three_archived(proj)
    res = _workflow(["start", WF, "--score", "2"], env, proj)
    assert res.returncode == 0, res.stderr
    init = _read_state(proj, WF)["estimate_initial"]
    assert init["source"] == "archive" and init["n"] == 3
    # Gesamtdauer der drei: 110, 130, 150 -> q25 120, Median 130, q75 140
    assert init["low"] == pytest.approx(120, abs=1)
    assert init["mid"] == pytest.approx(130, abs=1)
    assert init["high"] == pytest.approx(140, abs=1)


@pytest.mark.parametrize("bad", ["9", "x", "-1", "7"])
def test_ac8_start_invalid_score_exit1(tmp_path, bad):
    """AC-8: GIVEN ungültiger Score WHEN start --score THEN Exit 1 mit Usage, kein State."""
    proj, env = _case(tmp_path, f"bad{bad}")
    res = _workflow(["start", WF, "--score", bad], env, proj)
    assert res.returncode == 1, (res.stdout, res.stderr)
    assert "usage" in res.stderr.lower(), res.stderr
    assert not (proj / ".claude" / "workflows" / f"{WF}.json").exists()


def test_ac8_start_without_score_unchanged(tmp_path):
    """AC-8: GIVEN start ohne --score WHEN ausgeführt THEN kein intake_score, Exit 0."""
    proj, env = _case(tmp_path, "plain")
    res = _workflow(["start", WF], env, proj)
    assert res.returncode == 0, res.stderr
    assert "intake_score" not in _read_state(proj, WF)


# =============================================================================
# AC-9: CLI estimate
# =============================================================================

def test_ac9_estimate_cli_on_with_archive(tmp_path):
    """AC-9: GIVEN aktiver Workflow und drei Archiv-Workflows WHEN workflow.py estimate
    THEN alle KEY=value-Zeilen, BASIS = 3, LINE mit Spanne, Exit 0."""
    proj, env = _case(tmp_path, "on")
    _three_archived(proj)
    _write_active(proj, _state("phase5_tdd_red", now=datetime.now(),
                               created_ago=30, phase_ago=5))
    res = _workflow(["estimate"], env, proj)
    assert res.returncode == 0, res.stderr
    assert _kv(res.stdout, "ESTIMATE") == "on", res.stdout
    for key in ("ESTIMATE_LOW_MIN", "ESTIMATE_HIGH_MIN", "ESTIMATE_START",
                "ESTIMATE_END_LOW", "ESTIMATE_END_HIGH", "ESTIMATE_BASIS", "LINE"):
        assert _kv(res.stdout, key) not in (None, ""), (key, res.stdout)
    assert float(_kv(res.stdout, "ESTIMATE_LOW_MIN")) <= float(_kv(res.stdout,
                                                                   "ESTIMATE_HIGH_MIN"))
    assert _kv(res.stdout, "ESTIMATE_BASIS") == "3"
    line = _kv(res.stdout, "LINE")
    assert line.startswith("Grobe Schätzung: "), line
    assert ", Ende ca. " in line and line.endswith("(aus 3 Workflows)"), line


def test_ac9_estimate_cli_default_off_and_error(tmp_path):
    """AC-9: GIVEN kein Archiv / Kill-Switch / Fehler WHEN workflow.py estimate
    THEN BASIS=default mit "(Startwert)" bzw. nur ESTIMATE=off, immer Exit 0."""
    proj, env = _case(tmp_path, "default")
    _write_active(proj, _state("phase1_context", now=datetime.now()))
    res = _workflow(["estimate"], env, proj)
    assert res.returncode == 0, res.stderr
    assert _kv(res.stdout, "ESTIMATE") == "on", res.stdout
    assert _kv(res.stdout, "ESTIMATE_BASIS") == "default"
    assert _kv(res.stdout, "LINE").endswith("(Startwert)")

    proj2, env2 = _case(tmp_path, "kill", config=KILL_CFG)
    _write_active(proj2, _state("phase1_context", now=datetime.now()))
    res = _workflow(["estimate"], env2, proj2)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "ESTIMATE=off", res.stdout

    proj3, env3 = _case(tmp_path, "broken")
    bad = _state("phase1_context", now=datetime.now())
    bad["created"] = "kaputt"
    _write_active(proj3, bad)
    res = _workflow(["estimate"], env3, proj3)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "ESTIMATE=off", res.stdout

    proj4, env4 = _case(tmp_path, "none")
    res = _workflow(["estimate"], env4, proj4)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "ESTIMATE=off", res.stdout


# =============================================================================
# AC-10: Retro "Schätzung vs. Ist"
# =============================================================================

def test_ac10_retro_shows_estimate_vs_actual(tmp_path):
    """AC-10: GIVEN archivierter Workflow mit estimate_initial WHEN retro <name>
    THEN Zeile "Schätzung vs. Ist" mit Spanne, tatsächlicher Dauer und Einordnung."""
    proj, env = _case(tmp_path, "retro")
    start = datetime(2026, 11, 20, 8, 0)
    init = {"low": 60, "mid": 100, "high": 120, "n": 3, "source": "archive",
            "at": start.isoformat()}
    inside = _archived("drin", [("phase1_context", 30), ("phase7_validate", 60)],
                       start=start, estimate_initial=init, intake_score=2)
    over = _archived("drueber", [("phase1_context", 100), ("phase7_validate", 50)],
                     start=start, estimate_initial=init, intake_score=2)
    under = _archived("drunter", [("phase1_context", 20), ("phase7_validate", 25)],
                      start=start, estimate_initial=init, intake_score=2)
    for data in (inside, over, under):
        _write_archived(proj, data)

    def _line(name):
        res = _workflow(["retro", name], env, proj)
        assert res.returncode == 0, res.stderr
        found = [ln for ln in res.stdout.splitlines() if "Schätzung vs. Ist" in ln]
        assert len(found) == 1, res.stdout
        return found[0]

    line = _line("drin")
    assert "geschätzt 1 h–2 h" in line, line
    assert "tatsächlich 1 h 30 min" in line, line
    assert "(innerhalb)" in line, line
    line = _line("drueber")
    assert "tatsächlich 2 h 30 min" in line and "(darüber)" in line, line
    line = _line("drunter")
    assert "tatsächlich 45 min" in line and "(darunter)" in line, line


def test_ac10_retro_without_estimate_initial_unchanged(tmp_path):
    """AC-10: GIVEN archivierter Workflow ohne estimate_initial WHEN retro
    THEN keine Zeile "Schätzung vs. Ist"."""
    proj, env = _case(tmp_path, "retro-alt")
    _write_archived(proj, _archived("alt", [("phase1_context", 30)]))
    res = _workflow(["retro", "alt"], env, proj)
    assert res.returncode == 0, res.stderr
    assert "Schätzung vs. Ist" not in res.stdout
    assert "RETRO: alt" in res.stdout


# =============================================================================
# AC-11: Kill-Switch und Fail-open
# =============================================================================

def test_ac11_plan_shows_block_when_enabled(tmp_path):
    """AC-11 (Gegenprobe): GIVEN enabled und aktiver Workflow WHEN plan
    THEN Zeit-Block mit "(Startwert)" — die Negativfälle unten sind also nicht trivial."""
    proj, env = _case(tmp_path, "plan-on")
    _write_active(proj, _state("phase5_tdd_red", now=datetime.now(), created_ago=10))
    res = _workflow(["plan"], env, proj)
    assert res.returncode == 0, res.stderr
    times = _time_lines(res.stdout)
    assert [t.split("  ")[0] for t in times] == ["Start", "Dauer", "Ende"], res.stdout
    assert times[1].endswith("(Startwert)"), times


@pytest.mark.parametrize("label,config,breakage", [
    ("kill", KILL_CFG, None),
    ("badcfg", BAD_CFG, None),
    ("created", ON_CFG, "created"),
    ("fields", ON_CFG, "fields"),
])
def test_ac11_plan_and_estimate_fail_open(tmp_path, label, config, breakage):
    """AC-11: GIVEN Kill-Switch, ungültige Konfiguration, ungültiges created oder fehlende
    Felder WHEN plan, plan --watch und estimate laufen
    THEN keine Zeit-Zeilen, Exit 0."""
    proj, env = _case(tmp_path, label, config=config,
                      OPENSPEC_PLAN_WATCH_ROUNDS="1", OPENSPEC_PLAN_WATCH_INTERVAL="0")
    data = _state("phase5_tdd_red", now=datetime.now(), created_ago=10)
    if breakage == "created":
        data["created"] = "kaputt"
    elif breakage == "fields":
        del data["created"]
        data["phase_log"] = "kein-log"
    _write_active(proj, data)

    plan = _workflow(["plan"], env, proj)
    assert plan.returncode == 0, plan.stderr
    assert _time_lines(plan.stdout) == [], plan.stdout
    assert "TDD-RED" in plan.stdout

    watch = _workflow(["plan", "--watch"], env, proj)
    assert watch.returncode == 0, watch.stderr
    assert _time_lines(watch.stdout.replace("\x1b[H\x1b[2J", "\n")) == [], watch.stdout
    assert "TDD-RED" in watch.stdout

    est = _workflow(["estimate"], env, proj)
    assert est.returncode == 0, est.stderr
    assert est.stdout.strip() == "ESTIMATE=off", est.stdout


def test_ac11_broken_archive_does_not_break_plan(tmp_path):
    """AC-11: GIVEN kaputte Archiv-Datei WHEN plan und estimate THEN kein Abbruch,
    die kaputte Datei wird übersprungen."""
    proj, env = _case(tmp_path, "broken-archive")
    _three_archived(proj)
    (_archive_dir(proj) / "kaputt.json").write_text("{kaputt")
    _write_active(proj, _state("phase5_tdd_red", now=datetime.now(), created_ago=10))
    plan = _workflow(["plan"], env, proj)
    assert plan.returncode == 0, plan.stderr
    assert "TDD-RED" in plan.stdout
    est = _workflow(["estimate"], env, proj)
    assert est.returncode == 0, est.stderr
    assert _kv(est.stdout, "ESTIMATE_BASIS") == "3", est.stdout


def test_ac11_start_never_breaks(tmp_path):
    """AC-11: GIVEN Kill-Switch bzw. kaputtes Archiv WHEN start --score
    THEN Exit 0; mit Kill-Switch kein estimate_initial."""
    proj, env = _case(tmp_path, "start-kill", config=KILL_CFG)
    res = _workflow(["start", WF, "--score", "3"], env, proj)
    assert res.returncode == 0, res.stderr
    state = _read_state(proj, WF)
    assert "estimate_initial" not in state

    proj2, env2 = _case(tmp_path, "start-broken")
    (_archive_dir(proj2) / "kaputt.json").write_text("{kaputt")
    res = _workflow(["start", WF, "--score", "3"], env2, proj2)
    assert res.returncode == 0, res.stderr
    assert _read_state(proj2, WF)["intake_score"] == 3

    proj3, env3 = _case(tmp_path, "start-badcfg", config=BAD_CFG)
    res = _workflow(["start", WF, "--score", "3"], env3, proj3)
    assert res.returncode == 0, res.stderr


# =============================================================================
# AC-12: Befehlstexte, Config, Skill-Drift
# =============================================================================

def test_ac12_intake_texts_config_and_no_drift():
    """AC-12: GIVEN 00-intake (Quelle und Skill) und config.yaml WHEN gelesen
    THEN --score, workflow.py estimate und time_estimate vorhanden, keine Skill-Drift."""
    for path in (REPO_ROOT / "core" / "commands" / "00-intake.md",
                 REPO_ROOT / "skills" / "00-intake" / "SKILL.md"):
        text = path.read_text(encoding="utf-8")
        has_score = "--score" in text
        has_estimate = "workflow.py estimate" in text
        assert has_score, f"--score fehlt in {path}"
        assert has_estimate, f"workflow.py estimate fehlt in {path}"

    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text(encoding="utf-8"))
    section = cfg.get("time_estimate")
    assert isinstance(section, dict), "time_estimate fehlt in config.yaml"
    assert section["enabled"] is True
    assert section["min_samples"] == 3
    assert list(section["quantiles"]) == [0.25, 0.75]
    assert list(section["defaults"]["feature"]) == [60, 240]
    assert list(section["defaults"]["feature-fast"]) == [20, 60]

    res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"),
                          "--check"], capture_output=True, text=True, cwd=str(REPO_ROOT),
                         timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr
