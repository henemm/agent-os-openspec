#!/usr/bin/env python3
"""
OpenSpec Framework - Setup Tool

Installs and configures the OpenSpec framework for a new project.

Usage:
    python3 setup.py /path/to/project [--module home-assistant]
    python3 setup.py /path/to/project --update
    python3 setup.py --help

This tool:
1. Creates .claude/ directory structure
2. Copies core hooks and commands
3. Optionally installs module-specific components
4. Generates settings.json with hook configuration
5. Creates initial docs/ structure
6. Can update existing installations with --update
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from datetime import datetime
import hashlib


FRAMEWORK_ROOT = Path(__file__).parent


def _read_plugin_version() -> str:
    plugin_json = FRAMEWORK_ROOT / ".claude-plugin" / "plugin.json"
    if plugin_json.exists():
        try:
            return json.loads(plugin_json.read_text()).get("version", "3.0.0")
        except Exception:
            pass
    return "3.0.0"


FRAMEWORK_VERSION = _read_plugin_version()
CORE_DIR = FRAMEWORK_ROOT / "core"
MODULES_DIR = FRAMEWORK_ROOT / "modules"
TEMPLATES_DIR = FRAMEWORK_ROOT / "templates"
SCRIPTS_DIR = FRAMEWORK_ROOT / "scripts"

# Alias-Inhalt hat genau eine Quelle (Issue #150). Dieselben Funktionen nutzt
# das SessionStart-Banner, um veraltete Kopien zu erkennen — zwei Fassungen
# derselben Logik wuerden auseinanderlaufen und der Banner meldete falsch.
sys.path.insert(0, str(CORE_DIR / "hooks"))
from alias_sync import (  # noqa: E402
    ALIAS_MARKER,
    _read_or_none,
    alias_content,
    embeds_full_skill,
    is_alias_file,
    skill_names,
)

# Platzhalter, den sync_skills.py fuer skills/ ersetzt. Im Kopiermodus kopierte
# setup.py die Befehle unveraendert — im Zielprojekt landete die rohe
# Platzhalter-Zeile (Issue #150).
VERSION_PLACEHOLDER = "{{OPENSPEC_VERSION}}"

# Laufzeit-Zustand, den das Framework im Projektordner anlegt. Nichts davon
# gehoert je in ein Repository — `.claude/active_workflow` existiert genau
# waehrend eines Workflows, also genau dann, wenn committet wird, und ein
# `git add -A` nimmt sie mit (Issue #78). Das Framework kennt diese Liste als
# einziges, weil es die Dateien selbst anlegt; also traegt es sie auch ein,
# statt es jedem Konsumenten-Projekt einzeln zu ueberlassen.
GITIGNORE_RUNTIME_ENTRIES = [
    ".claude/active_workflow",
    ".claude/workflows/",
    ".claude/session-locks/",
    ".claude/stop_lock.json",
    ".claude/user_override_token.json",
    ".claude/pending_validation_*.json",
    ".claude/user_approved_validation_*",
    ".claude/gate-events.jsonl",
    ".worktrees/",
]

GITIGNORE_SECTION_HEADER = "# OpenSpec runtime state (never commit)"

# Von Claude Code in Hook-Kommandos ersetzt: Projekt-Root, in dem die Sitzung
# gestartet ist. Einzige verlaessliche Verankerung fuer Hook-Pfade — Hooks
# laufen im aktuellen Arbeitsverzeichnis, nicht im Projekt-Root (Issue #165).
# Wird auch von migrate_to_plugin.py importiert: eine Quelle fuer die Schreibweise.
PROJECT_DIR_PLACEHOLDER = "${CLAUDE_PROJECT_DIR}"

# Im Plugin-Modus darf `framework_version.json` KEINE Versionsnummer nennen.
# Sie waere die Version des setup.py, das zufaellig gerade lief: danach laufen
# alle Aktualisierungen ueber `claude plugin update`, und das ruehrt die Datei
# nie an. Die Zahl ist damit ab der ersten Aktualisierung falsch — gemessen in
# henemm/gregor_zwanzig (Datei: 3.4.13, ausgeliefertes Plugin: 3.25.1).
# Im Copy-Modus bleibt sie richtig und wird weiter geschrieben: dort hat
# setup.py die Dateien selbst kopiert, die Datei IST dort die Auskunftsquelle.
PLUGIN_MODE_VERSION_SOURCE = "plugin"
PLUGIN_MODE_VERSION_NOTE = (
    "Im Plugin-Modus pinnt diese Datei keine Version — Updates laufen ueber "
    "`claude plugin update` und aendern sie nicht. Massgeblich ist das geladene "
    "Plugin: `claude plugin list`, oder der Marker am Ende jeder Phase "
    "(⚙ /<befehl> · agent-os-openspec <version>)."
)


def get_file_hash(path: Path) -> str:
    """Get MD5 hash of a file for comparison."""
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


def should_update_file(src: Path, dst: Path, force: bool = False) -> tuple[bool, str]:
    """
    Determine if a file should be updated.
    Returns (should_update, reason).
    """
    if not dst.exists():
        return True, "new file"

    if force:
        return True, "forced update"

    src_hash = get_file_hash(src)
    dst_hash = get_file_hash(dst)

    if src_hash != dst_hash:
        return True, "content changed"

    return False, "unchanged"


def ensure_gitignore_entries(project_path: Path) -> None:
    """Laufzeit-Eintraege in die `.gitignore` des Projekts aufnehmen (Issue #78).

    Legt die Datei an, wenn sie fehlt, und haengt nur an, was noch nicht
    drinsteht. Vorhandener Inhalt bleibt unangetastet — eine `.gitignore` ist
    Projekteigentum, das Framework traegt dort nur seine eigenen Spuren ein.
    """
    gitignore = project_path / ".gitignore"
    existing_text = gitignore.read_text() if gitignore.exists() else ""
    present = {line.strip() for line in existing_text.splitlines()}

    missing = [e for e in GITIGNORE_RUNTIME_ENTRIES if e not in present]
    if not missing:
        return

    parts = []
    if existing_text and not existing_text.endswith("\n"):
        # Sonst klebt der erste neue Eintrag an der letzten vorhandenen Zeile.
        parts.append("\n")
    if existing_text:
        parts.append("\n")
    parts.append(GITIGNORE_SECTION_HEADER + "\n")
    parts.extend(entry + "\n" for entry in missing)

    with open(gitignore, "a") as f:
        f.write("".join(parts))

    print(f"  Updated: .gitignore ({len(missing)} Eintrag/Eintraege ergaenzt)")


def create_directory_structure(project_path: Path):
    """Create the .claude/, .agent-os/, and docs/ directory structure."""
    dirs = [
        ".claude/hooks",
        ".claude/agents",
        ".claude/commands",
        ".claude/tools",
        ".claude/scripts",
        ".claude/workflows",
        ".claude/workflows/_archive",
        ".claude/artifacts/screenshots",
        ".agent-os/standards/global",
        "docs/specs",
        "docs/reference",
        "docs/features",
        "docs/project",
    ]

    for d in dirs:
        (project_path / d).mkdir(parents=True, exist_ok=True)
        print(f"  Created: {d}/")


def copy_command_text(text: str) -> str:
    """Befehlstext fuer den Kopiermodus aufbereiten (Issue #150).

    `scripts/sync_skills.py` ersetzt `{{OPENSPEC_VERSION}}` beim Erzeugen von
    `skills/`. Der Kopiermodus kopierte dieselben Quelldateien unveraendert —
    im Zielprojekt stand danach die rohe Platzhalter-Zeile in der Ausgabe, die
    der Befehl woertlich ausgeben soll.
    """
    return text.replace(VERSION_PLACEHOLDER, FRAMEWORK_VERSION)


def copy_command_file(src: Path, dst: Path) -> None:
    """Eine Befehlsdatei kopieren und dabei Platzhalter ersetzen."""
    dst.write_text(copy_command_text(src.read_text()))


def should_update_command(src: Path, dst: Path, force: bool = False) -> tuple[bool, str]:
    """Wie `should_update_file`, aber fuer Befehle mit ersetzten Platzhaltern.

    Ein Hash-Vergleich gegen die *Quelle* meldete jeden Befehl mit Platzhalter
    bei jedem Update als geaendert, weil das Ziel den ersetzten Text traegt.
    Verglichen wird deshalb gegen das, was hier tatsaechlich geschrieben wuerde.
    """
    if not dst.exists():
        return True, "new file"
    if force:
        return True, "forced update"
    if copy_command_text(src.read_text()) != dst.read_text():
        return True, "content changed"
    return False, "unchanged"


def copy_core_components(project_path: Path):
    """Copy core hooks, agents, commands, and tools."""
    # Copy hooks
    hooks_src = CORE_DIR / "hooks"
    hooks_dst = project_path / ".claude" / "hooks"

    for hook_file in hooks_src.glob("*.py"):
        shutil.copy(hook_file, hooks_dst / hook_file.name)
        print(f"  Copied hook: {hook_file.name}")

    # Copy agents
    agents_src = CORE_DIR / "agents"
    agents_dst = project_path / ".claude" / "agents"

    for agent_file in agents_src.glob("*.md"):
        shutil.copy(agent_file, agents_dst / agent_file.name)
        print(f"  Copied agent: {agent_file.name}")

    # Copy commands
    commands_src = CORE_DIR / "commands"
    commands_dst = project_path / ".claude" / "commands"

    for cmd_file in commands_src.glob("*.md"):
        copy_command_file(cmd_file, commands_dst / cmd_file.name)
        print(f"  Copied command: {cmd_file.name}")

    # Copy tools (v2.0 - validation, E2E testing, output validation)
    tools_src = CORE_DIR / "tools"
    tools_dst = project_path / ".claude" / "tools"

    if tools_src.exists():
        tools_dst.mkdir(parents=True, exist_ok=True)
        for tool_file in tools_src.glob("*.py"):
            shutil.copy(tool_file, tools_dst / tool_file.name)
            print(f"  Copied tool: {tool_file.name}")

    # Copy standards (v2.0 - scoping limits, testing, etc.)
    standards_src = CORE_DIR / "standards"
    standards_dst = project_path / ".agent-os" / "standards"

    if standards_src.exists():
        for subdir in standards_src.iterdir():
            if subdir.is_dir():
                dst_subdir = standards_dst / subdir.name
                dst_subdir.mkdir(parents=True, exist_ok=True)
                for std_file in subdir.glob("*.md"):
                    shutil.copy(std_file, dst_subdir / std_file.name)
                    print(f"  Copied standard: {subdir.name}/{std_file.name}")


def install_ci_gate(project_path: Path, force: bool = False):
    """Installiere das serverseitige Spec-Gate (Script + GitHub-Action-Vorlage).

    Die lokalen Hooks sind abschaltbar; dieses Gate prueft dieselben Regeln noch
    einmal auf dem Server, wo niemand sie umschreiben kann. Die Action-Vorlage
    wird NIE ueberschrieben — die CI eines Projekts gehoert dem Projekt.
    """
    script_src = SCRIPTS_DIR / "ci_spec_gate.py"
    if not script_src.exists():
        return
    scripts_dst = project_path / ".claude" / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    shutil.copy(script_src, scripts_dst / script_src.name)
    print(f"  Copied CI gate: .claude/scripts/{script_src.name}")

    workflow_src = TEMPLATES_DIR / "ci_spec_gate.yml"
    workflow_dst = project_path / ".github" / "workflows" / "spec-gate.yml"
    if not workflow_src.exists():
        return
    if workflow_dst.exists() and not force:
        print("  Skipped: .github/workflows/spec-gate.yml (existiert bereits)")
        return
    workflow_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(workflow_src, workflow_dst)
    print("  Created: .github/workflows/spec-gate.yml")


def install_module(project_path: Path, module_name: str):
    """Install a specific module."""
    module_dir = MODULES_DIR / module_name

    if not module_dir.exists():
        print(f"  ERROR: Module '{module_name}' not found")
        return False

    # Copy module hooks
    hooks_src = module_dir / "hooks"
    if hooks_src.exists():
        hooks_dst = project_path / ".claude" / "hooks"
        for hook_file in hooks_src.glob("*.py"):
            shutil.copy(hook_file, hooks_dst / hook_file.name)
            print(f"  Copied module hook: {hook_file.name}")

    # Copy module agents
    agents_src = module_dir / "agents"
    if agents_src.exists():
        agents_dst = project_path / ".claude" / "agents"
        for agent_file in agents_src.glob("*.md"):
            shutil.copy(agent_file, agents_dst / agent_file.name)
            print(f"  Copied module agent: {agent_file.name}")

    # Copy module commands (slash commands)
    commands_src = module_dir / "commands"
    if commands_src.exists():
        commands_dst = project_path / ".claude" / "commands"
        for cmd_file in commands_src.glob("*.md"):
            copy_command_file(cmd_file, commands_dst / cmd_file.name)
            print(f"  Copied module command: {cmd_file.name}")

    # Copy module tools
    tools_src = module_dir / "tools"
    if tools_src.exists():
        tools_dst = project_path / "tools"
        tools_dst.mkdir(exist_ok=True)
        for tool_file in tools_src.glob("*"):
            if tool_file.is_file():
                shutil.copy(tool_file, tools_dst / tool_file.name)
                print(f"  Copied tool: {tool_file.name}")

    # Copy module standards (for ios-swiftui and similar modules)
    standards_src = module_dir / "standards"
    if standards_src.exists():
        standards_dst = project_path / ".agent-os" / "standards"
        for subdir in standards_src.iterdir():
            if subdir.is_dir():
                dst_subdir = standards_dst / subdir.name
                dst_subdir.mkdir(parents=True, exist_ok=True)
                for std_file in subdir.glob("*.md"):
                    shutil.copy(std_file, dst_subdir / std_file.name)
                    print(f"  Copied standard: {subdir.name}/{std_file.name}")

    # Copy module workflows
    workflows_src = module_dir / "workflows"
    if workflows_src.exists():
        workflows_dst = project_path / ".agent-os" / "workflows"
        workflows_dst.mkdir(parents=True, exist_ok=True)
        for wf_file in workflows_src.glob("*.md"):
            shutil.copy(wf_file, workflows_dst / wf_file.name)
            print(f"  Copied workflow: {wf_file.name}")

    # Copy module templates
    templates_src = module_dir / "templates"
    if templates_src.exists():
        docs_dst = project_path / "DOCS"
        docs_dst.mkdir(exist_ok=True)
        for tmpl_file in templates_src.glob("*.md"):
            shutil.copy(tmpl_file, docs_dst / tmpl_file.name)
            print(f"  Copied template: {tmpl_file.name}")

    # Copy module config
    module_config = module_dir / "config.yaml"
    if module_config.exists():
        dst = project_path / ".claude" / f"module_{module_name}.yaml"
        shutil.copy(module_config, dst)
        print(f"  Copied module config: module_{module_name}.yaml")

    return True


_PLUGIN_HOOK_CMD_RE = re.compile(r"^\$\{CLAUDE_PLUGIN_ROOT\}/core/hooks/(\S+\.py)(.*)$")

# Modul-Hooks (modules/<name>/config.yaml -> hooks:) haengen an diese Gruppen an.
_MODULE_HOOK_SLOTS = {
    "edit_write": ("PreToolUse", "Edit|Write|MultiEdit", 5),
    "bash": ("PreToolUse", "Bash", 300),
    "post_bash": ("PostToolUse", "Bash", 5),
    "user_prompt": ("UserPromptSubmit", None, 5),
}


def copy_mode_hooks(project_path: Path, modules: list) -> dict:
    """Hook-Registrierung fuer den Copy-Modus, abgeleitet aus hooks/hooks.json (#279).

    Vorher fuehrte setup.py eine eigene Liste mit 4 der Kern-Hooks; Worktree-
    Pflicht, Secrets-Guard, Egress-Guard, Edit-Verify und die Events
    SessionStart/SessionEnd fehlten im Copy-Modus still. Jetzt gibt es eine
    Quelle: jeder Eintrag aus hooks.json wird auf die kopierte Datei
    umgeschrieben (`python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/x.py" [args]`,
    Issue #165). Fehlt eine kopierte Datei, bricht die Erzeugung ab — ein
    halber Schutz, der wie ein ganzer aussieht, ist das, was #279 beseitigt.
    """
    hooks_dir = project_path / ".claude" / "hooks"
    plugin_hooks = json.loads((FRAMEWORK_ROOT / "hooks" / "hooks.json").read_text())["hooks"]

    def project_command(hook_name: str, args: str = "") -> str:
        if not (hooks_dir / hook_name).exists():
            raise FileNotFoundError(
                f".claude/hooks/{hook_name} fehlt — in hooks/hooks.json registriert, aber nicht kopiert"
            )
        return f'python3 "{PROJECT_DIR_PLACEHOLDER}/.claude/hooks/{hook_name}"{args}'

    result: dict = {}
    for event, groups in plugin_hooks.items():
        result[event] = []
        for group in groups:
            entries = []
            for hook in group["hooks"]:
                match = _PLUGIN_HOOK_CMD_RE.match(hook["command"])
                if not match:
                    raise ValueError(f"hooks.json: unbekanntes Kommando-Format: {hook['command']}")
                entries.append({**hook, "command": project_command(match.group(1), match.group(2))})
            result[event].append({**group, "hooks": entries})

    for module_name in modules:
        module_config_path = MODULES_DIR / module_name / "config.yaml"
        if not module_config_path.exists():
            continue
        try:
            import yaml
            with open(module_config_path, 'r') as f:
                module_hooks = (yaml.safe_load(f) or {}).get("hooks", {}) or {}
        except Exception as e:
            print(f"  WARNING: Could not load hooks from {module_name}: {e}")
            continue
        for slot, (event, matcher, timeout) in _MODULE_HOOK_SLOTS.items():
            names = [n for n in module_hooks.get(slot, []) if (hooks_dir / n).exists()]
            if not names:
                continue
            groups = result.setdefault(event, [])
            group = next((g for g in groups if g.get("matcher") == matcher), None)
            if group is None:
                group = {"matcher": matcher, "hooks": []} if matcher else {"hooks": []}
                groups.append(group)
            group["hooks"].extend(
                {"type": "command", "command": project_command(n), "timeout": timeout}
                for n in names
            )
        print(f"  Loaded module hooks from: {module_name}")
    return result


def merge_missing_copy_mode_hooks(project_path: Path, modules: list) -> list:
    """`--update` im Copy-Modus: fehlende Framework-Hooks in settings.json nachtragen (#279).

    Bestehende Eintraege (eigene Hooks, Rechte, geaenderte Timeouts) bleiben
    unangetastet; ergaenzt wird nur, was in der Gruppe mit demselben Matcher
    noch fehlt. Ein Hook gilt als vorhanden, wenn ein Kommando der Gruppe
    `.claude/hooks/<datei>` mit denselben Argumenten aufruft — egal in welcher
    Schreibweise. Eine unerwartete Struktur bricht das Update nicht ab, sondern
    hinterlaesst eine Warnung und eine unveraenderte Datei.
    Rueckgabe: die ergaenzten Kommandos (leer = nichts zu tun).
    """
    settings_path = project_path / ".claude" / "settings.json"
    try:
        settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
        before = json.dumps(settings, sort_keys=True)
        wanted = copy_mode_hooks(project_path, modules)
        added = _merge_hook_entries(settings, wanted)
    except Exception as e:  # nie das ganze Update abbrechen (Struktur unbekannt)
        print(f"  WARNING: Hook-Registrierung nicht abgeglichen ({type(e).__name__}: {e}) — "
              ".claude/settings.json bitte pruefen")
        return []
    if json.dumps(settings, sort_keys=True) != before:
        try:
            settings_path.write_text(json.dumps(settings, indent=2) + "\n")
        except OSError as e:
            print(f"  WARNING: .claude/settings.json nicht schreibbar ({e})")
            return []
    return added


# Vor #279 registrierte der Copy-Modus Edit-Hooks unter "Edit|Write" — MultiEdit
# blieb dort ungeprueft. Gruppen, die NUR Framework-Hooks enthalten, werden auf
# den Plugin-Matcher angehoben.
_LEGACY_MATCHERS = {"Edit|Write": "Edit|Write|MultiEdit"}


def _merge_hook_entries(settings: dict, wanted: dict) -> list:
    if not isinstance(settings, dict):
        raise ValueError("settings.json ist kein JSON-Objekt")
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("'hooks' ist kein JSON-Objekt")

    def key(hook) -> "tuple[str, str] | None":
        command = hook.get("command", "") if isinstance(hook, dict) else ""
        m = re.search(r'\.claude/hooks/(\S+?\.py)"?(.*)$', command or "")
        return (m.group(1), m.group(2).strip()) if m else None

    added = []
    for event, groups in wanted.items():
        existing_groups = hooks.setdefault(event, [])
        if not isinstance(existing_groups, list):
            raise ValueError(f"'hooks.{event}' ist keine Liste")
        if any(not isinstance(g, dict) or not isinstance(g.get("hooks", []), list)
               or not all(isinstance(h, dict) for h in g.get("hooks", []))
               for g in existing_groups):
            raise ValueError(f"'hooks.{event}' enthaelt eine ungueltige Gruppe")
        matchers = {g.get("matcher") for g in existing_groups}
        for g in existing_groups:
            new_matcher = _LEGACY_MATCHERS.get(g.get("matcher"))
            if (new_matcher and new_matcher not in matchers
                    and g.get("hooks") and all(key(h) for h in g["hooks"])):
                g["matcher"] = new_matcher
                matchers.add(new_matcher)
        for group in groups:
            target = next((g for g in existing_groups
                           if g.get("matcher") == group.get("matcher")), None)
            # Eine verbliebene Alt-Gruppe (gemischt oder neben der neuen) zaehlt mit —
            # sonst liefe derselbe Hook bei Edit/Write zweimal.
            legacy = [old for old, new in _LEGACY_MATCHERS.items() if new == group.get("matcher")]
            present = {key(h) for g in existing_groups
                       if g is target or g.get("matcher") in legacy for h in g.get("hooks", [])}
            missing = [h for h in group["hooks"] if key(h) not in present]
            if not missing:
                continue
            if target is None:
                target = {k: v for k, v in group.items() if k != "hooks"}
                target["hooks"] = []
                existing_groups.append(target)
            target.setdefault("hooks", []).extend(missing)
            added += [f"{event}: {h['command']}" for h in missing]
    return added


def generate_settings_json(project_path: Path, modules: list):
    """Generate .claude/settings.json for copy mode — same hooks as the plugin (#279)."""
    settings = {
        "permissions": {
            "allow": ["Bash", "WebSearch", "WebFetch"],
            "deny": [],
            "ask": []
        },
        "hooks": copy_mode_hooks(project_path, modules),
    }

    settings_path = project_path / ".claude" / "settings.json"
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)

    print(f"  Generated: .claude/settings.json")


def generate_settings_json_plugin_mode(project_path: Path, modules: list):
    """Generate settings.json using ${CLAUDE_PLUGIN_ROOT} references — no hook files copied."""
    hooks_json_path = FRAMEWORK_ROOT / "hooks" / "hooks.json"
    if not hooks_json_path.exists():
        print("  ERROR: hooks/hooks.json not found in plugin root — cannot generate plugin-mode settings.")
        return

    hooks_data = json.loads(hooks_json_path.read_text())

    settings = {
        "permissions": {
            "allow": ["Bash", "WebSearch", "WebFetch"],
            "deny": [],
            "ask": []
        },
        "hooks": hooks_data["hooks"]
    }

    if modules:
        settings["env"] = {
            "OPENSPEC_ENABLED_MODULES": ",".join(modules)
        }

    settings_path = project_path / ".claude" / "settings.json"
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)
    print(f"  Generated: .claude/settings.json (plugin mode, modules: {modules or 'none'})")


def install_plugin_mode(project_path: Path, modules: list):
    """Install in plugin mode — no hook copying, uses ${CLAUDE_PLUGIN_ROOT} references."""
    print(f"\nOpenSpec Framework Setup (Plugin Mode)")
    print(f"=======================================")
    print(f"Framework version: {FRAMEWORK_VERSION}")
    print(f"Project: {project_path}")
    print(f"Modules: {modules or ['core only']}")
    print()

    dirs = [
        ".claude/workflows",
        ".claude/workflows/_archive",
        ".claude/artifacts/screenshots",
        "docs/specs",
        "docs/artifacts",
        "docs/context",
    ]
    print("Creating directory structure...")
    for d in dirs:
        (project_path / d).mkdir(parents=True, exist_ok=True)
        print(f"  Created: {d}/")

    print("\nGenerating configuration...")
    generate_settings_json_plugin_mode(project_path, modules)
    generate_config_yaml(project_path, modules)
    create_spec_template(project_path)
    create_workflows_dir(project_path)
    ensure_gitignore_entries(project_path)

    version_file = project_path / ".claude" / "framework_version.json"
    version_info = {
        # Bewusst None — siehe PLUGIN_MODE_VERSION_NOTE.
        "framework_version": None,
        "version_source": PLUGIN_MODE_VERSION_SOURCE,
        "note": PLUGIN_MODE_VERSION_NOTE,
        "installed": datetime.now().isoformat(),
        "installed_modules": modules,
        "plugin_mode": True,
    }
    with open(version_file, 'w') as f:
        json.dump(version_info, f, indent=2)
    print("  Created: .claude/framework_version.json")

    print("\nCreating CLAUDE.md...")
    create_claude_md(project_path)

    print("\n" + "=" * 50)
    print("Setup complete! (Plugin Mode)")
    print("=" * 50)
    print(f"""
Plugin mode: hooks run from ${{CLAUDE_PLUGIN_ROOT}}/core/hooks/
No hooks copied to .claude/hooks/ — they live in the plugin.

Workflow via skills (preferred):
  /80-workflow start <name>
  /80-workflow status

Or directly:
  python3 ${{CLAUDE_PLUGIN_ROOT}}/core/hooks/workflow.py start <name>
  python3 ${{CLAUDE_PLUGIN_ROOT}}/core/hooks/workflow.py status

Next steps:
1. Review openspec.yaml and customize for your project
2. Ensure the plugin is installed in Claude Code
""")


def generate_config_yaml(project_path: Path, modules: list):
    """Generate project-level config.yaml."""
    config_src = FRAMEWORK_ROOT / "config.yaml"
    config_dst = project_path / "openspec.yaml"

    if config_src.exists():
        shutil.copy(config_src, config_dst)

        # Update project path in config
        content = config_dst.read_text()
        content = content.replace(
            'base_path: "/path/to/project"',
            f'base_path: "{project_path}"'
        )
        content = content.replace(
            'name: "My Project"',
            f'name: "{project_path.name}"'
        )

        # Enable modules
        for module in modules:
            content = content.replace(
                f'{module.replace("-", "_")}:\n    enabled: false',
                f'{module.replace("-", "_")}:\n    enabled: true'
            )

        config_dst.write_text(content)
        print(f"  Generated: openspec.yaml")


def create_spec_template(project_path: Path):
    """Create the spec template file."""
    template_content = '''---
entity_id: entity_name
type: module
created: {date}
updated: {date}
status: draft
version: "1.0"
tags: []
---

# Entity Name

## Approval

- [ ] Approved

## Purpose

[1-2 sentences: What does this entity do? Why does it exist?]

## Source

- **File:** `path/to/file`
- **Identifier:** `class/function name`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| | | |

## Scope

- **Affected Files:** `path/to/file`
- **Estimated Changes:** ~N LoC

## Implementation Details

```
[Code or logic description]
```

## Expected Behavior

- **Input:** [description]
- **Output:** [description]
- **Side effects:** [if any]

## Known Limitations

- [Any limitations or edge cases]

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] [beobachtbares Ergebnis, an dem der PO „fertig“ erkennt — kein „Code gemerged“]
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given <Vorbedingung> / When <Aktion> / Then <beobachtbares Ergebnis>
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_entity.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** [ADR-NNNN oder "keine"]
- **Rationale:** [kurz: warum diese Entscheidung bzw. warum keine nötig ist]

## Changelog

- {date}: Initial spec created
'''.format(date=datetime.now().strftime("%Y-%m-%d"))

    template_path = project_path / "docs" / "specs" / "_template.md"
    template_path.write_text(template_content)
    print(f"  Created: docs/specs/_template.md")


def create_workflows_dir(project_path: Path):
    """Create .claude/workflows/ directory for v3 isolated workflow state."""
    wf_dir = project_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = wf_dir / "_archive"
    archive_dir.mkdir(exist_ok=True)
    print(f"  Created: .claude/workflows/ (v3 isolated state)")
    print(f"  Created: .claude/workflows/_archive/")


def create_claude_md(project_path: Path):
    """Create initial CLAUDE.md file."""
    content = f'''# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

Generated by OpenSpec Framework v{FRAMEWORK_VERSION} on {datetime.now().strftime("%Y-%m-%d")}

---

## How to Start (First Conversation)

**New feature or bug fix:**
```
Start a new workflow for [feature/bug name]:
python3 .claude/hooks/workflow.py start "[workflow-name]"
Then use /10-context to begin.
```

**Check current state:**
```
python3 .claude/hooks/workflow.py status
python3 .claude/hooks/workflow.py list
```

---

## The 8-Phase Workflow

| Phase | Command | Gate |
|-------|---------|------|
| 1 — Context | `/10-context` | — |
| 2 — Analysis | `/20-analyse` | — |
| 3 — Spec | `/30-write-spec` | Spec must have `## Acceptance Criteria` with `AC-N` entries |
| 4 — Approval | User: "approved" | **HUMAN GATE** — hooks detect keyword |
| 5 — TDD RED | `/40-tdd-red` | Real failing test artifacts required |
| 6 — Implement | `/50-implement` | Code edits blocked until RED artifacts exist + AC present |
| 6b — Adversary | Auto after `/50-implement` | VERIFIED verdict + a valid, stamped dialog artifact required to commit |
| 7 — Validate | `/60-validate` | AMBIGUOUS verdict blocks commit |
| 8 — Complete | `workflow.py write-log && workflow.py finish` | Execution log required |

**Hooks enforce every gate.** Skipping phases is blocked, not just discouraged.

---

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/10-context` | Phase 1: Collect relevant context |
| `/20-analyse` | Phase 2: Analyse requirements |
| `/30-write-spec` | Phase 3: Create specification |
| `/40-tdd-red` | Phase 5: Write failing tests |
| `/50-implement` | Phase 6: Implement (make tests green) |
| `/60-validate` | Phase 7: Validate |
| `/01-feature` | Plan a new feature |
| `/80-workflow` | Manage workflows |
| `/81-add-artifact` | Register test artifacts |

---

## Workflow State Management

```bash
# Start / switch
python3 .claude/hooks/workflow.py start "feature-login"
python3 .claude/hooks/workflow.py switch "bugfix-crash"

# Track progress
python3 .claude/hooks/workflow.py status       # phase, LoC delta, log status
python3 .claude/hooks/workflow.py list

# Complete a workflow (requires execution log)
python3 .claude/hooks/workflow.py write-log success
python3 .claude/hooks/workflow.py finish
```

---

## Enforcement Rules

- **Code edits** blocked unless in phase6+ with RED artifacts and `## Acceptance Criteria` in spec
- **LoC limit**: Max 250 lines changed per workflow (override: `workflow.py set-field loc_limit_override <N>`)
- **git commit** blocked unless adversary verdict is VERIFIED and a valid, stamped dialog artifact matches the current code
- **AMBIGUOUS** verdict blocks commit — requires: `workflow.py override-ambiguous "<reason>"`
- **Stop-lock**: Say "stop" to freeze all edits; "resume" to unfreeze

---

## Spec Format

All specs must contain:
```markdown
## Acceptance Criteria

- **AC-1:** Given <precondition> / When <action> / Then <observable outcome>
  - Test: (test file:function after TDD RED)

## Approval
- [ ] Approved
```

Template: `docs/specs/_template.md`

---

## GitHub Issues

All features and bugs are tracked as GitHub Issues:
- Feature: `gh issue create --title "feat: ..." --label "enhancement"`
- Bug: `gh issue create --title "bug: ..." --label "bug"`
- Link to workflow: `workflow.py set-field github_issue <N>`
'''

    claude_md_path = project_path / "CLAUDE.md"
    if not claude_md_path.exists():
        claude_md_path.write_text(content)
        print(f"  Created: CLAUDE.md")
    else:
        print(f"  Skipped: CLAUDE.md (already exists)")


def update_project(project_path: Path, modules: list, force: bool = False):
    """Update an existing project installation."""
    print(f"\nOpenSpec Framework Update")
    print(f"=========================")
    print(f"Framework version: {FRAMEWORK_VERSION}")
    print(f"Project: {project_path}")
    print()

    # Track changes
    updated = []
    skipped = []
    new_files = []

    # Update core hooks
    hooks_src = CORE_DIR / "hooks"
    hooks_dst = project_path / ".claude" / "hooks"

    if hooks_dst.exists():
        for hook_file in hooks_src.glob("*.py"):
            dst = hooks_dst / hook_file.name
            should_update, reason = should_update_file(hook_file, dst, force)

            if should_update:
                shutil.copy(hook_file, dst)
                if reason == "new file":
                    new_files.append(f"hook: {hook_file.name}")
                else:
                    updated.append(f"hook: {hook_file.name}")
            else:
                skipped.append(f"hook: {hook_file.name}")

    # CI-Gate mitziehen (Script immer, Action-Vorlage nur falls fehlend)
    install_ci_gate(project_path)

    # Update core commands
    commands_src = CORE_DIR / "commands"
    commands_dst = project_path / ".claude" / "commands"

    if commands_dst.exists():
        for cmd_file in commands_src.glob("*.md"):
            dst = commands_dst / cmd_file.name
            should_update, reason = should_update_command(cmd_file, dst, force)

            if should_update:
                copy_command_file(cmd_file, dst)
                if reason == "new file":
                    new_files.append(f"command: {cmd_file.name}")
                else:
                    updated.append(f"command: {cmd_file.name}")
            else:
                skipped.append(f"command: {cmd_file.name}")

    # Update core agents
    agents_src = CORE_DIR / "agents"
    agents_dst = project_path / ".claude" / "agents"

    if agents_dst.exists():
        for agent_file in agents_src.glob("*.md"):
            dst = agents_dst / agent_file.name
            should_update, reason = should_update_file(agent_file, dst, force)

            if should_update:
                shutil.copy(agent_file, dst)
                if reason == "new file":
                    new_files.append(f"agent: {agent_file.name}")
                else:
                    updated.append(f"agent: {agent_file.name}")
            else:
                skipped.append(f"agent: {agent_file.name}")

    # Update core tools (v2.0)
    tools_src = CORE_DIR / "tools"
    tools_dst = project_path / ".claude" / "tools"

    if tools_src.exists():
        tools_dst.mkdir(parents=True, exist_ok=True)
        for tool_file in tools_src.glob("*.py"):
            dst = tools_dst / tool_file.name
            should_update, reason = should_update_file(tool_file, dst, force)

            if should_update:
                shutil.copy(tool_file, dst)
                if reason == "new file":
                    new_files.append(f"tool: {tool_file.name}")
                else:
                    updated.append(f"tool: {tool_file.name}")
            else:
                skipped.append(f"tool: {tool_file.name}")

    # Update modules
    for module in modules:
        module_dir = MODULES_DIR / module
        if module_dir.exists():
            print(f"\nUpdating module: {module}...")
            # Similar logic for module files...
            install_module(project_path, module)

    # Laufzeit-Eintraege nachziehen — auch in Projekten, die vor #78
    # installiert wurden.
    ensure_gitignore_entries(project_path)

    # Update version tracking
    #
    # Der vorherige Stand schrieb die Datei blind neu und verlor dabei
    # `plugin_mode`, `version_source` und `note` — ein Plugin-Modus-Projekt
    # galt nach jedem `--update` als Copy-Modus-Projekt, und die in 3.26.0
    # entfernte Falschauskunft ("framework_version" im Plugin-Modus) kehrte
    # zurueck. Ein Update ist kein Moduswechsel (Issue #159).
    version_file = project_path / ".claude" / "framework_version.json"
    existing = {}
    if version_file.exists():
        try:
            existing = json.loads(version_file.read_text())
        except (json.JSONDecodeError, OSError):
            # Unlesbare Datei wird neu aufgebaut — aber nicht stillschweigend.
            print("  WARNING: .claude/framework_version.json unlesbar, wird neu geschrieben")
            existing = {}

    if existing.get("plugin_mode"):
        version_info = {
            # Bewusst None — siehe PLUGIN_MODE_VERSION_NOTE.
            "framework_version": None,
            "version_source": PLUGIN_MODE_VERSION_SOURCE,
            "note": PLUGIN_MODE_VERSION_NOTE,
            "installed": existing.get("installed"),
            "last_updated": datetime.now().isoformat(),
            "installed_modules": modules,
            "plugin_mode": True,
        }
    else:
        version_info = {
            "framework_version": FRAMEWORK_VERSION,
            "last_updated": datetime.now().isoformat(),
            "installed_modules": modules,
        }
        if hooks_dst.exists():
            for entry in merge_missing_copy_mode_hooks(project_path, modules):
                new_files.append(f"hook registration: {entry}")
    with open(version_file, 'w') as f:
        json.dump(version_info, f, indent=2)

    # Print summary
    print("\n" + "=" * 50)
    print("Update Summary")
    print("=" * 50)

    if new_files:
        print(f"\nNew files ({len(new_files)}):")
        for f in new_files:
            print(f"  + {f}")

    if updated:
        print(f"\nUpdated ({len(updated)}):")
        for f in updated:
            print(f"  ~ {f}")

    if skipped and not force:
        print(f"\nUnchanged ({len(skipped)}): Use --force to overwrite all")

    print(f"\nFramework updated to version {FRAMEWORK_VERSION}")


def generate_command_aliases(project_path: Path) -> None:
    """Generate short command aliases in .claude/commands/<name>.md.

    For every skill under FRAMEWORK_ROOT/skills/ that has a SKILL.md, write a
    command file so that `/name` behaves like `/agent-os-openspec:name`. Each
    generated file carries a marker on the first line after its frontmatter
    (#251; keeps the frontmatter parseable) so migrate_to_plugin.py does not
    mistake it for a legacy duplicate.

    Two alias strategies, depending on the target skill's
    `disable-model-invocation` frontmatter:
      - false (model may self-invoke) → thin text redirect
        (`/agent-os-openspec:name $ARGUMENTS`). Claude resolves this via the
        Skill tool, which is allowed for these skills.
      - true (only direct user `/name` typing allowed, e.g. Implement/
        Validate/Deploy phases) → a text redirect would still make Claude
        resolve it via the Skill tool, which the harness then blocks with
        "cannot be used with Skill tool due to disable-model-invocation" —
        breaking the alias entirely. So instead the full SKILL.md body is
        embedded verbatim: the harness then executes the alias command
        directly as a real user-typed command, no Skill-tool call involved.

    Overwrite rules per target file:
      - missing            → create
      - marker (old or new position) → update (overwrite)
      - no marker          → skip (assumed project-specific custom command)

    KNOWN ISSUE (#87): Claude Code resolves same-named commands from
    `~/.claude/commands/` (user scope) and `<project>/.claude/commands/`
    (project scope) with **user scope winning**, contrary to the documented
    project > user precedence. Running this function against the home
    directory therefore silently shadows any project's own unmarked
    `.claude/commands/<name>.md` for every project on the machine — verified
    live for `70-deploy` (see #87). This is a Claude Code harness behaviour,
    not something this function can correct at runtime; see the warning
    printed below and `docs/specs/short-command-aliases.md` for mitigation.
    """
    skills_dir = FRAMEWORK_ROOT / "skills"
    commands_dir = project_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    names = skill_names(skills_dir)

    created = 0
    updated = 0
    skipped: list[str] = []

    for name in names:
        target = commands_dir / f"{name}.md"
        skill_text = (skills_dir / name / "SKILL.md").read_text()
        content = alias_content(name, skill_text)

        if not target.exists():
            target.write_text(content)
            created += 1
            continue

        existing = _read_or_none(target)  # unlesbar (Rechte, kein UTF-8): nie ueberschreiben (#353)
        if existing is None:
            skipped.append(f"{name}.md (unlesbar)")
        elif is_alias_file(existing):
            target.write_text(content)
            updated += 1
        else:
            skipped.append(f"{name}.md")

    print(
        f"Command aliases: {created} created, {updated} updated, "
        f"{len(skipped)} skipped."
    )
    for name in skipped:
        print(f"  SKIPPED (custom command exists or unreadable): {name}")

    if project_path.resolve() == Path.home().resolve():
        full_content_names = [
            name for name in names
            if embeds_full_skill((skills_dir / name / "SKILL.md").read_text())
        ]
        if full_content_names:
            print(
                "\nWARNING: Global run detected (~/.claude/commands/). Claude "
                "Code currently resolves same-named commands with user scope "
                "winning over project scope (confirmed bug, project scope is "
                "documented to win — see issue #87). The files just written "
                f"for {', '.join(full_content_names)} will therefore SHADOW "
                "any project's own .claude/commands/<name>.md of the same "
                "name on this machine, even projects with a real, unmarked "
                "custom command for that name. Check every project that "
                "defines its own version of these commands before relying "
                "on '/<name>' there — prefer running --command-aliases "
                "per-project instead of globally if any project customizes "
                "these names."
            )


def refresh_command_aliases(scope_path: Path) -> None:
    """Erneuert veraltete Framework-Aliase in <scope>/.claude/commands/.

    Anders als generate_command_aliases legt dieser Modus NIE eine Datei an:
    nur bereits vorhandene, markierte und veraltete Kopien werden ueber-
    schrieben. Damit kann er nichts ueberschatten (#87) und ist auch fuer
    `~` sicher.
    """
    sys.path.insert(0, str(FRAMEWORK_ROOT / "core" / "hooks"))
    from alias_sync import alias_content, find_removed_aliases, find_stale_aliases

    skills_dir = FRAMEWORK_ROOT / "skills"
    commands_dir = scope_path / ".claude" / "commands"
    stale = find_stale_aliases(
        skills_dir, commands_dir, loaded_version=FRAMEWORK_VERSION
    )
    for name in stale:
        skill_text = (skills_dir / name / "SKILL.md").read_text()
        (commands_dir / f"{name}.md").write_text(alias_content(name, skill_text))
        print(f"  Refreshed: {name}.md")
    # Aliase entfernter Befehle (z.B. 00-bug, #333): nur markierte Dateien.
    removed = find_removed_aliases(commands_dir)
    for path in removed:
        path.unlink()
        print(f"  Removed: {path.name}")
    print(
        f"Command aliases: {len(stale)} refreshed, {len(removed)} removed, "
        "none created."
    )


def remove_command_aliases(scope_path: Path) -> None:
    """Loescht markierte Framework-Aliase in <scope>/.claude/commands/ (#251).

    Nur Dateien mit Alias-Marker werden geloescht; projekteigene (unmarkierte)
    Befehle bleiben stehen und werden als `Kept:` gemeldet. Legt nie etwas an.
    """
    sys.path.insert(0, str(FRAMEWORK_ROOT / "core" / "hooks"))
    from alias_sync import find_aliases

    commands_dir = scope_path / ".claude" / "commands"
    aliases = find_aliases(commands_dir)
    for path in aliases:
        path.unlink()
        print(f"  Removed: {path.name}")
    kept = sorted(
        p for p in commands_dir.glob("*.md") if p.is_file()
    ) if commands_dir.is_dir() else []
    for path in kept:
        print(f"  Kept: {path.name}")
    print(f"Command aliases: {len(aliases)} removed, {len(kept)} kept.")


def main():
    parser = argparse.ArgumentParser(
        description="Install or update OpenSpec Framework for a project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fresh installation (legacy mode — hooks copied to .claude/hooks/)
  python3 setup.py /path/to/project
  python3 setup.py /path/to/project --module home-assistant

  # Plugin mode (no file copying — uses ${CLAUDE_PLUGIN_ROOT} references)
  python3 setup.py /path/to/project --plugin-mode
  python3 setup.py /path/to/project --plugin-mode --module ios-swiftui

  # Update existing installation
  python3 setup.py /path/to/project --update
  python3 setup.py /path/to/project --update --force

  # Generate short command aliases (/name → /agent-os-openspec:name)
  python3 setup.py /path/to/project --command-aliases   # recommended default: per-project
  python3 setup.py ~ --command-aliases          # global — see WARNING below if any
                                                 # project has its own custom version of
                                                 # 50-implement/60-validate/70-deploy/
                                                 # 80-workflow/81-add-artifact/99-reset
                                                 # (issue #87: global shadows project
                                                 # commands due to a Claude Code
                                                 # scope-precedence bug)

Available modules:
  ios-swiftui     - iOS/SwiftUI standards, agents, and workflows
  home-assistant  - Home Assistant specific hooks and agents
  generic         - Generic optional hooks (bug tracking, etc.)
"""
    )

    parser.add_argument(
        "project_path",
        help="Path to the project to install framework into"
    )

    parser.add_argument(
        "--module", "-m",
        action="append",
        dest="modules",
        default=[],
        help="Install specific module (can be used multiple times)"
    )

    parser.add_argument(
        "--update", "-u",
        action="store_true",
        help="Update existing installation instead of fresh install"
    )

    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force overwrite all files during update"
    )

    parser.add_argument(
        "--skip-hooks",
        action="store_true",
        help="Skip generating settings.json hooks configuration"
    )

    parser.add_argument(
        "--plugin-mode",
        action="store_true",
        help=(
            "Install in plugin mode: no hooks copied, settings.json references "
            "${CLAUDE_PLUGIN_ROOT}/core/hooks/ instead of local .claude/hooks/"
        )
    )

    parser.add_argument(
        "--command-aliases",
        action="store_true",
        help=(
            "Generate short command aliases in .claude/commands/<name>.md that "
            "redirect to /agent-os-openspec:<name> (opt-in, no install/update)"
        )
    )

    parser.add_argument(
        "--refresh-aliases",
        action="store_true",
        help=(
            "Refresh outdated command aliases that already exist in "
            ".claude/commands/ (never creates files; safe for ~ as well)"
        )
    )

    parser.add_argument(
        "--remove-aliases",
        action="store_true",
        help=(
            "Remove marked command aliases from .claude/commands/ (never "
            "creates files; unmarked project commands are kept)"
        )
    )

    parser.add_argument(
        "--global",
        action="store_true",
        dest="global_scope",
        help="With --remove-aliases: act on ~/.claude/commands/ instead of the project"
    )

    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"OpenSpec Framework {FRAMEWORK_VERSION}"
    )

    args = parser.parse_args()

    project_path = Path(args.project_path).resolve()

    if not project_path.exists():
        print(f"ERROR: Project path does not exist: {project_path}")
        sys.exit(1)

    if args.global_scope and not args.remove_aliases:
        print("WARNING: --global wirkt nur zusammen mit --remove-aliases "
              "und wird ignoriert.", file=sys.stderr)

    # Command aliases mode
    if args.remove_aliases:
        scope = Path.home() if args.global_scope else project_path
        remove_command_aliases(scope)
        return

    if args.refresh_aliases:
        refresh_command_aliases(project_path)
        return

    if args.command_aliases:
        generate_command_aliases(project_path)
        return

    # Update mode
    if args.update:
        update_project(project_path, args.modules, args.force)
        return

    # Plugin mode
    if args.plugin_mode:
        install_plugin_mode(project_path, args.modules)
        return

    # Fresh installation
    print(f"\nOpenSpec Framework Setup")
    print(f"========================")
    print(f"Framework version: {FRAMEWORK_VERSION}")
    print(f"Project: {project_path}")
    print(f"Modules: {args.modules or ['core only']}")
    print()

    print("Creating directory structure...")
    create_directory_structure(project_path)

    # Also create artifacts directory for TDD
    (project_path / "docs" / "artifacts").mkdir(parents=True, exist_ok=True)
    (project_path / "docs" / "context").mkdir(parents=True, exist_ok=True)
    print("  Created: docs/artifacts/")
    print("  Created: docs/context/")

    print("\nCopying core components...")
    copy_core_components(project_path)
    install_ci_gate(project_path)

    for module in args.modules:
        print(f"\nInstalling module: {module}...")
        install_module(project_path, module)

    print("\nGenerating configuration...")
    generate_config_yaml(project_path, args.modules)
    create_spec_template(project_path)
    create_workflows_dir(project_path)
    ensure_gitignore_entries(project_path)

    # Save version info
    version_file = project_path / ".claude" / "framework_version.json"
    version_info = {
        "framework_version": FRAMEWORK_VERSION,
        "installed": datetime.now().isoformat(),
        "installed_modules": args.modules,
    }
    with open(version_file, 'w') as f:
        json.dump(version_info, f, indent=2)
    print("  Created: .claude/framework_version.json")

    if not args.skip_hooks:
        generate_settings_json(project_path, args.modules)

    print("\nCreating CLAUDE.md...")
    create_claude_md(project_path)

    print("\n" + "=" * 50)
    print("Setup complete!")
    print("=" * 50)
    print(f"""
Framework version: {FRAMEWORK_VERSION}

Workflow v3 (consolidated hooks):
  /10-context   -> Gather relevant context (Phase 1)
  /20-analyse   -> Analyse requirements (Phase 2)
  /30-write-spec -> Create specification (Phase 3)
  "approved" -> User approval (Phase 4)
  /40-tdd-red   -> Write failing tests (Phase 5)
  /50-implement -> Make tests pass (Phase 6)
  /60-validate  -> Validation (Phase 7)

Hook architecture: 4 consolidated hooks (edit_gate, bash_gate, post_bash, phase_listener)
State: Isolated per-workflow JSON in .claude/workflows/

Workflow CLI:
  python3 .claude/hooks/workflow.py start <name>
  python3 .claude/hooks/workflow.py switch <name>
  python3 .claude/hooks/workflow.py status
  python3 .claude/hooks/workflow.py list

Migration from v2:
  python3 .claude/hooks/migrate_state.py          # Dry run
  python3 .claude/hooks/migrate_state.py --apply  # Migrate

Next steps:
1. Review openspec.yaml and customize for your project
2. Update protected_paths to match your project structure
3. Add specs to docs/specs/ as you develop
""")


if __name__ == "__main__":
    main()
