"""Phasenkette im Auto-Modus flach fortsetzen, Auto-/clear stillgelegt (Issue #662).

Spec: docs/specs/feat-662-kette-flach.md (AC-1 bis AC-6, AC-8; AC-7 und AC-9 in
tests/test_context_stop_658.py, AC-10 in tests/test_clear_checkpoint_blocks.py).

Neu: Herdr tippt nie mehr `/clear` und den Folgebefehl. `herdr_bridge.auto_clear_active()`
liefert immer False, `maybe_auto_clear` (Stop-Hook) spawnt nie, kein Phasenwechsel
schreibt `auto_clear_boundary`, `workflow.py autoclear` sagt immer `AUTO_CLEAR=off`,
`CONTEXT_STOP=on` nur noch im Modus manual; die Befehlstexte 10 bis 50 verlieren den
Herdr-Absatz.

#663 (docs/specs/chore-663-rueckbau-autoclear.md): Der Auto-/clear-Code ist geloescht.
AC-1 prueft deshalb, dass die Symbole nicht mehr existieren (statt `auto_clear_active()`
fest False); der Stop-Hook-Test prueft nur noch den echten Hook (kein Runner, kein
Log, kein Signal-Ordner) statt `maybe_auto_clear` direkt.

Jedes Szenario schaltet Auto-/clear nach dem bisherigen Massstab EIN (Herdr-Pane mit
Stub-Binary, Config `herdr.auto_clear.enabled: true` und/oder Env
`OPENSPEC_HERDR_AUTO_CLEAR=1`); seit #663 gibt es keine Bridge-Funktion mehr, die das
bestaetigen koennte, der Aufbau setzt Config und Env daher direkt. Die Test-Env
entfernt alle geerbten `OPENSPEC_*`/`HERDR_*`/`CLAUDE_*` und setzt Autonomie, Herdr
und Sitzung explizit (die Cloud-Umgebung setzt `OPENSPEC_AUTONOMY=auto`).

Bewusst eigenstaendig: keine Importe aus anderen Testdateien.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "core" / "hooks"
COMMANDS = REPO / "core" / "commands"
SKILLS = REPO / "skills"
WORKFLOW = HOOKS / "workflow.py"
FOOTER_GATE = HOOKS / "footer_gate.py"
LISTENER = HOOKS / "phase_listener.py"
SYNC = REPO / "scripts" / "sync_skills.py"

PANE = "pane-662"
WF = "feat-662-kette-demo"
ISSUE = "#662"
PHASE = "phase6_implement"
CMD = f"/50-implement {ISSUE}"
SESSION = "sess-662"

# Ein Stub, der jeden Aufruf NUL-getrennt in STUB_LOG protokolliert: jeder Spawn eines
# Runners faellt hier auf (der Runner ruft zuerst `notification show` bzw. tippt).
STUB = r"""#!/bin/bash
{ for a in "$@"; do printf '%s\0' "$a"; done; printf '\n'; } >> "$STUB_LOG"
exit 0
"""

# Auto-/clear nach altem Massstab EIN; grace 0 und announce true: ein gestarteter
# Runner riefe den Stub sofort auf.
CLEAR_CFG = ("herdr:\n  enabled: true\n  auto_clear:\n    enabled: true\n"
             "    grace_s: 0\n    idle_timeout_s: 5\n    announce: true\n")
HERDR_ONLY_CFG = "herdr:\n  enabled: true\n"
NO_GATES = "po_briefing_gate:\n  enabled: false\nsession_banner:\n  behind_check: false\n"
BUDGET_CFG = ("context_budget:\n  enabled: true\n  clear_threshold_tokens: 100000\n")

# Zwei Wege, Auto-/clear einzuschalten (#480): Projekt-Config oder Env-Schalter
SWITCHES = {
    "config": (CLEAR_CFG, None),
    "env": (HERDR_ONLY_CFG, "1"),
    "config+env": (CLEAR_CFG, "1"),
}

POSITIVE = "✅ **`/clear` ist jetzt gefahrlos** — alles auf Platte gesichert."


# --- Gemeinsame Helfer ----------------------------------------------------------

def _stub(root: Path) -> Path:
    stub = root / "herdr-stub"
    stub.write_text(STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _clean_env() -> dict:
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("OPENSPEC_", "HERDR_", "STUB_", "CLAUDE_"))}


def _calls(log: Path) -> list:
    if not log.exists():
        return []
    return [ln.split("\0") for ln in log.read_bytes().decode("utf-8", "replace").split("\n")
            if ln]


def _boundary(phase: str = PHASE, command: str = CMD) -> dict:
    return {"phase": phase, "command": command, "at": datetime.now().astimezone().isoformat()}


class Proj:
    """Isoliertes Projekt (Hooks aus dem Repo) mit Workflow-State und Herdr-Stub."""

    def __init__(self, tmp_path: Path, label: str, *, phase: str = PHASE,
                 config: str = CLEAR_CFG, switch: "str | None" = None,
                 autonomy: "str | None" = "auto", herdr: bool = True,
                 workflow: bool = True, **fields):
        self.root = tmp_path / label
        self.root.mkdir(parents=True)
        self.proj = self.root / "proj"
        (self.proj / ".git").mkdir(parents=True)
        (self.proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
        (self.proj / "_home").mkdir()
        (self.proj / "config.yaml").write_text(config + NO_GATES)
        if workflow:
            data = {"name": WF, "workflow_type": "feature", "current_phase": phase,
                    "phase_transitions": [], "phase_log": [], "approvals": []}
            data.update(fields)
            self.wf_file.write_text(json.dumps(data))
            (self.proj / ".claude" / "active_workflow").write_text(WF)
        self.log = self.root / "stub.log"
        env = _clean_env()
        env.update({"CLAUDE_PROJECT_DIR": str(self.proj), "HOME": str(self.proj / "_home"),
                    "CLAUDE_CODE_SESSION_ID": SESSION, "STUB_LOG": str(self.log)})
        if workflow:
            env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
        if autonomy is not None:
            env["OPENSPEC_AUTONOMY"] = autonomy
        if herdr:
            env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": PANE,
                        "HERDR_BIN_PATH": str(_stub(self.root))})
        if switch is not None:
            env["OPENSPEC_HERDR_AUTO_CLEAR"] = switch
        self.env = env

    @property
    def wf_file(self) -> Path:
        return self.proj / ".claude" / "workflows" / f"{WF}.json"

    def state(self) -> dict:
        return json.loads(self.wf_file.read_text())

    def ac_log(self) -> str:
        path = self.proj / ".claude" / "herdr_auto_clear.log"
        return path.read_text() if path.exists() else ""

    def py(self, code: str, *args: str) -> subprocess.CompletedProcess:
        full = f"import sys; sys.path.insert(0, {str(HOOKS)!r})\n{code}"
        return subprocess.run([sys.executable, "-c", full, *args], capture_output=True,
                              text=True, env=self.env, cwd=str(self.proj), timeout=60)

    def wf(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(WORKFLOW), *args], capture_output=True,
                              text=True, env=self.env, cwd=str(self.proj), timeout=60)

    def footer(self, message: str, **extra) -> subprocess.CompletedProcess:
        payload = {"session_id": SESSION, "hook_event_name": "Stop", "cwd": str(self.proj),
                   "last_assistant_message": message,
                   "prompt_id": "11111111-2222-3333-4444-555555555662"}
        payload.update(extra)
        return subprocess.run([sys.executable, str(FOOTER_GATE)], input=json.dumps(payload),
                              capture_output=True, text=True, env=self.env,
                              cwd=str(self.proj), timeout=30)

    def leftovers(self) -> list:
        """Spuren des Auto-/clear im Projekt (Signale, Runner-Log, Sperre)."""
        claude = self.proj / ".claude"
        return [name for name in ("herdr_signals", "herdr_auto_clear.log",
                                  "herdr_auto_clear.lock") if (claude / name).exists()]


def _message(*blocks: str, command: str = CMD) -> str:
    return "\n\n".join(["Phase abgeschlossen, Stand liegt auf der Platte.", *blocks,
                        f"❗ Du: `{command}` — der naechste Pflicht-Schritt",
                        "⚙ /50-implement · agent-os-openspec 4.23.0"])


# --- AC-1 (#663): die Auto-/clear-Symbole gibt es nicht mehr ------------------------

def test_auto_clear_symbols_gone(tmp_path):
    case = Proj(tmp_path, "symbols", switch="1")
    names = ("auto_clear_active", "auto_clear_enabled", "maybe_auto_clear",
             "spawn_auto_clear", "run_auto_clear", "record_signal", "run_signal")
    res = case.py("import json, herdr_bridge as h\n"
                  f"print('RESULT=' + json.dumps([n for n in {names!r} if hasattr(h, n)]))")
    lines = [ln for ln in res.stdout.splitlines() if ln.startswith("RESULT=")]
    assert res.returncode == 0 and lines, (res.stdout, res.stderr)
    left = json.loads(lines[-1][len("RESULT="):])
    assert left == [], f"herdr_bridge enthaelt noch Auto-/clear-Symbole: {left}"


# --- AC-2: `workflow.py autoclear` -> immer AUTO_CLEAR=off, kein Vermerk -----------

def test_autoclear_cli_always_off(tmp_path):
    cases = []
    for label, (config, switch) in SWITCHES.items():
        for autonomy in ("auto", "manual", None):
            cases.append((f"{label}-{autonomy}", dict(config=config, switch=switch,
                                                       autonomy=autonomy)))
    # ohne Pane bzw. ohne Schalter (schon heute off) und ohne aktiven Workflow
    cases += [("no-pane", dict(herdr=False, switch="1")),
              ("no-switch", dict(config=HERDR_ONLY_CFG)),
              ("no-workflow", dict(workflow=False, switch="1"))]
    misses = []
    for label, kw in cases:
        case = Proj(tmp_path, label, **kw)
        res = case.wf("autoclear")
        assert res.returncode == 0, (label, res.stderr)
        assert "Traceback" not in res.stderr, (label, res.stderr)
        if res.stdout != "AUTO_CLEAR=off\n":
            misses.append(f"{label}: Ausgabe {res.stdout!r}")
        if kw.get("workflow", True) and "auto_clear_boundary" in case.state():
            misses.append(f"{label}: Grenz-Vermerk {case.state()['auto_clear_boundary']!r}")
    assert not misses, "\n".join(misses)


# --- AC-3: Stop-Hook startet nie einen Runner --------------------------------------

def _with_context_cut(case: Proj, tokens: int = 151_128) -> None:
    """Kontext-Schnitt der stoppenden Sitzung aktiv (#598-Weg ohne Vermerk)."""
    config = case.proj / "config.yaml"
    config.write_text(config.read_text() + BUDGET_CFG + "  growth_tokens: 75000\n")
    usage = case.proj / ".claude" / "context_usage" / f"{SESSION}.json"
    usage.parent.mkdir(parents=True, exist_ok=True)
    usage.write_text(json.dumps({"session_id": SESSION, "tokens": tokens,
                                 "baseline_tokens": 69_000, "announced_bucket": 1}))


def test_stop_hook_never_spawns_runner(tmp_path):
    scenarios = {
        # Grenz-Vermerk aus dem Phasenwechsel, saubere Antwort mit Positiv-Block
        "boundary": dict(fields=dict(auto_clear_boundary=_boundary()), extra={}),
        # Folge-Stop (#597): spawnte bisher ebenfalls
        "boundary-stop-hook-active": dict(fields=dict(auto_clear_boundary=_boundary()),
                                          extra={"stop_hook_active": True}),
        # nur Env-Schalter (#480)
        "boundary-env-switch": dict(fields=dict(auto_clear_boundary=_boundary()), extra={},
                                    config=HERDR_ONLY_CFG, switch="1"),
        # Kontext-Schnitt ohne Vermerk (#598)
        "context-cut": dict(fields={}, extra={}, cut=True),
        # Modus manual: Auto-/clear entfaellt auch dort
        "manual-boundary": dict(fields=dict(auto_clear_boundary=_boundary()), extra={},
                                autonomy="manual"),
    }
    misses = []
    for label, sc in scenarios.items():
        kw = dict(config=sc.get("config", CLEAR_CFG), switch=sc.get("switch"),
                  autonomy=sc.get("autonomy", "auto"))
        # (a) echter Stop-Hook: kein Aufruf des Herdr-Stubs, kein Runner-/Skip-Log
        case = Proj(tmp_path, f"hook-{label}", **kw, **sc["fields"])
        if sc.get("cut"):
            _with_context_cut(case)
        res = case.footer(_message(POSITIVE), **sc["extra"])
        assert res.returncode == 0, (label, res.stderr)
        assert "Traceback" not in res.stderr, (label, res.stderr)
        time.sleep(1.5)  # ein detached Runner riefe den Stub sofort auf (grace 0)
        if _calls(case.log):
            misses.append(f"{label}: Runner gestartet, Herdr-Aufrufe {_calls(case.log)}")
        if case.ac_log():
            misses.append(f"{label}: Auto-/clear-Log geschrieben {case.ac_log()!r}")
        if case.leftovers():
            misses.append(f"{label}: Spuren {case.leftovers()}")
    assert not misses, "\n".join(misses)


# --- AC-4: kein Phasenwechsel schreibt einen Grenz-Vermerk -------------------------

SPEC_OK = (
    "# Demo Spec\n\n"
    "## Purpose\n\nEin Feature, das etwas tut.\n\n"
    "## Scope\n\n- Eine Datei im Modul.\n\n"
    "## Definition of Done\n\n- Fertig, wenn X sichtbar ist.\n\n"
    "## Acceptance Criteria\n\n"
    "- **AC-1:** Given ein Nutzer / When er klickt / Then passiert etwas Sichtbares.\n\n"
    "## Test Plan\n\n- pytest tests/\n\n"
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** keine\n"
    "- **Rationale:** Kleine Aenderung, keine Weichenstellung.\n"
)

BRIEFING = (
    "# PO-Briefing: demo\n\n"
    "- **Spec:** docs/specs/demo.md\n\n"
    "## Was gebaut wird\n\n"
    "Nutzer koennen kuenftig mit einem Klick etwas ausloesen, das heute fehlt.\n\n"
    "## Definition of Done\n\n"
    "Fertig ist es, wenn der Klick sichtbar etwas ausloest und das automatisch geprueft wird.\n\n"
    "## Wie geprueft wird\n\n"
    "Ein automatischer Test klickt stellvertretend und prueft das sichtbare Ergebnis.\n\n"
    "## Kritische Anmerkungen\n\n"
    "- Keine offene Entscheidung fuer den PO.\n"
    "\n## Ampel\n\nAmpel: gruen\n"
)

_PRE = {"context_file": "docs/context.md"}
_POST = {"context_file": "docs/context.md", "spec_file": "docs/specs/missing.md",
         "spec_approved": True, "red_test_done": True}

# (von, nach, Zusatzfelder) — die Grenzen aus AUTO_CLEAR_BOUNDARIES ohne die Freigabe
PHASE_BOUNDARIES = [
    ("phase1_context", "phase2_analyse", _PRE),
    ("phase2_analyse", "phase3_spec", _PRE),
    ("phase5_tdd_red", "phase6_implement", _POST),
    ("phase6b_adversary", "phase7_validate", _POST),
]


def _adversary_evidence(case: Proj) -> None:
    """Gestempelter Dialog + VERIFIED: Voraussetzung fuer den Wechsel nach phase7."""
    (case.proj / "src").mkdir(exist_ok=True)
    (case.proj / "src" / "checked_module.py").write_text("VALUE = 1\n")
    rel = f"docs/artifacts/{WF}/adversary-dialog.md"
    art = case.proj / rel
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(
        f"# Adversary Dialog — {WF}\n\n## Checkliste\n"
        "- [x] AC-1: kein Vermerk — Beweis: Testlauf\n"
        "  Code reference: src/checked_module.py:1\n\n## Dialog\n\n"
        "### Runde 1\n**Adversary:** A1\n**Implementierer:** B1\n\n"
        "### Runde 2\n**Adversary:** A2\n**Implementierer:** B2\n\nVERDICT: VERIFIED\n")
    stamp = subprocess.run([sys.executable, str(HOOKS / "adversary_dialog.py"), "stamp",
                            str(art)], capture_output=True, text=True, env=case.env,
                           cwd=str(case.proj), timeout=60)
    assert stamp.returncode == 0, stamp.stdout + stamp.stderr
    data = case.state()
    data["adversary_verdict"] = "VERIFIED:Tests PASSED: 5 passed"
    data["test_artifacts"] = [{"type": "adversary_dialog", "path": rel,
                               "description": "dialog", "phase": "phase6b_adversary",
                               "created": "2026-11-25T10:00:00"}]
    case.wf_file.write_text(json.dumps(data))


def _approval_case(tmp_path: Path, label: str, config: str, switch) -> Proj:
    """phase3_spec mit Spec und per set-briefing gebundenem Briefing (Briefing-Gate an)."""
    case = Proj(tmp_path, label, phase="phase3_spec", config=config, switch=switch,
                autonomy="auto", context_file="docs/context.md",
                spec_file="docs/specs/demo.md", spec_approved=False)
    (case.proj / "config.yaml").write_text(config + "session_banner:\n  behind_check: false\n")
    (case.proj / "docs" / "specs").mkdir(parents=True)
    (case.proj / "docs" / "specs" / "demo.md").write_text(SPEC_OK)
    (case.proj / "docs" / "briefings").mkdir(parents=True)
    (case.proj / "docs" / "briefings" / "demo.md").write_text(BRIEFING)
    res = case.wf("set-briefing", "docs/briefings/demo.md")
    assert res.returncode == 0, f"set-briefing: {res.stdout!r} {res.stderr!r}"
    return case


def test_phase_change_writes_no_boundary(tmp_path):
    misses = []
    for sw_label, (config, switch) in SWITCHES.items():
        # 1->2, 2->3, 5->6, 6b->7 ueber `workflow.py phase`
        for src, dst, fields in PHASE_BOUNDARIES:
            label = f"{sw_label}-{src}-{dst}"
            case = Proj(tmp_path, label, phase=src, config=config, switch=switch, **fields)
            if src == "phase6b_adversary":
                _adversary_evidence(case)
            res = case.wf("phase", dst)
            assert res.returncode == 0, (label, res.stdout, res.stderr)
            data = case.state()
            assert data["current_phase"] == dst, (label, data["current_phase"])
            if "auto_clear_boundary" in data:
                misses.append(f"{label}: {data['auto_clear_boundary']!r}")

        # 3->4 ueber beide Freigabewege: auto-approve und phase_listener „approved“
        case = _approval_case(tmp_path, f"{sw_label}-auto-approve", config, switch)
        res = case.wf("auto-approve")
        assert "AUTO_APPROVE=done" in res.stdout, (sw_label, res.stdout, res.stderr)
        data = case.state()
        assert data["current_phase"] == "phase4_approved", (sw_label, data["current_phase"])
        if "auto_clear_boundary" in data:
            misses.append(f"{sw_label}-auto-approve: {data['auto_clear_boundary']!r}")

        case = _approval_case(tmp_path, f"{sw_label}-listener", config, switch)
        res = subprocess.run([sys.executable, str(LISTENER)],
                             input=json.dumps({"prompt": "approved"}), capture_output=True,
                             text=True, env=case.env, cwd=str(case.proj), timeout=60)
        assert res.returncode == 0, (sw_label, res.stderr)
        data = case.state()
        assert data["current_phase"] == "phase4_approved", (sw_label, res.stdout, res.stderr)
        if "auto_clear_boundary" in data:
            misses.append(f"{sw_label}-listener: {data['auto_clear_boundary']!r}")
    assert not misses, "Grenz-Vermerk trotz Stilllegung:\n" + "\n".join(misses)


# --- AC-5 / AC-6: `workflow.py context` ---------------------------------------------

def _ctx_project(tmp_path: Path, label: str, config: str = "") -> Path:
    root = tmp_path / label
    hooks = root / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    for f in HOOKS.glob("*.py"):
        shutil.copy(f, hooks / f.name)
    (root / ".claude" / "config.yaml").write_text(BUDGET_CFG + config)
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    usage = root / ".claude" / "context_usage" / f"{SESSION}.json"
    usage.parent.mkdir(parents=True)
    usage.write_text(json.dumps({"session_id": SESSION, "tokens": 150_000,
                                 "baseline_tokens": 20_000, "at": "2026-11-25T10:00:00",
                                 "announced_bucket": 0}))
    return root


def _ctx_env(root: Path, *, autonomy, herdr: bool, switch) -> dict:
    env = _clean_env()
    env.update({"CLAUDE_PROJECT_DIR": str(root), "CLAUDE_CODE_SESSION_ID": SESSION})
    home = root / "_home"
    home.mkdir(exist_ok=True)
    env["HOME"] = str(home)
    if autonomy is not None:
        env["OPENSPEC_AUTONOMY"] = autonomy
    if herdr:
        env.update({"HERDR_ENV": "1", "HERDR_PANE_ID": PANE,
                    "HERDR_BIN_PATH": str(_stub(root)), "STUB_LOG": str(root / "stub.log")})
    if switch is not None:
        env["OPENSPEC_HERDR_AUTO_CLEAR"] = switch
    return env


def _ctx_lines(root: Path, env: dict) -> "list[str]":
    res = subprocess.run([sys.executable, str(root / ".claude" / "hooks" / "workflow.py"),
                          "context"], cwd=root, env=env, capture_output=True, text=True,
                         timeout=60)
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    return res.stdout.splitlines()


def test_context_auto_with_herdr_stop_off(tmp_path):
    expected = ["CONTEXT_TOKENS=150000", "CONTEXT_CUT=on", "CONTEXT_THRESHOLD=100000",
                "CONTEXT_REASON=AUTO_NO_CLEAR", "CONTEXT_STOP=off"]
    cases = {
        "env-auto-cfg-clear": (CLEAR_CFG, dict(autonomy="auto", switch=None)),
        "env-auto-env-clear": (HERDR_ONLY_CFG, dict(autonomy="auto", switch="1")),
        "env-auto-both": (CLEAR_CFG, dict(autonomy="auto", switch="1")),
        "cfg-auto-cfg-clear": ("autonomy:\n  mode: auto\n" + CLEAR_CFG,
                               dict(autonomy=None, switch="1")),
    }
    misses = []
    for label, (config, kw) in cases.items():
        root = _ctx_project(tmp_path, label, config)
        env = _ctx_env(root, herdr=True, **kw)
        lines = _ctx_lines(root, env)
        if lines != expected:
            misses.append(f"{label}: {lines}")
    assert not misses, "Auto-Modus mit Herdr haelt die Kette noch an:\n" + "\n".join(misses)


def test_context_manual_stop_on(tmp_path):
    expected = ["CONTEXT_TOKENS=150000", "CONTEXT_CUT=on", "CONTEXT_THRESHOLD=100000",
                "CONTEXT_STOP=on"]
    cases = {
        "manual-herdr-cfg-clear": (CLEAR_CFG, dict(autonomy="manual", herdr=True,
                                                   switch=None)),
        "manual-herdr-env-clear": (HERDR_ONLY_CFG, dict(autonomy="manual", herdr=True,
                                                        switch="1")),
        "manual-no-herdr": ("", dict(autonomy="manual", herdr=False, switch=None)),
        "default-herdr-clear": (CLEAR_CFG, dict(autonomy=None, herdr=True, switch="1")),
        "default-no-herdr": ("", dict(autonomy=None, herdr=False, switch=None)),
    }
    for label, (config, kw) in cases.items():
        root = _ctx_project(tmp_path, label, config)
        lines = _ctx_lines(root, _ctx_env(root, **kw))
        assert lines[-1] == "CONTEXT_STOP=on", (label, lines)
        assert "CONTEXT_REASON=AUTO_NO_CLEAR" not in lines, (label, lines)
        assert lines == expected, (label, lines)


# --- AC-8: Befehlstexte 10 bis 50 ohne Herdr-Absatz ---------------------------------

CHAIN = ["10-context", "20-analyse", "30-write-spec", "40-tdd-red", "50-implement"]


@pytest.mark.parametrize("name", CHAIN)
def test_phase_commands_without_herdr_paragraph(name):
    for path in (COMMANDS / f"{name}.md", SKILLS / name / "SKILL.md"):
        text = path.read_text(encoding="utf-8")
        assert "Herdr-Auto-/clear" not in text, (
            f"{path}: Herdr-Auto-/clear-Absatz bzw. -Verweis steht noch")
        assert not re.search(r"(?:workflow\.py|\$WF) autoclear", text), (
            f"{path}: ruft noch `workflow.py autoclear` auf")
        assert "AUTO_CLEAR" not in text, f"{path}: nennt noch AUTO_CLEAR"
        # Halt bleibt: CONTEXT_STOP=on (Modus manual) beendet den Turn
        assert "CONTEXT_STOP=on" in text, f"{path}: Verweis auf CONTEXT_STOP=on fehlt"
        paras = [p for p in text.split("\n\n")
                 if "CONTEXT_STOP=on" in p and "Kontext-Haushalt" in p]
        assert len(paras) == 1, (path, len(paras))
        assert "manual" in paras[0], (path, paras[0])
        assert "Herdr" not in paras[0], (f"{path}: Kontext-Absatz nennt noch Herdr", paras[0])

    res = subprocess.run([sys.executable, str(SYNC), "--check"], capture_output=True,
                         text=True, cwd=str(REPO), timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr
