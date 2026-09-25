---
spec_file: docs/specs/fix-234-footer-gate.md
spec_sha256: 6a9ed7beab92193661e4a3acb25fef9225cba819a812e4064375819a051957b0
---

# PO-Briefing: fix-234-footer-command

- **Spec:** docs/specs/fix-234-footer-gate.md
- **Issue:** #234
- **Erstellt:** 2026-09-25

## Was gebaut wird

Eine automatische Prüfung ersetzt reines Text-Nachschärfen: falsche Nächster-Schritt-Angabe wird technisch erkannt und noch im selben Moment korrigiert.

## Definition of Done

Automatisierte Tests zeigen: falscher Nächster-Schritt-Hinweis wird erkannt und korrigiert, richtige Hinweise und alle Sonderfälle bleiben ungestört – nicht per manueller Prüfung.

## Wie geprüft wird

Zehn automatische Testfälle decken Treffer, alle Ausweich-Szenarien und Doppel-Auslösung ab; echtes Nutzerverhalten im Live-Betrieb wird nicht getestet.

## Kritische Anmerkungen

- Schutz gilt nur im Plugin-Modus; viele Projekte (Copy-Modus) bleiben ungeschützt, laut Spec bewusst ausgeklammert (Issue #236).
- Falsche Angabe bleibt laut Spec kurz sichtbar, bevor die Korrektur folgt – kein echtes Verhindern.
- Kein Test für einen Absturz durch kaputte Eingabedaten selbst – nur Workflow-Speicher-Fehler sind abgedeckt.

## Freigabe-Frage

Soll diese technische Prüfung jetzt gebaut werden, obwohl sie vorerst nur einen Teil der Projekte schützt und Restrisiko bleibt?
