# Hintergrund zu /60-validate

Begründungen und Sonderfälle zu core/commands/60-validate.md; der Befehlstext enthält Ablauf und Pflichtschritte.

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

Der komplette State überlebt jeden `/clear` und jeden Worktree.

Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58).

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Verdict.

## Hängende Subagenten

Primärer Schutz gegen einen hängenden Subagenten: Die Sitzung wird automatisch erneut aufgerufen,
sobald der Hintergrund-Agent fertig ist. Liegt beim nächsten eigenen Zug noch kein Bericht vor,
`TaskList` prüfen — ist der Agent dort noch als aktiv gelistet, ihn mit `TaskStop` beenden und
mit präziserem Briefing neu starten. Kein endloses Warten.

Nur falls dieser Befehl innerhalb eines `/loop`-Laufs (Selbsttaktung, dynamischer Modus) läuft,
zusätzlich der Rückfall aus dem Befehlstext; er gilt für jeden noch aktiven
Kontext-/Validierungs-/Auto-Fix-/Docs-Updater-Agent.

## Kontext laden (nur bei Wiedereinstieg nach `/clear`)

Bevor du mit den Prerequisites fortfährst, lade den vollständigen Validierungs-Kontext — damit die nachfolgenden Agenten konkrete Werte statt Platzhalter erhalten.

Ursprünglicher Auftrag an den Explore-Agenten:

```
  Lies folgende Ressourcen und extrahiere die konkreten Werte:
  1. [spec_file aus dem Wiedereinstieg-Block oben] → Acceptance Criteria (AC-1 bis AC-N)
  2. docs/artifacts/<workflow-name>/adversary-dialog.md → Adversary-Verdict und Findings
  3. config.yaml (Feld qa_gate.test_command) → konkreter Test-Befehl

  Gib zurück:
  - spec_file_path: [konkreter Pfad, bereits aus Wiedereinstieg bekannt]
  - affected_files: [bereits aus Wiedereinstieg bekannt]
  - test_command: [konkreter Befehl]
  - Acceptance Criteria: [Liste aller AC-N]
  - adversary_verdict: [VERIFIED / BROKEN / AMBIGUOUS]
```

Ersetze alle `[...]`-Platzhalter in Step 1 und Step 3 mit den geladenen Werten — kein Agent darf mit Platzhaltern gestartet werden.

## Prerequisites

- Implementation complete (`phase6_implement`)
- All tests passing (GREEN artifacts registered)
- **Adversary Dialog verified** (`phase6b_adversary` passed, `adversary_verdict` set)

## Adversary Dialog Prerequisite

**Du MUSST pruefen, dass der Adversary Dialog valid ist, bevor du fortfaehrst.**

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

## Step 1: Parallele Validierung (4x Haiku)

Dispatche **4 parallele Haiku-Agenten** fuer umfassende Validierung — alle vier in EINER Nachricht, dann laufen sie trotz Vordergrund parallel.

