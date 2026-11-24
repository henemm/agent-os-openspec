---
spec_file: docs/specs/fix-435-symlink-parent.md
spec_sha256: f448aae09022d7d6b1809425c42f3fbb5c43ed3b1060a20a8e8b5bb9c282fe83
spec_frozen_sha256: 4574d40259dc28c0108396e2ef0271bd1e67b36800f0ca2db1aec0e89c5bba9b
---

# PO-Briefing: fix-435-symlink-parent

- **Spec:** docs/specs/fix-435-symlink-parent.md
- **Issue:** #435
- **Erstellt:** 2026-11-24

## Was gebaut wird

Einen eigenen Verknüpfungs-Ordner im Arbeitsbereich darf man löschen, umbenennen oder neu setzen, ohne Fehlalarm des Schutzes.

## Definition of Done

Löschen, Umbenennen und Neusetzen eines solchen Links läuft ohne Sperre; Schreiben durch den Link in den Hauptordner wird weiterhin blockiert.

## Wie geprüft wird

Automatische Tests am echten Schutz belegen freie und weiter gesperrte Fälle; Umgehungen per Skript werden nicht erfasst.

## Kritische Anmerkungen

- Ein Link namens node_modules bleibt durch eine andere Sperre weiter blockiert; das löst erst Folge-Ticket #652.
- Befehle wie sed -i oder truncate auf einen Link bleiben bewusst gesperrt; Ausweg ist "override".

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
