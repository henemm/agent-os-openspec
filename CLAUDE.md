# Agent OS + OpenSpec Framework

> **Meta-Projekt**: Dies ist das zentrale Framework-Repository, das abstraktes Projekt- und Workflow-Wissen konsolidiert. Alle Projekte können Improvements hierher zurückführen und von Verbesserungen aus anderen Projekten profitieren.

**Version**: 2.0.0

## Projektzweck

Dieses Repository vereint zwei Ansätze:

1. **Agent OS**: Hook-basierte Workflow-Enforcement für Claude Code
2. **OpenSpec (SpecDriven)**: Spec-First Development - kein Code ohne Spezifikation

Das Framework erzwingt technisch (nicht nur durch Dokumentation), dass Claude strukturiert arbeitet:
- Erst Kontext sammeln, dann analysieren, dann spezifizieren
- TDD: Erst Tests schreiben (RED), dann implementieren (GREEN)
- Keine Änderungen an geschützten Dateien ohne freigegebene Spec
- ECHTE Test-Artefakte (Screenshots, Logs, etc.) - keine Platzhalter

## Architektur

```
agent-os-openspec/
├── core/                    # Basis-System (immer installiert)
│   ├── hooks/               # Python-Hooks für Workflow-Enforcement
│   │   ├── workflow_gate.py         # Phasen-Gate für geschützte Dateien
│   │   ├── workflow_state_multi.py  # Multi-Workflow State Manager (v2.0)
│   │   ├── tdd_enforcement.py       # TDD mit echten Artefakten
│   │   ├── spec_enforcement.py      # Spec-First Enforcement
│   │   └── ...
│   ├── agents/              # Agent-Definitionen (Markdown)
│   └── commands/            # Slash-Commands
│       ├── context.md       # Phase 1: Kontext sammeln
│       ├── analyse.md       # Phase 2: Analysieren
│       ├── write-spec.md    # Phase 3: Spec schreiben
│       ├── tdd-red.md       # Phase 5: Failing Tests
│       ├── implement.md     # Phase 6: Implementieren
│       ├── validate.md      # Phase 7: Validieren
│       ├── workflow.md      # Workflow-Management
│       └── add-artifact.md  # Test-Artefakte registrieren
├── modules/                 # Domain-spezifische Erweiterungen
│   ├── ios-swiftui/         # iOS/SwiftUI Standards, TDD, Localization
│   └── home-assistant/      # HA Config-Validation, Dashboard-QA
├── templates/               # Spec-Templates
├── setup.py                 # Installations- und Update-Tool
├── config.yaml              # Zentrale Konfiguration
└── CHANGELOG.md             # Versionshistorie
```

## Der 8-Phasen-Workflow (v2.0)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         OPENSPEC WORKFLOW v2.0                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  phase0_idle                                                            │
│       │                                                                 │
│       ▼                                                                 │
│  phase1_context ─── /context ───► Kontext sammeln                       │
│       │                                                                 │
│       ▼                                                                 │
│  phase2_analyse ─── /analyse ───► Anforderungen analysieren             │
│       │                                                                 │
│       ▼                                                                 │
│  phase3_spec ────── /write-spec ► Spezifikation schreiben               │
│       │                                                                 │
│       ▼                                                                 │
│  phase4_approved ── "approved" ─► User-Freigabe (GATE)                  │
│       │                                                                 │
│       ▼                                                                 │
│  phase5_tdd_red ─── /tdd-red ───► Tests schreiben, MÜSSEN FEHLSCHLAGEN  │
│       │                           + ECHTE Artefakte!                    │
│       ▼                                                                 │
│  phase6_implement ─ /implement ─► Code schreiben, Tests GRÜN machen     │
│       │                                                                 │
│       ▼                                                                 │
│  phase7_validate ── /validate ──► Manuelle Tests, Validierung           │
│       │                                                                 │
│       ▼                                                                 │
│  phase8_complete                  ► Fertig, bereit für Commit           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Parallele Workflows

Mehrere Features können gleichzeitig bearbeitet werden:

```bash
# Workflow starten
python3 .claude/hooks/workflow_state_multi.py start "feature-login"
python3 .claude/hooks/workflow_state_multi.py start "bugfix-crash"

# Zwischen Workflows wechseln
python3 .claude/hooks/workflow_state_multi.py switch "bugfix-crash"

# Alle Workflows anzeigen
python3 .claude/hooks/workflow_state_multi.py list

# Status des aktiven Workflows
python3 .claude/hooks/workflow_state_multi.py status
```

## TDD mit ECHTEN Artefakten

Der `tdd_enforcement.py` Hook erzwingt echte Test-Artefakte:

