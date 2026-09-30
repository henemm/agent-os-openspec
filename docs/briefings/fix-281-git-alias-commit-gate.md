---
spec_file: docs/specs/fix-281-git-alias-commit-gate.md
spec_sha256: 19fcfb6e0a6e0d98f91d46596898ceac727962943e92b157169eb85e7431a2cb
---

# PO-Briefing: fix-281-git-alias-commit-gate

- **Spec:** docs/specs/fix-281-git-alias-commit-gate.md
- **Issue:** #281
- **Erstellt:** 2026-09-30

## Was gebaut wird

Die Prüfung vor einem Commit lässt sich nicht mehr per Git-Abkürzung umgehen.

## Definition of Done

Ein Commit per Git-Abkürzung wird ohne bestandene Prüfung abgewiesen, gängige Git-Befehle laufen unverändert.

## Wie geprüft wird

Alle 17 Kriterien haben automatische Tests; andere Umgehungen (Merge, Cherry-Pick, Shell-Aufrufe mit kombinierten Optionen) bleiben ungeprüft.

## Kritische Anmerkungen

- Zusatz: Unklare Git-Aufrufe (Variable, sudo) gelten als Commit und können gelegentlich fälschlich blocken.
- Umfang: rund 340 statt höchstens 250 Zeilen Code; Freigabe schließt die Überschreitung ein.
- Abweichung vom Ticket: Verweis in der älteren Spezifikation (#259) fehlt (eingefroren); dort bleibt die überholte Aussage.

## Freigabe-Frage

Soll die Prüfung Git-Abkürzungen erfassen, obwohl harmlose Aufrufe gelegentlich blocken und andere Umgehungen offen bleiben?
