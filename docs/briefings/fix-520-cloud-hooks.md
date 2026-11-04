---
spec_file: docs/specs/fix-520-cloud-hooks.md
spec_sha256: c029b7f1c75ad78f5010cf924b2a1678c52fd4b58efb2ea7ca00cf1d9749bfc4
spec_frozen_sha256: 82bf123f8f6f92195ddbdecb99ce91be92d25375f23901bce941c58878618ffe
---

# PO-Briefing: fix-520-cloud-hooks

- **Spec:** docs/specs/fix-520-cloud-hooks.md
- **Issue:** #520
- **Erstellt:** 2026-11-04

## Was gebaut wird

Cloud-Sitzungen dieses Repos laufen mit denselben Gates wie lokale Sitzungen, lokal laufen die Gates weiterhin nur einmal.

## Definition of Done

Eine frische Cloud-Sitzung blockt nachweislich per Gate, lokal läuft nichts doppelt, und die README beschreibt den Weg.

## Wie geprüft wird

Automatische Tests belegen Erzeugung, Abgleich und lokales Verhalten; ob ein Gate in echter Cloud blockt, zeigt erst eine Stichprobe nach dem Merge.

## Kritische Anmerkungen

- Ticket verlangt Gates auch für Konsumenten-Projekte; die Spec sichert nur dieses Repo, Konsumenten mit Plugin bleiben in der Cloud ungeschützt.
- Zusätzlich entfällt in der Cloud die Worktree-Pflicht für alle Projekte; das verlangte niemand, ist aber Voraussetzung.

## Freigabe-Frage

Soll diese Änderung nur dieses Repo absichern, während Konsumenten-Projekte in einem Folge-Ticket kommen?

## Ampel

Ampel: rot
