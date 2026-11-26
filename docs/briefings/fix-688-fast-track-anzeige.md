---
spec_file: docs/specs/infra/fix-688-fast-track-anzeige.md
spec_sha256: bb38ec82448121b5d6d98bb583f33bf2d605ba4aefb3a30f045343141cca1bfe
spec_frozen_sha256: 6b080e0daae4c5654870a5ed73a005d053afd189589fcf16ab3349951062e690
---

# PO-Briefing: fix-688-fast-track-anzeige

- **Spec:** docs/specs/infra/fix-688-fast-track-anzeige.md
- **Issue:** #688
- **Erstellt:** 2026-11-26

## Was gebaut wird

Im kleinen Ablauf nennt die Anzeige nach der Freigabe den richtigen nächsten Schritt, und bei Auto-Freigabe steht „Läuft noch“ statt „Du“.

## Definition of Done

Nach Freigabe zeigen Seitenleiste und Plan im kleinen Ablauf „Implementieren“, bei Auto-Freigabe ohne Aufforderung an dich; der große Ablauf bleibt unverändert.

## Wie geprüft wird

Automatische Tests belegen jede Anforderung samt Fußzeilen-Prüfung und Seitenleiste; die Gesamtsuite muss grün bleiben, echte Anzeige im Betrieb wird nicht eigens geprüft.

## Kritische Anmerkungen

- Nach manueller Freigabe im Auto-Modus steht weiter „Du“ im Plan; die Spec nennt das als bewusste Einschränkung.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
