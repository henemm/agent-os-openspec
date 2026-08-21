# Mini-Spec: /clear-Checkpoint — Sicherungslage belegen statt behaupten

Issue: #107 · Workflow: `feat-107-clear-checkpoint` · Track: Fast

## Ausgangslage

Seit #103/#104 endet jede Phase mit einem `/clear`-Hinweis. Er behauptet pauschal, der State
liege "sicher auf der Platte", zeigt aber nicht **was** gesichert ist — und kennt den Fall
nicht, dass gerade **nichts** gesichert ist. Die Abstufung hängt zudem an der Kontextgröße
("_Bei kleinem Kontext optional_") statt an der Sicherungslage.

## Was ändert sich

**Betroffen: 5 Dateien** unter `core/commands/` — `10-context.md`, `20-analyse.md`,
`30-write-spec.md`, `40-tdd-red.md`, `50-implement.md`.

### 1. Der Block wird durch einen einheitlichen Checkpoint ersetzt

Alt (überall identisch):

```
Nächster Schritt — Kontext zurücksetzen spart Tokens (der Workflow-State liegt sicher auf der Platte):
1. `/clear`
2. `/<folge> #<N>`   (lädt ... automatisch von der Platte)

_Bei kleinem Kontext optional — dann genügt direkt `/<folge>`._
```

Neu — **Positiv-Fall**, wenn alle Vorbedingungen erfüllt sind:

```
**Gesichert auf der Platte:**
- `.claude/workflows/<name>.json` — Phase `<phase>`, Verdict, Artefakt-Register
- `<pfad/zur/ergebnisdatei>` — <was genau darin steht>
- <weitere Ergebnisdatei mit Pfad>

✅ **`/clear` ist jetzt gefahrlos** — alles oben Gelistete stellt der Folge-Befehl allein aus
diesen Dateien wieder her. Im Gesprächsverlauf steht nichts, was verloren ginge.

1. `/clear`
2. `/<folge> #<N>`
```

Neu — **Negativ-Fall**, wenn mindestens eine Vorbedingung verletzt ist:

```
⚠️ **`/clear` jetzt NICHT** — Folgendes steht nur im Gesprächsverlauf:
- <was fehlt> → sichern mit: <konkreter Befehl oder Schritt>

Erst sichern, dann ist `/clear` gefahrlos.
```

### 2. Vorbedingungs-Prüfung als Instruktion an Claude

Vor jedem Checkpoint-Block steht künftig eine Prüf-Anweisung in einem eigenen
`### Checkpoint prüfen (Anweisung an dich — nicht ausgeben)`-Abschnitt. Sie steht
**oberhalb** der Ausgabe-Vorlagen; die Vorlagen selbst (`### Ausgabe A: Positiv-Block …`,
`### Ausgabe B: Negativ-Block …`) enthalten ausschließlich Text, der wörtlich an den User
geht. Claude gibt das `✅`-Verdikt **nur** aus, wenn alle Punkte erfüllt sind:

In **allen** fünf Dateien:

- Phase im Workflow-State geschrieben (`workflow.py status` bestätigt sie)
- Alle Ergebnisdateien der Phase liegen auf der Platte
- Keine Erkenntnis, die für den Folgeschritt nötig und nirgends niedergeschrieben ist

Zusätzlich **nur ab Phase 5** (`40-tdd-red.md`, `50-implement.md`):

- Alle RED-Artefakte per `add-artifact` registriert
- Keine uncommitteten Änderungen an Dateien, die der Folgeschritt braucht

Ist ein Punkt verletzt → Negativ-Block mit dem konkreten Sicherungsschritt.

**Warum die Commit-Bedingung in Phase 1-3 fehlt:** `/clear` löscht den Gesprächsverlauf,
nicht das Arbeitsverzeichnis — "uncommitted" und "nicht gesichert" sind nicht dasselbe. Die
Phasen 1-3 committen nichts; ihre Ergebnisdatei (z.B. `docs/context/<name>.md`) ist per
Definition uncommitted und wird vom Folgeschritt gebraucht. Als Vorbedingung formuliert wäre
sie dort immer verletzt — der ⚠️-Block erschiene in drei von fünf Phasen ausnahmslos, und eine
Warnung, die immer feuert, wird ignoriert. Dass die Ergebnisdatei geschrieben ist, deckt der
Punkt "Alle Ergebnisdateien der Phase liegen auf der Platte" bereits ab. Ab Phase 5 wird
tatsächlich committed (Spec + RED-Tests bzw. Implementierung), dort bleibt die Bedingung
fachlich richtig und stehen.

### 3. Kontextgrößen-Zusatz entfällt

