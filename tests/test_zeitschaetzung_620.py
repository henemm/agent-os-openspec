"""Zeitschätzung für Workflows (Issue #620): Intake-Schätzung und Plan-Pane.

Das System lernt aus den archivierten Workflows (`phase_log` in
`.claude/workflows/_archive/*.json`): Restdauer je Vergleichs-Workflow =
`max(0, Dauer aktuelle Phase - verstrichen) + Summe der späteren Phasen`,
Spanne = Quantile 0.25/0.75 (lineare Interpolation), Punktwert = Median.
Zu wenige Erfahrungswerte -> Startwerte aus `time_estimate.defaults`,
skaliert mit dem Anteil offener Plan-Schritte.

Schnittstellen (Spec docs/specs/feat-620-zeitschaetzung.md):
- `load_archive_phase_durations(archive_dir=None) -> list[dict]`
- `estimate_remaining(data, history, config, now) -> dict | None` (pure)
- `render_plan(..., estimate=None)` mit Block `Start` / `Dauer` / `Ende`
- `_estimate_now()`; `_plan_watch` rechnet je Runde neu, Archiv-Cache über
  (mtime, Dateizahl)
- CLI: `start <name> --score N`, `estimate`, `retro <name>` ("Schätzung vs. Ist")

#642 (docs/specs/fix-642-zeitschaetzung.md) ändert das Anzeigeformat: nur
Archiv-Workflows mit Aktivitätsdatei zählen (`clean`), ohne sie keine Zahl
(keine Startwerte mehr), keine „Dauer“-Zeile in der Prognose, Ende auf
Viertelstunden. Die Rechenlogik (Restdauer, Quantile, Median) prüft diese
Datei weiterhin; die Startwert-Tests sind durch #642 ersetzt.
"""

import json
import os
import subprocess
import sys
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
FULL_ORDER = (P1, P2, P3, P4, P5, P6, P6B, P7)

CFG = {"enabled": True, "min_samples": 3, "quantiles": [0.25, 0.75],
       "defaults": {"feature": [60, 240], "feature-fast": [20, 60]}}

CONFIG_ON = """time_estimate:
  enabled: true
  min_samples: 3
  quantiles: [0.25, 0.75]
  defaults:
    feature: [60, 240]
    feature-fast: [20, 60]
"""
CONFIG_OFF = """time_estimate:
  enabled: false
"""

NOW = datetime(2026, 11, 21, 14, 0, 0)
TIME_PREFIXES = ("Start  ", "Dauer  ", "Ende  ")


# --- Helpers ---------------------------------------------------------------

def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _state(phase: str, now: datetime = NOW, in_phase_min: float = 0.0,
           elapsed_min: float = 90.0, wtype: str = "feature", score=None,
           name: str = "zeit-aktuell", **fields) -> dict:
    """Aktueller State: seit `elapsed_min` gestartet, seit `in_phase_min` in `phase`."""
    created = now - timedelta(minutes=elapsed_min)
    entered = now - timedelta(minutes=in_phase_min)
    first = P3 if wtype == "feature-fast" else P1
    log = []
    if entered > created:
        log.append({"phase": first, "entered_at": _iso(created), "exited_at": _iso(entered),
                    "duration_min": round((entered - created).total_seconds() / 60, 1)})
    log.append({"phase": phase, "entered_at": _iso(entered), "exited_at": None,
                "duration_min": None})
    data = {"name": name, "workflow_type": wtype, "current_phase": phase,
            "created": _iso(created), "last_updated": _iso(entered),
            "phase_transitions": [], "phase_log": log}
    if score is not None:
        data["intake_score"] = score
    data.update(fields)
    return data


def _h(phases: dict, wtype: str = "feature", stage=None) -> dict:
    """Ein Eintrag der geladenen Historie (Format von load_archive_phase_durations).

    #642: `clean` = mit Aktivitätsdatei; nur solche bilden die Vergleichsgruppe.
    """
    return {"type": wtype, "stage": stage, "phases": dict(phases), "clean": True}


def _activity(proj: Path, name: str, phases: dict) -> None:
    """Aktivitätsdatei (#628) zum Archiv-Workflow: macht ihn „sauber“ (#642)."""
    folder = proj / ".claude" / "workflows" / "_activity"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps(
        {"last": "2026-11-01T18:00:00", "phases": {k: float(v) for k, v in phases.items()}}))


def _write_clean(proj: Path, data: dict, phases: dict) -> Path:
    """Archiv-Workflow mit passender Aktivitätsdatei (#642)."""
    _activity(proj, data["name"], phases)
    return _write_archived(proj, data)


