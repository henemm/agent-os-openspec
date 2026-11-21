"""Zeitschätzung: verlässlich statt früh, Viertelstunden, 80 % Sicherheit (Issue #642).

Spec: docs/specs/fix-642-zeitschaetzung.md (v1.1, AC-1 bis AC-8).

Ergänzt #620 (`tests/test_zeitschaetzung_620.py`) und #628
(`tests/test_arbeitszeit_628.py`):
- nur Archiv-Workflows mit Aktivitätsdatei („sauber“) bilden die Vergleichsgruppe
- ohne saubere Gruppe keine Zahl („Ende  offen“, „zu wenig Vergleichsdaten“)
- vor der Freigabe nur Start und „Freigabe  ca. HH:MM“ (Median, nächste Viertelstunde)
- ab der Freigabe „Ende  ca. A–B“ aus den Quantilen 0.1/0.9, A ab-, B aufgerundet
- Basiszeile „P % sicher, aus N Workflows“ (P nachgemessen, Leave-one-out) ab 10
- Zeitblock wird bei `width` umgebrochen statt gekappt

Alle Tests laufen in eigenen tmp-Projekten; die Uhr wird über
`workflow._estimate_now` ersetzt. Anzeigezone `local`, damit die erwarteten
Uhrzeiten unabhängig von der Systemzone des Testrechners sind.
"""

import json
import os
import re
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

# Standard-Config OHNE `quantiles`: es gilt der neue Standard [0.1, 0.9] (AC-4).
CONFIG = """time_estimate:
  enabled: true
  min_samples: 3
  display_timezone: local
"""
TIME_PREFIXES = ("Start  ", "Dauer  ", "Ende  ", "Freigabe  ")
# Nicht auf einer Viertelstunde, damit Runden sichtbar wird.
NOW = datetime(2026, 11, 21, 14, 7, 0)
HIST_START = datetime(2026, 11, 1, 9, 0)


# --- Helpers ---------------------------------------------------------------

def _wf():
    sys.path.insert(0, str(HOOKS_DIR))
    import workflow  # noqa: PLC0415
    return workflow


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _reset_config_cache():
    sys.path.insert(0, str(HOOKS_DIR))
    import config_loader  # noqa: PLC0415
    for fn in (config_loader.find_project_root, config_loader.load_config):
        clear = getattr(fn, "cache_clear", None)
        if clear:
            clear()


def _project(root: Path, config: "str | None" = CONFIG) -> Path:
    proj = root / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_archive").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_activity").mkdir(parents=True)
    (proj / "_home").mkdir()
    if config is not None:
        (proj / "openspec.yaml").write_text(config)
    return proj


@pytest.fixture(autouse=True)
def proj(tmp_path, monkeypatch):
    """Jeder Test läuft in einem eigenen tmp-Projekt, nie im echten Archiv."""
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


def _case(tmp_path: Path, label: str, config: "str | None" = CONFIG):
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


def _activity_dir(project: Path) -> Path:
    return _workflows(project) / "_activity"


def _clear_history(project: Path) -> None:
    for folder in (_archive(project), _activity_dir(project)):
        for f in folder.glob("*.json"):
            f.unlink()


def _seg(phase: str, start: datetime, end: "datetime | None", dur=None) -> dict:
    if end is None:
        return {"phase": phase, "entered_at": _iso(start), "exited_at": None,
                "duration_min": None}
    minutes = round((end - start).total_seconds() / 60, 1) if dur is None else dur
    return {"phase": phase, "entered_at": _iso(start), "exited_at": _iso(end),
            "duration_min": float(minutes)}


def _archived(name: str, phases: dict, start: datetime = HIST_START, **fields) -> dict:
    """Archiv-Workflow mit lückenlosem `phase_log` aus `phases` (Minuten)."""
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


