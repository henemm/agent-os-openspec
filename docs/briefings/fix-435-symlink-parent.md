---
spec_file: docs/specs/fix-435-symlink-parent.md
spec_sha256: b0936f7269e06e3b25c4beeb6a537113c5efdc9e0f710316dac04a4651cbadb9
spec_frozen_sha256: 899e9325554cd26ef10e7be291f948fc45468cfc11ca9d0a00039a2df5bcb4bb
---

# PO-Briefing: fix-435-symlink-parent

- **Spec:** docs/specs/fix-435-symlink-parent.md
- **Issue:** #435
- **Erstellt:** 2026-11-24

## Was gebaut wird

Im eigenen Arbeitsordner lassen sich Verknüpfungen zum Hauptordner (etwa Modulordner) löschen oder umbenennen, ohne „override“ tippen zu müssen.

## Definition of Done

Löschen, Umbenennen und Neusetzen des Verknüpfungs-Links klappt ohne „override“, während jedes Schreiben durch den Link in den Hauptordner weiter blockiert wird.

## Wie geprüft wird

Automatische Tests gegen den echten Schutz decken jede Anforderung ab, freie und weiterhin blockierte Befehle; Umgehung über Skripte bleibt ungeprüft.

## Kritische Anmerkungen

- Enger als verlangt: touch, ln und mv-Ziel sind nur mit bestimmten Schaltern frei, sonst schreiben sie durch den Link.
- Zusätzlich eingebaut: auch git rm, checkout und restore werden freigegeben; im Ticket nicht genannt.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
