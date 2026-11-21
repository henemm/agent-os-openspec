# Intake: Aufgaben-Klassifikation

**Immer der erste Schritt** — vor jedem Feature-Workflow. Auch Bugs starten hier.
Bestimmt den Track und verhindert, dass ein 10-Minuten-Fix 8 Phasen durchläuft.

## Scoring

Bewerte die Aufgabe anhand von 3 Kriterien:

| Kriterium | Low (0) | Medium (1) | High (2) |
|-----------|---------|------------|---------|
| **Scope** | 1–3 Dateien, ≤30 LoC | 4–8 Dateien, ≤100 LoC | Neue Architektur, neue Dateien |
| **Blast Radius** | Internes Utility, isoliert | Service-Schnittstelle | Infra, Auth, kritischer Pfad, Breaking Change |
| **Unsicherheit** | Bekanntes Pattern, vertrauter Code | Teilweise bekannt | Neue Technologie, unbekannter Bereich |

**Summe 0**: Fast Track (`feature-fast`) — Phasen 3→4→6→8
**Summe ≥ 1**: Voller Prozess (`feature`) — alle Phasen 1→8, Adversary: mindestens 2 Dialog-Runden bei hohem Risiko, eine Runde bei niedrigem Risiko
(`MIN_ROUNDS` in `adversary_dialog.py`). Das Risiko folgt mechanisch aus der Dateiliste der Änderung
(Hook-/Gate-Code, Guards, Konfiguration = hoch; nur Anweisungstext, Doku, Tests = niedrig; im Zweifel hoch) —
`python3 .claude/hooks/adversary_dialog.py risk` zeigt Stufe, Grund und geforderte Runden (#342)

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

### 1c. Issue-Kurzfassung für den Plan prüfen

Der Plan-Pane zeigt im Kopf den Issue-Titel und darunter „Problem: …“ / „Ziel: …“. Beides
liest `workflow.py` selbst aus dem Issue-Text (Abschnitte wie *Problem*, *Beschreibung*,
*Motivation* bzw. *Ziel*, *Expected*, *Lösung*; ohne Überschriften der erste Absatz):

```bash
python3 .claude/hooks/workflow.py issue-brief <N>
```

Ausgabe `TITLE=`, `PROBLEM=`, `ZIEL=`, `SOURCE=issue|manual|none`. Ist `PROBLEM=` oder `ZIEL=`
leer, nichtssagend oder falsch (etwa weil das Issue nur Stichpunkte enthält), schreibe nach
dem Lesen des Issues selbst je ein bis zwei Sätze in Alltagssprache — was heute stört und was
danach gelten soll:

```bash
python3 .claude/hooks/workflow.py issue-brief <N> --problem "<was heute stört>" --ziel "<was danach gilt>"
```

Eine so gesetzte Fassung (`SOURCE=manual`) wird vom Issue nicht mehr überschrieben;
`issue-brief <N> --auto` liest wieder aus dem Issue. Ohne Issue-Nummer entfällt der Schritt.

### 1a. Mehr-Issue-Auftrag sichern (#551)

Erteilt der PO mehrere Issues in einem Auftrag („Setze 545, 547 und 548 um …“),
sichere den Auftrag vor dem ersten Workflow per `workflow.py queue add` auf der
Platte, damit er `/clear` und Worktree-Wechsel überlebt:

```bash
python3 .claude/hooks/workflow.py queue add <N...> [--autark] [--note "<Wortlaut>"] [--spur <name>]
```

`--autark` nur, wenn der PO „autark“ bzw. „melde dich nur, wenn …“ gesagt hat.
`--spur <name>` (auch einzeln: `workflow.py spur <name>`), wenn der PO eine Spur genannt hat
oder die Aufgabe zu einer erkennbaren Reihe gehört (#591): nach „fertig“ schlägt `endstate`
dann offene Issues mit dem GitHub-Label `spur:<name>` vor. Epic und Meilenstein haben Vorrang;
die Spur wirkt als Stufe 3. Das Label muss an den Issues gesetzt sein.
Der Auftrag gehört dieser Sitzung (#613): Er liegt im Haupt-Repo unter
`.claude/auftrag/<sitzung>.json` (herdr-Workspace, sonst Sitzungs-Id; ohne beides
`.claude/auftrag.json`), andere Sitzungen sehen ihn nicht. `workflow.py complete` hakt
das Issue ab, `workflow.py queue` zeigt den Stand (`NEXT=`, `PROMPT=`, `OWNER=`); meldet
es `ALTAUFTRAG=`, liegt ein Auftrag ohne laufende Sitzung vor, den diese Sitzung nur
übernimmt (`workflow.py queue claim`), wenn er nachweislich ihr gilt. Ein
autarker Auftrag hält die Kette nicht für `/clear` an; menschliche Pflichtstopps
(AMBIGUOUS, zweites BROKEN, Override, Deploy-Freigabe, Stop-Lock, Produktfragen)
bleiben. Bei nur einem Issue entfällt der Schritt.

### 1c. Bugs: Vorprüfung vor dem Scoring

Bei einem Fehlerbericht, noch bevor bewertet wird:

1. **Duplikatsuche:** `gh issue list --label "bug" --state open` und
   `gh issue list --search "<Stichwort>" --state open`. Duplikat → bestehendes Issue verwenden.
2. **Fehler nachstellen** und die Ursache mit `file:line` belegen. Die ausführliche Vorgehensweise
   steht in `/20-analyse` Step 2b.
3. **Scoring speisen:** Ursache bekannt und ≤3 Dateien → Unsicherheit **Low**.
   Ursache unklar → Unsicherheit mindestens Medium.
4. **STOP** und nachfragen, wenn: Ursache unklar, nicht reproduzierbar, mehrere mögliche Ursachen,
   Fix > 5 Dateien.

Es gibt keinen eigenen Bug-Typ: Der Nachweis ist ein Test, der den Fehler vorher rot zeigt.
Danach gilt dieselbe Wahl `feature-fast` / `feature` wie für jede andere Aufgabe.

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

### 2b. Autonomie prüfen (#472)

```bash
python3 .claude/hooks/workflow.py autonomy
```

- **`AUTONOMY=auto`** — übernimm den Track-Vorschlag ohne Rückfrage: Bewertung
  ausgeben (als Info, ohne Frage nach dem Track) und den Workflow aus Step 3
  sofort mit `workflow.py start` starten, dann direkt mit dem nächsten Befehl
  weiter. Fast Track nur bei Summe 0 — im Zweifel höher bewerten, nie
  herunterrunden. Die Rückfrage-STOPs aus Step 1c bleiben: Ursache unklar, nicht
  reproduzierbar, mehrere mögliche Ursachen oder Fix > 5 Dateien → STOP und
  nachfragen, auch bei `AUTONOMY=auto`.
- **`AUTONOMY=manual`** (oder jede andere Ausgabe) — wie bisher: Track vorschlagen
  und auf die Bestätigung des Users warten.

Immer menschlich bleiben — auch bei `AUTONOMY=auto`: AMBIGUOUS-Verdict, zweites BROKEN bzw. Circuit Breaker, Override, Deploy, Stop-Lock.

### 3. Workflow starten (nach User-Bestätigung des Tracks, bei `AUTONOMY=auto` sofort)

`--issue <N>` nur, wenn die Issue-Nummer bekannt ist — sonst weglassen (die Nummer kommt dann
aus dem Namen).
`--score <S>` immer mit der Summe aus Step 2 (0–6): daraus lernt die Zeitschätzung (#620).

**Fast Track:**
```bash
python3 .claude/hooks/workflow.py start [name] --type feature-fast --issue <N> --score <S>
export OPENSPEC_ACTIVE_WORKFLOW=[name]
```
→ Weiter mit `/30-write-spec` (Mini-Spec-Format, siehe unten)

**Voller Prozess:**
```bash
python3 .claude/hooks/workflow.py start [name] --type feature --issue <N> --score <S>
export OPENSPEC_ACTIVE_WORKFLOW=[name]
```
→ Summe 1–3: weiter mit `/10-context` (Context + Analyse in einem Durchgang kombinieren)
→ Summe 4–6: weiter mit `/10-context`, dann `/20-analyse` (getrennt, 3x parallele Agenten), dann `/30-write-spec`

**Zeitschätzung (#620), direkt nach dem Start:**
```bash
python3 .claude/hooks/workflow.py estimate
```
Meldet `workflow.py estimate` `ESTIMATE=on`, den Satz aus `LINE=` als letzte Zeile der Intake-Bewertung nennen, z.B.
„Grobe Schätzung: 1 h 10 min–2 h 30 min, Ende ca. 15:40–17:00 (aus 7 Workflows)“; „(Startwert)“
heißt: noch zu wenige abgeschlossene Workflows. Bei `ESTIMATE=off` die Schätzung weglassen. Dieselbe
Spanne steht im Plan-Pane und wird mit jeder Phase enger.

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
| Adversary | ❌ entfällt | ✅ mindestens 2 Runden bei hohem Risiko, 1 bei niedrigem | ✅ mindestens 2 Runden bei hohem Risiko, 1 bei niedrigem |
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

**Auto-Modus (`autonomy.mode: auto`, #470):** Auch der Fast Track braucht dann ein
unabhängiges PO-Briefing mit `## Ampel` — die Ausnahme `skip_fast_track` gilt im
Auto-Modus nicht. Also nach der Mini-Spec den `po-briefer` laufen lassen
(`/30-write-spec` Step 3b), `workflow.py set-briefing <pfad>` und danach
`workflow.py auto-approve`: `AUTO_APPROVE=done` → direkt weiter zu `/50-implement`,
`AUTO_APPROVE=human` → der PO gibt wie bisher mit "approved" frei.

## Was beim Fast Track IMMER aktiv bleibt

- **Spec + User-Freigabe** — keine Implementierung ohne "approved"
- **Rebase-Gate** — Branch muss auf `origin/main` stehen
- **Secrets Guard** — nie Credentials im Code
- **Stop-Lock** — "stopp" pausiert sofort
