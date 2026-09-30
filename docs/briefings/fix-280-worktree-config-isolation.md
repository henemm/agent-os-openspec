---
spec_file: docs/specs/infra/fix-280-worktree-config-isolation.md
spec_sha256: ccce1a02595a5f663902b96213b7c000d6dcc9f233973022a59d7ee47abded77
---

# PO-Briefing: fix-280-worktree-config-isolation

- **Spec:** docs/specs/infra/fix-280-worktree-config-isolation.md
- **Issue:** #280
- **Erstellt:** 2026-09-30

## Was gebaut wird

Meldungen über eine blockierte Aktion landen künftig im Protokoll der Sitzung, in der sie passieren, statt immer im Hauptordner.

## Definition of Done

Eine Blockade in einem Nebenzweig erscheint nur in dessen eigenem Protokoll, eine im Hauptordner wie bisher, und drei benannte Testdateien hinterlassen keine echten Protokollzeilen mehr.

## Wie geprüft wird

Automatisierte Tests mit einem echten Nebenzweig belegen beide Fälle; ob andere, hier nicht benannte Testdateien noch Spuren hinterlassen, prüft das nicht.

## Kritische Anmerkungen

- Das ursprüngliche Ziel „null Spuren im gesamten Testlauf" gilt jetzt nur für drei Testdateien; der Rest läuft separat als #295.
- Der Testumfang wuchs nachträglich von zwei auf drei Dateien, weil ein echter Lauf sechs zusätzliche Fehlschläge zeigte.
- Befund 1 aus #280 (Konfigurationsdatei im Nebenzweig) bleibt unangetastet und läuft separat als #292.

## Freigabe-Frage

Sollen wir das jetzige verengte Protokoll-Ziel (drei Dateien) freigeben, obwohl der Rest erst mit #295 folgt?