def _clean(project: Path, name: str, phases: dict) -> None:
    """Sauberer Archiv-Workflow: Archivdatei UND Aktivitätsdatei (#628).

    Das `phase_log` trägt absichtlich Wanduhr-Minuten mit 8 h Leerlauf in
    phase6; zählen darf nur die Aktivitätsdatei.
    """
    wall = {p: float(m) for p, m in phases.items()}
    wall[P6] = wall.get(P6, 0.0) + 480.0
    _write_archived(project, _archived(name, wall))
    (_activity_dir(project) / f"{name}.json").write_text(json.dumps(
        {"last": "2026-11-01T18:00:00", "phases": {p: float(m) for p, m in phases.items()}}))


def _dirty(project: Path, name: str, phases: dict) -> None:
    """Alt-Workflow ohne Aktivitätsdatei (nur `phase_log`)."""
    _write_archived(project, _archived(name, phases))


def _running(name: str, phase: str, created: datetime, entered: datetime,
             **fields) -> dict:
    """Laufender Workflow in `phase`, seit `entered` (offenes Segment)."""
    data = {"name": name, "workflow_type": "feature", "current_phase": phase,
            "created": _iso(created), "last_updated": _iso(entered),
            "phase_transitions": [],
            "phase_log": [_seg(P1, created, entered), _seg(phase, entered, None)]}
    data.update(fields)
    return data


def _write_active(project: Path, data: dict) -> Path:
    path = _workflows(project) / f"{data['name']}.json"
    path.write_text(json.dumps(data))
    (project / ".claude" / "active_workflow").write_text(data["name"])
    return path


def _workflow(args, env, cwd, timeout: float = 30):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args], capture_output=True,
                          text=True, env=env, cwd=str(cwd), timeout=timeout)


def _kv(text: str, key: str) -> "str | None":
    for line in text.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _time_lines(text: str) -> list:
    return [ln for ln in text.splitlines() if ln.startswith(TIME_PREFIXES)]


def _line(text: str, prefix: str) -> "str | None":
    return next((ln for ln in text.splitlines() if ln.startswith(prefix)), None)


def _stripped(text: str) -> list:
    return [ln.strip() for ln in text.splitlines()]


def _plan(wf, monkeypatch, data, now=NOW, width=None) -> "tuple[str, dict]":
    monkeypatch.setattr(wf, "_estimate_now", lambda: now)
    est = wf.current_estimate(dict(data))
    assert isinstance(est, dict), est
    return wf.render_plan(data, width=width, estimate=est), est


def _kv_lines(wf, est) -> str:
    return "\n".join(wf._estimate_kv_lines(est))


def _naive(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=None)


# Phasen eines Vergleichs-Workflows: P1–P3 fest, Rest ab Freigabe in P6.
def _phases_rest(rest: float) -> dict:
    return {P1: 10, P2: 10, P3: 10, P6: rest}


# =============================================================================
# AC-1: Vergleichsgruppe nur aus Workflows mit Aktivitätsdatei
# =============================================================================

CLEAN_A = {"wf-clean-1": {P1: 10, P2: 10, P3: 15, P4: 1, P5: 10, P6: 30, P6B: 10, P7: 5},
           "wf-clean-2": {P1: 12, P2: 8, P3: 20, P4: 1, P5: 12, P6: 40, P6B: 8, P7: 4},
           "wf-clean-3": {P1: 8, P2: 12, P3: 25, P4: 1, P5: 8, P6: 50, P6B: 12, P7: 6}}


