---
spec_file: docs/specs/fix-550-endzustand.md
spec_sha256: 554f3126c49d48a99e8336caf963f2d5f25ff875b0668bd5cd78bc15ccb03509
spec_frozen_sha256: ed715e774ade4860994cdf175f0a446d4b00a336ce6f177d3ef0c41508bd8b2d
---

# PO-Briefing: fix-550-endzustand

- **Spec:** docs/specs/fix-550-endzustand.md
- **Issue:** #550
- **Erstellt:** 2026-11-09

## Was gebaut wird

Jede Abschlussmeldung, Plan-Ansicht und Seitenleiste zeigen genau einen von drei Zuständen: erledigt, wartet, du musst handeln.

## Definition of Done

Ein Workflow endet in Chat, Plan und Seitenleiste in genau einem der drei Zustände; ohne Deploy steht dort „Erledigt“.

## Wie geprüft wird

Automatische Tests prüfen alle Fälle, auch Warten auf CI oder Agent; nicht geprüft wird, ob Claude die Zeile wörtlich ausgibt.

## Kritische Anmerkungen

- Das Warten auf CI oder Agent zeigt nur, wenn Claude es vorher selbst einträgt; vergisst er es, steht ein Pflicht-Schritt.
- Projekte ohne Deploy-Konfiguration bekommen nie mehr einen Deploy-Schritt; fehlgeschlagener Deploy ist immer Aufgabe für dich, nie für Claude.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
