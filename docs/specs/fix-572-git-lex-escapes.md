---
entity_id: fix-572-git-lex-escapes
type: bugfix
created: 2026-11-10
updated: 2026-11-10
status: draft
version: "1.0"
workflow: fix-572-git-lex-escapes
issue: 572
tags: [hooks, hook_utils, bash_gate, lexer, commit-gate, epic-429]
---

# `hook_utils._git_lex` zerlegt Befehle bash-gerecht (Fortsetzung, gequotete Operatoren) (Issue #572, Teil von Epic #429)

## Approval

- [ ] Approved

## Purpose

`hook_utils._git_lex` zerlegt Shell-Befehle für alle Bash-Prüfungen des Kern-Gates, tut das aber anders als bash: Es entfernt jede Backslash-Zeilenfortsetzung blind, auch hinter einem maskierten Backslash (`\\` + Zeilenumbruch), wo bash einen wörtlichen Backslash und einen echten Befehlstrenner liest. Ein `git commit` kann dadurch unsichtbar werden, und das Commit-Gate entfällt. Außerdem werden gequotete oder maskierte Operatorzeichen (`';'`, `\;`) zu Trennern; das zerreißt bei Schreib-Erkennungen Befehle wie `cp ';' <geschütztes Ziel>`. Diese Änderung macht die Zerlegung quote- und escape-bewusst, sodass sie die Wörter und Befehle ergibt, die bash tatsächlich ausführt.

## Source

- **File:** `core/hooks/hook_utils.py`
- **Identifier:** `_git_lex`, `_is_git_separator`, `_is_git_redirect`, `_git_segments`, `is_git_subcommand`; neu `_lex_prepare` und `_QuotedWord`; in `core/hooks/bash_gate.py` `_strip_leading_separators`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils._strip_shell_comments` (#319) | function | Vorbild für den zeichenweisen Scanner mit Quote-Zustand; sein Vertrag bleibt unverändert |
| `shlex.shlex(posix=True, punctuation_chars=...)` | stdlib | bleibt die eigentliche Tokenisierung; der Scanner arbeitet davor |
| `hook_utils._GIT_PUNCTUATION` | constant | Menge der Operatorzeichen (`();<>\|&`, Zeilenumbruch, Backtick), die maskiert werden |
| `hook_utils._git_segments`, `git_subcommands`, `is_git_subcommand`, `is_pure_git_command`, `git_head_subcommands` | function | Aufrufer von `_git_lex`; Verhalten für echte Trenner muss gleich bleiben |
| `bash_gate._writes_main_repo`, `_writes_effective_config`, `_redirects_to_protected` | function | Schreib-Erkennungen, die von korrekt erhaltenen gequoteten Operatoren abhängen |
| `bash_gate._strip_leading_separators` | function | schneidet Trenner vor Umleitungen ab; darf die Markierung gequoteter Token nicht verlieren |
| `tests/test_git_invocation_detection.py`, `tests/test_bash_gate_erkennung_299_teil_c.py` | test | bestehende Regressionsbasis |
| `docs/context/fix-572-git-lex-escapes.md` | context | Reproduktion, bash-Semantik-Tabelle, Technical Approach |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | Neue Vorstufe `_lex_prepare` (bash-gerechte Fortsetzungs-Entfernung, Platzhalter für gequotete/maskierte Operator- und Trennwort-Zeichen), `_QuotedWord(str)`, Rückabbildung in `_git_lex`; `_is_git_separator` und `_is_git_redirect` ignorieren `_QuotedWord`; blindes `replace` samt `_GIT_LINE_CONTINUATIONS` entfällt |
| core/hooks/bash_gate.py | MODIFY | `_strip_leading_separators` gibt ein `_QuotedWord` unverändert zurück (sonst geht die Markierung beim `lstrip` verloren) |
| tests/test_git_lex_escapes_572.py | CREATE | Tests zu allen ACs, Fortsetzungs-Fälle zusätzlich gegen echtes bash belegt |
| CHANGELOG.md | MODIFY | `[Unreleased]` → Fixed mit `#572` |

