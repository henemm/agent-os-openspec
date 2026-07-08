# Agent OS + OpenSpec Framework

> **Meta-Projekt**: Dies ist das zentrale Framework-Repository, das abstraktes Projekt- und Workflow-Wissen konsolidiert. Alle Projekte können Improvements hierher zurückführen und von Verbesserungen aus anderen Projekten profitieren.

**Version**: 3.4.15

## Projektzweck

Dieses Repository vereint zwei Ansätze:

1. **Agent OS**: Hook-basierte Workflow-Enforcement für Claude Code
2. **OpenSpec (SpecDriven)**: Spec-First Development - kein Code ohne Spezifikation

Das Framework erzwingt technisch (nicht nur durch Dokumentation), dass Claude strukturiert arbeitet:
- Erst Kontext sammeln, dann analysieren, dann spezifizieren
- TDD: Erst Tests schreiben (RED), dann implementieren (GREEN)
- Keine Änderungen an geschützten Dateien ohne freigegebene Spec
- ECHTE Test-Artefakte (Screenshots, Logs, etc.) - keine Platzhalter

## Orchestrator-Prinzip (v3.1)

**Der Hauptkontext schreibt niemals Code direkt.**

| Rolle | Werkzeuge | Aufgabe |
|-------|-----------|---------|
| **Orchestrator** (Hauptkontext) | Read, Grep, Bash, koordinieren | Planen, entscheiden, koordinieren |
| **Developer Agent** (`developer-agent`) | Edit, Write, Bash, Read | Code schreiben, Tests ausführen |
| **Adversary Agent** (`implementation-validator`) | Read, Grep, Bash | Implementierung angreifen, Beweise fordern |

Warum: Separation of concerns verhindert Conversation Drift (der Implementierer validiert sich nicht selbst), ermöglicht echte Kontext-Isolation beim Adversary, und macht den Developer Agent austauschbar (z.B. mit worktree-Isolation für parallele Workflows).

## Architektur

