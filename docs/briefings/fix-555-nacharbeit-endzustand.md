---
spec_file: docs/specs/fix-555-nacharbeit-endzustand.md
spec_sha256: e5f005b21e0118d5aed36e5e9279a395dd1d50813a618687f193c369d5505c64
spec_frozen_sha256: 230354b1ef3cfa76de35b6ad51be0aab8b3b53ba13ef56f61814e76d8103c0ef
---

# PO-Briefing: fix-555-nacharbeit-endzustand

- **Spec:** docs/specs/fix-555-nacharbeit-endzustand.md
- **Issue:** #555
- **Erstellt:** 2026-11-09

## Was gebaut wird

Im Auto-Modus zeigt die Fußzeile keine erfundene Aufgabe mehr, wenn Claude selbst weiterarbeitet; kleine Folgefehler werden behoben.

## Definition of Done

Bei autarkem Auftrag erscheint für Claudes eigene Schritte ⏳ statt ❗, und Plan, Fußzeile und Seitenleiste zeigen denselben Zustand.

## Wie geprüft wird

Automatische Tests belegen jede Anforderung einzeln; ob Claude den angekündigten Schritt wirklich ausführt, prüft kein Test.

## Kritische Anmerkungen

- Fund 9 (stille Nummern-Normalisierung) bleibt bewusst unverändert, wie im Ticket selbst als gewollt vermerkt.
- Freigabe-Wörter bleiben auch im Auto-Modus ❗; die Auto-Freigabe ist ein eigener Fall.
- Die Zusage „Claude führt den Schritt aus“ wird von keinem Hook erzwungen.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
