#!/usr/bin/env python3
"""SessionStart-Banner: zeigt, welche Framework-Version wirklich geladen ist.

Ausgabe (stdout, JSON) → `systemMessage`, die Claude Code dem User anzeigt:

    agent-os-openspec 3.23.0 aktiv

Zusaetzlich eine Warnzeile, wenn `setup.py --command-aliases` erzeugte
Befehls-Kopien in `~/.claude/commands` oder `<projekt>/.claude/commands`
veraltet sind. Solche Vollkopien (Skills mit `disable-model-invocation: true`)
aendern sich bei einem Plugin-Update NICHT mit — der User tippt `/name` und
bekommt still die alte Anleitung. Soll-Inhalt und Vergleich kommen aus
`alias_sync.py`, derselben Logik, mit der setup.py die Kopien schreibt.

Zwei Regeln haelt der Banner dabei ein (#163): Kopien mit einem beweisbar
neueren Versions-Marker als die geladene Fassung bleiben unerwaehnt — ein
Neuerzeugen wuerde sie herabstufen. Und der genannte Reparatur-Befehl kommt
immer aus der INSTALLIERTEN Fassung; laesst sie sich nicht aufloesen, nennt
der Banner gar keinen Pfad.

Robust by design: jede Exception → still Exit 0. Ein Banner darf den
Session-Start nie blockieren. Bei `framework: {enabled: false}` bzw.
OPENSPEC_FRAMEWORK=off wird nichts ausgegeben.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent


def plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if env:
        return Path(env)
    # core/hooks/session_banner.py → Plugin-Wurzel zwei Ebenen darueber
    return _HOOK_DIR.parent.parent


def plugin_version(root: Path) -> "str | None":
    try:
        data = json.loads((root / ".claude-plugin" / "plugin.json").read_text())
    except Exception:
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) and version else None


def _payload_cwd() -> "str | None":
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return None
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        cwd = data.get("cwd") if isinstance(data, dict) else None
        return cwd if isinstance(cwd, str) and cwd else None
    except Exception:
        return None


def project_dir(payload_cwd: "str | None") -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    return Path(env or payload_cwd or os.getcwd())


def installed_plugin() -> "tuple[Path, str] | None":
    """setup.py-Pfad und Version der INSTALLIERTEN Fassung, sonst None.

    Wirft nie: fehlende oder defekte Registry-Datei ergibt None.

    Quelle ist `~/.claude/plugins/installed_plugins.json`: der Eintrag, dessen
    Schluessel mit `agent-os-openspec@` beginnt, bevorzugt `scope: user`. Die
    Version kommt aus der `plugin.json` dieser Installation, nicht aus dem
    Verzeichnisnamen. Aufloesbar ist sie nur, wenn dort auch wirklich eine
    `setup.py` liegt — sonst waere der Reparatur-Befehl eine Luege.

    Bewusst NICHT `CLAUDE_PLUGIN_ROOT`: das ist die beim Session-Start
    eingefrorene, moeglicherweise aeltere Fassung (#163).
    """
    registry = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    entries = []
    try:
        data = json.loads(registry.read_text())
        for key, value in (data.get("plugins") or {}).items():
            if key.startswith("agent-os-openspec@") and isinstance(value, list):
                entries.extend(e for e in value if isinstance(e, dict))
    except Exception:
        return None
    if not entries:
        return None
    entry = next((e for e in entries if e.get("scope") == "user"), entries[0])
    install_path = entry.get("installPath")
    if not isinstance(install_path, str) or not install_path:
        return None
    root = Path(install_path)
    setup_py = root / "setup.py"
    version = plugin_version(root)
    if not setup_py.is_file() or not version:
        return None
    return setup_py, version


def _repair_hint(label: str, installed: "tuple[Path, str] | None") -> str:
    """Wie der User die Kopien erneuert — oder warum hier kein Befehl steht."""
    if installed is None:
        return ("installierte Plugin-Fassung nicht auffindbar — bitte Kopien "
                "nach dem Plugin-Update von Hand neu erzeugen")
    setup_py, version = installed
    if label == "~":
        # Der globale Lauf ueberschattet projekteigene Befehle (#87) — nie raten.
        return (f"global nicht neu erzeugen (#87) — stattdessen je Projekt mit "
                f"{version}: python3 {setup_py} <projekt> --command-aliases")
    return f"neu erzeugen mit {version}: python3 {setup_py} {label} --command-aliases"


def stale_alias_lines(root: Path, project: Path) -> "list[str]":
    """Eine Warnzeile je Scope (~ bzw. Projekt) mit veralteten Alias-Kopien."""
    from alias_sync import find_stale_aliases

    skills_dir = root / "skills"
    home = Path.home()
    scopes = [("~", home)]
    try:
        same = project.resolve() == home.resolve()
    except Exception:
        same = False
    if not same:
        scopes.append((str(project), project))

    loaded = plugin_version(root)
    try:
        installed = installed_plugin()
    except Exception:
        installed = None

    lines = []
    for label, scope in scopes:
        try:
            stale = find_stale_aliases(
                skills_dir, scope / ".claude" / "commands", loaded_version=loaded
            )
        except Exception:
            continue
        if stale:
            lines.append(
                f"Veraltete Befehls-Kopien: {', '.join(stale)} "
                f"(Scope {label}) — {_repair_hint(label, installed)}"
            )
    return lines


def build_message(root: Path, project: Path) -> "str | None":
    version = plugin_version(root)
    if not version:
        return None
    lines = [f"agent-os-openspec {version} aktiv"]
    lines.extend(stale_alias_lines(root, project))
    return "\n".join(lines)


def main() -> None:
    sys.path.insert(0, str(_HOOK_DIR))
    from hook_utils import framework_disabled

    payload_cwd = _payload_cwd()
    if framework_disabled():
        return
    message = build_message(plugin_root(), project_dir(payload_cwd))
    if message:
        print(json.dumps({"systemMessage": message}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