**Im Vordergrund starten (`run_in_background: false`, #83):** Das Ergebnis wird sofort gebraucht, der Orchestrator hat währenddessen nichts zu tun. Hintergrund-Starts kurzlebiger Prüfagenten ohne Worktree-Isolation kamen wiederholt ohne Bericht zurück — Nachfordern oder Doppelstart kostete jedes Mal eine volle Runde.

## Step 2: Ergebnis-Auswertung

Auto-Fix darf nur Nicht-Code aendern (Doku, Tests, Config — Code im Sinne des TDD-Gates,
`is_gated_code_path`, ist tabu). **Braucht ein Fund eine Code-Aenderung, ist das kein Auto-Fix,
sondern der BROKEN-Pfad (#259):** zurueck zu `phase6_implement`, gezielter Fix per Developer Agent
(`/50-implement`), danach eine Adversary-Runde aus demselben Kontingent wie jedes BROKEN-Verdict
(Adversary-Limit in `CLAUDE.md`). Phase 8 erzwingt das ohnehin: ein Code-Fix aendert eine zitierte
Datei (Hash) oder eine nicht zitierte (Abdeckung).

**Nachprüfung nach Phase 8 (Staging/live, #561):** Ein fachlicher Befund (eine AC ist ausgeliefert
nicht erfuellt, nicht die Infrastruktur) zaehlt genauso wie BROKEN: `deploy-status failed --note`,
zurueck zu `phase6_implement`, Fix per `/50-implement`, eine Adversary-Runde aus demselben
Kontingent, danach erneut `/60-validate` und `/70-deploy` (Ablauf in `/70-deploy` Step 4, Teil b). Kein
Korrektur-PR am Workflow vorbei.

Ursprünglicher Auftrag an den Auto-Fix-Agenten:

```
  Folgende Validierungsfehler wurden gefunden:
  [Fehler-Liste aus den 4 Haiku-Reports]

  Behebe die Fehler. Beachte:
  - Nur die gemeldeten Fehler fixen, keine anderen Aenderungen
  - Keine Code-Dateien aendern (nur Doku, Tests, Config) — Code-Fix = BROKEN-Pfad
  - Scoping Limits einhalten
  - Tests nach dem Fix erneut ausfuehren
```

## Step 3: Dokumentation aktualisieren (docs-updater/Sonnet)

Der **docs-updater** ist ein eigener Agent-Typ (Projekt-Agent in `.claude/agents/`, lokal auch als Plugin-Agent), Start **ohne `model`**, das Modell steht im Frontmatter (#577).

**Warum `spec_file_path` nur Lesekontext ist (#230, #439):** Das PO-Briefing ist per
Teil-Hash (`spec_frozen_sha256`) an den freigegebenen Teil der Spec gebunden. Ändert der
docs-updater ihn, bricht Step 4 (`phase phase8_complete`) mit „PO-Briefing ist veraltet"
ab. Deshalb gilt: Der freigegebene Teil ist eingefroren — `edit_gate.py` (Schritt 1d)
blockiert solche Schreibzugriffe technisch, auch mit „override". Bewegliche Teile
(Frontmatter, Approval, Implementation Details, Known Limitations, Test Plan, Changelog,
`- Test:`-Zeilen) bleiben änderbar. Eine gewollte Änderung am Freigegebenen geht nur über
`workflow.py phase phase3_spec`, neues Briefing und neue Freigabe.

## Step 4: Workflow State aktualisieren

Phase 8 heißt nur **„Code fertig“**: Der Wechsel vermerkt `ship_status: open`, und Plan,
Fußzeile und Seitenleiste zeigen ab jetzt den Schritt **Ausliefern** (Commit, Push, PR, CI,
Merge) als offen — nicht ✅. Erst `ship-status done` (oder `skipped`) macht den Workflow
fertig. `scripts/ship.py` meldet die Stände selbst (`running` beim Push, `done` nach dem
Merge, `failed` bei roter CI oder Konflikt); wer die Schritte einzeln ausführt, meldet sie
von Hand (`<N>` = Issue-Nummer, nach `complete` findet der Befehl den Workflow auch ohne
Nummer, solange die Auslieferung offen ist).

`skipped` nur, wenn es wirklich nichts auszuliefern gibt (kein Remote, direkt auf dem
Default-Branch committet bei `AUTO_SHIP=off`). Ein Turn, der mit `open` oder `running`
endet, zeigt dem PO ⏳ (Auto-Modus) bzw. ❗ „Sichern freigeben“ — nie ein falsches ✅.

## Validation Report

Ursprüngliche Gliederung der Abschnitte Spec Compliance, Regression Check und Scope Check:

```markdown
### Spec Compliance
- Acceptance Criteria: [N]/[N] erfuellt
- [Details zu nicht-erfuellten Kriterien]

### Regression Check
- Status: [Keine Regressionen / N Regressionen]

### Scope Check
- Files changed: [N] (Limit: 5)
- LoC changed: +[N]/-[N] (Limit: 250)
- Out-of-scope changes: [Keine / Liste]
```

## Autonomen Weiterlauf prüfen

Existiert im Projekt ein `/70-deploy` (eigene `.claude/commands/70-deploy.md` oder Skill) UND
steht in der Projekt-Config `deploy.autonomous: true` (Ausgabe von
`python3 .claude/hooks/workflow.py deploy-config`) — oder dokumentiert das Projekt selbst, in
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

## Beobachtbare Oberfläche prüfen

Diese Prüfung ersetzt die Autonomie-Prüfung oben nicht, sie tritt daneben. Führe sie aus —
**keine eigene Einschätzung von dir ersetzt den Aufruf**, auch dann nicht, wenn du sicher zu
wissen glaubst, dass nur Hooks oder Tests geändert wurden.

Die Auskunft endet immer mit Rückgabecode 0 und nennt in fünf Zeilen Urteil (`OBSERVABLE_SURFACE=`),
Begründung, Anzahl geprüfter Dateien, Messwurzel und Config-Quelle.

Fehlt in dieser Ausgabe die Zeile `OBSERVABLE_SURFACE=no` — aus welchem Grund auch immer, also
auch bei `OBSERVABLE_SURFACE=yes`, bei einem Absturz, bei abweichendem Format oder wenn der
Aufruf ganz ausgeblieben ist —, dann gilt das als „Oberfläche vorhanden" und die Schlussfrage
„Soll ich den Stand sichern?" wird gestellt. Nur die ausdrücklich gelesene Zeile
`OBSERVABLE_SURFACE=no` lässt sie entfallen.

Daraus ergeben sich vier Kombinationen — die Autonomie-Regel sticht, die neue Prüfung wirkt in
genau einer Zeile.

## Zusammenfassung an den User

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

## Abschluss: Endzustand melden

Nach `complete` ist der Workflow archiviert; die Endzustand-Zeile kommt trotzdem aus derselben
Quelle wie Plan und Seitenleiste.

`ENDSTATE=done|waiting|you` nennt die Art, `FOOTER=` die fertige Zeile, `SHIP_STATUS=` den
Stand der Auslieferung. Gib den Wert hinter `FOOTER=` **wörtlich** als Endzustand-Zeile aus —
genau eine der drei Formen `✅ Erledigt: …`, `⏳ Läuft noch: …` oder `❗ Du: … — …`. Erfinde
keine Aufgabe für den PO (keine „Abnahme“, kein „Deploy“, wenn `endstate` es nicht nennt) und
keine zweite Abschlusszeile. Steht `SHIP_STATUS=open` oder `running`, obwohl Push, PR und
Merge erledigt sind, fehlt dein `ship-status done` (Step 4) — erst melden, dann `endstate`
erneut. Wartest du danach noch auf CI, einen Agenten oder einen Server: `ship-status running
--note "<worauf>"` bzw. `workflow.py waiting "<worauf>" <N>`, dann `endstate` erneut aufrufen.

Im herdr-Workspace mit `#E` im Namen (#610) kommt der Vorschlag nur aus den offenen Kindern
von Epic E (in Plan-Reihenfolge, ohne Issues anderer Sitzungen); ist keines frei, nennt die
✅-Zeile keine Nummer und es folgen `SUGGEST_SOURCE=epic-leer`, `SUGGEST_EPIC=E` und
`SUGGEST_REASON=`: dann prüfst du das Abschlusskriterium des Epics, schlägst aber nie ein
Issue außerhalb vor.

Die Kette greift weiterhin nur bei „aus deinem Auftrag“ (bei einem
autarken Auftrag hängt `endstate` Epic-/Meilenstein-Nachfolger selbst an und meldet dann ⏳).

## Wiedereinstieg und Hängende Subagenten (Wortlaut vor #678)

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/60-validate #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf:

```bash
python3 .claude/hooks/workflow.py find 42   # die übergebene Nummer
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (ein reines `export` reicht NICHT):

```bash
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
```

Fasse dem User in 2 Sätzen den Stand zusammen (Phase, Verdict) und fahre dann mit den Prerequisites fort.

### Hängende Subagenten

Die Sitzung wird automatisch erneut aufgerufen, sobald der Hintergrund-Agent fertig ist. Fehlt beim
nächsten eigenen Zug der Bericht: `TaskList` prüfen, noch aktiv → `TaskStop`, mit präziserem Briefing
neu starten. Nur innerhalb eines `/loop`-Laufs zusätzlich:

```
ScheduleWakeup(1200, "Validierung Rückfall [60-validate], nur im /loop-Kontext: TaskList → noch aktiver Agent? JA → TaskStop, dann User: 'Agent hängt — bitte /60-validate neu starten.' NEIN → fertig.")
```

## Kontext laden (Wortlaut vor #678)

Dispatche einen **Explore/Haiku Subagenten**:

```
Agent(subagent_type="Explore", model="haiku", description="Validierungs-Kontext laden", run_in_background=true, prompt="
  Lies [spec_file] (AC-1 bis AC-N), docs/artifacts/<workflow-name>/adversary-dialog.md
  (Verdict, Findings) und config.yaml (qa_gate.test_command).
  Gib zurück: spec_file_path, affected_files, test_command, Liste aller AC-N,
  adversary_verdict (VERIFIED / BROKEN / AMBIGUOUS).")
```

Kein Agent darf mit `[...]`-Platzhaltern gestartet werden.

## Prerequisites und Adversary Dialog Prerequisite (Wortlaut vor #678)

Implementation complete, GREEN artifacts registered, **Adversary Dialog verified** (`adversary_verdict` set) — `python3 .claude/hooks/workflow.py status`.

### Adversary Dialog Prerequisite

**Pflicht vor allem Weiteren:**

```bash
python3 .claude/hooks/adversary_dialog.py validate docs/artifacts/<workflow-name>/adversary-dialog.md
```

Wenn die Validierung fehlschlaegt: Zurueck zu `/50-implement` Step 8 (Adversary Dialog wiederholen).
Akzeptierte Verdicts: **VERIFIED** oder **AMBIGUOUS** (mit User-OK).

## Step 1: Parallele Validierung (Wortlaut vor #678)

Dispatche **4 parallele Haiku-Agenten** im Vordergrund — alle vier in EINER Nachricht, dann laufen sie parallel:

```
Agent(subagent_type="general-purpose", model="haiku", description="TEST CHECK", run_in_background=false, prompt="
  Fuehre ALLE Tests aus: python3 .claude/hooks/qa_gate.py --run (ohne test_command: [test_command])
  Report: Anzahl passed/failed, Laufzeit, Fehlerdetails.")

Agent(subagent_type="general-purpose", model="haiku", description="SPEC COMPLIANCE", run_in_background=false, prompt="
  Lies die Spec: [spec_file_path]
  Pruefe jeden Acceptance Criterion gegen die Implementation.
  Report: Welche Kriterien sind erfuellt, welche nicht?")

Agent(subagent_type="general-purpose", model="haiku", description="REGRESSION CHECK", run_in_background=false, prompt="
  Fuehre die vollstaendige Test-Suite aus (nicht nur Feature-Tests).
  Report: Gibt es Regressionen? Welche Tests die vorher gruen waren
  sind jetzt rot?")

Agent(subagent_type="general-purpose", model="haiku", description="SCOPE CHECK", run_in_background=false, prompt="
  Vergleiche die geaenderten Dateien mit der Spec.
  Wurden Dateien ausserhalb des Specs geaendert?
  Wurden mehr als 5 Dateien / 250 LoC geaendert?")
```

## Step 2: Ergebnis-Auswertung (Wortlaut vor #678)

**Step 2a: Alle Checks bestanden** -> Weiter zu Step 3

**Step 2b: Fehler gefunden -> Auto-Fix nur fuer Nicht-Code (general-purpose/Sonnet)**

Auto-Fix darf nur Nicht-Code aendern (Doku, Tests, Config). **Braucht ein Fund eine Code-Aenderung,
ist das der BROKEN-Pfad:** zurueck zu `phase6_implement`, gezielter Fix per `/50-implement`, danach
eine Adversary-Runde aus demselben Kontingent wie jedes BROKEN-Verdict.

**Nachprüfung nach Phase 8 (Staging/live):** Ein fachlicher Befund zaehlt wie BROKEN:
`deploy-status failed --note`, zurueck zu `phase6_implement`, Fix per `/50-implement`, eine
Adversary-Runde aus demselben Kontingent, danach erneut `/60-validate` und `/70-deploy`.

Bei Nicht-Code-Fehlern dispatche einen **general-purpose/Sonnet Subagenten**:

```
Agent(subagent_type="general-purpose", model="sonnet", description="Auto-Fix Nicht-Code", run_in_background=true, prompt="
  Behebe nur diese Validierungsfehler: [Fehler-Liste aus den 4 Haiku-Reports]
  Keine Code-Dateien aendern (nur Doku, Tests, Config) — Code-Fix = BROKEN-Pfad.
  Scoping Limits einhalten, Tests danach erneut ausfuehren.")
```

Nach dem Fix: Dispatche die relevanten Haiku-Checks erneut zur Verifikation.

## Step 3: docs-updater-Auftrag (Wortlaut vor #678)

  spec_file_path: [Pfad zur Spec — NUR LESEN, kein Bearbeitungsziel]
  Aktualisiere alle betroffene Dokumentation.

  Die Spec-Datei selbst NICHT bearbeiten — der freigegebene Teil ist nach der
  Freigabe eingefroren (#230, #439).")

## Validation Report (Vorlage)

```markdown
## Validation Report: [Workflow Name]

### Test Results
- Unit Tests: [N] passed, [N] failed, [N] übersprungen
- Integration Tests: [N] passed, [N] failed, [N] übersprungen
- Full Suite: [N] total, [N] passed, [N] übersprungen
- Ein Lauf mit 0 bestanden und ≥ 1 übersprungen ist nicht grün.

### Spec Compliance / Regression / Scope
- Acceptance Criteria: [N]/[N] erfuellt [Details zu nicht erfuellten]
- Regressionen: [Keine / N]
- Files/LoC: [N] (Limit 5) / +[N]/-[N] (Limit 250), out-of-scope: [Keine / Liste]

### Result: PASS / FAIL
```

## Autonomen Weiterlauf prüfen (Wortlaut vor #678)

Existiert im Projekt ein `/70-deploy` UND steht `deploy.autonomous: true` in der Projekt-Config
(`python3 .claude/hooks/workflow.py deploy-config`) — oder dokumentiert das Projekt (`CLAUDE.md`,
`70-deploy.md`) explizit, dass Deploy **ohne Freigabe-Halt autonom** läuft? Dann ist das bindende
Projekt-Policy: committe wie unten beschrieben und rufe `/70-deploy` **im selben Turn selbst auf**;
melde das Ergebnis der ganzen Kette. Sonst Standardverhalten unten (fragen, nicht autonom weiterlaufen).

## Beobachtbare Oberfläche prüfen (Wortlaut vor #678)

Fehlt die Zeile `OBSERVABLE_SURFACE=no` (auch bei `yes`, Absturz, abweichendem Format oder
ausgebliebenem Aufruf), wird die Schlussfrage „Soll ich den Stand sichern?" gestellt. Nur die
ausdrücklich gelesene Zeile `OBSERVABLE_SURFACE=no` lässt sie entfallen. Die Autonomie-Regel sticht:

## On Failure (Wortlaut vor #678)

If validation fails after auto-fix attempt:
1. Do NOT update state to complete
2. Report the remaining issues to the user
3. User decides: fix manually or re-implement

## Auto-Modus Punkt 3: ship.py (Wortlaut vor #678)

   **Ein Aufruf statt vieler (Kontext-Haushalt):** `python3 .claude/scripts/ship.py` erledigt Punkt 3
   und Punkt 5 in einem Schritt: Branch prüfen (nie Default-Branch, nie detached `HEAD`; mit
   `--branch <workflow-name>` legt es den Feature-Branch aus Punkt 2 an, bei Namenskonflikt mit
   Suffix `-2`, `-3` …), `git push -u origin <feature-branch>`, PR anlegen oder den offenen PR
   wiederverwenden, CI abwarten und bei `AUTO_SHIP=on` mit `--merge squash` (bzw. der im Repo
   üblichen Methode) mergen. Zurück kommen nur wenige Zeilen `BRANCH=… PR=… CI=green|red|none
   MERGED=yes|no|skipped`; bei `CI=red` nennt `FAILED_CHECKS=` die roten Checks — dann gilt Punkt 5
   (Ursache beheben oder in Alltagssprache melden). Die Regeln dieses Abschnitts (nie `--force`,
   nie Schutzregeln umgehen, rote CI nie überbrücken) gelten im Skript genauso; bei `AUTO_SHIP=off`
   ohne `--merge` aufrufen.

## Zusammenfassung: Ausnahmen (Wortlaut vor #678)

**Ausnahmen (siehe Prüfungen oben):** Bei dokumentierter Autonomie oder ohne beobachtbare
Oberfläche ersetzt die Ankündigung aus der Tabelle die letzte Zeile, ohne Frage. Im Auto-Modus
(`AUTONOMY=auto`): ersetze die letzte Zeile durch das Ergebnis plus den Block — keine Commit-Frage.

## Vorschlag (#589) (Wortlaut vor #678)

Vorschlag (#589): Ohne nächstes Issue aus dem Auftrag nennt die ✅-Zeile hinter `FOOTER=` oft
schon die nächste Aufgabe („… mit /00-intake #M weitermachen (<Grund>).“); dann folgen
`SUGGEST_ISSUE=M`, `SUGGEST_SOURCE=epic|milestone|spur|related|priority` und `SUGGEST_REASON=`.
Bei `SUGGEST_SOURCE=epic-leer` prüfst du das Abschlusskriterium des Epics, schlägst aber nie ein
Issue außerhalb vor.
Das ist nur Auskunft für dich: gib die Zeile wörtlich aus und starte wegen eines bloßen
Vorschlags nichts selbst — die Kette greift weiterhin nur bei „aus deinem Auftrag“.

## Auto-Modus prüfen: Einleitung (Wortlaut vor #678)

Nur die ausdrücklich gelesene Zeile `AUTONOMY=auto` schaltet um; jede andere Ausgabe (auch ein
Fehler) gilt als `manual` — dann gilt die Tabelle oben unverändert.

## Auto-Modus Punkt 1: auto-ship (Wortlaut vor #678)

   Nur die ausdrücklich gelesene Zeile `AUTO_SHIP=on` schaltet um; jede andere Ausgabe (auch ein
   Fehler) gilt als `AUTO_SHIP=off`. Default im Auto-Modus ist an; abschalten per
   `autonomy.ship: false` in der Projekt-`config.yaml` (`settings.local.json` zählt nicht).

## Auto-Modus Punkt 6: approvals (Wortlaut vor #678)

   Erste Zeile `APPROVALS=<n>`, danach je Eintrag `- <gate> | <by> | <at> | <reason>`. Übernimm
   jede Zeile als Gate, Zeit und Grund in die Abschlussmeldung; bei `APPROVALS=0` schreibe
   „keine automatischen Freigaben".

## Endzustand melden (Wortlaut vor #678)

Gib den Wert hinter `FOOTER=` **wörtlich** als Endzustand-Zeile aus — genau eine der drei Formen
`✅ Erledigt: …`, `⏳ Läuft noch: …` oder `❗ Du: … — …`; keine erfundene PO-Aufgabe, keine zweite
Abschlusszeile. `SHIP_STATUS=open`/`running` trotz Auslieferung: erst `ship-status done` (Step 4).
Wartest du noch auf CI, Agent oder Server: `ship-status running --note "<worauf>"` bzw.
`workflow.py waiting "<worauf>" <N>`, dann `endstate` erneut aufrufen.

## Auto-Modus Punkt 4 (Wortlaut vor #678)

4. **Deploy bleibt beim PO.** Der Auto-Modus löst nie ein Deploy aus —
   `deploy.autonomous` (siehe „Autonomen Weiterlauf prüfen" oben) ist eine eigene, getrennte
   Entscheidung des Projekts und wird von `AUTONOMY=auto` weder gesetzt noch ersetzt. Kein
   `/70-deploy` aus dem Auto-Modus heraus.

## Auto-Modus Punkt 5: Versions-Bump (Wortlaut vor #678)

   **Versions-Bump bei Einzel-Auslieferung (#640):** Regelt das Projekt die Einzel-Auslieferung
   (im Framework-Repo `docs/arbeitsweise.md`), gilt beim Ausliefern dessen Regel: Wird ein Issue
   allein und sofort veröffentlicht, steckt der Versions-Bump schon im Fix- oder Feature-PR (ein
   einziger Testlauf bis zur veröffentlichten Version); ein getrennter Release-PR folgt nur beim
   Bündeln mehrerer Issues.

## Step 4: ship-status von Hand (Wortlaut vor #678)

Workflow fertig. `scripts/ship.py` meldet die Stände selbst; von Hand:

```bash
python3 .claude/hooks/workflow.py ship-status running <N> --note "PR <nr>: CI läuft"
python3 .claude/hooks/workflow.py ship-status done <N> --note "PR <nr> gemergt"
python3 .claude/hooks/workflow.py ship-status failed <N> --note "<Grund in Alltagssprache>"
python3 .claude/hooks/workflow.py ship-status skipped <N> --note "<warum nichts auszuliefern ist>"
```

`skipped` nur, wenn es wirklich nichts auszuliefern gibt.

## Kette bei offenem Auftrag: Übergabe (Wortlaut vor #678)

übergib #M an eine
frische Sitzung (Befehl `workflow.py handoff`, #667), kein Halt für `/clear`. Erst `python3 .claude/hooks/workflow.py handoff`,
dann je nach `HANDOFF=`:

## Auto-Modus Punkt 3: Beispiel Default-Branch (Wortlaut vor #678)

Default-Branch des Remotes ermitteln: zuerst `git symbolic-ref --short refs/remotes/origin/HEAD`
   (z. B. `origin/main` → `main`); schlägt das fehl, `git ls-remote --symref origin HEAD` und die
   Zeile `ref: refs/heads/<name>` auswerten.
