---
spec_file: docs/specs/feat-466-herdr-sidebar.md
spec_sha256: 3d62f82d2b8869662a051a6ae1e3cd78ada804272df8caf8b80518b1d169b27f
spec_frozen_sha256: ce17febdc73fa0841c0ca5a34de9b9da21bd2f1a4b4e31533ca631d0606b1462
---

# PO-Briefing: feat-466-herdr-sidebar

- **Spec:** docs/specs/feat-466-herdr-sidebar.md
- **Issue:** #466
- **Erstellt:** 2026-10-28

## Was gebaut wird

Herdr-Sidebar zeigt Issue, Phase (z. B. 5/8) und nächsten Befehl des laufenden Workflows an, ohne Pane-Wechsel.

## Definition of Done

Nach Start, jedem Phasenwechsel und Freigabe zeigt die Sidebar Titel, Phase und nächsten Schritt; nach Abschluss oder Abbruch ist sie leer.

## Wie geprüft wird

Automatische Tests gegen eine Attrappe belegen Anzeige, Wirkungslosigkeit ausserhalb Herdr und Nicht-Blockieren; echtes Herdr wird nicht getestet.

## Kritische Anmerkungen

- Nur gegen Attrappe getestet; Darstellung in echter Sidebar bleibt ungeprüft.
- Optionale Benachrichtigung bei Gate-Ereignissen fehlt; nur technische Grundlage für #467 entsteht.
- Bei Abschluss wird Anzeige geleert statt 8/8 gezeigt; vom Ticket nicht verlangt.

## Freigabe-Frage

Genügt dir die Anzeige ohne Benachrichtigungen und ohne Test in echtem Herdr als erste Version?