### Estimated Changes

- Files: 1 neu (Test), 2 produktiv geändert, CHANGELOG
- LoC: +~90/-~5 Produktion, +~150 Test
- Risk Level: HIGH (Kern-Gate, wirkt in allen Konsumenten-Projekten; Unter-Erkennung öffnet Schutzlücken, Über-Erkennung erzeugt Fehlalarme)

## Implementation Details

**Ursache.** `_git_lex` entfernt vor `shlex` blind jedes `\`+Zeilenumbruch. bash entfernt es nur, wenn der Backslash selbst nicht maskiert ist und nicht in `'…'` steht. Bei `a\\`+Umbruch ist `\\` ein Paar (wörtlicher Backslash), der Umbruch trennt Befehle; die Entfernung verklebt die Zeilen, und `git commit` verschwindet im Token davor. Zusätzlich macht `shlex` mit `punctuation_chars` aus gequotetem `';'` oder `'&&'` ein Trenner-Token, weil Trenner am Inhalt erkannt werden.

**Ansatz: Vorstufe plus Markierung, `shlex` bleibt.** Kein eigener Tokenizer (wäre ~150 LoC mit neuen `shlex`-Abweichungen; die Aufrufer vergleichen ohnehin Strings).

1. `_lex_prepare(command)` läuft zeichenweise nach dem Muster von `_strip_shell_comments`. Quote-Zustände: `'…'`, `"…"`, `$'…'`; `$'` öffnet nur außerhalb von Quotes ein Quote (nicht innerhalb `"…"`).
   - Außerhalb von Quotes: `\`+LF und `\`+CRLF werden entfernt; `\\` wird als Paar kopiert; `\`+Sonderzeichen wird zu `\`+Platzhalter.
   - In `"…"`: `\`+LF wird entfernt; `\X` wird als Paar kopiert (Sonderzeichen wird Platzhalter); ungemaskierte Sonderzeichen werden Platzhalter.
   - In `'…'` und `$'…'`: keine Fortsetzung (Backslash und Umbruch bleiben Inhalt); Sonderzeichen werden Platzhalter.
   - Sonderzeichen sind `_GIT_PUNCTUATION` plus die Trennwort-Zeichen `{`, `}`, `!`. Jedes bekommt ein eigenes Platzhalterzeichen aus einem Bereich, der in echten Befehlen nicht vorkommt.
2. Endet der Scanner in einem offenen Quote, liefert jede Zerlegung `None`. Kommt ein Zeichen des Standard-Platzhalterblocks (ab U+E000) schon in der Eingabe vor, liefert `_git_lex` (strikt) `None`; damit greift für die Commit-Erkennung die Grundhaltung des Moduls (nicht zerlegbar → Fall 3, im Zweifel prüfen).
   - Gemeinsamer Kern ist `_lex_tokens(command, base)`. `_git_lex` nutzt den Standardblock. `_git_lex_robust` wählt per `_lex_free_base` den ersten 12-Zeichen-Block, dessen Zeichen nicht in der Eingabe stehen (Standardblock, sonst Supplementary PUA ab U+F0000), und bildet die Token exakt auf die Originalzeichen zurück.
   - `_git_segments` und `bash_gate._redirects_to_protected` nutzen `_git_lex_robust` (Adversary-Befund F001): ein auch gequotetes Platzhalterzeichen darf die Schreibprüfungen (Gate-Config, `OPENSPEC_AUTONOMY`, Cloud-Gate-Dateien, Haupt-Repo, `cd`-Kontext, Umleitungen) nicht abschalten, die bei `None` fail-open nichts sehen würden.
3. `_git_lex` tokenisiert den aufbereiteten Text mit `shlex`, bildet Platzhalter in jedem Token auf die Originalzeichen zurück und liefert Token, die ein Platzhalterzeichen enthielten, als `_QuotedWord(str)`.
4. `_is_git_separator` und `_is_git_redirect` behandeln ein `_QuotedWord` nie als Trenner oder Umleitung. Echte Operatoren bleiben normale `str` und verhalten sich wie bisher.
5. `bash_gate._strip_leading_separators` lässt ein `_QuotedWord` unverändert (`str.lstrip` würde die Unterklasse verlieren).

**bash-Semantik (real mit bash geprüft, Tests belegen sie erneut).** `a\\`+LF+`x`: Wort `a\`, dann neuer Befehl `x`. `"a\`+LF+`b"`: `ab`. `'a\`+LF+`b'` und `$'a\`+LF+`b'`: unverändert. `a\\\`+LF+`b`: `a\b`. `"a\;b"`: `a\;b`. `a\;b`: `a;b`, kein Trenner.

**Positions-Suche bleibt wirksam.** `git_subcommands` findet `commit` auch ohne Trenner (`eval git status ';' git commit`, `xargs`, `find -exec … \; -exec git commit …`); deshalb sind diese Fälle als Regressionstests festgehalten, nicht als Neuerung.

**Unverändert.** `_strip_shell_comments` samt Vertrag; echte Trenner und Umleitungen (`&&`, `;`, `|`, `>`, `2>&1`, Heredoc); mehrzeilige `-m`-Messages bleiben ein Token.

**Tests.** `tests/test_git_lex_escapes_572.py`. Fortsetzungs-Fälle laufen zusätzlich in einem echten Temp-Git-Repo mit `bash -c`; der Test belegt dort, dass bash den Commit wirklich ausführt, wenn die Erkennung `commit` meldet. Kein Mock von Shell oder git.

## Expected Behavior

- **Input:** Bash-Befehlszeichenketten mit Backslash-Fortsetzungen, maskierten Backslashes, gequoteten oder maskierten Operatorzeichen, offenen Quotes.
- **Output:** `_git_lex`, `_git_segments` und `is_git_subcommand` liefern dieselben Wörter und Befehlsgrenzen wie bash. Gequotete/maskierte Operatoren bleiben Wortinhalt (`_QuotedWord`). Nicht sicher zerlegbare Eingaben liefern `None`, und `is_git_subcommand` fällt auf Fall 3 zurück.
- **Side effects:** Keine Schreibzugriffe, keine neuen Konfigurationsschalter. Das Commit-Gate sieht `git commit` auch hinter `\\`+Umbruch; Schreib-Erkennungen sehen `cp ';' <Ziel>` als einen Befehl mit Ziel.

## Known Limitations

- Ziffern-Präfix: `'2'>x` gilt weiter als Datei-Deskriptor-Präfix (harmlos, Über-Erkennung).
- Kommentar vor einer Fortsetzung (`x #c \`+Umbruch+`y`): bash setzt dort nicht fort, der Scanner kopiert Fortsetzungen im Kommentar wie bisher; vorbestehend, keine Umgehung bekannt.
- Kommandosubstitution in `"…"` (`"$(git commit)"`) bleibt unberührt und ist Issue #573.
- `\r` als Leerraum wird nicht behandelt; nur `\`+CRLF gilt als Fortsetzung.
- Platzhalterzeichen des Standardblocks (U+E000–U+E00B) in der Eingabe: `_git_lex` liefert `None`, die Commit-Erkennung prüft dann im Zweifel per Teilstring (Fall 3, AC-7). Die Segment- und Umleitungsprüfungen zerlegen mit einem freien Ersatzblock weiter (F001).
- Enthält eine Eingabe Zeichen aus jedem 12er-Block ab U+F0000 (rund 11.000 Zeichen) plus ein Standard-Platzhalterzeichen, findet `_lex_free_base` keinen freien Block; die Segmentprüfungen sehen dann nichts (Adversary-Befund F003, LOW, praktisch nicht erreichbar).
- `$'…'` wird von `shlex` nicht dekodiert: `git $'commit'` gilt als Wort `$commit`, nicht als `commit`. Vorbestehend, Issue #574.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test in `tests/test_git_lex_escapes_572.py` belegt
- [ ] Die Befehle aus dem Issue (`\\`+Umbruch vor `git commit`) werden als `commit` erkannt, und ein echter bash-Lauf in einem Temp-Repo bestätigt, dass bash den Commit ausführt (AC-1)
- [ ] Gequotete oder maskierte Operatoren zerreißen keinen Befehl mehr, echte Trenner und Umleitungen verhalten sich unverändert (AC-4, AC-5)
- [ ] Nicht sicher zerlegbare Eingaben fallen auf die vorsichtige Prüfung zurück (AC-7)
- [ ] CHANGELOG `[Unreleased]` → Fixed nennt `#572`
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün)

