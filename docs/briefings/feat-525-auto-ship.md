---
spec_file: docs/specs/feat-525-auto-ship.md
spec_sha256: 818a0f26493a3f932bd146f2b19ba515249b9097efb05f01f5f2d1af60209b25
spec_frozen_sha256: c135ffe9d0ff647da474baf5702f1c0cdb5e698f40cc99e903c890a73d7f7447
---

# PO-Briefing: feat-525-auto-ship

- **Spec:** docs/specs/feat-525-auto-ship.md
- **Issue:** #525
- **Erstellt:** 2026-11-05

## Was gebaut wird

Im Auto-Modus erstellt Claude den PR, wartet auf grüne Prüfung und mergt selbst; der PO bekommt nie einen Git-Auftrag.

## Definition of Done

Abschlussmeldung und Du-Zeile nennen im Auto-Modus keinen Git-Schritt; Änderung ist gemergt oder Problem wird in Alltagssprache gemeldet; Schalter schaltet ab.

## Wie geprüft wird

Automatische Tests prüfen Schalter und Anweisungstext; ob Claude sich im echten Lauf daran hält, beweisen sie nicht.

## Kritische Anmerkungen

- Der Merge geschieht automatisch in jedem Auto-Modus-Projekt; Schutz nur durch Schalter und Schutzregeln des Repos.
- Ohne CI-Prüfung im Repo mergt Claude nach lokalen Tests; Deploy bleibt weiter Ihre Entscheidung.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
