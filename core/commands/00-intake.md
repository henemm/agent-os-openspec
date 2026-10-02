# Intake: Aufgaben-Klassifikation

**Immer der erste Schritt** — vor jedem Feature-Workflow.
Bestimmt den Track und verhindert, dass ein 10-Minuten-Fix 8 Phasen durchläuft.

## Scoring

Bewerte die Aufgabe anhand von 3 Kriterien:

| Kriterium | Low (0) | Medium (1) | High (2) |
|-----------|---------|------------|---------|
| **Scope** | 1–3 Dateien, ≤30 LoC | 4–8 Dateien, ≤100 LoC | Neue Architektur, neue Dateien |
| **Blast Radius** | Internes Utility, isoliert | Service-Schnittstelle | Infra, Auth, kritischer Pfad, Breaking Change |
| **Unsicherheit** | Bekanntes Pattern, vertrauter Code | Teilweise bekannt | Neue Technologie, unbekannter Bereich |

**Summe 0**: Fast Track (`feature-fast`) — Phasen 3→4→6→8
**Summe ≥ 1**: Voller Prozess (`feature`) — alle Phasen 1→8, Adversary mit mindestens 2 Dialog-Runden
(`MIN_ROUNDS` in `adversary_dialog.py`)

Der Workflow-State kennt genau diese zwei Stufen (`feature-fast`, `feature`). Die **Tiefe** im vollen
Prozess richtet sich nach der Summe — das ist eine Anweisung, kein Zustand im State (#254):

- Summe 1–3: Kontext und Analyse kurz in einem Durchgang (1x Explore)
- Summe 4–6: Kontext und Analyse getrennt, Analyse mit 3x Haiku parallel

## Deine Aufgaben

### 1. Aufgabe verstehen + schnell recherchieren

Lies den Aufgaben-Kontext aus dem Gespräch (ARGUMENTS oder letzte User-Nachricht).
Bei Unklarheit über Scope: schnelle Suche:

```bash
# Betroffene Dateien schätzen
grep -rn "keyword" --include="*.py" -l | head -10
```

### 1b. Issue-Nummer(n) ins Session-Register eintragen

Sobald die Issue-Nummer(n) aus dem Aufgaben-Kontext bekannt sind — noch vor der
Track-Bewertung, denn im Fast Track entsteht nie ein Workflow:

```bash
python3 .claude/hooks/session_singleton_guard.py claim --issue <N>[,<M>...]
```

Damit weiß jede andere Session, wer gerade an Issue #N arbeitet. Ohne Issue-Nummer
(z.B. reiner Wartungs-Task) entfällt der Schritt.

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
python3 .claude/hooks/workflow.py start [name] --type feature-fast
export OPENSPEC_ACTIVE_WORKFLOW=[name]
```
→ Weiter mit `/30-write-spec` (Mini-Spec-Format, siehe unten)

**Voller Prozess:**
```bash
python3 .claude/hooks/workflow.py start [name] --type feature
export OPENSPEC_ACTIVE_WORKFLOW=[name]
```
→ Summe 1–3: weiter mit `/10-context` (Context + Analyse in einem Durchgang kombinieren)
→ Summe 4–6: weiter mit `/10-context`, dann `/20-analyse` (getrennt, 3x parallele Agenten), dann `/30-write-spec`

## Modell-Empfehlung

| Stufe | Hauptkontext | Begründung |
|-------|-------------|-----------|
| Fast Track | **Sonnet** | Bekannte Aufgabe, kein komplexes Reasoning nötig |
| Voller Prozess, Summe 1–3 | **Sonnet** | Kreativ/analytisch aber gut definiert — Kosten/Qualitäts-Optimum |
| Voller Prozess, Summe 4–6 | **Opus** | Hohe Komplexität, hoher Einsatz, potenziell Neuland — Mehrpreis lohnt im Haupt-Reasoning-Loop |

Die Modell-Wahl gilt für den **Hauptkontext** (die laufende Claude-Session).
Sub-Agenten haben eigene Modelle (Haiku für mechanische Tasks, Sonnet für Analyse/Specs) — das bleibt unabhängig vom Track.

Modell wechseln: `/model` in der Claude-Code-Session oder beim Start `claude --model claude-opus-4-8`.

## Unterschiede nach Stufe und Tiefe

| Phase | Fast Track | Voller Prozess, Summe 1–3 | Voller Prozess, Summe 4–6 |
|-------|-----------|---------|-------------|
| Context-Doc | ❌ entfällt | ✅ kurz, inline | ✅ vollständig |
| Analyse | ❌ entfällt | ✅ 1x Explore | ✅ 3x Haiku parallel |
| Spec | ✅ Mini-Spec | ✅ Vollständig | ✅ Vollständig |
| User-Freigabe | ✅ immer | ✅ immer | ✅ immer |
| TDD RED | ❌ inline | ✅ Separate Phase | ✅ Separate Phase |
| Adversary | ❌ entfällt | ✅ mindestens 2 Runden | ✅ mindestens 2 Runden |
| Validierung | ✅ immer | ✅ immer | ✅ immer |

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
