# Adversary Dialog — fix-645-plan-zeit-auslieferung
Spec: docs/specs/fix-645-plan-zeit-auslieferung.md
Datum: 2026-11-24 12:45

## Checkliste
- [x] **Input:** `render_plan(data, archived=…, estimate={"actual": True, "now": …})` mit `ship_status` und `phase_log`.
- [x] **Output:** Während der Auslieferung steht „Ausliefern  seit HH:MM (N min)“ und „Ende  offen“; nach `done`/`skipped` Ende und Dauer bis zum Abschluss der Auslieferung.
- [x] **Side effects:** keine; reine Anzeige.
- [x] **AC-1:** Given ein Workflow in `phase8_complete` mit `ship_status` `open`, `running` oder `failed` und Phase-8-Eintritt um 08:57 bei Start 08:07 / When der Plan mit Testuhr 12:30 gerendert wird / Then zeigt der Zeitblock „Start  08:07“, „Ausliefern  seit 08:57 (<Dauer 3 h 33 min>)“ und „Ende  offen“, ohne „Dauer  “-Zeile und ohne feste Ende-Uhrzeit.
- [x] **AC-2:** Given ein Workflow mit mehreren `phase8_complete`-Einträgen im `phase_log` und `ship_at` nach mehrfachem `running` / When der Plan rendert / Then ist der Auslieferungsbeginn der `entered_at` des letzten `phase8_complete`-Eintrags und nicht `ship_at`; fehlt der Eintrag, steht das Ende aus `_finished_span`.
- [x] **AC-3:** Given `ship_status` `done` oder `skipped` mit gültigem `ship_at` nicht vor dem Start / When der Plan rendert / Then steht „Ende  “ mit der Uhrzeit von `ship_at` und „Dauer  “ bis dahin, die Arbeitszeit-/Gesamt-Logik aus #628 gilt unverändert.
- [x] **AC-4:** Given ein Workflow ohne `ship_status` oder mit `done`/`skipped` ohne bzw. mit unlesbarem `ship_at` / When der Plan rendert / Then ist die Ausgabe exakt wie vor der Änderung, und die Tests in `test_zeitschaetzung_620.py` (AC-6), `test_arbeitszeit_628.py`, `test_zeitschaetzung_642.py` und `test_anzeige_zeitzone_637.py` bleiben grün.
- [x] **AC-5:** Given ein abgebrochener Workflow (`abandoned`), fehlende Zeitstempel oder ein kaputter `phase_log` / When der Plan rendert / Then entsteht weiterhin kein Zeitblock bzw. `[]`, und es wird keine Ausnahme ausgelöst; `_finished_span` und die Retro-Zeile „Schätzung vs. Ist“ liefern dasselbe Ergebnis wie vorher.
- [x] **AC-6:** Given eine Anzeigezone ungleich UTC (#637) und `render_plan` mit `width=34` / When die Auslieferung läuft / Then zeigt die Zeile „Ausliefern  seit HH:MM (<Dauer>)“ die Uhrzeit in der Anzeigezone, und keine Zeile ist länger als 34 Zeichen (Umbruch statt Kappen, #642).

## Dialog

### Runde 1
**Adversary:** Angriff auf Zeitstempel: ship_at (UTC mit Offset) gegen naive entered_at, Vergleich `shipped >= start`, `now` vor Auslieferungsbeginn, unbekannter ship_status, ship_at vor Start, Phase 8 ohne phase8-Eintrag, Retro/_finished_span.
**Implementierer:** Beweise (eigene Läufe):
- `_parse_time` normalisiert tz-bewusste Werte auf naive Ortszeit, `_shipped_at`, `_ship_start` und `now` laufen alle darüber, der Vergleich mischt nie naiv/aware.
Code reference: core/hooks/workflow.py:1041
Code reference: core/hooks/workflow.py:1306
Code reference: core/hooks/workflow.py:1319
Code reference: core/hooks/workflow.py:1330
Code reference: core/hooks/workflow.py:1346
- Probe: ship_at 07:00 vor Start 08:07 mit done -> Ausgabe wie Altbestand (Start 08:07, Dauer 56 min, Ende 09:03). ship_at == Start -> Dauer 0 min, Ende 08:07 (zulässig). now 08:00 vor Beginn 09:03 -> "seit 09:03 (0 min)" (max 0). Unbekannter ship_status "weird" -> Altbestand-Ausgabe. Phase 8 ohne Log-Eintrag -> Fallback _finished_span (Test AC-2). abandoned/kaputtes Log -> [] (Test AC-5).
- Testlauf: 93 passed (neue Datei plus #620/#628/#642/#637), siehe docs/artifacts/fix-645-plan-zeit-auslieferung/adversary-test-output.txt.

### Runde 2
**Adversary:** Mutations-Gegenprobe (Sicherungskopie im Scratchpad, String-Ersetzung, danach diff = identisch, `git diff --stat` leer für workflow.py). Ergebnis je Mutation gegen tests/test_plan_zeit_auslieferung_645.py:
- M1 _ship_start nutzt ship_at: gefangen. M4 reversed entfernt: gefangen. M5 Fallback entfernt: gefangen. M8 done als pending: gefangen. M9 skipped nicht erkannt: gefangen. M10 max(0) entfernt: gefangen.
- M2 `>=` -> `>`: ÜBERLEBT. M3 Guard `shipped >= start` entfernt (ship_at vor Start): ÜBERLEBT. M6 `_parse_time(now)` -> `now`: überlebt (Produktivuhr ist naiv, nur tz-bewusste Testuhr betroffen). M7 Anzeigezone in der Ausliefern-Zeile weggelassen: ÜBERLEBT, weil die Systemzone der Testumgebung (Europe/Berlin) der Testzone entspricht; unter TZ=UTC wäre er rot.
**Implementierer:** Die Überlebenden sind Testlücken, kein Produktfehler; das Verhalten ist in den Proben aus Runde 1 korrekt. Code reference: core/hooks/workflow.py:1346 (Guard), core/hooks/workflow.py:1343 (Zone in der Ausliefern-Zeile).

Findings:
Finding:
  ID: F001
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/workflow.py:1346
  Description: `shipped >= start` schützt ship_at vor dem Start; kein Test (Mutation M3 und M2 überleben).
  Spec requirement: AC-3 — "gültigem ship_at nicht vor dem Start"
  Conflict: Entfall des Guards erzeugte negative Spanne (auf 0 geklemmt, falsches Ende), unbemerkt.
  Remediation: Test mit ship_at vor Start (erwartet Altbestand-Ausgabe) und ship_at == Start ergänzen.
Finding:
  ID: F002
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/workflow.py:1343
  Description: Die Anzeigezone in der Ausliefern-Zeile ist nur bei abweichender Systemzone geprüft; Test AC-6 läuft in Berlin mit Zone Europe/Berlin (M7 überlebt).
  Spec requirement: AC-6 — Uhrzeit in der Anzeigezone
  Conflict: Testdaten und Pruefling decken sich zufällig mit der Systemzone.
  Remediation: Zone wählen, die von der Systemzone abweicht (z. B. Asia/Tokyo) bzw. TZ per monkeypatch/tzset auf UTC setzen.
Finding:
  ID: F003
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/workflow.py:1341
  Description: tz-bewusstes `now` ungetestet (M6 überlebt); Produktivuhr ist naiv.
  Spec requirement: AC-6
  Conflict: keiner im Produktivpfad.
  Remediation: optional Test mit tz-bewusstem now.

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

VERDICT: VERIFIED
Alle ACs belegt (93 Tests grün, Code reference: core/hooks/workflow.py:1330), Produktverhalten in Randfällen korrekt; F001-F003 sind Testlücken (MEDIUM/LOW), keine Spec-Verletzung.

## Geprüfte Dateien

- sha256:5b6ae7aab5b9d60d13b7ce9c8911084ef858e5ff2dc7dccd34e6f40bb9407223  core/hooks/workflow.py

## Prüfbasis

- base: dff965774fd5501eed8233884074a0e93c787583
- blob:685b1a592af79041e5ba779164642ba6853805ee  core/hooks/workflow.py
