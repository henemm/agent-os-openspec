---
spec_file: docs/specs/feat-577-cloud-agents.md
spec_sha256: 6a580849474d8caa517b20bd1a6a45c7f14dd1eef0a05a0b0e50cc5108dda34d
spec_frozen_sha256: 1ea0ce9c5a91251a0cee494c386df68203bf2a14777f18fd9a1d8fcde3ea2a8e
---

# PO-Briefing: issue-577-cloud-agents

- **Spec:** docs/specs/feat-577-cloud-agents.md
- **Issue:** #577
- **Erstellt:** 2026-11-11

## Was gebaut wird

Prüf- und Hilfs-Agenten laufen in Cloud-Sitzungen auf ihrem vorgesehenen günstigeren Modell statt auf dem teuersten.

## Definition of Done

Alle Agenten liegen in Cloud und Konsumentenprojekten bereit, jeder Agent-Start nennt sein Modell, und alle automatischen Tests sind grün.

## Wie geprüft wird

Tests prüfen Kopien, Aufräumen, Setup-Läufe und Befehlstexte; dass Claude zur Laufzeit wirklich das günstigere Modell wählt, belegen sie nicht.

## Kritische Anmerkungen

- Doppelte Agenten lokal werden nicht verhindert, nur Doppelstarts pro Aufruf; die Agentenliste wird länger, das kostet etwas Kontext.
- Der Entwickler-Agent bleibt auf dem teuersten Modell; dort entfällt nur das Nachlesen der Definition.
- Ohne Cloud-Anbindung gibt es keine Kopien; Cloud-Nutzer führen einmal das Setup aus.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
