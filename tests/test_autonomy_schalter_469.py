"""Autonomie-Schalter und Freigabe-Protokoll (Issue #469) — Tests zu AC-1 bis AC-15.

Spec: docs/specs/feat-469-autonomie-schalter.md

Festgelegte Vertraege (die Spec nennt sie nur sinngemaess):
- `workflow.autonomy_mode()` liest ueber `workflow.trusted_config()` (zur Laufzeit
  aufgeloest, damit ein Monkeypatch greift). Seit #470 (AC-1) nur die wirksame
  Config-Datei ohne `settings.local.json`; vorher `config_loader.load_config()`.
- `workflow.record_approval(data, gate, by, reason, evidence=None)` gibt den
  angehaengten Eintrag zurueck; Schluessel gate/by/mode/at/reason/evidence;
  `at` ist mit `datetime.fromisoformat` parsebar.
- CLI `workflow.py autonomy`: genau eine stdout-Zeile `AUTONOMY=<mode>`, Exit 0.
- `status` zeigt bei Eintraegen eine Zeile `Freigaben: <Anzahl>`; ohne Eintraege
  kommt das Wort `Freigaben` nicht vor.

Fehlende Funktionen erscheinen pro Test als FAIL (Import erst im Testkoerper).
"""

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
CI_GATE = REPO_ROOT / "scripts" / "ci_spec_gate.py"


# --- Helpers ---------------------------------------------------------------

def _project(tmp_path: Path, config_text=None) -> Path:
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    if config_text is not None:
        (proj / "openspec.yaml").write_text(config_text)
    return proj


def _auto_cfg(value="auto") -> str:
    return f"autonomy:\n  mode: {value}\n"


def _env(proj: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    return env


def _wf_cli(args, proj: Path, active: str = ""):
    env = _env(proj)
    if active:
        env["OPENSPEC_ACTIVE_WORKFLOW"] = active
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args],
                          capture_output=True, text=True, env=env,
                          cwd=str(proj), timeout=60)


def _wf_file(proj: Path, name: str) -> Path:
    return proj / ".claude" / "workflows" / f"{name}.json"


def _write_wf(proj: Path, name: str, phase: str = "phase6_implement", **fields):
    data = {"name": name, "workflow_type": "feature", "current_phase": phase,
            "phase_transitions": [], "phase_log": [], "spec_approved": True,
            "green_approved": True}
    data.update(fields)
    _wf_file(proj, name).write_text(json.dumps(data))
    (proj / ".claude" / "active_workflow").write_text(name)
    return data


