---
spec_file: docs/specs/feat-461-issue-registrierung.md
spec_sha256: d6df22b23491bc570d75832f95a79ae0e35f0bff4921e833d17d8475c272f619
spec_frozen_sha256: 2e934a4af445a709549d8582cafaa9a95617e49572903f7ca4e2d1f3edf845ba
---

# PO-Briefing: feat-461-issue-registrierung

- **Spec:** docs/specs/feat-461-issue-registrierung.md
- **Issue:** #461
- **Erstellt:** 2026-11-24

## Was gebaut wird

Jede Sitzung trägt sich beim Start am Issue ein, sodass eine zweite Sitzung auf demselben Issue erkannt und gestoppt wird.

## Definition of Done

Ein Start am Issue hinterlässt sichtbar Ort, Name und Beginn; ein zweiter Start bricht mit verständlicher Meldung ab, wer wo arbeitet.

## Wie geprüft wird

Automatische Tests mit simuliertem GitHub belegen alle 15 Kriterien; echte Cloud-Sitzungen und echtes GitHub sind nicht getestet.

## Kritische Anmerkungen

- Ohne Netz startet die Arbeit trotzdem; der Doppelstart-Schutz fehlt dann bis zum Nachtragen (bewusst, dokumentiert).
- Der ursprüngliche Ticketteil (Dateien je Sitzung, Überschneidungen, Aufräumen) wird auf ein Folge-Ticket verschoben.
- Ob die Registrierung in Cloud-Sitzungen funktioniert, ist unbewiesen; dort droht nur eine Warnung.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
