---
spec_file: docs/specs/docs-674-commands-slim.md
spec_sha256: 218a6e6254954f2997ab1a25bdaf32e9f7a53637e248303146f0632f007f9bb9
spec_frozen_sha256: 3b4f8746274eec385e6bcc02f282334dc7c9e603c4c6296e5762bc4730371dc1
---

# PO-Briefing: docs-674-commands-slim

- **Spec:** docs/specs/docs-674-commands-slim.md
- **Issue:** #674
- **Erstellt:** 2026-11-26

## Was gebaut wird

Die zwei größten Befehlstexte werden um rund ein Drittel kürzer, Hintergrundwissen wandert in die Doku.

## Definition of Done

Beide Befehle bleiben unter ihrem Größenlimit, ihr Ablauf ist unverändert, die gesamte Testsuite läuft grün und Version 4.25.5 ist veröffentlicht.

## Wie geprüft wird

Tests messen Dateigrößen, Verweise und Skill-Abgleich; dass der Ablauf inhaltlich gleich bleibt, belegen nur die bestehenden Wortlaut-Tests.

## Kritische Anmerkungen

- Ticket verlangt −40 % gesamt; dieser Schnitt liefert nur rund −30 % bei zwei Dateien, Rest in #677/#678.
- Hook-Hinweise und Marker-Block bleiben in diesem Schnitt unberührt (#679).

## Freigabe-Frage

Akzeptierst du, dass das Ticket in drei Teilschritte zerlegt wird und dieser Schritt das −40-%-Ziel noch nicht erreicht?

## Ampel

Ampel: rot
