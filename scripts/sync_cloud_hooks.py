#!/usr/bin/env python3
"""hooks-Block der Projekt-.claude/settings.json aus hooks/hooks.json erzeugen (#520).

Cloud-Sitzungen (Claude Code on the web) laden keine Plugins — auch nicht ueber
`enabledPlugins` in der Projekt-settings.json. Ausgefuehrt werden dort nur
Hooks, die direkt in `.claude/settings.json` des Repos stehen. Ohne diesen
Block lief in der Cloud fuer dieses Repo kein einziges Gate.

hooks/hooks.json bleibt die einzige Quelle. Jeder Eintrag wird 1:1 uebernommen
(Event, Matcher, Reihenfolge, type, timeout, Argumente); nur das Kommando wird
umgeschrieben:

    ${CLAUDE_PLUGIN_ROOT}/core/hooks/<datei>.py<args>
  →
    [ "$CLAUDE_CODE_REMOTE" != "true" ] || CLAUDE_PLUGIN_ROOT="${CLAUDE_PROJECT_DIR}" \\
        python3 "${CLAUDE_PROJECT_DIR}/core/hooks/<datei>.py"<args>

Lokal (Variable fehlt oder ist nicht genau "true") endet der Befehl sofort mit
Exit 0 und liest stdin nicht — die Plugin-Kopie laeuft dort ohnehin, nichts
laeuft doppelt. In der Cloud startet das Skript aus dem Arbeitsstand dieses
Repos mit unveraendertem stdin; sein Exit-Code ist der des Befehls.

Ein Kommando, das nicht zu `setup._PLUGIN_HOOK_CMD_RE` passt, bricht die
Erzeugung ab (Exit 1) — lieber kein Block als ein halber Schutz.

    python3 scripts/sync_cloud_hooks.py          # hooks-Block neu schreiben
    python3 scripts/sync_cloud_hooks.py --check  # nur pruefen, Exit 1 bei Drift

Nach jeder Aenderung an hooks/hooks.json ausfuehren; `release_check.py`
(Zeile "Cloud-Hooks") blockt das Release bei Drift.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Die Zerlegung `${CLAUDE_PLUGIN_ROOT}/core/hooks/<datei>.py [args]` hat genau
# eine Quelle (#279, Copy-Modus in setup.py) — importiert, nicht kopiert.
# Der Import von setup.py ist seiteneffektarm (Konstanten, plugin.json lesen,
# alias_sync importieren; main() nur unter __main__), haengt aber core/hooks
# vorn an sys.path. Diesen Eingriff machen wir rueckgaengig, damit ein
# Aufrufer (release_check.py, Tests) keine fremden Module untergeschoben bekommt.
_saved_path = list(sys.path)
try:
    sys.path.insert(0, str(REPO_ROOT))
    from setup import _PLUGIN_HOOK_CMD_RE  # noqa: E402
finally:
    sys.path[:] = _saved_path
del _saved_path

CLOUD_COMMAND = ('[ "$CLAUDE_CODE_REMOTE" != "true" ] || '
                 'CLAUDE_PLUGIN_ROOT="${{CLAUDE_PROJECT_DIR}}" '
                 'python3 "${{CLAUDE_PROJECT_DIR}}/core/hooks/{script}"{args}')

SYNC_HINT = "python3 scripts/sync_cloud_hooks.py"


def cloud_command(plugin_command: str) -> str:
    """Plugin-Kommando → Cloud-Kommando; ValueError, wenn es nicht passt."""
    match = _PLUGIN_HOOK_CMD_RE.match(plugin_command)
    if not match:
        raise ValueError(f"Hook-Kommando nicht umsetzbar: {plugin_command!r}")
    return CLOUD_COMMAND.format(script=match.group(1), args=match.group(2))


def cloud_hooks(hooks_json: dict) -> dict:
    """Reine Funktion: `hooks`-Block fuer die Projekt-settings.json.

    Alle Felder bleiben in Reihenfolge erhalten, nur `command` wird ersetzt.
    """
    result: dict = {}
    for event, groups in hooks_json.get("hooks", {}).items():
        out_groups = []
        for group in groups:
            out_group = copy.deepcopy(group)
            for hook in out_group.get("hooks", []):
                hook["command"] = cloud_command(hook["command"])
            out_groups.append(out_group)
        result[event] = out_groups
    return result


def _paths(root: Path) -> "tuple[Path, Path]":
    return root / "hooks" / "hooks.json", root / ".claude" / "settings.json"


def _read_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} ist kein JSON-Objekt")
    return data


def expected_hooks(root: Path = REPO_ROOT) -> dict:
    hooks_path, _ = _paths(root)
    return cloud_hooks(json.loads(hooks_path.read_text(encoding="utf-8")))


def check(root: Path = REPO_ROOT) -> "tuple[bool, str]":
    """(synchron?, Meldung) — schreibt nichts."""
    _, settings_path = _paths(root)
    try:
        expected = expected_hooks(root)
        actual = _read_settings(settings_path).get("hooks")
    except (OSError, ValueError) as exc:
        return False, f"Cloud-Hooks nicht pruefbar: {exc} — {SYNC_HINT}"
    if actual != expected:
        return False, (f"Cloud-Hooks nicht synchron: hooks-Block in .claude/settings.json "
                       f"weicht von hooks/hooks.json ab — {SYNC_HINT} ausführen")
    count = sum(len(g.get("hooks", [])) for groups in expected.values() for g in groups)
    return True, f"Cloud-Hooks synchron mit hooks/hooks.json ({count} Einträge)"


def write(root: Path = REPO_ROOT) -> bool:
    """hooks-Block ersetzen, alle anderen Schluessel unveraendert; True = geaendert."""
    _, settings_path = _paths(root)
    settings = _read_settings(settings_path)
    settings["hooks"] = expected_hooks(root)
    text = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
    if settings_path.exists() and settings_path.read_text(encoding="utf-8") == text:
        return False
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="nichts schreiben; Exit 1, wenn der hooks-Block abweicht")
    parser.add_argument("--root", type=Path, default=REPO_ROOT,
                        help="Repo-Wurzel mit hooks/hooks.json und .claude/settings.json "
                             "(Default: dieses Repo)")
    args = parser.parse_args()
    root = args.root.resolve()

    if args.check:
        ok, msg = check(root)
        print(msg, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    try:
        changed = write(root)
    except (OSError, ValueError) as exc:
        print(f"Cloud-Hooks nicht erzeugt: {exc}", file=sys.stderr)
        return 1
    print(".claude/settings.json: hooks-Block "
          + ("neu geschrieben." if changed else "unveraendert."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
