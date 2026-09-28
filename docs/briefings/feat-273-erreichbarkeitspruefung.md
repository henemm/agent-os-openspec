---
spec_file: docs/specs/feat-285-precondition-origins.md
spec_sha256: 8556b94dfc5486de6296fb567d227e8a267fb4097538ce3b1948721c1e137aa3
---

# PO-Briefing: feat-273-erreichbarkeitspruefung

- **Spec:** docs/specs/feat-285-precondition-origins.md
- **Issue:** #285 (Teilvorgang von Epic #273)
- **Erstellt:** 2026-09-28

## Was gebaut wird

Ein Hilfsprogramm listet automatisch auf, wie oft eine Testvorbedingung im Betrieb tatsächlich vorkommt — als Verdachtsliste für Prüfende, nicht als Eingriff.

## Definition of Done

Fertig ist es, wenn es am dokumentierten echten Fehlerfall zuverlässig eine kurze Verdachtsgruppe zeigt und jede Prüfbedingung nachgewiesen ist.

## Wie geprüft wird

Automatische Prüfungen decken jeden Punkt ab; der Nachweis am vollständigen alten Projekt bleibt ein einmaliger, nicht wiederholbarer Handnachweis.

## Kritische Anmerkungen

- Die ursprünglich verlangte Bedingung ('unter den ersten fünf Treffern') wurde nach Messung auf eine schwächere Gruppen-Zugehörigkeit abgeschwächt.
- Ein zusätzlicher Nachweis am vollständigen alten Projekt wurde ergänzt, bleibt aber einmalig und unautomatisiert.
- Der Umfang liegt mit rund 360 Zeilen deutlich über der üblichen Obergrenze von 250.

## Freigabe-Frage

Genügt die abgeschwächte Erfolgsmessung als Nachweis, oder soll die ursprünglich verlangte Messlatte gehalten werden?