```
agent-os-openspec/
├── core/                    # Basis-System (immer installiert)
│   ├── hooks/               # v3: 4 konsolidierte Hooks + Utilities
│   │   ├── edit_gate.py             # PreToolUse Edit|Write (ersetzt 17 Hooks)
│   │   ├── bash_gate.py             # PreToolUse Bash (ersetzt 15 Hooks)
│   │   ├── post_bash.py             # PostToolUse Bash (Adversary Detection)
│   │   ├── phase_listener.py        # UserPromptSubmit (ersetzt 6 Hooks)
│   │   ├── workflow.py              # Workflow State CLI (isolierte JSON-Files)
│   │   ├── qa_gate.py              # QA-Gate: Test-Output validieren, Verdict setzen
│   │   ├── override_token.py       # Shared Override-Token Management (TTL, Multi-WF)
│   │   ├── migrate_state.py         # v2 → v3 State-Migration
│   │   ├── hook_utils.py            # Shared Bootstrap (Imports, Parsing, Exit)
│   │   └── config_loader.py         # Config-Loader (YAML + Local Overrides)
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
├── setup.py                 # Installations- und Update-Tool (v3.0)
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
│  phase1_context ─── /10-context ───► Kontext sammeln                       │
│       │                                                                 │
│       ▼                                                                 │
│  phase2_analyse ─── /20-analyse ───► Anforderungen analysieren             │
│       │                                                                 │
│       ▼                                                                 │
│  phase3_spec ────── /30-write-spec ► Spezifikation schreiben               │
│       │                                                                 │
│       ▼                                                                 │
│  phase4_approved ── "approved" ─► User-Freigabe (GATE)                  │
│       │                                                                 │
│       ▼                                                                 │
│  phase5_tdd_red ─── /40-tdd-red ───► Tests schreiben, MÜSSEN FEHLSCHLAGEN  │
│       │                           + ECHTE Artefakte!                    │
│       ▼                                                                 │
│  phase6_implement ─ /50-implement ─► Code schreiben, Tests GRÜN machen     │
│       │                                                                 │
│       ▼                                                                 │
│  phase7_validate ── /60-validate ──► Manuelle Tests, Validierung           │
│       │                                                                 │
│       ▼                                                                 │
│  phase8_complete                  ► Fertig, bereit für Commit           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Parallele Workflows (v3 — Isolierter State)

Jeder Workflow bekommt ein eigenes JSON-File in `.claude/workflows/`.
Aktiver Workflow wird **ausschliesslich** per `OPENSPEC_ACTIVE_WORKFLOW` Env-Var verwaltet.

**Priorität bei der Namens-Auflösung:** `workflow.py` liest den aktiven Workflow-Namen NICHT
direkt aus der Env-Var, sondern ueber `hook_utils.resolve_active_workflow()`. Priorität:
worktree-lokale `.claude/active_workflow`-Datei > `settings.local.json` > `OPENSPEC_ACTIVE_WORKFLOW`
Env-Var. Eine manuell inline gesetzte Env-Var (`OPENSPEC_ACTIVE_WORKFLOW=x python3 ...`) wird
also von einer vorhandenen `active_workflow`-Datei ueberstimmt, wenn diese auf einen anderen,
existierenden Workflow zeigt.

**SYMLINK VERBOTEN:** Der `.active`-Symlink-Fallback ist deaktiviert. `workflow.py` bricht mit FATAL-Error ab wenn `OPENSPEC_ACTIVE_WORKFLOW` nicht gesetzt ist. Nach `workflow.py start <name>` gibt das Tool die notwendige `export`-Zeile direkt aus.

```
.claude/workflows/
├── FEAT_001.json        ← State fuer FEAT_001
├── BUG_042.json         ← State fuer BUG_042
└── _archive/            ← Abgeschlossene Workflows
```

```bash
# Workflow starten — Ausgabe enthaelt die Pflicht-export-Zeile
python3 .claude/hooks/workflow.py start "feature-login"
export OPENSPEC_ACTIVE_WORKFLOW=feature-login   # ← SOFORT setzen

