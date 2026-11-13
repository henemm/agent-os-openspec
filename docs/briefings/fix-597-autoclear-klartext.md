---
spec_file: docs/specs/fix-597-autoclear-klartext.md
spec_sha256: c14e2f4db105462e8099077fc510f5bbc863709123e2e4cc6da273ddb796d5ad
spec_frozen_sha256: 12830a18e8858ef5410bec7c3b69c868f27460d340d1f9ca8702f4cd5f27adaf
---

# PO-Briefing: fix-597-autoclear-klartext

- **Spec:** docs/specs/fix-597-autoclear-klartext.md
- **Issue:** #597
- **Erstellt:** 2026-11-13

## Was gebaut wird

Der Auto-Modus räumt an jeder Phasengrenze zuverlässig auf, auch wenn eine Antwort zwischendurch einmal zurückgewiesen wird.

## Definition of Done

Alle Tests grün, Vorlagen ohne Git-Wörter, und der lokale Herdr-Durchlauf zeigt nach einer zurückgewiesenen Antwort genau einen Neustart.

## Wie geprüft wird

Automatische Tests mit simuliertem Herdr belegen alles, nur das Verhalten im echten Herdr prüft ein lokales Skript.

## Kritische Anmerkungen

- Echtes Herdr ist nicht in der Serverprüfung testbar; das Skript muss lokal laufen.
- Ältere Regeln (600-Sekunden-Sperre, Sonderfall Folge-Stopp) werden bewusst ersetzt, Bestandstests angepasst.
- Restrisiko: Eine liegengebliebene Übergabe kann bis 15 Minuten später auslösen.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
