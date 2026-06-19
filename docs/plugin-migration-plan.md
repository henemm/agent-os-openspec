# Plugin-Migration Plan: agent-os-openspec v3.2

## Kontext

Umbau des agent-os-openspec Frameworks in ein offizielles Claude Code Plugin.
Branch: `feat/plugin-v3.2`

## Getroffene Entscheidungen

| # | Entscheidung | Ergebnis |
|---|---|---|
| 1 | Timing | Jetzt — v3.2 |
| 2 | Scope | Project-Scope (im Repo deklariert) |
| 3 | Claude-Autonomie | Context/Analyse/Spec: auto — TDD/Implement/Validate: nur User |
| 4 | State-Speicherort | Im Repo (`.claude/workflows/`) — NICHT in `${CLAUDE_PLUGIN_DATA}` |
| 5 | Modul-System | Ein Plugin, Module via `OPENSPEC_ENABLED_MODULES` Env-Var |
| 6 | Distribution | Privater GitHub-Marketplace (henemm/) → Community optional später |
| 7 | Migration | Harte Migration via `migrate_to_plugin.py` Script |

## Architektur-Prinzip

Das Plugin ist NICHT ein Ersatz für alles — Schicht-Architektur:

```
┌──────────────────────────────────┐
│  Projekt-spezifische Hooks       │  ← bleibt lokal in .claude/hooks/
│  (Mail-Validatoren, E2E-Gates)   │
├──────────────────────────────────┤
│  Plugin: agent-os-openspec       │  ← generisch, installierbar
│  (workflow engine, core gates,   │
│   agents, slash commands)        │
└──────────────────────────────────┘
```

Claude Code Hooks sind additiv — Plugin-Hooks + Projekt-Hooks laufen beide.

## Ziel-Dateistruktur

```
agent-os-openspec/
├── .claude-plugin/
│   └── plugin.json              # Manifest
├── hooks/
│   └── hooks.json               # Hook-Deklarationen
├── skills/                      # Umbenannt von core/commands/
│   ├── 10-context/SKILL.md
│   ├── 20-analyse/SKILL.md
│   ├── 30-write-spec/SKILL.md
│   ├── 40-tdd-red/SKILL.md
│   ├── 50-implement/SKILL.md
│   ├── 60-validate/SKILL.md
│   ├── 70-deploy/SKILL.md
│   ├── 80-workflow/SKILL.md
│   ├── 81-add-artifact/SKILL.md
│   ├── 82-test/SKILL.md
│   ├── 83-user-story/SKILL.md
│   └── 99-reset/SKILL.md
├── agents/                      # Symlink oder Kopie von core/agents/
├── core/
│   └── hooks/                   # Python-Hook-Skripte (weitgehend unverändert)
├── modules/
│   ├── ios-swiftui/
│   │   └── hooks.json           # Modul-spezifische Hook-Deklarationen
│   └── home-assistant/
│       └── hooks.json
├── config.yaml
├── setup.py                     # Erweitert: --plugin-mode Flag
└── migrate_to_plugin.py         # NEU: Migrations-Script für bestehende Projekte
```

## hooks.json Format

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/core/hooks/edit_gate.py", "timeout": 10}]
      },
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/core/hooks/bash_gate.py", "timeout": 300}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/core/hooks/post_bash.py", "timeout": 30}]
      }
    ],
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/core/hooks/phase_listener.py", "timeout": 5}]},
      {"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/core/hooks/session_singleton_guard.py", "timeout": 5}]}
    ],
    "Stop": [
      {"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/core/hooks/session_singleton_guard.py --cleanup", "timeout": 5}]}
    ]
  }
}
```

## Skills Frontmatter

```yaml
# Frühe Phasen — Claude darf selbst triggern:
---
description: "Gather context for a new feature or bug fix"
disable-model-invocation: false
---

