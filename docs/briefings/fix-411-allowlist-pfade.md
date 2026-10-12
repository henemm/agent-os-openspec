---
spec_file: docs/specs/fix-411-allowlist-pfade.md
spec_sha256: ebdd0087b65de7ea6e8c1cbaa3e296d0d22611645cbc0e3f2be16e58504f9ee3
---

# PO-Briefing: fix-411-allowlist-pfade

- **Spec:** docs/specs/fix-411-allowlist-pfade.md
- **Issue:** #411
- **Erstellt:** 2026-10-12

## Was gebaut wird

Zwei Schutzprüfungen für Dateibearbeitung lassen sich nicht mehr durch Pfad-Tricks umgehen und stürzen bei fehlerhaften Pfaden nicht mehr ab.

## Definition of Done

Ein Pfad wie docs/../src/x.py wird wie normaler Code geprüft, ein Pfad mit Nullzeichen verursacht keinen Absturz, alle Tests laufen grün.

## Wie geprüft wird

Sechs automatische Tests decken jeden Randfall ab; Symlinks und echte Sitzungen im Live-Betrieb werden nicht geprüft.

## Kritische Anmerkungen

- Ursprungsanfrage nur über das Kontextdokument geprüft, nicht über den Originaltext des Issues.
- Symlinks in relativen Pfaden bleiben ungeprüft; dort bleibt eine Umgehung möglich.
- Strenger als bisher: Pfade, die nach oben aus dem Projekt führen, werden immer geprüft.

## Freigabe-Frage

Soll die Härtung der Immer-erlaubt-Liste mit diesen drei Randfall-Korrekturen und der genannten Symlink-Lücke freigegeben werden?
