---
spec_file: docs/specs/fix-528-ship-default-branch.md
spec_sha256: f71dff50690528e1e464f06032480759e535df47a04a3c9c0dcb80cd93f9a2f7
spec_frozen_sha256: cf6f54349468f7f3c351a43f40f4581fee6e14ffd64a8d73a76a1a7134891595
---

# PO-Briefing: fix-528-ship-default-branch

- **Spec:** docs/specs/fix-528-ship-default-branch.md
- **Issue:** #528
- **Erstellt:** 2026-11-06

## Was gebaut wird

Claude liefert auch vom Hauptzweig aus selbst aus: eigener Zweig, Pull-Request, Prüfung, Merge – ohne Git-Aufgabe für den PO.

## Definition of Done

Bei automatischem Ausliefern auf dem Hauptzweig beschreibt die Anleitung einen eigenen Zweig vor dem Commit, nie eine Git-Aufgabe für den PO.

## Wie geprüft wird

Automatische Texttests belegen jede Anforderung in der Anleitung; ob Claude sie im echten Lauf befolgt, wird nicht geprüft.

## Kritische Anmerkungen

- Schon vorhandene lokale Commits auf dem Hauptzweig landen im neuen Zweig und damit im Pull-Request.
- Der lokale Hauptzweig läuft nach dem Merge vom Remote auseinander; er wird bewusst nicht zurückgesetzt.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