def _closed_log(phases: dict, start: datetime) -> list:
    """Aufeinanderfolgende, abgeschlossene phase_log-Einträge."""
    log = []
    t = start
    for phase, minutes in phases.items():
        end = t + timedelta(minutes=minutes)
        log.append({"phase": phase, "entered_at": _iso(t), "exited_at": _iso(end),
                    "duration_min": float(minutes)})
        t = end
    return log


def _archived(name: str, phases: dict, wtype: str = "feature", score=None,
              start: datetime = datetime(2026, 11, 1, 9, 0), **fields) -> dict:
    data = {"name": name, "workflow_type": wtype, "current_phase": P8,
            "created": _iso(start), "phase_transitions": [],
            "phase_log": _closed_log(phases, start)}
    if score is not None:
        data["intake_score"] = score
    data.update(fields)
    return data


def _project(root: Path, config: "str | None" = CONFIG_ON) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_archive").mkdir(parents=True)
    (proj / "_home").mkdir()
    if config is not None:
        (proj / "openspec.yaml").write_text(config)
    return proj


def _case(tmp_path: Path, label: str, config: "str | None" = CONFIG_ON):
    root = tmp_path / label
    root.mkdir()
    proj = _project(root, config)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_", "GH_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    return proj, env


def _archive(proj: Path) -> Path:
    return proj / ".claude" / "workflows" / "_archive"


def _write_active(proj: Path, data: dict) -> None:
    (proj / ".claude" / "workflows" / f"{data['name']}.json").write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(data["name"])


def _write_archived(proj: Path, data: dict) -> Path:
    path = _archive(proj) / f"{data['name']}.json"
    path.write_text(json.dumps(data))
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


def _close(a: datetime, b: datetime, seconds: float = 60.0) -> bool:
    return abs((a - b).total_seconds()) <= seconds


# Historie für AC-2: Rest in Phase 6 bei 10 min Verstrichenem
#   W1: max(0, 30-10) + 10 + 20 = 50
#   W2: max(0, 60-10) + 20 + 10 = 80
#   W3: max(0,  5-10) +  5 + 10 = 15
#   W4: max(0, 40-10) +  0 + 30 = 60   (kein 6b)
# sortiert 15, 50, 60, 80 -> q25 = 15 + 0.75*35 = 41.25, Median 55, q75 = 60 + 0.25*20 = 65
HIST_AC2 = [
    _h({P1: 100, P2: 50, P5: 30, P6: 30, P6B: 10, P7: 20}),
    _h({P1: 10, P3: 40, P6: 60, P6B: 20, P7: 10}),
    _h({P1: 300, P6: 5, P6B: 5, P7: 10}),
    _h({P2: 7, P6: 40, P7: 30}),
]

# Historie für AC-3 (alle Phasen)
HIST_AC3 = [
    _h({P1: 10, P2: 10, P3: 20, P4: 5, P5: 15, P6: 30, P6B: 10, P7: 20}),
    _h({P1: 20, P2: 15, P3: 40, P4: 30, P5: 20, P6: 60, P6B: 20, P7: 10}),
    _h({P1: 5, P2: 5, P3: 10, P4: 2, P5: 5, P6: 5, P6B: 5, P7: 10}),
    _h({P1: 15, P2: 10, P3: 30, P4: 60, P5: 25, P6: 40, P7: 30}),
]


# =============================================================================
# AC-1: Archiv-Dauern laden
# =============================================================================

def _ac1_archive(archive: Path) -> None:
    start = datetime(2026, 11, 2, 9, 0)
    t = lambda m: _iso(start + timedelta(minutes=m))  # noqa: E731
    a = {"name": "a", "workflow_type": "feature", "intake_score": 2, "created": t(0),
         "phase_log": [
             {"phase": P1, "entered_at": t(0), "exited_at": t(10), "duration_min": 10.0},
             {"phase": P2, "entered_at": t(10), "exited_at": t(15), "duration_min": 5.0},
             {"phase": P1, "entered_at": t(15), "exited_at": t(22), "duration_min": 7.0},
             # exited_at ohne duration_min -> zaehlt nicht
             {"phase": P4, "entered_at": t(22), "exited_at": t(30), "duration_min": None},
             {"phase": P3, "entered_at": t(30), "exited_at": None, "duration_min": None},
         ]}
    b = _archived("b", {P1: 50, P2: 50}, status="abandoned", intake_score=3)
    c = {"name": "c", "workflow_type": "feature", "created": t(0),
         "phase_log": [{"phase": P1, "entered_at": t(0), "exited_at": None,
                        "duration_min": None}]}
    d = _archived("d", {P3: 20}, wtype="feature-fast")
    e = _archived("e", {P1: 3}, score=0)
    del e["workflow_type"]
    f = _archived("f", {P6: 12.5}, score=6)
    for item in (a, b, c, d, e, f):
        (archive / f"{item['name']}.json").write_text(json.dumps(item))
    (archive / "kaputt.json").write_text("{kaputt")


