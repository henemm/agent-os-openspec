---
spec_file: docs/specs/fix-668-handoff-idempotent.md
spec_sha256: d818141db4e3820fb7d5adcc314023ef6ebea6bbb83318202115c1a708b419a1
spec_frozen_sha256: c3dc36eb3a44b0fd1ca5003e39856ef194fcb3f06c80dd23932b0ee51c3db257
---

# PO-Briefing: fix-668-handoff-idempotent

- **Spec:** docs/specs/fix-668-handoff-idempotent.md
- **Issue:** #668
- **Erstellt:** 2026-11-25

## Was gebaut wird

Die Übergabe eines Auftrags an eine frische Sitzung startet nie zwei Sitzungen für dasselbe Issue.

## Definition of Done

Ein zweiter Übergabe-Aufruf meldet "schon übergeben", ein gescheiterter Vermerk nach erfolgreichem Start meldet trotzdem "gestartet", alle Tests grün.

## Wie geprüft wird

Automatische Tests belegen die Meldungen und das Schreiben unter Sperre; ob Claude den Befehlstext wirklich befolgt, prüft kein Test.

## Kritische Anmerkungen

- Zusätzlich zum Ticket eingebaut: Zeile "MARKED" für das Ergebnis des Vermerks; unkritisch, nur Auskunft.
- Die Sperre ist nicht lückenlos, weil andere Schreiber sie nicht nehmen; das Spec-Risiko ist benannt.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