def test_gruppe_nur_workflows_mit_aktivitaet(proj, monkeypatch):
    wf = _wf()
    for name, phases in CLEAN_A.items():
        _clean(proj, name, phases)
    old = {P1: 10, P2: 10, P3: 15, P4: 1, P5: 10, P6: 30, P6B: 10, P7: 5}
    for i in range(4):
        _dirty(proj, f"wf-alt-{i}", old)
    # Alt-Workflow mit 10-h-Nachtsegment in phase6 (600 min Leerlauf)
    _dirty(proj, "wf-alt-nacht", dict(old, **{P6: 600}))

    history = wf.load_archive_phase_durations(_archive(proj))
    assert len(history) == 8, history
    assert sum(1 for h in history if h.get("clean") is True) == 3, history
    assert sum(1 for h in history if h.get("clean") is False) == 5, history
    # Saubere Einträge rechnen mit den Aktivminuten, nicht mit dem phase_log
    clean_phases = sorted(sorted((k, round(float(v), 1)) for k, v in h["phases"].items())
                          for h in history if h.get("clean") is True)
    expected = sorted(sorted((k, float(v)) for k, v in p.items()) for p in CLEAN_A.values())
    assert clean_phases == expected, clean_phases

    data = _running("wf-642-gruppe", P5, NOW - timedelta(minutes=60), NOW)
    group = wf._estimate_group(data, history, 3)
    assert len(group) == 3, group
    assert all(g.get("clean") is True for g in group), group

    # Das Nachtsegment beeinflusst keine Spanne: identisch zur Schätzung, die nur
    # die drei sauberen Workflows kennt.
    cfg = wf.time_estimate_config()
    assert cfg is not None
    est_all = wf.estimate_remaining(dict(data), history, cfg, NOW)
    est_clean = wf.estimate_remaining(
        dict(data), [h for h in history if h.get("clean") is True], cfg, NOW)
    assert isinstance(est_all, dict) and isinstance(est_clean, dict)
    assert est_all["n"] == 3, est_all
    assert est_all["end_low"] == est_clean["end_low"], (est_all, est_clean)
    assert est_all["end_high"] == est_clean["end_high"], (est_all, est_clean)
    # Rest ab phase5 der sauberen: 55, 64, 76 min; nie in der Nähe von 600 min
    assert est_all["end_high"] <= NOW + timedelta(minutes=90), est_all["end_high"]


# =============================================================================
# AC-2: ohne saubere Daten keine Zahl
# =============================================================================

def test_ohne_saubere_daten_keine_zahl(proj, monkeypatch, tmp_path):
    wf = _wf()
    # 2 saubere (< min_samples 3) und 5 alte ohne Aktivitätsdatei
    for name in ("wf-clean-1", "wf-clean-2"):
        _clean(proj, name, CLEAN_A[name])
    for i in range(5):
        _dirty(proj, f"wf-alt-{i}", CLEAN_A["wf-clean-1"])

    data = _running("wf-642-leer", P6, NOW - timedelta(minutes=50), NOW - timedelta(minutes=10))
    out, est = _plan(wf, monkeypatch, data)
    assert est["n"] == 0, est
    assert est["source"] == "none", est
    assert est.get("end_low") is None and est.get("end_high") is None, est
    assert est.get("approval") is None, est

    times = _time_lines(out)
    assert _line(out, "Start  ") is not None, out
    assert "Ende  offen" in times, out
    assert "zu wenig Vergleichsdaten" in _stripped(out), out
    assert not any("–" in ln for ln in times), out          # keine Uhrzeit-Spanne
    assert _line(out, "Dauer  ") is None, out
    assert "Startwert" not in out, out

    # CLI: Plan und estimate im eigenen Projekt
    project, env = _case(tmp_path, "cli-leer")
    for name in ("wf-clean-1", "wf-clean-2"):
        _clean(project, name, CLEAN_A[name])
    for i in range(5):
        _dirty(project, f"wf-alt-{i}", CLEAN_A["wf-clean-1"])
    real_now = datetime.now()
    _write_active(project, _running("wf-642-leer", P6, real_now - timedelta(minutes=50),
                                    real_now - timedelta(minutes=10)))
    plan = _workflow(["plan"], env, project)
    assert plan.returncode == 0 and "Traceback" not in plan.stderr, plan.stderr
    assert "Ende  offen" in _time_lines(plan.stdout), plan.stdout
    assert "zu wenig Vergleichsdaten" in _stripped(plan.stdout), plan.stdout
    assert "Startwert" not in plan.stdout, plan.stdout

    cli = _workflow(["estimate"], env, project)
    assert cli.returncode == 0 and "Traceback" not in cli.stderr, cli.stderr
    assert _kv(cli.stdout, "ESTIMATE") == "on", cli.stdout
    assert _kv(cli.stdout, "LINE") == "Noch keine Zeitschätzung: zu wenig Vergleichsdaten", \
        cli.stdout
    for key in ("ESTIMATE_LOW_MIN", "ESTIMATE_HIGH_MIN", "ESTIMATE_END_LOW",
                "ESTIMATE_END_HIGH"):
        assert _kv(cli.stdout, key) is None, (key, cli.stdout)
    assert "Startwert" not in cli.stdout, cli.stdout


