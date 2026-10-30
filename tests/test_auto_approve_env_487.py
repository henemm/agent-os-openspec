"""auto-approve beachtet den benutzerweiten Schalter OPENSPEC_AUTONOMY (Issue #487) — AC-1 bis AC-3.

Spec: docs/specs/fix-487-auto-approve-env.md
"""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PY = REPO_ROOT / "core" / "hooks" / "workflow.py"

WF = "fix-487-demo"
REL_SPEC = "docs/specs/demo.md"
REL_BRIEFING = "docs/briefings/demo.md"

SPEC_OK = (
    "# Demo Spec\n\n"
    "## Purpose\n\nEin Feature, das etwas tut.\n\n"
    "## Definition of Done\n\n- Fertig, wenn X sichtbar ist.\n\n"
    "## Acceptance Criteria\n\n"
    "- **AC-1:** Given ein Nutzer / When er klickt / Then passiert etwas Sichtbares.\n\n"
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


def _env(proj: Path, switch: "str | None") -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERDR_", "OPENSPEC_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["HOME"] = str(proj / "_home")
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    if switch is not None:
        env["OPENSPEC_AUTONOMY"] = switch
    return env


def _cli(args, proj: Path, switch: "str | None"):
    return subprocess.run([sys.executable, str(WORKFLOW_PY), *args],
                          capture_output=True, text=True,
                          env=_env(proj, switch), cwd=str(proj), timeout=60)


def _project(tmp_path: Path, config: str) -> Path:
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows" / "_log").mkdir(parents=True)
    (proj / "_home").mkdir()
    (proj / "openspec.yaml").write_text(config)
    (proj / REL_SPEC).parent.mkdir(parents=True)
    (proj / REL_SPEC).write_text(SPEC_OK)
    (proj / REL_BRIEFING).parent.mkdir(parents=True)
    (proj / REL_BRIEFING).write_text(BRIEFING)
    (proj / ".claude" / "workflows" / f"{WF}.json").write_text(json.dumps({
        "name": WF, "workflow_type": "feature", "current_phase": "phase3_spec",
        "context_file": "docs/context.md", "spec_file": REL_SPEC,
        "spec_approved": False, "phase_transitions": [], "phase_log": [],
        "approvals": [],
    }))
    (proj / ".claude" / "active_workflow").write_text(WF)
    res = _cli(["set-briefing", REL_BRIEFING], proj, "auto")
    assert res.returncode == 0, f"set-briefing: {res.stdout!r} {res.stderr!r}"
    return proj


def _state(proj: Path) -> dict:
    return json.loads((proj / ".claude" / "workflows" / f"{WF}.json").read_text())


def _verdict(res):
    m = re.search(r"^AUTO_APPROVE=(\w+)\s*$", res.stdout, re.M)
    assert m, f"AUTO_APPROVE fehlt: {res.stdout!r} {res.stderr!r}"
    return m.group(1)


def test_auto_approve_honours_env_switch(tmp_path):
    """AC-1: Env-Schalter auto ohne autonomy-Abschnitt -> done, phase4_approved."""
    proj = _project(tmp_path, "project:\n  name: x\n")
    res = _cli(["auto-approve"], proj, "auto")
    assert _verdict(res) == "done", res.stdout
    assert _state(proj)["current_phase"] == "phase4_approved"


def test_project_manual_still_wins(tmp_path):
    """AC-2: Projekteintrag manual schlaegt OPENSPEC_AUTONOMY=auto."""
    proj = _project(tmp_path, "autonomy:\n  mode: manual\n")
    res = _cli(["auto-approve"], proj, "auto")
    assert _verdict(res) == "human", res.stdout
    assert "REASON=Modus manual" in res.stdout, res.stdout
    assert _state(proj)["current_phase"] == "phase3_spec"


def test_mode_read_only_in_autonomy_mode():
    """AC-3: Lesezugriffe auf den mode-Schluessel nur innerhalb autonomy_mode()."""
    source = WORKFLOW_PY.read_text()
    tree = ast.parse(source)
    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert any(f.name == "autonomy_mode" for f in funcs), "autonomy_mode() nicht gefunden"

    def reads_mode(node):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "mode"):
            return True
        return (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant)
                and node.slice.value == "mode")

    offenders = []
    for f in funcs:
        if f.name == "autonomy_mode":
            continue
        nodes = list(ast.walk(f))
        touches_autonomy = any(isinstance(n, ast.Constant) and n.value == "autonomy"
                               for n in nodes)
        if touches_autonomy and any(reads_mode(n) for n in nodes):
            offenders.append(f.name)
    assert not offenders, f"mode-Lesezugriffe auf autonomy ausserhalb autonomy_mode(): {offenders}"
