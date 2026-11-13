# Adversary Dialog — fix-597-autoclear-klartext
Spec: docs/specs/fix-597-autoclear-klartext.md
Datum: 2026-11-13 17:41

## Checkliste
- [x] **Input:** Auto-/clear aktiv, Phasenwechsel hat `auto_clear_boundary` gesetzt, Antwort endet mit `❗ Du: /<nächster> #N`; ein weiterer Stop-Hook (z. B. `klartext_gate`) weist die Antwort einmal zurück, Claude schreibt sie neu
- [x] **Output:** Nach der Neufassung (Folge-Stop, `stop_hook_active`) startet ein Runner, nimmt den Vermerk atomar und tippt genau einmal `/clear` und den Folgebefehl; ein früher gestarteter Runner bricht beim neueren Stop ab, ohne den Vermerk zu verwerfen
- [x] **Vorprüfung:** Würde `klartext_gate` die Antwort zurückweisen, startet `maybe_auto_clear` keinen Runner (Log `skip: Klartext-Prüfung weist die Antwort zurück`), der Vermerk bleibt
- [x] **Nutzer schreibt, Sitzung endet, Phase wechselt:** Abbruch, Vermerk verworfen, keine Wiederholung
- [x] **Side effects:** neue Sperrdatei `.claude/herdr_auto_clear.lock` (leer, im Hauptprojekt); keine `herdr_auto_clear_state.json` mehr; Runner-Log wie bisher (`ABBRUCH`/`OK`/`skip:`); Vorlagen-Texte ohne Git-Wörter
- [x] **AC-1:** Given alle `core/commands/*.md` und alle `skills/*/SKILL.md` / When jeder Block zwischen den `---`-Trennern nach einer Überschrift mit "Ausgabe" und jede deutsch zitierte Phrase („…“ bzw. „…") durch `klartext_gate.treffer` läuft / Then gibt es keinen einzigen Treffer; `skills/` stimmt nach `sync_skills.py` mit `core/commands` überein
- [x] **AC-2:** Given `klartext_gate.pruefe(payload)` / When Antwort Git-Wörter außerhalb von Code enthält, bzw. `OPENSPEC_KLARTEXT=0`, bzw. `stop_hook_active`, bzw. letzte Nutzernachricht enthält selbst Git-Wörter, bzw. kein Antworttext, bzw. Payload kein dict / Then liefert sie die Trefferliste bzw. in allen Ausnahmefällen `[]`, ohne Exception; `main` blockt unverändert mit Exit 2 und derselben Meldung nur bei Treffern
- [x] **AC-3:** Given Grenze passt, Antwort sauber, Payload mit `stop_hook_active: true` / When `footer_gate.py` (`maybe_auto_clear`) läuft / Then wird ein Runner gestartet (kein `skip: stop_hook_active`, Vermerk bleibt bis zum Tippen liegen)
- [x] **AC-4:** Given Grenze passt und die Antwort enthält Git-Wörter (`klartext_gate.pruefe` liefert Treffer) / When `maybe_auto_clear` läuft / Then wird kein Runner gestartet, das Log enthält `skip: Klartext-Prüfung weist die Antwort zurück` und der Vermerk ist unverändert vorhanden; bei Negativ-Marker oder veraltetem Vermerk bleibt das bisherige Verhalten (Vermerk verbraucht, Skip-Grund wie bisher)
- [x] **AC-5:** Given ein gültiger Vermerk / When ein Runner gespawnt wurde (noch vor dem Tippen) / Then liegt der Vermerk weiter im Workflow-State (kein Verbrauch beim Spawn) und es gibt keinen 600-s-Once-Lock (keine `herdr_auto_clear_state.json`, zwei Stops in Folge sind nicht per Sperre blockiert); der Spawn übergibt `--boundary-at` mit dem `at` des Vermerks
- [x] **AC-6:** Given zwei Runner für dieselbe Grenze starten gleichzeitig `_take_boundary` / When beide bis vor das Tippen kommen / Then bekommt genau einer den Vermerk (atomar unter flock), der andere bricht mit "Grenze bereits vergeben" ab ohne zu tippen; getippt wird `/clear` und der Folgebefehl insgesamt genau einmal
- [x] **AC-7:** Given `_take_boundary` / When der Vermerk fehlt, `phase`, `command` oder `at` nicht zu den Runner-Argumenten passen, der State nicht lesbar ist oder die Sperre fehlschlägt / Then liefert sie False, der State bleibt unverändert und der Runner tippt nichts
- [x] **AC-8:** Given Runner 1 im Wartefenster und ein neuerer Stop (`stop`-Signal nach seinem `since`), dann Runner 2 / When Runner 1 abbricht und Runner 2 weiterläuft / Then verwirft Runner 1 den Vermerk nicht ("Claude arbeitet weiter", Vermerk bleibt), Runner 2 nimmt ihn und tippt genau einmal `/clear` und den Folgebefehl; Log zeigt zuerst `ABBRUCH`, dann `OK`
- [x] **AC-9:** Given der Runner hat den Vermerk genommen, aber zwischen `send-text` und Enter trifft ein `stop`- oder `activity`-Signal ein / When er mit `ctrl+u` abbricht / Then wird der Vermerk zurückgelegt, aber nur, wenn im State kein (neuerer) Vermerk steht; ein vorhandener neuerer Vermerk wird nicht überschrieben
- [x] **AC-10:** Given Abbruch vor dem Abschicken von `/clear` durch Nutzereingabe ("Nutzer hat weitergeschrieben"), Sitzungsende/Neustart, Phasenwechsel/Befehl geändert, Herdr-Fehler oder Gesamt-Deadline / When der Runner abbricht / Then ist der Vermerk verworfen und es gibt keinen automatischen Neuversuch; nach abgeschicktem `/clear` bleibt der Vermerk verbraucht, `ABBRUCH` im Log
- [x] **AC-11:** Given die unveränderten Schutzfunktionen / When Berechtigungsdialog-Szenario (Aktivität/Stop nach der Referenz), `/99-reset`, zweimal falsche Fußzeile (`footer_gate._discard_boundary`), Negativ-Marker, veralteter Vermerk und Phasenwechsel in der Grace-Zeit laufen / Then verhalten sie sich wie vor der Änderung (kein Tippen bzw. Vermerk verworfen wie bisher); die angepassten Bestandstests (#467, #495, #497, #499, #506, #489, #480, #478) sind grün
- [x] **AC-12:** Given echtes Herdr mit Claude-TUI und ein fremder Stop-Hook, der genau einmal blockt (Szenario R) / When Claude die Antwort neu schreibt / Then erscheinen im TUI genau ein `❯ /clear` und genau ein Folgebefehl, das Log zeigt `ABBRUCH` des ersten und `OK` des zweiten Runners; Szenarien A, D, H, P, Q, S bleiben grün (lokal beim PO, nicht in CI)

## Dialog

### Runde 1
**Adversary:** Testlauf 105 passed (adversary-test-output.txt). Angriffe: (a) Race 6 Prozesse gleichzeitig auf `_take_boundary` mit echtem flock (Probe im Scratchpad race.py): genau 1 Gewinner, State ohne Vermerk, Sperrdatei leer — AC-6 PROVEN. (b) Tipp-Sicherheit: `/clear` wird erst nach `_check_activity` direkt vor dem Take und erneut zwischen send-text und Enter geprüft; Take misslingt bei Lockfehler, fehlendem fcntl, kaputtem State, Mismatch (alle Wege (False,None)) → kein Tippen. Code reference: core/hooks/herdr_bridge.py:1082. Szenario P (Berechtigungsdialog) greift unverändert über `activity`/`stop`-Signale (AC_CONTINUE_KINDS). (c) Vermerk-Lebenszyklus: `submitted` wird erst nach `_prompt` gesetzt (herdr_bridge.py:1086); Abbruch zwischen Text und Enter → continuation → Restore nur wenn kein Vermerk im State (herdr_bridge.py:886); Nutzereingabe → continuation=False → eigener Vermerk verworfen (herdr_bridge.py:907, nur gleiches `at`). (d) Klartext-Vorprüfung nach Vermerk-Existenz, vor jedem Verbrauch; `pruefe` fail-open (core/hooks/klartext_gate.py:137), `main` ruft nur `pruefe` und behält Meldung/Exit-Codes (Diff geprüft). (e) AC-1: eigene Gegenprobe über alle `---`-Blöcke aller Vorlagen: verbleibende Git-Wörter nur in Anweisungstext (50-implement, 60-validate Auto-Modus, 82-test Regeln), nicht in Ausgabeblöcken; Test enthält Selbstprüfung gegen Leerlauf. Zu den Abweichungen: (1)-(3) und (5) plausibel, Testlauf grün; (4) richtig, da Verbrauchsfälle (Negativ/veraltet) sonst ihren Skip-Grund verlören.
**Implementierer:** keine Rückfrage nötig (Diff und Tests liegen vor).

### Runde 2
**Adversary:** Tiefere Angriffe. F001: `_take_boundary` vergleicht `at`, ISO-Zeitstempel mit Mikrosekunden (workflow.py:1413), Kollision praktisch ausgeschlossen. F002: Runner 1 bricht nach Nutzereingabe zwischen Stop 1 und Stop 2 mit continuation=False ab und verwirft den Vermerk, den Runner 2 (neuerer sauberer Stop) noch bräuchte; Runner 2 meldet "Grenze bereits vergeben", kein /clear. Entspricht AC-10 (Nutzereingabe verwirft), daher kein Spec-Bruch, aber Missed-Clear möglich. F003: ist das Framework im Kopiermodus ohne registrierten `klartext_gate` (setup.py registriert ihn nicht), unterdrückt die Vorprüfung das /clear bei Antworten mit Git-Wörtern, obwohl niemand neu schreiben lässt (Vermerk bleibt 15 min). Randfall, LOW. F004: Take-/Restore-Schreibzugriffe serialisieren nur Runner untereinander; `footer_gate._consume_boundary` und workflow.py schreiben ohne diese Sperre (Lost-Update-Fenster Millisekunden, wie vor der Änderung). Nicht blockierend. Fail-open: Exceptions in `maybe_auto_clear` sind komplett gefangen (herdr_bridge.py:515 ff.), `_klartext_hits` fängt Import-/Laufzeitfehler (herdr_bridge.py:580); `_with_token_lock` fängt SystemExit/Exception, 10-s-Lock-Timeout → kein Tippen, Sperre immer freigegeben. Liegengebliebener Vermerk: höchstens 15 min, phasen- und befehlsgebunden (`_boundary_matches`, `_boundary_fresh`) → in späterer Phase kein Fehlauslösen; im selben Phase-Zustand zieht er bei nächstem sauberem Stop absichtlich ("neuester Stop gewinnt").
**Implementierer:** keine Antwort nötig.

### Findings
Finding:
  ID: F002
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/herdr_bridge.py:924
  Description: settle_boundary verwirft bei nicht-continuation-Abbruch (z. B. Nutzereingabe nach Stop 1) den Vermerk, auch wenn ein Runner 2 eines neueren sauberen Stops ihn noch bräuchte.
  Spec requirement: AC-10 — Nutzereingabe verwirft den Vermerk
  Conflict: kein Bruch; mögliches ausbleibendes /clear nach Nutzereingabe, die Claude danach sauber beantwortet.
  Remediation: akzeptieren (Spec-konform) oder dokumentieren.

Finding:
  ID: F003
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/herdr_bridge.py:580
  Description: _klartext_hits wird auch ohne registrierten klartext_gate-Hook ausgewertet; Antworten mit Git-Wörtern lösen dann nie ein Auto-/clear aus.
  Spec requirement: AC-4 — Vorprüfung nur sinnvoll, wenn ein Folge-Stop kommt
  Conflict: Randfall im Kopiermodus (setup.py ohne klartext_gate).
  Remediation: optional; klartext_gate in setup.py registrieren (Bestandslücke aus #582).

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

Confirmation:
  AC: AC-1
  Code reference: tests/test_vorlagen_klartext_597.py:70
  Evidence: Parser-Selbstprüfung plus Test über alle Vorlagen grün; eigene Gegenprobe ohne Git-Wörter in Ausgabeblöcken.
  Status: CONFIRMED

Confirmation:
  AC: AC-2
  Code reference: core/hooks/klartext_gate.py:137
  Evidence: pruefe liefert [] in allen Ausnahmefällen mit try/except; main nutzt es unverändert (Exit 2 nur bei Treffern); test_klartext_gate_582 grün.
  Status: CONFIRMED

Confirmation:
  AC: AC-3, AC-4, AC-5
  Code reference: core/hooks/herdr_bridge.py:515
  Evidence: kein stop_hook_active-Skip mehr, Vorprüfung vor Verbrauch, Spawn ohne Verbrauch mit --boundary-at (herdr_bridge.py:445), kein Once-Lock; test_autoclear_retry_597 grün.
  Status: CONFIRMED

Confirmation:
  AC: AC-6, AC-7
  Code reference: core/hooks/herdr_bridge.py:863
  Evidence: Race-Probe 6 Prozesse: genau 1 Gewinner; Mismatch/Lockfehler → False, State unverändert.
  Status: CONFIRMED

Confirmation:
  AC: AC-8, AC-9
  Code reference: core/hooks/herdr_bridge.py:886
  Evidence: Restore nur ohne vorhandenen Vermerk ("newer" bleibt); continuation-Abbruch lässt Vermerk liegen.
  Status: CONFIRMED

Confirmation:
  AC: AC-10, AC-11
  Code reference: core/hooks/herdr_bridge.py:924
  Evidence: settle_boundary: nach submitted nichts, continuation → liegen/zurücklegen, sonst eigenen Vermerk verwerfen; Bestandstests (#467/#495/#506/#499) 105 passed.
  Status: CONFIRMED

Confirmation:
  AC: AC-12
  Code reference: core/hooks/herdr_bridge.py:1097
  Evidence: Echt-Herdr-E2E (Szenario R) lokal beim PO, nicht prüfbar; Skript scripts/e2e_auto_clear.sh enthält R und angepasste Q/S. Statisch konsistent, nicht ausgeführt.
  Status: CONFIRMED (statisch)

═══════════════════════════════════════
VERDICT: VERIFIED
═══════════════════════════════════════
Tests: 105 passed, 0 failed, 0 übersprungen
Edge cases: geprüft; F002/F003 LOW, nicht blockierend
Regressions: None found
Checklist: 12/12 points proven (AC-12 nur statisch, E2E lokal beim PO)

## Geprüfte Dateien

- sha256:dd215ec657bf34dbca96bd26b8cb7da6c3c581b84e16958b52c7cb1cad4d9fba  core/hooks/herdr_bridge.py
- sha256:214615b0935f2451b0acba71b88c541bd66e44afa624df83d283b169eda10274  core/hooks/klartext_gate.py
- sha256:8db4cde1fe942570555e6b34da54c91895cf187b02638cec8bc7b2fd48c98e7f  tests/test_vorlagen_klartext_597.py

## Prüfbasis

- base: 081ac849968db6a0abaca0a2cd410eee6f7746fa
- blob:4159a1f27f05abfa4265b99b3221ca0418e36716  core/hooks/herdr_bridge.py
- blob:d9b01b54b74c432ef2fc4a4a57731653b18453de  core/hooks/klartext_gate.py
- blob:53c80aeddbf347d8cc5ccc3fcc8a7c3ee3153efe  tests/test_vorlagen_klartext_597.py

## Geprüfte Dateien

- sha256:dd215ec657bf34dbca96bd26b8cb7da6c3c581b84e16958b52c7cb1cad4d9fba  core/hooks/herdr_bridge.py
- sha256:214615b0935f2451b0acba71b88c541bd66e44afa624df83d283b169eda10274  core/hooks/klartext_gate.py
- sha256:8db4cde1fe942570555e6b34da54c91895cf187b02638cec8bc7b2fd48c98e7f  tests/test_vorlagen_klartext_597.py

## Prüfbasis

- base: 081ac849968db6a0abaca0a2cd410eee6f7746fa
- blob:4159a1f27f05abfa4265b99b3221ca0418e36716  core/hooks/herdr_bridge.py
- blob:d9b01b54b74c432ef2fc4a4a57731653b18453de  core/hooks/klartext_gate.py
- blob:53c80aeddbf347d8cc5ccc3fcc8a7c3ee3153efe  tests/test_vorlagen_klartext_597.py