# Alle weiteren Befehle immer mit Env-Var-Prefix
OPENSPEC_ACTIVE_WORKFLOW=feature-login python3 .claude/hooks/workflow.py status
OPENSPEC_ACTIVE_WORKFLOW=feature-login python3 .claude/hooks/workflow.py phase phase6_implement
OPENSPEC_ACTIVE_WORKFLOW=feature-login python3 .claude/hooks/workflow.py complete
```

Beim Agent-Spawn den Workflow-Namen immer im Prompt uebergeben: `export OPENSPEC_ACTIVE_WORKFLOW=<name>` als erste Pflicht-Zeile im Agent-Brief.

### Migration von v2
```bash
python3 .claude/hooks/migrate_state.py          # Dry run
python3 .claude/hooks/migrate_state.py --apply   # Tatsaechlich migrieren
```

## TDD mit ECHTEN Artefakten

`edit_gate.py` prueft RED-Test-Artefakte bevor Code-Edits in phase6+ erlaubt werden.

**Artefakte registrieren (v3):**
```bash
python3 .claude/hooks/workflow.py add-artifact test_output "logs/test.log" "Tests failed: 3 errors" phase5_tdd_red
python3 .claude/hooks/workflow.py add-artifact screenshot "docs/artifacts/test-failed.png" "UI assertion error" phase5_tdd_red
python3 .claude/hooks/workflow.py mark-red "3 tests failed"
python3 .claude/hooks/workflow.py mark-ui-red "UI test assertion error"
```

**Akzeptiert:** Screenshots (>1KB), Test-Output-Logs, UI-Test-Output, API-Responses
**Blockiert:** Kein RED-Artefakt → kein Code-Edit in phase6+

## Modell-Zuweisungsstrategie

Jeder Agent und jede Phase verwendet gezielt das passende Modell:

| Model | Einsatz | Use Cases |
|-------|---------|-----------|
| **Haiku** | Schnell + guenstig fuer mechanische Aufgaben | Validierung (spec-validator), Kontext laden (Explore), Scope-Reviews, Test-Running (test-runner), Bug-Intake |
| **Sonnet** | Qualitaet + Kosten-Balance fuer kreative/analytische Arbeit | Specs schreiben (spec-writer), Bug-Analyse (bug-investigator), Feature-Planung (feature-planner), Docs-Updates (docs-updater), Analysis-Challenger, Implementation-Validator, Auto-Fixes |
| **Opus** | Hoechste Qualitaet fuer Kern-Arbeit | Implementation (Hauptkontext), User-Interaktion, Synthese, User Story Discovery (user-story-planner) |

**Dispatching-Muster:**
- **Parallel Explore (3x Haiku):** Schnelle Kontextsammlung in Analyse-Phasen
- **Write + Validate (Sonnet + Haiku):** Spec-Erstellung mit Qualitaetssicherung
- **Parallel Validation (4x Haiku):** Umfassende Validierung nach Implementation
- **Auto-Fix (Sonnet nach Haiku):** Haiku findet Probleme, Sonnet behebt sie

Siehe `templates/agent_orchestration.md` fuer das vollstaendige Referenz-Template.

## Adversary System (v3.1 — 2-Rollen-Modell)

Das Adversary System implementiert ein **QA-Tester / Fixer Cycle** mit strukturiertem Dialog:

### Rollen
- **Fixer** (Hauptkontext/Opus): Implementiert Code, liefert Beweise
- **QA-Tester** (`implementation-validator` Agent/Sonnet): Versucht aktiv die Implementierung zu brechen

### Ablauf
```
phase6_implement → User-Freigabe ("go") → phase6b_adversary → Dialog → Verdict
                                                                         ↓
                                                              VERIFIED → phase7
                                                              BROKEN → zurueck zu phase6
                                                              AMBIGUOUS → User-Review
```

### Adversary Dialog (`adversary_dialog.py`)
- Parst Spec `## Expected Behavior` und/oder `## Acceptance Criteria` (`- **AC-N:** ...`, section-gebunden, additiv gemergt bei Koexistenz) → Checkliste
- Mindestens 2 Dialog-Runden (Early-Agreement-Skepticism)
- Strukturierte Findings mit Severity (CRITICAL/HIGH/MEDIUM/LOW) und Category
- Tri-State Verdict: **VERIFIED** / **BROKEN** / **AMBIGUOUS**
- Circuit Breaker: Max 3 Iterationen, dann Eskalation an User

### Hooks
- `post_bash.py` erkennt Test-Framework-Output und setzt automatisch `adversary_verdict`
- `bash_gate.py` prueft bei `git commit` ob ein VERIFIED-Verdict vorliegt
- `qa_gate.py` validiert Test-Output + optional Adversary-Dialog-Checklist (`--checklist`)

### Fresh Eyes Inspector
`fresh-eyes-inspector.md` — Unabhaengiger UI-Beobachter der Screenshots OHNE Bug-Kontext bewertet. Ergaenzt den Adversary-Dialog um eine neutrale Perspektive.

## Stop Lock

Sofort-Pause fuer Claude:
- User sagt **"stop"/"stopp"/"halt"** → `phase_listener.py` setzt Stop-Lock
- Alle Edit/Write/Bash blockiert durch `edit_gate.py` / `bash_gate.py`
- User sagt **"resume"/"weiter"/"continue"** → Wieder freigegeben
- Keywords konfigurierbar via `openspec.yaml` → `stop_lock`

## Override Token

Einmal-Bypass fuer Gates:
- User sagt **"override"** → `phase_listener.py` erstellt Token
- `edit_gate.py` prueft Token und ueberspringt Phase-/TDD-Check
- Keywords konfigurierbar via `openspec.yaml` → `override_token`

