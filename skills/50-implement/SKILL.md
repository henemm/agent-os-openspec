---
description: "Implement the feature (TDD GREEN + Adversary)"
disable-model-invocation: false
---

# Phase 6: Implementation (TDD GREEN)

You are in **Phase 6 - Implementation / TDD GREEN Phase**.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
_S="${_H%/core/hooks}/scripts"; [ "$_H" = ".claude/hooks" ] && _S=".claude/scripts"
```

## Purpose

Write the **minimal code** to make failing tests pass. No more, no less.

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/50-implement.md` im Plugin-Ordner — nur bei Bedarf lesen.

## Prerequisites

- Spec approved (`phase4_approved`)
- TDD RED complete (`phase5_tdd_red`)
- Test artifacts registered showing failures

Check status:
```bash
$WF status
```

**If TDD RED artifacts are missing, the `tdd_enforcement` hook will BLOCK your edits!**

## Your Tasks

### Step 0: Workflow-State auflösen (ZUERST — vor allem anderen)

**Wurde dieser Befehl mit einer Issue-Nummer aufgerufen** (z. B. `/50-implement #42` — typisch nach einem `/clear`)? Dann löse den Workflow-Namen von der Platte auf:

```bash
$WF find 42   # die übergebene Nummer
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (ein reines `export` reicht NICHT):

```bash
$WF switch <NAME-aus-obigem-Output>
$WF status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** (Phase, Spec, offene Punkte). Ohne Issue-Argument reicht `workflow.py status`.

### Hängende Subagenten

Die Sitzung wird automatisch erneut aufgerufen, sobald der Hintergrund-Agent fertig ist. Fehlt beim
nächsten eigenen Zug der Bericht: `TaskList` prüfen, noch aktiv → `TaskStop`, mit präziserem Briefing
neu starten. Nur innerhalb eines `/loop`-Laufs zusätzlich:

```
ScheduleWakeup(1200, "Implementierung Rückfall [50-implement], nur im /loop-Kontext: TaskList → noch aktiver Explore-/Developer-/Adversary-Agent? JA → TaskStop, dann User: 'Agent hängt — bitte /50-implement neu starten.' NEIN → ignorieren, fertig.")
```

### Agent-Typen und Fallback (#577)

`developer-agent` und `implementation-validator` mit `subagent_type="<name>"` **ohne `model`** starten; anonyme Starts (`Explore`, `general-purpose`) tragen immer ein `model`.

**Fallback, wenn ein Typ in der Agent-Liste fehlt:**
- developer-agent → `agent-os-openspec:developer-agent`, sonst `Agent(subagent_type="general-purpose", model="opus", prompt="Lies zuerst .claude/agents/developer-agent.md und folge ihr. …")`
- implementation-validator → `agent-os-openspec:implementation-validator`, sonst `Agent(subagent_type="general-purpose", model="sonnet", prompt="Lies zuerst .claude/agents/implementation-validator.md und folge ihr. …")`

### Step 2: Kontext laden (Explore/Haiku)

Dispatche einen **Explore/Haiku Subagenten** um den Implementierungs-Kontext zu laden:

**Im Vordergrund starten (`run_in_background: false`).**

```
Agent(subagent_type="Explore", model="haiku", description="Kontext laden", run_in_background=false, prompt="
  Lies folgende Dateien und fasse den relevanten Kontext zusammen:
  - Spec: [spec_file_path]
  - Betroffene Dateien: [affected_files]
  - Test-Dateien: [test_files]

  Fasse zusammen: Welche Interfaces existieren, welche Methoden muessen
  implementiert werden, welche Imports werden benoetigt.")
```

**Kontext-Haushalt (Nachschlagen abgeben, gezielt lesen):** Nachschlagefragen („Wo wird X benutzt?“) gehen an einen Explore-Teilagenten (Haiku), der nur die Antwort zurückgibt. Selbst liest du nur, was du gleich brauchst, mit Zeilenbereich (`sed -n 120,160p`, Read mit offset/limit) oder gezielter Suche statt ganzer Dateien. Mehrere `grep`/`sed -n` zur selben Frage in einen Aufruf bündeln; Workflow-Aufrufe mit `workflow.py batch a -- b -- c` zusammenfassen.

### Step 3: Developer Agent spawnen (ORCHESTRATOR-PRINZIP)

**Der Hauptkontext schreibt KEINEN Code. Nie. Keine Ausnahmen.** Code-Edits gehoeren ausschliesslich dem **Developer Agent**.

```
Agent(subagent_type="developer-agent", description="Implementieren", run_in_background=true, prompt="
  Implementiere gemaess Spec.

  Spec: [spec_file_path einfuegen]
  Betroffene Dateien: [affected_files aus workflow status]
  Test-Dateien: [test_files]
  Test-Command: [qa_gate.test_command aus config.yaml]

  Deine Aufgabe:
  1. Lies Spec vollstaendig — alle AC-N Acceptance Criteria verstehen
  2. Lies failing Tests — was genau wird getestet?
  3. Lies betroffene Dateien — aktueller Stand
  4. Schreibe minimalen Code um jeden failing Test gruen zu machen
  5. Fuehre Tests aus nach jeder wesentlichen Aenderung
  6. Finaler Testlauf: python3 ${_H}/qa_gate.py --run
  7. Melde zurueck: Dateien geaendert, Tests gruen/rot, welche ACs erfuellt

  NICHT:
  - Features die nicht in der Spec stehen
  - Refactoring das nicht zum Gruen benoetigt wird
  - Premature optimization
  - Mehr als 3 Loesungsversuche ohne Rueckmeldung")
```

**Danach:** GRUEN → Step 4; ROT → Developer Agent erneut mit Fehlermeldung beauftragen (max. 3 Versuche total, dann Eskalation an User).

### Step 4: GREEN Artifacts registrieren

Den finalen Lauf liefert `qa_gate.py --run` (#404; fehlt er, selbst starten). Orchestrator registriert den Test-Output:

```bash
$WF add-artifact test_output \
    "docs/artifacts/[workflow]/test-run-output.txt" \
    "All tests PASSED" \
    phase6_implement
```

### Step 6: User-Freigabe der GREEN-Ergebnisse (PFLICHT)

Zuerst den Autonomie-Modus pruefen (`workflow.py autonomy`):

```bash
$WF autonomy
```

**Bei `AUTONOMY=auto`** (#471) die GREEN-Freigabe automatisch pruefen lassen (`workflow.py auto-green`):

```bash
$WF auto-green
```

- `AUTO_GREEN=done` → GREEN ist automatisch freigegeben (`green_approved`, protokolliert in `approvals`). Gib die Zusammenfassung unten als reine Information aus — ohne die Zeile mit `go` und ohne Rueckfrage — und gehe direkt zu Step 7. Auffaelligkeiten nicht zurueckhalten: sie stehen in der Zusammenfassung und gehen an den Adversary.
- `AUTO_GREEN=human` → nenne die `REASON=`-Zeile und verfahre wie im Modus `manual` unten.

**Bei `AUTONOMY=manual` oder `AUTO_GREEN=human`:**

**STOP! Du darfst NICHT weitermachen ohne User-Freigabe!**

Praesentiere dem User folgende Zusammenfassung:

---
**Implementierung fertig — deine Freigabe bitte.**

**Was wurde umgesetzt?**
[Feature/Bugfix in 1–2 Sätzen aus Nutzerperspektive — kein Code, keine Dateinamen]

**Was funktioniert jetzt?**
- [Konkretes Verhalten 1 aus Nutzersicht]
- [Konkretes Verhalten 2 aus Nutzersicht]

**Qualitätsprüfungen:** [N] Tests ✅ bestanden[, N fehlgeschlagen ❌ — falls vorhanden mit Erklärung in einfacher Sprache]

**Auffälligkeiten:**
[Alles was aufgefallen ist — oder: Keine]

Wenn das Ergebnis so stimmt, schreibe `go`.

---

**WICHTIG:**
- Du darfst NICHT selbst entscheiden ob Auffaelligkeiten relevant sind
- Du darfst NICHT "go" simulieren oder die Freigabe umgehen
- Der User gibt frei mit: "go", "weiter", "tests ok", "green ok"
- Freigaben nie über den Auswahldialog (`AskUserQuestion`) einholen, nur als Textzeile

### Step 7: Update Workflow State to Adversary Phase

```bash
$WF phase phase6b_adversary
```

### Step 8: Run Adversary Dialog (MANDATORY)

**Du kannst NICHT direkt zu `/60-validate` springen. Der Adversary-Dialog muss zuerst stattfinden.**

#### 8a. Spec parsen — Checkliste erstellen

```bash
python3 ${_H}/adversary_dialog.py parse <spec-pfad>
```

Danach das Protokoll-Geruest erzeugen (einzige Quelle des Formats; der Adversary-Agent befuellt es):

```bash
python3 ${_H}/adversary_dialog.py scaffold <workflow-name> <spec-pfad> \
    > docs/artifacts/<workflow-name>/adversary-dialog.md
```

Ist in der Projekt-`config.yaml` `precondition_origins.default_lang` gesetzt, zusaetzlich die Tabelle erzeugen und dem `implementation-validator`-Auftrag beilegen:

```bash
python3 ${_H}/precondition_origins.py --lang <default_lang> --root .
```

Ist `default_lang` nicht gesetzt, entfaellt der Aufruf.

#### 8b. Adversary-Dialog fuehren

Starte den `implementation-validator` Agent mit der Checkliste:

```
Agent(subagent_type="implementation-validator", description="Adversary-Dialog", run_in_background=true, prompt="
  Pruefe den aktuellen Workflow gegen die Spec.
  Hier ist die Checkliste der zu beweisenden Punkte:
  [Punkte aus 8a einfuegen]

  REGELN:
  - Lies NUR die Spec (nicht den Code!)
  - Fordere fuer JEDEN Punkt einen Beweis (Screenshot, Test-Output, konkreter Code-Pfad)
  - Akzeptiere NICHT die erste Antwort — bohre nach, frage nach Edge Cases
  - Mindestens 2 Runden Dialog bei hohem Risiko, 1 Runde bei niedrigem Risiko (Stufe: `python3 ${_H}/adversary_dialog.py risk`); auch eine einzige Runde belegt jeden Punkt
  - Fuehre Tests aus und speichere Output
  - Nutze das Structured Findings Schema (python3 ${_H}/adversary_dialog.py schema)")
```

Fordert der Adversary einen Beweis, beauftragst du den Developer Agent und relayierst dessen Output — bis alle AC-N-Punkte bewiesen ODER ein Defekt gefunden ist.

**Bei BROKEN:** Developer Agent erneut beauftragen (Schritt 3) — nicht selbst fixen!

#### 8c. Dialog-Protokoll speichern

**Pflicht-Liste zuerst (#259):**
```bash
python3 ${_H}/adversary_dialog.py required-files
```
Das Protokoll (`docs/artifacts/<workflow-name>/adversary-dialog.md`) muss **jede gelistete Datei**
per `Code reference: <pfad>:<zeile>` zitieren. Registriere es im Workflow:
```bash
$WF add-artifact adversary_dialog \
    "docs/artifacts/<workflow-name>/adversary-dialog.md" \
    "Adversary Dialog Protokoll" phase6b_adversary
```

**Stemple das Artifact (PFLICHT):**
```bash
python3 ${_H}/adversary_dialog.py stamp \
    "docs/artifacts/<workflow-name>/adversary-dialog.md"
```
Ohne Stempel lehnt das Gate das Artifact ab. Aendert ein spaeterer Fix eine zitierte Datei, braucht es einen neuen Dialog.

#### 8d. QA-Gate mit Checklist-Validierung

```bash
python3 ${_H}/qa_gate.py --run \
    --checklist docs/artifacts/<workflow-name>/adversary-dialog.md \
    --screenshot docs/artifacts/<workflow-name>/adversary-screenshot.png

# Fuer Infra-Tickets (ohne UI):
python3 ${_H}/qa_gate.py --run \
    --checklist docs/artifacts/<workflow-name>/adversary-dialog.md \
    --infra --no-visual "Infra-Ticket ohne UI"
```

`--run` fuehrt `qa_gate.test_command` aus `config.yaml` selbst aus (Ausgabe `docs/artifacts/<workflow-name>/test-run-output.txt`, Stempel `qa_run_stamp`); der Datei-Modus `qa_gate.py <datei>` ist veraltet und bei `qa_gate.require_run: true` abgeschaltet (#404). Ohne `--checklist` oeffnet `qa_gate.py` weder Commit noch Phase 8. Ausgaben immer unter `docs/artifacts/<workflow-name>/` ablegen, nie unter `/tmp`.

**Verdict:** VERIFIED → Phase 7; BROKEN → zurueck zu Step 3 (neuer Fix + neuer Dialog, nach 3 Loops Eskalation an User); AMBIGUOUS → User-Review.

**Wenn VERIFIED oder AMBIGUOUS (mit User-OK):**
```bash
$WF phase phase7_validate
```

## Implementation Constraints

Max 4-5 files, max +/-250 LoC, functions <= 50 LoC, no side effects outside spec scope.

## Next Step

Wenn Adversary VERIFIED (oder AMBIGUOUS mit User-OK): Stelle sicher, dass alle geänderten Dateien committed sind und das Adversary-Verdict im State steht — der nächste Schritt setzt den Gesprächskontext zurück. Danach folgt die Ausgabe an den User, danach rufst du `60-validate` selbst auf (siehe unten).

### Checkpoint prüfen (Anweisung an dich — nicht ausgeben)

Prüfe der Reihe nach, bevor du unten etwas ausgibst:

- Phase im Workflow-State geschrieben — `$WF status` bestätigt sie
- Alle Ergebnisdateien dieser Phase liegen auf der Platte
- Alle RED-Artefakte per `add-artifact` registriert
- Keine ungesicherten Änderungen an Dateien, die `/60-validate` braucht
- Keine Erkenntnis, die für `/60-validate` nötig und nirgends niedergeschrieben ist

Sind alle Punkte erfüllt: Gib den Positiv-Block aus. Ist mindestens einer verletzt: Gib stattdessen den Negativ-Block aus und ersetze dessen Platzhalter durch den konkreten Sicherungsschritt.

Weder diese Anweisung noch die `###`-Überschriften gehören in die Ausgabe — an den User geht ausschließlich der Text zwischen den `---`-Trennern, und zwar genau einmal, als letzter inhaltlicher Teil der Nachricht: keine Vorab- oder Kurzfassung davor, keine Wiederholung danach.

### Ausgabe: Zusammenfassung (immer)

---
✅ Phase 6 (Implementierung) abgeschlossen — Adversary VERIFIED.

Workflow: `<name>` · Issue: **#<N>** · Verdict: VERIFIED

**Was wurde erreicht:** Der Code ist fertig und hat eine unabhängige interne Qualitätsprüfung bestanden. Als Nächstes folgt die finale Validierung — dabei wird geprüft, ob alle Anforderungen aus der Spezifikation lückenlos erfüllt sind.

---

### Ausgabe A: Positiv-Block (alle Vorbedingungen erfüllt)

---
**Gesichert auf der Platte:**
- `.claude/workflows/<name>.json` — Phase `phase7_validate`, Feld `spec_file`, Verdict `VERIFIED`, Artefakt-Register
- Stand der Implementierung — alle geänderten Dateien sind gesichert, es gibt keine ungesicherten Änderungen

✅ **`/clear` ist jetzt gefahrlos** — alles oben Gelistete stellt der Folge-Befehl allein aus diesen Dateien wieder her. Im Gesprächsverlauf steht nichts, was verloren ginge.

1. `/clear`
2. `/60-validate #<N>`

---

### Ausgabe B: Negativ-Block (mindestens eine Vorbedingung verletzt)

---
⚠️ **`/clear` jetzt NICHT** — Folgendes steht nur im Gesprächsverlauf:
- <was fehlt> → sichern mit: <konkreter Befehl oder Schritt>

Erst sichern, dann ist `/clear` gefahrlos.

---

Vor dem Selbstaufruf zusätzlich `$WF context` ausführen (Kontext-Haushalt): Bei `CONTEXT_STOP=on` (Kontext über der wirksamen Schwelle `CONTEXT_THRESHOLD` aus `context_budget`: Grundkontext der Sitzung + `growth_tokens`, mindestens `clear_threshold_tokens`, Default 100.000 Token, nur im Modus manual) den Skill `60-validate` NICHT selbst aufrufen, sondern die Antwort mit dem Checkpoint und der ❗Du-Zeile `/60-validate #<N>` beenden — der Stand liegt auf der Platte, der PO tippt `/clear`. Bei `CONTEXT_STOP=off` (auch mit `CONTEXT_REASON=AUTO_NO_CLEAR`: Auto-Modus, niemand tippt `/clear`, Nachschlagen an Teilagenten abgeben, Claude Code komprimiert automatisch) oder `CONTEXT_TOKENS=unknown`: Kette unverändert selbst fortsetzen (#658).

Ohne `/clear` in derselben Session: Rufe den Skill `60-validate` jetzt sofort selbst
auf — warte nicht auf eine weitere User-Eingabe, das VERIFIED-Verdict des Adversary und
die GREEN-Freigabe `go` aus Step 6 sind bereits die Voraussetzung, keine zusätzliche
Entscheidung steht mehr aus.

Mit `/clear` dazwischen: Der Checkpoint-Block oben zeigt den regulären Wiedereinstieg
über den expliziten Befehl `/60-validate #<N>`.

## Common Mistakes

- Unrequested features, skipped tests, large functions
- Adversary oder User-Freigabe übersprungen -> BLOCKED
- Orchestrator schreibt Code selbst

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /50-implement · agent-os-openspec 4.26.1

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von drei Formen (es gibt keine vierte):

- `✅ Erledigt: <was>. Du kannst /clear ausführen und das nächste Issue starten.` — nur wenn der Workflow wirklich abgeschlossen ist.
- `⏳ Läuft noch: <worauf gewartet wird>. Du musst nichts tun, ich melde mich.` — du wartest auf CI, einen Hintergrund-Agenten oder einen Server.
- `❗ Du: …` (`❗ Du: <Schritt> — <warum>`), wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist immer ❗, nie ⏳.

Beendest du einen Turn, während du auf CI, Agent oder Server wartest, setze vorher `workflow.py waiting "<worauf>"` und gib die ⏳-Zeile aus; ist das Ergebnis da, `workflow.py waiting --clear`. Die passende Zeile liefert `workflow.py endstate [#<N>]` als `FOOTER=…` — gib sie wörtlich aus. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase geben den Stand AM ENDE dieser Nachricht wieder. Quelle ist der Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — aber nur, solange du die Phase in dieser Nachricht nicht selbst gewechselt hast. Hast du per `workflow.py phase <x>` (oder `complete`) gewechselt, beschreibt der Hinweis den Stand von Turn-Beginn; maßgeblich ist dann der neue Stand, den `workflow.py status` zeigt. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfällt die Statuszeile; die erste Zeile kommt dann aus `workflow.py endstate #<N>` und entfällt nur ohne Workflow. Die Marker-Zeilen entfallen NIE wegen eines Phasenwechsels; die ⚙-Zeile bleibt immer die letzte Zeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
