---
spec_file: docs/specs/fix-417-bash-main-write.md
spec_sha256: 6717388ebedc0fea241fa708bf6cbfdf14f94f97dc2eaa5b6442911cf722409a
---

# PO-Briefing: fix-417-bash-main-write

- **Spec:** docs/specs/fix-417-bash-main-write.md
- **Issue:** #417
- **Erstellt:** 2026-10-12

## Was gebaut wird

Schreibbefehle aus einer Arbeitskopie-Sitzung in den Haupt-Ordner werden blockiert, mit „override“ als Ausweg.

## Definition of Done

In einer Worktree-Sitzung scheitern Kopieren, Umleiten, Verschieben und Ändern im Haupt-Ordner mit Hinweis auf „override“; Arbeiten im eigenen Worktree läuft weiter.

## Wie geprüft wird

Automatische Tests am echten Gate belegen alle Schreibweisen und Ausnahmen; absichtliche Umgehung, etwa über Python-Skripte, wird nicht geprüft.

## Kritische Anmerkungen

- Issue-Text war nicht direkt abrufbar; Abgleich nur gegen das Kontext-Dokument.
- Umgehung per Python oder Shell-Variablen bleibt möglich; nur Schutz vor Versehen.
- Legitime Schreibvorgänge in den Haupt-Ordner brauchen künftig „override“.

## Freigabe-Frage

Soll der Schutz bewusst nur versehentliche Schreibzugriffe abfangen und absichtliche Umgehung ausklammern?
