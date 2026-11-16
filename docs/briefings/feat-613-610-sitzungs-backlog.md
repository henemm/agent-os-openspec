---
spec_file: docs/specs/feat-613-610-sitzungs-backlog.md
spec_sha256: 9a6ead6ad8c6c02bb87e93fdeb03e29c1194fd878f77ba6d345543b7589fcd52
spec_frozen_sha256: 2f53c8616effcf1501a5ccc57abd4a9dd205281ba8495b06d604313e86a0b117
---

# PO-Briefing: feat-613-610-sitzungs-backlog

- **Spec:** docs/specs/feat-613-610-sitzungs-backlog.md
- **Issue:** #613, #610
- **Erstellt:** 2026-11-16

## Was gebaut wird

Jede parallele Sitzung bekommt ihren eigenen Auftrag, und der Folgevorschlag kommt nur aus dem Epic ihrer Spur.

## Definition of Done

Eine Sitzung sieht den Auftrag der anderen nie; der Vorschlag nennt nur freie Kinder des eigenen Epics, sonst ausdrücklich keinen.

## Wie geprüft wird

Neun automatische Tests, je Kriterium einer, mit Attrappen für herdr und GitHub; echte Mehrsitzungs-Praxis prüfen sie nicht.

## Kritische Anmerkungen

- Zusatz: neuer Befehl zum Übernehmen alter Aufträge; nach Neustart ohne herdr bei mehreren Sitzungen nötig.
- Der Projektbefehl für das nächste Ticket liegt außerhalb dieses Repos und muss separat angepasst werden.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
