---
spec_file: docs/specs/feat-667-fresh-session.md
spec_sha256: 86ea3a9fda6d78772eedd27fdd6cd4e84b694b038625cbc3697d18efae277bbd
spec_frozen_sha256: d62f7a5b4dcc67d22325e78cb5577d513cc5e7b9ec1ba93ce5918e20744fdf2d
---

# PO-Briefing: feat-667-fresh-session

- **Spec:** docs/specs/feat-667-fresh-session.md
- **Issue:** #667
- **Erstellt:** 2026-11-25

## Was gebaut wird

Jedes Issue eines Auftrags startet nach der Auslieferung des vorigen automatisch in einer neuen Sitzung mit frischem Kontext.

## Definition of Done

Ein Auftrag mit zwei Issues läuft ohne Tippen durch, in der Cloud belegt, und die Kontextgröße je Sitzung liegt unter der Schwelle.

## Wie geprüft wird

Automatische Tests prüfen Wegwahl, Startauftrag und Herdr-Start mit Attrappe; der echte lokale Herdr-Durchlauf wird nicht getestet.

## Kritische Anmerkungen

- Lokaler Echtbeleg mit Herdr fehlt; er wird wie von dir verlangt am Epic #649 als offen vermerkt.
- Die Kontextmessung unter der Schwelle ist nur manuell belegbar, nicht automatisch getestet.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