@pytest.fixture
def inproc(tmp_path, monkeypatch):
    """In-Process-Zugriff auf workflow/config_loader mit frischem Cache."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("OPENSPEC_ACTIVE_WORKFLOW", raising=False)
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    import config_loader  # noqa: PLC0415
    import workflow  # noqa: PLC0415

    def reset():
        for fn in (config_loader.find_project_root, config_loader.load_config):
            clear = getattr(fn, "cache_clear", None)  # load_config kann gepatcht sein
            if clear:
                clear()

    reset()
    (tmp_path / ".git").mkdir(exist_ok=True)

    class Ctx:
        pass

    ctx = Ctx()
    ctx.root = tmp_path
    ctx.config_loader = config_loader
    ctx.workflow = workflow
    ctx.reset = reset
    yield ctx
    reset()


# --- AC-1 -------------------------------------------------------------------

def test_default_manual_without_section(inproc):
    """AC-1: ohne Abschnitt `autonomy` -> manual."""
    (inproc.root / "openspec.yaml").write_text("project:\n  name: x\n")
    inproc.reset()
    assert inproc.workflow.autonomy_mode() == "manual"


# --- AC-2 -------------------------------------------------------------------

def test_mode_auto_returns_auto(inproc):
    """AC-2: autonomy.mode: auto -> auto."""
    (inproc.root / "openspec.yaml").write_text(_auto_cfg("auto"))
    inproc.reset()
    assert inproc.workflow.autonomy_mode() == "auto"


# --- AC-3 -------------------------------------------------------------------

def test_other_values_fall_back_to_manual(inproc, monkeypatch):
    """AC-3: nur der exakte Literal "auto" schaltet an (fail-closed)."""
    wf = inproc.workflow
    bad_modes = ["AUTO", " auto", "auto ", True, 1, "yes", None, "manual"]
    failures = []
    for value in bad_modes:
        monkeypatch.setattr(inproc.workflow, "trusted_config",
                            lambda v=value: {"autonomy": {"mode": v}})
        got = wf.autonomy_mode()
        if got != "manual":
            failures.append((value, got))
    for section in ["auto", ["auto"], 5, True]:
        monkeypatch.setattr(inproc.workflow, "trusted_config",
                            lambda s=section: {"autonomy": s})
        got = wf.autonomy_mode()
        if got != "manual":
            failures.append((f"section={section!r}", got))
    # Gegenprobe: der Literal-String wirkt weiterhin (kein Dauer-manual).
    monkeypatch.setattr(inproc.workflow, "trusted_config",
                        lambda: {"autonomy": {"mode": "auto"}})
    assert wf.autonomy_mode() == "auto"
    assert not failures, failures


# --- AC-4 -------------------------------------------------------------------

def test_broken_config_falls_back_to_manual(inproc, monkeypatch):
    """AC-4: Ausnahme beim Config-Lesen oder kaputte YAML -> manual, kein Wurf."""
    wf = inproc.workflow

    def boom():
        raise RuntimeError("config kaputt")

    monkeypatch.setattr(inproc.workflow, "trusted_config", boom)
    assert wf.autonomy_mode() == "manual"
    monkeypatch.undo()

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(inproc.root))
    (inproc.root / "openspec.yaml").write_text("autonomy: [unclosed\n  - : :\nmode: auto\n")
    inproc.reset()
    assert wf.autonomy_mode() == "manual"


# --- AC-5 -------------------------------------------------------------------

def test_cli_prints_autonomy_line(tmp_path):
    """AC-5: `workflow.py autonomy` -> genau `AUTONOMY=auto|manual`, Exit 0."""
    proj_auto = _project(tmp_path / "a", _auto_cfg("auto"))
    r = _wf_cli(["autonomy"], proj_auto)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines() == ["AUTONOMY=auto"], r.stdout

    proj_none = _project(tmp_path / "b", "project:\n  name: x\n")
    r = _wf_cli(["autonomy"], proj_none)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines() == ["AUTONOMY=manual"], r.stdout


# --- AC-6 -------------------------------------------------------------------

def test_cli_exit_zero_on_error(tmp_path):
    """AC-6: kaputte Config und kein aktiver Workflow -> Exit 0, AUTONOMY=manual."""
    proj = _project(tmp_path, "autonomy: [unclosed\n  - : :\n")
    r = _wf_cli(["autonomy"], proj)
    assert r.returncode == 0, (r.returncode, r.stderr)
    assert r.stdout.strip().splitlines() == ["AUTONOMY=manual"], r.stdout


# --- AC-7 -------------------------------------------------------------------

def test_new_workflow_has_empty_approvals(tmp_path):
    """AC-7: `start` legt `"approvals": []` an."""
    proj = _project(tmp_path, "project:\n  name: x\n")
    r = _wf_cli(["start", "wf-469"], proj)
    assert r.returncode == 0, r.stderr
    state = json.loads(_wf_file(proj, "wf-469").read_text())
    assert state.get("approvals") == [], state.keys()


# --- AC-8 -------------------------------------------------------------------

def test_set_field_approvals_blocked(tmp_path):
    """AC-8: set-field approvals wird abgelehnt, State bleibt byte-gleich."""
    proj = _project(tmp_path, "project:\n  name: x\n")
    _write_wf(proj, "wf-469", approvals=[])
    before = _wf_file(proj, "wf-469").read_bytes()
    r = _wf_cli(["set-field", "approvals", "[]"], proj, active="wf-469")
    assert r.returncode != 0, (r.stdout, r.stderr)
    assert "record_approval" in (r.stderr + r.stdout), r.stderr
    assert _wf_file(proj, "wf-469").read_bytes() == before


# --- AC-9 -------------------------------------------------------------------

def test_record_approval_appends_entry(inproc, monkeypatch):
    """AC-9: Eintrag mit gate/by/mode/at/reason/evidence, haengt an."""
    monkeypatch.setattr(inproc.workflow, "trusted_config",
                        lambda: {"autonomy": {"mode": "auto"}})
    wf = inproc.workflow
    data = {"name": "x", "approvals": []}
    entry = wf.record_approval(data, "spec", "claude", "Grund",
                               evidence="docs/briefings/x.md")
    assert len(data["approvals"]) == 1
    e = data["approvals"][0]
    assert entry == e
    assert (e["gate"], e["by"], e["mode"], e["reason"], e["evidence"]) == (
        "spec", "claude", "auto", "Grund", "docs/briefings/x.md")
    datetime.fromisoformat(e["at"])  # ISO-Zeitstempel

    first = dict(e)
    e2 = wf.record_approval(data, "green", "user", "ok")
    assert len(data["approvals"]) == 2
    assert data["approvals"][0] == first
    assert data["approvals"][1]["evidence"] is None
    assert data["approvals"][1]["gate"] == "green"


# --- AC-10 ------------------------------------------------------------------

def test_record_approval_creates_missing_list(inproc, monkeypatch):
    """AC-10: fehlender Schluessel `approvals` wird angelegt."""
    monkeypatch.setattr(inproc.workflow, "trusted_config", lambda: {})
    data = {"name": "alt"}
    inproc.workflow.record_approval(data, "spec", "user", "Grund")
    assert isinstance(data.get("approvals"), list)
    assert len(data["approvals"]) == 1
    assert data["approvals"][0]["mode"] == "manual"


# --- AC-11 ------------------------------------------------------------------

def test_backstep_keeps_approvals(tmp_path):
    """AC-11: Ruecksprung nach phase3_spec behaelt approvals, setzt Marker zurueck."""
    proj = _project(tmp_path, "project:\n  name: x\n")
    entries = [{"gate": "spec", "by": "claude", "mode": "auto",
                "at": "2026-10-28T10:00:00", "reason": "r", "evidence": None}]
    _write_wf(proj, "wf-469", "phase6_implement", approvals=entries)
    r = _wf_cli(["phase", "phase3_spec"], proj, active="wf-469")
    assert r.returncode == 0, (r.stdout, r.stderr)
    state = json.loads(_wf_file(proj, "wf-469").read_text())
    assert state["current_phase"] == "phase3_spec"
    assert state["spec_approved"] is False
    assert state["green_approved"] is False
    assert state.get("approvals") == entries


# --- AC-12 ------------------------------------------------------------------

def test_status_shows_approvals(tmp_path):
    """AC-12: status zeigt Anzahl und je Eintrag Gate, Urheber, Modus, Zeit."""
    proj = _project(tmp_path, "project:\n  name: x\n")
    _write_wf(proj, "wf-469", approvals=[])
    base = _wf_cli(["status"], proj, active="wf-469")
    assert base.returncode == 0, base.stderr
    assert "Freigaben" not in base.stdout

    entries = [
        {"gate": "spec", "by": "claude", "mode": "auto",
         "at": "2026-10-28T10:00:00", "reason": "r1", "evidence": None},
        {"gate": "green", "by": "user", "mode": "manual",
         "at": "2026-10-28T11:30:00", "reason": "r2", "evidence": "e"},
    ]
    _write_wf(proj, "wf-469", approvals=entries)
    r = _wf_cli(["status"], proj, active="wf-469")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "Freigaben: 2" in out, out
    for e in entries:
        lines = [ln for ln in out.splitlines()
                 if e["gate"] in ln and e["by"] in ln and e["mode"] in ln
                 and e["at"] in ln]
        assert lines, (e, out)


# --- AC-13 ------------------------------------------------------------------

def test_autonomy_in_both_plugin_key_sets(inproc):
    """AC-13: `autonomy` in PLUGIN_CONFIG_KEYS und _FALLBACK_PLUGIN_KEYS, identisch."""
    spec = importlib.util.spec_from_file_location("ci_spec_gate_469", CI_GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    loader_keys = set(inproc.config_loader.PLUGIN_CONFIG_KEYS)
    fallback = set(gate._FALLBACK_PLUGIN_KEYS)
    assert "autonomy" in loader_keys
    assert "autonomy" in fallback
    assert loader_keys == fallback


# --- AC-14 ------------------------------------------------------------------

def test_config_yaml_default_is_manual():
    """AC-14: mitgelieferte config.yaml hat autonomy.mode == manual."""
    import yaml  # noqa: PLC0415
    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())
    assert isinstance(cfg.get("autonomy"), dict), cfg.get("autonomy")
    assert cfg["autonomy"].get("mode") == "manual"


# --- AC-15 ------------------------------------------------------------------

def test_no_gate_imports_autonomy_mode(inproc):
    """AC-15: kein Gate nutzt den Schalter; er existiert nur in workflow.py (+CLI)."""
    assert hasattr(inproc.workflow, "autonomy_mode")  # sonst triviales Gruen
    gates = ["edit_gate.py", "bash_gate.py", "phase_listener.py",
             "post_implementation_gate.py", "post_bash.py"]
    offenders = []
    for g in gates:
        text = (HOOKS_DIR / g).read_text()
        if "autonomy_mode" in text or "record_approval" in text:
            offenders.append(g)
    assert not offenders, offenders