`_Bei kleinem Kontext optional_` wird gestrichen. Die Entscheidung hängt an der
Sicherungslage, nicht an der Kontextgröße — ein `/clear` bei kleinem Kontext verliert
eine ungesicherte Erkenntnis genauso.

### 4. Phasen-spezifische Sicherungslisten

Jede Datei listet ihre eigenen Ergebnisse:

| Command | Sicherungsliste |
|---------|----------------|
| `10-context.md` | Workflow-State (Phase) + Kontext-Dokument |
| `20-analyse.md` | Workflow-State (Phase) + Analyse-Dokument |
| `30-write-spec.md` | Workflow-State (`phase4_approved`) + freigegebene Spec-Datei |
| `40-tdd-red.md` | Workflow-State (Phase) + Test-Dateien + registrierte RED-Artefakte |
| `50-implement.md` | Workflow-State (Phase + Verdict) + Commit der Implementierung |

## Was darf sich nicht ändern

- **Keine Hook-, Gate- oder State-Logik.** Ausschließlich Markdown unter `core/commands/`.
- **Der Wiedereinstiegs-Abschnitt am Dateianfang** (`## Wiedereinstieg via Issue-Nummer`)
  bleibt unangetastet — der funktioniert und ist nicht Gegenstand dieses Issues.
- **`60-validate.md` bekommt keinen Checkpoint.** Nach der Validierung folgt der Commit in
  derselben Sitzung; ein `/clear` dazwischen wäre schädlich, kein Angebot. (Abweichung von
  AC-3 im Issue, das von sechs Dateien spricht — im Issue nachtragen.)
- **Die bestehende Zusammenfassungs-Struktur** jeder Phase (Was wurde erreicht, Risiko etc.)
  bleibt erhalten; nur der `/clear`-Block darunter wird ersetzt.
- **Keine neuen Slash-Commands, keine Umbenennungen.**

## Manuelle Test-Schritte

1. `grep -c "liegt sicher auf der Platte" core/commands/*.md` → 0 Treffer in allen fünf Dateien
2. `grep -c "Bei kleinem Kontext optional" core/commands/*.md` → 0 Treffer
3. `grep -l "/clear\` ist jetzt gefahrlos" core/commands/*.md` → genau die fünf Zieldateien
4. `grep -l "clear\` jetzt NICHT" core/commands/*.md` → dieselben fünf Dateien
5. `grep -c "Gesichert auf der Platte" core/commands/*.md` → je 1 pro Zieldatei
6. `60-validate.md` enthält keinen der neuen Marker
7. Sichtprüfung: In allen fünf Dateien ist der Block wortgleich aufgebaut, nur die
   Sicherungsliste und der Folge-Befehl unterscheiden sich

## Inline-Test (während Implementierung)

- [ ] `tests/test_clear_checkpoint_blocks.py` — parst die fünf Command-Dateien und prüft:
  - jede enthält genau einen `**Gesichert auf der Platte:**`-Block
  - jede enthält beide Verdikt-Varianten (`✅ ... gefahrlos` und `⚠️ ... NICHT`)
  - keine enthält die Alt-Formulierungen (`liegt sicher auf der Platte`,
    `Bei kleinem Kontext optional`)
  - `60-validate.md` enthält keinen der Marker
  - die Prüf-Anweisung steht vor den beiden Ausgabe-Vorlagen und enthält die
    Vorbedingungen der jeweiligen Phase
  - in den Ausgabe-Vorlagen steht keine Meta-Anweisung (`Positiv-Block`,
    `Anweisung an dich`, `###` …)
  - Phase 1-3 nennt weder eine Commit- noch eine RED-Artefakt-Vorbedingung,
    Phase 5/6 nennen beide
  - die im Positiv-Block genannte Phase ist die, die dieselbe Datei zuletzt setzt
  - das Struktur-Gerüst der drei Abschnitte ist über alle fünf Dateien identisch
    (Vergleich ohne Aufzählungspunkte und ohne Command-Namen)

## Erfüllung der Akzeptanzkriterien

| AC | Erfüllt durch |
|----|--------------|
| AC-1 | Positiv-Block mit Sicherungsliste inkl. Pfaden + explizitem `✅`-Verdikt |
| AC-2 | Negativ-Block mit benanntem Sicherungsschritt + Vorbedingungs-Prüfung (Punkt 2), abgesichert durch `test_preconditions_listed_in_instruction_section` |
| AC-3 | Wortgleiche Struktur in allen fünf Dateien (60-validate ausgenommen, s.o.), abgesichert durch `test_checkpoint_structure_identical_across_files` |
| AC-4 | Vorbedingungs-Prüfung stellt sicher, dass `✅` nur erscheint, wenn der bestehende Wiedereinstiegs-Pfad tatsächlich trägt |
