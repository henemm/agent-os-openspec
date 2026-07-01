---
description: "Intake: Aufgaben-Klassifikation"
disable-model-invocation: false
---

# Intake: Aufgaben-Klassifikation

**Immer der erste Schritt** — vor jedem Feature-Workflow.
Bestimmt den Track und verhindert, dass ein 10-Minuten-Fix 8 Phasen durchläuft.

## Setup

```bash
# Plugin: CLAUDE_PLUGIN_ROOT; Legacy-Fallback: .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"; _H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## Scoring

Bewerte die Aufgabe anhand von 3 Kriterien:

| Kriterium | Low (0) | Medium (1) | High (2) |
|-----------|---------|------------|---------|
| **Scope** | 1–3 Dateien, ≤30 LoC | 4–8 Dateien, ≤100 LoC | Neue Architektur, neue Dateien |
| **Blast Radius** | Internes Utility, isoliert | Service-Schnittstelle | Infra, Auth, kritischer Pfad, Breaking Change |
| **Unsicherheit** | Bekanntes Pattern, vertrauter Code | Teilweise bekannt | Neue Technologie, unbekannter Bereich |

**Summe 0**: Fast Track (`feature-fast`) — Phasen 3→4→6→8
**Summe 1–3**: Standard (`feature`) — Phasen 1+2→3→4→5→6→7→8
**Summe 4–6**: Full Process (`feature`) — alle Phasen, volle Tiefe, 2+ Adversary-Runden

## Deine Aufgaben

### 1. Aufgabe verstehen + schnell recherchieren

Lies den Aufgaben-Kontext aus dem Gespräch (ARGUMENTS oder letzte User-Nachricht).
Bei Unklarheit über Scope: schnelle Suche:

```bash
# Betroffene Dateien schätzen
grep -rn "keyword" --include="*.py" -l | head -10
```

### 2. Score präsentieren und Track vorschlagen

Gib dem User exakt dieses Format aus:

```
## Intake-Bewertung: [Aufgaben-Titel]

| Kriterium     | Score  | Begründung            |
|---------------|--------|-----------------------|
| Scope         | Low    | 2 Dateien, ~20 LoC    |
| Blast Radius  | Low    | Internes Utility      |
| Unsicherheit  | Low    | Bekanntes Pattern     |

Summe: 0 → **Fast Track** · Modell: **Sonnet**

Was das bedeutet:
- Kein Context-Doc, keine Analyse-Phase
- Mini-Spec (Bullets statt vollständige Spec) + User-Freigabe
- Inline-Test während Implementierung (kein separates TDD-RED)
- Kein Adversary Agent
```

**Workflow-Name:** Leite ihn selbst aus dem Aufgaben-Titel ab (Issue-Nummer + Stichwort, z.B. `fix-862-col-labels`). Nie beim User erfragen.

### 3. Workflow starten (nach User-Bestätigung des Tracks)

**Fast Track:**
```bash
$WF start [name] --type feature-fast
export OPENSPEC_ACTIVE_WORKFLOW=[name]
```
→ Weiter mit `/30-write-spec` (Mini-Spec-Format, siehe unten)

**Standard Track:**
```bash
$WF start [name] --type feature
export OPENSPEC_ACTIVE_WORKFLOW=[name]
```
→ Weiter mit `/10-context` (Context + Analyse in einem Durchgang kombinieren)

**Full Process:**
```bash
$WF start [name] --type feature
export OPENSPEC_ACTIVE_WORKFLOW=[name]
```
→ Weiter mit `/10-context`, dann `/20-analyse` (getrennt, 3x parallele Agenten), dann `/30-write-spec`

## Modell-Empfehlung

| Track | Hauptkontext | Begründung |
|-------|-------------|-----------|
| Fast Track | **Sonnet** | Bekannte Aufgabe, kein komplexes Reasoning nötig |
| Standard | **Sonnet** | Kreativ/analytisch aber gut definiert — Kosten/Qualitäts-Optimum |
| Full Process | **Opus** | Hohe Komplexität, hoher Einsatz, potenziell Neuland — Mehrpreis lohnt im Haupt-Reasoning-Loop |

Die Modell-Wahl gilt für den **Hauptkontext** (die laufende Claude-Session).
Sub-Agenten haben eigene Modelle (Haiku für mechanische Tasks, Sonnet für Analyse/Specs) — das bleibt unabhängig vom Track.

Modell wechseln: `/model` in der Claude-Code-Session oder beim Start `claude --model claude-opus-4-8`.

## Track-Unterschiede

| Phase | Fast Track | Standard | Full Process |
|-------|-----------|---------|-------------|
| Context-Doc | ❌ entfällt | ✅ kurz, inline | ✅ vollständig |
| Analyse | ❌ entfällt | ✅ 1x Explore | ✅ 3x Haiku parallel |
| Spec | ✅ Mini-Spec | ✅ Vollständig | ✅ Vollständig |
| User-Freigabe | ✅ immer | ✅ immer | ✅ immer |
| TDD RED | ❌ inline | ✅ Separate Phase | ✅ Separate Phase |
| Adversary | ❌ entfällt | ✅ 1 Runde | ✅ 2+ Runden |
| Manuelle Validierung | ✅ immer | ✅ immer | ✅ immer |

## Mini-Spec (Fast Track)

Beim Fast Track schreibt der Hauptkontext direkt (kein Sonnet-Agent) eine Mini-Spec.
Datei: `docs/specs/fast/[name].md`

```markdown
# Mini-Spec: [Name]

## Was ändert sich
- [Änderung 1]
- [Änderung 2]

## Was darf sich nicht ändern
- [Invariante]

## Manuelle Test-Schritte
1. [Schritt]
2. [Schritt]

## Inline-Test (wird während Implementierung geschrieben)
- [ ] Test für [Hauptverhalten]
```

Nach User-Freigabe ("approved") direkt zu `/50-implement`.

## Was beim Fast Track IMMER aktiv bleibt

- **Spec + User-Freigabe** — keine Implementierung ohne "approved"
- **Rebase-Gate** — Branch muss auf `origin/main` stehen
- **Secrets Guard** — nie Credentials im Code
- **Stop-Lock** — "stopp" pausiert sofort