AC1_EXPECTED = sorted([
    ("feature", "1-3", ((P1, 17.0), (P2, 5.0))),
    ("feature-fast", "None", ((P3, 20.0),)),
    ("feature", "0", ((P1, 3.0),)),
    ("feature", "4-6", ((P6, 12.5),)),
])


def _norm_history(history: list) -> list:
    out = []
    for item in history:
        phases = tuple(sorted((k, float(v)) for k, v in item["phases"].items()))
        out.append((item["type"], str(item["stage"]), phases))
    return sorted(out)


def test_ac1_load_archive_counts_valid_and_sums_reentries(tmp_path):
    wf = _wf()
    archive = tmp_path / "_archive"
    archive.mkdir()
    _ac1_archive(archive)
    history = wf.load_archive_phase_durations(archive)
    assert isinstance(history, list)
    assert _norm_history(history) == AC1_EXPECTED, history


def test_ac1_load_archive_default_dir(tmp_path, monkeypatch):
    wf = _wf()
    archive = tmp_path / "_archive"
    archive.mkdir()
    _ac1_archive(archive)
    monkeypatch.setattr(wf, "_archive_dir", lambda: archive)
    assert _norm_history(wf.load_archive_phase_durations()) == AC1_EXPECTED


def test_ac1_load_archive_missing_dir_is_empty(tmp_path):
    wf = _wf()
    assert wf.load_archive_phase_durations(tmp_path / "gibt-es-nicht") == []


# =============================================================================
# AC-2: Restdauer, Quantile, Median, Ende
# =============================================================================

def test_ac2_estimate_exact_values_phase6():
    wf = _wf()
    data = _state(P6, in_phase_min=10, elapsed_min=90)
    est = wf.estimate_remaining(data, HIST_AC2, CFG, NOW)
    assert isinstance(est, dict), est
    assert est["source"] == "archive"
    assert est["n"] == 4
    assert est["low_min"] == pytest.approx(41.25, abs=0.01)
    assert est["mid_min"] == pytest.approx(55.0, abs=0.01)
    assert est["high_min"] == pytest.approx(65.0, abs=0.01)
    assert est["elapsed_min"] == pytest.approx(90.0, abs=0.01)
    assert est["total_low_min"] == pytest.approx(131.25, abs=0.01)
    assert est["total_high_min"] == pytest.approx(155.0, abs=0.01)
    assert est["start"] == NOW - timedelta(minutes=90)
    # #642: Ende auf die Viertelstunde, 14:41:15 ab- und 15:05 aufgerundet
    assert est["end_low"] == NOW + timedelta(minutes=30), est["end_low"]
    assert est["end_high"] == NOW + timedelta(minutes=75), est["end_high"]


def test_ac2_fast_track_uses_fast_plan_steps():
    """Fast Track: nach Phase 6 folgen nur 7 und 8 — 6b zaehlt nicht."""
    wf = _wf()
    hist = [_h({P3: 10, P6: 20, P6B: 50, P7: 10}, wtype="feature-fast") for _ in range(3)]
    data = _state(P6, in_phase_min=5, elapsed_min=30, wtype="feature-fast")
    est = wf.estimate_remaining(data, hist, CFG, NOW)
    assert est["source"] == "archive" and est["n"] == 3
    # max(0, 20-5) + 10 = 25 (ohne 6b: 50)
    assert est["low_min"] == pytest.approx(25.0, abs=0.01)
    assert est["mid_min"] == pytest.approx(25.0, abs=0.01)
    assert est["high_min"] == pytest.approx(25.0, abs=0.01)


def test_ac2_configured_quantiles_are_used():
    wf = _wf()
    data = _state(P6, in_phase_min=10, elapsed_min=90)
    est = wf.estimate_remaining(data, HIST_AC2, dict(CFG, quantiles=[0.0, 1.0]), NOW)
    # Reste 15, 50, 60, 80: Quantile 0 und 1 = Minimum und Maximum
    assert est["low_min"] == pytest.approx(15.0, abs=0.01)
    assert est["mid_min"] == pytest.approx(55.0, abs=0.01)
    assert est["high_min"] == pytest.approx(80.0, abs=0.01)


def test_ac2_invalid_created_gives_no_estimate():
    wf = _wf()
    data = _state(P6, in_phase_min=10, elapsed_min=90, created="kaputt")
    assert wf.estimate_remaining(data, HIST_AC2, CFG, NOW) is None


# =============================================================================
# AC-3: wird präziser, lernt
# =============================================================================

