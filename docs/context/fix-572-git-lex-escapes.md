# Context: fix-572-git-lex-escapes

## Request Summary
`hook_utils._git_lex` zerlegt Shell-Befehle anders als bash. Ein maskierter
Backslash vor einem Zeilenumbruch (`\\` + Umbruch) wird als Zeilenfortsetzung
entfernt; bash liest dort einen wörtlichen Backslash und einen echten
Befehlstrenner. Folge: `git commit` wird unsichtbar, das Commit-Gate entfällt.
Laut Wiederaufnahme-Empfehlung in #563 soll #572 den Lexer quote-/escape-bewusst
machen, sodass gequotete/maskierte Operator-Zeichen keine Trenner-Token werden
(Befund F013).

## Reproduktion (Stand origin/main 19c448e)
| Befehl (Python-Repr) | `_git_lex` | bash |
|---|---|---|
| `git status "a\\\\\n" && git commit -m pwn && git status "b\\\\\n"` | `['git','status','a" && git commit … b"']` — commit unsichtbar | führt `git commit` aus |
| `git status a\\\\\ngit commit -m pwn` | `['git','status','agit','commit',…]` — commit unsichtbar | Zeile 2 = `git commit` |
| `git status 'a\\\n' && git commit -m x` | Inhalt `a` statt `a\<NL>` (strukturell ok) | `'…'` kennt keine Fortsetzung |
| `git status '&&' git commit -m x` | `&&` wird Trenner (Über-Zerlegung) | ein einziger `git status`-Aufruf |
| `touch m ';' git status` / `touch m \; git status` | `;` wird Trenner | ein `touch`-Aufruf mit Datei `;` |

Über-Zerlegung ist für die Commit-Erkennung die sichere Richtung, für
Schreib-Erkennungen (`_writes_main_repo`, `_writes_effective_config`,
`_writes_cloud_gate_file`, `_dir_token_in_cd_context`) dagegen gefährlich: ein
gequotetes `';'` zerreißt `cp ';' <ziel>` in zwei Segmente, das Ziel steht dann
ohne Schreibbefehl da.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/hook_utils.py` (Z. 76–85) | `_GIT_LINE_CONTINUATIONS`, Kommentar zu F009 (ersatzlose Entfernung) |
| `core/hooks/hook_utils.py` (Z. 383–431) | `_strip_shell_comments` — bereits quote-/escape-bewusster Scanner (#319); kopiert Fortsetzungen unverändert |
| `core/hooks/hook_utils.py` (Z. 434–465) | `_git_lex` — blindes `replace("\\\n", "")`, dann `shlex` mit `punctuation_chars` |
| `core/hooks/hook_utils.py` (Z. 468–527) | `_is_git_redirect`, `_is_git_separator` (inhaltsbasiert), `_git_segments` |
| `core/hooks/bash_gate.py` | ~30 Aufrufer: `_git_segments`, `git_subcommands`, `is_git_subcommand`, `is_pure_git_command`, `git_head_subcommands`; `_redirects_to_protected` nutzt `_git_lex` + `_is_git_redirect` direkt (Z. 289–321, mit `lstrip` auf Token) |
| `tests/test_git_invocation_detection.py` | Bestandstests Erkennung (23) |
| `tests/test_bash_gate_erkennung_299_teil_c.py` | Tests `_strip_shell_comments` (#319) |

## Existing Patterns
- Grundhaltung (Modul-Kommentar hook_utils Z. 40–54): „bin ich sicher, dass keiner drinsteckt?" — nicht zerlegbar ⇒ Fall 3 (im Zweifel prüfen).
- `_strip_shell_comments` zeigt das Muster eines zeichenweisen Scanners mit Quote-Zustand (`'`, `"`, `$'`) und Backslash-Paaren; endet er in offenem Quote, kommt der Befehl unverändert zurück.
- Token sind `str`; Trenner/Umleitung werden am Inhalt erkannt.

## Dependencies
- Upstream: `shlex.shlex(posix=True, punctuation_chars=…)`.
- Downstream: alle Kern-Gate-Prüfungen in `bash_gate.py`, `secret_egress_guard`? (nein: nur bash_gate/hook_utils importieren `_git_*`).

## Existing Specs
- Keine Spec zum Lexer selbst; Vorgeschichte in Code-Kommentaren (#1431 F001/F002, F005, F009, #298, #304, #318, #319).
- Zurückgestellt: `docs/specs/fix-563-foreign-repo-commit.md` auf Branch `archive/563-foreign-repo-commit`.

## Risks & Considerations
- Kern-Gate, alle Konsumenten-Projekte: Unter-Erkennung öffnet Schutzlücken, Über-Erkennung erzeugt Fehlalarme (z. B. `grep "a;b"` darf nicht blocken).
- `str`-Unterklassen für Operator-Token gehen bei `lstrip`/Slicing verloren (`_strip_leading_separators` in bash_gate).
- bash-Semantik der Fortsetzung: außerhalb von Quotes und in `"…"` wird `\`+Umbruch entfernt, in `'…'` nie; `\\` ist ein Paar (wörtlicher Backslash). `\`+CRLF analog.
- Nicht im Scope: Kommandosubstitution in `"…"` (eigenes Issue #573), `\r` als Leerraum.
- Tests müssen gegen echtes bash belegt werden (Issue-Vorgabe).
