---
spec_file: docs/specs/fix-134-approval-marker-binding.md
spec_sha256: 4751ba4671c1e980ffb6d96b3f63e855e03be478589d118f8b697aeac8260212
---

# PO-Briefing: fix-134-approval-marker-binding

- **Spec:** docs/specs/fix-134-approval-marker-binding.md
- **Issue:** #134
- **Erstellt:** 2026-09-30

## Was gebaut wird

Eine Freigabe zur Weiterarbeit gilt künftig nur noch für den Prüflauf, in dem sie erteilt wurde.

## Definition of Done

Eine alte Freigabe entsperrt keinen neuen, gleichnamigen Lauf mehr; die normale Freigabe per Zuruf bleibt unverändert.

## Wie geprüft wird

Automatische Tests prüfen passende, fehlende und veraltete Freigaben, beweisen aber nicht, dass niemand den Marker von Hand fälscht.

## Kritische Anmerkungen

- Ein von Hand nachgebauter Marker mit passendem Zeitstempel gilt weiterhin als echte Freigabe.
- Neun bereits vorhandene alte Freigabe-Dateien bleiben unaufgeräumt liegen, das folgt separat.
- Zwei zusätzliche Prüfpunkte gehen über die fünf ursprünglich verlangten hinaus.

## Freigabe-Frage

Reicht dieser Schutz, oder soll zusätzlich verhindert werden, dass jemand eine Freigabe-Datei von Hand nachbaut?
