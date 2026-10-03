---
spec_file: docs/specs/fix-324-env-aliase.md
spec_sha256: fe8537e1b0f861fbe6a5ccbc0e159322d022c896f5415d89d47f6876fab15369
---

# PO-Briefing: fix-324-env-aliase

- **Spec:** docs/specs/fix-324-env-aliase.md
- **Issue:** #324
- **Erstellt:** 2026-10-02

## Was gebaut wird

Die Prüfung vor dem Commit erkennt auch Abkürzungen, die über git-Umgebungsvariablen auf „commit“ gesetzt werden, und blockt sie.

## Definition of Done

Die vier Umgehungsschreibweisen werden abgewiesen, harmlose Befehle laufen weiter durch, und alle bisherigen Tests bleiben grün.

## Wie geprüft wird

Automatische Tests lassen das echte Gate alle vier Schreibweisen und Kontrollfälle prüfen; vorsätzliche Verschleierung wird nicht abgedeckt.

## Kritische Anmerkungen

- Zusatz: Eine nicht auffindbare Variable gilt als „commit“; ein harmloser Alias dieses Namens würde fälschlich blockiert.
- Zuweisungen in anderen Befehlsteilen zählen immer mit, auch wirkungslose; mögliche Fehlalarme, nie verpasste Treffer.
- Vorsätzliche Umgehung bleibt möglich; Wirkung in Projekten erst nach Plugin-Update.

## Freigabe-Frage

Sollen die vier Umgehungen gesperrt werden, auch wenn dabei selten ein harmloser Alias fälschlich blockiert wird?
