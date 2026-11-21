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
