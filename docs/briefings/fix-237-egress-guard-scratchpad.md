---
spec_file: docs/specs/fix-237-egress-guard-scratchpad.md
spec_sha256: 97ed005fad683531df75923a5f862c83b7e115afc6f82e84ef20954f58dcfdcb
---

# PO-Briefing: fix-237-egress-guard-scratchpad

- **Spec:** docs/specs/fix-237-egress-guard-scratchpad.md
- **Issue:** #237 (zusätzlich Issue #239 im selben Umbau mitgefixt)
- **Erstellt:** 2026-09-26

## Was gebaut wird

Ein Sicherheits-Wächter blockiert seltener zu Unrecht: Nullgerät, Standardkanäle und das eigene Sitzungs-Scratchpad werden künftig erlaubt.

## Definition of Done

Alle festgelegten Testfälle laufen grün, echte Blockaden bleiben blockiert, der Praxisnachweis fürs Scratchpad folgt erst danach.

## Wie geprüft wird

Automatisierte Tests belegen jede Freigabe einzeln; ob das Scratchpad in echten Sitzungen erkannt wird, bleibt unbewiesen.

## Kritische Anmerkungen

- Das zentrale Versprechen — automatische Scratchpad-Freigabe — ist unbewiesen; der Nachweis folgt erst nach der Umsetzung, nicht vorher.
- Für 14 der 15 Prüfkriterien ist der zugehörige Test bei Freigabe noch nicht benannt, nur eines ist konkret verknüpft.
- Die Lockerung betrifft eine Sicherheitsschranke, die in jedem Projekt mit diesem Framework aktiv ist, nicht nur hier.

## Freigabe-Frage

Sollen die drei Lockerungen freigegeben werden, obwohl der Praxisbeweis fürs Scratchpad erst nach dem Bauen erbracht wird?
