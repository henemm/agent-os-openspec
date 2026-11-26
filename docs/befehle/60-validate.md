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
