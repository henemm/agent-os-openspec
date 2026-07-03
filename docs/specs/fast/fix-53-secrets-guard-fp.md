# Mini-Spec: fix-53-secrets-guard-fp

## Problem (Issue #53, dreifach live reproduziert am 2026-07-03)
`secrets_guard.py` (und der Secrets-Check in `bash_gate.py`) scannen den ROHEN
Befehlsstring mit unverankerten Regexen (`_matches(cmd, sensitive)` über den
Gesamttext + `_DANGEROUS_CMD_RE`). Lange Befehle mit Freitext (Commit-Messages,
PR-Bodies, Issue-Texte, grep-Muster) triggern False-Positives, obwohl keine
Secret-Datei berührt wird. Live geblockt wurden u.a.:
1. `git add ... && git commit -m "<Heredoc-Fließtext>" && gh pr create --body "<Fließtext>"`
2. `grep -n "SECRET\|def _check_secrets\|secrets_guard\|SENSITIVE" core/hooks/bash_gate.py`
3. `gh issue create --body "<Text, der das False-Positive beschreibt>"`

## Was ändert sich

**Schritt 0 — Reproduktion (Pflicht, vor jedem Fix):** Die drei geblockten
Original-Befehle als Payload an `secrets_guard.py` UND an den Secrets-Check von
`bash_gate.py` pipen, exakt bestimmen, WELCHES Pattern in WELCHEM Guard matcht.
Erst mit dieser Diagnose den Fix bauen (kein Raten).

**Fix-Prinzip (analog zu #30/#31, 3.4.15):**
- Sensitive-Datei-Patterns nur noch gegen tatsächliche DATEI-Token des Befehls
  matchen (shlex-Tokenisierung; Argumente von `-m`/`--body`/`--title`/`-F`-
  Freitext sind keine Datei-Token). Bei shlex-Parse-Fehler konservativer
  Fallback auf den bisherigen Roh-Scan (kein neues Loch — identisches Muster
  wie `_has_real_redirect()` aus 3.4.15).
- `_DANGEROUS_CMD_RE` bleibt als zweite Bedingung erhalten (Ausgabe-Befehle),
  wird aber nur relevant, wenn ein echtes Datei-Token matcht.
- Identische Behandlung an BEIDEN Stellen (secrets_guard.py und der
  entsprechende Check in bash_gate.py), damit kein Guard-Drift entsteht.

Zusätzlich: `CHANGELOG.md`-Eintrag, Version 3.8.2 → 3.8.3 (PATCH).

## Was darf sich nicht ändern (Sicherheits-Invarianten, je als Gegenprobe testen)
- `cat .env`, `head credentials.json`, `grep x private.key` → weiterhin BLOCK.
- `cat "datei mit leerzeichen/.env"` (quoted Pfad) → weiterhin BLOCK.
- `bash -c "cat .env"` bzw. nicht-parsebare Befehle → konservativer Fallback blockt.
- `grep -l` -Ausnahme bleibt erhalten.
- Staging-Modus-Verhalten unverändert.

## Manuelle Test-Schritte
1. Die drei Original-Befehle (oben) laufen nach dem Fix durch.
2. `cat .env` wird weiterhin geblockt.

## Inline-Tests (werden während Implementierung geschrieben)
- [ ] Die 3 Realfall-Befehle als Regressionstests → kein Block.
- [ ] Alle Sicherheits-Invarianten oben → Block bleibt.
- [ ] shlex-Fallback-Fall (kaputte Quotes + .env) → Block bleibt.
