---
spec_file: docs/specs/fix-259-adversary-diff-binding.md
spec_sha256: 89babfe508e3740ba85d22b35d12f9d0590e4066d934a2e625381571ccc9e007
---

# PO-Briefing: fix-259-adversary-diff-binding

- **Spec:** docs/specs/fix-259-adversary-diff-binding.md
- **Issue:** #259
- **Erstellt:** 2026-09-27

## Was gebaut wird

Eine Freigabe zählt nur noch, wenn die unabhängige Prüfung wirklich die geänderte Arbeit selbst geprüft hat.

## Definition of Done

Ein Test zeigt: Freigaben mit fremdem oder unpassendem Prüfprotokoll werden abgelehnt, vollständig passende weiterhin akzeptiert.

## Wie geprüft wird

Automatisierte Tests simulieren die Fehlerbeispiele; sie beweisen nicht, dass niemand die Prüfung selbst schreibt und abzeichnet.

## Kritische Anmerkungen

- Der Umfang übersteigt die Schätzung 'Medium' klar: deutlich mehr Code und Tests als das übliche Limit.
- Schlägt die Prüfung bei einer Freigabe fehl, gibt es keinen Einzel-Ausweg — nur alles abschalten oder abbrechen.
- Wer die Prüfung selbst schreibt und abzeichnet, kommt weiterhin durch; erkannt werden nur fremde, unpassende Protokolle.

## Freigabe-Frage

Trägst du den höheren Aufwand für diese stärkere Prüfung, oder soll der Umfang vorher reduziert werden?
