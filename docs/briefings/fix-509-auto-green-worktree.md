---
spec_file: docs/specs/fix-509-auto-green-worktree.md
spec_sha256: 6d2b40556c4d4a1671849d8977dc11a7721298d17567392e4f338db6cd871e41
spec_frozen_sha256: fe18717ed99a4d9ed6dd7dd06891a0b854ba44f5d4e5e24f2a2aeb9903802355
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
