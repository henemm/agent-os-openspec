---
spec_file: docs/specs/fix-407-ln-state-integrity.md
spec_sha256: 58970504646074f51725fc1a443de8f0ce177440b3185fbdb47f768f8b826769
---

# PO-Briefing: fix-407-ln-state-integrity

- **Spec:** docs/specs/fix-407-ln-state-integrity.md
- **Issue:** #407
- **Erstellt:** 2026-10-09

## Was gebaut wird

Das Sicherheitstor blockiert Verweise und Ordner-Verschiebungen auf Workflow-Zustandsdateien, mit denen man heute die Prüfungen fälschen kann.

## Definition of Done

Verweis-, Verschiebe- und Kopierbefehle auf Zustandsdateien werden abgewiesen, harmlose Befehle laufen weiter, und alle bestehenden Tor-Tests bleiben grün.

## Wie geprüft wird

Automatische Tests schicken Befehle durch das echte Tor, in beide Richtungen; absichtliche Umgehung per Skript oder Platzhalter weisen sie nicht nach.

## Kritische Anmerkungen

- Umfang über den Ticket-Wortlaut hinaus: auch Ordner-Verweise, Verschieben, Kopieren, Synchronisieren werden blockiert.
- Absichtliche Umgehung (Platzhalter, Skript-Verweise) bleibt offen; ausgelagert in Ticket 410.
- Kopieren des Home-Ordners ~/.claude wird im Workflow fälschlich blockiert.

## Freigabe-Frage

Soll der Umfang über das Ticket hinaus (Ordner, Verschieben, Kopieren) so freigegeben werden, mit den genannten Restlücken?
