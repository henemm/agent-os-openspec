---
spec_file: docs/specs/fix-schritte-ueberspringen.md
spec_sha256: 50509d4bfb5ac18098007b44f9906e0e1ac22ba5c394bc9271c292d61ed9a258
spec_frozen_sha256: 5c2b7c4c8524ee8e266957c77270f4565753daab6ba3a1138fe337be5bca6614
---

# PO-Briefing: fix-schritte-ueberspringen

- **Spec:** docs/specs/fix-schritte-ueberspringen.md
- **Issue:** keine
- **Erstellt:** 2026-11-06

## Was gebaut wird

Claude kann Arbeitsschritte nicht mehr unbemerkt überspringen: Befehlstext wird geliefert, Phasenwechsel prüft Nachweise, Fußzeilen-Meldung nennt den Grund.

## Definition of Done

Der Implementierungs-Befehl zeigt in Cloud-Sitzungen dieses Repos den Befehlstext, Wechsel zur Validierung ohne Adversary-Nachweis wird abgelehnt, Fußzeilen-Meldung nennt Phase und Grund.

## Wie geprüft wird

Automatische Tests belegen alle 15 Kriterien; ob der Befehlstext in einer echten Cloud-Sitzung ankommt, prüft nur eine manuelle Abnahme.

## Kritische Anmerkungen

- Die Anfrage verlangt Auslieferung oder Sperre der Phase; die Spec liefert nur einen Stopp-Text, keine technische Sperre.
- Plugin-Nutzer in Cloud-Sitzungen bekommen weiterhin keinen Befehlstext, nur den Stopp-Text; die eigentliche Ursache bleibt offen.
- Die Spec verschärft nur den Wechsel nach Phase 7; andere Übergänge bleiben ungeprüft, obwohl der PO ein allgemeines Problem vermutet.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
