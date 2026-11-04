---
spec_file: docs/specs/fix-509-auto-green-worktree.md
spec_sha256: 1c6c2409aeabd469959cca1bb3caee915b8bf78f8da29b1e7e86cdad3e9f7701
spec_frozen_sha256: 0ab2dd8d6727a860afe6f45046f3fb58ab01b576d856fa938fdfda1bf7f1e8b7
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
