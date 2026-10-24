---
spec_file: docs/specs/fix-445-guard-no-git.md
spec_sha256: d3fe443d2b29c347df6cd86d8a5b33eecf4e5b93b617b692f421eced18440e11
spec_frozen_sha256: 15ee4d7e968a0655fa47fb21ca26049e28ef0b8053b8de795a9f9a4e94649983
---

# PO-Briefing: fix-445-guard-no-git

- **Spec:** docs/specs/fix-445-guard-no-git.md
- **Issue:** #445
- **Erstellt:** 2026-10-23

## Was gebaut wird

Sitzungen in Ordnern ohne Git werden nicht mehr ausgesperrt; in Git-Projekten bleibt die Worktree-Pflicht bestehen.

## Definition of Done

Eine Sitzung in einem Ordner ohne Git arbeitet ohne "override"; in Git-Projekten wird weiterhin blockiert.

## Wie geprüft wird

Automatische Tests belegen Erlauben ohne Git und Blockieren mit Git; eine echte Sitzung im Notizordner wird nicht getestet.

## Kritische Anmerkungen

- Issue-Text war nicht lesbar; Abgleich nur gegen das Kontext-Dokument, Deckung der Originalforderung unbestätigt.
- Ohne Git entfällt die Worktree-Pflicht vollständig, auch bei Projekten mit eigenem Worktree-Mechanismus.
- Task- und Agent-Aufrufe haben keinen eigenen Test; geprüft werden nur Bash, Edit, Write.

## Freigabe-Frage

Soll der Wächter in Ordnern ohne Git künftig nichts mehr erzwingen, auch wenn dort theoretisch ein Worktree möglich wäre?