# =============================================================================
# AC-3: vor der Freigabe nur Start und Freigabezeit
# =============================================================================

# Restarbeit bis zur Freigabe je Vergleichs-Workflow (laufende Phase phase2 seit
# 5 min): max(0, P2 - 5) + P3 = 25, 45, 125 -> Median 45 (Mittelwert wäre 65).
# 14:07 + 45 = 14:52 -> nächste Viertelstunde 14:45 (Aufrunden gäbe 15:00).
CLEAN_PRE = {"wf-pre-1": {P1: 10, P2: 10, P3: 20, P4: 1, P5: 10, P6: 30, P6B: 10, P7: 5},
             "wf-pre-2": {P1: 10, P2: 20, P3: 30, P4: 1, P5: 10, P6: 30, P6B: 10, P7: 5},
             "wf-pre-3": {P1: 10, P2: 30, P3: 100, P4: 1, P5: 10, P6: 30, P6B: 10, P7: 5}}
PRE_CREATED = datetime(2026, 11, 21, 13, 41)


def test_vor_freigabe_nur_start_und_freigabezeit(proj, monkeypatch):
    wf = _wf()
    for name, phases in CLEAN_PRE.items():
        _clean(proj, name, phases)

    data = _running("wf-642-p2", P2, PRE_CREATED, NOW - timedelta(minutes=5))
    out, est = _plan(wf, monkeypatch, data)
    times = _time_lines(out)
    assert "Start  13:41" in times, out
    assert "Freigabe  ca. 14:45" in times, out
    assert re.search(r":(00|15|30|45)$", _line(out, "Freigabe  ")), out
    assert _line(out, "Ende  ") is None, out
    assert _line(out, "Dauer  ") is None, out
    assert "aus 3 Workflows" in _stripped(out), out
    assert est.get("approval") == datetime(2026, 11, 21, 14, 45), est
    assert est.get("end_low") is None and est.get("end_high") is None, est

    # Wartet die menschliche Freigabe (Briefing registriert, Ampel rot):
    waiting = _running("wf-642-p3", P3, PRE_CREATED, NOW - timedelta(minutes=20),
                       po_briefing={"created": _iso(NOW - timedelta(minutes=10)),
                                    "ampel": "red", "file": "docs/briefings/x.md"})
    assert wf.awaiting_human_approval(waiting) is True
    out2, _est2 = _plan(wf, monkeypatch, waiting)
    times2 = _time_lines(out2)
    assert "Freigabe  wartet auf dich" in times2, out2
    assert not any(ln.startswith("Freigabe  ca.") for ln in times2), out2
    assert _line(out2, "Ende  ") is None, out2
    assert _line(out2, "Dauer  ") is None, out2
    assert "Wartezeit auf dich" not in out2, out2


# =============================================================================
# AC-4: Ende-Spanne auf Viertelstunden aus den Quantilen 0.1/0.9
# =============================================================================

# Rest ab phase5 (seit 0 min) je Vergleichs-Workflow: 45, 55, 60, 75, 195.
# Quantil 0.1: Pos 0.4 -> 45 + 0.4*10 = 49  -> 14:56 -> abgerundet 14:45
#   (nächste Viertelstunde wäre 15:00)
# Quantil 0.9: Pos 3.6 -> 75 + 0.6*120 = 147 -> 16:34 -> aufgerundet 16:45
#   (nächste Viertelstunde wäre 16:30)
# Alte Quantile 0.25/0.75 gäben 55/75 -> 15:00–15:30.
RESTS_AC4 = [45, 55, 60, 75, 195]


def _phases_from_p5(rest: float) -> dict:
    return {P1: 10, P2: 10, P3: 10, P4: 1, P5: 5, P6: rest - 15, P6B: 5, P7: 5}


