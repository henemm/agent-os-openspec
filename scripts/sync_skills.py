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


def render_skill(command_text: str, frontmatter: str, version: str) -> str:
    """Skill-Inhalt aus Befehlstext + Frontmatter (ohne `---`) + Version."""
    body = command_text
    if _HOOK_PATH in body:
        body = insert_setup_block(rewrite_hook_paths(body))
    body = body.replace(VERSION_PLACEHOLDER, version)
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
        result[target] = render_skill(command_text, frontmatter, version)
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
