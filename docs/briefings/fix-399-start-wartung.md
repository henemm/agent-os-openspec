---
spec_file: docs/specs/fix-399-start-wartung.md
spec_sha256: e030dedaf753b080f5fe34cdf1596e6f00cb8e30f6e27db487169e5bc822fce4
---

# PO-Briefing: fix-399-start-wartung

- **Spec:** docs/specs/fix-399-start-wartung.md
- **Issue:** #399
- **Erstellt:** 2026-10-08

## Was gebaut wird

Beim Sitzungsstart erledigt das System Wartung selbst; du siehst nie wieder Befehle zum Abtippen.

## Definition of Done

Nach dem Start sind veraltete Kurzbefehle aktuell, ein sauberer Projektstand ist nachgezogen, und sichtbar steht nur Klartext.

## Wie geprüft wird

Automatische Tests mit echten Git-Ordnern belegen jede Anforderung; ob es in anderen Projekten greift, zeigt erst das Plugin-Update.

## Kritische Anmerkungen

- Abweichung: Projekt-Kurzbefehle werden beim Start nicht aufgefrischt, nur Claude erhält einen Hinweis; dort bleibt Veraltetes zunächst liegen.
- Zusatz: Start kann bis zu 10 Sekunden dauern, Claudes erste Antwort wartet darauf.
- Der Start schreibt erstmals selbst; Fehler dabei sind unwahrscheinlich, aber in jeder Sitzung wirksam.

## Freigabe-Frage

Soll der Start Kurzbefehle und Projektstand selbst aktualisieren, obwohl er dafür bis zu 10 Sekunden brauchen darf?