def test_ende_spanne_viertelstunden_quantile(proj, monkeypatch):
    wf = _wf()
    # Neuer Standard ohne Override und in der Projekt-config.yaml: [0.1, 0.9]
    assert wf.time_estimate_config()["quantiles"] in ([0.1, 0.9], (0.1, 0.9))
    import yaml  # noqa: PLC0415
    repo_cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())["time_estimate"]
    assert list(wf._valid_estimate_config(repo_cfg)["quantiles"]) == [0.1, 0.9], repo_cfg

    for i, rest in enumerate(RESTS_AC4):
        _clean(proj, f"wf-q-{i}", _phases_from_p5(rest))
    data = _running("wf-642-p5", P5, datetime(2026, 11, 21, 13, 30), NOW)
    out, est = _plan(wf, monkeypatch, data)
    times = _time_lines(out)
    assert "Ende  ca. 14:45–16:45" in times, out
    assert _line(out, "Dauer  ") is None, out
    assert _line(out, "Freigabe  ") is None, out
    assert "aus 5 Workflows" in _stripped(out), out
    assert est["end_low"] == datetime(2026, 11, 21, 14, 45), est
    assert est["end_high"] == datetime(2026, 11, 21, 16, 45), est

    # A = B: alle Rest 53 min -> 14:07 + 53 = 15:00 -> eine einzige Uhrzeit
    _clear_history(proj)
    for i in range(3):
        _clean(proj, f"wf-gleich-{i}", _phases_from_p5(53))
    out2, est2 = _plan(wf, monkeypatch, data)
    assert "Ende  ca. 15:00" in _time_lines(out2), out2
    assert _line(out2, "Dauer  ") is None, out2


# =============================================================================
# AC-5: Basiszeile mit nachgemessener Prozentzahl erst ab 10 Vergleichen
# =============================================================================

def _loo_hits(rests: list, q_low: float = 0.1, q_high: float = 0.9) -> int:
    """Nachrechnung im Test: für jeden Workflow i die Spanne aus den übrigen
    (lineare Interpolation wie `_quantile`), Treffer, wenn Rest i darin liegt."""
    def q(values, p):
        values = sorted(values)
        pos = (len(values) - 1) * p
        lo = int(pos)
        hi = min(lo + 1, len(values) - 1)
        return values[lo] + (values[hi] - values[lo]) * (pos - lo)
    hits = 0
    for i, r in enumerate(rests):
        others = rests[:i] + rests[i + 1:]
        if q(others, q_low) <= r <= q(others, q_high):
            hits += 1
    return hits


# 8 von 10: v0 und v9 fallen heraus (aus den übrigen 9: Spanne 30.8–84.8 bzw.
# 26–80.2), v1..v8 liegen in ihrer Spanne (z. B. v8=81 in 26–84).
RESTS_8_OF_10 = [10, 30, 31, 40, 50, 60, 70, 80, 81, 100]
# 7 von 10: zusätzlich v1=12 außerhalb (Spanne aus den übrigen: 26.8–84.8).
# Belegt, dass P gemessen und nicht aus der Quantilbreite (80 %) angenommen ist.
RESTS_7_OF_10 = [10, 12, 31, 40, 50, 60, 70, 80, 81, 100]


def test_basiszeile_prozent_erst_ab_zehn(proj, monkeypatch):
    wf = _wf()
    assert _loo_hits(RESTS_8_OF_10) == 8
    assert _loo_hits(RESTS_7_OF_10) == 7

    data = _running("wf-642-p5", P5, datetime(2026, 11, 21, 13, 30), NOW)

    def render(rests):
        _clear_history(proj)
        for i, rest in enumerate(rests):
            _clean(proj, f"wf-loo-{i:02d}", _phases_rest(rest))
        out, _est = _plan(wf, monkeypatch, data)
        return out

    out8 = render(RESTS_8_OF_10)
    assert "80 % sicher, aus 10 Workflows" in _stripped(out8), out8

    out7 = render(RESTS_7_OF_10)
    assert "70 % sicher, aus 10 Workflows" in _stripped(out7), out7

    out9 = render(RESTS_8_OF_10[:9])
    assert "aus 9 Workflows" in _stripped(out9), out9
    assert "%" not in out9, out9


