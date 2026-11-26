# Hintergrund zu /00-intake

Begründungen und Sonderfälle zu core/commands/00-intake.md; der Befehlstext enthält Ablauf und Pflichtschritte.

## Scoring: Tiefe im vollen Prozess

Der Workflow-State kennt genau diese zwei Stufen (`feature-fast`, `feature`). Die **Tiefe** im vollen
Prozess richtet sich nach der Summe — das ist eine Anweisung, kein Zustand im State (#254):

- Summe 1–3: Kontext und Analyse kurz in einem Durchgang (1x Explore)
- Summe 4–6: Kontext und Analyse getrennt, Analyse mit 3x Haiku parallel

## 1. Aufgabe verstehen: Suche nach betroffenen Dateien

```bash
# Betroffene Dateien schätzen
grep -rn "keyword" --include="*.py" -l | head -10
```

## 1b. Session-Register

Sobald die Issue-Nummer(n) aus dem Aufgaben-Kontext bekannt sind — noch vor der
Track-Bewertung, denn im Fast Track entsteht nie ein Workflow:

Damit weiß jede andere Session, wer gerade an Issue #N arbeitet. Ohne Issue-Nummer
(z.B. reiner Wartungs-Task) entfällt der Schritt.

## 1c. Issue-Kurzfassung für den Plan

Der Plan-Pane zeigt im Kopf den Issue-Titel und darunter „Problem: …“ / „Ziel: …“. Beides
liest `workflow.py` selbst aus dem Issue-Text (Abschnitte wie *Problem*, *Beschreibung*,
*Motivation* bzw. *Ziel*, *Expected*, *Lösung*; ohne Überschriften der erste Absatz):

Ausgabe `TITLE=`, `PROBLEM=`, `ZIEL=`, `SOURCE=issue|manual|none`. Ist `PROBLEM=` oder `ZIEL=`
leer, nichtssagend oder falsch (etwa weil das Issue nur Stichpunkte enthält), schreibe nach
dem Lesen des Issues selbst je ein bis zwei Sätze in Alltagssprache — was heute stört und was
danach gelten soll:

Eine so gesetzte Fassung (`SOURCE=manual`) wird vom Issue nicht mehr überschrieben;
`issue-brief <N> --auto` liest wieder aus dem Issue. Ohne Issue-Nummer entfällt der Schritt.

## 1a. Mehr-Issue-Auftrag: Besitz und Pflichtstopps

Erteilt der PO mehrere Issues in einem Auftrag („Setze 545, 547 und 548 um …“),
sichere den Auftrag vor dem ersten Workflow per `workflow.py queue add` auf der
Platte, damit er `/clear` und Worktree-Wechsel überlebt:

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

## 1c. Bugs: Einordnung

2. **Fehler nachstellen** und die Ursache mit `file:line` belegen. Die ausführliche Vorgehensweise
   steht in `/20-analyse` Step 2b.

Es gibt keinen eigenen Bug-Typ: Der Nachweis ist ein Test, der den Fehler vorher rot zeigt.
Danach gilt dieselbe Wahl `feature-fast` / `feature` wie für jede andere Aufgabe.

## 3. Workflow starten: Issue-Nummer, Score und Registrierung

`--issue <N>` nur, wenn die Issue-Nummer bekannt ist — sonst weglassen (die Nummer kommt dann
aus dem Namen).
`--score <S>` immer mit der Summe aus Step 2 (0–6): daraus lernt die Zeitschätzung (#620).

**Registrierung am Issue (#461):** `start` trägt die Sitzung als Kommentar am Issue ein (Ort,
Name, Beginn, Phase). Bricht `start` mit `ABGEBROCHEN: An Issue #N arbeitet bereits eine andere
Sitzung` ab, entsteht kein Workflow: nicht weiterarbeiten, dem PO in einfachen Worten sagen, wer
wo seit wann daran arbeitet. `workflow.py claim status` zeigt Alter des Eintrags und offene Pull
Requests; `start <name> --uebernehmen` nur, wenn die andere Sitzung nachweislich nicht mehr
arbeitet oder der PO zustimmt. Eine Warnung ohne Netz blockiert nicht (wird nachgeholt).

## Zeitschätzung: Beispiele

Meldet `workflow.py estimate` `ESTIMATE=on`, den Satz aus `LINE=` als letzte Zeile der Intake-Bewertung nennen, z.B.
„Start 21:41, Freigabe ca. 22:15 (aus 7 Workflows)“ (#642: vor der Spec-Freigabe nur deren
ungefährer Zeitpunkt, danach „Ende ca. 22:15–23:15 (80 % sicher, aus 12 Workflows)“, Prozent erst ab
10 Vergleichen); „Noch keine Zeitschätzung: zu wenig Vergleichsdaten“ heißt: noch zu wenige
abgeschlossene Workflows mit gemessener Arbeitszeit. Bei `ESTIMATE=off` die Schätzung weglassen.
Dieselben Zeiten stehen im Plan-Pane und werden mit jeder Phase genauer.

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
