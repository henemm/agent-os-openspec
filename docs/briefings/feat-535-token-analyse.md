---
spec_file: docs/specs/feat-535-token-analyse.md
spec_sha256: c98ca5f86b0e6282615e669f537ba4f6f2ba51abd4e0c297cf5f3425397859a8
spec_frozen_sha256: 5c309e24890bc705d4a0d686a2813f0638f3e1fa067e0a7aad838bc78990a71c
---

# PO-Briefing: feat-535-token-analyse

- **Spec:** docs/specs/feat-535-token-analyse.md
- **Issue:** #535
- **Erstellt:** 2026-11-12

## Was gebaut wird

Ein Auswertungswerkzeug zeigt, welche Tätigkeit wie viel Token-Kostenanteil verbraucht, auch aufgeteilt nach Kontextgröße, für alle Projekte.

## Definition of Done

Ein Aufruf listet die Projekte und zeigt je Tätigkeit den Kostenanteil, ohne Protokollinhalte auszugeben; doppelt gespeicherte Antworten zählen einmal.

## Wie geprüft wird

Automatische Tests mit künstlichen Protokollen belegen Zuordnung, Zählung, Gewichtung und Datenschutz; echte Nutzerprotokolle und die Treffsicherheit der Zuordnung werden nicht geprüft.

## Kritische Anmerkungen

- Keine — Spec deckt die Anfrage ab, jede Anforderung hat einen Test.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
