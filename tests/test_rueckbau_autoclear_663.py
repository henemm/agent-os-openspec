"""Rueckbau Auto-/clear per Herdr (Issue #663, Epic #649 Schnitt 4).

Spec: docs/specs/chore-663-rueckbau-autoclear.md (AC-1 bis AC-6, AC-9, AC-10;
AC-7/AC-8 sind die unveraenderten Bestandstests der Seitenleiste und des Plan-Panes).

Seit #662 ist das Auto-/clear stillgelegt; #663 loescht den toten Code: Runner,
Signale (`record_signal`, `signal activity`), Grenz-Vermerk `auto_clear_boundary`,
Skip-Log, E2E-Skript und die sieben reinen Auto-/clear-Testsuiten. Uebrig bleibt
nur die Kompatibilitaetszeile `workflow.py autoclear` -> `AUTO_CLEAR=off`.

Jedes Szenario schaltet Auto-/clear nach dem alten Massstab EIN (Herdr-Pane mit
Stub-Binary, Config `herdr.auto_clear.enabled: true` und/oder Env
`OPENSPEC_HERDR_AUTO_CLEAR=1`). Die Test-Env entfernt alle geerbten
`OPENSPEC_*`/`HERDR_*`/`CLAUDE_*`/`STUB_*` und setzt Autonomie, Herdr, Schalter
und Sitzung explizit (die Cloud-Umgebung setzt `OPENSPEC_AUTONOMY=auto`).

Bewusst eigenstaendig: keine Importe aus anderen Testdateien.
"""
from __future__ import annotations

import ast
import json
import os
import re
import stat
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "core" / "hooks"
BRIDGE = HOOKS / "herdr_bridge.py"
WORKFLOW = HOOKS / "workflow.py"
FOOTER_GATE = HOOKS / "footer_gate.py"
LISTENER = HOOKS / "phase_listener.py"
BANNER = HOOKS / "session_banner.py"
GUARD = HOOKS / "session_singleton_guard.py"
HOOKS_JSON = REPO / "hooks" / "hooks.json"

PANE = "pane-663"
WF = "chore-663-demo"
SESSION = "sess-663"
PHASE = "phase6_implement"
CMD = "/50-implement #663"

# Stub: protokolliert jeden Aufruf NUL-getrennt in STUB_LOG, Exit 0
STUB = r"""#!/bin/bash
{ for a in "$@"; do printf '%s\0' "$a"; done; printf '\n'; } >> "$STUB_LOG"
exit 0
"""

# Auto-/clear nach altem Massstab EIN (grace 0: ein Runner riefe den Stub sofort);
# Plan-Pane aus, damit kein legitimer Prozess-Start das Bild truebt.
CLEAR_CFG = ("herdr:\n  enabled: true\n  plan_pane:\n    enabled: false\n"
             "  auto_clear:\n    enabled: true\n    grace_s: 0\n"
             "    idle_timeout_s: 2\n    announce: true\n")
HERDR_ONLY_CFG = "herdr:\n  enabled: true\n  plan_pane:\n    enabled: false\n"
NO_GATES = "po_briefing_gate:\n  enabled: false\nsession_banner:\n  behind_check: false\n"
BUDGET_CFG = "context_budget:\n  enabled: true\n  clear_threshold_tokens: 100000\n"

SWITCHES = {
    "config": (CLEAR_CFG, None),
    "env": (HERDR_ONLY_CFG, "1"),
    "config+env": (CLEAR_CFG, "1"),
}

# Herdr-Aufrufe, mit denen der Runner in die Sitzung tippt bzw. ankuendigt
TYPING_KINDS = ("pane send-text", "pane send-keys", "agent prompt", "agent wait",
                "notification show")

POSITIVE = "✅ **`/clear` ist jetzt gefahrlos** — alles auf Platte gesichert."

REMOVED_BRIDGE_SYMBOLS = ("maybe_auto_clear", "spawn_auto_clear", "run_auto_clear",
                          "record_signal", "run_signal", "auto_clear_active",
                          "auto_clear_enabled", "_auto_clear_config", "_Runner",
                          "has_clear_marker", "resolve_command_form", "read_signal")