## Hook-Architektur (v3 — 4 Hooks)

**PreToolUse Edit|Write:** `edit_gate.py` → [module hooks]
  Intern: Protected State → Always-Allowed → Code-Check → Infra → Stop-Lock → Workflow → Phase → Override → TDD

**PreToolUse Bash:** `bash_gate.py` → [module hooks]
  Intern: Stop-Lock → Git Fast-Path → State-Integrity → Secrets → Commit-Gates

**PostToolUse Bash:** `post_bash.py` → [module hooks]
  Intern: Test-Output-Detection → Adversary-Verdict

**UserPromptSubmit:** `phase_listener.py` → [module hooks]
  Intern: Override → Stop-Lock → Approval → New-UI → GREEN

## Konventionen für dieses Repository

### Beim Bearbeiten des Frameworks

1. **Keine Breaking Changes** ohne Migration-Pfad
2. **CHANGELOG.md** bei jeder Änderung aktualisieren
3. **Versionsnummer** in setup.py bei Releases erhöhen
4. **Tests** für Hooks: Manuell in einem Test-Projekt validieren

### Verzeichnis-Konventionen

| Pfad | Zweck |
|------|-------|
| `core/hooks/*.py` | v3: 4 konsolidierte Hooks + Utilities |
| `core/agents/*.md` | Agent-Definitionen mit YAML-Frontmatter |
| `core/commands/*.md` | Slash-Command-Definitionen |
| `modules/<name>/` | Domain-Module mit eigener config.yaml |
| `templates/` | Wiederverwendbare Spec-Templates |

### Hook-Entwicklung (v3)

v3 konsolidiert alle Checks in 4 Hooks. Neue Checks gehoeren IN die bestehenden Hooks, nicht als separate Dateien. Modul-spezifische Hooks werden via `modules/<name>/config.yaml` → `hooks:` registriert.

```python
# Modul-Hook schreiben — nutze hook_utils fuer Bootstrap:
from hook_utils import setup_path, find_project_root, get_tool_input, block, allow
setup_path()
from config_loader import load_config

def main():
    tool_input = get_tool_input()
    file_path = tool_input.get("file_path", "")

    if violation_detected:
        block("BLOCKED: Reason for blocking")
    allow()

if __name__ == "__main__":
    main()
```

**Exit-Codes:** 0 = erlaubt, 2 = blockiert (stderr wird Claude angezeigt)

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

# Kurze Slash-Command-Aliase generieren (z.B. /50-implement statt /agent-os-openspec:50-implement)
python3 /path/to/agent-os-openspec/setup.py ~ --command-aliases   # empfohlen: global (~)