# =============================================================================
# AC-6: Zeitblock wird umgebrochen, nicht gekappt
# =============================================================================

def test_zeitblock_umbrochen_nicht_gekappt(proj, monkeypatch):
    wf = _wf()
    for i in range(32):
        _clean(proj, f"wf-w-{i:02d}", _phases_rest(20 + 3 * i))
    data = _running("wf-642-schmal", P5, datetime(2026, 11, 21, 13, 30), NOW,
                    issue_title="Zeitschätzung: verlässlich statt früh")
    out, est = _plan(wf, monkeypatch, data, width=34)
    assert est["n"] == 32, est
    too_long = [ln for ln in out.splitlines() if len(ln) > 34]
    assert not too_long, too_long
    joined = " ".join(out.split())
    assert "aus 32 Workflows" in joined, out
    assert "% sicher, aus 32 Workflows" in joined, out
    assert _line(out, "Ende  ca. ") is not None, out
    # Das Plan-Pane ist ~34 Zeichen breit: die Basiszeile steht dort als EINE Zeile
    basis = [ln for ln in out.splitlines()
             if re.fullmatch(r" *\d{1,3} % sicher, aus 32 Workflows", ln)]
    assert len(basis) == 1, out
    # Auch der breiteste Fall (3-stellige Prozent- und Workflow-Zahl) passt
    widest = wf._wrap_time_line(wf.TIME_INDENT + "100 % sicher, aus 120 Workflows", 34)
    assert len(widest) == 1, widest


# =============================================================================
# AC-7: workflow.py estimate — Schlüssel und LINE=
# =============================================================================