def test_ac3_span_narrows_in_later_phase():
    wf = _wf()
    early = wf.estimate_remaining(_state(P3, elapsed_min=60), HIST_AC3, CFG, NOW)
    late = wf.estimate_remaining(_state(P7, elapsed_min=200), HIST_AC3, CFG, NOW)
    # Phase 3: Reste 100, 180, 37, 185 -> 84.25 .. 181.25
    assert early["low_min"] == pytest.approx(84.25, abs=0.01)
    assert early["high_min"] == pytest.approx(181.25, abs=0.01)
    # Phase 7: Reste 20, 10, 10, 30 -> 10 .. 22.5
    assert late["low_min"] == pytest.approx(10.0, abs=0.01)
    assert late["high_min"] == pytest.approx(22.5, abs=0.01)
    assert (late["high_min"] - late["low_min"]) <= (early["high_min"] - early["low_min"])


def test_ac3_additional_archive_workflow_changes_result():
    wf = _wf()
    data = _state(P7, elapsed_min=200)
    before = wf.estimate_remaining(data, HIST_AC3, CFG, NOW)
    after = wf.estimate_remaining(data, HIST_AC3 + [_h({P7: 100})], CFG, NOW)
    assert after["n"] == before["n"] + 1
    assert (after["low_min"], after["mid_min"], after["high_min"]) != \
        (before["low_min"], before["mid_min"], before["high_min"])


# =============================================================================
# AC-4: Stufe -> Typ -> Startwerte
# =============================================================================

def test_ac4_stage_group_used_when_enough():
    wf = _wf()
    hist = ([_h({P7: 100}, stage="4-6") for _ in range(3)]
            + [_h({P7: 10}, stage="1-3") for _ in range(3)]
            + [_h({P7: 10}) for _ in range(2)])
    est = wf.estimate_remaining(_state(P7, score=5), hist, CFG, NOW)
    assert est["source"] == "archive"
    assert est["n"] == 3
    assert est["low_min"] == pytest.approx(100.0) and est["high_min"] == pytest.approx(100.0)


def test_ac4_stage_zero_is_its_own_group():
    wf = _wf()
    hist = [_h({P7: 7}, stage="0") for _ in range(3)] + [_h({P7: 70}) for _ in range(3)]
    est = wf.estimate_remaining(_state(P7, score=0), hist, CFG, NOW)
    assert est["n"] == 3
    assert est["mid_min"] == pytest.approx(7.0)


def test_ac4_falls_back_to_type_group():
    wf = _wf()
    hist = ([_h({P7: 10}, stage="1-3") for _ in range(2)]
            + [_h({P7: 100}, stage="4-6") for _ in range(2)]
            + [_h({P7: 50})]
            + [_h({P7: 999}, wtype="feature-fast") for _ in range(3)])
    est = wf.estimate_remaining(_state(P7, score=2), hist, CFG, NOW)
    # Typ-Gruppe feature: 10, 10, 50, 100, 100 -> q25 10, Median 50, q75 100
    assert est["source"] == "archive"
    assert est["n"] == 5
    assert est["low_min"] == pytest.approx(10.0)
    assert est["mid_min"] == pytest.approx(50.0)
    assert est["high_min"] == pytest.approx(100.0)


def test_ac4_without_score_uses_type_group():
    wf = _wf()
    hist = [_h({P7: 100}, stage="4-6") for _ in range(3)] + [_h({P7: 10})]
    est = wf.estimate_remaining(_state(P7), hist, CFG, NOW)
    assert est["n"] == 4


def test_ac4_without_clean_group_no_numbers():
    """#642 ersetzt die Startwerte: ohne saubere Gruppe keine Zahl."""
    wf = _wf()
    hist = [_h({P7: 10}) for _ in range(2)] + \
        [_h({P7: 10}, wtype="feature-fast") for _ in range(5)] + \
        [dict(_h({P7: 10}), clean=False) for _ in range(5)]
    for data in (_state(P1, elapsed_min=0), _state(P6, in_phase_min=5, elapsed_min=120)):
        est = wf.estimate_remaining(data, hist, CFG, NOW)
        assert est["source"] == "none" and est["n"] == 0, est
        assert est["end_low"] is None and est["end_high"] is None and est["approval"] is None
        assert "low_min" not in est and "total_low_min" not in est, est


def test_ac4_fast_track_without_history_no_numbers():
    wf = _wf()
    est = wf.estimate_remaining(_state(P3, elapsed_min=0, wtype="feature-fast"), [], CFG, NOW)
    assert est["source"] == "none" and est["n"] == 0
    assert est["end_low"] is None and est["approval"] is None


# =============================================================================
# AC-5: Plan-Block Start / Dauer / Ende
# =============================================================================

