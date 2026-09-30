---
spec_file: docs/specs/fix-278-adversary-protokoll-format.md
spec_sha256: 63cda35125a3825a577db421a04f1c954322f05370466f4ce0cde36fd97dff39
---

# PO-Briefing: fix-278-adversary-protokoll-format

- **Spec:** docs/specs/fix-278-adversary-protokoll-format.md
- **Issue:** #278
- **Erstellt:** 2026-09-30

## Was gebaut wird

Das Prüfprotokoll für Freigaben akzeptiert beide Überschriftenformen und schreibt Fund- und Dateizahlen automatisch in den Status.

## Definition of Done

Ein bislang blockiertes Protokoll wird angenommen, und nach einer Prüfung stehen echte Fund- und Dateizahlen im Status statt einer festen Null.

## Wie geprüft wird

Automatische Tests zeigen: akzeptiertes und abgelehntes Format, echte Fund- und Dateizahlen nach einer Prüfung — keine manuelle Kontrolle nötig.

## Kritische Anmerkungen

- Die Anfrage wollte auch die Verteilung nach Schweregrad im Status sehen; die Spec schreibt nur die Gesamtzahl der Funde.

## Freigabe-Frage

Reicht die Gesamtzahl der Funde im Status, oder soll zusätzlich die Verteilung nach Schweregrad festgehalten werden, bevor freigegeben wird?
