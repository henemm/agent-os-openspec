---
spec_file: docs/specs/feat-345-qa-gate-selbst-ausfuehren.md
spec_sha256: ff5baad15c87631c7ab5c822b4cdd57c67ddcf349085cccc486cc82a7f3b5987
---

# PO-Briefing: feat-345-qa-gate-selbst-ausfuehren

- **Spec:** docs/specs/feat-345-qa-gate-selbst-ausfuehren.md
- **Issue:** #345
- **Erstellt:** 2026-10-08

## Was gebaut wird

Das Prüftor startet den hinterlegten Testbefehl selbst und urteilt nach dem echten Ergebnis, statt Textausgaben zu raten.

## Definition of Done

Ein Lauf liefert Urteil, gespeicherte Ausgabe und gesperrten Stempel; der alte Weg über Textdateien funktioniert unverändert weiter.

## Wie geprüft wird

Dreizehn automatische Tests mit echten Prozessen belegen Urteil, Zeitlimit, Stempel und Sperren; nicht belegt wird, dass die hinterlegten Tests sinnvoll sind.

## Kritische Anmerkungen

- Abweichung: Anfrage wollte den Befehl als Argument; er kommt nun aus der Projektkonfiguration, weil die Argument-Variante dreimal durchfiel.
- Ohne Pflicht bleibt Fälschen möglich; Durchsetzung, Migrationspfad und Ausrollen folgen erst im Folge-Issue #404.
- Stempel per Python-Import und Änderung der Konfiguration bleiben umgehbar.

## Freigabe-Frage

Reicht dir, dass diese erste Scheibe nur den prüfbaren Weg schafft, während Pflicht und Migration später folgen?
