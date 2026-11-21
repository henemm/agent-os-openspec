# Adversary Dialog — fix-642-zeitschaetzung
Spec: docs/specs/fix-642-zeitschaetzung.md
Datum: 2026-11-21 22:24

## Checkliste
- [x] Alte Workflows ohne Aktivitätsdatei verzerren die Schätzung nicht mehr; kein Ende über Nacht aus Leerlaufdaten.
- [x] Vor der Freigabe zeigt der Plan Start und ungefähre Freigabezeit; danach eine Ende-Spanne auf Viertelstunden, die mit jeder Phase enger wird.
- [x] Die Datengrundlage ist bei jeder Pane-Breite vollständig lesbar.
- [x] Es gibt keine Zeile mehr, die sich mit Start und Ende widerspricht.
- [x] **AC-1:** Given ein Archiv mit drei Workflows mit Aktivitätsdatei und fünf ohne (darunter einer mit 10-h-Nachtsegment) / When `load_archive_phase_durations` und `_estimate_group` laufen / Then besteht die Vergleichsgruppe nur aus den drei Workflows mit Aktivitätsdatei, und das Nachtsegment beeinflusst keine Spanne.
- [x] **AC-2:** Given weniger als `min_samples` saubere Vergleichs-Workflows / When Plan und `workflow.py estimate` rendern / Then steht „Ende  offen“ mit „zu wenig Vergleichsdaten“, keine Uhrzeit-Spanne und kein Startwert aus `defaults`.
- [x] **AC-3:** Given ein Workflow in `phase2_analyse` mit sauberer Vergleichsgruppe / When der Plan rendert / Then zeigt er „Start“ und „Freigabe  ca. HH:MM“ (Minute 00, 15, 30 oder 45, Median der Restarbeit bis zur Freigabe) und keine „Ende“- und keine „Dauer“-Zeile; wartet eine menschliche Freigabe, steht „Freigabe  wartet auf dich“.
- [x] **AC-4:** Given ein Workflow ab `phase4_approved` mit sauberer Vergleichsgruppe / When der Plan rendert / Then zeigt er „Ende  ca. A–B“ mit A auf die Viertelstunde abgerundet und B aufgerundet aus den Quantilen 0.1/0.9, bei A = B eine einzige Uhrzeit, und keine „Dauer“-Zeile.
- [x] **AC-5:** Given 10 oder mehr bzw. weniger als 10 saubere Vergleichs-Workflows mit bekannter Restarbeit ab der Freigabe / When der Plan rendert / Then steht in einer eigenen Zeile „P % sicher, aus N Workflows“ mit P = Leave-one-out-Trefferquote (z. B. 8 von 10 getroffen → „80 % sicher“) bzw. nur „aus N Workflows“.
- [x] **AC-6:** Given `render_plan` mit `width=34` und einer Prognose mit Basiszeile / When gerendert wird / Then ist keine Zeile länger als 34 Zeichen und der vollständige Text der Basiszeile („… aus 32 Workflows“) ist im Ergebnis enthalten.
- [x] **AC-7:** Given ein Workflow vor bzw. nach der Freigabe / When `workflow.py estimate` läuft / Then enthält die Ausgabe `ESTIMATE_APPROVAL=` bzw. `ESTIMATE_END_LOW=`/`ESTIMATE_END_HIGH=` und eine `LINE=` im Format aus Implementation Details 7, ohne Minutenspanne der Dauer.
- [x] **AC-8:** Given kaputte Aktivitätsdateien, leeres Archiv und ungültige Zeitstempel / When Plan und `estimate` laufen / Then entsteht keine Ausnahme, und der Ist-Block fertiger Workflows bleibt unverändert.

## Dialog

