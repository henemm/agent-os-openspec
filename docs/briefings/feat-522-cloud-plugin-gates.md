---
spec_file: docs/specs/feat-522-cloud-plugin-gates.md
spec_sha256: e00f053239597a2e9a1866e24f38dca62f5da2a79802fb88151bbb7395f6b765
spec_frozen_sha256: 983e3cba25389218e40e11b3b459b56bc8228626bf9118acdc6fabe31675e01f
---

# PO-Briefing: feat-522-cloud-plugin-gates

- **Spec:** docs/specs/feat-522-cloud-plugin-gates.md
- **Issue:** #522
- **Erstellt:** 2026-11-09

## Was gebaut wird

Cloud-Sitzungen von Plugin-Projekten bekommen dieselben Schutzregeln wie lokal, mit einer vom PO auslösbaren einstündigen Ausnahme.

## Definition of Done

In einer frischen Cloud-Sitzung blockt ein Schutzmechanismus nachweislich eine Änderung, lokal läuft nichts doppelt, und der PO kann per Wort „override“ freigeben.

## Wie geprüft wird

Automatische Tests mit echtem Testrepository und ein gespeicherter Mitschnitt einer echten Cloud-Sitzung; der Live-Lauf selbst wird nicht automatisch wiederholt.

## Kritische Anmerkungen

- Ohne Zugang zu github.com sind schreibende Werkzeuge gesperrt, bis die Umgebung freigegeben ist oder der PO „override“ tippt.
- Während der Ausnahme-Stunde läuft die Sitzung ohne Schutz; Zugangsdaten-Wächter fehlen schon im Sperrzustand für Lesezugriffe.
- Cloud-Projekt-Threads führen laut Doku keine Schutzregeln des Projekts aus; dort bleibt der Schutz aus.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
