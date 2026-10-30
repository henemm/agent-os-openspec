---
spec_file: docs/specs/fix-499-befehlsform-context-titel.md
spec_sha256: 6402a632718578c0e9a112dce9923266495ce3c82ea88328b27296ed1730696b
spec_frozen_sha256: 6392019062249765919c2d3ad80e78232014c1c17eface54dc0b0e4aa971bdcc
---

# PO-Briefing: fix-499-befehlsform-context-titel

- **Spec:** docs/specs/fix-499-befehlsform-context-titel.md
- **Issue:** #499 (zusammen mit #500 und #492)
- **Erstellt:** 2026-10-30

## Was gebaut wird

Automatisches Weiterarbeiten nach /clear tippt einen existierenden Befehl, /10-context führt bis zur Analyse durch, Issue-Titel erscheint zuverlässig.

## Definition of Done

Automatischer Folgebefehl läuft ohne „Unknown command", Abschluss-Befehl bleibt manuell, /10-context endet ohne Fehler in der Analysephase, Titel erscheint auch bei gesperrtem GitHub-Zugriff.

## Wie geprüft wird

Automatische Tests belegen jede Anforderung, ein Lauf im echten Herdr die Befehlsform; andere Umgebungen und Alias-Quellen bleiben ungeprüft.

## Kritische Anmerkungen

- Fußzeile zeigt weiter die Kurzform; ohne installierte Aliase lässt sie sich nicht direkt kopieren (Anzeige-Entscheidung, nicht verlangt).
- Der große Echtlauf (Szenario E) kostet Zeit und Geld und läuft nur gezielt.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