KEPT_BRIDGE_SYMBOLS = ("report_workflow", "report_active", "clear", "open_plan_pane",
                       "open_plan_pane_for_active", "run_plan_pane", "run_plan_pane_close")
REMOVED_WORKFLOW_SYMBOLS = ("AUTO_CLEAR_BOUNDARIES", "_boundary_timestamp",
                            "_note_transition_boundary", "_record_auto_clear_boundary")
REMOVED_FOOTER_SYMBOLS = ("_maybe_auto_clear", "_discard_boundary", "_record_stop")
REMOVED_GUARD_SYMBOLS = ("_record_activity",)

REMOVED_FILES = (
    "tests/test_herdr_auto_clear_467.py",
    "tests/test_autoclear_boundary_495.py",
    "tests/test_autoclear_transition_497.py",
    "tests/test_autoclear_kontextschnitt_598.py",
    "tests/test_autoclear_retry_597.py",
    "tests/test_autoclear_eigene_signale_506.py",
    "tests/test_auto_clear_global_480.py",
    "scripts/e2e_auto_clear.sh",
)
DEAD_TOKENS = ("record_signal", "maybe_auto_clear", "auto_clear_boundary",
               "AUTO_CLEAR_BOUNDARIES", "herdr_signals", "auto_clear_active")


# --- Helfer -------------------------------------------------------------------

def _clean_env() -> dict:
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("OPENSPEC_", "HERDR_", "STUB_", "CLAUDE_"))}


def _stub(root: Path) -> Path:
    stub = root / "herdr-stub"
    stub.write_text(STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _calls(log: Path) -> list:
    if not log.exists():
        return []
    return [ln.rstrip("\0").split("\0")
            for ln in log.read_bytes().decode("utf-8", "replace").split("\n") if ln]


def _typing(log: Path) -> list:
    return [c for c in _calls(log) if " ".join(c[:2]) in TYPING_KINDS]


def _symbols(module: str, names, env: "dict | None" = None) -> dict:
    """Welche Namen hat das frisch importierte Modul? (Subprozess, eigener Cache)"""
    code = (f"import sys, json; sys.path.insert(0, {str(HOOKS)!r})\n"
            f"import {module} as m\n"
            f"print('RESULT=' + json.dumps({{n: hasattr(m, n) for n in {list(names)!r}}}))")
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=env if env is not None else _clean_env(), cwd=str(REPO),
                         timeout=60)
    lines = [ln for ln in res.stdout.splitlines() if ln.startswith("RESULT=")]
    assert res.returncode == 0 and lines, (module, res.stdout, res.stderr)
    return json.loads(lines[-1][len("RESULT="):])


class Proj:
    """Isoliertes Projekt (Hooks aus dem Repo), Workflow-State, Herdr-Stub, Schalter."""

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
        plugin = self.root / "plugin"
        (plugin / ".claude-plugin").mkdir(parents=True)
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": "9.9.9"}))
        self.log = self.root / "stub.log"
        env = _clean_env()
        env.update({"CLAUDE_PROJECT_DIR": str(self.proj), "HOME": str(self.proj / "_home"),
                    "CLAUDE_CODE_SESSION_ID": SESSION, "CLAUDE_PLUGIN_ROOT": str(plugin),
                    "STUB_LOG": str(self.log)})
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

    def leftovers(self) -> list:
        """Spuren des Auto-/clear im Projekt (Signale, Runner-Log, Sperre)."""
        claude = self.proj / ".claude"
        return [name for name in ("herdr_signals", "herdr_auto_clear.log",
                                  "herdr_auto_clear.lock") if (claude / name).exists()]

    def run(self, argv, stdin: "str | None" = None, cwd: "Path | None" = None):
        return subprocess.run(argv, input=stdin, capture_output=True, text=True,
                              env=self.env, cwd=str(cwd or self.proj), timeout=60)

    def wf(self, *args: str):
        return self.run([sys.executable, str(WORKFLOW), *args])


