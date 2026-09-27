---
spec_file: docs/specs/fix-253-adversary-evidence-gate.md
spec_sha256: 303321e63d96139f3aa9db0b91904ff1bac3dcdb3bfa44e31f63ce9ad8b0b446
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
