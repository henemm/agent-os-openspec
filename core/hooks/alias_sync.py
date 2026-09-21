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

import re
from pathlib import Path

ALIAS_MARKER = "<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->"
_MARKER_PREFIX = "<!-- openspec-alias:"
# Versions-Marker, den sync_skills.py an jede Vollkopie anhaengt:
# "⚙ /50-implement · agent-os-openspec 3.26.2"
_VERSION_PREFIX = "⚙ "
_VERSION_RE = re.compile(r"agent-os-openspec\s+(\d+(?:\.\d+)*)")


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


def alias_version(text: str) -> "str | None":
    """Version aus dem Versions-Marker einer Alias-Kopie, sonst None.

    Gewertet wird der LETZTE Treffer: der Marker steht am Ende der Datei,
    frueher im Text kann derselbe Satzbau zitiert sein. Kopien ohne Marker
    (reine Redirects, MARKER_EXEMPT) liefern None — ohne Version gibt es
    keinen Beweis, und ohne Beweis wird nichts unterdrueckt.
    """
    found = None
    for line in text.splitlines():
        if not line.startswith(_VERSION_PREFIX):
            continue
        match = _VERSION_RE.search(line)
        if match:
            found = match.group(1)
    return found


def version_tuple(version: "str | None") -> "tuple[int, ...] | None":
    """Version als Zahlen-Tupel. String-Vergleich waere falsch: '3.9.0' > '3.25.0'."""
    if not isinstance(version, str):
        return None
    parts = version.strip().split(".")
    if not parts or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def is_newer_than(text: str, loaded_version: "str | None") -> bool:
    """True nur, wenn die Kopie beweisbar neuer ist als `loaded_version`."""
    copy = version_tuple(alias_version(text))
    loaded = version_tuple(loaded_version)
    if copy is None or loaded is None:
        return False
    return copy > loaded


def find_stale_aliases(skills_dir: Path, commands_dir: Path,
                       loaded_version: "str | None" = None) -> "list[str]":
    """Namen der Framework-Aliase in `commands_dir`, die nicht dem Soll entsprechen.

    Veraltet ist eine markierte Datei, deren Inhalt von `alias_content` fuer
    den aktuellen Skill abweicht. Das deckt beide Faelle ab: eine Vollkopie
    einer aelteren SKILL.md-Fassung, und eine Vollkopie zu einem Skill, der
    inzwischen `disable-model-invocation: false` hat (Soll waere dann der
    Redirect). Nicht markierte Dateien sind projekteigene Befehle — tabu.

    Ist `loaded_version` gesetzt, bleiben Kopien aussen vor, deren Marker
    beweisbar neuer ist: sie stammen aus einer neueren Fassung als der
    aufrufenden, und ein Neuerzeugen wuerde sie herabstufen. Ohne den
    Parameter bleibt das Verhalten fuer alle anderen Aufrufer unveraendert.
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
        if actual == expected:
            continue
        if is_newer_than(actual, loaded_version):
            continue
        stale.append(name)
    return stale
