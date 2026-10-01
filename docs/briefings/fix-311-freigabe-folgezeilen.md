---
spec_file: docs/specs/fix-311-freigabe-folgezeilen.md
spec_sha256: cf66083530e3f07c03be9c4b9584277514e0dc0a37c39f65ec0895a0fd0f0216
---

# PO-Briefing: fix-311-freigabe-folgezeilen

- **Spec:** docs/specs/fix-311-freigabe-folgezeilen.md
- **Issue:** #311
- **Erstellt:** 2026-10-01

## Was gebaut wird

Eine Freigabe wie „go“ gilt nicht mehr, wenn in einer Folgezeile eine Einschränkung („erst die Doku“, „später“) oder Frage steht.

## Definition of Done

Mehrzeilige Freigaben mit Einschränkung in Zeile 2 setzen nichts, der Nutzer sieht einen Hinweis; reine Freigaben mit harmlosem Zusatztext wirken weiter.

## Wie geprüft wird

Automatische Tests prüfen jede Beispielnachricht in beide Fehlerrichtungen; sie belegen nicht, dass unbekannte Einschränkungswörter erkannt werden.

## Kritische Anmerkungen

- Zusatz: Neue Bedingungswörter („falls“, „sobald“) und strengeres Override stehen in der Spec, das Ticket verlangte sie nicht.
- Echte Freigaben wie „go, Danke, bitte danach noch X prüfen“ werden verworfen; Wiederholung nötig.
- Nicht gelistete Einschränkungswörter bleiben unerkannt.

## Freigabe-Frage

Darf eine Freigabe bei Einschränkungen in Folgezeilen künftig streng verworfen werden, auch auf Kosten gelegentlicher Wiederholung von „go“?
