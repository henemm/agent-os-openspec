"""Issue #279, Befund 3 (#224): CLAUDE.md nennt nur Agenten-Dispatches, die es gibt.

Die Modell-Tabelle nannte `user-story-planner` als Opus-Dispatch, obwohl
/83-user-story keinen Agenten startet. Jeder Agent aus core/agents/, den
CLAUDE.md nennt, muss in einem Befehl (core oder Modul) vorkommen — oder als
bewusste Ausnahme unten stehen.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Bewusst ohne Befehl: Ad-hoc-Nutzung durch den Orchestrator.
UNDISPATCHED_BY_DESIGN = {
    "analysis-challenger": "Ad-hoc-Gegenpruefung einer Analyse",
    "external-validator": "Ad-hoc-Pruefung von aussen",
    "fresh-eyes-inspector": "Ad-hoc-UI-Beobachter ohne Bug-Kontext",
    "user-story-planner": "Definition vorhanden, /83-user-story laeuft im Hauptkontext",
}


def _dispatching_text() -> str:
    paths = list((REPO_ROOT / "core" / "commands").glob("*.md"))
    paths += list((REPO_ROOT / "modules").glob("*/commands/*.md"))
    return "\n".join(p.read_text() for p in paths)


def test_agents_named_in_claude_md_are_dispatched():
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text()
    commands = _dispatching_text()
    agents = [p.stem for p in (REPO_ROOT / "core" / "agents").glob("*.md")]
    missing = [a for a in agents
               if re.search(rf"\b{re.escape(a)}\b", claude_md)
               and a not in commands and a not in UNDISPATCHED_BY_DESIGN]
    assert not missing, f"CLAUDE.md nennt Agenten ohne Dispatch in einem Befehl: {missing}"


def test_exceptions_are_real_and_still_undispatched():
    """Eine Ausnahme, die inzwischen dispatcht wird oder geloescht ist, faellt auf."""
    commands = _dispatching_text()
    for agent in UNDISPATCHED_BY_DESIGN:
        assert (REPO_ROOT / "core" / "agents" / f"{agent}.md").exists(), agent
        assert agent not in commands, f"{agent} wird dispatcht — Ausnahme entfernen"


def test_model_table_names_no_undispatched_agent():
    table = [ln for ln in (REPO_ROOT / "CLAUDE.md").read_text().splitlines()
             if ln.startswith("| **Haiku**") or ln.startswith("| **Sonnet**")
             or ln.startswith("| **Opus**")]
    assert table
    for agent in UNDISPATCHED_BY_DESIGN:
        assert not any(f"({agent})" in ln for ln in table), agent
