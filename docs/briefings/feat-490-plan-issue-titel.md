---
spec_file: docs/specs/feat-490-plan-issue-titel.md
spec_sha256: d0ddc7697aa7f1e518a8d0bea691fac6a1bffd211387fd477b52ac32bbe82fc9
spec_frozen_sha256: 720c96b498d76e04625e413ba89c7baacfe78132c271141509dfa599bbf1a30f
---

# PO-Briefing: feat-490-plan-issue-titel

- **Spec:** docs/specs/feat-490-plan-issue-titel.md
- **Issue:** #490
- **Erstellt:** 2026-10-30

## Was gebaut wird

Im Seitenfenster steht unter der Workflow-Nummer der auf sechs Wörter gekürzte Issue-Titel.

## Definition of Done

Du siehst im Seitenfenster unter der Nummer den Kurztitel des Issues; alle sechs Prüfkriterien sind automatisch belegt, bestehende Tests bleiben grün.

## Wie geprüft wird

Automatische Tests prüfen Kürzen, Anzeige, Zwischenspeicher, Abruf ohne Verzögerung und Verhalten ohne Netz; das tatsächliche Aussehen im Seitenfenster prüfst du selbst.

## Kritische Anmerkungen

- Gekürzt wird mechanisch auf die ersten sechs Wörter, nicht inhaltlich zusammengefasst; Titel können dadurch abgeschnitten wirken.
- Ändert sich der Issue-Titel später, bleibt der alte Titel stehen, bis die Zwischenspeicher-Datei gelöscht wird.

## Freigabe-Frage

Keine – Ampel gruen.

## Ampel

Ampel: gruen
