---
spec_file: docs/specs/feat-694-handoff-tab.md
spec_sha256: 4d3412ea98ff0790f22ccf5347840113406b541b7d03805d6a1023b743ddecf3
spec_frozen_sha256: 73f799049cd0b019024c6188bb87254a744245731b2dac369c8d9a7076ba0271
---

# PO-Briefing: feat-694-handoff-tab

- **Spec:** docs/specs/feat-694-handoff-tab.md
- **Issue:** #694
- **Erstellt:** 2026-11-26

## Was gebaut wird

Jede Folgesitzung eines Auftrags startet in eigenem, beschriftetem Herdr-Tab; die Nachfolgerin schließt nach sauberer Übergabe den alten Tab.

## Definition of Done

Das zweite Issue läuft im eigenen Tab; nach ⏳-Übergabe verschwindet der alte Tab, bei ❗ oder unklarem Zustand bleibt er stehen.

## Wie geprüft wird

Automatische Tests gegen ein Fake-Herdr belegen Tab-Start, Rückfall und Schließregeln; ein Echtlauf mit echtem Herdr ist nicht Teil der Tests.

## Kritische Anmerkungen

- Plan-Pane im neuen Tab (Ticketforderung) hat keinen eigenen Test; die Spec verlässt sich auf bestehendes Verhalten.
- Schließen hängt am Bildschirmtext der Vorgängerin; bei Fehlerkennung bleibt der Tab stehen, nie umgekehrt.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