# Ab TDD-Red — nur User:
---
description: "Write failing tests (RED phase)"
disable-model-invocation: true
---
```

| Skill | disable-model-invocation |
|---|---|
| 10-context | false |
| 20-analyse | false |
| 30-write-spec | false |
| 40-tdd-red | **true** |
| 50-implement | **true** |
| 60-validate | **true** |
| 70-deploy | **true** |
| 80-workflow | **true** |
| 81-add-artifact | **true** |
| 82-test | false |
| 83-user-story | false |
| 99-reset | **true** |

## Implementierungsphasen

### Phase 0 — Vorbereitung (Tag 1)
- Git-Branch `feat/plugin-v3.2` anlegen
- `setup.py` darf in dieser Migration keine Funktionalität verlieren (Zero-Breaking-Change-Garantie)

### Phase 1 — Plugin-Gerüst (Tag 1–2)
Zwei neue Dateien, kein Code geändert:

**`.claude-plugin/plugin.json`:**
```json
{
  "name": "agent-os-openspec",
  "version": "3.2.0",
  "description": "8-Phase Workflow Engine with TDD Enforcement for Claude Code",
  "author": "henemm",
  "modules": [
    {"id": "ios-swiftui", "label": "iOS/SwiftUI", "env_key": "OPENSPEC_ENABLED_MODULES"},
    {"id": "home-assistant", "label": "Home Assistant", "env_key": "OPENSPEC_ENABLED_MODULES"}
  ]
}
```

**`hooks/hooks.json`:** Siehe Format oben.

### Phase 2 — Kritischer Kern: Plugin-Root vs. Projekt-Root (Tag 2–3)

Das ist die einzige wirklich heikle Änderung. Zwei Roots müssen klar getrennt werden:
- **Plugin-Root**: wo die Hook-Skripte liegen → via `CLAUDE_PLUGIN_ROOT`
- **Projekt-Root**: wo `.claude/workflows/` liegt → via `CLAUDE_PROJECT_DIR` / `.git`

**2.1 — `hook_utils.py`: `find_plugin_root()` hinzufügen**

```python
def find_plugin_root() -> Path:
    """Plugin-Root: wo die Hook-Skripte liegen."""
    # 1. CLAUDE_PLUGIN_ROOT Env-Var (gesetzt von Claude Code)
    env = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if env:
        return Path(env)
    # 2. Fallback: hook_utils.py liegt in plugin_root/core/hooks/
    candidate = Path(__file__).parent.parent.parent
    if (candidate / ".claude-plugin" / "plugin.json").exists():
        return candidate
    return Path(__file__).parent.parent.parent
```

`find_project_root()` bleibt unverändert.

**2.2 — `config_loader.py`: `CLAUDE_PROJECT_DIR` als erste Priorität**

Die bestehende `find_project_root()` in config_loader.py muss `CLAUDE_PROJECT_DIR` als allererste Option prüfen (vor der YAML-Suche), damit sie nicht versehentlich den Plugin-Root zurückgibt wenn dort auch eine `config.yaml` liegt.

**2.3 — `qa_gate.py`: Hardcoded Pfad reparieren**

Aktuell:
```python
workflow_py = _root / ".claude" / "hooks" / "workflow.py"
```
Muss werden:
```python
from hook_utils import find_plugin_root
workflow_py = find_plugin_root() / "core" / "hooks" / "workflow.py"
```
**Dies ist die kritischste einzelne Codeänderung.**

**2.4 — `override_token.py`: Lazy Evaluation**

```python
# VORHER (läuft beim Import — falsch):
TOKEN_FILE = find_project_root() / ".claude" / "user_override_token.json"

# NACHHER (lazy — korrekt):
def _get_token_file() -> Path:
    return find_project_root() / ".claude" / "user_override_token.json"
```

Alle Referenzen auf `TOKEN_FILE` durch `_get_token_file()` ersetzen.

### Phase 3 — Modul-System (Tag 3–4)

**3.1 — `hook_utils.py`: `is_module_enabled()` hinzufügen**

```python
def is_module_enabled(module_id: str) -> bool:
    enabled = os.environ.get("OPENSPEC_ENABLED_MODULES", "")
    return module_id in [m.strip() for m in enabled.split(",")]
