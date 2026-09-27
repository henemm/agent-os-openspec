---
spec_file: docs/specs/feat-88-wakeup-blocks.md
spec_sha256: 7b24030332d0e738103f064cb94ded6d048e8dcb0b84436e515ea4acdaff6d98
---

# PO-Briefing: feat-250-prozess-abstufung

- **Spec:** docs/specs/feat-88-wakeup-blocks.md
- **Issue:** #88 (Teilauftrag 1 aus #250)
- **Erstellt:** 2026-09-26

## Was gebaut wird

Die vier Kernbefehle des Ablaufs bekommen je einen realistischen Rückfall für hängende Hintergrundarbeit statt mehrerer wirkungsloser Wecker.

## Definition of Done

In allen vier betroffenen Abläufen verschwindet der alte Weckruf-Zwang; übrig bleibt ein einziger echter Rückfall je Ablauf.

## Wie geprüft wird

Automatische Textprüfungen zeigen nur, dass die Formulierungen geändert wurden — nicht, ob Claude den verbliebenen Rückfall im Ernstfall tatsächlich beachtet.

## Kritische Anmerkungen

- Der /loop-Rückfall verliert nur das Wort PFLICHT — er bleibt eine unerzwingbare Anweisung mit neuer, übersehbarer Bedingung.
- Die Prüfungen belegen nur geänderten Text, nicht dass der Rückfall im Ernstfall wirklich greift.

## Freigabe-Frage

Reicht Ihnen ein spürbar selteneres, aber weiterhin unbewiesenes Rückfall-Versprechen als Fortschritt, oder soll erst ein echter Nachweis her?
