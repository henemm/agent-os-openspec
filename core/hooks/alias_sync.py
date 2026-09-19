#!/usr/bin/env python3
"""Kurz-Aliase fuer Plugin-Skills — einzige Quelle fuer ihren Soll-Inhalt.

`setup.py --command-aliases` schreibt fuer jeden Skill eine Datei
`<scope>/.claude/commands/<name>.md`, damit `/name` wie
`/agent-os-openspec:name` wirkt. Skills mit `disable-model-invocation: true`
bekommen dabei den KOMPLETTEN SKILL.md-Inhalt eingebettet (ein Text-Redirect
scheitert dort am Skill-Tool-Gate). Diese Vollkopien veralten bei jedem
Plugin-Update still — genau das erkennt `find_stale_aliases`.

Bewusst in core/hooks/: `setup.py` (Erzeugen) und `session_banner.py`
(Erkennen) importieren beide diese Funktionen, damit Soll-Inhalt und
Veraltet-Pruefung nie auseinanderlaufen.
"""

from __future__ import annotations

from pathlib import Path

ALIAS_MARKER = "<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->"
_MARKER_PREFIX = "<!-- openspec-alias:"


def skill_names(skills_dir: Path) -> "list[str]":
    """Namen aller Skills (Verzeichnisse mit SKILL.md), sortiert."""
    return sorted(
        p.name
        for p in skills_dir.iterdir()
        if p.is_dir() and (p / "SKILL.md").exists()
    )


def embeds_full_skill(skill_text: str) -> bool:
    """True, wenn der Alias den vollen Skill-Inhalt einbetten muss."""
    return "disable-model-invocation: true" in skill_text


def alias_content(name: str, skill_text: str) -> str:
    """Soll-Inhalt der Alias-Datei fuer Skill `name`."""
    if embeds_full_skill(skill_text):
        return f"{ALIAS_MARKER}\n{skill_text}"
    return (
        f"{ALIAS_MARKER}\n"
        "---\n"
        f"description: Kurz-Alias für /agent-os-openspec:{name}\n"
        "---\n"
        "\n"
        f"/agent-os-openspec:{name} $ARGUMENTS\n"
    )


def is_alias_file(text: str) -> bool:
    """True, wenn die Datei vom Framework erzeugt wurde (Marker in Zeile 1)."""
    first_line = text.splitlines()[0] if text else ""
    return first_line.startswith(_MARKER_PREFIX)


def find_stale_aliases(skills_dir: Path, commands_dir: Path) -> "list[str]":
    """Namen der Framework-Aliase in `commands_dir`, die nicht dem Soll entsprechen.

    Veraltet ist eine markierte Datei, deren Inhalt von `alias_content` fuer
    den aktuellen Skill abweicht. Das deckt beide Faelle ab: eine Vollkopie
    einer aelteren SKILL.md-Fassung, und eine Vollkopie zu einem Skill, der
    inzwischen `disable-model-invocation: false` hat (Soll waere dann der
    Redirect). Nicht markierte Dateien sind projekteigene Befehle — tabu.
    """
    if not commands_dir.is_dir() or not skills_dir.is_dir():
        return []
    stale = []
    for name in skill_names(skills_dir):
        target = commands_dir / f"{name}.md"
        if not target.is_file():
            continue
        actual = target.read_text()
        if not is_alias_file(actual):
            continue
        expected = alias_content(name, (skills_dir / name / "SKILL.md").read_text())
        if actual != expected:
            stale.append(name)
    return stale
