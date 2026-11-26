---
spec_file: docs/specs/fix-653-target-dir-flag.md
spec_sha256: 4f03956d34b0169e37ba4f09a5d9324823b2fee7611bf9eb7b8dae0a15aef712
spec_frozen_sha256: 46ae84bb2cd576528f7fba05789d07602c9f3b85b77a4bb0208a4688e146f950
---

# PO-Briefing: fix-653-target-dir-flag

- **Spec:** docs/specs/fix-653-target-dir-flag.md
- **Issue:** #653
- **Erstellt:** 2026-11-26

## Was gebaut wird

Das Sicherheitsgate erkennt Schreibzugriffe in den Haupt-Ordner oder auf die Gate-Konfiguration auch bei allen Schreibweisen des Zielordner-Flags.

## Definition of Done

Eine Sitzung, die per Kopieren, Verschieben oder Verlinken über irgendeine Zielordner-Schreibweise in den Haupt-Ordner schreibt, wird blockiert; eigener Arbeitsordner bleibt frei.

## Wie geprüft wird

Automatische Tests gegen das echte Gate belegen jede Schreibweise, Freifälle und bestehende Tests; nicht erfasst sind Umgehungen über Skripte oder Variablen.

## Kritische Anmerkungen

- Keine — Spec deckt die Anfrage ab, jede Anforderung hat einen Test.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
