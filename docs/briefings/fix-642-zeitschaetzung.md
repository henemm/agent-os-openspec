---
spec_file: docs/specs/fix-642-zeitschaetzung.md
spec_sha256: 0117eeea6be7a0cae6372cd8b8a4b05248ed6b0bd3513af8bfea530ca4dc9887
spec_frozen_sha256: 3c83015582358d50c1b8c9e213d44cd6190f7da4ec15c7f1a662ee5a6698d78f
---

# PO-Briefing: fix-642-zeitschaetzung

- **Spec:** docs/specs/fix-642-zeitschaetzung.md
- **Issue:** #642
- **Erstellt:** 2026-11-21

## Was gebaut wird

Der Plan zeigt vor der Freigabe Start und Freigabezeit, danach eine Ende-Spanne in Viertelstunden, vollständig lesbar und ohne widersprüchliche Dauer.

## Definition of Done

Im schmalen Plan stehen Start, Freigabe bzw. Ende und die Datengrundlage vollständig, ohne Nacht-Ausreißer, und alle acht Kriterien sind getestet.

## Wie geprüft wird

Automatische Tests belegen Rechnung, Rundung, nachgemessene Prozentzahl, Umbruch und Fehlerfestigkeit; ob die Zeiten im echten Projekt stimmen, beweisen sie nicht.

## Kritische Anmerkungen

- Projekte mit wenigen Workflows ohne Aktivitätsdatei zeigen vorerst gar keine Prognose („Ende offen“); das ist dokumentiert und folgt „verlässlich vor früh“.
- Die angezeigte Prozentzahl kann von 80 % abweichen, da sie die tatsächliche Trefferquote zeigt.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
