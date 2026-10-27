---
spec_file: docs/specs/fix-404-qa-stempel-faelschung.md
spec_sha256: 57c9664ecd83ae50b82a58a2b7afec21748fcdc1e10716f5b109dfaef39e01fa
---

# PO-Briefing: fix-404-qa-stempel-faelschung

- **Spec:** docs/specs/fix-404-qa-stempel-faelschung.md
- **Issue:** #404 (nur Befund F003)
- **Erstellt:** 2026-10-13

## Was gebaut wird

Der QA-Stempel „Gate hat selbst gemessen“ lässt sich nicht mehr per Python-Aufruf von außen fälschen.

## Definition of Done

Ein Fälschungsversuch wird abgelehnt und im Bash-Gate geblockt; der reguläre QA-Lauf schreibt den Stempel weiterhin.

## Wie geprüft wird

Tests belegen Ablehnung, Blockade, Freitext-Ausnahme und regulären Lauf, nicht aber Sicherheit gegen bewusstes Überschreiben.

## Kritische Anmerkungen

- Issue-Text nicht lesbar; nur gegen Kontext-Dokument geprüft.
- Bewusstes Überschreiben der Prozess-Kennung umgeht den Schutz; echte Sicherheit bringt erst Teil B.
- Offen: Brechen bestehende Tests, die den Stempel direkt schreiben? Spec klärt das nicht.

## Freigabe-Frage

Genügt dir ein Schutz gegen naive Fälschung, bis Teil B den Stempel beim Lesen prüft?