**Akzeptiert:**
- Screenshots (PNG, JPG) mit echtem Inhalt (>1KB)
- Test-Output-Logs mit echten Fehlern
- API-Responses als JSON/XML-Dateien
- E-Mails als .eml oder .txt

**Blockiert:**
- Platzhalter-Text wie "[Screenshot hier]"
- Leere Dateien
- Artefakte ohne Beschreibung
- Artefakte älter als 24 Stunden

```bash
# Artefakt registrieren
python3 -c "
import sys; sys.path.insert(0, '.claude/hooks')
from workflow_state_multi import add_test_artifact, load_state
state = load_state()
add_test_artifact(state['active_workflow'], {
    'type': 'screenshot',
    'path': 'docs/artifacts/feature-x/test-failed.png',
    'description': 'Test failed: Login button not found - assertion error',
    'phase': 'phase5_tdd_red'
})
"
```

## Konventionen für dieses Repository

### Beim Bearbeiten des Frameworks

1. **Keine Breaking Changes** ohne Migration-Pfad
2. **CHANGELOG.md** bei jeder Änderung aktualisieren
3. **Versionsnummer** in setup.py bei Releases erhöhen
4. **Tests** für Hooks: Manuell in einem Test-Projekt validieren

### Verzeichnis-Konventionen

| Pfad | Zweck |
|------|-------|
| `core/hooks/*.py` | Python-Scripts mit Exit-Code 2 zum Blockieren |
| `core/agents/*.md` | Agent-Definitionen mit YAML-Frontmatter |
| `core/commands/*.md` | Slash-Command-Definitionen |
| `modules/<name>/` | Domain-Module mit eigener config.yaml |
| `templates/` | Wiederverwendbare Spec-Templates |

### Hook-Entwicklung

```python
# Exit-Codes:
# 0 = Operation erlaubt
# 2 = Operation blockiert (Nachricht wird Claude angezeigt)

import sys
if violation_detected:
    print("BLOCKED: Reason for blocking", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
```

## Improvement-Flow zwischen Projekten

### Improvements zu diesem Meta-Projekt beitragen

Wenn in einem Projekt eine Verbesserung am Framework entsteht:

1. **Extrahieren**: Projekt-spezifische Details entfernen
2. **Generalisieren**: Auf andere Domains anwendbar machen
3. **Dokumentieren**: In CHANGELOG.md unter [Unreleased] eintragen
4. **PR erstellen**: Mit Referenz zum Ursprungsprojekt

### Improvements aus diesem Projekt beziehen

```bash
# Framework in bestehendes Projekt aktualisieren
python3 /path/to/agent-os-openspec/setup.py /path/to/project --update

# Force-Update (alle Dateien überschreiben)
python3 /path/to/agent-os-openspec/setup.py /path/to/project --update --force

# Neues Modul hinzufügen
python3 /path/to/agent-os-openspec/setup.py /path/to/project --module ios-swiftui

# Version prüfen
python3 /path/to/agent-os-openspec/setup.py --version
```

## Wichtige Dateien

| Datei | Beschreibung |
|-------|--------------|
| `setup.py` | Installations- und Update-Tool (v2.0) |
| `config.yaml` | Template für Projektkonfiguration |
| `CHANGELOG.md` | Versionshistorie |
| `core/hooks/workflow_state_multi.py` | Multi-Workflow State Manager |
| `core/hooks/tdd_enforcement.py` | TDD mit echten Artefakten |
| `core/hooks/workflow_gate.py` | Phasen-Gate |
| `core/hooks/spec_enforcement.py` | Spec-First Enforcement |

## Slash-Commands Übersicht

| Command | Phase | Beschreibung |
|---------|-------|--------------|
| `/context` | 1 | Relevanten Kontext sammeln |
| `/analyse` | 2 | Anforderungen analysieren |
| `/write-spec` | 3 | Spezifikation erstellen |
| `/tdd-red` | 5 | Failing Tests schreiben |
| `/implement` | 6 | Implementieren (Tests grün) |
| `/validate` | 7 | Manuelle Validierung |
| `/workflow` | - | Workflows verwalten |
| `/add-artifact` | - | Test-Artefakte registrieren |

## Arbeitsanweisungen für Claude

Wenn du an diesem Framework arbeitest:

1. **Verstehe den Kontext**: Dies ist ein Meta-Projekt, Änderungen betreffen viele abhängige Projekte
2. **Teste Hooks**: Validiere Python-Hooks auf Syntax-Fehler vor Commit
3. **CHANGELOG**: Jede Änderung unter [Unreleased] dokumentieren
4. **Versionierung**: Semantische Versionierung (MAJOR.MINOR.PATCH)

Bei Feature-Requests:
- Prüfe erst, ob das Feature in core/ oder als Modul gehört
- Core = universell für alle Projekte
- Module = domain-spezifisch