def _est(**over) -> dict:
    est = {"low_min": 30.0, "mid_min": 60.0, "high_min": 110.0, "elapsed_min": 40.0,
           "total_low_min": 70.0, "total_high_min": 150.0, "n": 7, "source": "archive",
           "start": datetime(2026, 11, 21, 12, 30), "end_low": datetime(2026, 11, 21, 15, 40),
           "end_high": datetime(2026, 11, 21, 17, 0), "now": NOW}
    est.update(over)
    return est


def test_ac5_render_without_estimate_is_unchanged():
    wf = _wf()
    for data, kwargs in (
        (_state(P6, in_phase_min=10), {}),
        (_state(P1, elapsed_min=0), {"deploy": "configured"}),
        (_state(P6, wtype="feature-fast"), {"width": 30}),
        (_archived("zeit-alt", {P1: 10}, ship_status="done"), {"archived": True}),
    ):
        assert wf.render_plan(data, estimate=None, **kwargs) == wf.render_plan(data, **kwargs)


def test_ac5_render_with_estimate_block_after_steps():
    wf = _wf()
    data = _state(P6, in_phase_min=10)
    plain = wf.render_plan(data)
    out = wf.render_plan(data, estimate=_est())
    lines = out.splitlines()
    # #642: keine Dauer-Zeile, Basis in eigener, eingerückter Zeile
    # #655: Countdown-Zeile unter der Ende-Zeile (14:00 -> L 100, H 180 min)
    block = ["Start  12:30", "Ende  ca. 15:40–17:00", "Noch  ca. 1,5–3 h",
             "  aus 7 Workflows"]
    assert _time_lines(out) == block[:2], lines
    i = lines.index(block[0])
    assert lines[i:i + 4] == block
    ship = next(k for k, ln in enumerate(lines) if "Ausliefern" in ln)
    assert ship < i, lines
    assert i + 3 < len(lines) - 1, lines  # vor der Schlusszeile
    assert lines[-1] == plain.splitlines()[-1]
    # Sonst unverändert (abgesehen von Leerzeilen)
    rest = [ln for ln in lines if ln not in block and ln]
    assert rest == [ln for ln in plain.splitlines() if ln]


def test_ac5_duration_formats_and_no_startwert():
    """Dauerformat (Ist-Block); #642: ohne Daten „Ende  offen“ statt Startwert."""
    wf = _wf()
    assert [wf.format_duration(m) for m in (45, 120, 70)] == ["45 min", "2 h", "1 h 10 min"]
    out = wf.render_plan(_state(P1, elapsed_min=0),
                         estimate=_est(n=0, source="none", end_low=None, end_high=None))
    assert "Ende  offen" in out.splitlines(), out
    assert "  zu wenig Vergleichsdaten" in out.splitlines(), out
    assert "Startwert" not in out and "Dauer" not in out, out


def test_ac5_dates_when_not_today():
    wf = _wf()
    est = _est(start=datetime(2026, 11, 20, 16, 5), end_low=datetime(2026, 11, 21, 23, 30),
               end_high=datetime(2026, 11, 22, 1, 10))
    out = wf.render_plan(_state(P6, in_phase_min=10), estimate=est)
    lines = out.splitlines()
    assert "Start  20.11. 16:05" in lines, lines
    assert "Ende  ca. 23:30–22.11. 01:10" in lines, lines


# =============================================================================
# AC-6: abgeschlossen / archiviert -> tatsächliche Werte
# =============================================================================

def _done_data(**over) -> dict:
    data = _archived("zeit-fertig", {P1: 15, P2: 30, P3: 60}, ship_status="done",
                     start=datetime(2026, 11, 20, 9, 0))
    data.update(over)
    return data


ACTUAL = {"actual": True, "now": datetime(2026, 11, 20, 12, 0)}


def test_ac6_archived_shows_actual_values():
    wf = _wf()
    out = wf.render_plan(_done_data(), archived=True, estimate=dict(ACTUAL))
    assert _time_lines(out) == ["Start  09:00", "Dauer  1 h 45 min", "Ende  10:45"], out
    assert "ca." not in out


def test_ac6_phase8_falls_back_to_last_updated():
    wf = _wf()
    data = _done_data(last_updated="2026-11-20T11:20:00")
    data["phase_log"].append({"phase": P8, "entered_at": "2026-11-20T10:45:00",
                              "exited_at": None, "duration_min": None})
    out = wf.render_plan(data, estimate=dict(ACTUAL))
    assert _time_lines(out) == ["Start  09:00", "Dauer  2 h 20 min", "Ende  11:20"], out


