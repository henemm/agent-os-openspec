---
spec_file: docs/specs/fix-513-issue-nummer.md
spec_sha256: b59a76ae6b5afb107bf21bb468e13fa73669a6915258051c2da42d3beb004f21
spec_frozen_sha256: 0e13de788a2384b2a365039d1cb0c166d1f7b7d8353dbb67a567bd5ce5a3a9d8
---

# PO-Briefing: fix-513-issue-nummer

- **Spec:** docs/specs/fix-513-issue-nummer.md
- **Issue:** #513
- **Erstellt:** 2026-11-04

## Was gebaut wird

Workflows zeigen die richtige Issue-Nummer statt einer zufälligen Ziffer, und der Test-Rot-Schritt schaltet korrekt weiter.

## Definition of Done

Ein Workflow namens i18n-a2-e2e-2681 zeigt in Fußzeile und Statuszeile #2681, und alle bestehenden Tests bleiben grün.

## Wie geprüft wird

Automatische Tests prüfen Nummernregel, Start mit Nummer, Suche, Sitzungsregister und Befehlstext; nicht geprüft wird, ob ein Modell den Rot-Schritt wirklich ausführt.

## Kritische Anmerkungen

- Laufende Workflows mit mehrdeutigem Namen verlieren ihre Nummer, bis jemand sie von Hand setzt; vorher zeigten sie oft eine falsche.
- Teile 3–5 des Tickets (Abgleich, Phasen überspringen, Ausweg im Fußzeilen-Gate) fehlen bewusst; Folge-Issue nötig.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
