---
spec_file: docs/specs/feat-620-zeitschaetzung.md
spec_sha256: ecfb00ab8347611d2ff230e8e9cfbc5323d3b51f703a06984a59cecffa24d706
spec_frozen_sha256: 28c6774057d017861bd8b24a6b486d9fa2eb3378983d37bef4d857960966b620
---

# PO-Briefing: feat-620-zeitschaetzung

- **Spec:** docs/specs/feat-620-zeitschaetzung.md
- **Issue:** #620
- **Erstellt:** 2026-11-21

## Was gebaut wird

Der Plan-Pane zeigt Startzeit, geschätzte Dauer als Spanne und prognostiziertes Ende, gelernt aus früheren Workflows und beim Start vom Intake genannt.

## Definition of Done

Beim Start nennt der Intake eine Zeitspanne, der rechte Bereich zeigt Start, Dauer und Ende, und die Spanne wird mit Fortschritt enger.

## Wie geprüft wird

Automatische Tests belegen alle zwölf Kriterien samt Abschaltung und Fehlerfall; ob die Schätzungen in der Praxis treffen, wird nicht geprüft.

## Kritische Anmerkungen

- Ohne frühere Workflows (Cloud-Sitzungen) gelten grobe Startwerte (Feature 1–4 Stunden); die Anzeige kennzeichnet das als "Startwert".
- Zusätzlich eingebaut, nicht verlangt: Vergleichszeile "Schätzung vs. Ist" im Rückblick, als Lernnachweis.
- Wartezeiten und Nächte zählen mit; das Ende berücksichtigt weder Nacht noch Wochenende.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
