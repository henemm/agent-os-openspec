---
spec_file: docs/specs/fix-131-adversary-dialog-hash-binding.md
spec_sha256: e62ceb00fb7113cad514d0c7e7978f28bc25e7eef68d5b88a8f0f78eaa025d84
---

# PO-Briefing: fix-131-adversary-dialog-hash-binding

- **Spec:** docs/specs/fix-131-adversary-dialog-hash-binding.md
- **Issue:** #131
- **Erstellt:** 2026-09-23

## Was gebaut wird

Das Test-Protokoll des Adversary gilt heute nur 60 Minuten. Künftig zählt eine Prüfsumme: Bleiben die untersuchten Dateien unverändert, bleibt das Protokoll gültig — egal wie alt.

## Definition of Done

Ein Protokoll ist gültig, solange die geprüften Dateien seither unverändert sind — unabhängig vom Alter. Ändert sich eine, muss neu getestet werden.

## Wie geprüft wird

Automatisierte Tests (erst nach Freigabe geschrieben) prüfen: altes Protokoll bleibt gültig, geänderter oder fehlender Prüfblock wird abgelehnt. Nicht geprüft: ob Agenten den Stempel-Schritt zuverlässig ausführen.

## Kritische Anmerkungen

- Die Datei-Liste kommt aus den Zitaten des Prüfers, nicht wie im Issue vorgeschlagen aus Spec oder Workflow-Liste — nachvollziehbar, aber eine Abweichung. Folge: eine geänderte, nie zitierte Datei bleibt unsichtbar.
- Die Alters-Grenze fällt ersatzlos weg: Ein Protokoll bleibt unbegrenzt gültig, solange die zitierten Dateien unverändert bleiben.
- Die im Issue erwähnte zweite Prüf-Runde ist bewusst nicht Teil dieser Änderung — bei Bedarf separat zu beauftragen.

## Freigabe-Frage

Soll die Alters-Frist wie beschrieben durch die Datei-Prüfsumme ersetzt werden?
