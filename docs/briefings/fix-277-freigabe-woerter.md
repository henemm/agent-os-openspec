---
spec_file: docs/specs/fix-277-freigabe-woerter.md
spec_sha256: e4f3eb7a15ca63a57b76b60ad4c8fcb44586ed95f089283036a9fe5daaac97a6
---

# PO-Briefing: fix-277-freigabe-woerter

- **Spec:** docs/specs/fix-277-freigabe-woerter.md
- **Issue:** #277 (mit #310)
- **Erstellt:** 2026-10-01

## Was gebaut wird

Sperrmeldung nennt nur wirksame Freigabe-Wörter, Einschränkungen wie „erst noch" heben Freigaben auf, Hook-Rückmeldungen werden sichtbar.

## Definition of Done

Sperrmeldung nennt nur wirksame Wörter, „go, erst noch die Doku" gibt nicht frei, verworfene Freigaben melden sich sichtbar.

## Wie geprüft wird

Automatische Tests prüfen Wortlisten, Meldungstexte und Ausgabeformat; dass die Meldung im echten Terminal erscheint, beweisen sie nicht.

## Kritische Anmerkungen

- Issue-Texte nicht lesbar; geprüft nur gegen Kontext-Dokument, nicht gegen Originalwortlaut.
- „approved" bleibt in phase6 wirkungslos, nur „go" gilt — Abweichung von der Issue-Empfehlung.
- Wortliste endlich: unbekannte Einschränkungen geben weiter frei, echte Sätze mit „noch/wenn/war" werden verworfen.

## Freigabe-Frage

Genügt dir, dass in phase6 nur „go" freigibt und Einschränkungswörter bei jeder Freigabeart greifen?
