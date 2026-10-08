---
spec_file: docs/specs/fix-400-alias-robust.md
spec_sha256: 95e362ad7abb45b6b4b767c52baab6c523f5d83487f4fd9958261d704510df06
---

# PO-Briefing: fix-400-alias-robust

- **Spec:** docs/specs/fix-400-alias-robust.md
- **Issue:** #400
- **Erstellt:** 2026-10-08

## Was gebaut wird

Die automatische Kurzbefehl-Pflege beim Start überschreibt keine verlinkten Dateien mehr und lässt sich nicht von einer gesperrten Datei stoppen.

## Definition of Done

Verlinkte Kurzbefehle bleiben unverändert, eine schreibgeschützte Datei stoppt die übrigen nicht, und Start-Hinweis sowie Setup-Ausgabe nennen Übersprungenes.

## Wie geprüft wird

Sechs automatische Tests spielen Verlinkung, Schreibschutz, Start-Hinweis und Setup-Aufruf durch; echte Dotfiles-Setups werden nicht nachgestellt.

## Kritische Anmerkungen

- Verlinkte Kurzbefehle (Dotfiles) werden nie mehr erneuert, nur gemeldet; veralteter Stand bleibt, Meldung erscheint bei jedem Start.
- Schreibschutz-Test läuft als Administrator nicht; dort ist der Fall ungeprüft.

## Freigabe-Frage

Soll die Pflege verlinkte Kurzbefehle künftig nur melden statt erneuern?
