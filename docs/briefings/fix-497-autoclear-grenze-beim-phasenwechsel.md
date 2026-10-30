---
spec_file: docs/specs/fix-497-autoclear-grenze-beim-phasenwechsel.md
spec_sha256: e375a8887ac6e6455aad340870ac2943b2ee9187314dd16813b175a6ac32e265
spec_frozen_sha256: c5dfd01472ede886836d968a12d877373f2f41a0dc1feccc8260826b9bb9d60b
---

# PO-Briefing: fix-497-autoclear-grenze-beim-phasenwechsel

- **Spec:** docs/specs/fix-497-autoclear-grenze-beim-phasenwechsel.md
- **Issue:** #497
- **Erstellt:** 2026-10-30

## Was gebaut wird

Beim Phasenwechsel merkt sich das System die Phasengrenze selbst, damit der Kontext automatisch geleert wird und der Folgebefehl startet.

## Definition of Done

Ein echter Durchlauf mit großem Modell leert den Kontext und startet den Folgebefehl ohne Zusatzaufruf; alle bestehenden Tests bleiben grün.

## Wie geprüft wird

Automatische Tests belegen Vermerk, Fehlerfälle und Zeitzone; der Praxislauf in echter Umgebung wird per Skript belegt, nicht im Standardtestlauf.

## Kritische Anmerkungen

- Der Praxislauf mit großem Modell läuft nur auf Anweisung und kostet wenige Dollar; der Beleg muss vor Abschluss vorliegen.
- Ein manueller Phasenwechsel an einer Grenze kann ebenfalls das Leeren auslösen; dokumentiertes, begrenztes Restrisiko.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
