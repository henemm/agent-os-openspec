---
spec_file: docs/specs/fix-299-bash-gate-erkennung.md
spec_sha256: 536194e7d7a920c9210f7b98092cda149d6ff20763c051d7f88a54851b90c7b1
---

# PO-Briefing: fix-299-bash-gate-erkennung

- **Spec:** docs/specs/fix-299-bash-gate-erkennung.md
- **Issue:** #299
- **Erstellt:** 2026-10-01

## Was gebaut wird

Der Commit-Wächter erkennt mehr Schreibweisen für Commits und blockiert sie ohne Prüfnachweis; Rebase-Hinweis funktioniert bei vorgemerkten Dateien.

## Definition of Done

Jede der geprüften Commit-Schreibweisen wird ohne Prüfnachweis blockiert, harmlose Befehle laufen weiter, und der Rebase-Hinweis gelingt tatsächlich.

## Wie geprüft wird

Automatische Tests spielen jede Schreibweise gegen das echte Gate durch, in beide Richtungen; vorsätzliche Umgehungen und Alias-Tricks prüfen sie nicht.

## Kritische Anmerkungen

- Nur Teil A: Alias-Umgehung (#281) und merge/cherry-pick (#297) bleiben offen; #299 kann nicht geschlossen werden.
- Verschärfte Whitelist-Regel wirkt auch auf die Geheimnisprüfung; Über-Blockieren legitimer Befehle ist möglich, nur teilweise getestet.
- Vorsätzliche Umgehung bleibt möglich; erst die Abschlussprüfung am Ende fängt sie ab.

## Freigabe-Frage

Gibst du frei, dass nur Teil A (Schreibweisen-Lücken, Rebase-Hinweis) jetzt gebaut wird und #281/#297 später folgen?
