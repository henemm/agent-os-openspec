# Agent Orchestration & Model Strategy

> Referenz-Template fuer die Modell-Zuweisungsstrategie in allen Projekten.

## Kernphilosophie

| Model | Staerke | Einsatz | Kosten |
|-------|---------|---------|--------|
| **Haiku** | Schnell, guenstig | Mechanische Aufgaben: Validierung, Kontext laden, Scope-Reviews | Niedrig |
| **Sonnet** | Qualitaet + Balance | Kreative/analytische Arbeit: Specs schreiben, Tests, Planung | Mittel |
| **Opus** | Hoechste Qualitaet | Kern-Implementierung im Hauptkontext (nicht delegiert) | Hoch |

## Architektur

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION FLOW                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User Request                                                    │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────┐                                                 │
│  │  Command     │  (Slash-Command startet Workflow-Phase)         │
│  │  /analyse    │                                                 │
│  └──────┬──────┘                                                 │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────────┐                │
│  │  Parallel Dispatching                         │                │
│  │                                               │                │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐      │                │
│  │  │ Explore  │ │ Explore  │ │ Explore  │      │                │
│  │  │ /haiku   │ │ /haiku   │ │ /haiku   │      │                │
│  │  │ Files    │ │ Specs    │ │ Deps     │      │                │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘      │                │
│  │       │             │             │            │                │
│  │       └─────────────┼─────────────┘            │                │
│  │                     │                          │                │
│  └─────────────────────┼──────────────────────────┘                │
│                        ▼                                          │
│  ┌──────────────────────────────────────────────┐                │
│  │  Strategic Assessment                         │                │
│  │  Plan / sonnet                                │                │
│  │  → Risiko, Scope, Empfehlung                  │                │
│  └──────────────────────┬───────────────────────┘                │
│                         │                                         │
│                         ▼                                         │
│  ┌──────────────────────────────────────────────┐                │
│  │  Synthese + Praesentieren                     │                │
│  │  Hauptkontext (Opus)                          │                │
│  └──────────────────────────────────────────────┘                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Model Selection Strategy

### Haiku-Aufgaben (schnell, mechanisch)

| Agent/Task | Beschreibung |
|------------|--------------|
| `spec-validator` | Spec auf Vollstaendigkeit pruefen (VALID/INVALID) |
| `test-runner` | Tests ausfuehren und Ergebnis zusammenfassen |
| `bug-intake` | Bug-Symptome sammeln, parallele Investigation |
| Explore-Tasks | Dateien finden, Kontext laden, Dependencies auflisten |
| Scope-Check | Geaenderte Dateien gegen Spec vergleichen |
| Config-Check | Konfigurationsdateien auf noetige Updates pruefen |

### Sonnet-Aufgaben (kreativ, analytisch)

| Agent/Task | Beschreibung |
|------------|--------------|
| `spec-writer` | Spezifikationen erstellen und aktualisieren |
| `docs-updater` | Dokumentation nach Aenderungen aktualisieren |
| `bug-investigator` | Tiefe Bug-Analyse mit Root Cause Identifikation |
| `feature-planner` | Feature-Planung und Architektur-Entscheidungen |
| Plan-Tasks | Strategische Bewertung, Risiko-Analyse |
| Auto-Fix | Validierungsfehler beheben |
| Test-Writing | TDD RED Tests schreiben |

### Opus-Aufgaben (Hauptkontext, nicht delegiert)

| Task | Beschreibung |
|------|--------------|
| Kern-Implementierung | Eigentlicher Code in Phase 6 |
| User-Interaktion | Dialog mit dem User, Entscheidungen |
| Synthese | Ergebnisse aus Subagenten zusammenfuehren |
| `user-story-planner` | Kreative JTBD-Discovery (laeuft im Hauptkontext) |

## Dispatching-Muster

### Parallel Explore (3x Haiku)

Fuer schnelle Kontextsammlung. Ideal fuer Analyse-Phasen.

```
Dispatche 3 parallele Task-Aufrufe:
  Task(subagent_type="Explore", model="haiku", prompt="...")
  Task(subagent_type="Explore", model="haiku", prompt="...")
  Task(subagent_type="Explore", model="haiku", prompt="...")
```

### Write + Validate (Sonnet + Haiku)

Fuer Spec-Erstellung mit Qualitaetssicherung.

```
Step 1: Task(subagent_type="general-purpose", model="sonnet", prompt="Erstelle Spec...")
Step 2: Task(subagent_type="general-purpose", model="haiku", prompt="Validiere Spec...")
Step 3: Bei INVALID -> Fix + Re-Validate
```

### Parallel Validation (4x Haiku)

Fuer umfassende Validierung nach Implementation.

```
Dispatche 4 parallele Task-Aufrufe:
  Task(model="haiku", prompt="Test Check...")
  Task(model="haiku", prompt="Spec Compliance...")
  Task(model="haiku", prompt="Regression Check...")
  Task(model="haiku", prompt="Scope Check...")
```

### Auto-Fix Pattern (Sonnet nach Haiku-Findings)

```
Step 1: Haiku findet Probleme
Step 2: Task(model="sonnet", prompt="Behebe: [Haiku-Findings]...")
Step 3: Haiku verifiziert den Fix
```

## Kostenoptimierung

- **Mechanische Arbeit an Haiku delegieren** -> Spart Tokens im Hauptkontext
- **Parallel dispatchen** -> Schnellere Ausfuehrung
- **Opus nur fuer Kern-Arbeit** -> Hoechste Qualitaet wo es zaehlt
- **Sonnet fuer kreative Aufgaben** -> Gute Balance aus Qualitaet und Kosten

## Integration in bestehende Projekte

1. Agents aus `core/agents/` uebernehmen (via setup.py)
2. Commands aus `core/commands/` verwenden
3. `config.yaml` Agent-Section konfigurieren
4. Optional: Eigene domain-spezifische Agents in `modules/` erstellen
