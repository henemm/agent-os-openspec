# Fast Track: secrets_guard-Muster aus dem eigenen Zweig, mit Untergrenze (#292)

## Problem

`load_config()` liest auch in Worktree-Sitzungen nur die Config des Haupt-Ordners (#153). Für
Grenzwerte ist das gewollt; für die secrets_guard-Muster erzeugt es Fehlalarme: Hat ein Zweig zu
breite Muster bereits verengt, blockt der Wächter weiter harmlose Dateinamen. Eine pauschale
Übernahme der Zweig-Config wäre ein Generalschlüssel (Schutz im Zweig leeren, ohne Review). Der PO
hat am 2026-10-05 Option A entschieden: Zweig-Muster ja, eingebaute Grundmuster immer.

## Scope

- `core/hooks/config_loader.py`: `secrets_guard_patterns()`, `_worktree_secrets_section()`
- `core/hooks/secrets_guard.py`, `core/hooks/bash_gate.py`: nutzen den gemeinsamen Helfer
- Nicht enthalten: Untergrenze auch für die Haupt-Ordner-Config (vorbestehend, eigene Abwägung)

## Definition of Done

Ein Zweig kann projekteigene Muster verengen, aber keines der eingebauten Grundmuster abschalten;
belegt mit echtem Haupt-Repo, echtem Worktree und beiden Hooks als Subprozess.

## Acceptance Criteria

- **AC-1:** Given ein Worktree, dessen Config `_key` zu `private_key` verengt, When `cat notes_key.txt` geprüft wird, Then lassen secrets_guard und bash_gate den Befehl durch.
- **AC-2:** Given ein Worktree mit leeren Listen, `enabled: false` oder ungültiger Regex, When `cat .env`, `cat x.pem` oder `cat credentials.json` geprüft wird, Then blocken beide Hooks.
- **AC-3:** Given eine Sitzung im Haupt-Ordner, When ein Worktree abweichende Muster hat, Then gelten weiter die Muster des Haupt-Ordners.

## Test Plan

- `tests/test_secrets_guard_worktree_292.py` (AC-1 bis AC-3), volle Suite
