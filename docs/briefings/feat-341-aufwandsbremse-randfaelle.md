---
spec_file: docs/specs/feat-341-aufwandsbremse-randfaelle.md
spec_sha256: 5e37b1ee95f63d50b8fb32b3f4368580cfc3cadaf8076b406342f120072b189e
---

# PO-Briefing: feat-341-aufwandsbremse-randfaelle

- **Spec:** docs/specs/feat-341-aufwandsbremse-randfaelle.md
- **Issue:** #341
- **Erstellt:** 2026-10-03

## Was gebaut wird

Zeilenzählung beim Abschluss stimmt nach Rebase und Umbenennung, und die Freigabe löst bei Budgetüberschreitung die Rückfrage aus.

## Definition of Done

Nach Rebase zählt nur eigene Arbeit, Umbenennungen werden richtig zugeordnet, und Überschreitung bei Freigabe erzeugt die Rückfrage.

## Wie geprüft wird

Automatische Tests mit echten Git-Repositories und echtem Freigabe-Ablauf; ob Claude die Rückfrage befolgt, bleibt ungeprüft.

## Kritische Anmerkungen

- Abweichung vom Ticket: Rebase-Basis und Umbenennungen werden anders gelöst als verlangt (bewusst, genauer); Ticket-Wortlaut ist nicht erfüllt.
- Teil 4 ist nur Klärungstext in der neuen Spec; alte Spec unverändert, Test existiert schon, kein Rot-zu-Grün.
- Bei Umbenennung zwischen Produktiv und Test werden entfallene Zeilen nicht abgezogen; leichte Überzählung möglich.

## Freigabe-Frage

Akzeptierst du, dass Rebase und Umbenennungen anders als im Ticket beschrieben gelöst werden?
