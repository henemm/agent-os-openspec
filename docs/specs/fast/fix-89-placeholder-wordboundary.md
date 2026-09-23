# Fast Track: `_PLACEHOLDER_RE` mit Wortgrenzen — Testname „placeholder" blockiert keine RED-Artefakte mehr (#89, Epic #199, 3.30.2)

## Problem

`tdd_enforcement.py::_PLACEHOLDER_RE` prüft die generischen Wörter `TODO|PLACEHOLDER|FIXME`
ohne Wortgrenzen (`re.IGNORECASE`, kein `\b`) — anders als `_FAILURE_RE` zwei Definitionen
weiter oben in derselben Datei, das seine Keywords bereits mit `\b(...)\b` prüft.

Ein RED-Artefakt ist echte pytest-Ausgabe. Enthält darin auch nur ein Testname das Wort
„placeholder" als Teilstring — z. B. `test_gate_ignores_known_placeholder_values` — feuert die
Regel, weil sie an jeder Fundstelle matcht, nicht nur an einer eigenständigen. Der Testname
erscheint typischerweise dreimal in echter Ausgabe (Testkopf, Traceback, `short test summary`)
und blockiert damit jede Neuanlage von Dateien in `phase6_implement`/`phase6b_adversary`, obwohl
das Artefakt echte Fehler-Evidenz enthält.

## Scope

- `core/hooks/tdd_enforcement.py::_PLACEHOLDER_RE` — die drei bloßen Wörter (`TODO`,
  `PLACEHOLDER`, `FIXME`) bekommen `\b`-Wortgrenzen, exakt das bereits etablierte Muster von
  `_FAILURE_RE` in derselben Datei. Die Klammer-/Phrasen-Alternativen (`<test_output>`,
  `<your output>`, `insert output`, `copy output`, `example output`) bleiben unverändert — sie
  enthalten Leerzeichen bzw. spitze Klammern, die innerhalb eines snake_case- oder
  camelCase-Bezeichners nicht vorkommen können, waren also nie die Ursache dieses Fehlalarms.

**Nicht enthalten** (beides im Issue selbst als Alternativen skizziert):

- Testnamen-/Pfadzeilen vor der Prüfung entfernen, analog zu `_TAP_SUMMARY_RE` (#73). Verworfen,
  weil das eine Framework-spezifische „sieht aus wie eine Testzeile"-Heuristik pro Runner
  bräuchte (pytest, node, jest, go, swift …) — Wortgrenzen lösen dieselbe Fehlerklasse
  framework-unabhängig, ohne Zeilen zu klassifizieren.
- Ein `workflow.py`-Kommando, um ein ungültiges RED-Artefakt zu ersetzen. Eigener Ausweg für den
  Fall, dass trotzdem ein Fehlalarm auftritt — im Issue selbst als „Zusätzlich" markiert, keine
  Voraussetzung für diesen Fix.

## Definition of Done

Ein RED-Artefakt, dessen einziger „Platzhalter"-Treffer ein echter Bezeichner ist, der
`placeholder`/`todo`/`fixme` als Teilstring enthält (mindestens einseitig durch `_` oder
Groß-/Kleinschreibung verbunden, keine eigene Wortgrenze), wird nicht mehr blockiert. Ein
echter Platzhalter-Marker — das Wort für sich, mit echten Wortgrenzen (Leerzeichen,
Satzzeichen, Zeilenanfang/-ende) — wird weiterhin blockiert, unverändert.

## Acceptance Criteria

- **AC-1:** Given RED-Artefakt-Inhalt mit `test_gate_ignores_known_placeholder_values` in
  Testkopf-, Traceback- und Short-Summary-Zeile (plus echter Fehler-Evidenz), When
  `tdd_enforcement._validate_artifact` es prüft, Then liefert es `None` (gültig).
- **AC-2:** Given RED-Artefakt-Inhalt mit `TODO`/`PLACEHOLDER`/`FIXME` als eigenständigem Wort
  (echte Wortgrenzen), When geprüft, Then bleibt das Artefakt blockiert, Meldung enthält
  weiterhin „Platzhalter" — unverändert gegenüber vorher.
- **AC-3:** Given RED-Artefakt-Inhalt mit den Klammer-/Phrasen-Mustern (`<test_output>`,
  `insert output` etc.), When geprüft, Then bleibt das Artefakt blockiert — unverändert.
- **AC-4:** Given die bestehenden Tests in `tests/test_gate_parser_fixes_73_76_79.py`
  (`TestTapSummaryNotPlaceholder`), When sie nach dem Fix erneut laufen, Then bleiben alle drei
  grün (kein Regressionsschaden am #73-Fix).

## Test Plan

`tests/test_tdd_enforcement_placeholder_wordboundary_89.py`, Stilvorlage:
`tests/test_gate_parser_fixes_73_76_79.py::TestTapSummaryNotPlaceholder` (direkter Aufruf von
`tdd_enforcement._validate_artifact(art, tmp_path)` mit echten Dateien in `tmp_path`).

Nachweis:

- Ausgangsstand: 1103 passed, 4 skipped
- RED vor dem Fix: 2 der 6 neuen Tests rot (beide `TestPlaceholderSubstringInTestNameNotBlocked`
  – der reale Testname-Fall und die FIXME/TODO-Variante), 4 grün (die vier
  „bleibt-blockiert"-Kontrollen bestanden schon vorher, weil ihre Muster echte Wortgrenzen haben)
- GREEN nach dem Fix: 1109 passed, 4 skipped (6 neue, keine bestehenden verändert;
  `tests/test_gate_parser_fixes_73_76_79.py::TestTapSummaryNotPlaceholder` weiterhin 3/3 grün)

**Gegenprobe (Mutation).** `_PLACEHOLDER_RE` auf die ursprüngliche, wortgrenzenlose Fassung
zurückgesetzt: exakt die 2 Tests aus `TestPlaceholderSubstringInTestNameNotBlocked` wurden rot,
die 4 Kontroll-Tests blieben grün (sie hätten das Mutat nicht erkannt — bestätigt, dass sie
etwas anderes prüfen als der Fix). Arbeitsbaum danach per Backup-Datei exakt wiederhergestellt,
volle Suite erneut grün (1109 passed, 4 skipped).
