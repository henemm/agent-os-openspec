---
spec_file: docs/specs/feat-510-plan-deploy-status.md
spec_sha256: fb8fa774dbc38275a14c04591850c1d9145df18e9b1cd3f64c60a384d726cdc1
spec_frozen_sha256: 14a8a5d5d447663df12e05e0846a03427f5d376fd58b36dce67fbb6fe4e20446
---

# PO-Briefing: feat-510-plan-deploy-status

- **Spec:** docs/specs/feat-510-plan-deploy-status.md
- **Issue:** #510
- **Erstellt:** 2026-11-02

## Was gebaut wird

Der Plan zeigt Deploy erst als erledigt, wenn die Nachprüfung nach dem Deploy erfolgreich war.

## Definition of Done

Nach Abschluss bleibt Deploy im Plan offen und wird erst nach erfolgreich geprüftem Deploy abgehakt; Phase 8 heißt „Code fertig“.

## Wie geprüft wird

Automatische Tests prüfen Anzeige und Statusbefehl; ob der Deploy-Befehl den Marker wirklich setzt, prüft nur Ihre Abnahme.

## Kritische Anmerkungen

- Test für Deploy-Befehl liest nur dessen Anleitungstext; dass Claude die Statusmeldungen im echten Lauf absetzt, beweist nur Ihre Abnahme.
- Bereits archivierte Workflows und Projekte ohne Deploy-Einstellung zeigen dauerhaft „Deploy offen“ bzw. „nicht eingerichtet“, bis manuell gesetzt.
- Wer am Deploy-Befehl vorbei deployt, muss den Marker selbst setzen, sonst bleibt der Plan dauerhaft offen.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