def test_ac6_abandoned_and_missing_timestamps_no_block():
    wf = _wf()
    abandoned = wf.render_plan(_done_data(status="abandoned"), archived=True,
                               estimate=dict(ACTUAL))
    assert _time_lines(abandoned) == [], abandoned
    bare = {"name": "zeit-leer", "workflow_type": "feature", "current_phase": P8,
            "phase_transitions": [], "phase_log": [], "ship_status": "done"}
    out = wf.render_plan(bare, archived=True, estimate=dict(ACTUAL))
    assert _time_lines(out) == [], out


# =============================================================================
# AC-7: plan --watch rechnet je Runde neu, Archiv-Cache
# =============================================================================

def _reset_config_cache():
    import config_loader  # noqa: PLC0415
    for fn in (config_loader.find_project_root, config_loader.load_config):
        clear = getattr(fn, "cache_clear", None)
        if clear:
            clear()


def test_ac7_watch_caches_archive_and_recomputes(tmp_path, monkeypatch, capsys):
    """Ein Vergleichs-Workflow (P6 = 15 min) ist in der laufenden Phase schon
    ueberzogen: nur dann wandert das Ende mit der Uhr, sonst kuerzt sich `now`
    aus `now + (Dauer - verstrichen) + spaetere Phasen` heraus."""
    wf = _wf()
    proj = _project(tmp_path)
    for k in list(os.environ):
        if k.startswith(("OPENSPEC_", "HERDR_")):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.setenv("HOME", str(proj / "_home"))
    monkeypatch.setenv("OPENSPEC_PLAN_WATCH_ROUNDS", "3")
    monkeypatch.setenv("OPENSPEC_PLAN_WATCH_INTERVAL", "0")
    monkeypatch.chdir(proj)
    _reset_config_cache()
    try:
        archive = _archive(proj)
        for i, p6 in enumerate((15, 60, 90)):
            _write_clean(proj, _archived(f"zeit-arch-{i}", {P1: 10, P6: p6, P7: 20}),
                         {P1: 10, P6: p6, P7: 20})
        monkeypatch.setattr(wf, "_archive_dir", lambda: archive)

        base = datetime(2026, 11, 21, 10, 0)
        data = _state(P6, now=base, in_phase_min=10, elapsed_min=60)
        monkeypatch.setattr(wf, "_plan_active", lambda: (data["name"], dict(data)))
        monkeypatch.setattr(wf, "_plan_watch_should_end", lambda *a, **k: False)
        monkeypatch.setattr(wf, "_plan_follow_target", lambda *a, **k: None)
        monkeypatch.setattr(wf, "_plan_fetch_missing", lambda *a, **k: None)

        ticks = [0]

        def fake_now():  # #642: 20-min-Takt, das Ende ist auf Viertelstunden gerundet
            ticks[0] += 1
            return base + timedelta(minutes=20 * ticks[0])

        monkeypatch.setattr(wf, "_estimate_now", fake_now)

        sleeps = [0]

        def fake_sleep(_s):
            sleeps[0] += 1
            if sleeps[0] == 2:  # nach Runde 2: neuer Messpunkt im Archiv
                _write_clean(proj, _archived("zeit-arch-neu", {P6: 200, P7: 50}),
                             {P6: 200, P7: 50})
                st = archive.stat().st_mtime + 100
                os.utime(archive, (st, st))

        monkeypatch.setattr(wf.time, "sleep", fake_sleep)

        original_load = wf.load_archive_phase_durations
        loads = []

        def counting_load(*a, **k):
            loads.append(a)
            return original_load(*a, **k)

        monkeypatch.setattr(wf, "load_archive_phase_durations", counting_load)

        original_render = wf.render_plan
        estimates = []

        def recording_render(*a, **k):
            estimates.append(k.get("estimate"))
            return original_render(*a, **k)

        monkeypatch.setattr(wf, "render_plan", recording_render)

        wf._plan_watch()
        capsys.readouterr()

        assert len(estimates) == 3, estimates
        assert all(isinstance(e, dict) for e in estimates), estimates
        assert len(loads) == 2, loads
        assert estimates[0]["end_low"] != estimates[1]["end_low"]
        assert estimates[0]["n"] == 3 and estimates[1]["n"] == 3
        assert estimates[2]["n"] == 4  # neu archivierter Workflow zaehlt
    finally:
        monkeypatch.undo()
        _reset_config_cache()


def test_estimate_now_returns_current_time():
    wf = _wf()
    before = datetime.now()
    value = wf._estimate_now()
    after = datetime.now()
    assert isinstance(value, datetime) and before <= value <= after


# =============================================================================
# AC-8: start --score N
# =============================================================================

def _state_file(proj: Path, name: str) -> dict:
    return json.loads((proj / ".claude" / "workflows" / f"{name}.json").read_text())


