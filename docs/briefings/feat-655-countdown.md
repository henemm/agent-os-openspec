---
spec_file: docs/specs/feat-655-countdown.md
spec_sha256: 9fa7ef5bf677145a71fa708dea79aebdc99f1d2e6b636573639348229adf89ff
spec_frozen_sha256: 8d9d5d9f4eee9cb6768779851c45b3edf4b136d73fe12e8dfaf1faa1f8507f72
---

# PO-Briefing: feat-655-countdown

- **Spec:** docs/specs/feat-655-countdown.md
- **Issue:** #655
- **Erstellt:** 2026-11-25

## Was gebaut wird

Die Seitenleiste zeigt zusätzlich die verbleibende Zeit: nach der Freigabe als Spanne, vor der Freigabe als Countdown.

## Definition of Done

Die Seitenleiste zeigt „Noch ca. 30–75 Min“ nach der Freigabe und „Noch ca. 45 Min bis Freigabe“ davor; die Chat-Ausgabe bleibt unverändert.

## Wie geprüft wird

Automatische Tests mit festem Zeitpunkt belegen jede Anzeigeform, die Fälle ohne Zeile und den schmalen Pane; echtes Aussehen in Herdr bleibt ungeprüft.

## Kritische Anmerkungen

- Zusatz: Ab zwei Stunden wechselt die Anzeige auf Stunden („ca. 1–3,5 h“); das hast du nicht verlangt, es ist nur Darstellung.
- Der Wert springt in Viertelstunden-Schritten statt minütlich zu laufen; die Spec nennt das als gewollte Einschränkung.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