## Acceptance Criteria

Testaufbau: reine Funktionsaufrufe auf `hook_utils` und `bash_gate`; Fortsetzungs-Fälle zusätzlich per `subprocess` mit `bash -c` in einem Temp-Git-Repo.

- **AC-1:** Given `git status a\\<LF>git commit -m x` sowie die Issue-Repro mit `"a\\<LF>"` / When `is_git_subcommand(cmd, "commit")` prüft / Then ist das Ergebnis True, und ein echter bash-Lauf in einem Temp-Repo führt den Commit wirklich aus
  - Test: tests/test_git_lex_escapes_572.py::test_escaped_backslash_before_newline_exposes_commit

- **AC-2:** Given echte Fortsetzungen `git \<LF>commit`, `gi\<LF>t commit`, `"a\<LF>b"` und `\`+CRLF / When `_git_lex` zerlegt / Then entsteht dasselbe Ergebnis wie bei bash (`git commit`, `git commit`, Wort `ab`, CRLF-Fortsetzung entfernt)
  - Test: tests/test_git_lex_escapes_572.py::test_real_line_continuations_still_joined

- **AC-3:** Given `'a\<LF>b'` und `$'a\<LF>b'` / When `_git_lex` zerlegt / Then bleibt der Token-Inhalt `a\<LF>b` unverändert, es gibt keine Fortsetzung
  - Test: tests/test_git_lex_escapes_572.py::test_no_continuation_inside_single_and_ansi_c_quotes

- **AC-4:** Given gequotete oder maskierte Operator- und Trennwort-Zeichen (`';'`, `'&&'`, `\;`, `'|'`, `'>'`, `'{'`, `"!"`) / When `_git_segments` zerlegt und die Schreib-Erkennung in `bash_gate` prüft / Then ist `_git_segments("cp ';' x")` genau ein Segment, `_writes_main_repo` sieht `cp ';' <Ziel im Haupt-Repo>` als Schreibzugriff auf das Ziel, und `_redirects_to_protected` ignoriert `echo '>' <Pfad>`, erkennt aber eine echte Umleitung `echo x > <geschützter Pfad>`
  - Test: tests/test_git_lex_escapes_572.py::test_quoted_operators_are_not_separators_or_redirects

- **AC-5:** Given echte Trenner und Umleitungen `cd /tmp&&git commit`, `git status;>x`, `2>&1`, Heredoc und mehrzeilige `-m`-Messages / When `_git_segments` und `_git_lex` zerlegen / Then bleibt das Verhalten unverändert (Trenner trennen, Umleitungen bleiben Umleitungen, die mehrzeilige Message ist ein Token)
  - Test: tests/test_git_lex_escapes_572.py::test_real_separators_and_redirects_unchanged

- **AC-6:** Given `eval git status ';' git commit -m x` und `find . -exec git status \; -exec git commit -m x \;` / When `is_git_subcommand(cmd, "commit")` prüft / Then wird `commit` weiterhin erkannt (Positions-Suche)
  - Test: tests/test_git_lex_escapes_572.py::test_position_search_still_finds_commit

- **AC-7:** Given ein offenes Quote am Ende oder ein Platzhalterzeichen in der Eingabe / When `_git_lex` zerlegt / Then ist das Ergebnis `None`, und `is_git_subcommand` fällt auf Fall 3 zurück (prüft im Zweifel)
  - Test: tests/test_git_lex_escapes_572.py::test_unparseable_input_returns_none_and_falls_back

- **AC-8:** Given `$'` innerhalb von `"…"` (z. B. `echo "$'x" ; git commit -m y`) / When `_git_lex` zerlegt / Then öffnet es kein Quote, das Wort bleibt Teil des `"…"`-Inhalts, und `commit` wird erkannt
  - Test: tests/test_git_lex_escapes_572.py::test_ansi_c_quote_opener_inside_double_quotes_is_literal

