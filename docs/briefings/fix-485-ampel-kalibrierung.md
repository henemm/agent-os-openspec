---
spec_file: docs/specs/fix-485-ampel-kalibrierung.md
spec_sha256: e0082b00bc8c6812465ab48103b4d22fa6f7b1edc8b9a289a7581ad7c66fbb3a
spec_frozen_sha256: 0dfe232e15ac846d9b2b65e744a0f118f3ba6d1f24819f4d7d561ce3e8518245
---

# PO-Briefing: fix-485-ampel-kalibrierung

- **Spec:** docs/specs/fix-485-ampel-kalibrierung.md
- **Issue:** #485
- **Erstellt:** 2026-10-29

## Was gebaut wird

Die Ampel zeigt nur noch rot, wenn wirklich eine Entscheidung offen ist, die nur der PO treffen kann.

## Definition of Done

Eine Spec ohne offene PO-Entscheidung läuft im Auto-Modus ohne dein Stichwort durch; echte Abweichungen vom Ticket bleiben rot.

## Wie geprüft wird

Automatische Tests prüfen nur den Anweisungstext, nicht, ob die Ampel im Einzelfall richtig urteilt; das siehst du erst im Betrieb.

## Kritische Anmerkungen

- Freigabe im Auswahldialog zählt weiterhin nicht; Claude fragt nur nicht mehr danach und bittet gegebenenfalls um das Stichwort.
- Die Schwelle sinkt bewusst: Wirklich unklare Specs könnten künftig ohne dein Wort durchgehen.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