def test_ac8_start_with_score_stamps_estimate(tmp_path):
    proj, env = _case(tmp_path, "score5")
    res = _workflow(["start", "zeit-a", "--score", "5"], env, proj)
    assert res.returncode == 0, res.stderr
    state = _state_file(proj, "zeit-a")
    assert state["intake_score"] == 5 and isinstance(state["intake_score"], int)
    # #642: ohne Vergleichsdaten keine Zahl, also kein `estimate_initial` aus Startwerten
    assert "estimate_initial" not in state, state


def test_ac8_start_score_zero_and_fast_track(tmp_path):
    proj, env = _case(tmp_path, "score0")
    res = _workflow(["start", "zeit-b", "--type", "feature-fast", "--score", "0"], env, proj)
    assert res.returncode == 0, res.stderr
    state = _state_file(proj, "zeit-b")
    assert state["intake_score"] == 0
    assert "estimate_initial" not in state, state  # #642: keine Startwerte


def test_ac8_start_score_uses_archive(tmp_path):
    proj, env = _case(tmp_path, "score-arch")
    for i, p1 in enumerate((30, 60, 90)):
        _write_clean(proj, _archived(f"zeit-arch-{i}", {P1: p1, P3: 20, P7: 10}, score=4),
                     {P1: p1, P3: 20, P7: 10})
    res = _workflow(["start", "zeit-f", "--score", "5"], env, proj)
    assert res.returncode == 0, res.stderr
    init = _state_file(proj, "zeit-f")["estimate_initial"]
    assert set(init) >= {"low", "mid", "high", "n", "source", "at"}, init
    assert init["source"] == "archive" and init["n"] == 3, init
    assert init["low"] <= init["mid"] <= init["high"]
    assert isinstance(init["at"], str) and init["at"]


@pytest.mark.parametrize("bad", ["9", "x", "-1"])
def test_ac8_start_invalid_score_usage(tmp_path, bad):
    proj, env = _case(tmp_path, f"bad{bad}")
    res = _workflow(["start", "zeit-c", "--score", bad], env, proj)
    assert res.returncode == 1, (res.stdout, res.stderr)
    assert "Usage" in res.stderr, res.stderr


def test_ac8_start_without_score_unchanged(tmp_path):
    proj, env = _case(tmp_path, "noscore")
    res = _workflow(["start", "zeit-d"], env, proj)
    assert res.returncode == 0, res.stderr
    assert "intake_score" not in _state_file(proj, "zeit-d")


# =============================================================================
# AC-9: CLI estimate
# =============================================================================

def test_ac9_estimate_cli_archive(tmp_path):
    proj, env = _case(tmp_path, "est")
    for i, p6 in enumerate((30, 60, 90)):
        _write_clean(proj, _archived(f"zeit-arch-{i}", {P1: 10, P6: p6, P7: 20}),
                     {P1: 10, P6: p6, P7: 20})
    _write_active(proj, _state(P6, now=datetime.now(), in_phase_min=10, elapsed_min=60))
    res = _workflow(["estimate"], env, proj)
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert _kv(out, "ESTIMATE") == "on", out
    low = float(_kv(out, "ESTIMATE_LOW_MIN"))
    high = float(_kv(out, "ESTIMATE_HIGH_MIN"))
    assert 0 <= low <= high
    for key in ("ESTIMATE_START", "ESTIMATE_END_LOW", "ESTIMATE_END_HIGH"):
        assert _kv(out, key), (key, out)
    assert _kv(out, "ESTIMATE_BASIS") == "3", out
    assert _kv(out, "LINE").startswith("Ende ca. "), out  # #642: Format wie der Plan
    assert _kv(out, "LINE").endswith("(aus 3 Workflows)"), out


def test_ac9_estimate_cli_no_data_basis(tmp_path):
    """#642: ohne saubere Vergleichsdaten Basis `none` und keine Zahl."""
    proj, env = _case(tmp_path, "estdef")
    _write_active(proj, _state(P1, now=datetime.now(), elapsed_min=0))
    res = _workflow(["estimate"], env, proj)
    assert res.returncode == 0, res.stderr
    assert _kv(res.stdout, "ESTIMATE") == "on", res.stdout
    assert _kv(res.stdout, "ESTIMATE_BASIS") == "none", res.stdout
    assert _kv(res.stdout, "LINE") == "Noch keine Zeitschätzung: zu wenig Vergleichsdaten"


def test_ac9_estimate_cli_disabled(tmp_path):
    proj, env = _case(tmp_path, "estoff", config=CONFIG_OFF)
    _write_active(proj, _state(P6, now=datetime.now(), in_phase_min=10))
    res = _workflow(["estimate"], env, proj)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "ESTIMATE=off", res.stdout