### Runde 1
**Adversary:** Tests gelaufen (docs/artifacts/fix-642-zeitschaetzung/adversary-tests.log): 80 passed, 0 failed (642, 620, 628, 637).
Beweise je AC:
- AC-1: Code reference: core/hooks/workflow.py:1087 (`h.get("clean") is True`), `clean = bool(phases)` in `_archive_phase_entry` (Z. 955ff). Mutation M1 (Filter entfernt) -> Test rot.
- AC-2: workflow.py:1176 leere Gruppe -> `n=0, source="none"`, Basis NO_DATA (Z. 1373). Mutation M12 rot.
- AC-3: workflow.py:1183-1187 Median bis phase3_spec, Viertelstunde; M9, M10 rot; M13 (wartet auch nach Freigabe) rot. Fast-Track (3-4-6-8) sondiert: Freigabe 00:00, ab phase6 nur Ende-Spanne, keine Ausnahme.
- AC-4: workflow.py:1189-1190; M2, M3, M4, M15, M16 rot.
- AC-5: workflow.py:1131-1134 Leave-one-out laesst i aus (M5 in-sample -> rot); Schwelle 10 doppelt abgesichert (1191 und 1377).
- AC-6: workflow.py:700 Umbruch; Basiszeile bei 34 vollstaendig. Sonde mit Tageswechsel: Zeile 'Ende  ca. 22.11. 00:45-22.11. 04:45' wird bei 34 umbrochen, keine Zeile > 34.
- AC-7: workflow.py:5151ff Schluessel und LINE nur mit Spanne bzw. Approval.
- AC-8: Sonden: kaputtes created -> None; ungueltige Zeitstempel -> []; ungueltige quantiles ([0.9,0.1], [None,1], 'x', [0.1]) -> Config None bzw. None; Ist-Block unveraendert (Code 1314-1325).
Mutationen, die KEIN Test faengt: M6 (Leave-one-out-Basis ohne phase4 verschoben), M11 (Umbruch durch Kappen ersetzt), M7/M8 einzeln und gemeinsam (Prozent-Schwelle; durch doppelte Absicherung teils gleichwertig). M18 (Zone ignoriert) ist gleichwertig, da alle Zonen mit Viertelstunden-Versatz.
**Implementierer:** (keine Rueckmeldung eingeholt; Kontextisolation)

### Runde 2
**Adversary:** Zweite Runde, Schaerfung der Funde.
F001 (MEDIUM, edge_case): Code reference: core/hooks/workflow.py:700 / 716ff `_wrap_time_line`. Bei Tageswechsel ist 'Ende  ca. 22.11. 00:45-22.11. 04:45' laenger als 34 und wird per textwrap an einem Leerzeichen umbrochen ('...22.11.' / '  04:45'): die Spanne reisst auseinander, lesbar bleibt sie. Mutation M11 (Kappen statt Umbruch) bleibt gruen, weil der Test nur den kurzen Fall (Basiszeile 31 Zeichen) abdeckt. Spec AC-6 formal erfuellt; Test bewacht den Umbruch nicht.
F002 (LOW, edge_case): Code reference: core/hooks/workflow.py:1126 `_measured_hit_rate`. Mutation M6 (Basis ab phase5 statt ab phase4) bleibt gruen: der Test fixiert die Basis der Leave-one-out-Restarbeit nicht. Logik stimmt mit Spec.
F003 (LOW, anti_pattern): Code reference: core/hooks/workflow.py:1191 und 1377. Doppelte Schwelle PERCENT_MIN_SAMPLES; Mutation einer Stelle ist unsichtbar. Harmlos.
Hinweis: Freigabezeit nutzt Rundung auf naechste Viertelstunde (+7.5, floor); Spec sagt 'naechste Viertelstunde', Lesart akzeptiert.
Keine spec_violation, keine Regression gefunden. Originaldatei per Diff gegen Sicherung identisch.
**Implementierer:** (keine Rueckmeldung)

## Findings und Confirmations

Finding F001: Umbruch-Test bewacht lange Zeilen nicht (Mutation M11 gruen)
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/workflow.py:700
  Remediation: Test mit Tageswechsel-Spanne bei width=34 ergaenzen.

Finding F002: Leave-one-out-Basis nicht fixiert (Mutation M6 gruen)
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/workflow.py:1126
  Remediation: Test mit asymmetrischer phase4-Dauer.

Confirmation AC-1..AC-8:
  Code reference: core/hooks/workflow.py:1087
  Evidence: Filter, Freigabe-Prognose (1183), LOO (1131), Umbruch (700), fail-open durch Sonden belegt.
  Status: CONFIRMED

## Herkunft der Vorbedingungen

<!-- vom Prüfer auszufüllen, siehe `precondition_origins.py` -->

## Verdict

VERDICT: VERIFIED

Findings: F001 MEDIUM Testluecke Umbruch (M11), F002 LOW Testluecke LOO-Basis (M6), F003 LOW doppelte Schwelle. Kein Produktfehler.

## Geprüfte Dateien

- sha256:09d09f93b75ee2666925cd6d5b0cdfdcc56ced116b0e4624470d1567a33f365b  core/hooks/workflow.py

## Prüfbasis

- base: e1514299d3c4feb9e19519fc46fc39676866ddbd
- blob:7b5871df77bdf8b59fac47a36d80624fcd56a61a  core/hooks/workflow.py
