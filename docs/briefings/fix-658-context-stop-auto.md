---
spec_file: docs/specs/fix-658-context-stop-auto.md
spec_sha256: ffddd024ec348fd2044bd04fdb629ba259d9d49ae7751b4b6b65b7e05453e906
spec_frozen_sha256: 289d80d311de7040b76e5fdda2b4058015cefaf62f9060e55e4f09c7149ee45f
---

# PO-Briefing: fix-658-context-stop-auto

- **Spec:** docs/specs/fix-658-context-stop-auto.md
- **Issue:** #658
- **Erstellt:** 2026-11-25

## Was gebaut wird

Im Auto-Modus ohne Herdr läuft die Phasenkette über die Kontext-Schwelle weiter, statt auf manuelles Neustarten zu warten.

## Definition of Done

Eine Cloud-Sitzung im Auto-Modus arbeitet über die Schwelle hinweg weiter; im Modus manual und unter Herdr-Auto-Clear hält die Kette weiterhin an.

## Wie geprüft wird

Automatische Tests belegen die Ausgabezeile und Hinweistexte in allen Modi; ob Claude sich daran hält, erzwingt kein Hook und bleibt ungeprüft.

## Kritische Anmerkungen

- Ohne Herdr wächst der Kontext ungebremst weiter (mehr Kosten); Ausgleich nur Teilagenten und automatische Komprimierung, bekannte Grenze, grundsätzlich Epic #649.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
