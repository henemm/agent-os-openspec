---
spec_file: docs/specs/docs-678-commands-slim-3.md
spec_sha256: 94c18b1626a33a7242c86f18d7cddf117d2e802a8b186436dd2733d5e8da5c61
spec_frozen_sha256: c7f7c22aa14ec54a6519e97ab49a8c8a170f79b28549ee907007122f52b62bf3
---

# PO-Briefing: docs-678-commands-slim-3

- **Spec:** docs/specs/docs-678-commands-slim-3.md
- **Issue:** #678
- **Erstellt:** 2026-11-26

## Was gebaut wird

Elf weitere Befehlstexte werden gekürzt, Hintergrundwissen zieht in Begleitdokumente um, damit alle Befehle zusammen höchstens 83 KB messen.

## Definition of Done

Gesamtgröße höchstens 83 000 Bytes, Größenwächter je Befehl grün, Begleitdokumente vollständig, Version 4.26.2 veröffentlicht, Messung im Sammel-Issue.

## Wie geprüft wird

Automatische Größentests und die bestehende Testsuite belegen Budgets und unveränderte Pflichtwortlaute; ob die gekürzten Anweisungen im Alltag gleich gut wirken, bleibt ungeprüft.

## Kritische Anmerkungen

- Zusatz zum Ticket: 60-validate bekommt einen zweiten Kürzungsdurchgang, sonst wäre das Gesamtziel nicht erreichbar; Spec begründet das, Folge: keine.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
