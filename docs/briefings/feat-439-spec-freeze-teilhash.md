---
spec_file: docs/specs/feat-439-spec-freeze-teilhash.md
spec_sha256: eb04d90e5fffc29c4bfff4843ce00abae8256f146723935f251b58777cc31306
---

# PO-Briefing: feat-439-spec-freeze-teilhash

- **Spec:** docs/specs/feat-439-spec-freeze-teilhash.md
- **Issue:** #439
- **Erstellt:** 2026-10-13

## Was gebaut wird

Nach der Freigabe bleiben nur freigegebene Spec-Teile gesperrt; Testnamen und Begleittext lassen sich ohne Override nachtragen.

## Definition of Done

Testnamen und Begleittext sind nach Freigabe ohne Override änderbar, Zweck, Umfang und Abnahmetexte bleiben mit Override gesperrt, alte Briefings bleiben gültig.

## Wie geprüft wird

Automatische Tests prüfen Erlauben, Sperren, Umgehungsversuche und Altbriefings; nicht geprüft wird Änderung der Spec über die Kommandozeile.

## Kritische Anmerkungen

- Override öffnet die Spec nie mehr; echte Änderungen erfordern Rücksprung, neues Briefing, neue Freigabe. Bewusste Verschärfung.
- Test Plan gilt als frei änderbar, im Ticket nicht genannt; Änderungen dort werden nur protokolliert.
- Änderung per Kommandozeile umgeht die Sperre bis zum Phasenwechsel; alte CI-Kopien melden Begleittext-Änderungen weiter als veraltet.

## Freigabe-Frage

Gibst du frei, dass Override die freigegebene Spec nicht mehr öffnet und der Testplan frei änderbar ist?
