# Mini-Spec: fix-671-wackelige-tests

Issue #671 (enthält auch #683, als Duplikat geschlossen). Zwei Tests scheitern in der CI gelegentlich, ohne dass sich Code geändert hat.

## Was ändert sich
- `tests/test_herdr_sidebar_466.py`: Der Herdr-Stub baut die Protokollzeile eines Aufrufs zuerst vollständig in einer Variablen und schreibt sie mit genau einem `printf` ans Log. Zusätzlich wertet `_calls` eine letzte Zeile ohne abschließendes `\n` nicht als Aufruf (sie ist noch im Schreiben).
- `tests/test_mention_guard_617.py::test_laufzeit_150kb_unter_2s_und_ueber_200kb_frei`: Die Zeitmessung zieht den Grundaufwand eines Hook-Aufrufs ab, gemessen im selben Lauf am selben Hook mit einem kurzen Befehl (Minimum aus zwei Läufen). Geprüft wird: Mehraufwand für 150 KB unter 2,0 s. Die Prüfung, dass 150 KB geblockt und über 200 KB freigegeben werden, bleibt.
- CHANGELOG-Eintrag, Patch-Version.

## Was darf sich nicht ändern
- Kein Produktivcode (`core/`) wird geändert.
- Die übrigen Tests beider Dateien bleiben grün und unverändert in ihrer Aussage.
- Ein quadratisch oder schlimmer wachsender Prüfaufwand (mehrere Sekunden für 150 KB) lässt den Laufzeittest weiterhin scheitern.

## Acceptance Criteria
- **AC-1:** Given der Stub schreibt einen Aufruf mit mehreren Argumenten / When `_calls` das Log liest, während die Zeile erst teilweise geschrieben ist / Then erscheint kein unvollständiger Aufruf in der Liste.
- **AC-2:** Given ein Log, dessen letzte Zeile kein abschließendes `\n` hat / When `_calls` es liest / Then enthält das Ergebnis nur die vollständigen Zeilen davor.
- **AC-3:** Given ein CI-Runner, auf dem jeder Hook-Aufruf durch Last um eine gleiche Grundzeit langsamer ist / When der Laufzeittest läuft / Then zählt nur der Mehraufwand gegenüber dem kurzen Befehl gegen die Grenze von 2,0 s.
- **AC-4:** Given der Erwähnungs-Wächter bräuchte für 150 KB mehr als 2 s zusätzlich / When der Laufzeittest läuft / Then scheitert er.

## Manuelle Test-Schritte
1. Entfällt; `pytest tests/test_herdr_sidebar_466.py tests/test_mention_guard_617.py` mehrfach hintereinander.

## Inline-Test (wird während Implementierung geschrieben)
- [ ] `tests/test_herdr_sidebar_466.py::test_calls_ignoriert_unvollstaendige_letzte_zeile` (AC-2)
- [ ] Laufzeittest angepasst (AC-3, AC-4)

## Architektur-Entscheidung (ADR)
- **ADR-Nr.:** keine
- **Rationale:** Reine Teständerung. Relative Messung statt fester Wanduhr-Grenze: Last auf geteilten Runnern verlangsamt vor allem Prozessstart und Interpreter-Import; der Abzug des Grundaufwands im selben Lauf hält die Schutzwirkung gegen algorithmische Ausreißer, ohne vom Runner abzuhängen.