def test_ac9_estimate_cli_broken_state(tmp_path):
    proj, env = _case(tmp_path, "estbroken")
    _write_active(proj, _state(P6, now=datetime.now(), in_phase_min=10, created="kaputt"))
    res = _workflow(["estimate"], env, proj)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    assert res.stdout.strip() == "ESTIMATE=off", res.stdout


def test_ac9_estimate_cli_broken_archive_file(tmp_path):
    proj, env = _case(tmp_path, "estbrokenarch")
    (_archive(proj) / "kaputt.json").write_text("{kaputt")
    _write_active(proj, _state(P6, now=datetime.now(), in_phase_min=10))
    res = _workflow(["estimate"], env, proj)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    assert _kv(res.stdout, "ESTIMATE") in ("on", "off"), res.stdout


# =============================================================================
# AC-10: Retro "Schätzung vs. Ist"
# =============================================================================

def test_ac10_retro_shows_estimate_vs_actual(tmp_path):
    proj, env = _case(tmp_path, "retro")
    _write_archived(proj, _archived(
        "zeit-retro", {P1: 20, P2: 30, P3: 50},
        estimate_initial={"low": 60, "mid": 90, "high": 120, "n": 5, "source": "archive",
                          "at": "2026-11-01T09:00:00"}))
    res = _workflow(["retro", "zeit-retro"], env, proj)
    assert res.returncode == 0, res.stderr
    lines = [ln for ln in res.stdout.splitlines() if "Schätzung vs. Ist" in ln]
    assert len(lines) == 1, res.stdout
    assert "innerhalb" in lines[0], lines


def test_ac10_retro_without_estimate_unchanged(tmp_path):
    proj, env = _case(tmp_path, "retro-old")
    _write_archived(proj, _archived("zeit-retro-alt", {P1: 20, P2: 30}))
    res = _workflow(["retro", "zeit-retro-alt"], env, proj)
    assert res.returncode == 0, res.stderr
    assert "Schätzung vs. Ist" not in res.stdout


# =============================================================================
# AC-11: Kill-Switch und Fail-open
# =============================================================================

def test_ac11_plan_shows_block_when_enabled(tmp_path):
    proj, env = _case(tmp_path, "plan-on")
    _write_active(proj, _state(P6, now=datetime.now(), in_phase_min=10, elapsed_min=30))
    res = _workflow(["plan"], env, proj)
    assert res.returncode == 0, res.stderr
    prefixes = [ln.split("  ")[0] for ln in _time_lines(res.stdout)]
    assert prefixes == ["Start", "Ende"], res.stdout  # #642: keine Dauer-Zeile
    assert "zu wenig Vergleichsdaten" in res.stdout and "Startwert" not in res.stdout


def test_ac11_plan_kill_switch_no_time_lines(tmp_path):
    proj, env = _case(tmp_path, "plan-off", config=CONFIG_OFF)
    _write_active(proj, _state(P6, now=datetime.now(), in_phase_min=10))
    res = _workflow(["plan"], env, proj)
    assert res.returncode == 0, res.stderr
    assert _time_lines(res.stdout) == [], res.stdout


def test_ac11_plan_broken_inputs_no_abort(tmp_path):
    proj, env = _case(tmp_path, "plan-broken")
    (_archive(proj) / "kaputt.json").write_text("{kaputt")
    _write_active(proj, _state(P6, now=datetime.now(), in_phase_min=10, created="kaputt"))
    res = _workflow(["plan"], env, proj)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr
    assert _time_lines(res.stdout) == [], res.stdout


def test_ac11_start_with_broken_archive(tmp_path):
    proj, env = _case(tmp_path, "start-broken")
    (_archive(proj) / "kaputt.json").write_text("{kaputt")
    res = _workflow(["start", "zeit-e", "--score", "3"], env, proj)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr
    state = _state_file(proj, "zeit-e")
    assert state["intake_score"] == 3


# =============================================================================
# AC-12: Befehlstext, Config, Skill-Sync
# =============================================================================

def test_ac12_intake_command_and_skill_mention_score_and_estimate():
    for path in (REPO_ROOT / "core" / "commands" / "00-intake.md",
                 REPO_ROOT / "skills" / "00-intake" / "SKILL.md"):
        text = path.read_text(encoding="utf-8")
        assert "--score" in text, path
        assert "workflow.py estimate" in text, path


def test_ac12_repo_config_has_time_estimate():
    import yaml  # noqa: PLC0415
    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text(encoding="utf-8"))
    section = cfg.get("time_estimate")
    assert isinstance(section, dict), section
    for key in ("enabled", "min_samples", "quantiles", "defaults"):
        assert key in section, key
    assert section["defaults"].get("feature") and section["defaults"].get("feature-fast")


def test_ac12_sync_skills_no_drift():
    res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"),
                          "--check"], capture_output=True, text=True, cwd=str(REPO_ROOT),
                         timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr
