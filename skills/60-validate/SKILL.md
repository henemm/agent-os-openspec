---
description: "Validate the implementation"
disable-model-invocation: false
---

# Phase 7: Validation

You are in **Phase 7 - Validation**.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
_S="${_H%/core/hooks}/scripts"; [ "$_H" = ".claude/hooks" ] && _S=".claude/scripts"
```

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/60-validate #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — der komplette State überlebt jeden `/clear` und jeden Worktree:

```bash
$WF find 42   # die übergebene Nummer
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen). Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58):

```bash
$WF switch <NAME-aus-obigem-Output>
$WF status
```

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Verdict. Fasse dem User in 2 Sätzen den Stand zusammen (Phase, Verdict) und fahre dann mit den Prerequisites fort.

### Hängende Subagenten

Primärer Schutz gegen einen hängenden Subagenten: Die Sitzung wird automatisch erneut aufgerufen,
sobald der Hintergrund-Agent fertig ist. Liegt beim nächsten eigenen Zug noch kein Bericht vor,
`TaskList` prüfen — ist der Agent dort noch als aktiv gelistet, ihn mit `TaskStop` beenden und
mit präziserem Briefing neu starten. Kein endloses Warten.

Nur falls dieser Befehl innerhalb eines `/loop`-Laufs (Selbsttaktung, dynamischer Modus) läuft,
zusätzlich dieser Rückfall:

```
ScheduleWakeup(1200, "Validierung Rückfall [60-validate], nur im /loop-Kontext: TaskList → noch aktiver Kontext-/Validierungs-/Auto-Fix-/Docs-Updater-Agent? JA → TaskStop, dann User: 'Agent hängt — bitte /60-validate neu starten.' NEIN → ignorieren, fertig.")
```

### Kontext laden (nur bei Wiedereinstieg nach `/clear`)

Bevor du mit den Prerequisites fortfährst, lade den vollständigen Validierungs-Kontext — damit die nachfolgenden Agenten konkrete Werte statt Platzhalter erhalten.

Dispatche einen **Explore/Haiku Subagenten**:

```
Task (Explore/haiku, run_in_background: true): "Lies folgende Ressourcen und extrahiere die konkreten Werte:
  1. [spec_file aus dem Wiedereinstieg-Block oben] → Acceptance Criteria (AC-1 bis AC-N)
  2. docs/artifacts/<workflow-name>/adversary-dialog.md → Adversary-Verdict und Findings
  3. openspec.yaml (Feld test_command) → konkreter Test-Befehl

  Gib zurück:
  - spec_file_path: [konkreter Pfad, bereits aus Wiedereinstieg bekannt]
  - affected_files: [bereits aus Wiedereinstieg bekannt]
  - test_command: [konkreter Befehl]
  - Acceptance Criteria: [Liste aller AC-N]
  - adversary_verdict: [VERIFIED / BROKEN / AMBIGUOUS]"
```

Ersetze alle `[...]`-Platzhalter in Step 1 und Step 3 mit den geladenen Werten — kein Agent darf mit Platzhaltern gestartet werden.

## Prerequisites

- Implementation complete (`phase6_implement`)
- All tests passing (GREEN artifacts registered)
- **Adversary Dialog verified** (`phase6b_adversary` passed, `adversary_verdict` set)

Check status:
```bash
$WF status
```

### Adversary Dialog Prerequisite

**Du MUSST pruefen, dass der Adversary Dialog valid ist, bevor du fortfaehrst:**

```bash
python3 ${_H}/adversary_dialog.py validate docs/artifacts/<workflow-name>/adversary-dialog.md
```

Wenn die Validierung fehlschlaegt: Zurueck zu `/50-implement` Step 8 (Adversary Dialog wiederholen).
Akzeptierte Verdicts: **VERIFIED** oder **AMBIGUOUS** (mit User-OK).

**Gate-Wirkung (#253):** Commit-Gate und Phase 8 (`phase phase8_complete`, `complete`, `finish`)
akzeptieren das Verdict nur mit diesem registrierten (bzw. am Standardpfad liegenden), gestempelten
Artefakt, dessen gehashte Dateien zum aktuellen Code passen. Ein gruener Testlauf aktualisiert nur
`last_test_run` — er setzt kein Verdict. Aendert der Auto-Fix aus Step 2b eine im Dialog zitierte
Datei (`Code reference:`), blockt Phase 8, bis ein neuer Dialog gefuehrt, gestempelt und registriert
ist (`/50-implement` Step 8).

**Gate-Wirkung (#259):** Zusaetzlich muss der Hash-Block jede seit der Basis geaenderte Code-Datei
binden — `adversary_dialog.py required-files` listet genau diese Aenderungsmenge. Eine nicht zitierte
Code-Datei (etwa aus einem Fix nach dem Dialog) blockt Phase 8 ebenso wie eine geaenderte zitierte.

**Schon beim Wechsel nach Phase 7:** `workflow.py phase phase7_validate` prueft Verdict, registriertes
und gestempeltes Artefakt und Abdeckung bereits beim Eintritt in diese Phase, nicht erst bei Phase 8
oder beim Commit. Ergibt die Validierung BROKEN, bleibt der Ruecksprung `phase phase6_implement` frei.

## Your Tasks

### Step 1: Parallele Validierung (4x Haiku)

Dispatche **4 parallele Haiku-Agenten** fuer umfassende Validierung — alle vier in EINER Nachricht, dann laufen sie trotz Vordergrund parallel:

**Im Vordergrund starten (`run_in_background: false`, #83):** Das Ergebnis wird sofort gebraucht, der Orchestrator hat währenddessen nichts zu tun. Hintergrund-Starts kurzlebiger Prüfagenten ohne Worktree-Isolation kamen wiederholt ohne Bericht zurück — Nachfordern oder Doppelstart kostete jedes Mal eine volle Runde.

```
Task 1 (general-purpose/haiku, run_in_background: false) - TEST CHECK:
  "Fuehre ALLE Tests aus: [test_command]
  Report: Anzahl passed/failed, Laufzeit, Fehlerdetails."

Task 2 (general-purpose/haiku, run_in_background: false) - SPEC COMPLIANCE:
  "Lies die Spec: [spec_file_path]
  Pruefe jeden Acceptance Criterion gegen die Implementation.
  Report: Welche Kriterien sind erfuellt, welche nicht?"

Task 3 (general-purpose/haiku, run_in_background: false) - REGRESSION CHECK:
  "Fuehre die vollstaendige Test-Suite aus (nicht nur Feature-Tests).
  Report: Gibt es Regressionen? Welche Tests die vorher gruen waren
  sind jetzt rot?"

Task 4 (general-purpose/haiku, run_in_background: false) - SCOPE CHECK:
  "Vergleiche die geaenderten Dateien mit der Spec.
  Wurden Dateien ausserhalb des Specs geaendert?
  Wurden mehr als 5 Dateien / 250 LoC geaendert?"
```

### Step 2: Ergebnis-Auswertung

Werte die 4 Reports aus:

**Step 2a: Alle Checks bestanden**
-> Weiter zu Step 3

**Step 2b: Fehler gefunden -> Auto-Fix nur fuer Nicht-Code (general-purpose/Sonnet)**

Auto-Fix darf nur Nicht-Code aendern (Doku, Tests, Config — Code im Sinne des TDD-Gates,
`is_gated_code_path`, ist tabu). **Braucht ein Fund eine Code-Aenderung, ist das kein Auto-Fix,
sondern der BROKEN-Pfad (#259):** zurueck zu `phase6_implement`, gezielter Fix per Developer Agent
(`/50-implement`), danach eine Adversary-Runde aus demselben Kontingent wie jedes BROKEN-Verdict
(Adversary-Limit in `CLAUDE.md`). Phase 8 erzwingt das ohnehin: ein Code-Fix aendert eine zitierte
Datei (Hash) oder eine nicht zitierte (Abdeckung).

Bei Nicht-Code-Fehlern dispatche einen **general-purpose/Sonnet Subagenten**:

```
Task (general-purpose/sonnet, run_in_background: true): "Folgende Validierungsfehler wurden gefunden:
  [Fehler-Liste aus den 4 Haiku-Reports]

  Behebe die Fehler. Beachte:
  - Nur die gemeldeten Fehler fixen, keine anderen Aenderungen
  - Keine Code-Dateien aendern (nur Doku, Tests, Config) — Code-Fix = BROKEN-Pfad
  - Scoping Limits einhalten
  - Tests nach dem Fix erneut ausfuehren"
```

Nach dem Fix: Dispatche die relevanten Haiku-Checks erneut zur Verifikation.

### Step 3: Dokumentation aktualisieren (docs-updater/Sonnet)

Bei erfolgreicher Validierung dispatche den **docs-updater**:

```
Task (general-purpose/sonnet, run_in_background: true): "Du bist der docs-updater Agent.

  Input:
  - changed_files: [Liste der geaenderten Dateien]
  - feature_summary: [Kurzbeschreibung]
  - spec_file_path: [Pfad zur Spec — NUR LESEN, kein Bearbeitungsziel]

  Aktualisiere alle betroffene Dokumentation.

  Die Spec-Datei selbst NICHT bearbeiten — der freigegebene Teil ist nach der
  Freigabe eingefroren (#230, #439)."
```

**Warum `spec_file_path` nur Lesekontext ist (#230, #439):** Das PO-Briefing ist per
Teil-Hash (`spec_frozen_sha256`) an den freigegebenen Teil der Spec gebunden. Ändert der
docs-updater ihn, bricht Step 4 (`phase phase8_complete`) mit „PO-Briefing ist veraltet"
ab. Deshalb gilt: Der freigegebene Teil ist eingefroren — `edit_gate.py` (Schritt 1d)
blockiert solche Schreibzugriffe technisch, auch mit „override". Bewegliche Teile
(Frontmatter, Approval, Implementation Details, Known Limitations, Test Plan, Changelog,
`- Test:`-Zeilen) bleiben änderbar. Eine gewollte Änderung am Freigegebenen geht nur über
`workflow.py phase phase3_spec`, neues Briefing und neue Freigabe.

### Step 4: Workflow State aktualisieren

```bash
$WF phase phase8_complete
```

## Validation Report

Erstelle eine Zusammenfassung:

```markdown
## Validation Report: [Workflow Name]

### Test Results
- Unit Tests: [N] passed, [N] failed, [N] übersprungen
- Integration Tests: [N] passed, [N] failed, [N] übersprungen
- Full Suite: [N] total, [N] passed, [N] übersprungen
- Ein Lauf mit 0 bestanden und ≥ 1 übersprungen ist nicht grün.

### Spec Compliance
- Acceptance Criteria: [N]/[N] erfuellt
- [Details zu nicht-erfuellten Kriterien]

### Regression Check
- Status: [Keine Regressionen / N Regressionen]

### Scope Check
- Files changed: [N] (Limit: 5)
- LoC changed: +[N]/-[N] (Limit: 250)
- Out-of-scope changes: [Keine / Liste]

### Result: PASS / FAIL
```

## Next Step

### Autonomen Weiterlauf prüfen (PFLICHT, vor der Ausgabe)

Existiert im Projekt ein `/70-deploy` (eigene `.claude/commands/70-deploy.md` oder Skill) UND
steht in der Projekt-Config `deploy.autonomous: true` (Ausgabe von
`$WF deploy-config`) — oder dokumentiert das Projekt selbst, in
dessen `CLAUDE.md` oder direkt in `70-deploy.md`, explizit, dass Deploy **ohne Freigabe-Halt
autonom** läuft (Formulierungen wie "läuft
autonom", "kein Freigabe-Halt", "ohne manuelle Ausführung")? Dann ist das bindende
Projekt-Policy — nicht erneut zur Diskussion stellen und nicht darauf warten, dass der
User `/70-deploy` selbst eintippt. Das gilt auch dann, wenn "eigentlich" an dieser Stelle
generell auf eine Bestätigung gewartet wird: eine explizite Projekt-Policy sticht die
Default-Ceremony dieses Commands. Committe wie unten beschrieben und rufe danach
`/70-deploy` **im selben Turn selbst auf** — melde dem User das Ergebnis der ganzen Kette,
nicht einen Zwischenstand, der auf seine Eingabe wartet.

Fehlt eine solche explizite Projekt-Policy: Standardverhalten unten (fragen, nicht
autonom weiterlaufen) — Autonomie ist ein Opt-in des Projekts, kein Default des Frameworks.

### Beobachtbare Oberfläche prüfen (PFLICHT, vor der Ausgabe)

Diese Prüfung ersetzt die Autonomie-Prüfung oben nicht, sie tritt daneben. Führe sie aus —
**keine eigene Einschätzung von dir ersetzt den Aufruf**, auch dann nicht, wenn du sicher zu
wissen glaubst, dass nur Hooks oder Tests geändert wurden:

```bash
$WF observable-surface
```

Die Auskunft endet immer mit Rückgabecode 0 und nennt in fünf Zeilen Urteil (`OBSERVABLE_SURFACE=`),
Begründung, Anzahl geprüfter Dateien, Messwurzel und Config-Quelle.

Fehlt in dieser Ausgabe die Zeile `OBSERVABLE_SURFACE=no` — aus welchem Grund auch immer, also
auch bei `OBSERVABLE_SURFACE=yes`, bei einem Absturz, bei abweichendem Format oder wenn der
Aufruf ganz ausgeblieben ist —, dann gilt das als „Oberfläche vorhanden" und die Schlussfrage
„Soll ich den Code committen?" wird gestellt. Nur die ausdrücklich gelesene Zeile
`OBSERVABLE_SURFACE=no` lässt sie entfallen.

Daraus ergeben sich vier Kombinationen — die Autonomie-Regel sticht, die neue Prüfung wirkt in
genau einer Zeile:

| Oberfläche | Autonomie dokumentiert | Schlusszeile |
|---|---|---|
| `yes` | nein | Frage „Soll ich den Code committen?" — unverändert wie bisher |
| `yes` | ja | Ankündigung: schreibe fest und deploye, Kette im selben Turn |
| `no` | nein | Ankündigung: schreibe jetzt fest, keine Rückfrage |
| `no` | ja | Ankündigung: schreibe fest und deploye, Kette im selben Turn |

### Auto-Modus prüfen (PFLICHT, vor der Ausgabe, #472)

```bash
$WF autonomy
```

Nur die ausdrücklich gelesene Zeile `AUTONOMY=auto` schaltet um; jede andere Ausgabe (auch ein
Fehler) gilt als `manual` — dann gilt die Tabelle oben unverändert.

Bei `AUTONOMY=auto` (nach Step 4, also mit `phase8_complete`):

1. **`auto-ship` prüfen (#525)** — vor dem Commit, denn davon hängt Punkt 2 ab:

   ```bash
   $WF auto-ship
   ```

   Nur die ausdrücklich gelesene Zeile `AUTO_SHIP=on` schaltet um; jede andere Ausgabe (auch ein
   Fehler) gilt als `AUTO_SHIP=off`. Default im Auto-Modus ist an; abschalten per
   `autonomy.ship: false` in der Projekt-`config.yaml` (`settings.local.json` zählt nicht).
2. **Committen ohne Rückfrage** — unabhängig von `OBSERVABLE_SURFACE`; die Frage „Soll ich den
   Code committen?" entfällt. Die Commit-Gates (`bash_gate.py`) gelten wie immer.
   Bei `AUTO_SHIP=on`: Steht der Checkout auf `main`, `master`, dem Default-Branch des Remotes
   (ermittelt wie in Punkt 3) oder einem detached `HEAD`, legst du VOR dem Commit einen
   Feature-Branch mit dem Workflow-Namen an (`git switch -c <workflow-name>`). Existiert der Name
   schon lokal oder auf dem Remote, wird `-2`, `-3` und so weiter angehängt. Der lokale Default-Branch
   wird nie zurückgesetzt (kein `reset`, kein `--force`). Bei `AUTO_SHIP=off` gilt der Text oben
   unverändert.
3. **Den Feature-Branch pushen** — Branch prüfen mit `git rev-parse --abbrev-ref HEAD` und den
   Default-Branch des Remotes ermitteln: zuerst `git symbolic-ref --short refs/remotes/origin/HEAD`
   (z. B. `origin/main` → `main`); schlägt das fehl, `git ls-remote --symref origin HEAD` und die
   Zeile `ref: refs/heads/<name>` auswerten. Gepusht wird nur, wenn der aktuelle Branch weder
   `main` noch `master` noch der Default-Branch des Remotes ist: dann
   `git push -u origin <feature-branch>`. Schlagen beide Wege fehl, gilt: bei `AUTO_SHIP=off` wird
   wie bisher nicht gepusht und das in der Abschlussmeldung gemeldet; bei `AUTO_SHIP=on` wird
   ebenfalls nicht gepusht und das Problem in Alltagssprache gemeldet (etwa „Der Server war nicht
   erreichbar, ausgeliefert wird später“), nie als Git-Auftrag an den PO.
   Nie `main`, `master` oder den Default-Branch pushen (auch kein detached `HEAD`), nie
   `--force`. Nur bei `AUTO_SHIP=off` gilt: steht der Checkout darauf, wird nur committet und der
   PO in der Abschlussmeldung darauf hingewiesen. Schlägt der Push fehl, melden statt umgehen.
   **Ein Aufruf statt vieler (Kontext-Haushalt):** `python3 ${_S}/ship.py` erledigt Punkt 3
   und Punkt 5 in einem Schritt: Branch prüfen (nie Default-Branch, nie detached `HEAD`; mit
   `--branch <workflow-name>` legt es den Feature-Branch aus Punkt 2 an, bei Namenskonflikt mit
   Suffix `-2`, `-3` …), `git push -u origin <feature-branch>`, PR anlegen oder den offenen PR
   wiederverwenden, CI abwarten und bei `AUTO_SHIP=on` mit `--merge squash` (bzw. der im Repo
   üblichen Methode) mergen. Zurück kommen nur wenige Zeilen `BRANCH=… PR=… CI=green|red|none
   MERGED=yes|no|skipped`; bei `CI=red` nennt `FAILED_CHECKS=` die roten Checks — dann gilt Punkt 5
   (Ursache beheben oder in Alltagssprache melden). Die Regeln dieses Abschnitts (nie `--force`,
   nie Schutzregeln umgehen, rote CI nie überbrücken) gelten im Skript genauso; bei `AUTO_SHIP=off`
   ohne `--merge` aufrufen.
4. **Deploy bleibt beim PO.** Der Auto-Modus löst nie ein Deploy aus —
   `deploy.autonomous` (siehe „Autonomen Weiterlauf prüfen" oben) ist eine eigene, getrennte
   Entscheidung des Projekts und wird von `AUTONOMY=auto` weder gesetzt noch ersetzt. Kein
   `/70-deploy` aus dem Auto-Modus heraus.
5. **Ausliefern (Merge und PR, #525)** —
   **Bei `AUTO_SHIP=on` liefert Claude selbst aus:** Nach Punkt 2 und 3 im selben Turn den PR vom
   Feature-Branch auf den Default-Branch anlegen (PR-Vorlage des Repos beachten), die CI abwarten
   (PR-Aktivität abonnieren statt Polling, wo verfügbar) und bei grüner CI und konfliktfreiem PR
   mergen, mit der im Repo üblichen Methode (an der Historie des Default-Branchs ablesbar, im
   Zweifel Squash); danach den Feature-Branch auf den neuen Stand bringen. Merge-Konflikt:
   Default-Branch in den Feature-Branch mergen, Konflikt lösen, Tests erneut laufen lassen, wieder
   warten. Bei roter CI die Ursache suchen und beheben (ein Code-Fix zählt wie BROKEN: zurück zu
   `phase6_implement`) oder, wenn nicht aus diesem Änderungssatz behebbar, das Problem in
   Alltagssprache melden. Hat das Repo keine CI-Checks, wird auf Basis der grünen lokalen
   Testsuite aus Phase 7 gemergt. Schutzregeln (Pflicht-Reviews, Branch-Protection) werden nie
   umgangen, nie `--force`, rote CI nie überbrücken; verhindert eine Schutzregel den Merge, lautet
   die Meldung „wartet auf Prüfung durch einen Techniker“. Auch ohne Zugang zu Remote oder GitHub:
   in Alltagssprache melden, nie ein Git-Auftrag an den PO. Die Abschlussmeldung nennt dem PO
   keinen Git-Schritt, auch nicht für den neu angelegten Branch.
   **Bei `AUTO_SHIP=off`** gilt unverändert:
   **Merge und PR — Git-Policy des Projekts sticht:** Steht in der `CLAUDE.md` des Projekts
   (oder in der Memory), dass Claude Git und Auslieferung selbst erledigt (Formulierungen wie
   „Git entscheidet Claude selbst“, „bis `main` ausliefern“, „PO will mit Git nichts zu tun haben“),
   dann ist das bindend: Du legst den PR an, wartest die CI ab und lieferst nach den dort
   beschriebenen Regeln (z. B. Vorspulen) selbst auf den Default-Branch aus, im selben Turn, und
   meldest nur das Ergebnis. Das Verbot aus Punkt 3 (nie `main` pushen) gilt dann nur so weit,
   wie die Projektregel den Weg nicht ausdrücklich vorgibt; nie `--force`, nie Schutzregeln
   umgehen, rote CI nie überbrücken. Auch ohne ausdrückliche Policy liegen PR und Merge beim Tech Lead
   (Claude), nie beim PO (PO-Vorgabe 2026-11-08): PR anlegen, CI abwarten, bei grün mergen und
   dem PO nur das Ergebnis melden.
6. **Automatische Freigaben auflisten** — für die Abschlussmeldung:

   ```bash
   $WF approvals --auto
   ```

   Erste Zeile `APPROVALS=<n>`, danach je Eintrag `- <gate> | <by> | <at> | <reason>`. Übernimm
   jede Zeile als Gate, Zeit und Grund in die Abschlussmeldung; bei `APPROVALS=0` schreibe
   „keine automatischen Freigaben".

Immer menschlich bleiben — auch bei `AUTONOMY=auto`: AMBIGUOUS-Verdict, zweites BROKEN bzw. Circuit Breaker, Override, Deploy, Stop-Lock.

### Zusammenfassung an den User

Nach erfolgreicher Validierung, gib dem User folgende Zusammenfassung:

---
✅ **Alles fertig und geprüft.**

**Was wurde umgesetzt:** [Feature/Bugfix in 1–2 Sätzen aus Nutzerperspektive]

**Ergebnis:**
- Alle Qualitätsprüfungen bestanden
- Alle Anforderungen aus dem Plan erfüllt
- Keine bestehenden Funktionen beeinträchtigt

**Bereit für:** Commit[, dann Deploy — falls im Projekt vorgesehen]

Soll ich den Code committen?

---

**Ausnahme bei dokumentierter Autonomie (siehe Prüfung oben):** Ersetze die letzte Zeile
durch die kurze Ankündigung, dass jetzt committet und automatisch weiterdeployt wird —
keine Frage, keine Wartezeile wie "Warte auf /70-deploy". Führe die Kette im selben Turn
aus und melde danach das Endergebnis.

**Ausnahme ohne beobachtbare Oberfläche (siehe Prüfung oben):** Liegt die Zeile
`OBSERVABLE_SURFACE=no` vor und ist keine Autonomie dokumentiert, ersetze die letzte Zeile
durch die kurze Ankündigung, dass du den Code jetzt festschreibst. Es gibt in diesem Fall
nichts, was der User beurteilen könnte — eine Rückfrage wäre inhaltsleer.

**Ausnahme im Auto-Modus (`AUTONOMY=auto`, siehe Prüfung oben):** Committe und pushe den
Feature-Branch im selben Turn und ersetze die letzte Zeile durch das Ergebnis plus den Block —
keine Commit-Frage.

Bei `AUTO_SHIP=on` (Claude hat ausgeliefert, siehe Punkt 5):

```
**Ergebnis:** <PR-Link> · gemergt ja/nein · <Merge-Commit>   (sonst in Alltagssprache, warum nicht)
**Automatisch freigegeben:**
- <Gate> · <Zeit> · <Grund>     (je Zeile aus `workflow.py approvals --auto`)
```

Die ❗Du-Zeile nennt nie einen Git-Schritt (PR, Merge, Push, Branch, Commit); die
Endzustand-Zeile kommt ausschließlich aus `workflow.py endstate` (siehe „Abschluss:
Endzustand melden“).

Bei `AUTO_SHIP=off` (Ergebnis: Commit-Hash, gepushter Branch):

```
**Automatisch freigegeben:**
- <Gate> · <Zeit> · <Grund>     (je Zeile aus `workflow.py approvals --auto`)
```

Die Endzustand-Zeile nennt auch hier nie einen Git-Schritt (PR, Merge, Push, Branch, Commit) —
das erledigt Claude, siehe Punkt 5.

### Abschluss: Endzustand melden (Pflicht, #550)

Nach `complete` ist der Workflow archiviert; die Endzustand-Zeile kommt trotzdem aus derselben
Quelle wie Plan und Seitenleiste:

```bash
$WF endstate <N>
```

`ENDSTATE=done|waiting|you` nennt die Art, `FOOTER=` die fertige Zeile. Gib den Wert hinter
`FOOTER=` **wörtlich** als Endzustand-Zeile aus — genau eine der drei Formen `✅ Erledigt: …`,
`⏳ Läuft noch: …` oder `❗ Du: … — …`. Erfinde keine Aufgabe für den PO (keine „Abnahme“, kein
„Deploy“, wenn `endstate` es nicht nennt) und keine zweite Abschlusszeile. Wartest du danach
noch auf CI, einen Agenten oder einen Server: vorher `workflow.py waiting "<worauf>" <N>`, dann
`endstate` erneut aufrufen.

Kette bei offenem Auftrag (#551): Steht nach `endstate` `ENDSTATE=waiting` und meldet
`$WF queue` ein `NEXT=M`, gib die ⏳-Zeile aus und rufe danach
`/00-intake #M` selbst auf (autarker Auftrag) — kein Halt für `/clear`. Bei `ENDSTATE=you`
(Auftrag nicht autark) gib die ❗-Zeile wörtlich aus und warte auf den PO.

## On Failure

If validation fails after auto-fix attempt:
1. Do NOT update state to complete
2. Report the remaining issues to the user
3. User decides: fix manually or re-implement

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /60-validate · agent-os-openspec 4.8.0

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von drei Formen (es gibt keine vierte):

- `✅ Erledigt: <was>. Du kannst /clear ausführen und das nächste Issue starten.` — nur wenn der Workflow wirklich abgeschlossen ist.
- `⏳ Läuft noch: <worauf gewartet wird>. Du musst nichts tun, ich melde mich.` — du wartest auf CI, einen Hintergrund-Agenten oder einen Server.
- `❗ Du: …` (`❗ Du: <Schritt> — <warum>`), wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist immer ❗, nie ⏳.

Beendest du einen Turn, während du auf CI, Agent oder Server wartest, setze vorher `workflow.py waiting "<worauf>"` und gib die ⏳-Zeile aus; ist das Ergebnis da, `workflow.py waiting --clear`. Die passende Zeile liefert `workflow.py endstate [#<N>]` als `FOOTER=…` — gib sie wörtlich aus. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase geben den Stand AM ENDE dieser Nachricht wieder. Quelle ist der Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — aber nur, solange du die Phase in dieser Nachricht nicht selbst gewechselt hast. Hast du per `workflow.py phase <x>` (oder `complete`) gewechselt, beschreibt der Hinweis den Stand von Turn-Beginn; maßgeblich ist dann der neue Stand, den `workflow.py status` zeigt. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfällt die Statuszeile; die erste Zeile kommt dann aus `workflow.py endstate #<N>` und entfällt nur ohne Workflow. Die Marker-Zeilen entfallen NIE wegen eines Phasenwechsels; die ⚙-Zeile bleibt immer die letzte Zeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.
