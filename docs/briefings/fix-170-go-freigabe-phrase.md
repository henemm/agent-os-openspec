---
spec_file: docs/specs/fix-170-go-freigabe-phrase.md
spec_sha256: 62e9ed9692615a2e1a7547f92f0c98ef9593fc6e762844486ea9507fad29728a
---

# PO-Briefing: fix-170-go-freigabe-phrase

- **Spec:** docs/specs/fix-170-go-freigabe-phrase.md
- **Issue:** #170
- **Erstellt:** 2026-09-21

## Was gebaut wird

Ein beiläufiges „go“ oder „approved“ in einer Diskussionsnachricht löst keine Freigabe mehr aus; nur kurze, echte Freigaben zählen.

## Definition of Done

Die Issue-Nachricht gibt nichts frei, echte Freigaben wie „go, passt“ wirken weiter, jede Freigabe nennt ihren Auslöser sichtbar.

## Wie geprüft wird

Tests spielen Diskussionssätze und echte Freigaben durch und prüfen die Meldungen; ungeprüft bleiben unvorhergesehene Formulierungen.

## Kritische Anmerkungen

- Abweichung vom Issue („höchstens 3 Wörter“): Stattdessen Satzbau-Regel mit bis zu zwei Zusatzwörtern, einem Füllwort und ignorierten Klammern.
- Restrisiko: Kurze Diskussionssätze wie „Go ist unglücklich“ oder „Go back“ gelten weiterhin als Freigabe.
- Zusatz über das Issue hinaus: Hinweis bei verworfenem Stichwort und strengere Override-Regel (nur das Wort allein).

## Freigabe-Frage

Darf „Go ist unglücklich“ weiterhin freigeben, damit natürliche Freigaben wie „Passt für mich“ funktionieren?