def test_estimate_cli_line_und_schluessel(proj, monkeypatch, tmp_path):
    wf = _wf()

    # (a) vor der Freigabe, in-process mit fester Uhr (Daten aus AC-3)
    for name, phases in CLEAN_PRE.items():
        _clean(proj, name, phases)
    pre = _running("wf-642-p2", P2, PRE_CREATED, NOW - timedelta(minutes=5))
    _out, est = _plan(wf, monkeypatch, pre)
    kv = _kv_lines(wf, est)
    assert _kv(kv, "ESTIMATE") == "on", kv
    assert _kv(kv, "ESTIMATE_APPROVAL") is not None, kv
    assert _naive(_kv(kv, "ESTIMATE_APPROVAL")) == datetime(2026, 11, 21, 14, 45), kv
    assert _kv(kv, "ESTIMATE_START") is not None, kv
    assert _kv(kv, "ESTIMATE_BASIS") is not None, kv
    for key in ("ESTIMATE_END_LOW", "ESTIMATE_END_HIGH", "ESTIMATE_LOW_MIN",
                "ESTIMATE_HIGH_MIN"):
        assert _kv(kv, key) is None, (key, kv)
    assert _kv(kv, "LINE") == "Start 13:41, Freigabe ca. 14:45 (aus 3 Workflows)", kv

    # (b) nach der Freigabe, in-process (Daten aus AC-4)
    _clear_history(proj)
    for i, rest in enumerate(RESTS_AC4):
        _clean(proj, f"wf-q-{i}", _phases_from_p5(rest))
    post = _running("wf-642-p5", P5, datetime(2026, 11, 21, 13, 30), NOW)
    _out, est = _plan(wf, monkeypatch, post)
    kv = _kv_lines(wf, est)
    assert _naive(_kv(kv, "ESTIMATE_END_LOW")) == datetime(2026, 11, 21, 14, 45), kv
    assert _naive(_kv(kv, "ESTIMATE_END_HIGH")) == datetime(2026, 11, 21, 16, 45), kv
    assert _kv(kv, "ESTIMATE_APPROVAL") is None, kv
    line = _kv(kv, "LINE")
    assert line == "Ende ca. 14:45–16:45 (aus 5 Workflows)", kv
    assert not re.search(r"\d+ (h|min)\b", line), line   # keine Minutenspanne der Dauer

    # (c) ab 10 Vergleichen mit nachgemessener Prozentzahl (8 von 10)
    _clear_history(proj)
    for i, rest in enumerate(RESTS_8_OF_10):
        _clean(proj, f"wf-loo-{i:02d}", _phases_rest(rest))
    _out, est = _plan(wf, monkeypatch, post)
    line = _kv(_kv_lines(wf, est), "LINE")
    assert re.fullmatch(r"Ende ca\. \d\d:(00|15|30|45)(–\d\d:(00|15|30|45))? "
                        r"\(80 % sicher, aus 10 Workflows\)", line or ""), line

    # (d) CLI als Subprozess (echte Uhr): Schlüssel und Format
    clock = r"(\d\d\.\d\d\. )?\d\d:\d\d"
    quarter = r"(\d\d\.\d\d\. )?\d\d:(00|15|30|45)"
    real_now = datetime.now()
    project, env = _case(tmp_path, "cli-vor")
    for name, phases in CLEAN_PRE.items():
        _clean(project, name, phases)
    _write_active(project, _running("wf-642-p2", P2, real_now - timedelta(minutes=30),
                                    real_now - timedelta(minutes=5)))
    res = _workflow(["estimate"], env, project)
    assert res.returncode == 0 and "Traceback" not in res.stderr, res.stderr
    assert _kv(res.stdout, "ESTIMATE_APPROVAL") is not None, res.stdout
    assert _kv(res.stdout, "ESTIMATE_END_LOW") is None, res.stdout
    assert re.fullmatch(rf"Start {clock}, Freigabe ca\. {quarter} \(aus 3 Workflows\)",
                        _kv(res.stdout, "LINE") or ""), res.stdout

    project, env = _case(tmp_path, "cli-nach")
    for i, rest in enumerate(RESTS_AC4):
        _clean(project, f"wf-q-{i}", _phases_from_p5(rest))
    _write_active(project, _running("wf-642-p5", P5, real_now - timedelta(minutes=40),
                                    real_now))
    res = _workflow(["estimate"], env, project)
    assert res.returncode == 0 and "Traceback" not in res.stderr, res.stderr
    assert _kv(res.stdout, "ESTIMATE_END_LOW") is not None, res.stdout
    assert _kv(res.stdout, "ESTIMATE_END_HIGH") is not None, res.stdout
    assert _kv(res.stdout, "ESTIMATE_APPROVAL") is None, res.stdout
    assert re.fullmatch(rf"Ende ca\. {quarter}(–{quarter})? \(aus 5 Workflows\)",
                        _kv(res.stdout, "LINE") or ""), res.stdout


# =============================================================================
# AC-8: fail-open, Ist-Block unverändert
# =============================================================================

def _ist_data() -> dict:
    """Fertiger Workflow aus #628 AC-7: Arbeitszeit 70 min, gesamt 9 h 2 min."""
    start = datetime(2026, 11, 20, 21, 0)
    m = lambda k: start + timedelta(minutes=k)  # noqa: E731
    approve = m(40) + timedelta(minutes=472)
    log = [_seg(P1, m(0), m(20)), _seg(P2, m(20), m(30)), _seg(P3, m(30), m(40)),
           _seg(P3, m(40), approve)]
    t = approve
    for phase, minutes in ((P4, 2), (P5, 10), (P6, 10), (P7, 8)):
        log.append(_seg(phase, t, t + timedelta(minutes=minutes)))
        t += timedelta(minutes=minutes)
    return {"name": "wf-ist", "workflow_type": "feature", "current_phase": P8,
            "created": _iso(start), "phase_log": log, "ship_status": "done",
            "phase_transitions": [{"from": P3, "to": P4, "at": _iso(approve),
                                   "trigger": "approval"}],
            "po_briefing": {"created": m(40).isoformat(timespec="seconds"),
                            "ampel": "red", "file": "docs/briefings/wf-ist.md"}}


