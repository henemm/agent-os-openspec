#!/usr/bin/env python3
"""Kurz-Aliase fuer Plugin-Skills — einzige Quelle fuer ihren Soll-Inhalt.

`setup.py --command-aliases` schreibt fuer jeden Skill eine Datei
`<scope>/.claude/commands/<name>.md`, damit `/name` wie
`/agent-os-openspec:name` wirkt. Skills mit `disable-model-invocation: true`
bekommen dabei den KOMPLETTEN SKILL.md-Inhalt eingebettet (ein Text-Redirect
scheitert dort am Skill-Tool-Gate). Diese Vollkopien veralten bei jedem
Plugin-Update still — genau das erkennt `find_stale_aliases`.

Die uebrigen Skills bekommen einen Text-Redirect. Ohne geladenes Plugin
(Cloud-Sitzungen) liefe er ins Leere; deshalb traegt er einen einzeiligen
Inline-Bash-Block, der dann die lokale `skills/<name>/SKILL.md` ausgibt oder
hoerbar mit `BEFEHLSTEXT FEHLT` stoppt (fix-schritte-ueberspringen).

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


def _frontmatter_close(lines: "list[str]") -> "int | None":
    """Index des schliessenden `---`, wenn die Datei mit Frontmatter beginnt."""
    if not lines or lines[0].rstrip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].rstrip() == "---":
            return index
    return None


def _read_or_none(path: Path) -> "str | None":
    """Dateiinhalt, oder None wenn nicht lesbar (Rechte, kein UTF-8; #350)."""
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def alias_content(name: str, skill_text: str) -> str:
    """Soll-Inhalt der Alias-Datei fuer Skill `name`.

    Der Marker steht direkt hinter dem Frontmatter (#251): stuende er davor,
    waere das Frontmatter nicht parsbar und die Befehlsauswahl zeigte den
    Marker statt der Beschreibung (#238).

    Redirect: `allowed-tools: Bash(python3 -c *)` genehmigt den Inline-Block
    vor; der Block ist still, wenn das Plugin installiert ist, gibt sonst die
    lokale SKILL.md aus (oder den Stopp-Text `BEFEHLSTEXT FEHLT`).
    """
    if embeds_full_skill(skill_text):
        lines = skill_text.split("\n")
        close = _frontmatter_close(lines)
        if close is None:
            return f"{ALIAS_MARKER}\n{skill_text}"
        return "\n".join(lines[:close + 1] + [ALIAS_MARKER] + lines[close + 1:])
    return (
        "---\n"
        f"description: Kurz-Alias für /agent-os-openspec:{name}\n"
        "allowed-tools: Bash(python3 -c *)\n"
        "---\n"
        f"{ALIAS_MARKER}\n"
        "\n"
        f"/agent-os-openspec:{name} $ARGUMENTS\n"
        "\n"
        f"{_FALLBACK_NOTE}\n"
        "\n"
        "```!\n"
        f"{_fallback_command(name)}\n"
        "```\n"
    )


# Redirect-Fallback ohne Plugin (Cloud-Sitzungen laden keine Plugins): der
# Inline-Bash-Block laeuft vor dem Senden an Claude und ersetzt sich durch seine
# Ausgabe. EINE Zeile ohne `&&`, `;` oder `|`, weil Bash-Permission-Regeln
# Praefix-Treffer sind, die an Shell-Operatoren enden (wie SETUP_BLOCK in
# scripts/sync_skills.py). Exit immer 0; keine Ausgabezeile beginnt mit `⚙ `.
_FALLBACK_NOTE = (
    "Ist das Plugin agent-os-openspec geladen, gilt die Weiterleitung oben und der "
    "Block unten gibt nichts aus. Steht unten der Befehlstext, arbeite danach. "
    "Steht unten BEFEHLSTEXT FEHLT, beginne die Phase nicht und informiere den PO. "
    "Erscheint der Codeblock unten wörtlich statt seiner Ausgabe, führe ihn per Bash aus."
)

_FALLBACK_SOURCE = "\n".join([
    "import json, os, re, sys",
    "n = sys.argv[1]",
    "try:",
    "    d = json.load(open(os.path.expanduser(\"~/.claude/plugins/installed_plugins.json\")))",
    "    ok = any(str(k).startswith(\"agent-os-openspec@\") for k in (d.get(\"plugins\") or {}))",
    "except Exception:",
    "    ok = False",
    "c = [os.environ.get(\"CLAUDE_PROJECT_DIR\") or \"\", os.getcwd()]",
    "c += [a for a in sys.argv[2:] if a and not a.startswith(\"${\")]",
    "s = lambda x: os.path.join(x, \"skills\", n, \"SKILL.md\")",
    # Pin-Cache (#562): <cache_base>/<cloud_ref> nur ohne Symlink und mit .ok == cloud_sha.
    "def p(q):",
    "    try:",
    "        f = json.load(open(os.path.join(q, \".claude\", \"framework_version.json\"),"
    " encoding=\"utf-8\"))",
    "        b = os.environ.get(\"AGENT_OS_CLOUD_CACHE\") or"
    " os.path.expanduser(\"~/.cache/agent-os-openspec\")",
    "        x = os.path.join(b, f[\"cloud_ref\"])",
    "        k = os.path.join(x, \".ok\")",
    "        w = (x, k, os.path.join(x, \"skills\"), os.path.dirname(s(x)), s(x))",
    "        v = re.fullmatch(\"agent-os-openspec--v[0-9]+[.][0-9]+[.][0-9]+\", f[\"cloud_ref\"])",
    "        v = v and re.fullmatch(\"[0-9a-f]{40}\", f[\"cloud_sha\"]) and os.path.isfile(s(x))",
    "        v = v and not any(os.path.islink(y) for y in w)",
    "        return x if v and open(k, encoding=\"utf-8\").read().strip() == f[\"cloud_sha\"] else None",
    "    except Exception:",
    "        return None",
    "r = next((x for x in c if x and os.path.isfile(s(x))), None)",
    "r = r or p(next((x for x in [c[0]] + c[2:] + [c[1]] if x), \"\"))",
    "if ok:",
    "    pass",
    "elif r:",
    "    print(\"Plugin agent-os-openspec ist in dieser Sitzung nicht geladen — "
    "der folgende Befehlstext gilt.\")",
    "    if os.path.isdir(os.path.join(r, \"core\", \"hooks\")):",
    "        print(\"export CLAUDE_PLUGIN_ROOT=\" + r)",
    "    for line in open(s(r), encoding=\"utf-8\").read().splitlines():",
    "        v = line.startswith(\"\\u2699 \")",
    "        print((\"Versionsmarker (als letzte Zeile ausgeben): \" + line) if v else line)",
    "else:",
    "    print(\"BEFEHLSTEXT FEHLT: Plugin agent-os-openspec ist nicht geladen und unter \""
    " + s(c[0] or c[1]) + \" liegt keine Kopie. Beginne die Phase NICHT und rate nicht — "
    "informiere den PO, dass der Befehlstext in dieser Sitzung fehlt."
    " Cache noch nicht bereit (Cloud-Pin): python3 .claude/cloud_bootstrap.py --retry"
    " ausführen, die Umgebung muss github.com erreichen.\")",
])


def _fallback_command(name: str) -> str:
    """Einzeiler `python3 -c 'exec("...")' <name> "${CLAUDE_PROJECT_DIR}"`."""
    literal = (_FALLBACK_SOURCE.replace("\\", "\\\\").replace("\"", "\\\"")
               .replace("\n", "\\n"))
    return f"python3 -c 'exec(\"{literal}\")' {name} \"${{CLAUDE_PROJECT_DIR}}\""


def is_alias_file(text: str) -> bool:
    """True, wenn die Datei vom Framework erzeugt wurde.

    Erkannt werden zwei Positionen: alt (Zeile 1) und neu (erste Zeile nach
    einem am Dateianfang stehenden, geschlossenen Frontmatter). Ein Marker an
    anderer Stelle zaehlt nicht.
    """
    lines = text.splitlines()
    if not lines:
        return False
    if lines[0].startswith(_MARKER_PREFIX):
        return True
    close = _frontmatter_close(lines)
    if close is None or close + 1 >= len(lines):
        return False
    return lines[close + 1].startswith(_MARKER_PREFIX)


def find_aliases(commands_dir: Path) -> "list[Path]":
    """Alle markierten Alias-Dateien in `commands_dir`, sortiert."""
    if not commands_dir.is_dir():
        return []
    found = []
    for p in commands_dir.glob("*.md"):
        if not p.is_file():
            continue
        text = _read_or_none(p)
        if text is not None and is_alias_file(text):
            found.append(p)
    return sorted(found)


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
        actual = _read_or_none(target)
        if actual is None or not is_alias_file(actual):
            continue
        skill_text = _read_or_none(skills_dir / name / "SKILL.md")
        if skill_text is None:
            continue
        expected = alias_content(name, skill_text)
        if actual == expected:
            continue
        if is_newer_than(actual, loaded_version):
            continue
        stale.append(name)
    return stale


# Befehle, die das Framework entfernt hat (#333). Ihre markierten Kurz-Aliase
# sind verwaist; `setup.py --refresh-aliases` loescht sie. Bewusst eine feste
# Liste statt "markierter Alias ohne Skill": ein aelteres Setup wuerde sonst
# Aliase von Skills loeschen, die nur eine neuere Plugin-Version kennt.
REMOVED_SKILLS = ("00-bug",)


def find_removed_aliases(commands_dir: Path) -> "list[Path]":
    """Markierte Alias-Dateien entfernter Befehle in `commands_dir`.

    Unmarkierte Dateien gleichen Namens sind projekteigene Befehle — tabu.
    """
    if not commands_dir.is_dir():
        return []
    found = []
    for name in REMOVED_SKILLS:
        target = commands_dir / f"{name}.md"
        if not target.is_file():
            continue
        text = _read_or_none(target)
        if text is not None and is_alias_file(text):
            found.append(target)
    return found


def _skip(skipped: "list[str] | None", name: str, reason: str) -> None:
    if skipped is not None:
        skipped.append(f"{name}: {reason}")


def _reason(exc: OSError) -> str:
    """Kurzgrund fuer `skipped` (#400)."""
    if isinstance(exc, PermissionError):
        return "schreibgeschützt"
    return f"Fehler ({type(exc).__name__})"


def refresh_aliases(skills_dir: Path, commands_dir: Path,
                    loaded_version: "str | None",
                    skipped: "list[str] | None" = None) -> "tuple[list[str], list[str]]":
    """Veraltete markierte Kopien erneuern, Aliase entfernter Befehle loeschen.

    Gemeinsame Kernlogik von `setup.py --refresh-aliases` und dem Start-Hinweis
    (#399). Legt nie eine Datei an (#87/#205); unmarkierte, fremde oder
    unlesbare Dateien bleiben unberuehrt (#353). Kopien mit beweisbar neuerem
    Versions-Marker werden nicht herabgestuft (#163).

    Symlinks werden weder beschrieben noch geloescht, ein OSError an einer
    Datei bricht den Lauf nicht ab (#400). Beides landet als "<name>: <grund>"
    in `skipped`, falls eine Liste uebergeben wird.

    Liefert (erneuerte Namen, geloeschte Dateinamen).
    """
    stale = find_stale_aliases(skills_dir, commands_dir, loaded_version=loaded_version)
    refreshed = []
    for name in stale:
        target = commands_dir / f"{name}.md"
        # Symlink zeigt evtl. aus dem Schreibbereich heraus — nicht anfassen.
        if target.is_symlink():
            _skip(skipped, name, "Symlink")
            continue
        try:
            skill_text = (skills_dir / name / "SKILL.md").read_text()
        except (OSError, UnicodeDecodeError):
            _skip(skipped, name, "Skill nicht lesbar")
            continue
        try:
            target.write_text(alias_content(name, skill_text))
        except OSError as exc:
            _skip(skipped, name, _reason(exc))
            continue
        refreshed.append(name)
    removed = []
    for path in find_removed_aliases(commands_dir):
        if path.is_symlink():
            _skip(skipped, path.stem, "Symlink")
            continue
        try:
            path.unlink()
        except OSError as exc:
            _skip(skipped, path.stem, _reason(exc))
            continue
        removed.append(path.name)
    return refreshed, removed
