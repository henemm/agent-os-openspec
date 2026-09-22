#!/usr/bin/env python3
"""skills/*/SKILL.md aus core/commands/*.md erzeugen — core/commands ist die Quelle.

Das Plugin liefert zur Laufzeit NUR skills/<name>/SKILL.md aus; entwickelt wird
in core/commands/<name>.md (auch Quelle des alten setup.py-Kopiermodus). Ohne
Generator liefen beide auseinander: zwischen 3.18 und 3.22 erreichte keine
Aenderung an den Befehlen einen Plugin-Nutzer.

Transformationen (Befehl → Skill):
  1. YAML-Frontmatter der bestehenden SKILL.md voranstellen (description,
     disable-model-invocation bleiben erhalten — sie sind Skill-Metadaten,
     die es in core/commands nicht gibt).
  2. Referenziert der Befehl Hook-Pfade: Setup-Block (Hook-Pfad-Aufloesung
     fuer Plugin-Installationen) vor die erste `## `-Ueberschrift.
  3. `python3 .claude/hooks/workflow.py` → `$WF`,
     `python3 .claude/hooks/<x>.py` → `python3 ${_H}/<x>.py`,
     sonstige `.claude/hooks/` → `${_H}/`.
  4. `{{OPENSPEC_VERSION}}` → Version aus .claude-plugin/plugin.json.
  5. Versions-Marker anhaengen: jede Phase endet mit `⚙ /<befehl> ·
     agent-os-openspec <version>`. Ohne ihn sieht der PO am Ergebnis nicht,
     ob ueberhaupt die neue Fassung geladen war (bis 3.23 nur bei
     /30-write-spec sichtbar).

    python3 scripts/sync_skills.py          # alle Skills neu schreiben
    python3 scripts/sync_skills.py --check  # nur pruefen, Exit 1 bei Drift
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS_DIR = REPO_ROOT / "core" / "commands"
SKILLS_DIR = REPO_ROOT / "skills"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"

VERSION_PLACEHOLDER = "{{OPENSPEC_VERSION}}"

# Hook-Pfad-Aufloesung fuer Skills. Bewusst als Konstante hier und nicht aus
# einer generierten SKILL.md gelesen: der Generator soll eine reine Funktion
# von core/commands + Frontmatter sein.
SETUP_BLOCK = (
    "## Setup\n"
    "\n"
    "```bash\n"
    "# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks\n"
    '_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"\n'
    'if [ -z "$_H" ]; then _p="$(python3 -c \'import json,os;d=json.load(open(os.path.expanduser('
    '"~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in '
    'd.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in '
    '[next((x for x in v if x.get("scope")=="user"),v[0])]),""))\' 2>/dev/null)"; '
    '[ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi\n'
    '_H="${_H:-.claude/hooks}"\n'
    'WF="python3 ${_H}/workflow.py"\n'
    "```\n"
    "\n"
)

DEFAULT_FRONTMATTER = {"description": "", "disable-model-invocation": "false"}

_HOOK_PATH = ".claude/hooks/"

# 30-write-spec gibt die Freigabe woertlich als Briefing plus eigene
# Marker-Zeile aus ("keine eigene Zusammenfassung davor oder danach"). Ein
# generischer Zusatz-Marker kollidiert mit dieser strikten Vorlage — und die
# Version steht dort ohnehin schon in der Ausgabe.
MARKER_EXEMPT = {"30-write-spec"}


def marker_block(name: str, version: str) -> str:
    """Pflicht-Abschnitt: Statuszeile + Versions-Marker am Ende jeder Phase.

    Die Statuszeile (3.25.0) steht hier zentral und nicht in 16 Befehlsdateien:
    Sie ist in jeder Phase dieselbe Regel, und sie muss zur Formulierung passen,
    die der Hook `phase_listener.py` liefert — zwei Fassungen driften sofort
    auseinander.
    """
    return (
        "## Versions-Marker (Pflicht)\n"
        "\n"
        "Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, "
        "in dieser Reihenfolge:\n"
        "\n"
        "❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>\n"
        "ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8\n"
        f"⚙ /{name} · agent-os-openspec {version}\n"
        "\n"
        "Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der "
        "Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und "
        "steht in genau einer von zwei Formen: `❗ Du: …`, wenn der PO den Schritt "
        "tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt "
        "`❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und "
        "nur auf den nächsten Befehl des PO wartest — das ist niemals „nichts zu "
        "tun“. Oder `ℹ️ Nichts zu tun: <du arbeitest gerade selbst / wartest auf "
        "ein Ergebnis, z. B. einen Hintergrund-Agenten> — danach: /<befehl> "
        "#<N>`, ausschließlich wenn du auf etwas ANDERES als den PO wartest. So "
        "muss der PO nie raten, ob etwas von ihm erwartet wird.\n"
        "\n"
        "Schritt und Phase übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER "
        "WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der "
        "Schritt „Nächster Pflicht-Schritt“) — Phase und Schritt wörtlich von dort. "
        "Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfallen die "
        "erste Zeile und die Statuszeile.\n"
        "\n"
        "Hast DU SELBST in dieser Nachricht per `workflow.py phase <x>` (oder "
        "`complete`) die Phase gewechselt, ist der Hinweis noch der ALTE Stand von "
        "Turn-Beginn — nutze trotzdem den NEUEN, von dir selbst herbeigeführten "
        "Stand für Schritt und Phase. Die Marker-Zeilen entfallen NIE aus diesem "
        "Grund; die ⚙-Zeile bleibt immer die letzte Zeile.\n"
        "\n"
        "Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei "
        "Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ "
        "oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab "
        "`phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). "
        "In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor "
        "jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit "
        "einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben "
        "bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)\n"
        "\n"
        "In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die "
        "Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile "
        "übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal "
        "in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen "
        "abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der "
        "Nachricht, auch wenn die übrigen Zeilen entfallen.\n"
    )


def plugin_version() -> str:
    return json.loads(PLUGIN_JSON.read_text()).get("version", "")


def extract_frontmatter(skill_text: str) -> "str | None":
    """Frontmatter-Block (ohne die `---`-Zeilen) einer SKILL.md, oder None."""
    match = re.match(r"^---\n(.*?\n)---\n", skill_text, re.DOTALL)
    return match.group(1) if match else None


def rewrite_hook_paths(body: str) -> str:
    body = body.replace("python3 .claude/hooks/workflow.py", "$WF")
    body = re.sub(r"python3 \.claude/hooks/([\w.-]+\.py)", r"python3 ${_H}/\1", body)
    return body.replace(_HOOK_PATH, "${_H}/")


def insert_setup_block(body: str) -> str:
    match = re.search(r"^## ", body, re.MULTILINE)
    if match is None:
        return body.rstrip("\n") + "\n\n" + SETUP_BLOCK
    return body[:match.start()] + SETUP_BLOCK + body[match.start():]


def render_skill(command_text: str, frontmatter: str, version: str,
                 name: "str | None" = None) -> str:
    """Skill-Inhalt aus Befehlstext + Frontmatter (ohne `---`) + Version.

    `name` = Befehlsname; nur damit wird der Versions-Marker angehaengt
    (nicht fuer MARKER_EXEMPT). Der Marker kommt ganz zuletzt, nach
    Setup-Block und Platzhalter-Ersetzung.
    """
    body = command_text
    if _HOOK_PATH in body:
        body = insert_setup_block(rewrite_hook_paths(body))
    body = body.replace(VERSION_PLACEHOLDER, version)
    if name is not None and name not in MARKER_EXEMPT:
        body = body.rstrip("\n") + "\n\n" + marker_block(name, version)
    return f"---\n{frontmatter}---\n\n{body}"


def _default_frontmatter() -> str:
    return "".join(f"{k}: {v}\n" for k, v in DEFAULT_FRONTMATTER.items())


def synced_names(commands_dir: Path = COMMANDS_DIR, skills_dir: Path = SKILLS_DIR) -> "list[str]":
    """Namen, die als Befehl UND als Skill existieren (alte Kurznamen ignoriert)."""
    return sorted(
        p.stem for p in commands_dir.glob("*.md")
        if (skills_dir / p.stem).is_dir()
    )


def expected_skills(commands_dir: Path = COMMANDS_DIR, skills_dir: Path = SKILLS_DIR,
                    version: "str | None" = None) -> "dict[Path, str]":
    """Soll-Inhalt je SKILL.md-Pfad."""
    version = plugin_version() if version is None else version
    result = {}
    for name in synced_names(commands_dir, skills_dir):
        target = skills_dir / name / "SKILL.md"
        current = target.read_text() if target.exists() else ""
        frontmatter = extract_frontmatter(current) or _default_frontmatter()
        command_text = (commands_dir / f"{name}.md").read_text()
        result[target] = render_skill(command_text, frontmatter, version, name)
    return result


def check(commands_dir: Path = COMMANDS_DIR, skills_dir: Path = SKILLS_DIR,
          version: "str | None" = None) -> "list[str]":
    """Namen der Skills, deren SKILL.md vom Generat abweicht."""
    drift = []
    for target, content in expected_skills(commands_dir, skills_dir, version).items():
        if not target.exists() or target.read_text() != content:
            drift.append(target.parent.name)
    return drift


def write(commands_dir: Path = COMMANDS_DIR, skills_dir: Path = SKILLS_DIR,
          version: "str | None" = None) -> "list[str]":
    """Alle Skills neu schreiben. Gibt die tatsaechlich geaenderten Namen zurueck."""
    changed = []
    for target, content in expected_skills(commands_dir, skills_dir, version).items():
        if not target.exists() or target.read_text() != content:
            target.write_text(content)
            changed.append(target.parent.name)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="nichts schreiben; Exit 1, wenn ein Skill abweicht")
    args = parser.parse_args()

    if args.check:
        drift = check()
        if drift:
            print("Skills weichen von core/commands ab: " + ", ".join(drift), file=sys.stderr)
            print("→ python3 scripts/sync_skills.py ausführen", file=sys.stderr)
            return 1
        print(f"Skills synchron ({len(synced_names())} geprüft).")
        return 0

    changed = write()
    print(f"{len(changed)} Skill(s) neu geschrieben"
          + (": " + ", ".join(changed) if changed else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
