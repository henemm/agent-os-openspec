---
spec_file: docs/specs/feat-577-cloud-agents.md
spec_sha256: 8ecea3f89f00a95e0dc7f8a9851649e6b0f9c2cdf04b04f9c471d5ea5356d0e4
spec_frozen_sha256: 29fee13d0a928942ef147e6bed19995545875c4d55030098cd6afe447a2b5ed2
---

# PO-Briefing: issue-577-cloud-agents

- **Spec:** docs/specs/feat-577-cloud-agents.md
- **Issue:** #577
- **Erstellt:** 2026-11-11

## Was gebaut wird

Prüf- und Entwickler-Agenten laufen in Cloud-Sitzungen mit ihrem günstigeren Modell statt auf dem teuersten.

## Definition of Done

Cloud-Sitzungen finden alle Framework-Agenten mit richtigem Modell; Framework-Projekt und Konsumenten-Projekte erhalten sie automatisch, ein Release-Check meldet Abweichungen.

## Wie geprüft wird

Automatische Tests prüfen Kopieren, Aktualisieren und Befehlstexte; ob Claude im echten Betrieb den richtigen Agententyp startet, bleibt ungeprüft.

## Kritische Anmerkungen

- Lokal erscheinen Agenten doppelt in der Liste; Mehrkosten gering, gestartet wird nur einer.
- Konsumenten ohne Cloud-Anbindung bekommen keine Kopien; Cloud-Nutzer müssen einmal Setup ausführen und Dateien einchecken.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
