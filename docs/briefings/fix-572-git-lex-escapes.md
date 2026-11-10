---
spec_file: docs/specs/fix-572-git-lex-escapes.md
spec_sha256: c2fcc92279286dc90e740c1cbe10f6d5f24692dd30fc13d5003a06031f5d1971
spec_frozen_sha256: 9b7f8ba333e5145322784d4743029f3704426bf695ddc248737b973cf8e5a060
---

# PO-Briefing: fix-572-git-lex-escapes

- **Spec:** docs/specs/fix-572-git-lex-escapes.md
- **Issue:** #572
- **Erstellt:** 2026-11-10

## Was gebaut wird

Das Commit-Gate erkennt versteckte Commits und gequotete Sonderzeichen so, wie die Shell sie liest.

## Definition of Done

Der Trick aus dem Ticket umgeht das Commit-Gate nicht mehr, und alle automatischen Tests, auch gegen echtes bash, laufen grün.

## Wie geprüft wird

Automatische Tests, teils mit echter bash im Testrepo, belegen jede Anforderung, nicht aber Befehle in Kommandosubstitution (eigenes Ticket 573).

## Kritische Anmerkungen

- Ticket schlug Abbruch bei Verdacht oder sauberes Entfernen vor; gewählt ist eine Vorstufe, Ergebnis gleichwertig.
- Zusatz aus Ticket 563 (gequotete Sonderzeichen) ist enthalten, ausdrücklich beauftragt.
- Hohes Risiko, da Kern-Gate aller Projekte; Fehlalarme möglich, Regressionslauf sichert ab.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
