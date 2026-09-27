---
spec_file: docs/specs/fix-147-validierung-abstufen.md
spec_sha256: cfec00f46d530f627982665fccc46efc4cd346fe3c26a5f885c56bfcb89e6274
---

# PO-Briefing: fix-147-validierung-abstufen

- **Spec:** docs/specs/fix-147-validierung-abstufen.md
- **Issue:** #147 (Teil 1 von 2, Rest in #260)
- **Erstellt:** 2026-09-27

## Was gebaut wird

Nach deiner Freigabe laufen Umsetzung und Prüfung automatisch weiter, ohne dass du zwischendurch selbst etwas eintippst.

## Definition of Done

Fertig ist es, wenn nach deinem Ok die Prüfung ohne weitere Eingabe durchläuft und nur Ergebnismeldungen erscheinen.

## Wie geprüft wird

Automatische Tests belegen den Wegfall der beiden Zwischenschritte; das Bestehende bleibt unverändert.

## Kritische Anmerkungen

- Die Nachführung hat inhaltlich nichts verändert — nur Testverweise je Kriterium und echte gemessene Zahlen neben der Schätzung ergänzt.
- Widerspruch in der Fertig-Definition: Sie verspricht, jede Anforderung sei durch einen Test belegt — bei drei von elf ist der einzige Nachweis der Skript-Lauf selbst, kein eigener Test.
- Du kontrollierst weiterhin Freigabe, dein Ok zu den Ergebnissen und die Übernahme-Rückfrage am Ende; nicht mehr die zwei Momente, in denen ein getippter Befehl dir zufällig etwas hätte auffallen lassen.
- Rückgängigmachen wäre unaufwändig: zwei Schaltstellen plus automatisch abgeleitete Kopien, keine Prüfmechanik wird angerührt.