def _message(*blocks: str, command: str = CMD) -> str:
    return "\n\n".join(["Phase abgeschlossen, Stand liegt auf der Platte.", *blocks,
                        f"❗ Du: `{command}` — der naechste Pflicht-Schritt",
                        "⚙ /50-implement · agent-os-openspec 4.24.0"])


def _boundary(phase: str = PHASE, command: str = CMD) -> dict:
    return {"phase": phase, "command": command, "at": datetime.now().astimezone().isoformat()}


# --- AC-1: herdr_bridge ohne Auto-/clear-Symbole -------------------------------

def test_bridge_has_no_auto_clear_symbols():
    present = _symbols("herdr_bridge", REMOVED_BRIDGE_SYMBOLS + KEPT_BRIDGE_SYMBOLS)
    left = [n for n in REMOVED_BRIDGE_SYMBOLS if present[n]]
    assert not left, f"herdr_bridge enthaelt noch Auto-/clear-Symbole: {left}"
    # Gegenprobe: Seitenleiste und Plan-Pane bleiben
    gone = [n for n in KEPT_BRIDGE_SYMBOLS if not present[n]]
    assert not gone, f"Seitenleisten-/Plan-Pane-Symbole mitgeloescht: {gone}"

    # Keine Spawn-Funktion fuer einen Pane-Tipp: kein Popen auf `herdr_bridge.py auto-clear`
    tree = ast.parse(BRIDGE.read_text(encoding="utf-8"))
    consts = {n.value for n in ast.walk(tree)
              if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "auto-clear" not in consts, "herdr_bridge kennt noch den Modus `auto-clear`"
    assert "signal" not in consts, "herdr_bridge kennt noch den Modus `signal`"


# --- AC-2: `workflow.py autoclear` -> genau AUTO_CLEAR=off ------------------------

def test_autoclear_cli_prints_off(tmp_path):
    cases = []
    for label, (config, switch) in SWITCHES.items():
        for autonomy in ("auto", "manual", None):
            cases.append((f"{label}-{autonomy}",
                          dict(config=config, switch=switch, autonomy=autonomy)))
    cases += [("no-pane", dict(herdr=False, switch="1")),
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
        if case.leftovers():
            misses.append(f"{label}: Spuren {case.leftovers()}")
    assert not misses, "\n".join(misses)

    # Die Vermerk-Funktion hinter `autoclear` ist entfernt (nur die Auskunft bleibt)
    present = _symbols("workflow", ("cmd_autoclear", "_record_auto_clear_boundary"))
    assert present["cmd_autoclear"], "Kompatibilitaetszeile `autoclear` fehlt"
    assert not present["_record_auto_clear_boundary"], \
        "workflow._record_auto_clear_boundary steht noch"


# --- AC-3: kein Phasenwechsel schreibt einen Grenz-Vermerk ------------------------

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

# 1->2, 2->3, 5->6, 6b->7 ueber `workflow.py phase`; 3->4 ueber die Freigabe (unten)
PHASE_CHANGES = [
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
    stamp = case.run([sys.executable, str(HOOKS / "adversary_dialog.py"), "stamp", str(art)])
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
                context_file="docs/context.md", spec_file="docs/specs/demo.md",
                spec_approved=False)
    (case.proj / "config.yaml").write_text(config + "session_banner:\n  behind_check: false\n")
    (case.proj / "docs" / "specs").mkdir(parents=True)
    (case.proj / "docs" / "specs" / "demo.md").write_text(SPEC_OK)
    (case.proj / "docs" / "briefings").mkdir(parents=True)
    (case.proj / "docs" / "briefings" / "demo.md").write_text(BRIEFING)
    res = case.wf("set-briefing", "docs/briefings/demo.md")
    assert res.returncode == 0, f"set-briefing: {res.stdout!r} {res.stderr!r}"
    return case


def test_phase_change_writes_no_boundary(tmp_path):
    present = _symbols("workflow", REMOVED_WORKFLOW_SYMBOLS)
    left = [n for n in REMOVED_WORKFLOW_SYMBOLS if present[n]]
    assert not left, f"workflow.py enthaelt noch Grenz-Vermerk-Code: {left}"

    misses = []
    for sw_label, (config, switch) in SWITCHES.items():
        for src, dst, fields in PHASE_CHANGES:
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

        case = _approval_case(tmp_path, f"{sw_label}-listener", config, switch)
        res = case.run([sys.executable, str(LISTENER)], stdin=json.dumps({"prompt": "approved"}))
        assert res.returncode == 0, (sw_label, res.stderr)
        data = case.state()
        assert data["current_phase"] == "phase4_approved", (sw_label, res.stdout, res.stderr)
        if "auto_clear_boundary" in data:
            misses.append(f"{sw_label}-listener: {data['auto_clear_boundary']!r}")
    assert not misses, "Grenz-Vermerk beim Phasenwechsel:\n" + "\n".join(misses)


# --- AC-4: Hooks starten nichts und schreiben keine Signale -----------------------

def _run_hooks(case: Proj) -> dict:
    proj = str(case.proj)
    results = {
        "stop": case.run([sys.executable, str(FOOTER_GATE)], stdin=json.dumps(
            {"session_id": SESSION, "hook_event_name": "Stop", "cwd": proj,
             "last_assistant_message": _message(POSITIVE),
             "prompt_id": "11111111-2222-3333-4444-555555555663"})),
        "prompt": case.run([sys.executable, str(LISTENER)], stdin=json.dumps(
            {"prompt": "wie ist der Stand?", "session_id": SESSION, "cwd": proj,
             "hook_event_name": "UserPromptSubmit"})),
        "session": case.run([sys.executable, str(BANNER)], stdin=json.dumps(
            {"session_id": SESSION, "cwd": proj, "hook_event_name": "SessionStart",
             "source": "clear"})),
        "pretooluse": case.run([sys.executable, str(GUARD), "guard"], stdin=json.dumps(
            {"session_id": SESSION, "hook_event_name": "PreToolUse", "cwd": proj,
             "tool_name": "Read", "tool_input": {"file_path": "x.txt"}})),
    }
    return results


def test_hooks_spawn_nothing_and_write_no_signal_files(tmp_path):
    misses = []
    for label, (config, switch) in SWITCHES.items():
        for autonomy in ("auto", "manual"):
            tag = f"{label}-{autonomy}"
            case = Proj(tmp_path, tag, config=config, switch=switch, autonomy=autonomy,
                        auto_clear_boundary=_boundary())
            for hook, res in _run_hooks(case).items():
                assert res.returncode == 0, (tag, hook, res.stdout, res.stderr)
                assert "Traceback" not in res.stderr, (tag, hook, res.stderr)
            time.sleep(1.5)  # ein detached Runner riefe den Stub sofort auf (grace 0)
            if _typing(case.log):
                misses.append(f"{tag}: Herdr-Tipp/Ankuendigung {_typing(case.log)}")
            if case.leftovers():
                misses.append(f"{tag}: Spuren {case.leftovers()}")
    assert not misses, "\n".join(misses)

    # Die Auto-/clear-Aufrufer in den Hooks sind entfernt
    footer = _symbols("footer_gate", REMOVED_FOOTER_SYMBOLS)
    guard = _symbols("session_singleton_guard", REMOVED_GUARD_SYMBOLS)
    left = [f"footer_gate.{n}" for n, v in footer.items() if v]
    left += [f"session_singleton_guard.{n}" for n, v in guard.items() if v]
    assert not left, f"Auto-/clear-Aufrufer stehen noch: {left}"


# --- AC-5: hooks.json ohne `signal activity`, mit `plan-pane-close` ---------------

def test_hooks_json_has_no_signal_entries_but_plan_pane_close():
    hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
    commands = []
    for event, groups in hooks.items():
        assert isinstance(groups, list) and groups, f"leerer Event-Block {event!r}"
        for group in groups:
            assert group.get("hooks"), f"{event}: Gruppe ohne Hooks {group}"
            for hook in group["hooks"]:
                commands.append((event, hook.get("command", "")))
    signal = [(e, c) for e, c in commands if re.search(r"herdr_bridge\.py\s+signal\b", c)]
    assert not signal, f"Registrierungen auf `herdr_bridge.py signal`: {signal}"
    close = [c for e, c in commands
             if e == "SessionEnd" and c.endswith("herdr_bridge.py plan-pane-close")]
    assert close == ["${CLAUDE_PLUGIN_ROOT}/core/hooks/herdr_bridge.py plan-pane-close"], \
        f"plan-pane-close unter SessionEnd fehlt: {commands}"


# --- AC-6: entfernte CLI-Modi enden still mit Exit 0 ------------------------------

def test_removed_cli_modes_exit_zero_silently(tmp_path):
    case = Proj(tmp_path, "cli", switch="1", auto_clear_boundary=_boundary())
    payloads = {
        "Notification": {"notification_type": "permission_prompt", "message": "permission"},
        "PermissionRequest": {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        "SessionEnd": {"reason": "clear"},
    }
    runs = []
    for event, extra in payloads.items():
        payload = {"session_id": SESSION, "cwd": str(case.proj), "hook_event_name": event,
                   **extra}
        runs.append((f"signal activity/{event}", ["signal", "activity"], json.dumps(payload)))
    runs += [
        ("auto-clear (Runner-Argumente)",
         ["auto-clear", "--pane", PANE, "--workflow", WF, "--phase", PHASE,
          "--command", CMD, "--grace", "0", "--settle", "0", "--idle-timeout", "2",
          "--announce", "1", "--boundary-at", case.state()["auto_clear_boundary"]["at"]], ""),
        ("auto-clear (ohne Argumente)", ["auto-clear"], ""),
        ("signal (ohne Argumente)", ["signal"], ""),
    ]
    misses = []
    for label, args, stdin in runs:
        res = case.run([sys.executable, str(BRIDGE), *args], stdin=stdin)
        if (res.returncode, res.stdout, res.stderr) != (0, "", ""):
            misses.append(f"{label}: {(res.returncode, res.stdout, res.stderr)!r}")
    time.sleep(1.0)
    if _calls(case.log):
        misses.append(f"Herdr-Stub aufgerufen: {_calls(case.log)}")
    if case.leftovers():
        misses.append(f"Spuren: {case.leftovers()}")
    assert not misses, "\n".join(misses)


# --- AC-9: Config und Env bewirken nichts ----------------------------------------

def _ctx_lines(case: Proj) -> list:
    res = case.wf("context")
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr, res.stderr
    return res.stdout.splitlines()


def _ctx_case(tmp_path: Path, label: str, config: str, switch, autonomy) -> Proj:
    case = Proj(tmp_path, label, config=config + BUDGET_CFG, switch=switch, autonomy=autonomy)
    usage = case.proj / ".claude" / "context_usage" / f"{SESSION}.json"
    usage.parent.mkdir(parents=True)
    usage.write_text(json.dumps({"session_id": SESSION, "tokens": 150_000,
                                 "baseline_tokens": 20_000, "at": "2026-11-25T10:00:00",
                                 "announced_bucket": 0}))
    return case


def _reads(path: Path) -> list:
    """Aufrufe/Indizes, die `OPENSPEC_HERDR_AUTO_CLEAR` oder den Schluessel `auto_clear` lesen."""
    hits = []
    watched = {"OPENSPEC_HERDR_AUTO_CLEAR", "auto_clear"}
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        args = []
        if isinstance(node, ast.Call):
            args = list(node.args)
        elif isinstance(node, ast.Subscript):
            args = [node.slice]
        for arg in args:
            if isinstance(arg, ast.Constant) and arg.value in watched:
                hits.append(f"{path.name}:{node.lineno} {arg.value}")
    return hits


def test_config_and_env_have_no_effect(tmp_path):
    misses = []
    for autonomy in ("auto", "manual"):
        base = _ctx_case(tmp_path, f"base-{autonomy}", HERDR_ONLY_CFG, None, autonomy)
        base_ctx, base_ac = _ctx_lines(base), base.wf("autoclear").stdout
        assert base_ac == "AUTO_CLEAR=off\n", base_ac
        assert base_ctx[-1] == ("CONTEXT_STOP=off" if autonomy == "auto"
                                else "CONTEXT_STOP=on"), base_ctx
        for label, (config, switch) in SWITCHES.items():
            case = _ctx_case(tmp_path, f"{label}-{autonomy}", config, switch, autonomy)
            if _ctx_lines(case) != base_ctx:
                misses.append(f"{label}/{autonomy}: context {_ctx_lines(case)} != {base_ctx}")
            if case.wf("autoclear").stdout != base_ac:
                misses.append(f"{label}/{autonomy}: autoclear weicht ab")
    assert not misses, "\n".join(misses)

    # Kein Hook liest den Env-Schalter oder den Config-Schluessel noch aus
    reads = [hit for path in sorted(HOOKS.glob("*.py")) for hit in _reads(path)]
    assert not reads, f"Auto-/clear-Schalter wird noch gelesen: {reads}"


def test_auto_clear_files_removed():
    """AC-9 (Rest) und DoD: geloeschte Dateien weg, keine toten Bezeichner mehr."""
    still = [rel for rel in REMOVED_FILES if (REPO / rel).exists()]
    assert not still, f"Noch vorhanden: {still}"

    hits = []
    for base in ("core", "hooks", "scripts"):
        for path in sorted((REPO / base).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix not in (".py", ".json", ".sh", ".md", ".yaml", ".yml"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in DEAD_TOKENS:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert not hits, "Tote Auto-/clear-Bezeichner:\n" + "\n".join(hits)


# --- AC-10: Doku und Version -------------------------------------------------------

VERSION = "4.24.0"
DOC_FORBIDDEN = ("maybe_auto_clear", "auto_clear_active", "record_signal",
                 "auto_clear_boundary", "signal activity", "herdr_auto_clear.log",
                 "Rueckbau #663", "Rückbau #663")


def _changelog_section(version: str) -> str:
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    start = text.find(f"## [{version}]")
    assert start != -1, f"CHANGELOG ohne Abschnitt [{version}]"
    end = text.find("\n## [", start + 1)
    return text[start:end if end != -1 else len(text)]


def _version_tuple(text: str) -> tuple:
    return tuple(int(p) for p in text.split("."))


def test_docs_and_version_consistent():
    # Seit #667 (4.25.0): nicht mehr auf genau 4.24.0 gepinnt, sondern mindestens
    # 4.24.0 und in plugin.json, CLAUDE.md und README gleich.
    plugin = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    current = plugin["version"]
    assert _version_tuple(current) >= _version_tuple(VERSION), current
    claude = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert f"**Version**: {current}" in claude, "CLAUDE.md nennt nicht die neue Version"
    assert re.search(rf"^\*\*Version\*\*: {re.escape(current)}\b", readme, re.M), \
        "README nennt nicht die neue Version"

    for name, text in (("CLAUDE.md", claude), ("README.md", readme)):
        found = [tok for tok in DOC_FORBIDDEN if tok in text]
        assert not found, f"{name} beschreibt noch Auto-/clear-Code: {found}"
    stale = [ln for ln in claude.splitlines()
             if re.search(r"auto-?/?clear", ln, re.I) and "stillgelegt" in ln]
    assert not stale, "CLAUDE.md beschreibt Auto-/clear noch als stillgelegt vorhanden:\n" + \
        "\n".join(stale)

    section = _changelog_section(VERSION)
    for needle in ("#663", "signal", "auto-clear", "herdr.auto_clear",
                   "OPENSPEC_HERDR_AUTO_CLEAR"):
        assert needle in section, f"CHANGELOG [{VERSION}] ohne Migrationshinweis zu {needle!r}"
    assert "AUTO_CLEAR=off" in section or "autoclear" in section, \
        "CHANGELOG nennt die Kompatibilitaetszeile `autoclear` nicht"

