# Adversary Dialog — fix-572-git-lex-escapes
Spec: docs/specs/fix-572-git-lex-escapes.md
Datum: 2026-11-10 19:33

## Checkliste
- [x] **Input:** Bash-Befehlszeichenketten mit Backslash-Fortsetzungen, maskierten Backslashes, gequoteten oder maskierten Operatorzeichen, offenen Quotes. (Beleg: Runde 1, 77 handgeschriebene Fälle plus 4500 Zufallsfälle gegen echtes bash)
- [x] **Output:** `_git_lex`, `_git_segments` und `is_git_subcommand` liefern dieselben Wörter und Befehlsgrenzen wie bash. Gequotete/maskierte Operatoren bleiben Wortinhalt (`_QuotedWord`). Nicht sicher zerlegbare Eingaben liefern `None`, und `is_git_subcommand` fällt auf Fall 3 zurück. (Beleg: Runde 1; Ausnahme `$'…'` mit Inhalt siehe F002, vorbestehend)
- [x] **Side effects:** Keine Schreibzugriffe, keine neuen Konfigurationsschalter. Das Commit-Gate sieht `git commit` auch hinter `\\`+Umbruch; Schreib-Erkennungen sehen `cp ';' <Ziel>` als einen Befehl mit Ziel. (Beleg Runde 3: F001 behoben, `echo ''; <Schreibbefehl>` blockt wieder mit rc 2; Restpunkt F003 LOW)
- [x] **AC-1:** Given `git status a\\<LF>git commit -m x` sowie die Issue-Repro mit `"a\\<LF>"` / When `is_git_subcommand(cmd, "commit")` prüft / Then ist das Ergebnis True, und ein echter bash-Lauf in einem Temp-Repo führt den Commit wirklich aus (Beleg: Runde 1, Fälle 1/2 des Fuzz-Skripts, echter Gate-Lauf rc 2)
- [x] **AC-2:** Given echte Fortsetzungen `git \<LF>commit`, `gi\<LF>t commit`, `"a\<LF>b"` und `\`+CRLF / When `_git_lex` zerlegt / Then entsteht dasselbe Ergebnis wie bei bash (`git commit`, `git commit`, Wort `ab`, CRLF-Fortsetzung entfernt) (Beleg: Runde 1, kein UNDER-Treffer)
- [x] **AC-3:** Given `'a\<LF>b'` und `$'a\<LF>b'` / When `_git_lex` zerlegt / Then bleibt der Token-Inhalt `a\<LF>b` unverändert, es gibt keine Fortsetzung (Beleg: Pytest-Lauf grün, Fuzz-Fälle `echo '\\\n'; git commit`)
- [x] **AC-4:** Given gequotete oder maskierte Operator- und Trennwort-Zeichen (`';'`, `'&&'`, `\;`, `'|'`, `'>'`, `'{'`, `"!"`) / When `_git_segments` zerlegt und die Schreib-Erkennung in `bash_gate` prüft / Then ist `_git_segments("cp ';' x")` genau ein Segment, `_writes_main_repo` sieht `cp ';' <Ziel im Haupt-Repo>` als Schreibzugriff auf das Ziel, und `_redirects_to_protected` ignoriert `echo '>' <Pfad>`, erkennt aber eine echte Umleitung `echo x > <geschützter Pfad>` (Beleg: Runde 1, Lexer-Ausgabe und Gate-Läufe für `echo x '>'>f`, `cp ';' <State>`)
- [x] **AC-5:** Given echte Trenner und Umleitungen `cd /tmp&&git commit`, `git status;>x`, `2>&1`, Heredoc und mehrzeilige `-m`-Messages / When `_git_segments` und `_git_lex` zerlegen / Then bleibt das Verhalten unverändert (Trenner trennen, Umleitungen bleiben Umleitungen, die mehrzeilige Message ist ein Token) (Beleg: Runde 1, Heredoc-Fälle im Fuzz, Pytest grün)
- [x] **AC-6:** Given `eval git status ';' git commit -m x` und `find . -exec git status \; -exec git commit -m x \;` / When `is_git_subcommand(cmd, "commit")` prüft / Then wird `commit` weiterhin erkannt (Positions-Suche) (Beleg: Pytest grün)
- [x] **AC-7:** Given ein offenes Quote am Ende oder ein Platzhalterzeichen in der Eingabe / When `_git_lex` zerlegt / Then ist das Ergebnis `None`, und `is_git_subcommand` fällt auf Fall 3 zurück (prüft im Zweifel) (Beleg Runde 3: `_git_lex` strikt None, `is_git_subcommand` Fall 3 rc 2; Schreib-Erkennungen nutzen `_git_lex_robust`)
- [x] **AC-8:** Given `$'` innerhalb von `"…"` (z. B. `echo "$'x" ; git commit -m y`) / When `_git_lex` zerlegt / Then öffnet es kein Quote, das Wort bleibt Teil des `"…"`-Inhalts, und `commit` wird erkannt (Beleg: Fuzz-Fälle `echo "$'" ; git commit`, `echo "\$'" ; git commit`, kein UNDER)
- [x] **AC-9:** Given die bestehende Test-Suite / When `pytest tests/` läuft / Then bleibt sie grün, insbesondere die Erkennungs-Tests (#299, #319) und die Kern-Gate-Tests (Beleg: gezielter Lauf `162 passed`, siehe adversary-test-output.txt; kompletter `pytest tests/`-Lauf wurde wegen Laufzeit nicht abgewartet)

## Dialog

### Runde 1
**Adversary:** Ich greife die Unter-Erkennung an (bash führt `git commit` aus, `is_git_subcommand(cmd,"commit")` sagt False) und die Schreib-Erkennungen. Fragen: (1) Stimmen Fortsetzungen, maskierte Backslashes, CRLF, `\"`, `\'`, `$'…\'…'`, Heredocs, `{`/`}`/`!`, Kommentare mit Quotes mit echtem bash überein? (2) Bleiben gequotete Operatoren in Tokenfolgen mit echten Operatoren (`echo x '>'>f`, `'a;b'>f`) korrekt getrennt? (3) Was passiert, wenn `_lex_prepare` None liefert: Fall 3 gilt nur in `is_git_subcommand`, die Schreib-Erkennungen nutzen `_git_segments(...) or []`. (4) Verhalten gegenüber dem Stand vor der Änderung (19c448e).

**Implementierer:** Gemessene Belege (Skripte im Scratchpad `/tmp/claude-0/sp`, Orakel ist echtes `bash -c` mit einem `git`-Shim, der das erste Argument protokolliert):
- (1) `fuzz.py`: 77 handgeschriebene Fälle (Fortsetzung hinter `\\`, `\\\\`, `\\\\\\`, CRLF, `$'it\'s'`, `"a\"b"`, `${x:-'}'}`, Heredocs, `{ …; }`, `! …`, Kommentare mit `'`) ergeben `bad 0 of 77`. Dazu drei Zufallsläufe über je 1500 Fälle (Alphabet aus `git commit`, Quotes, `\`, LF, CRLF, `$'`, Operatoren, Heredoc-Anfang): zwei Läufe `bad 0`, einer `UNDER "git commit$''" False` (siehe F002). Alle anderen Abweichungen waren Über-Erkennung (z. B. `git commit\` am Ende, `true||git commit`, wo bash selbst nicht ausführt oder Syntaxfehler meldet): LOW, absichtlich vorsichtig.
- (2) `lex.py`: `echo x '>'>f` -> Tokens `echo x >(_QuotedWord) >(str) f`, ein Segment `['echo','x','>','>','f']`; `echo 'a;b'>f` -> `['echo','a;b','>','f']`; `echo x>';'f` -> `>` dann `;f`; `echo x '|'&&git commit` -> zwei Segmente, `git commit` erkannt. Echte Umleitung bleibt echt, gequotete bleibt Wort.
- (3) `gate3.py` (echte Gate-Subprozesse im Sandbox-Projekt): `echo x > .claude/cloud_bootstrap.py` -> rc 2 (BLOCKED). `echo ''; echo x > .claude/cloud_bootstrap.py` -> **rc 0** (nicht blockiert, bash würde schreiben). Ebenso `echo ''; export OPENSPEC_AUTONOMY=1` rc 0 und `echo ''; cp a .claude/framework_version.json` rc 0. Vorher (`gate4.py`): `old._git_segments(...)` liefert zwei Segmente, neu `None`. Ursache: `_lex_prepare` gibt bei jedem Zeichen aus U+E000..U+E00x None zurück (hook_utils.py:449 ff.), und bash_gate.py:1873/1883/1891/1902 setzen bei None `or []` ein, die Prüfungen laufen auf leerer Liste. `echo "unterminated; …` liefert ebenfalls rc 0, ist aber vorbestehend und kein Bypass, weil bash selbst mit Syntaxfehler abbricht; ein PUA-Zeichen dagegen ist gültiger bash-Text. Die State-Datei-Schutzregeln (`Direct state file manipulation`) bleiben dank Regex-Rückfall auch bei PUA-Zeichen wirksam (`gate2.py`, rc 2).
- (4) `diff.py` (20000 Zufallsbefehle, alt gegen neu `_git_segments`): 324 Abweichungen, alle in die richtige Richtung (maskierte `\;`, `\|`, `\&&`, `\}` bleiben Wortinhalt statt Trenner, z. B. `'\\;'` alt `[]`, neu `[[';']]`). Keine Abweichung, bei der neu ein echter Trenner fehlt.
Code reference: core/hooks/hook_utils.py:469 (`_lex_prepare`, Rückgabe None bei Platzhalterzeichen des Blocks) und core/hooks/hook_utils.py:496 (alter Stand, `_git_lex`).
Code reference: core/hooks/bash_gate.py:1902 (`_writes_main_repo(_git_segments(scan_cmd) or [], …)`, ebenso 1873/1883/1891) und core/hooks/bash_gate.py:289 (`_strip_leading_separators`, unauffällig).

**Findings:**
```json
[
  {"id": "F001", "severity": "HIGH", "category": "regression",
   "description": "Ein Zeichen aus dem Platzhalterbereich U+E000-U+E00x irgendwo im Befehl (auch in einem Quote) macht _lex_prepare/_git_lex/_git_segments zu None. Alle segmentbasierten Schutzpruefungen in bash_gate (Gate-Config, OPENSPEC_AUTONOMY, Cloud-Gate-Dateien, Haupt-Repo-Schreibzugriff) laufen dann mit `or []` auf leerer Liste und lassen den Befehl durch; bash fuehrt ihn aus. Vor der Aenderung wurde so ein Befehl zerlegt und blockiert.",
   "evidence": "core/hooks/hook_utils.py:449 (return None), core/hooks/bash_gate.py:1873,1883,1891,1902; Gate-Lauf: echo '\\ue000'; echo x > .claude/cloud_bootstrap.py -> rc 0, ohne Zeichen rc 2",
   "remediation": "Platzhalter dynamisch aus einem in der Eingabe unbenutzten Codepunktbereich waehlen (statt None), oder Aufrufer bei None konservativ behandeln (Fall 3 / Rohtext-Regex wie in _deletes_dependency_dir), oder Tokens mit PUA-Zeichen im Rohtext vorab maskieren."},
  {"id": "F002", "severity": "MEDIUM", "category": "security",
   "description": "Vorbestehend, nicht durch diese Aenderung verursacht: ANSI-C-Quoting im Unterbefehl umgeht das Commit-Gate. shlex kennt `$'…'` nicht, `git $'commit' -m x` wird als Token `$commit` gelesen, bash fuehrt `git commit` aus. Gleiches fuer `git commit$''` und `git $'\\x63ommit'`.",
   "evidence": "real: PATH=<shim> bash -c \"git $'commit' -m x\" protokolliert `commit`; Gate-Lauf `git $'commit' -m x` rc 0 (alter und neuer Lexer gleich, cmp.py)",
   "remediation": "In _lex_prepare `$'…'`-Inhalt bash-gerecht dekodieren (Escapes, `$` weg) oder Befehle mit `$'` vor einem Unterbefehl in Fall 3 schicken; eigenes Issue."}
]
```

### Runde 2
**Adversary:** Nachbohren: (a) Ist F001 mit realistischen Eingaben erreichbar, oder nur mit exotischen Zeichen? (b) Greift der Rückfall "Fall 3" wenigstens für das Commit-Gate bei PUA-Zeichen? (c) Schlägt der Reviewer-Kommentar-Pfad (`_strip_shell_comments` vor `_lex_prepare`) das PUA-Zeichen weg, wenn es nur in einem Kommentar steht? (d) Bleibt die Suite insgesamt grün?

**Implementierer:** Belege:
- (a) U+E000 ist ein gültiges, im Quote oder Wort frei verwendbares Zeichen (Icon-Schriften, Nerd-Font-Glyphen kommen in Terminalausgaben und Dateien vor, z. B. Text aus Prompt-Themes), und der Angreifer kann es absichtlich einbauen. `gate3.py` zeigt rc 0 für alle drei segmentbasierten Schutzziele.
- (b) Commit-Gate: `echo ''; git commit -m x` -> rc 2 (`Adversary verdict missing`), Fall 3 greift (`gate2.py`). Das Commit-Gate bleibt dicht, nur die Schreib-Erkennungen sind betroffen.
- (c) Zeichen nur im Kommentar: `_strip_shell_comments` läuft vor `_lex_prepare`, das Zeichen verschwindet, der Befehl wird normal zerlegt (Code hook_utils.py:513-516). Nur Zeichen im Befehl selbst lösen None aus.
- (d) Gezielter Lauf `pytest tests/test_git_lex_escapes_572.py tests/test_git_invocation_detection.py tests/test_bash_gate_erkennung_299*.py -q`: `162 passed in 20.95s` (adversary-test-output.txt). Die Tests decken F001 nicht ab: AC-7 prüft nur `_git_lex is None` und `is_git_subcommand`, nicht die Schreib-Erkennungen.
Code reference: core/hooks/hook_utils.py:496 und core/hooks/bash_gate.py:1902.

### Runde 3
**Adversary:** Ich prüfe den Fix (`_lex_tokens`, `_lex_free_base`, `_git_lex_robust`, Nutzung in `_git_segments` und `_redirects_to_protected`) in vier Richtungen: (1) Sind die F001-Reproduktionen jetzt wieder rc 2? (2) Zeichen aus dem Ausweichblock U+F0000.., Zeichen beider Blöcke, Surrogate, Randcodepoints, sehr lange Eingaben. (3) Weichen `_git_lex` (strikt) und `_git_segments` (robust) so ab, dass `is_pure_git_command`/Whitelist getäuscht wird, etwa ein erlaubter git-Befehl mit Standardblock-Zeichen, der Geschütztes schreibt? (4) Commit-Unter-Erkennung per bash-Orakel auf dem neuen Code. Außerdem: kann man alle Ausweichblöcke belegen, sodass `_lex_free_base` None liefert?

**Implementierer:** Belege:
- (1) `gate3.py` (echte Gate-Subprozesse): `echo ''; echo x > .claude/cloud_bootstrap.py` rc 2, `echo ''; export OPENSPEC_AUTONOMY=1` rc 2, `echo ''; cp a .claude/framework_version.json` rc 2 (zuvor rc 0). `gate2.py`: `echo ; git commit -m x` rc 2. Offenes Quote (`echo "unterminated; …`) bleibt rc 0, vorbestehend und kein Bypass, weil bash dort selbst abbricht.
- (2) `gate5.py`: Zeichen aus U+F0000, beide Blöcke gemischt (24 Zeichen), Surrogate `\ud800`/`\udfff`, `\U0010ffff\U0010fffe`, 50000 mal `a;` im Quote: alle rc 2 (Schreibziel bzw. Commit-Gate), längster Lauf 1,13 s. 50000 mal `` kann der Test-Harness nicht über die Umgebung übergeben (`OSError Argument list too long`); auf Funktionsebene (`exh.py`) liefert `_git_segments` dafür die erwarteten Segmente (`['echo','…'], …`), kein None.
- (3) `gate5.py`: `git status '' > <State>`, `git status  > <State>`, `git status;'' > <State>` rc 2 (State-Schutz), `echo ''; git status && touch .claude/user_approved_validation_x` rc 2. Lexer-Ebene: strikt None, robust Tokens, `is_pure_git_command` False, d. h. die Whitelist-Ausnahme wird bei Standardblock-Zeichen NICHT gewährt (sichere Richtung). `_is_confidently_decomposed` nutzt weiter den strikten `_git_lex` (hook_utils.py:622), also Fall 3 für `is_git_subcommand`.
- (4) `fuzz.py` mit drei neuen Seeds (11/12/13, je 1500 Zufallsbefehle plus die 77 festen Fälle): zweimal `bad 0`, einmal ein UNDER-Treffer `git commit' <<EOF\n#`}$'`. Das ist ein Fehlalarm meines Orakels: bash liest `commit <<EOF…` als EIN Wort (Quote geht bis zum `$'`), git bekommt keinen Unterbefehl `commit`. Kein Gate-Befund.
- Ausschöpfung: `exh.py` baut einen Befehl mit je einem Zeichen pro 12er-Block des Supplementary-PUA (43739 Byte): `_git_segments` liefert None, `_lex_free_base` None. Siehe F003 (LOW): nur mit gezielt gebautem Befehl ab etwa 44 KB; die Gate-Prüfung über die Umgebungsvariable scheitert dort schon am Argumentlängen-Limit des Systems (nicht über den Gate-Subprozess verifiziert, nur auf Funktionsebene).
- Tests: `pytest tests/test_git_lex_escapes_572.py tests/test_git_invocation_detection.py tests/test_bash_gate_erkennung_299*.py -q` gibt `163 passed in 18.82s` (adversary-test-output.txt), darunter der neue `test_placeholder_chars_do_not_open_write_checks`.
Code reference: core/hooks/hook_utils.py:454 (`_lex_free_base`), core/hooks/hook_utils.py:518 (`_lex_tokens`), core/hooks/hook_utils.py:537 (`_git_lex_robust`), core/hooks/hook_utils.py:625 (`_git_segments`).
Code reference: core/hooks/bash_gate.py:312 (`_redirects_to_protected` nutzt `_git_lex_robust`), core/hooks/bash_gate.py:289 (`_strip_leading_separators`).

**Bewertung:** F001 behoben (Belege oben). Neu: F003 LOW.
```json
[
  {"id": "F001", "severity": "HIGH", "category": "regression", "status": "RESOLVED",
   "description": "Platzhalterzeichen im Befehl schalteten die segmentbasierten Schreib-Erkennungen ab. Behoben durch _git_lex_robust mit freiem Ausweichblock.",
   "evidence": "gate3.py: alle drei Reproduktionen rc 2; tests/test_git_lex_escapes_572.py::test_placeholder_chars_do_not_open_write_checks gruen",
   "remediation": "keine"},
  {"id": "F003", "severity": "LOW", "category": "edge_case",
   "description": "Enthaelt der Befehl je ein Zeichen aus JEDEM 12er-Block U+F0000..U+10FFFD (ca. 10900 Zeichen, 43,7 KB) plus eines aus dem Standardblock, liefert _lex_free_base None, _git_segments wird None und die Schreib-Erkennungen laufen auf leerer Liste.",
   "evidence": "/tmp/claude-0/sp/exh.py: _git_segments(c) is None bei 43739 Byte; Gate-Subprozess nicht ausfuehrbar (Argument list too long)",
   "remediation": "Bei base None statt None den Rohtext-Rueckfall nutzen oder die Schreib-Erkennungen bei None konservativ blocken; oder Befehle ab einer Laengengrenze mit Platzhalter-Ueberlauf blockieren."}
]
```

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict
**VERIFIED**
Offene Punkte: 0 / 13

F001 (HIGH) behoben und in Runde 3 mit echten Gate-Läufen belegt. Restpunkt F003 (LOW, Ausschöpfung der Platzhalterblöcke ab ca. 44 KB) und das vorbestehende F002 ($'…' im Unterbefehl, Issue #574) sind keine Blocker.

## Geprüfte Dateien

- sha256:c5aec4a3e655a81d82cc8f63c1dfa984d5ebd90889df5cd332aae63dadf5ff17  core/hooks/bash_gate.py
- sha256:6e45898f63d75efdb5ba127bf272b3dd5a6783fd5d56171fac982a9e4ff04761  core/hooks/hook_utils.py

## Prüfbasis

- base: 19c448e145aa6a821bfa8e3535ebf893bc3f81e1
- blob:35cde648ee478a7b1a3cd86df3adc0cd62c07531  core/hooks/bash_gate.py
- blob:f356f4498499ba3c48db7e9482fc0d99c6ff9a95  core/hooks/hook_utils.py