- **AC-9:** Given die bestehende Test-Suite / When `pytest tests/` läuft / Then bleibt sie grün, insbesondere die Erkennungs-Tests (#299, #319) und die Kern-Gate-Tests
  - Test: tests/test_git_invocation_detection.py (gesamte Datei, Regressionslauf)

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- Test: GIVEN `a\\`+Umbruch+`git commit` WHEN `is_git_subcommand(..., "commit")` THEN True, bash führt den Commit im Temp-Repo wirklich aus (AC-1)
- Test: GIVEN echte Fortsetzungen inkl. CRLF WHEN `_git_lex` THEN Token wie bei bash (AC-2)
- Test: GIVEN `'…'` und `$'…'` mit Backslash+Umbruch WHEN `_git_lex` THEN Inhalt unverändert (AC-3)
- Test: GIVEN gequotete/maskierte Operatoren WHEN `_git_segments`, `_writes_main_repo`, `_redirects_to_protected` THEN keine Trenner, Ziel sichtbar, echte Umleitung erkannt (AC-4)
- Test: GIVEN echte Trenner, Umleitungen, Heredoc, mehrzeilige Message WHEN Zerlegung THEN unverändert (AC-5)
- Test: GIVEN `eval`/`find -exec` mit gequotetem Trenner WHEN `is_git_subcommand` THEN commit erkannt (AC-6)
- Test: GIVEN offenes Quote oder Platzhalterzeichen WHEN `_git_lex` THEN None, Fall 3 (AC-7)
- Test: GIVEN gequotetes Platzhalterzeichen vor einem geschützten Schreibzugriff WHEN `_git_segments`, `_redirects_to_protected` und bash_gate THEN Segmente mit Originalzeichen, Schreibzugriff geblockt wie ohne das Zeichen (AC-7, Befund F001; `test_placeholder_chars_do_not_open_write_checks`)
- Test: GIVEN `$'` in `"…"` WHEN `_git_lex` THEN kein Quote geöffnet (AC-8)

Ausführung:

- Neue Datei: `pytest tests/test_git_lex_escapes_572.py`
- Betroffene bestehende Tests: `pytest tests/test_git_invocation_detection.py tests/test_bash_gate_erkennung_299_teil_c.py`
- TDD RED: Die neue Testdatei muss vor der Implementierung fehlschlagen (heute verschwindet `git commit` hinter `\\`+Umbruch, und `cp ';' x` ergibt zwei Segmente)
- Regressionslauf: `pytest tests/` (lokal im venv mit `pytest` und `pyyaml`)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Das Repo führt keine ADR-Sammlung, und die Vorgänger-Änderungen am Lexer (#298, #304, #318, #319) haben bewusst keine ADR eingetragen. Diese Änderung schließt eine Abweichung zwischen Lexer und bash-Semantik innerhalb der bestehenden Architektur (Vorstufe vor `shlex`, Grundhaltung „nicht zerlegbar → Fall 3"). Weder ein neues Gate noch eine neue Regel entsteht; die Wahl gegen einen eigenen Tokenizer ist im Implementation-Details-Abschnitt begründet.

## Changelog

- 2026-11-10: Initial spec created
- 2026-11-10: Implementation Details/Known Limitations/Test Plan nach Adversary-Befund F001 ergänzt (`_git_lex_robust`)
