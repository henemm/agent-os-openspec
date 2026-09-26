---
spec_file: docs/specs/fix-237-egress-guard-scratchpad.md
spec_sha256: 4967bb68bbb774f3689a19d42e43f2fb136094795a28e41c2603b8731cd48fad
---

# PO-Briefing: fix-237-egress-guard-scratchpad

- **Spec:** docs/specs/fix-237-egress-guard-scratchpad.md
- **Issue:** #237 (zusätzlich Issue #239 im selben Umbau mitgefixt)
- **Erstellt:** 2026-09-26

## Was gebaut wird

Ein Sicherheits-Wächter lässt harmlose Befehle (Nullgerät, eigenes Sitzungs-Scratchpad) künftig durch, statt sie fälschlich zu blockieren.

## Definition of Done

Alle Testfälle sind grün, echte Blockaden bleiben blockiert, und die Scratchpad-Erkennung ist per Programmcode-Analyse belegt — nicht per echtem Abfang.

## Wie geprüft wird

Automatisierte Tests decken jede Freigabe und jede weiterhin blockierte Lage ab; der komplette Testlauf hat keinen eigenen Test.

## Kritische Anmerkungen

- Der Nachweis, dass das Scratchpad tatsächlich erkannt wird, stammt aus Programmcode-Analyse, nicht aus einem echten abgefangenen Vorgang.
- Der Umbau wuchs während der Umsetzung: eine Nachprüfung fand zwei weitere Fehler im Scratchpad-Bereich, jetzt behoben.
- Zwei dabei entdeckte Randthemen wurden bewusst nicht mitgelöst, sondern als eigene Aufgaben #245 und #246 vorgemerkt.

## Freigabe-Frage

Sollen die Lockerungen freigegeben werden, obwohl der Scratchpad-Nachweis nur aus Programmcode-Analyse stammt und zwei Randfunde offen bleiben?