```

**3.2 — Jeder Modul-Hook bekommt Early-Exit**

Ganz am Anfang jedes Hooks in `modules/*/hooks/`:
```python
import os, sys
if "ios-swiftui" not in os.environ.get("OPENSPEC_ENABLED_MODULES", "").split(","):
    sys.exit(0)
```

**3.3 — Modul-Hooks: `sys.path` reparieren**

`modules/ios-swiftui/hooks/ui_test_preflight.py` importiert `hook_utils` nicht (hat eigene lokale `find_project_root()`). Fix:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core" / "hooks"))
from hook_utils import setup_path, find_project_root, find_plugin_root
```

**3.4 — `modules/*/hooks.json` anlegen**

Jedes Modul bekommt eine eigene `hooks.json`. Falls Claude Code mehrere `hooks.json` nicht nativ zusammenführt → Modul-Hooks in die zentrale `hooks/hooks.json` aufnehmen, Modul-Check läuft dann im Hook selbst via `is_module_enabled()`.

### Phase 4 — Skills (Tag 4–5)

**4.1 — Verzeichnisstruktur:**
```
skills/
├── 10-context/SKILL.md
├── 20-analyse/SKILL.md
└── ...
```
Inhalt = bisherige `core/commands/*.md` + Frontmatter (siehe Tabelle oben).

**4.2 — 54 Pfad-Referenzen patchen**

Strategie: Setup-Block am Anfang jedes Skills:
```bash
WF="python3 ${CLAUDE_PLUGIN_ROOT}/core/hooks/workflow.py"
QA="python3 ${CLAUDE_PLUGIN_ROOT}/core/hooks/qa_gate.py"
AD="python3 ${CLAUDE_PLUGIN_ROOT}/core/hooks/adversary_dialog.py"
```
Dann im Body: `$WF start "feature-name"` statt langem Pfad.

Kommentar für Backward-Compat:
```
# Legacy (setup.py-Install): python3 .claude/hooks/workflow.py
# Plugin:                     $WF
```

### Phase 5 — setup.py erweitern (Tag 5)

**Neuer Flag `--plugin-mode`:**
```bash
python3 setup.py /path/to/project --plugin-mode
```
Im Plugin-Modus:
- Kopiert KEINE Hooks mehr nach `.claude/hooks/`
- Setzt `CLAUDE_PLUGIN_ROOT`-basierte Pfade in `.claude/settings.json`
- Erstellt weiterhin `.claude/workflows/`, `docs/specs/`

Legacy-Modus (ohne Flag): unverändert.

**Neues Script `migrate_to_plugin.py`:**
Identisches Pattern wie `migrate_state.py` — Dry-Run by default, `--apply` für echte Änderungen.

Aktionen:
1. Liest `.claude/settings.json` des Projekts
2. Sucht Hook-Pfade die auf `.claude/hooks/` zeigen
3. Ersetzt durch `${CLAUDE_PLUGIN_ROOT}/core/hooks/`-Pfade
4. Bietet an: `.claude/hooks/*.py` entfernen (da nun im Plugin)
5. Schreibt `OPENSPEC_ENABLED_MODULES` in `env`-Sektion

### Phase 6 — Agents (Tag 5–6)

Agent-Definitionen bleiben in `core/agents/`. Frontmatter validieren ob Claude Code Plugin-Agents zusätzliche Keys braucht. Falls ein Top-Level `agents/`-Verzeichnis erwartet wird → Symlink oder Kopie.

### Phase 7 — Lokales Testen (Tag 6–7)

**Vor allem anderen klären:** Wie setzt Claude Code `CLAUDE_PLUGIN_ROOT`? Zeigt es auf den Plugin-Root oder auf `.claude-plugin/`? Minimaler Test:

```bash
# Test-Hook der nur den Wert ausgibt:
cat > /tmp/test_hook.py << 'EOF'
import os, sys
print(f"CLAUDE_PLUGIN_ROOT={os.environ.get('CLAUDE_PLUGIN_ROOT', 'NOT SET')}", file=sys.stderr)
sys.exit(0)
EOF
```

**Hook-Tests:**
```bash
export CLAUDE_PLUGIN_ROOT=/home/hem/agent-os-openspec
export CLAUDE_PROJECT_DIR=/tmp/openspec-plugin-test
export OPENSPEC_ACTIVE_WORKFLOW=test-workflow

echo '{"tool_input": {"file_path": "/tmp/openspec-plugin-test/src/main.py"}}' \
  | python3 $CLAUDE_PLUGIN_ROOT/core/hooks/edit_gate.py
echo "Exit: $?"
```

**Szenarien pro Hook:**
1. Kein aktives Workflow → Block erwartet
2. Aktives Workflow in falscher Phase → Block erwartet
3. Aktives Workflow in korrekter Phase → Allow erwartet
4. `OPENSPEC_ENABLED_MODULES` nicht gesetzt → Modul-Hooks sind No-Op
5. `OPENSPEC_ENABLED_MODULES=ios-swiftui` → Modul-Hooks aktiv

**End-to-End:** Vollständigen 8-Phasen-Workflow in Testprojekt durchspielen.

### Phase 8 — Migration bestehender Projekte (Tag 7)

Workflow-State (`.claude/workflows/*.json`) bleibt unverändert — kein Datenmigrations-Schritt.

```bash
# Dry-Run
python3 /home/hem/agent-os-openspec/migrate_to_plugin.py /home/hem/gregor_zwanzig

# Anwenden
python3 /home/hem/agent-os-openspec/migrate_to_plugin.py /home/hem/gregor_zwanzig --apply
```

## Technische Fallstricke

| Fallstrick | Mitigation |
|---|---|
| `CLAUDE_PLUGIN_ROOT` zeigt auf `.claude-plugin/` statt Plugin-Root | **Vor Phase 2 klären** mit Minimal-Test-Hook |
| `qa_gate.py` ruft `workflow.py` via hardcodiertem Pfad auf | Kritischste Codeänderung, zuerst patchen (Phase 2.3) |
| Modul-Hooks haben kein `sys.path`-Setup für `hook_utils` | Jeder Modul-Hook braucht expliziten `sys.path.insert` (Phase 3.3) |
| 54 Pfad-Referenzen in Skills | `WF=`-Variable am Anfang jedes Skills (Phase 4.2) |
| `config_loader.find_project_root` findet Plugin-Root statt Projekt-Root | `CLAUDE_PROJECT_DIR` als erste Priorität (Phase 2.2) |
| `MultiEdit` als separates Tool | Matcher `"Edit|Write|MultiEdit"` in hooks.json |
| `override_token.py` wertet Pfad beim Import aus | Lazy `_get_token_file()` (Phase 2.4) |

## Geänderte Dateien (Übersicht)

| Datei | Art | Änderung |
|---|---|---|
| `.claude-plugin/plugin.json` | NEU | Plugin-Manifest |
| `hooks/hooks.json` | NEU | Hook-Deklarationen |
| `skills/*/SKILL.md` (12 Dateien) | NEU | Skills aus core/commands/ |
| `modules/*/hooks.json` (2 Dateien) | NEU | Modul-Hook-Deklarationen |
| `migrate_to_plugin.py` | NEU | Migrations-Script |
| `core/hooks/hook_utils.py` | GEÄNDERT | `find_plugin_root()` hinzufügen |
| `core/hooks/config_loader.py` | GEÄNDERT | `CLAUDE_PROJECT_DIR` Priorität |
| `core/hooks/override_token.py` | GEÄNDERT | Lazy `_get_token_file()` |
| `core/hooks/qa_gate.py` | GEÄNDERT | Pfad zu `workflow.py` via `find_plugin_root()` |
| `modules/ios-swiftui/hooks/ui_test_preflight.py` | GEÄNDERT | sys.path + hook_utils Import |
| `modules/home-assistant/hooks/*.py` | GEÄNDERT | sys.path + hook_utils Import |
| `setup.py` | GEÄNDERT | `--plugin-mode` Flag, Version aus `plugin.json` |

## Nicht geänderte Dateien

Alle anderen Dateien in `core/hooks/`, `core/agents/`, `config.yaml`, CHANGELOG.md, bestehende Workflow-States.