# Version prüfen
python3 /path/to/agent-os-openspec/setup.py --version
```

## Wichtige Dateien

| Datei | Beschreibung |
|-------|--------------|
| `setup.py` | Installations- und Update-Tool (v3.0) |
| `config.yaml` | Template fuer Projektkonfiguration |
| `CHANGELOG.md` | Versionshistorie |
| `core/hooks/edit_gate.py` | Konsolidierter Edit/Write Guard (ersetzt 17 Hooks) |
| `core/hooks/bash_gate.py` | Konsolidierter Bash Guard (ersetzt 15 Hooks) |
| `core/hooks/post_bash.py` | PostToolUse Bash (Adversary Detection) |
| `core/hooks/phase_listener.py` | UserPromptSubmit Listener (ersetzt 6 Hooks) |
| `core/hooks/workflow.py` | Workflow State CLI (isolierte JSON-Files pro Workflow) |
| `core/hooks/qa_gate.py` | QA-Gate: Test-Output validieren, Verdict setzen |
| `core/hooks/override_token.py` | Shared Override-Token Management (TTL, Multi-WF) |
| `core/hooks/migrate_state.py` | v2 → v3 State-Migration |
| `core/hooks/hook_utils.py` | Shared Bootstrap (Imports, Parsing, Exit-Helpers) |
| `core/hooks/config_loader.py` | Config-Loader (YAML + Local Overrides) |
| `core/hooks/adversary_dialog.py` | Adversary Dialog System (Spec-Checkliste, Tri-State Verdict) |
| `core/agents/fresh-eyes-inspector.md` | Unabhaengiger UI-Beobachter ohne Bug-Kontext |

## Slash-Commands Übersicht

| Command | Phase | Beschreibung |
|---------|-------|--------------|
| `/10-context` | 1 | Relevanten Kontext sammeln |
| `/20-analyse` | 2 | Anforderungen analysieren |
| `/30-write-spec` | 3 | Spezifikation erstellen |
| `/40-tdd-red` | 5 | Failing Tests schreiben |
| `/50-implement` | 6 | Implementieren (Tests grün) |
| `/60-validate` | 7 | Manuelle Validierung |
| `/80-workflow` | - | Workflows verwalten |
| `/81-add-artifact` | - | Test-Artefakte registrieren |
| `/83-user-story` | - | JTBD-basierte User Story Discovery |
| `/01-feature` | - | Feature planen (startet feature-planner Agent) |
| `/82-test` | - | Tests ausführen (startet test-runner Agent) |

## Arbeitsanweisungen für Claude

Wenn du an diesem Framework arbeitest:

1. **Verstehe den Kontext**: Dies ist ein Meta-Projekt, Änderungen betreffen viele abhängige Projekte
2. **Teste Hooks**: Validiere Python-Hooks auf Syntax-Fehler vor Commit
3. **CHANGELOG**: Jede Änderung unter [Unreleased] dokumentieren
4. **Versionierung**: Semantische Versionierung (MAJOR.MINOR.PATCH)

### Workflow-Isolation — häufiges Missverständnis

**Workflows blockieren sich gegenseitig NICHT.** Jeder Workflow läuft in einem eigenen Worktree und ist vollständig isoliert. Gates (Adversary-Verdict, Approval-Marker, Phase-Checks) gelten ausschließlich für den **eigenen aktiven Workflow** (`OPENSPEC_ACTIVE_WORKFLOW`).

Siehst du einen anderen Workflow in `phase6` oder `phase7_validate` — das ist nicht dein Problem. Committe nur dann nicht, wenn dein eigener Workflow ein Gate auslöst. Niemals einen Commit verweigern oder dem User Befehle zur manuellen Ausführung geben, weil ein *fremder* Workflow in einer bestimmten Phase steckt.

Bei Feature-Requests:
- Prüfe erst, ob das Feature in core/ oder als Modul gehört
- Core = universell für alle Projekte
- Module = domain-spezifisch

## Adversary-Limit: Kein Fix-Loop nach VERIFIED

**Regel:** Nach dem ersten VERIFIED-Verdict des `implementation-validator`-Agenten ist Schluss. Kein weiterer Fix-Zyklus, kein zweiter Adversary-Lauf.

```
phase6_implement → Adversary → VERIFIED → workflow.py phase phase7_validate → FERTIG
                             ↘ BROKEN   → Gezielter Fix → nochmal Adversary (max. 1x)
                             ↘ AMBIGUOUS → User fragen
```

**Begründung:** Der Agent-Kaskaden-Effekt (Developer → Adversary → Fix → Adversary → Fix → Adversary) hat in realen Sessions 177 Minuten und ~3M Output-Tokens verbraucht. Ein VERIFIED bedeutet, die Implementierung ist gut genug — weitere Runden sind Token-Verbrennung ohne Mehrwert.

**Konkret:**
- Nach VERIFIED: Sofort `workflow.py phase phase7_validate` ausführen
- Bei BROKEN: Gezielten Fix-Agenten spawnen, dann NUR EINE weitere Adversary-Runde
- Zweites VERIFIED nach Fix: direkt zu phase7, kein dritter Lauf
- Zweites BROKEN nach Fix: Eskalation an User, kein weiterer Agent
