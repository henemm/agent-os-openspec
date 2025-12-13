# Agent OS + OpenSpec Templates

Templates fuer die Migration von iOS-Projekten zu Agent OS + OpenSpec.

## Schnellstart

```bash
# Migration starten
~/.agent-os-templates/migrate-project.sh /path/to/project "ProjectName"
```

## Was enthalten ist

### Standards (`standards/`)

Wiederverwendbare Coding-Standards:

| Standard | Beschreibung |
|----------|--------------|
| `global/analysis-first.md` | Erst analysieren, dann fixen |
| `global/scoping-limits.md` | Max 4-5 Dateien, +/-250 LoC |
| `global/documentation-rules.md` | Dokumentations-Pflichten |
| `swiftui/lifecycle-patterns.md` | SwiftUI Guard Flag Pattern etc. |
| `swiftui/localization.md` | Lokalisierungs-Best Practices |
| `swiftui/state-management.md` | State & Modal Patterns |

### Agents (`agents/`)

Spezialisierte Agenten mit injizierten Standards:

| Agent | Zweck |
|-------|-------|
| `bug-investigator.md` | Bug-Analyse nach Analysis-First |
| `feature-planner.md` | Feature-Planung mit Spec-First |
| `localizer.md` | DE/EN Lokalisierung |
| `test-runner.md` | Unit Test Ausfuehrung |

### Workflows (`workflows/`)

Komplette Arbeitsablaeufe:

| Workflow | Beschreibung |
|----------|--------------|
| `bug-fix-workflow.md` | Bug-Fix von Analyse bis Test |
| `feature-workflow.md` | Feature mit TDD |
| `release-workflow.md` | Version Bump und Deploy |

### Slash Commands (`slash-commands/`)

Claude Code Slash Commands:

| Command | Zweck |
|---------|-------|
| `/bug [desc]` | Bug analysieren |
| `/feature [name]` | Feature planen |
| `/test` | Tests ausfuehren |
| `/localize` | Lokalisierung pruefen |

## Nach der Migration

### 1. CLAUDE.md anpassen

Ersetze alle `{{PLACEHOLDER}}` mit projektspezifischen Werten:

- `{{PROJECT_NAME}}` - Projektname
- `{{PROJECT_DESCRIPTION}}` - Kurzbeschreibung
- `{{VERSION}}` - Aktuelle Version
- `{{PROJECT_FILE}}` - z.B. `MyApp.xcodeproj`
- `{{MAIN_SCHEME}}` - z.B. `MyApp`
- `{{TEST_SCHEME}}` - z.B. `MyAppTests`
- etc.

### 2. Workflows anpassen

In `.agent-os/workflows/*.md`:

- `{{PROJECT_FILE}}` ersetzen
- `{{TEST_SCHEME}}` ersetzen
- `{{MAIN_SCHEME}}` ersetzen

### 3. OpenSpec erstellen

1. `openspec/project.md` ausfuellen
2. Feature Specs in `openspec/specs/features/` erstellen

### 4. Projekt-spezifische Standards

Falls benoetigt, zusaetzliche Standards hinzufuegen:

- `standards/healthkit/` - HealthKit-spezifisch
- `standards/audio/` - Audio-Handling
- etc.

## Struktur nach Migration

```
YourProject/
├── .agent-os/
│   ├── standards/
│   │   ├── global/
│   │   │   ├── analysis-first.md
│   │   │   ├── scoping-limits.md
│   │   │   └── documentation-rules.md
│   │   └── swiftui/
│   │       ├── lifecycle-patterns.md
│   │       ├── localization.md
│   │       └── state-management.md
│   ├── agents/
│   │   ├── bug-investigator.md
│   │   ├── feature-planner.md
│   │   ├── localizer.md
│   │   └── test-runner.md
│   └── workflows/
│       ├── bug-fix-workflow.md
│       ├── feature-workflow.md
│       └── release-workflow.md
├── .claude/
│   ├── commands/
│   │   ├── bug.md
│   │   ├── feature.md
│   │   ├── test.md
│   │   └── localize.md
│   └── settings.local.json
├── openspec/
│   ├── project.md
│   ├── specs/
│   │   ├── features/
│   │   └── integrations/
│   └── changes/
├── DOCS/
│   ├── ACTIVE-todos.md
│   └── ACTIVE-roadmap.md
└── CLAUDE.md
```

## Globale Regeln

Die globalen Zusammenarbeits-Regeln bleiben in `~/.claude/CLAUDE.md`.
Diese gelten fuer ALLE Projekte und muessen nicht kopiert werden.
