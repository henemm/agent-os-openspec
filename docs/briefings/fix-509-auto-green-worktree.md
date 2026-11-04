---
spec_file: docs/specs/fix-509-auto-green-worktree.md
spec_sha256: 7316d888f6e8a73dbe5199ee8215090c5eda16c07304d212cbe1ebe2f34297e1
spec_frozen_sha256: e34412e0915909e465eaf2a8436c5c9ebfbe25ed47a952d679a1a7047e569299
---

# PO-Briefing: fix-509-auto-green-worktree

- **Spec:** docs/specs/fix-509-auto-green-worktree.md
- **Issue:** #509
- **Erstellt:** 2026-11-04

## Was gebaut wird

Die automatische GREEN-Freigabe funktioniert künftig auch in Arbeitsordnern (Worktrees), statt dort immer manuelle Freigabe zu verlangen.

## Definition of Done

Ein grünes Testprotokoll, das nur im Arbeitsordner liegt, führt zu automatischer Freigabe; alle bestehenden Tests bleiben grün.

## Wie geprüft wird

Automatische Tests prüfen Fund im Arbeitsordner, Rückfall aufs Hauptprojekt und Ablehnung von Verknüpfungen und Pfaden nach außen; echte Sitzungen nicht.

## Kritische Anmerkungen

- Fehlt die Datei im Arbeitsordner, zählt eine alte Datei im Hauptprojekt; Altersgrenze 30 Minuten fängt das meist ab.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