def test_fail_open_und_ist_block_unveraendert(proj, monkeypatch, tmp_path):
    wf = _wf()
    monkeypatch.setattr(wf, "_estimate_now", lambda: NOW)

    # (1) Leeres Archiv: keine Ausnahme, keine Zahl
    data = _running("wf-642-kaputt", P6, NOW - timedelta(minutes=50),
                    NOW - timedelta(minutes=10))
    est = wf.current_estimate(dict(data))
    assert isinstance(est, dict), est
    assert est["n"] == 0 and est["source"] == "none", est
    out = wf.render_plan(data, estimate=est)
    assert "Ende  offen" in _time_lines(out), out
    assert "zu wenig Vergleichsdaten" in _stripped(out), out
    _kv_lines(wf, est)  # wirft nicht
    out_narrow = wf.render_plan(data, width=34, estimate=est)
    assert all(len(ln) <= 34 for ln in out_narrow.splitlines()), out_narrow

    # (2) Kaputte Aktivitätsdateien: Archiv-Eintrag zählt nicht als sauber,
    #     der laufende Workflow wirft nie
    for name, phases in CLEAN_A.items():
        _clean(proj, name, phases)
    _write_archived(proj, _archived("wf-kaputt-akt", CLEAN_A["wf-clean-1"]))
    (_activity_dir(proj) / "wf-kaputt-akt.json").write_text("{kaputt")
    (_activity_dir(proj) / "wf-642-kaputt.json").write_text("{kaputt")
    history = wf.load_archive_phase_durations(_archive(proj))
    broken = [h for h in history if h.get("clean") is not True]
    assert len(broken) == 1 and len(history) == 4, history
    est = wf.current_estimate(dict(data))
    assert isinstance(est, dict) and est["n"] == 3, est
    wf.render_plan(data, estimate=est)
    _kv_lines(wf, est)

    # (3) Ungültige Zeitstempel im Archiv und im laufenden Workflow
    bad = _archived("wf-kaputt-zeit", CLEAN_A["wf-clean-2"], created="kaputt")
    for seg in bad["phase_log"]:
        seg["entered_at"] = "kaputt"
    _write_archived(proj, bad)
    (_activity_dir(proj) / "wf-kaputt-zeit.json").write_text(json.dumps(
        {"last": "kaputt", "phases": {P1: 5.0, P6: "x"}}))
    wf.load_archive_phase_durations(_archive(proj))
    broken_ts = dict(data, po_briefing={"created": "kaputt", "ampel": "red"},
                     phase_transitions=[{"from": P3, "to": P4, "at": "kaputt",
                                         "trigger": "approval"}])
    for variant in (broken_ts, dict(data, created="kaputt"),
                    dict(data, phase_log=[{"phase": P6, "entered_at": "kaputt",
                                           "exited_at": None}])):
        res = wf.current_estimate(dict(variant))
        wf.render_plan(variant, estimate=res)
        wf.render_plan(variant, width=34, estimate=res)
        if isinstance(res, dict) and not res.get("actual"):
            _kv_lines(wf, res)

    # (4) CLI mit leerem Archiv und kaputter Aktivitätsdatei: kein Traceback
    project, env = _case(tmp_path, "cli-kaputt")
    real_now = datetime.now()
    _write_active(project, _running("wf-642-kaputt", P6, real_now - timedelta(minutes=50),
                                    real_now - timedelta(minutes=10)))
    (_activity_dir(project) / "wf-642-kaputt.json").write_text("{kaputt")
    for args in (["plan"], ["estimate"]):
        res = _workflow(args, env, project)
        assert res.returncode == 0 and "Traceback" not in res.stderr, (args, res.stderr)
    est_cli = _workflow(["estimate"], env, project)
    assert _kv(est_cli.stdout, "LINE") == \
        "Noch keine Zeitschätzung: zu wenig Vergleichsdaten", est_cli.stdout

    # (5) Ist-Block eines fertigen Workflows exakt wie in #628
    ist = _ist_data()
    est_ist = wf.current_estimate(dict(ist), archived=True)
    assert est_ist.get("actual") is True, est_ist
    out_ist = wf.render_plan(ist, archived=True, estimate=est_ist)
    assert _time_lines(out_ist) == ["Start  20.11. 21:00",
                                    "Dauer  1 h 10 min (gesamt 9 h 2 min)",
                                    "Ende  06:02"], out_ist
