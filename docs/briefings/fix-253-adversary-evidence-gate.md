---
spec_file: docs/specs/fix-253-adversary-evidence-gate.md
spec_sha256: 4e61f469f826f0fa46251038b787137b3de54212c1da177888ccb14a106ec7fc
---

# PO-Briefing: fix-253-adversary-evidence-gate

- **Spec:** docs/specs/fix-253-adversary-evidence-gate.md
- **Issue:** #253
- **Erstellt:** 2026-09-26

## Was gebaut wird

Ein Commit braucht künftig zusätzlich zum grünen Testlauf eine echte, unabhängige Prüfung.

## Definition of Done

Ein Commit gilt nur noch als freigegeben, wenn zusätzlich zum grünen Testlauf eine unabhängige Prüfung nachgewiesen ist.

## Wie geprüft wird

Automatisierte Tests decken jeden Einzelfall inklusive der im Bug-Bericht beschriebenen Situation ab, außer absichtlichem Fälschen der Prüfung.

## Kritische Anmerkungen

- Laufende Arbeiten mit rein testbasierter Freigabe werden nach dem Update sofort blockiert.
- Ein absichtlich gefälschter Nachweis besteht weiterhin — geschlossen wird nur der beiläufige Fall.
- Die Lösung ändert zusätzlich eine Meldung und einen verwandten Freigabeweg, ungenannt im ursprünglichen Bug-Bericht.

## Freigabe-Frage

Akzeptierst du, dass laufende, nur testbasiert freigegebene Arbeiten bis zur echten Prüfung blockiert bleiben?
