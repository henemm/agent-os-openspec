# Adversary-Dialog — fix-281-git-alias-commit-gate (#281)

**Rolle:** implementation-validator (Adversary; Kontext-Isolation: nur Spec, Tests und Liste der geänderten Dateien).
**Stand:** Runde 3 (kurze Abschlussprüfung nach der PO-Entscheidung) abgeschlossen — das Verdict steht am Ende dieses Protokolls (Runde 1 blieb ohne Verdict, Runde 2 endete mit BROKEN; Runde 3 ab `### Runde 3`; danach `adversary_dialog.py stamp`). Belege: `docs/artifacts/fix-281-git-alias-commit-gate/adversary-repro-round2.txt` und `adversary-repro-round3.txt`.
**Material:** Spec `docs/specs/fix-281-git-alias-commit-gate.md` (27 Checklisten-Punkte: 10 Expected Behavior + AC-1…AC-17); Pflicht-Dateien (`adversary_dialog.py required-files`): `core/hooks/bash_gate.py`, `core/hooks/git_alias.py`; Tests `tests/test_git_alias_commit_gate_281.py`.
**Arbeitsweise:** Wegwerf-Repos unter `/tmp`, hermetisch (`HOME` im tmp-Baum, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, keine `GIT_*`-/Sitzungsvariablen). Gesperrter Zustand wie in der Testvorlage: Workflow `feature`, `phase6_implement`, kein Verdict, gestagte Änderung. Jeder Bypass wurde gegen die **echte bash** gegengeprüft (Commit entstanden: ja/nein) und gegen das **alte** Gate (HEAD, per `git archive` entpackt) verglichen. Reproduktionslauf mit Ausgabe: `docs/artifacts/fix-281-git-alias-commit-gate/adversary-repro-round1.txt` (Wegwerf-Skripte: `/tmp/claude-0/-home-user-agent-os-openspec/76054b3f-0401-5941-9b95-6f771556ea2e/scratchpad/adv/`, dort `advlib.py`, `repro_round1*.py`, `atk*.py`). Am Repo, an Code, Tests, Spec und Doku wurde nichts geändert.

## Testläufe (selbst ausgeführt, den mitgelieferten GREEN-Belegen nicht vertraut)

| Lauf | Ergebnis |
|------|----------|
| `python3 -m pytest tests/test_git_alias_commit_gate_281.py -q` | 151 passed |
| `python3 -m pytest tests/ -q` (gespeichert: `docs/artifacts/fix-281-git-alias-commit-gate/adversary-test-output.txt`) | 1710 passed, 28 skipped, Exit 0 |
| Invarianz-Differential: 450 zufällige Befehlsketten (Builtin-git bzw. ohne git; Trenner, Wrapper, Heredocs, Marker-/Protected-Pfade), je gesperrt und ohne Workflow, ALTES (HEAD) gegen NEUES Gate | 900 Läufe, 0 Abweichungen im Exit-Code |
| Heißer Pfad: git-Wrapper zählt JEDEN git-Prozess (`status`, `-C . status`, `--no-pager log`, `GIT_DIR=… status`, `env X=1 diff`, `add`, `stage`, `push`, `worktree`, `rev-parse`, `config`, Ketten) | 0 Prozesse, alt = neu; `git submodule status` / `git st` = 1 Abfrage; `git commit` = 1 Prozess (vorhanden: `git diff --cached`) |
| Robustheit: git-Wrapper hängt / liefert Müll, Binärdaten, 200 MB / rc 129 / rc 141; `LC_ALL=C`, `PYTHONIOENCODING=ascii:strict`; ohne `HOME`; Override-Token; Stop-Lock | kein Traceback; drei Abfragen ≤ 6,1 s; Override hebt den Alias-Block auf; Stop-Lock startet keinen git-Prozess |
| Resolver-Fuzz: 60 000 zufällige Shell-Token-Folgen, Fake-Runner | 0 × „interner Fehler“ |
| Struktur-Fuzz gegen echte bash: 1000 Befehle (Wrapper × Container × Quoting, lokaler Alias) ohne die Formen aus F001 und ohne Here-String (Parität zum alten Gate); mit diesen Formen gab es in 600 Läufen 65 Bypässe, alle F001 bzw. Here-String | 0 Bypässe (ohne diese Formen) |
| Alias-Quellen-Fuzz gegen echte bash: 570 Fälle (Ketten, Optionen, `-C`/`cd`/`-c`/`--config-env`/`GIT_CONFIG_GLOBAL`/verschachtelt/Präfix) | einziger Bypass: F003 |
| `git --list-cmds=builtins` gegen `GIT_BUILTINS` (git 2.43.0) | identisch (140 = 140) |
| `python3 scripts/ci_spec_gate.py --base origin/main` | „keine Code-Änderung im PR — nichts zu prüfen“ (Änderungen sind noch nicht committet) — nicht aussagekräftig |

## Vorläufiger Stand je Checklisten-Punkt (Runde 1; verbindlich erst in Runde 2)

| # | Punkt | Vorläufig | Bezug |
|---|-------|-----------|-------|
| 1 | Input (cwd, Umgebung, Alias-Konfiguration „dort, wo der Aufruf läuft“) | widerlegt in Teilen | F002, F004, F005, F009 |
| 2 | Output (Exit 0/2, stderr-Zeile) | bestätigt, Vorbehalt Timeout | F008 |
| 3 | Side effects (≤ 3 Abfragen, „schreibt nichts“) | widerlegt in Teilen | F012 |
| 4 | Builtins (nie nachgeschlagen, exakt/case-insensitiv) | bestätigt | Heißer-Pfad-Messung |
| 5 | Unterbefehl erst zur Laufzeit bekannt → unresolved | widerlegt in Teilen | F011, F006 |
| 6 | Alias auf `commit` gilt wie `commit` | widerlegt | F001, F003, F007 |
| 7 | Shell-Aliase (Rumpf auf Commit/Marker/Secrets geprüft) | widerlegt in Teilen | F007 |
| 8 | Kontext nachgespielt / Alias-Änderung im selben Befehl | widerlegt | F002, F004, F005, F009, F017 |
| 9 | Fehlerrichtung „prüfen“ | widerlegt in Teilen | F006 |
| 10 | Invarianz bei leerer Sicht, `_is_whitelisted` unverändert | bestätigt (900 Läufe), Vorbehalt Laufzeit | F008 |
| 11–27 | AC-1 … AC-17 wie wörtlich formuliert | AC-1…AC-17 bestätigt (Tests + eigene E2E), Varianten je AC widerlegt | AC-1: F001; AC-3: F002; AC-5: F003; AC-6: F007; AC-7: F004; AC-9: F008; AC-11: F012; AC-12: F010; AC-15: F006 |

## Runde 1

### Runde 1 — Angriffe des Adversary (ohne Verdict)

**Adversary:** Ich habe die Implementierung nicht auf dem Happy Path geprüft, sondern gegen die echte bash: Alias `ci = commit` gilt als Ziel, gesperrter Zustand, Ergebnis „Exit 0 des Hooks UND Commit entsteht“ = Bypass. Die Findings F001–F007 und F009 sind solche Bypässe; F008 ist eine Regression mit Fail-open-Folge, F010 eine Unterzählung der #259-Menge, F012 verletzt die Zusicherung „die Abfrage schreibt nichts“; F011, F013–F017 sind kleiner oder Parität zum alten Gate. Bekannte Grenzen der Spec (`bash -lc` → #298, externe `git-<name>` → #297, Whitelist-Gefälle #296, Shell-Funktion `git`, `source`, Tiefe > 2, ältere git-Versionen) habe ich NICHT als Finding gewertet.

#### Findings

Finding:
  ID: F001
  Severity: CRITICAL
  Category: spec_violation
  Code reference: core/hooks/git_alias.py:311
  Code reference: core/hooks/bash_gate.py:631
  Description: Beide Einstiegspunkte brechen mit der rohen Teilstring-Prüfung `"git" not in command` ab und liefern die leere Sicht. Bash und `_git_lex` normalisieren Quoting, Backslash und Zeilenfortsetzung aber vor der Befehlsauflösung: `g""it`, `"g""it"`, `gi''t`, `g\it`, `gi\<Zeilenumbruch>t` sind das Wort `git`, enthalten den Teilstring jedoch nicht. Der Resolver läuft nie; `is_pure_git_command` (token-basiert) hält den Befehl für reines git, der Schnellpfad lässt ihn durch. Das WÖRTLICHE `g""it commit -m x` blockt (Exit 2), der Alias-Weg nicht.
  Spec requirement: Expected Behavior „Alias auf commit gilt wie commit“, AC-1 (die Reproduktion aus #281), Abschnitt 1 („Enthält der Befehl das Teilwort git nicht, kommt sofort die leere Sicht zurück“).
  Conflict: Die Reproduktion aus #281 passiert das Gate, sobald ein Anführungszeichen im Wort `git` steht. Echte bash: Commit entsteht. Gilt auch verschachtelt (`bash -c 'g""it ci …'`, Heredoc, `(…)`, `$(…)`).
  Reproduction: gesperrter Zustand + lokales `alias.ci=commit`: `g""it ci -m x` → Exit 0 (erwartet 2), Kontrolle `g""it commit -m x` → Exit 2; ebenso `"g""it" ci`, `g\it ci`, `gi''t ci`. In einer Kopie mit `re.sub(r"[\\'\"\n]", "", command)` vor dem Teilstring-Test blocken alle Varianten (im Scratch geprüft, Repo unberührt).
  Remediation: Vorprüfung streichen oder auf den normalisierten Text anwenden; Test für quote-gesplittetes `git` ergänzen.

Finding:
  ID: F002
  Severity: HIGH
  Category: spec_violation
  Code reference: core/hooks/git_alias.py:284
  Code reference: core/hooks/git_alias.py:162
  Description: Das cd-Modell erkennt `cd`/`pushd`/`popd` nur als erstes Token eines Segments (bzw. hinter einem Kontrollwort). Nicht erkannt und damit als „Verzeichnis unverändert“ (statt „unbekannt“) modelliert: `builtin cd B`, `command cd B`, `X=1 cd B`, `time cd B`. Verschachtelte Texte erben den Stand mit „cd wirkt nicht nach außen“ (Zeile 162) — das stimmt für `sh -c`/`bash -c`, aber NICHT für `eval`, das in der aktuellen Shell läuft (Spec Abschnitt 6 behauptet das Gegenteil). Der Alias wird im falschen Repo nachgeschlagen.
  Spec requirement: AC-3 (Abfrage läuft dort, wo der Aufruf läuft), Expected Behavior „Kontext“, Abschnitt 6 (Aufzählung der „unbekannt“-Fälle).
  Conflict: Alias nur in Repo B, cwd in A: Exit 0, der Commit entsteht in B. Nicht in den Known Limitations (dort stehen nur literale Pfade auf oberster Ebene, `cd -`, `popd`, Kontrollwörter, Subshell/Pipeline/Hintergrund, bedingtes `cd`).
  Reproduction: `eval "cd B" && git ci -m x`, `builtin cd B && git ci -m x`, `command cd B && git ci -m x`, `X=1 cd B && git ci -m x`, `time cd B && git ci -m x` → je Exit 0, bash committet in B. Kontrolle `cd B && git ci -m x` → Exit 2.
  Remediation: `cd`/`pushd`/`popd` an jeder Position des Segments und in `eval` als Verzeichniswechsel mit Außenwirkung behandeln (oder „unbekannt“); Wrapper-Wörter `builtin`, `command`, `time`, Präfix-Zuweisungen abstreifen; Tests für `eval`, `builtin`, `command`, Präfix ergänzen.

Finding:
  ID: F003
  Severity: HIGH
  Category: spec_violation
  Code reference: core/hooks/git_alias.py:261
  Description: Der Alias-Wert wird mit `shlex.split` zerlegt, git zerlegt ihn mit `split_cmdline`. Beide weichen in genau einer Klasse ab: in Doppelanführungszeichen entfernt git den Backslash vor JEDEM Zeichen, shlex nur vor `"` und `\`. Wert `"com\mit"` (zu setzen mit dem reinen git-Aufruf `git config alias.ci '"com\mit"'`): git führt `commit` aus, der Resolver sieht `com\mit` (weder Builtin noch Alias → „Kette endet, kein unresolved“). Eine Portierung von `split_cmdline` gegen `shlex.split` über 600 000 zufällige Werte fand keine andere Abweichungsklasse.
  Spec requirement: Expected Behavior „Alias auf commit … Ketten, Optionen im Alias-Wert“, Abschnitt 7 („wie bei git“).
  Conflict: Ein Alias auf `commit` mit Backslash in Anführungszeichen umgeht das Gate vollständig; zwei reine git-Aufrufe genügen.
  Reproduction: `git config alias.ci '"com\mit"'`, dann `git ci -m x` → Exit 0, bash committet (Ausgabe: `adversary-repro-round1.txt`, F003). Das differentielle Fuzzing gegen echte bash (Seed 1) fand denselben Fall von allein.
  Remediation: `split_cmdline` nachbauen (rund 15 Zeilen) oder Backslash im Alias-Wert als `unresolved` werten; Test ergänzen.

Finding:
  ID: F004
  Severity: HIGH
  Category: spec_violation
  Code reference: core/hooks/git_alias.py:157
  Code reference: core/hooks/git_alias.py:294
  Code reference: core/hooks/git_alias.py:299
  Description: Taint („Alias-Änderung im selben Aufruf“) und cd-Modell wirken nur auf Segmente, die im TEXT später folgen; `walk` arbeitet pro Segment in der Reihenfolge Aufruf → cd → Taint (Zeilen 157–165). Die Ausführungsreihenfolge weicht ab bei Befehls-/Prozess-Substitution in Argumenten und Zuweisungen (läuft vor dem Befehl), Schleifen (zweite Iteration), Funktionen (Definition vor Aufruf) und `trap`. Zusätzlich ist der Inhalt einer gequoteten Substitution (`"x$(git config alias.ci commit)"`) EIN Token: weder Taint (a) noch (b) sehen ihn.
  Spec requirement: Abschnitt 5, AC-7 (a), Expected Behavior „Kontext“ („eine Alias-Änderung im selben Befehl … macht spätere Nicht-Builtins unresolved“). Nicht in den Known Limitations (dort: „Momentaufnahme vor dem Befehl“, Race, verschleierte Wege).
  Conflict: Der Wortlaut von AC-7 (a) `git config alias.ci commit && git ci` blockt, aber die Umstellung der Reihenfolge — ohne jede Verschleierung, `alias.` steht im Klartext — passiert: Exit 0 und Commit.
  Reproduction (alle Exit 0, bash committet; Kontrolle `git config alias.ci commit && git ci -m x` → Exit 2):
    `git ci -m x $(git config alias.ci commit)`
    `git ci -m "x$(git config alias.ci commit)"`
    `X="$(git config alias.ci commit)" git ci -m x`
    `for i in 1 2; do git ci -m x 2>/dev/null; git config alias.ci commit; done`
    `f() { git ci -m x; }; git config alias.ci commit; f`
    `trap 'git ci -m x' EXIT; git config alias.ci commit`
    (dasselbe Muster für das cd-Modell: `for i in 1 2; do git ci -m x 2>/dev/null; cd B; done`, Alias nur in B)
  Remediation: Taint reihenfolgeunabhängig: Kommt irgendwo im Befehl (auch in gequoteten Tokens, Substitutionen, Funktions-/Schleifenkörpern) ein Taint-Merkmal vor, sind ALLE Nicht-Builtin-Aufrufe unresolved (Preis: `git st; git config alias.x y` wird geprüft). Analog: `cd`/`export`/Zuweisung zusammen mit Schleife, Funktion, `trap` oder Substitution → Kontext unbekannt.

Finding:
  ID: F005
  Severity: MEDIUM
  Category: spec_violation
  Code reference: core/hooks/git_alias.py:199
  Code reference: core/hooks/git_alias.py:299
  Description: `--config-env=K=VAR` nimmt den Wert aus der HOOK-Umgebung, sobald VAR dort existiert (Zeilen 199–204). Ein `export VAR=commit` im selben Aufruf ändert den Wert zur Laufzeit; Taint (c) kennt nur die Freigabeliste (`GIT_*`, `HOME`, …), nicht beliebige Namen. Der Resolver rechnet mit dem Hook-Wert (`xterm`), git mit `commit`.
  Spec requirement: Abschnitt 4 („Wert aus einer Präfix-Zuweisung desselben Segments (beliebiger Name) oder aus der Hook-Umgebung“), Abschnitt 5 (c), Expected Behavior „Kontext“.
  Conflict: Bypass mit einem in nahezu jeder Umgebung vorhandenen Namen (`TERM`, `LANG`, `USER`, `SHELL`).
  Reproduction: Hook-Umgebung mit `TERM=xterm`: `export TERM=commit; git --config-env=alias.ci=TERM ci -m x` → Exit 0, bash committet. Kontrollen: `env TERM=commit git --config-env=alias.ci=TERM ci -m x` → Exit 2; Variable, die es in der Hook-Umgebung nicht gibt → Exit 2 (unresolved).
  Remediation: `--config-env` nur aus Präfix-Zuweisung desselben Segments auflösen, sonst unresolved; oder Taint (c) auf jeden als `--config-env`-Variable vorkommenden Namen ausdehnen.

Finding:
  ID: F006
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/git_alias.py:125
  Code reference: core/hooks/git_alias.py:152
  Description: Bei für `shlex` unzerlegbarem Gesamtbefehl sucht der Rückfall `_naive_subs` nur Whitespace-getrennte git-Token (`text.split()`, exakt `git` oder `…/git`). Mit einem Trenner direkt am `git` (`;git`, `&&git`, `||git`, `(git`, `$(git`) bleibt das Token unsichtbar: leere Sicht, Fail-open-Zweig bzw. Fall 2 lassen durch. Das wörtliche `git commit` in derselben Form fängt die Teilstring-Regel (Fall 3).
  Spec requirement: Abschnitt 15, AC-15, Expected Behavior „Fehlerrichtung“ („Was sich nicht sicher auflösen lässt, wird wie ein Commit geprüft“). Grenzfall zur Known Limitation „Nicht zerlegbare Gesamtbefehle … ohne Kandidaten bleibt der Fail-open-Durchlass“ — hier IST ein Kandidat vorhanden, die Suche findet ihn nur nicht.
  Conflict: Der Alias-Weg ist an dieser Stelle schwächer als der wörtliche Commit (Alias: Exit 0; `git commit`: Exit 2).
  Reproduction: `echo $'it\'s';git ci -m x` → Exit 0, bash committet; Kontrolle `echo $'it\'s';git commit -m x` → Exit 2. Ebenso `echo $'it\'s'&&git ci -m x`, `(git ci -m x); echo $'it\'s'`, `git status $'it\'s';git ci -m x`.
  Remediation: Kandidatensuche per Regex mit Trennerzeichen (`(?:^|[\s;&|()`])(?:\S*/)?git(?=\s)`) statt Whitespace-Split; oder bei unzerlegbarem Befehl mit Teilwort `git` und Nicht-Builtin-Rest immer unresolved.

Finding:
  ID: F007
  Severity: MEDIUM
  Category: spec_violation
  Code reference: core/hooks/bash_gate.py:705
  Code reference: core/hooks/git_alias.py:255
  Description: Für Shell-Alias-Rümpfe stellt git den exec-path vorn in `PATH`; `git-commit` (Hardlink/Symlink auf das Builtin, hier `/usr/lib/git-core/git-commit`) ist dort ausführbar. `is_git_subcommand(rumpf, "commit")` kennt nur das Token `git` — `!git-commit`, `!exec git-commit`, `!$(git --exec-path)/git-commit` sind kein „Commit im Rumpf“. Wörtlich außerhalb eines Alias steht `git-commit` nicht im PATH und ist unerheblich.
  Spec requirement: Expected Behavior „Shell-Aliase: … sein Rumpf wird auf Commit, Marker-Schreiben und Secrets geprüft“, Abschnitt 8.
  Conflict: Ein Shell-Alias mit dem gestrichenen Builtin-Namen umgeht Schnellpfad-Ausnahme und Commit-Gates (Nähe zu #297 „Commits ohne commit“, aber hier ist es der `commit`-Builtin selbst).
  Reproduction: `git config alias.ci '!git-commit'`, dann `git ci -m x` → Exit 0, bash committet (ebenso `!exec git-commit`, `!f() { git-commit "$@"; }; f`, `!$(git --exec-path)/git-commit`).
  Remediation: in Rümpfen `git-<builtin>` wie `git <builtin>` behandeln (mindestens `git-commit`); Test ergänzen.

Finding:
  ID: F008
  Severity: HIGH
  Category: regression
  Code reference: core/hooks/git_alias.py:183
  Code reference: core/hooks/git_alias.py:159
  Description: Der Aufwand je git-Token wächst linear mit der Segmentlänge (`seg[:gi]`, `_head(seg)` zweimal, Regex je Token, Zeilen 183–190), insgesamt quadratisch in der Zahl der git-Token pro Segment. Wörtlicher Commit mit Kommentar-Polster (`#` ist für den Lexer normaler Text, `commenters` ist leer): 5 000 Token 0,3 s → 3,8 s; 10 000: 0,4 → 16,0 s; 20 000: 0,7 → 58,7 s; 50 000 (200 KB): alt 1,7 s, neu 368 s. `hooks/hooks.json` gibt `bash_gate` 300 s; bei Überschreitung wird der Hook abgebrochen (Exit weder 0 noch 2 — nach Hook-Semantik ein nicht blockierender Fehler), also läuft auch der WÖRTLICHE Commit durch. (Annahme zur Hook-Semantik; in dieser Umgebung nicht prüfbar.)
  Spec requirement: Brief-Punkt „Robustheit: riesige Befehle — der Hook darf Bash nie lahmlegen“; Expected Behavior „Invarianz“ (das Verhalten bei leerer Sicht darf sich nicht ändern — hier ändert sich die Laufzeit um den Faktor 200 und ggf. das Ergebnis).
  Conflict: Der Resolver läuft VOR der wörtlichen Prüfung; ein langsamer Resolver schwächt das ganze Gate.
  Reproduction: gesperrter Zustand, `git commit -m x # ` + `git ` × 50 000 → `python3 core/hooks/bash_gate.py` braucht 368 s (altes Gate: 1,7 s; beide zuletzt Exit 2).
  Remediation: `before`/`_head` je Segment einmal berechnen; harte Obergrenze (z. B. > 2 000 git-Token oder > 200 KB → unresolved ohne Auswertung) und Gesamtdeadline des Resolvers (z. B. 3 s, danach unresolved).

Finding:
  ID: F009
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/git_alias.py:184
  Description: Nur das exakte Token `env` mit Option (und `sudo`) macht den Kontext unresolved. Nicht erkannt werden Wrapper, die das Arbeitsverzeichnis oder die Umgebung ändern und anders geschrieben sind: `/usr/bin/env -C B git …` (Pfadform), `find B … -execdir git …`. Für ein git-Token hinter einem unbekannten Kommando gilt der Kontext „ohne Präfix-Zuweisungen“ im cwd — der Alias wird im falschen Repo gesucht.
  Spec requirement: Abschnitt 4 („Kopf-Kontext und Wrapper“), AC-3, Expected Behavior „Kontext“.
  Conflict: Alias nur in B, cwd A: Exit 0, Commit in B.
  Reproduction: `/usr/bin/env -C B git ci -m x` → Exit 0; `find B -name f.txt -execdir git ci -m x \;` → Exit 0; Kontrolle `env -C B git ci -m x` → Exit 2.
  Remediation: Wrapper-Erkennung über den Basenamen (`env`, `sudo`, `doas`, `su` …); für jedes git-Token hinter einem NICHT als harmlos bekannten Kommando (`timeout`, `nice`, `nohup`, `time`, `xargs` ohne `-a` …) den Kontext als unbekannt werten.

Finding:
  ID: F010
  Severity: MEDIUM
  Category: edge_case
  Code reference: core/hooks/bash_gate.py:507
  Code reference: core/hooks/bash_gate.py:703
  Description: `_commit_form` liest Rümpfe nur über `_git_segments(t) or []`. Ein nicht zerlegbarer Rumpf ist für `committing` sichtbar (Fall 3 in `is_git_subcommand`), für die Commit-Form aber unsichtbar. Steht im Befehl zusätzlich IRGENDEIN zerlegbarer Commit, ist `commits` nicht leer und die Unsicherheitsregel („größte Menge“) greift nicht — die #259-Menge wird unterzählt.
  Spec requirement: Abschnitt 9 („Unsicherheit — view.unresolved oder kein zerlegbarer Commit — ergibt (True, True, True, True)“), Abschnitt 8 (Fall 3 für Rümpfe).
  Conflict: Der `-a`-Commit des Rumpfs wird gegen die Index-Form des wörtlichen Commits gemessen; uncitierte Arbeitsbaum-Änderungen passieren.
  Reproduction: Phase 7, VERIFIED, Dialog zitiert nur src/b.py, src/c.py getrackt geändert. Alias `sh1` mit Rumpf `git commit -a -m $'it\'s'`: `git sh1` → Exit 2, `git sh1 && git commit -m y` → Exit 0; mit zerlegbarem Rumpf (`!git commit -a -m x`) → Exit 2.
  Remediation: Für jeden Text mit `is_git_subcommand(t, "commit")` aber `_git_segments(t) is None` → (True, True, True, True).

Finding:
  ID: F011
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/git_alias.py:171
  Description: Der Backtick-Trenner direkt hinter `git` gilt nur, wenn `git` am Segmentkopf steht (`_head(seg) == gi`). Hinter Wrappern und Kontrollwörtern (`timeout 5 git …`, `exec git …`, `xargs git …`, `if git …; then`) bleibt ein per Backtick erzeugter Unterbefehl unerkannt, während die `$(…)`- und `$CMD`-Formen an denselben Stellen als unresolved geprüft werden.
  Spec requirement: Expected Behavior „Unterbefehl: … dessen Name erst zur Laufzeit feststeht … wird ohne Abfrage als unresolved geprüft“, Abschnitt 2.
  Conflict: Inkonsistente Erkennung derselben Klasse; der wörtliche `git `echo commit`` ist im alten Gate ebenfalls unerkannt (Parität), der Spec-Anspruch geht aber weiter.
  Reproduction: `timeout 5 git -c user.name=T -c user.email=t@t <Backtick-Substitution um echo ci> -m x` (genauer Befehl in `adversary-repro-round1.txt`, F011) → Exit 0, bash committet; ohne `timeout 5` → Exit 2. Ebenso `if git … <Backtick-Substitution> -m x; then :; fi`.
  Remediation: Backtick-Regel positionsunabhängig anwenden.

Finding:
  ID: F012
  Severity: MEDIUM
  Category: security
  Code reference: core/hooks/git_alias.py:234
  Code reference: core/hooks/git_alias.py:44
  Description: `HOME`, `XDG_CONFIG_HOME`, `GIT_CONFIG_GLOBAL` und `GIT_CONFIG_SYSTEM` stehen auf der Freigabeliste und werden an die Abfrage durchgereicht. trace2-Ziele (`trace2.eventTarget`, `normalTarget`, `perfTarget`) liest git aus der globalen/System-Konfiguration (aus `-c` und `GIT_CONFIG_COUNT` sind sie wirkungslos, geprüft). Legt der Agent eine solche Datei an, schreibt die Abfrage des HOOKS an einen beliebigen Pfad. `GIT_TRACE*` wird gefiltert, dieser Weg nicht.
  Spec requirement: Expected Behavior „Side effects: die Abfrage schreibt nichts“; AC-11 (Zweck: der Hook darf keinen Freigabe-Marker erzeugen); Abschnitt 4 (Begründung der Freigabeliste).
  Conflict: Bewiesen: Der Hook-Prozess legt `.claude/user_approved_validation_x` an, der Befehlstext nennt den Marker nicht.
  Reproduction: `git config --file /tmp/h/.gitconfig trace2.eventTarget <proj>/.claude/user_approved_validation_x` (reiner git-Aufruf), dann `HOME=/tmp/h git st` → Exit 0 und die Datei existiert, erzeugt vom Hook. Ebenso `GIT_CONFIG_GLOBAL=<datei> git st` (Datei muss existieren). Einordnung: KEINE neue Fähigkeit — dieselbe Datei entsteht mit dem ALTEN Gate durch zwei reine git-Aufrufe (`git config --file … trace2.eventTarget …`, `HOME=/tmp/h git status`, beide Exit 0). Die Marker-Fälschung über trace2 ist ein vorbestehendes Loch außerhalb #281; die Spec-Zusicherung stimmt trotzdem nicht.
  Remediation: Zusicherung abschwächen und in die Known Limitations aufnehmen, oder die genannte Konfigurationsquelle auf `trace2.`/`core.fsmonitor` prüfen (dann unresolved); die vorbestehende Marker-Fälschung getrennt melden.

Finding:
  ID: F013
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/git_alias.py:173
  Description: Ein Nicht-Builtin ohne Alias beendet die Kette ohne unresolved. `help.autocorrect` (inline per `-c` oder in der Konfiguration) macht aus `git comit` den Befehl `git commit`. Kein Alias, aber dieselbe Umgehung; in den Known Limitations nicht genannt.
  Spec requirement: Abschnitt 7 („Endet sie bei einem Namen, der weder Builtin noch Alias ist … ohne unresolved“).
  Conflict: Nur bei gesetztem `help.autocorrect`.
  Reproduction: `git -c help.autocorrect=immediate comit -m x` → Exit 0, bash committet.
  Remediation: in die Known Limitations aufnehmen oder `help.autocorrect` in die Abfrage einbeziehen und Nicht-Builtin-Namen ohne Alias dann als unresolved werten.

Finding:
  ID: F014
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/git_alias.py:255
  Description: Shell-Alias-Rümpfe werden rekursiv (Tiefe ≤ 2) aufgelöst, ohne Obergrenze für die Zahl der Auflösungen und Einträge in `shell_bodies`: `a = !git a; git a; …` (n Aufrufe) kostet n³ Läufe und n³ Textkopien in `scan_cmd` (n = 30: 1,2 s; n = 45: 4,0 s; n = 60: 8,6 s, 56 MB).
  Spec requirement: Brief-Punkt „Robustheit“, Abschnitt 8 (Tiefe ≤ 2).
  Conflict: Absichtlich pathologische Konfiguration kann den Hook über das 300-s-Limit treiben (n ≈ 200).
  Reproduction: `git config alias.a '!git a; git a; … (n×)'`, dann `git a`.
  Remediation: Gesamtbudget für Auflösungen/Rümpfe je Befehl (z. B. 64), danach unresolved.

Finding:
  ID: F015
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/hook_utils.py:80
  Description: `_GIT_OPTS_WITH_VALUE` kennt `--attr-source <tree>` (git ≥ 2.40, Wert als eigenes Token) nicht; ein Umleitungs-Token zwischen `git` und dem Unterbefehl (`git >/dev/null commit`) gilt als Unterbefehl. Beides umgeht schon das ALTE Gate beim WÖRTLICHEN Commit; der Resolver erbt diese Semantik für Aliase.
  Spec requirement: keine (vorbestehend, `hook_utils.py` bewusst unverändert).
  Conflict: Parität zum alten Gate, kein Rückschritt durch #281 — als Follow-up vermerkt.
  Reproduction: `git --attr-source HEAD -c user.name=T -c user.email=t@t commit -m x` und `git >/dev/null -c user.name=T -c user.email=t@t commit -m x` → altes Gate Exit 0, neues Gate Exit 0, bash committet. (Ebenfalls Parität: Here-String `bash <<< 'git commit'`, `echo 'git commit' | sh`, Klammer-Expansion `{git,commit}`, `git-commit` außerhalb eines Alias.)
  Remediation: eigenes Issue: `--attr-source` in `_GIT_OPTS_WITH_VALUE`, Umleitungs-Token beim Unterbefehl überspringen.

Finding:
  ID: F016
  Severity: LOW
  Category: regression
  Code reference: core/hooks/git_alias.py:175
  Description: Die Text-Auflösung tokenisiert Heredoc-Rümpfe mit. Daten in einem gequoteten Heredoc, die `git $VAR` oder `git "$@"` enthalten, gelten als „Unterbefehl mit Shell-Syntax“ und blocken im gesperrten Zustand (Exit 2, Meldung „Ausweg: Unterbefehl ausschreiben“ passt nicht). Alltäglich beim Schreiben von Wrapper-Skripten in Phase 6.
  Spec requirement: Brief-Punkt „Über-Erkennung“; Abschnitt 13 („Preis der Vorsicht“ nimmt Heredoc-Daten nicht ausdrücklich auf).
  Conflict: Alt Exit 0, neu Exit 2; kein Bypass, aber ein falscher Block ohne passenden Ausweg.
  Reproduction: `cat > run.sh` mit gequotetem Heredoc (Begrenzer `'EOF'`) und dem Datenzeilen-Text `exec git "$@"` im gesperrten Zustand → Exit 2 „Unterbefehl nicht auflösbar (Unterbefehl mit Shell-Syntax): git $@“ (altes Gate: Exit 0). Ebenso die Datenzeile `Run git $CMD when done`. Ausgabe: `adversary-repro-round1.txt`, F016.
  Remediation: Bodys von Heredocs mit gequotetem Begrenzer (`<<'EOF'`) bei der Auflösung überspringen (`strip_heredoc_bodies` wie für 3a/3b/4), sofern der Opener kein Interpreter ist.

Finding:
  ID: F017
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/git_alias.py:295
  Code reference: core/hooks/git_alias.py:223
  Description: Grenzen der Erkennung von Config-Änderungen im selben Aufruf, ohne dass ein üblicher Dateiname oder `alias.` im Klartext steht. Taint (a) kennt nur `git config` und `git clone`; `check_source` sieht nur Namen, die als Teilzeichenfolge in einem anderen Token stehen. Belegte Wege: `git init --template=<dir>` mit einer Datei `config` in der Vorlage (Verzeichnis existiert zur Hook-Zeit leer, auch wenn die Vorlage im selben Aufruf entsteht); Glob im Schreibziel (`cp alias.cfg /tmp/g.c* && GIT_CONFIG_GLOBAL=/tmp/g.cfg git ci`); zusammengesetzter Pfad (`printf … >> "$(git rev-parse --git-dir)/config"`, `--git-path config`); Skript ohne Pfadnennung (`python3 - <<EOF … '.git/con'+'fig' …`).
  Spec requirement: Abschnitt 4/5, Known Limitations „Verschleierte Config-Schreibzugriffe im selben Aufruf“ (zusammengesetzte Pfade, Skript ohne Pfadnennung).
  Conflict: Größtenteils dokumentierte Grenze; `git init --template` und Glob-Ziele sind nicht ausdrücklich genannt, `$(git rev-parse --git-dir)/config` ist ein naheliegender, nicht böswillig aussehender Weg.
  Reproduction: alle genannten Formen → Exit 0, bash committet; wörtlich `>> .git/config` → Exit 2.
  Remediation: `git init`/`git clone` mit `--template` sowie `git rev-parse --git-dir|--git-path|--git-common-dir` im selben Befehl als Taint werten; Known Limitations um Glob-Ziele und Template-Konfiguration ergänzen.

#### Nachweise ohne Fund (Runde 1, mit Belegen)

- Builtins lösen keine Abfrage aus (Heißer-Pfad-Messung über alle git-Prozesse, 20 Aufrufformen); `git st` genau eine; Budget: vierter Kontext unresolved, ≤ 3 Abfragen, ≤ 6,1 s unter hängendem git.
- Schatten-Regel und Groß-/Kleinschreibung (`git CI`, `git STATUS`) stimmen mit echtem git 2.43 überein (E2E).
- Alias-Quellen a–h (global, `include.path`, `-c`, `GIT_CONFIG_COUNT`, `--config-env` mit Präfix, `env GIT_CONFIG_GLOBAL`, `GIT_CONFIG` ignoriert, letzter Wert gewinnt), Ketten, Optionen im Alias-Wert, Schleife, Obergrenze: E2E gegen echtes git bestätigt.
- #259-Commit-Menge über Alias (`-a`, Pfadangabe, `--amend`, `--all`, `-am`, `add`/`stage`-Alias, Rumpf mit `add -A`, Inline-`-c alias.zz`): in Phase 7 dieselben Ergebnisse wie die wörtlichen Formen (siehe F010 für die einzige Ausnahme).
- Override-Token hebt den Alias-Block auf; Stop-Lock blockt vor der Abfrage; Worktree-Sitzung (cwd im Worktree, Alias in der gemeinsamen Konfiguration) wird erkannt.
- Marker über Shell-Alias (`!touch …user_approved…`) wird von 3a geblockt, Datei entsteht nicht; harmloser Shell-Alias Exit 0.
- Abfrage-Härtung wie spezifiziert: `GIT_TRACE*`/`GIT_CONFIG` nie im Runner-Env, `argv[0]` immer `git`, `./git` wird nicht ausgeführt. Keine Code-Ausführung durch die Abfrage in 14 Varianten (`-c core.pager`, `pager.config`, `-p`, `core.fsmonitor`, `core.hooksPath`, `core.sshCommand`, `credential.helper`, `alias.config`, Präfixe `GIT_PAGER`, `GIT_EXTERNAL_DIFF`, `GIT_EXEC_PATH`, `PATH`, `--exec-path=`, `--git-dir=` auf ein präpariertes Bare-Repo; ausführbares `./git` im cwd): kein Sentinel entstanden. Einzige Nebenwirkung: F012 (trace2-Ziel).
- Absturzsicherheit: kein Traceback in Fuzz und Fehlerinjektion; ASCII-Locale unkritisch (stderr nutzt `backslashreplace`).
- Dokumentation: WORKFLOW_GUIDE, CLAUDE.md, README, CHANGELOG stimmen mit dem Verhalten überein; `setup.py` verteilt `git_alias.py` per Glob.
- Bewusst nicht als Finding gewertet (Known Limitations bzw. Parität zum alten Gate): `bash -lc` (#298), Whitelist-Gefälle #296, `source`, Tiefe > 2, bedingtes `cd`, Unterbefehl aus stdin, `env -S`, Variablen als Befehl (`$G commit`), Here-String/Pipe in `sh`.

#### Offene Punkte für Runde 2

1. **Rückmeldung zu F001–F010** (Fix oder begründete Ablehnung). Jeder Fix wird gegen die echte bash erneut geprüft; die Tests enthalten heute keinen Fall für quote-gesplittetes `git`, `eval`/`builtin`/`command`/Präfix vor `cd`, Schleife/Funktion/`trap`/Substitution, `--config-env` mit `export`, `git-commit` im Rumpf, unzerlegbaren Befehl mit verklebtem `git`, Backslash in Anführungszeichen im Alias-Wert.
2. **F008 — Annahme prüfen:** Claude Code behandelt einen abgebrochenen Hook (Timeout) nicht als Block. Bitte bestätigen oder widerlegen; nach einem Fix muss der 50 000-Token-Fall deutlich unter 3 s liegen.
3. **F012 — Einordnung:** neu (Hook schreibt) oder vorbestehend (Marker-Fälschung per trace2 mit reinen git-Aufrufen)? Entscheidung, ob Known Limitation plus eigenes Issue.
4. **Ungeprüfte Config-Erzeuger** für Taint (a): `git submodule add`, `git remote`, `git config --edit` mit `GIT_EDITOR`, `git clone --template`, `git worktree`; ungeprüfte Wrapper: `doas`, `su`, `runuser`, `chroot`, `nsenter`, `sudo -D`, `CDPATH` (vermutlich Klasse F009/F002).
5. **Über-Erkennung in Phase 7:** `unresolved` + VERIFIED ergibt die größte Commit-Menge — Auswirkung auf legitime Befehle (`git -C "$D" st` bei untracktem Scratch-Datei-Bestand) nur stichprobenartig geprüft.
6. **Checkliste:** In Runde 2 bekommt jeder der 27 Punkte ein Finding oder eine Confirmation mit `Code reference:`; die Tabelle „Vorläufiger Stand“ oben ist nicht bindend.

## Runde 2

### Runde 2

**Adversary:** Ich habe der Rückmeldung des Fixers nichts geglaubt. Jede Reproduktion aus Runde 1 lief erneut gegen den neuen Stand, mit der echten bash und echtem git 2.43 in hermetischen Wegwerf-Repos (Hook-Exit gegen tatsächlich entstandene Commits; ALT = HEAD, per `git archive` entpackt). Danach habe ich die neuen Mechanismen angegriffen: Stellungsregel (Kopf / A / B / C), Plausibilitätsfilter der Erwähnung, reihenfolgeunabhängiger Taint, cd-Modell, Arbeitsgrenze 64 / 64 KiB und naive Zerlegung. Über-Erkennung und Laufzeit sind gemessen, die Robustheit erneut gefuzzt. Bypass heißt hier wie im Auftrag: das wörtliche `commit` blockt, die Alias-Form geht mit Exit 0 durch, die echte bash committet, und es ist keine Known Limitation oder dokumentierte Rest-Grenze. Alle Ausgaben stehen in `docs/artifacts/fix-281-git-alias-commit-gate/adversary-repro-round2.txt` (Abschnitte A bis I). In den Reproduktionen steht `G` für `-c user.name=T -c user.email=t@t`. Am Repo, an Code, Tests, Spec und Doku wurde nichts geändert; Remediation-Prototypen liefen in Scratch-Kopien.

**Kurzfassung:**
- Behoben und gegen die echte bash bestätigt: F001–F004, F006, F008, F010–F014. Teilweise behoben: F005, F007, F009, F017 (die Reste sind F018–F023). Bewusst nicht behoben: F015, F016.
- Neue, reproduzierbare Bypässe in den Fixes und den neuen Mechanismen: F018 (HIGH), F019 und F020 (MEDIUM), F021–F023 (LOW). Ursache von F019–F021 ist dieselbe wie bei F001: Roh-Text-Prüfungen statt Lexer-Tokens, die Quoting nicht überlebt. F018 ist eine zu enge Befehlsposition (Starter mit Optionswert oder Operand, führende Umleitung) und ein Plausibilitätsmuster, das gültige Alias-Namen nicht kennt.
- Über-Erkennung: F024 (MEDIUM). Auf realen Korpora selten (siehe Messwerte), aber ohne passenden Ausweg.
- Der Wortlaut aller 17 ACs gilt: 38 von 38 eigene wortgetreue Prüfungen, 238 Tests der Datei, volle Suite 1797 grün.

#### Testläufe Runde 2 (selbst ausgeführt)

| Lauf | Ergebnis |
|------|----------|
| `python3 -m pytest tests/test_git_alias_commit_gate_281.py -q` | 238 passed (Runde 1: 151) |
| `python3 -m pytest tests/ -q` (gespeichert, überschrieben: `docs/artifacts/fix-281-git-alias-commit-gate/adversary-test-output.txt`) | 1797 passed, 28 skipped, Exit 0 |
| Eigene wortgetreue AC-Prüfung gegen echtes git und echte bash (`acverify.py`, 38 Fälle: AC-1, AC-2a–h, AC-3 ×4, AC-4 ×2, AC-5a–c, AC-6 ×3, AC-7a–d, AC-8 ×3, AC-9 ×2, AC-10 ×2, AC-11 bis AC-15, AC-16/17) | 38/38 bestanden |
| Invarianz-Differential: 450 zufällige Befehlsketten (Builtin-git bzw. ohne git; Trenner, Wrapper, Heredocs, Marker- und Protected-Pfade), gesperrt und ohne Workflow, ALT gegen NEU | 900 Läufe, 0 Abweichungen im Exit-Code |
| Heißer Pfad: git-Wrapper zählt jeden git-Prozess (20 Aufrufformen) | Builtins 0 Prozesse (alt = neu); `git st` und `git submodule status` je 1 Abfrage; `git commit` 1 Prozess wie alt |
| Differentielles Fuzzing gegen die echte bash, Modi wrap / ctx / taint, je 300 Fälle, Seeds 2–5 | 3 600 Läufe, 0 Bypässe (die Grammatik nutzt nur plausible Alias-Namen und deckt F018–F023 deshalb nicht ab) |
| Robustheit: Resolver-Fuzz 2 × 60 000 zufällige Token-Folgen (u. a. `--tem`, `firejail`, `$'`, Heredoc-Marker, `CDPATH=`), Hook-Fuzz 2 × 600 echte Hook-Prozesse | 0 interne Fehler, 0 entwichene Ausnahmen; Exit nur 0 oder 2, kein Traceback |
| Abfrage führt keinen fremden Code aus (14 Varianten: `core.pager`, `pager.config`, `-p`, `core.fsmonitor`, `core.hooksPath`, `core.sshCommand`, `credential.helper`, `GIT_PAGER`, `GIT_EXTERNAL_DIFF`, `GIT_EXEC_PATH`, `PATH`, `--exec-path=`, `alias.config`, `--git-dir=` auf ein präpariertes Bare-Repo; ausführbares `./git`) | kein Sentinel entstanden |
| Über-Erkennung: Korpus 1 572 echte Bash-Befehle (743 mit „git“), ALT / Runde-1-Code / NEU, gesperrter Zustand, ohne Ausführung | alt blockt und neu nicht: 0; neu blockt zusätzlich 55 (3,5 %; Runde-1-Code: 23) — Details unter Messwerte |
| Laufzeit auf demselben Korpus | Median 0,090 s neu gegen 0,086 s alt; p95 0,146 / 0,132 s; Maximum 0,24 / 0,28 s |

#### Ergebnis je Fund aus Runde 1 (F001–F017), jeweils erneut gegen die echte bash

| Fund | Schwere R1 | Ergebnis R2 | Beleg |
|------|------------|-------------|-------|
| F001 | CRITICAL | behoben | 13 Formen (`g""it`, `"g""it"`, `gi''t`, `g\it`, `gi\<Zeilenumbruch>t`; verschachtelt in `bash -c`, Heredoc, `(…)`, `$(…)`, `timeout 5`; Alias-Name gesplittet `c""i`, `'ci'`, `c\i`) alle Exit 2 (alt 0), Kontrolle wörtlich `g""it … commit` Exit 2 (Abschnitt B). Vorprüfung jetzt auf normalisiertem Text: `bash_gate.py:631`, `git_alias.py:389`. |
| F002 | HIGH | behoben | `eval "cd B"`, `builtin cd B`, `command cd B`, `X=1 cd B`, `time cd B`, Schleife mit `cd` → Exit 2 (alt 0); Fuzz ctx 0 Bypässe (`git_alias.py:205–208`). Rest: `CDPATH` mit gesplittetem Namen → F021. |
| F003 | HIGH | behoben | Alias-Wert `"com\mit"` → Exit 2 (`git_alias.py:327`, Backslash → unresolved). |
| F004 | HIGH | behoben | alle sechs Reihenfolge-Formen (`$(…)` im Argument, in `-m "…"`, in Präfix-Zuweisung, Schleife, Funktion, `trap`) → Exit 2; Fuzz taint 0 Bypässe (`git_alias.py:395–396`). Preis: `git st; git config alias.x y` wird geprüft. Rest: Indirektion → F023. |
| F005 | MEDIUM | teilweise behoben | `export TERM=commit; git --config-env=alias.ci=TERM ci` → Exit 2; mit gesplittetem Variablennamen (`export TE""RM=commit`) oder Indirektion weiter Exit 0 → F020, F023. |
| F006 | MEDIUM | behoben | `;git`, `&&git`, `\|git`, `(git`, `status;git` → Exit 2; 18 weitere Formen der naiven Zerlegung (Quoting im Alias-Namen, Pfadform, Brace, Subshell, Tab, Zeilenfortsetzung, `-C`, `GIT_DIR=`, `cd B`, `env -C B`) alle Exit 2 (Abschnitt C4). |
| F007 | MEDIUM | teilweise behoben | `!git-commit`, `!exec git-commit`, `!env git-commit`, `!command git-commit`, `!f() { git-commit "$@"; }; f`, `!$(git --exec-path)/git-commit` → Exit 2; Quoting-Formen und `sh -c '…git-commit "$@"'` → Exit 0 → F019. |
| F008 | HIGH | behoben | 50 000 `git`-Token + wörtlicher Commit: 1,87 s (Runde 1: 368 s; alt 1,49 s); Arbeitsgrenze 64 (`git_alias.py:241–246`). Weitere pathologische Eingaben unter Messwerte. |
| F009 | MEDIUM | teilweise behoben | `/usr/bin/env -C B git`, `env --chdir=B`, `find -execdir`, `sudo -D B`, `sudo -u`, `runuser -u`, `chroot`, `nsenter --wd=`, `unshare --wd=` → Exit 2. Offen: Starter mit Argument oder Umleitung vor `git` fallen aus der Befehlsposition → F018; unbekannte Verzeichniswechsler (`nsenter -w<dir>`) = dokumentierte Rest-Grenze. |
| F010 | MEDIUM | behoben | Phase 7, VERIFIED: `git sh1 && git commit -m y` (Rumpf mit `$'…'`) jetzt Exit 2 (vorher 0) (`bash_gate.py:505`). |
| F011 | LOW | behoben | Backtick-Unterbefehl hinter `timeout 5`, in `if …; then` und am Kopf → Exit 2 (`git_alias.py:228`, `:232`). |
| F012 | MEDIUM | behoben (Hook schreibt nicht mehr) | trace2-Ziel in `HOME`-/`GIT_CONFIG_GLOBAL`-Konfiguration: Marker vom Hook nicht angelegt (`git_alias.py:67`, `:300`). Die Marker-Fälschung per trace2 mit reinen git-Aufrufen bleibt vorbestehend (alt 0, neu 0), nicht Teil von #281, bei #297 vermerkt. |
| F013 | LOW | behoben | `git -c help.autocorrect=immediate comit -m x` → Exit 2 (`git_alias.py:342–344`). Hinter unbekanntem Wrapper weiter Exit 0 → F018. |
| F014 | LOW | behoben | `a = !git a; git a; …` n = 15/30/45: Exit 2 in 0,1 s (Budget). |
| F015 | LOW | nicht behoben, bewusst | unverändert Parität alt = neu = Exit 0 (`--attr-source`, Umleitung hinter `git`); eigenes Issue #304. Kein Rückschritt durch #281. |
| F016 | LOW | nicht behoben, bewusst | Heredoc-Daten mit `exec git "$@"` blocken weiter (Exit 2); die Folgen sind größer als in Runde 1 gedacht → F024. |
| F017 | LOW | teilweise behoben | `init --template`, `clone --template`, `config -e`, `config --edit`, `config --worktree`, `config --file .git/config` → Exit 2; Abkürzungen `--tem`, `--te`, `config --ed` → Exit 0 (F022). Glob-Ziel, `$(git rev-parse --git-dir)/config` und Skript ohne Pfadnennung bleiben Exit 0 — dokumentierte Grenze „verschleierte Config-Schreibzugriffe“ (zusammengesetzte Pfade, Skript). |

Verschlechtert ist kein Bypass-Fund aus Runde 1. Verschlechtert hat sich nur die Über-Erkennung (Runde-1-Code: 23 Zusatzblöcke auf dem Korpus, jetzt 55), siehe F024.

#### Neue Funde (Runde 2)

Finding:
  ID: F018
  Severity: HIGH
  Category: spec_violation
  Code reference: core/hooks/git_alias.py:156
  Code reference: core/hooks/git_alias.py:230
  Code reference: core/hooks/git_alias.py:62
  Code reference: CHANGELOG.md:112
  Description: Die Stellungsregel hat zwei Lücken. (a) `_stellungen` hält ein git-Token nur dann in Befehlsposition (B), wenn davor ausschließlich Starter-Wörter, Optionen (`-…`), Zuweisungen oder Zahlen und Dauern stehen (Zeilen 156–157). Jedes andere Argument eines bekannten Starters kippt alles dahinter auf „Erwähnung“ (C): der Optionswert in `timeout -s KILL 5`, der Operand in `flock /tmp/lockx`, der Wert in `stdbuf -o L`, das Vorzeichen in `nice -n +5` (`_ARG` kennt kein `+`). Dasselbe gilt für einen führenden Umleitungsoperator (`>/dev/null git …`, `2>/dev/null git …`): der Lexer liefert `>` und das Ziel als eigene Tokens, `_head` hält `>` für das Befehlswort. (b) Für C zählt nur ein Name, der auf `[A-Za-z][A-Za-z0-9-]*` passt (Zeilen 62, 230). Laufzeitnamen (`$CMD`, `$(echo ci)`) fallen damit heraus — und auch der gültige Alias-Name mit Punkt: `git config alias.a.b commit` legt `[alias "a"] b = commit` an, `git a.b` führt `commit` aus. Am Kopf und direkt hinter `timeout 5` blockt derselbe Aufruf (Stellung Kopf bzw. B), hinter den genannten Wrappern geht er mit Exit 0 durch. Die `help.autocorrect`-Prüfung (Zeile 342, `k[0] != "C"`) ist hinter einem unbekannten Wrapper ebenso blind.
  Spec requirement: Expected Behavior „Unterbefehl“ (ein erst zur Laufzeit feststehender Unterbefehl wird als unresolved geprüft, auch hinter Wrappern), „Alias auf commit gilt wie commit“, Abschnitt 4 („Kopf-Kontext und Wrapper“); Zusage im CHANGELOG (Zeile 112): „in Befehlsposition hinter xargs, timeout & Co. wird normal aufgelöst“.
  Conflict: Das wörtliche `commit` blockt in jeder dieser Stellungen (alt und neu Exit 2), der Alias- bzw. Laufzeit-Aufruf nicht. Die dokumentierte Rest-Grenze nennt nur unbekannte Starter, die selbst Verzeichnis oder Benutzer wechseln; `timeout`, `flock`, `stdbuf`, `nice` und Umleitungen sind weder unbekannt noch wechseln sie das Verzeichnis. Die Regel verfehlt außerdem ihre eigene Dokumentation.
  Reproduction (gesperrter Zustand; jeweils Exit 0 und die echte bash committet; Abschnitt C):
    Alias `a.b` (lokal `[alias "a"]` mit `b = commit`): `timeout -s KILL 5 git G a.b -m x`, `flock /tmp/lockx git G a.b -m x`, `>/dev/null git G a.b -m x`, `2>/dev/null git G a.b -m x`, `mywrap git G a.b -m x`.
    Alias `ci=commit`, Name erst zur Laufzeit: `export CMD=ci; timeout -s KILL 5 git G $CMD -m x`, `timeout -s KILL 5 git G $(echo ci) -m x`, `stdbuf -o L git G $(echo ci) -m x`, `nice -n +5 git G $(echo ci) -m x`, `>/dev/null git G $(echo ci) -m x`.
    Autocorrect: `mywrap git G -c help.autocorrect=immediate comit -m x`.
    Kontrollen: `git G a.b -m x` → Exit 2; `timeout 5 git G a.b -m x` → Exit 2; `timeout -s KILL 5 git G ci -m x` → Exit 2 (plausibler Name); der wörtliche `… git G commit -m x` hinter jedem der Wrapper → Exit 2 (alt wie neu, Abschnitt C2).
  Remediation: Starter-Argumente überspringen — Tabelle Starter → wertnehmende Optionen und Operanden (`timeout -s/-k` plus Dauer, `flock` Sperrdatei, `stdbuf -i/-o/-e`, `nice -n`, `ionice -c/-n`, `xargs -I/-n/-P/-a …`), `_ARG` mit Vorzeichen, Umleitungsoperator samt Ziel (auch `2` davor) in `_head` und `_stellungen` überspringen; `_PLAUSIBLE` um `.` erweitern. Im Scratch geprüft (Repo unberührt): Umleitungen überspringen plus Operanden-Tabelle schließt alle genannten Formen, alle 238 Tests der Datei bleiben grün, die Erwähnungs-Kontrollen `echo git $X`, `grep -rn git $PATTERN docs/`, `strace git $X` bleiben frei (Abschnitt I). Ein bloßes Verlängern der Befehlsposition (jedes Argument nach einem Starter bleibt B) bricht vier `adv-fp-*`-Wächter (`find-exec`, `find-execdir`, `timeout-glob`, `xargs-I`) und ist keine Lösung. Hinter UNBEKANNTEN Wrappern (`mywrap git $(echo ci)`) bleibt die Erwähnungsregel wie dokumentiert; ob das tragbar ist, entscheidet der Tech Lead (der CHANGELOG nennt als Rest-Grenze nur Verzeichnis- und Benutzerwechsler). Tests für diese Klassen fehlen heute.

Finding:
  ID: F019
  Severity: MEDIUM
  Category: spec_violation
  Code reference: core/hooks/git_alias.py:54
  Code reference: core/hooks/git_alias.py:320
  Description: Der Fix für F007 normalisiert `git-<builtin>` im Shell-Alias-Rumpf per Regex `_DASHED` über den ROHEN Text des Alias-Werts (Zeile 320). Quoting verhindert den Treffer: `git\-commit`, `git-com""mit`, `g\it-commit`, `'git'-commit`, `git-'commit'` sind für bash dasselbe Wort `git-commit`. Außerdem erkennt die Regex ein gequotetes Wort nur, wenn das Schlusszeichen unmittelbar auf den Namen folgt. Dadurch gehen auch natürliche Schreibweisen ohne Verschleierungsabsicht durch: `sh -c 'git-commit "$@"' --`, `bash -c '…'`, `sh -c "git-commit …"` und `"$(git --exec-path)/git-commit" "$@"`. bash führt `git-commit` aus dem exec-path aus; `is_git_subcommand` kennt nur das Token `git`.
  Spec requirement: Expected Behavior „Shell-Aliase: sein Rumpf wird auf Commit, Marker-Schreiben und Secrets geprüft“, Abschnitt 8; der Fix zu F007 behauptet genau diese Abdeckung.
  Conflict: Derselbe Alias-Weg, der in der einfachen Schreibweise blockt (`!git-commit` Exit 2), geht in diesen Formen mit Exit 0 durch, die echte bash committet.
  Reproduction (Shell-Alias `dc`, gesetzt mit `git config alias.dc '<Wert>'`, dann `git G dc --allow-empty -m x`; alle Exit 0 und Commit; Abschnitte C und C7):
    `!git\-commit`, `!git-com""mit`, `!g\it-commit`, `!'git'-commit`, `!git-'commit'`
    `!sh -c 'git-commit "$@"' --`, `!bash -c 'git-commit "$@"' --`, `!sh -c "git-commit \"\$@\"" --`, `!"$(git --exec-path)/git-commit" "$@"`
    Kontrollen → Exit 2: `!git-commit`, `!exec git-commit`, `!env git-commit`, `!command git-commit`, `!f() { git-commit "$@"; }; f`, `!$(git --exec-path)/git-commit`.
  Remediation: die gestrichelte Form lexer-basiert erkennen (Tokens des Rumpfs und der verschachtelten Shell-Texte, wie `_all_tokens` sie liefert) statt per Regex über den Roh-Text; ein Token `git-<builtin>` oder `…/git-<builtin>` ergibt eine synthetische Zeile `git <builtin>`. Im Scratch geprüft: schließt alle zehn Formen, die 238 Tests bleiben grün, `!ls git-hooks` bleibt frei (Abschnitt I). Test für Quoting und verschachtelte Shell-Texte ergänzen.

Finding:
  ID: F020
  Severity: MEDIUM
  Category: spec_violation
  Code reference: core/hooks/git_alias.py:264
  Code reference: core/hooks/git_alias.py:265
  Description: Der Fix für F005 zählt, wie oft der Variablenname aus `--config-env=K=VAR` im ROHEN Befehlstext vorkommt (Regex über `self.command`, Zeilen 264–265); mehr als ein Vorkommen macht den Aufruf unresolved. Quoting im Namen der Zuweisung (`TE""RM`, `TE\RM`) entzieht ihn dem Zähler, bash setzt die Variable trotzdem. Der Resolver rechnet dann mit dem Hook-Wert (`xterm`), git mit `commit`. Gleiches gilt für `declare -x "TE""RM"=commit` und `eval "export TE""RM=commit"`.
  Spec requirement: Abschnitt 4 (Wert aus Präfix-Zuweisung desselben Segments oder aus der Hook-Umgebung), Abschnitt 5 (c), Expected Behavior „Kontext“ und „Alias auf commit (… `--config-env`, Umgebung)“.
  Conflict: Der Fix schließt die Klartext-Form, die Quoting-Form läuft durch. Dieselbe Klasse wie F001, die der Fixer als Fund akzeptiert hat.
  Reproduction (Hook-Umgebung mit `TERM=xterm`, kein Alias in der Konfiguration; alle Exit 0 und Commit; Abschnitt C):
    `export TE""RM=commit; git G --config-env=alias.ci=TERM ci -m x`
    `export TE\RM=commit; git G --config-env=alias.ci=TERM ci -m x`
    `declare -x "TE""RM"=commit; git G --config-env=alias.ci=TERM ci -m x`
    `eval "export TE""RM=commit"; git G --config-env=alias.ci=TERM ci -m x`
    Kontrolle → Exit 2: `export TERM=commit; git G --config-env=alias.ci=TERM ci -m x`.
  Remediation: Vorkommen auf Lexer-Tokens statt auf Roh-Text zählen, mindestens den Text mit `_UNQUOTE` normalisieren. Im Scratch geprüft: mit `_UNQUOTE` vor dem Zähler blocken alle vier Formen, die 238 Tests bleiben grün (Abschnitt I). Die Indirektion (`export ${PFX}RM=commit`) bleibt davon unberührt → F023.

Finding:
  ID: F021
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/git_alias.py:358
  Description: Der Fix für F002 prüft `CDPATH` als Teilzeichenfolge des ROHEN Befehlstexts (`"CDPATH" in self.command`, Zeile 358). Mit gesplittetem Namen (`CD""PATH`) landet ein relatives `cd` per `CDPATH` in einem anderen Verzeichnis, das Modell setzt `-C dec` relativ zum cwd und fragt das falsche Repo.
  Spec requirement: AC-3 und Expected Behavior „Kontext“ (die Abfrage läuft dort, wo der Aufruf läuft); Abschnitt 6 („relatives `cd` bei `CDPATH` unbekannt“, Abweichung 2 laut Fixer).
  Conflict: Alias nur im CDPATH-Repo, cwd-Repo ohne Alias: Exit 0, der Commit entsteht im CDPATH-Repo.
  Reproduction: `export CD""PATH=<dir>; cd dec && git G ci -m x` mit `<dir>/dec` als Repo mit `ci=commit` und einem Repo `dec` ohne Alias im cwd → Exit 0, Commit im CDPATH-Repo. Kontrolle → Exit 2: `export CDPATH=<dir>; cd dec && git G ci -m x`.
  Remediation: `_UNQUOTE`-normalisierten Text prüfen (im Scratch geprüft, Abschnitt I). Aufwand des Angriffs: ein präpariertes Repo plus Quoting — deshalb LOW.

Finding:
  ID: F022
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/git_alias.py:370
  Code reference: core/hooks/git_alias.py:371
  Description: Taint (a) erkennt `config -e|--edit` und `--template` nur in der vollen Schreibweise (`{"-e", "--edit"} & set(low)`, `t.startswith("--template")`). git akzeptiert eindeutige Optionspräfixe: `--tem`, `--te` bei `git init` und `git clone`, `--ed` bei `git config`. Eine Vorlage mit `config`-Datei bzw. ein per `GIT_EDITOR` bearbeitetes `git config --ed` legt den Alias im selben Aufruf an, ohne dass ein Taint entsteht.
  Spec requirement: Abschnitt 5 (Taint (a)), Expected Behavior „Kontext“ („Alias-Änderung im selben Befehl“); Runde-1-Fund F017, dessen Fix hier lückenhaft bleibt.
  Conflict: Volle Schreibweise blockt, die Abkürzung nicht; kein Eintrag in den Known Limitations.
  Reproduction (Vorlage mit `[alias] ci = commit` in `config`, leeres Zielverzeichnis; Abschnitt C): `git init -q --tem=<tpl> <C> && cd <C> && git G ci --allow-empty -m x` und `--te=` → Exit 0, Commit in C; `GIT_EDITOR=<ed.sh> git config --ed && git G ci -m x` → Exit 0, Commit. Kontrollen → Exit 2: `--template=`, `config -e`, `config --edit`.
  Remediation: Optionspräfix wie `bash_gate._commit_form` es für `--amend` schon tut (`"--amend".startswith(tok)`): `"--template".startswith(opt)` und `"--edit".startswith(opt)` bei Länge ≥ 3. Im Scratch geprüft: schließt die drei Formen, `git init --bare` bleibt frei, 238 Tests grün (Abschnitt I).

Finding:
  ID: F023
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/git_alias.py:364
  Code reference: core/hooks/git_alias.py:374
  Description: Taint (a) und (c) erkennen Config-Änderungen an der buchstäblichen Schreibweise: `alias.` im Token (Zeile 369) und der Name der Freigabeliste als Token vor `=` (Zeile 381). Steht der Schlüssel oder der Variablenname erst nach der Shell-Expansion fest, fehlt jeder Taint: `K=alias.ci; git config $K commit && git ci`, `PFX=GIT_CONFIG_GL; export ${PFX}OBAL=<datei mit ci=commit>; git ci`, `PFX=TE; export ${PFX}RM=commit; git --config-env=alias.ci=TERM ci`. Benachbart zur dokumentierten Grenze „zusammengesetzte Pfade (`$d/$f`)“, aber Schlüssel (`$K`) und Variablennamen (`${PFX}…`) sind dort nicht genannt.
  Spec requirement: Abschnitt 5, Known Limitations „Verschleierte Config-Schreibzugriffe im selben Aufruf“.
  Conflict: Teilweise dokumentiert; offen ist, ob die Grenze auch diese Formen umfasst. Das wörtliche `git config alias.ci commit && git ci` blockt (AC-7 a).
  Reproduction (Abschnitte C und C3; Exit 0 und Commit): `K=alias.ci; git config $K commit && git G ci -m x`; `PFX=GIT_CONFIG_GL; export ${PFX}OBAL=<datei> ; git G ci -m x`; `PFX=TE; export ${PFX}RM=commit; git G --config-env=alias.ci=TERM ci -m x` (Hook-Umgebung mit `TERM=xterm`).
  Remediation: entweder in die Known Limitations aufnehmen („Schlüssel oder Variablenname aus einer Variable“) oder `git config` mit Shell-Syntax in der Schlüsselposition und `export`/`declare`/`typeset`/`readonly` mit `$` im Namen als Taint werten. Entscheidung beim Tech Lead.

Finding:
  ID: F024
  Severity: MEDIUM
  Category: regression
  Code reference: core/hooks/git_alias.py:166
  Code reference: core/hooks/git_alias.py:205
  Code reference: core/hooks/git_alias.py:230
  Code reference: core/hooks/bash_gate.py:683
  Description: Über-Erkennung durch die Erwähnungsregel, die naive Zerlegung und das cd-Modell. Der Resolver bekommt den vollen Befehl samt Heredoc-Bodies (`bash_gate.py:683`; für die Muster-Scans nimmt `main()` dagegen `strip_heredoc_bodies`, Zeile 670). Prosa in einem Heredoc mit einem Apostroph macht den Gesamtbefehl für `shlex` unzerlegbar; die naive Zerlegung findet dann „git <Wort>“ im Text und prüft das Wort als Unterbefehl (`Befehl nicht zerlegbar`). Ohne Apostroph genügt `git $CMD` oder `git "$@"` im Text (Shell-Syntax) bzw. ein offenes Verzeichnis. Im einfachen Fall `echo git <wort>` blockt ein ungequoteter Text, sobald das Verzeichnis offen ist oder ein Taint besteht. Die Folge in Phase 7 (VERIFIED): ein WÖRTLICHER Commit wird zur größten #259-Menge hochgestuft und blockt, sobald nicht alle Arbeitsbaum-Dateien zitiert sind.
  Spec requirement: Auftrag Runde 2 („Über-Erkennung alltäglicher Befehle wäre ein Fund“); Expected Behavior „Fehlerrichtung“ („Wirkung nur dort, wo auch ein wörtlicher Commit geprüft würde“ — das gilt, der Preis ist aber ein Falschblock ohne passenden Ausweg).
  Conflict: Der Ausweg „Unterbefehl ausschreiben“ passt nicht, der Nutzer muss den Text umformulieren. Fund aus Runde 1 (F016) bewusst nicht behoben; die Regeln aus Runde 2 vergrößern die Wirkung.
  Reproduction (alt Exit 0, neu Exit 2; Abschnitt C):
    Phase 7, VERIFIED, Dialog zitiert nur `src/b.py`, `src/c.py` getrackt geändert: `cd <proj> && git commit -m "$(cat <<'EOF'` mit Nachricht `fix: tidy up the git hooks` (Heredoc, Standardform), und ohne `cd` mit `fix: don't resolve git aliases twice`. Kontrolle: Nachricht `fix: tidy up the module` mit `cd` → Exit 0.
    Phase 6: `gh pr create --title t --body "$(cat <<'EOF'` mit `- Fix git alias bypass (it's #281)`; `cat > docs/n.md <<'EOF'` mit `Don't run git hooks manually.`; `echo it's git time`; `cd "$D" && echo git done`; `cat > run.sh <<'EOF'` mit `exec git "$@"` (F016).
  Remediation: dem Resolver `strip_heredoc_bodies(command)` übergeben (dieselbe konservative Funktion, die Gate-Schritt 3a/3b/4 benutzen: Heredocs mit Interpreter auf der Öffner-Zeile bleiben sichtbar). Im Scratch geprüft: schließt beide Phase-7-Fälle (Commit-Nachricht mit und ohne `cd`) sowie PR-Text und Doku-Prosa in Phase 6; `bash <<'EOF'`/`sh <<'EOF'` mit `git ci` blocken weiter, `cat <<'EOF'` mit der Prosa `run git ci later` bleibt frei; `cat > run.sh <<'EOF'` (Opener-Zeile enthält `sh`) und `echo it's git time` (unzerlegbar, ohne Heredoc) bleiben Exit 2 (Abschnitt I). Alternativ den Text der Meldung für diese Gründe anpassen („Anführungszeichen/Heredoc prüfen“).

#### Messwerte

**Über-Erkennung** (Korpus `scratchpad/bash_corpus.json`: 1 572 echte Bash-Befehle aus den Transkripten, 743 mit „git“; gesperrter Zustand; ALT = HEAD, Runde-1-Code, NEU; kein Befehl wird ausgeführt):

| Übergang (alt / R1-Code / neu) | Anzahl |
|--------------------------------|--------|
| 0 / 0 / 0 | 1 452 |
| 0 / 0 / 2 (nur der neue Stand blockt) | 34 |
| 0 / 2 / 0 (R1-Code blockte, neu nicht) | 2 |
| 0 / 2 / 2 | 21 |
| 2 / 2 / 2 | 63 |
| 2 / – / 0 (alt blockt, neu nicht) | 0 |

Zusätzlich blocken gegenüber ALT jetzt 55 Befehle (3,5 %; Runde-1-Code: 23). Von diesen 55 enthalten 43 Heredoc und Alias-Text, 7 Alias-Text ohne Heredoc, 5 Heredoc-Skripte mit „git <Wort>“-Prosa ohne Alias-Text; keiner ist ohne Heredoc und ohne Alias- bzw. git-Syntax-Text. Das Korpus stammt aus der Arbeit am Alias-Gate selbst und ist dafür überrepräsentiert. Realistischere Vergleichskorpora: 388 Befehle aus Doku und Tests → 0 Zusatzblöcke; 186 echte Commit- und PR-Nachrichten-Befehle aus der Historie (Heredoc-Standardform) → 2 Zusatzblöcke, beide die Beschreibung von #281 selbst (Text mit `git $CMD` und „git führt“), also rund 1 %, und nur bei Texten, die über git-Syntax sprechen. 128 von mir geschriebene „typische“ Agenten-Befehle (bewusst auf Erwähnungen, Heredoc-Prosa, `cd "$D"` zugeschnitten, also kein Basiswert): 18 Zusatzblöcke, davon 12 Heredoc-Prosa oder -Skripte (Doku, PR- und Issue-Text, Python-Kommentare, `exec git "$@"`) mit „git <Wort>“, 3 ungequotete Texte (`echo it's git time`, `ls ~/.gitconfig; echo git done`, `cd "$D" && echo git done`) und 3 mit `cd` auf ein offenes oder im Testprojekt nicht vorhandenes Verzeichnis (`cd "$D" && git lfs pull`, `cd "$D" && git subtree pull …` — laut AC-3 gewollt; `cd /repo && git submodule status` — Artefakt des Korpus, das Verzeichnis gibt es dort nicht). Ergebnis: alltäglich sind (a) Heredoc-Prosa mit Apostroph und „git <Wort>“ (Doku, PR-Text, Commit-Nachricht) und (b) `cd "$D" && echo git done`; die Häufigkeit in realen Korpora ist niedrig, die Wirkung ein Falschblock ohne passenden Ausweg → F024 (MEDIUM). Für sich allein wäre das kein BROKEN.

**Laufzeit** (Abschnitte G und H der Belegdatei; Hook-Timeout 300 s laut `hooks/hooks.json`):

| Eingabe | neu | alt |
|---------|-----|-----|
| Korpus 1 572 Befehle, Median / p95 / Maximum | 0,090 / 0,146 / 0,24 s | 0,086 / 0,132 / 0,28 s |
| `git commit -m x # ` + 50 000 × `git ` (Runde 1: 368 s) | 1,87 s | 1,49 s |
| 50 000 × `git` ohne Commit (neu Exit 2, Arbeitsgrenze) | 2,54 s | 0,51 s |
| `git st;` × 20 000 (neu Exit 2) | 2,37 s | 0,49 s |
| 200 KB Prosa-Zeilen „git <Wort>“ (neu Exit 2) | 1,88 s | 1,96 s |
| 20 000 verschachtelte `bash -c`, `eval`, `sudo -u x`, `find -exec` | 3,67 / 2,92 / 2,47 / 3,67 s | 3,42 / 2,28 / 2,26 / 3,56 s |
| `a = !git a; git a; …` × 100 | 0,09 s | 0,06 s |
| ein einzelnes Token ohne Leerzeichen, 100 / 200 / 400 KB | 3,2 / 10,6 / 37,0 s | 2,8 / 9,6 / 35,0 s (vorbestehend quadratisch im Lexer) |
| unbalancierte Anführungszeichen, 100 / 200 / 400 KB (naive Zerlegung, neu Exit 2) | 2,6 / 9,2 / 34,7 s | 0,7 / 2,6 / 9,0 s |

Der Fall aus F008 (50 000 Token) liegt deutlich unter 3 s. Die Laufzeit wächst jetzt linear mit der Zahl der git-Token. Beim unbalancierten Anführungszeichen ist der neue Pfad rund 4 × langsamer als der alte, beide sind quadratisch; die 300-s-Schwelle läge bei etwa 1,2 MB (alt: 2,3 MB). Befehle dieser Größe sind unrealistisch — kein Fund, nur ein Hinweis.

#### Beurteilung der acht Abweichungen von der eingefrorenen Spec

Maßstab aus dem Auftrag: Eine Abweichung in die sichere Richtung ist kein BROKEN, solange alle AC-Fälle wörtlich gelten und sie keine alltäglichen Befehle blockt.

| # | Abweichung | Urteil |
|---|------------|--------|
| 1 | §5 Taint wirkt auf ALLE Nicht-Builtins des Befehls | sicher; AC-7 (c) bleibt Exit 0 (acverify AC-7c); Preis nur `git st; git config alias.x y` in Phase 6/7. Kein Fund. |
| 2 | §6 `cd` nur in einfach sequentiellen Befehlen; sonst offen; `CDPATH` | sicher; AC-3 gilt in allen vier Formen. Preis: komplexe Befehle mit `cd` und einer Erwähnung „git <Wort>“ → Teil von F024. Der `CDPATH`-Teil ist umgehbar (F021). |
| 3 | §4 Stellungsregel A/B/C | als „sicher“ gedacht, in der Praxis nicht: Starter mit Argument oder Umleitung fallen aus der Befehlsposition, gültige Alias-Namen mit Punkt fallen aus dem Plausibilitätsmuster (F018); die Erwähnungsregel erzeugt Über-Erkennung (F024). Fund. |
| 4 | §2/§7 Backtick an beliebiger Stelle → Shell-Syntax; Backslash im Alias-Wert → unresolved | sicher; Preis gering (F003, F011 sind damit geschlossen). Kein Fund. |
| 5 | §3 Abfrage mit `GIT_TRACE2*=0` und Regex für `help.autocorrect` | sicher und notwendig (F012, F013); AC-9 und AC-11 gelten wörtlich. Kein Fund. |
| 6 | §8 gestrichelte Form `git-<builtin>` normalisiert; Rümpfe dedupliziert | richtige Richtung, unvollständig umgesetzt (Roh-Text-Regex, F019). Fund. |
| 7 | §9 unzerlegbarer Rumpf → größte Commit-Menge | sicher; schließt F010. Kein Fund. |
| 8 | Arbeitsgrenze 64 Aufrufe / 64 KiB | sicher; linear gemessen; ein Befehl mit mehr als 64 Nicht-Builtin-Aufrufen ist unrealistisch. Kein Fund. |

#### Nachweise ohne Fund (Runde 2)

- Offener Punkt 4 aus Runde 1 (Wrapper und Config-Erzeuger, Alias nur in B, cwd in A; Abschnitt C5): `sudo -D B`, `sudo -u`, `runuser -u`, `chroot`, `nsenter --wd=`, `unshare --wd=`, `env -C`, `env --chdir`, `find -execdir` → Exit 2. `su -c '…'`, `runuser -l -c '…'`, `script -qec '…'` → Exit 0, aber auch der WÖRTLICHE Commit in derselben Form läuft im alten und im neuen Gate durch (Abschnitt C6): vorbestehend, dieselbe Klasse wie `bash -lc` (#298, Befehlsstring als Argument eines Nicht-Shell-Starters), kein Fund für #281. `nsenter -w<dir>` (Kurzform ohne `--wd`) → Exit 0 und Commit in B: dokumentierte Rest-Grenze (unbekannter Starter wechselt das Verzeichnis ohne A-Option); Hinweis an den Tech Lead: `nsenter` und `unshare` ließen sich in die A-Liste aufnehmen. Config-Erzeuger: `git config --worktree alias.…`, `git config --file .git/config alias.…`, `config -e` mit `GIT_EDITOR` und mit `core.editor`, `init --template`, `clone --template` → Exit 2; `git submodule add`, `git remote add`, `git worktree add` erzeugen keinen Alias (Exit 0, kein Commit, erwartet); Abkürzungen siehe F022.
- Parität zum alten Gate, kein Rückschritt: unzerlegbarer Gesamtbefehl mit `git -c … commit` (`echo $'it\'s';git G commit …`) → alt 0, neu 0 (Fail-open aus #1431, in den Known Limitations „ohne Kandidaten bleibt der Fail-open-Durchlass“); F015 unverändert.
- Marker über Shell-Alias (`!touch …user_approved…`) wird von 3a geblockt, Datei entsteht nicht; Override-Token und Stop-Lock wie in Runde 1 (Code in diesen Pfaden unverändert).
- Dokumentation: `docs/WORKFLOW_GUIDE.md`, `CLAUDE.md`, `README.md` und `CHANGELOG.md` stimmen mit dem Verhalten überein bis auf die Zusage `CHANGELOG.md:112` („in Befehlsposition hinter xargs, timeout & Co. wird normal aufgelöst“), die F018 widerlegt.
- Bewusst nicht als Fund gewertet (Known Limitations bzw. Parität): `bash -lc` (#298), externe `git-<name>` (#297), Whitelist-Gefälle (#296), `source`, Shell-Funktion `git`, Tiefe > 2, bedingtes `cd`, Unterbefehl aus stdin, unbekannte Starter, die Verzeichnis oder Benutzer wechseln, ältere git-Versionen, `su -c`/`runuser -c`/`script -c` mit Befehlsstring.
- Die Tests der Datei enthalten keinen Fall für die Klassen F018–F023 (Starter mit Argument/Umleitung, Quoting in Roh-Text-Prüfungen, Optionsabkürzungen, Indirektion); Wächter `adv-fp-*` und `adv-C-*` decken nur die gewählten Formen.

#### Checkliste: alle 27 Punkte (10 Expected Behavior und AC-1 bis AC-17)

Punkte, die ein Finding tragen, sind unten mit `Result: DISPROVEN` und dem Verweis auf das Finding geführt; alle anderen als Confirmation.

Confirmation:
  AC: Expected Behavior 1 — Input (Befehl, cwd und Umgebung des Hooks, Workflow-State, Alias-Konfiguration am Ort des Aufrufs)
  Code reference: core/hooks/bash_gate.py:683
  Code reference: core/hooks/git_alias.py:248
  Evidence: `_alias_view(command)` läuft genau einmal nach dem Stop-Lock; der Resolver nimmt `os.getcwd()` und `os.environ` des Hooks und spielt `-C`, `cd`, `-c`, `--config-env`, `--git-dir`, `--work-tree` und freigegebene Präfix-Zuweisungen nach (`context`, Zeilen 248–274). AC-3 gilt in allen vier Formen, der Fuzz ctx (Seeds 2–5, 1 200 Fälle) fand 0 Bypässe, die Runde-1-Lücken F002/F004/F009 sind geschlossen. Rest: dokumentierte Grenze (unbekannte Verzeichniswechsler); der `CDPATH`-Kontext steht unter Punkt 8 (F021).
  Status: CONFIRMED

Confirmation:
  AC: Expected Behavior 2 — Output (Exit 0 oder 2, Alias-Zeile auf stderr nur bei Erkennung über die Sicht, Block-Meldungen unverändert, `resolve_git_aliases` liefert eine `GitAliasView`)
  Code reference: core/hooks/bash_gate.py:767
  Code reference: core/hooks/git_alias.py:385
  Evidence: Hook-Fuzz 2 × 600: Exit nur 0 oder 2, kein Traceback. Die Zeile `Commit erkannt über Alias: …` kommt nur, wenn der Commit nicht wörtlich ist (`bash_gate.py:768–769`, `_alias_notice` Zeile 641); die 5c- und 3a-Texte bleiben (AC-1, AC-6). `resolve_git_aliases` liefert immer eine `GitAliasView` und wirft nie (120 000 Fuzz-Eingaben, 0 Ausnahmen; Rückfall Zeilen 400–403). Der Runde-1-Vorbehalt Timeout (F008) ist ausgeräumt: 50 000 Token in 1,87 s.
  Status: CONFIRMED

Confirmation:
  AC: Expected Behavior 3 — Side effects (höchstens drei lesende Abfragen, nur für Nicht-Builtins, schreibt nichts, führt nie Code aus dem Befehlstext aus)
  Code reference: core/hooks/git_alias.py:290
  Code reference: core/hooks/git_alias.py:67
  Evidence: Heißer Pfad über 20 Aufrufformen: Builtins 0 Prozesse (alt = neu), `git st` genau eine Abfrage, vierter Kontext unresolved (Budget, AC-9). Die Abfrage `git config -z --get-regexp ^(alias\..*|help\.autocorrect)$` ist lesend; F012 ist behoben: mit `GIT_TRACE2*=0` (Zeile 67, Anwendung Zeile 300) legt der Hook keine Datei mehr an, weder über `HOME` noch über `GIT_CONFIG_GLOBAL` (Abschnitt A2). 14 Varianten mit Code-Ausführungsversuch (Abschnitt E3): kein Sentinel. AC-11: `GIT_TRACE`-Datei wird nicht angelegt, `./git` nie ausgeführt.
  Status: CONFIRMED

Confirmation:
  AC: Expected Behavior 4 — Builtins (nie nachgeschlagen, nie überschattet; Alias-Namen case-insensitiv, Builtin-Namen exakt)
  Code reference: core/hooks/git_alias.py:228
  Code reference: core/hooks/git_alias.py:315
  Evidence: `sub in GIT_BUILTINS` beendet den Aufruf ohne Abfrage (Zeile 228); die Kette sucht `"alias." + name.lower()` und nur, solange der Name kein Builtin ist (Zeile 315). Zähler: 0 Prozesse für `git status`, `-C . status`, `--no-pager log`, `GIT_DIR=… status`, `env X=1 diff`, `add`, `stage`, `push`, `worktree`, `rev-parse`, `config`, Ketten. AC-4: `git CI` und `git STATUS` mit Alias blocken wie in echtem git 2.43; AC-8: `alias.status=commit` wirkt für `git status` nicht.
  Status: CONFIRMED

Checklist point 5 — Expected Behavior „Unterbefehl“ (ein erst zur Laufzeit feststehender Unterbefehl, auch in Alias-Werten und Shell-Rümpfen, wird ohne Abfrage als unresolved geprüft)
  Result: DISPROVEN — Finding F018
  Code reference: core/hooks/git_alias.py:230
  Evidence: Am Kopf und hinter `timeout 5` blockt `git $CMD`; hinter `timeout -s KILL 5`, `flock /tmp/lockx`, `stdbuf -o L`, `nice -n +5` und nach `>/dev/null` fällt der Laufzeitname durch den Plausibilitätsfilter (Exit 0, echte bash committet). AC-15 gilt in seinem Wortlaut (`CMD=commit; git $CMD -m x` Exit 2).

Checklist point 6 — Expected Behavior „Alias auf commit“ (gilt wie commit: lokal, global, `include.path`, `-c`, `--config-env`, Umgebung, Ketten, Optionen im Alias-Wert)
  Result: DISPROVEN — Findings F018 und F020
  Code reference: core/hooks/git_alias.py:264
  Evidence: `--config-env=K=VAR` mit im selben Aufruf veränderter Variable und gesplittetem Namen (F020) sowie der gültige Alias-Name `a.b` hinter Wrappern (F018) umgehen das Gate. Alle in den ACs genannten Quellen a–h gelten wörtlich (acverify AC-2a–h). Quellen, Ketten, Optionen im Alias-Wert und die #259-Commit-Menge über Alias (`-a`, Pfade, `--amend`, `add`/`stage`-Alias, Rumpf mit `add -A`) gleichen den wörtlichen Formen.

Checklist point 7 — Expected Behavior „Shell-Aliase“ (Rumpf wird auf Commit, Marker-Schreiben und Secrets geprüft)
  Result: DISPROVEN — Finding F019
  Code reference: core/hooks/git_alias.py:320
  Evidence: Rumpf mit `git commit`, Marker-Schreiben (3a) und der einfachen Form `git-commit` werden erkannt; Quoting (`git-com""mit`, `git\-commit`) und `sh -c 'git-commit "$@"'` umgehen die Regex (Exit 0, echte bash committet).

Checklist point 8 — Expected Behavior „Kontext“ (nachgespielter Kontext; Alias-Änderung im selben Befehl, im Befehl benannte oder geschriebene Konfigurationsdatei und unbestimmbarer Kontext machen spätere Nicht-Builtins unresolved)
  Result: DISPROVEN — Findings F020, F021, F022, F023
  Code reference: core/hooks/git_alias.py:358
  Evidence: `CDPATH` mit gesplittetem Namen (F021), Optionsabkürzungen bei den Taint-Quellen (F022), Indirektion bei Schlüssel und Variablenname (F023) und `--config-env` mit gesplittetem Variablennamen (F020) umgehen die Erkennung. Die in der Spec genannten Quellen und Formen gelten wörtlich (AC-3, AC-7 a–d); der reihenfolgeunabhängige Taint und das cd-Modell halten im Fuzz (taint und ctx, 2 400 Fälle, 0 Bypässe).

Checklist point 9 — Expected Behavior „Fehlerrichtung“ (was sich nicht sicher auflösen lässt, wird wie ein Commit geprüft; Wirkung nur, wo auch ein wörtlicher Commit geprüft würde)
  Result: DISPROVEN — Finding F018 (Erwähnungen mit Laufzeit- oder Punkt-Namen werden nicht geprüft) und, als Preis der Gegenrichtung, F024
  Code reference: core/hooks/bash_gate.py:703
  Evidence: Der Zweig `bash_gate.py:703–705` behandelt `view.unresolved` wie einen Commit; die Klausel „nur wo ein wörtlicher Commit geprüft würde“ gilt (Phase 6 und 7, Override und Stop-Lock wie zuvor). Die Lücke liegt davor: Aufrufe, die F018 als Erwähnung ohne Prüfung einstuft, erreichen `view.unresolved` nie. Der Preis in der anderen Richtung ist F024.

Confirmation:
  AC: Expected Behavior 10 — Invarianz (bei leerer Sicht verhält sich `bash_gate.py` wie zuvor, `_is_whitelisted` sieht keine Aliase)
  Code reference: core/hooks/bash_gate.py:629
  Code reference: core/hooks/bash_gate.py:218
  Evidence: 900 Läufe ALT gegen NEU (450 Befehlsketten, gesperrt und ohne Workflow): 0 Abweichungen. Auf dem Korpus von 1 572 Befehlen gibt es keinen Fall „alt blockt, neu nicht“. `_NO_VIEW` (Zeile 629) ist die leere Sicht, `_is_whitelisted` (Zeile 218) ist unverändert (AC-13). Die Laufzeitabweichung aus Runde 1 (F008) ist geschlossen.
  Status: CONFIRMED

Confirmation:
  AC: AC-1 — lokales `alias.ci=commit`, `git ci -m x` im gesperrten Zustand
  Code reference: core/hooks/bash_gate.py:703
  Code reference: tests/test_git_alias_commit_gate_281.py:303
  Evidence: acverify AC-1: Exit 2, stderr enthält „Adversary verdict missing or not VERIFIED“ und `git ci → git commit`; die Quoting-Form des Wortes git (F001) blockt jetzt ebenfalls.
  Status: CONFIRMED

Confirmation:
  AC: AC-2 — Alias-Quellen a–h
  Code reference: core/hooks/git_alias.py:248
  Code reference: tests/test_git_alias_commit_gate_281.py:340
  Evidence: acverify AC-2a–h alle bestanden: global über `GIT_CONFIG_GLOBAL`, `include.path`, inline `-c`, `GIT_CONFIG_COUNT`/`KEY_0`/`VALUE_0`, `ZZ=commit git --config-env=alias.ci=ZZ`, `env GIT_CONFIG_GLOBAL=<datei>`, `GIT_CONFIG` wird ignoriert, der letzte Wert (Kommandozeile) gewinnt; alle Exit 2. Die Quoting-Variante von `--config-env` steht unter F020.
  Status: CONFIRMED

Confirmation:
  AC: AC-3 — Kontext nachspielen (`-C`, `cd`, `bash -c`, `cd "$X"`)
  Code reference: core/hooks/git_alias.py:351
  Code reference: tests/test_git_alias_commit_gate_281.py:416
  Evidence: acverify AC-3 in allen vier Formen Exit 2 (Alias nur in Repo B, cwd in A); `cd "$X"` macht den Unterbefehl unresolved. Nachspiel-Lücken aus Runde 1 (`eval`, `builtin`, `command`, `X=1 cd`, `time`, Schleifen) sind geschlossen; `CDPATH` mit gesplittetem Namen siehe F021.
  Status: CONFIRMED

Confirmation:
  AC: AC-4 — Alias-Namen case-insensitiv, Builtin exakt
  Code reference: core/hooks/git_alias.py:315
  Code reference: tests/test_git_alias_commit_gate_281.py:443
  Evidence: acverify AC-4: `git CI -m x` mit `alias.ci=commit` und `git STATUS -m x` mit `alias.status=commit` Exit 2; entspricht echtem git 2.43 (E2E).
  Status: CONFIRMED

Confirmation:
  AC: AC-5 — Kette, Optionen im Alias-Wert, Schleife
  Code reference: core/hooks/git_alias.py:311
  Code reference: tests/test_git_alias_commit_gate_281.py:474
  Evidence: acverify AC-5a–c: `alias.c2=ci` mit `alias.ci=commit`, `alias.cx="-c user.name=zz commit"` und die Schleife `l1=l2`, `l2=l1` je Exit 2; bei der Schleife nennt stderr Grund und Ausweg. Der Backslash-Bypass aus Runde 1 (F003) ist geschlossen (Zeile 327).
  Status: CONFIRMED

Confirmation:
  AC: AC-6 — Shell-Aliase (Commit im Rumpf, Marker, harmlos)
  Code reference: core/hooks/bash_gate.py:705
  Code reference: tests/test_git_alias_commit_gate_281.py:504
  Evidence: acverify AC-6: `!git commit` Exit 2; `!touch .claude/user_approved_validation_x` Exit 2 mit der Marker-Meldung aus 3a und ohne dass die Datei entsteht; `!echo hi` Exit 0. Die Quoting-Varianten des gestrichelten Builtins stehen unter F019.
  Status: CONFIRMED

Confirmation:
  AC: AC-7 — Änderungen im selben Aufruf (Taint)
  Code reference: core/hooks/git_alias.py:364
  Code reference: tests/test_git_alias_commit_gate_281.py:572
  Evidence: acverify AC-7a, b, d Exit 2 (`git config alias.ci commit && git ci`, `export GIT_CONFIG_GLOBAL=<datei>; git ci`, im Befehl benannte, noch nicht vorhandene Datei), AC-7c Exit 0 (`git config user.name y && git st`, kein Taint). Fuzz taint 1 200 Fälle ohne Bypass. Abkürzungen und Indirektion siehe F022, F023.
  Status: CONFIRMED

Confirmation:
  AC: AC-8 — harmlose Aliase und Builtin-Schatten
  Code reference: core/hooks/git_alias.py:228
  Code reference: tests/test_git_alias_commit_gate_281.py:593
  Evidence: acverify AC-8: `git st`, `git lg`, `git status` (mit `alias.status=commit`) alle Exit 0.
  Status: CONFIRMED

Confirmation:
  AC: AC-9 — Builtins kosten keine Abfrage, Cache und Budget
  Code reference: core/hooks/git_alias.py:290
  Code reference: tests/test_git_alias_commit_gate_281.py:603
  Evidence: acverify AC-9: vier Builtin-Befehle null Abfragen; `git st && git lg` genau eine; `git -C a st; git -C b st; git -C c st; git -C d st` — der vierte Kontext ist unresolved (Budget drei). Arbeitsgrenze: `tests/test_git_alias_commit_gate_281.py:826`.
  Status: CONFIRMED

Confirmation:
  AC: AC-10 — Abfrage scheitert (rc 128)
  Code reference: core/hooks/git_alias.py:299
  Code reference: tests/test_git_alias_commit_gate_281.py:645
  Evidence: acverify AC-10: `git st` gesperrt Exit 2 mit „nicht auflösbar“ und Ausweg, `git status` Exit 0 (Builtin, keine Abfrage), `git st` ohne aktiven Workflow Exit 0.
  Status: CONFIRMED

Confirmation:
  AC: AC-11 — Abfrage führt nie fremden Code aus
  Code reference: core/hooks/git_alias.py:298
  Code reference: tests/test_git_alias_commit_gate_281.py:675
  Evidence: acverify AC-11: `GIT_TRACE=<pfad> git -c alias.ci=commit ci` und `./git ci` Exit 2; die Datei unter `<pfad>` entsteht nicht, das Sentinel des `./git` nicht; der Runner bekommt weder `GIT_TRACE*` noch `GIT_CONFIG`. Dazu 14 Code-Ausführungsversuche ohne Sentinel (Abschnitt E3).
  Status: CONFIRMED

Confirmation:
  AC: AC-12 — #259-Commit-Menge folgt den Alias-Argumenten
  Code reference: core/hooks/bash_gate.py:492
  Code reference: tests/test_git_alias_commit_gate_281.py:715
  Evidence: acverify AC-12: Phase 7, VERIFIED, Dialog zitiert nur B: `git ci` Exit 0 (Index-Form), `git cam msg` (`commit -a -m`) Exit 2 mit C in stderr, `git a NEU.py && git ci` und `git s NEU.py && git ci` Exit 2 mit NEU.py. Unzerlegbarer Rumpf → größte Menge (`bash_gate.py:505`, F010 geschlossen).
  Status: CONFIRMED

Confirmation:
  AC: AC-13 — Whitelist ruft den Resolver nie auf
  Code reference: core/hooks/bash_gate.py:218
  Code reference: tests/test_git_alias_commit_gate_281.py:734
  Evidence: acverify AC-13: `_is_whitelisted("git ci -m x")` mit einem auf eine werfende Funktion gepatchten Resolver liefert False ohne Fehler; die Whitelist wertet nur den Originaltext.
  Status: CONFIRMED

Confirmation:
  AC: AC-14 — Resolver-Ausnahme und fehlende Hilfsdatei
  Code reference: core/hooks/git_alias.py:400
  Code reference: core/hooks/bash_gate.py:633
  Evidence: acverify AC-14: (a) Ausnahme im Resolver → Sicht unresolved, wenn ein Nicht-Builtin gesehen wurde, sonst leer (Rückfall Zeilen 400–403); (b) Hook-Kopie ohne `git_alias.py`: `git st` Exit 0 wie bisher, stderr-Hinweis auf die fehlende Datei (`bash_gate.py:633–637`).
  Status: CONFIRMED

Confirmation:
  AC: AC-15 — nicht bestimmbarer Unterbefehl (unzerlegbar oder Laufzeitname)
  Code reference: core/hooks/git_alias.py:200
  Code reference: tests/test_git_alias_commit_gate_281.py:813
  Evidence: acverify AC-15: `git ci -m $'it\'s'` Exit 2, `git status $'it\'s'` Exit 0, `CMD=commit; git $CMD -m x` Exit 2. 18 Varianten der naiven Zerlegung (verklebter Trenner, Quoting, Pfadform, Wrapper, `cd`, `-C`, `GIT_DIR=`) alle Exit 2 (Abschnitt C4). Laufzeitnamen hinter Wrappern mit Argument stehen unter F018.
  Status: CONFIRMED

Confirmation:
  AC: AC-16 — Doku-Anker
  Code reference: docs/WORKFLOW_GUIDE.md:213
  Code reference: CLAUDE.md:56
  Code reference: README.md:382
  Code reference: CHANGELOG.md:77
  Evidence: Die Fast-Path-Zeile der `bash_gate.py`-Übersicht nennt die Alias-Auflösung (WORKFLOW_GUIDE Zeilen 213–214); `CLAUDE.md` (Baum Zeile 56, „Wichtige Dateien“ Zeile 441) und `README.md` (Baum Zeile 382) führen `git_alias.py` als Hilfsmodul ohne Hook; `CHANGELOG.md` nennt unter `[Unreleased]` #281, die neuen Block-Fälle und den Nebeneffekt von `git stage`. Die Doku-Tests der Datei laufen grün (`pytest -k`: 5 passed). Einzige Abweichung vom Verhalten: CHANGELOG.md:112 (F018).
  Status: CONFIRMED

Confirmation:
  AC: AC-17 — GIT_BUILTINS gegen die installierte git-Version
  Code reference: core/hooks/git_alias.py:29
  Code reference: tests/test_git_alias_commit_gate_281.py:867
  Evidence: git 2.43.0 installiert: `git --list-cmds=builtins` und `GIT_BUILTINS` sind identisch (140 = 140), der Test fordert nur die Teilmenge.
  Status: CONFIRMED

#### Hinweise an den Tech Lead (nicht verdict-relevant)

- Alle Remediation-Prototypen liefen in Scratch-Kopien unter `/tmp/claude-0/-home-user-agent-os-openspec/76054b3f-0401-5941-9b95-6f771556ea2e/scratchpad/adv/fix3*` (Repo unberührt); sie halten die 238 Tests der Datei grün (Belege: Abschnitt I der Belegdatei). Sie sind Hinweise, keine Vorgabe.
- Gemeinsames Muster hinter F019–F021: Prüfungen auf rohem Befehlstext statt auf Lexer-Tokens. Ein Grep nach `self.command`, `table[key]` und `"…" in …command` in `git_alias.py` liefert die Kandidaten (Zeilen 264–265, 320, 358 sind belegt); jede solche Prüfung sollte auf Tokens oder `_UNQUOTE`-normalisierten Text umgestellt werden.
- F023 und der Rest von F017 (Glob-Ziel, `$(git rev-parse --git-dir)/config`) sind eine Frage der Known Limitations: entweder dort ausdrücklich nennen oder als Taint werten.
- Nach CLAUDE.md gilt bei BROKEN: gezielter Fix, dann höchstens eine weitere Adversary-Runde; ein zweites BROKEN eskaliert an den User.

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

#### Abschluss Runde 2

Fünf Expected-Behavior-Punkte (5 bis 9) sind widerlegt, alle 17 ACs gelten in ihrem Wortlaut. Der Stand schließt die Runde-1-Bypässe F001–F004, F006, F008, F010–F014, öffnet aber an den Fixes und den neuen Mechanismen sieben neue Lücken: F018 (HIGH), F019 (MEDIUM), F020 (MEDIUM), F021–F023 (LOW) und die Über-Erkennung F024 (MEDIUM). F018, F019 und F020 sind weder Known Limitation noch dokumentierte Rest-Grenze, jede ist mit echter bash reproduziert (wörtliches `commit` blockt, die Alias-Form Exit 0, Commit entsteht) und stützt das Verdict BROKEN. Die Behebung ist überschaubar und im Scratch erprobt (Lexer-Tokens statt Roh-Text, Starter-Operanden und Umleitungen, `strip_heredoc_bodies` für den Resolver).

═══════════════════════════════════════
VERDICT: BROKEN
═══════════════════════════════════════
Findings: F018 (HIGH), F019, F020, F024 (MEDIUM), F021, F022, F023 (LOW)
Tests: 238 passed in der Datei, 1797 passed und 28 skipped in der vollen Suite, 0 failed
Checklist: 22/27 Punkte bewiesen (5 Expected-Behavior-Punkte widerlegt: F018–F023)

## Geprüfte Dateien

- sha256:947aeb839b3cab66da73937573b68670246dfaa1c8e8e65a73d039943e10aaca  CHANGELOG.md
- sha256:8a50d46875ad8c3dbddf0fc39c1c6f0305d275fdfa924a6ef2e8dc8f1f9b52a7  CLAUDE.md
- sha256:5621e3de0bb3ddb848dec73c38b822fb167c08c560d729de4a63358de53d7f4d  README.md
- sha256:5ecd252f54d33933c574bde087a8c69322caba6f97870088cf415776740a1a31  core/hooks/bash_gate.py
- sha256:297a9e47cf988184ae373691908a3c955c9cbde5161c44550dfc5a7313571077  core/hooks/git_alias.py
- sha256:fe55f687b30bb6a563808b8b6d870713c083fddde274848146813621b03d802b  core/hooks/hook_utils.py
- sha256:c6e5dd899186ddd39ae1f910c976584774431647e5f44e678bcd90d3c5661905  docs/WORKFLOW_GUIDE.md
- sha256:a40c1d7823baf4f7a0b5b61b31617a700ec402b2674bdcc6b9fa93896ae7a7ea  tests/test_git_alias_commit_gate_281.py

## Runde 3

### Runde 3

**Adversary:** Kurze Abschlussprüfung nach der PO-Entscheidung, nur auf die geänderten Stellen. Geändert sind `core/hooks/git_alias.py` (403 → 440 Zeilen: Umleitungen und Operanden-Tabelle in `_head`/`_stellungen`, Punkt-Namen, lexer-basierte gestrichelte Form, `_UNQUOTE`-Zählung, Optionspräfixe, Indirektions-Taint) und eine Zeile in `core/hooks/bash_gate.py:638` (der Resolver bekommt `strip_heredoc_bodies(command)`); die Tests wuchsen auf 283. Jede Runde-2-Reproduktion F018–F024 lief erneut gegen die echte bash (hermetische Wegwerf-Repos, echtes git 2.43, Hook-Exit gegen tatsächlich entstandene Commits; ALT = HEAD, R2 = Code des Runde-2-Stands, NEU = Arbeitsbaum), dazu je eine naheliegende Variante und die Angriffe auf die geänderten Stellen. Bypass heißt wie zuvor: das wörtliche `commit` blockt, die Alias-Form geht mit Exit 0 durch, die echte bash committet, keine Known Limitation oder dokumentierte Rest-Grenze. Alle Ausgaben: `docs/artifacts/fix-281-git-alias-commit-gate/adversary-repro-round3.txt` (Abschnitte A bis J). `G` steht für `-c user.name=T -c user.email=t@t`. Am Repo, an Code, Tests, Spec und Doku wurde nichts geändert; Remediation-Prototypen liefen in Scratch-Kopien.

**Kurzfassung:**
- F018–F024: Alle Runde-2-Reproduktionen sind blockiert. F019, F020, F021 und F024 sind behoben, F023 bis auf dokumentierte Reste; F018 und F022 haben Reste (F027, F029).
- **Der Fix für F024 öffnet einen neuen HIGH-Bypass (F025):** `strip_heredoc_bodies` hält jedes `<<` samt Bezeichner für einen Heredoc-Öffner, auch in Anführungszeichen, Kommentaren, Arithmetik und Suchmustern. Alle Folgezeilen sind für den Resolver unsichtbar: `echo '<<X'` und in der nächsten Zeile `git ci -m x` geht mit Exit 0 durch und committet. Der Runde-2-Code blockte alle diese Formen, das wörtliche `git commit` blockt weiter. Zufallsfuzz über 500 mehrzeilige Befehle: 67 Bypässe neu, 0 im Runde-2-Code.
- Weitere neue Funde: F026 (MEDIUM, die lexer-basierte gestrichelte Form verliert die Argumente: Phase 7 zählt `-a`, `--all` und Pfade im Rumpf nicht mehr), F027 (MEDIUM, Reste von F018: `sudo -u root git $CMD` und Punkt-Namen hinter A-Startern, Lücken der Operanden-Tabelle), F028 (LOW, dokumentierter Preis: ausgeführte Heredoc-Bodies), F029 (LOW, Varianten von F022/F023).
- Der Wortlaut aller 17 ACs gilt (38 von 38 eigene Prüfungen, 283 Tests der Datei, volle Suite grün); Über-Erkennung auf dem Korpus sinkt von 55 auf 39 Zusatzblöcke.

#### Testläufe Runde 3 (selbst ausgeführt)

| Lauf | Ergebnis |
|------|----------|
| `python3 -m pytest tests/test_git_alias_commit_gate_281.py -q` | 283 passed (Runde 2: 238) |
| `python3 -m pytest tests/ -q` (gespeichert, überschrieben: `docs/artifacts/fix-281-git-alias-commit-gate/adversary-test-output.txt`) | @@SUITE@@ |
| Eigene wortgetreue AC-Prüfung gegen echtes git und echte bash (`acverify.py`, 38 Fälle) | 38/38 bestanden |
| Runde-1-Reproduktionen (`repro_round1*.py`) und Runde-2-Reproduktionen (`repro_round2*.py`) erneut | alle Runde-2-Bypässe F018–F023 blockiert; unverändert Exit 0 nur die dokumentierten oder vorbestehenden Fälle (F015, F017-Reste, `su -c`, `nsenter -w<dir>`) |
| Invarianz-Differential: 450 zufällige Befehlsketten, gesperrt und ohne Workflow, ALT gegen NEU | 900 Läufe, 0 Abweichungen im Exit-Code |
| Heißer Pfad (git-Prozesszähler, 20 Aufrufformen), 14 Versuche, über die Abfrage fremden Code auszuführen, Override-Token, Stop-Lock | Builtins 0 Prozesse, `git st` 1 Abfrage; kein Sentinel; Override hebt auf, Stop-Lock blockt vor der Abfrage |
| Differentielles Fuzzing gegen die echte bash (wrap / ctx / taint, je 300 Fälle, Seeds 6 und 7) | 1 800 Läufe, 0 Bypässe (plausible Alias-Namen; deckt F025–F029 nicht ab) |
| Strukturelles Fuzzing (Wrapper × Container × Quoting, `struct_fuzz.py`, Seeds 1 und 2, je 300), differentielles Fuzzing mit Alias-Quellen, Ketten, `-C`/`cd`/`-c` (`diff_fuzz.py`, Seeds 1 und 2, je 200) und Quellen × Wrapper (`r2fuzz2.py`, Seed 3, 300) | 1 300 Läufe, 0 Bypässe (die Grammatiken enthalten weder Heredoc-Attrappen noch A-Starter mit Optionswert) |
| Heredoc-Fuzz (neu): 500 zufällige mehrzeilige Befehle aus Heredoc-ähnlichen Zeilen plus einem Alias-Aufruf | NEU 67 Bypässe (13 %), Runde-2-Code 0 |
| Robustheit: Resolver-Fuzz 2 × 60 000, Hook-Fuzz 2 × 600 | 0 interne Fehler, Exit nur 0 oder 2, kein Traceback |
| Korpus 1 572 echte Bash-Befehle, ALT / R2 / NEU, gesperrter Zustand (`corpus_diff.py` des Tech Leads und eigener Lauf) | alt blockt und neu nicht: 0; neu blockt zusätzlich 39 (2,5 %; Runde 2: 55); 16 Befehle sind gegenüber Runde 2 frei |
| Laufzeit auf demselben Korpus | Median 0,094 s neu gegen 0,090 s alt (Tech Lead: 0,160 / 0,154 s); Maximum 0,29 / 0,35 s |

#### Ergebnis je Fund F018–F024 (Runde-2-Reproduktion plus Variante, gegen die echte bash)

| Fund | Ergebnis R3 | Beleg |
|------|-------------|-------|
| F018 | teilweise behoben (Rest: F027) | Alle 14 Runde-2-Formen blocken (Abschnitt A-C; `timeout -s KILL 5`, `flock`, `stdbuf -o L`, `nice -n +5`, `>/dev/null`, `2>/dev/null` mit `$CMD`, `$(echo ci)`, `a.b`; Autocorrect hinter `mywrap`); auch `mywrap git a.b` (Verzeichnis bekannt) blockt jetzt. Variantenmatrix 59 Starter- und Umleitungsformen × 3 Namen (plausibel, Laufzeit, Punkt) = 177 Fälle: plausible und Punkt-Namen alle Exit 2, aber 10 Bypässe mit Laufzeitnamen (`timeout .5`, `1e1`, `5.`, `0x5`, `infinity`; `ionice --class best-effort`; `stdbuf --output L`; `flock --wait 5 F`; `exec -a foo`; `&>/dev/null`), dazu `sudo -u root git $CMD` und der Punkt-Name hinter `sudo -u root` (Abschnitt D) → F027. |
| F019 | behoben, Nebenwirkung F026 | Alle 7 Runde-2-Formen und die 18 Schreibweisen aus Abschnitt A-C7 sowie 17 weitere Rumpf-Varianten (Quoting, `sh -c`, `bash -c`, `eval`, absoluter Pfad, `$(git --exec-path)/git-commit`, Heredoc im Rumpf, `xargs`, `sudo`, `env -i`, `git-add && git-commit`) Exit 2; frei bleiben erwartungsgemäß `git-commit-tree`, `ls git-hooks` und die Schachtelung 3 (dokumentierte Grenze). Die Umstellung verliert die Argumente: F026. |
| F020 | behoben | Die 4 Runde-2-Formen (`TE""RM`, `TE\RM`, `declare -x`, `eval`) und `local`, `bash -c`, `eval "export ${P}RM"`, `export $'TE\x52M'` Exit 2. Rest `eval $'export TE\x52M=commit'` (Name aus eval, dokumentierte Grenze) → F029. |
| F021 | behoben | `export CD""PATH=…; cd dec && git ci` und `CD\PATH` Exit 2. |
| F022 | teilweise behoben (Rest: F029) | `init --tem=`, `--te=`, `--t=`, `--t <dir>`, `clone --templ=`, `config --ed`, `--edi` Exit 2. Gebündeltes `git config -ze`, `-ez`, `--local -ez` (git akzeptiert gebündelte Kurzoptionen und öffnet den Editor) → Exit 0, Commit. |
| F023 | behoben bis auf dokumentierte Reste | `K=alias.ci; git config $K commit`, `--add $K`, `--file F $K`, `eval 'git config $K …'`, `export ${P}OBAL`, `declare -x ${P}…`, `export "$N=$V"`, `printf -v`, `read`, `export $(cat vars)`, `` export `echo X`= `` Exit 2. Exit 0: `env $N=$V git ci` (dokumentiert: Name aus Variable) und `git config --type path $K commit` (Schlüssel ist nicht das erste Nicht-Option-Token) → F029. |
| F024 | behoben, Preis F025 | Phase 7 mit und ohne `cd`: Commit-Nachricht mit „git hooks“ und `don't resolve git aliases` Exit 0; `gh pr create` und `cat > docs/n.md` mit Apostroph Exit 0; `bash <<'EOF'`, `sh <<'EOF'`, `cat <<'EOF' \| bash` mit `git ci` blocken weiter. Bewusst weiter Exit 2: `echo it's git time`, `cd "$D" && echo git done`, Heredoc mit `.sh` auf der Öffner-Zeile. Korpus 55 → 39 Zusatzblöcke. Verschlechtert hat sich die Sicherheit: F025. |

#### Neue Funde (Runde 3)

Finding:
  ID: F025
  Severity: HIGH
  Category: regression
  Code reference: core/hooks/bash_gate.py:638
  Code reference: core/hooks/hook_utils.py:624
  Code reference: core/hooks/hook_utils.py:660
  Description: Der Fix für F024 gibt dem Resolver `strip_heredoc_bodies(command)` (`bash_gate.py:638`). Die Funktion erkennt einen Heredoc-Öffner mit einer Regex über die ganze Zeile (`hook_utils.py:624`): jedes `<<` plus Bezeichner zählt, auch in Anführungszeichen, in Kommentaren, in Arithmetik (`$((1<<N))`) und in Suchmustern (`grep "<<EOF"`). Alle folgenden Zeilen gelten dann als Body, bis eine Zeile dem Bezeichner gleicht, sonst bis zum Ende, und sind für den Resolver unsichtbar: Für einen Alias-Aufruf dort gibt es weder Abfrage noch `unresolved`. Der Interpreter-Schutz (Zeile 660) prüft nur die Öffner-Zeile selbst; eine Attrappe INNERHALB eines sichtbaren Interpreter-Bodys (`bash <<'EOF'`, darin `echo '<<X'`, darunter `git ci`) versteckt die Folgezeilen ebenso. Bei einem ungequoteten Begrenzer (`cat <<EOF`) strippt die Funktion den Body, obwohl die Shell `$(…)` und Backticks darin ausführt. Das wörtliche `git commit` blockt weiter, weil `main()` für `literal_commit` den vollen Text nimmt (`bash_gate.py:702`); die Alias-Form nicht.
  Spec requirement: Expected Behavior „Alias auf commit gilt wie commit“ und „Fehlerrichtung“, AC-1 (die Reproduktion aus #281); der CHANGELOG nennt nur „Heredoc-Prosa ohne Interpreter zählt nicht“.
  Conflict: Die Reproduktion aus #281 (Alias `ci=commit`, `git ci -m x`) geht mit Exit 0 durch und committet, sobald in einer Zeile davor `<<X` steht. Das ist weder Heredoc-Prosa noch eine dokumentierte Grenze: In den Formen unten kommt gar kein Heredoc vor. Der Runde-2-Stand blockte jede davon; der Fix hat den Bypass neu geöffnet. Auch arglos erreichbar: `echo $((1<<N))` oder `grep "<<EOF" f` in einer Zeile davor.
  Reproduction (Alias `ci=commit` lokal, gesperrter Zustand; jeweils Exit 0 und Commit entsteht; R2-Code und das wörtliche `commit` an derselben Stelle: Exit 2; Abschnitt B der Belegdatei):
    `echo '<<X'` ⏎ `git G ci --allow-empty -m x`
    `# kommentar <<X` ⏎ `git G ci …`; `echo "a <<X b"` ⏎ `git G ci …`; `echo $((1<<N))` ⏎ `git G ci …`; `grep -n "<<EOF" /dev/null` ⏎ `git G ci …`
    `echo "<<ZZZ"; cat <<EOF` ⏎ `data` ⏎ `EOF` ⏎ `git G ci …`
    `bash <<'EOF'` ⏎ `echo '<<X'` ⏎ `git G ci …` ⏎ `EOF` (Attrappe im sichtbaren Interpreter-Body); ebenso `sh -s <<'EOF'` mit `# <<X`
    `cat <<EOF` ⏎ `$(git G ci …)` ⏎ `EOF` und dasselbe mit Backticks (ungequoteter Heredoc führt den Body aus)
    Phase 7 (VERIFIED, Dialog zitiert nur `src/b.py`, Alias `cam = commit -a -m`): `echo '<<X'` ⏎ `git cam msg` → Exit 0 (R2 Exit 2); ohne die Attrappe Exit 2. Der wörtliche Commit mit `-a` auf der Folgezeile blockt weiter (`_commit_form` liest den vollen Text).
    Zufallsfuzz (500 mehrzeilige Befehle aus Heredoc-ähnlichen Zeilen plus einem Alias-Aufruf): NEU 67 Bypässe, R2 0.
    Kontrollen → Exit 2: `bash <<'EOF'` ⏎ `git G ci …` ⏎ `EOF`, `cat <<'EOF' | bash`, `bash -c "$(cat <<'EOF' …)"`, `cat > run.sh <<'EOF' … sh run.sh`.
  Remediation: Öffner so erkennen, wie die Shell es tut: `<<` nur außerhalb von Quotes, Kommentaren und `$((…))`, nur mit zitiertem Begrenzer (bei unzitiertem führt die Shell den Body aus), nur wenn die Öffner-Zeile weder Interpreter noch `eval`, `source`, `.`, `exec`, `xargs` enthält, und nur wenn die Terminator-Zeile existiert. Im Scratch erprobt (rund 50 Zeilen in `bash_gate.py`, Repo unberührt): alle Formen oben blocken wieder, auch die Attrappe im Interpreter-Body und der ungequotete Heredoc; die Prosa-Fälle aus F024 (`gh pr create`, `cat > doc`) bleiben frei; alle 283 Tests grün; Heredoc-Fuzz 250 Läufe 0 Bypässe (neuer Stand dort: 35) (Abschnitt J). Alternative: dem Resolver wieder den vollen Text geben (Runde-2-Verhalten) und die Prosa-Falschblöcke anders lösen. Tests für Attrappen fehlen heute; vorhanden sind nur `bash <<` und `sh <<` am Kopf.

Finding:
  ID: F026
  Severity: MEDIUM
  Category: regression
  Code reference: core/hooks/git_alias.py:353
  Code reference: core/hooks/git_alias.py:354
  Code reference: core/hooks/bash_gate.py:505
  Description: Die lexer-basierte Erkennung der gestrichelten Form (Fix für F019) hängt dem Rumpf je gefundenem `git-<builtin>` eine Zeile `git <builtin>` ohne Argumente an (Zeile 354). Der Runde-2-Code ersetzte `git-commit` an Ort und Stelle und ließ die Argumente stehen. `_commit_form` (`bash_gate.py:492`) liest jetzt nur noch das argumentlose `git commit` und wertet die Index-Form; `-a`, `--all` und Pfadangaben aus dem Rumpf gehen verloren (auch in verschachteltem `sh -c '…'`). In Phase 7 (VERIFIED, gestempelter Dialog) passiert so ein Commit, der nicht zitierte Arbeitsbaum-Dateien mitnimmt.
  Spec requirement: Expected Behavior „Alias auf commit“ („seine Argumente bestimmen die #259-Commit-Menge“) und „Shell-Aliase“, AC-12 (Arbeitsbaum-Form über Alias-Argumente), Abschnitte 8 und 9.
  Conflict: `!git commit -a -m` blockt (Exit 2, nennt die Datei C), `!git-commit -a -m` passiert (Exit 0); der Runde-2-Code blockte beide.
  Reproduction (Phase 7, VERIFIED, Dialog zitiert nur `src/b.py`, `src/c.py` getrackt geändert; Abschnitt C): Alias `!git-commit -a -m`, `!git-commit --all -m`, `!/usr/lib/git-core/git-commit -a -m`, `!git-commit -- src/c.py -m`, `!sh -c 'git-commit -a -m "$@"' --`, jeweils `git <alias> msg` → Exit 0 (R2: Exit 2 außer der `sh -c`-Form). Kontrollen → Exit 2: `!git commit -a -m`, `commit -a -m` (AC-12), `!git commit -- src/c.py -m`; die Index-Form `!git-commit -m` bleibt Exit 0.
  Remediation: die angehängte Zeile um die Argumente des Segments ergänzen (`git <builtin> <Rest des Segments>`). Im Scratch erprobt: alle fünf Formen blocken wieder, die Index-Form bleibt frei, 283 Tests grün (Abschnitt J). Test für `-a`, `--all`, Pfad und `sh -c` ergänzen.

Finding:
  ID: F027
  Severity: MEDIUM
  Category: spec_violation
  Code reference: core/hooks/git_alias.py:63
  Code reference: core/hooks/git_alias.py:68
  Code reference: core/hooks/git_alias.py:260
  Description: Reste von F018, die die Nachbesserung nicht schließt. (a) A-Starter: `_OPTVAL` (Zeile 63) kennt nur Starter, die Verzeichnis und Benutzer behalten. Bei `sudo -u root git …`, `sudo -n -u root git …` und `runuser -u root -- git …` kippt der Wert hinter der Option das git-Token nach „C!“ (hinter A-Starter). Dort wird ein Laufzeitname (`$CMD`, `$(echo ci)`) nicht geprüft, und der Punkt-Name `a.b` fällt durch die neue Ausnahme in Zeile 260 (`k == "C!"`). `sudo git …` und `sudo -E git …` blocken; der CHANGELOG nennt `sudo` als geblockt. (b) Dieselbe Ausnahme gilt bei offenem Verzeichnis für Erwähnungen: `cd "$D" && taskset 1 git a.b`, `cd "$D" && mywrap git a.b` passieren; der CHANGELOG verspricht für Erwähnungen mit möglichem Alias-Namen „dann aber mit allen Regeln“, die Ausnahme steht dort nicht (die Rückmeldung des Fixers nennt sie für das offene Verzeichnis, für „C!“ hinter A-Startern nennt sie nichts). Bei bekanntem Verzeichnis blockt dasselbe. (c) Lücken der Tabelle für BEKANNTE Starter, nur mit Laufzeitnamen: `_ARG` (Zeile 68) kennt `.5`, `1e1`, `5.`, `0x5`, `infinity` nicht (`timeout` nimmt sie alle), `ionice --class NAME`, `stdbuf --output L`, `flock --wait 5 FILE` (die 5 wird als Sperrdatei verbraucht), `exec -a NAME`; `&>/dev/null git …` (der Lexer macht `&>` zum Trenner, `/dev/null` wird zum Kopf; für `&>` greift `_REDIR_OP` deshalb nie).
  Spec requirement: Expected Behavior „Unterbefehl“ (Laufzeitname → unresolved), „Alias auf commit“; Zusagen im CHANGELOG zu `sudo` und zu Erwähnungen.
  Conflict: Das wörtliche `sudo -u root git commit` blockt (alt und neu); die Formen unten gehen mit Exit 0 durch, die echte bash committet.
  Reproduction (Alias `ci=commit` bzw. `[alias "a"] b = commit` lokal; jeweils Exit 0 und Commit; Abschnitt D):
    (a) `sudo -u root git G $(echo ci) --allow-empty -m x`, `export CMD=ci; sudo -u root git G $CMD …`, `sudo -n -u root git G $CMD …`, `runuser -u root -- git G $CMD …`; Punkt-Name: `sudo -u root git G a.b …`, `sudo -n -u root git G a.b …`, `runuser -u root -- git G a.b …`. Kontrollen → Exit 2: `sudo git G $CMD`, `sudo -E git G $CMD`, `sudo -u root git G ci …`.
    (b) `export D=<cwd>; cd "$D" && mywrap git G a.b …`, `cd "$D" && taskset 1 git G a.b …`. Kontrollen → Exit 2: `cd "$D" && timeout 5 git G a.b …`, `cd "$D" && >/dev/null git G a.b …`, `mywrap git G a.b …` ohne `cd`.
    (c) `timeout .5 git G $(echo ci) …`, `timeout 1e1`, `timeout 5.`, `timeout 0x5`, `timeout infinity`, `ionice --class best-effort git G $(echo ci) …`, `stdbuf --output L git G $(echo ci) …`, `flock --wait 5 /tmp/lock git G $(echo ci) …`, `exec -a foo git G $(echo ci) …`, `&>/dev/null git G $(echo ci) …`.
  Remediation: Starter-Tabelle um A-Starter erweitern (`sudo -u/-g/-D/-h/-p/-C/-R/-T/-U/-r/-t`, `runuser -u/-g/-G/-s/-c`, `doas -u/-C`), `exec -a`, `flock --wait`, `ionice --class`, `stdbuf --input/--output/--error`, `xargs --arg-file/--delimiter/--eof`, `_ARG` um `.5`, `1e1`, `5.`, `0x…`, `inf`/`infinity`. Die Punkt-Name-Ausnahme nur für echte Erwähnungen zulassen (Kopfwort ist ein Such- oder Ausgabekommando wie `grep`, `echo`, `cat`), nicht für `C!` und nicht für unbekannte Kopfwörter. Im Scratch erprobt (Tabelle und `_ARG`): alle Formen unter (a) und (c) außer `&>` blocken, die Erwähnungs-Kontrollen (`sudo grep -rn git README.md`, `nice -n 5 grep git $PATTERN docs/`, `xargs -a f grep git`) bleiben frei, 283 Tests grün (Abschnitt J). (b) und `&>` sind Entscheidungen beim Tech Lead (Ausnahme eng fassen; `&>` im Lexer als Umleitung statt Trenner lesen, das berührt das bewusst unveränderte `hook_utils.py`, F015/#304).

Finding:
  ID: F028
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/bash_gate.py:638
  Code reference: core/hooks/hook_utils.py:625
  Description: Heredoc-Bodies, die die Shell ausführt, bleiben für den Resolver unsichtbar, weil die Öffner-Zeile kein Interpreter-Wort aus `_HEREDOC_INTERPRETER_RE` enthält (`python3?`, `node`, `perl`, `ruby`, `php`, `sh`-Familie): `eval "$(cat <<'EOF' …)"`, `source /dev/stdin <<'EOF'`, `. /dev/stdin <<'EOF'`, `while read -r l; do eval "$l"; done <<'EOF'`, `cat > /tmp/s <<'EOF' … EOF` mit späterem `bash /tmp/s`. Das wörtliche `git commit` an derselben Stelle blockt, der Runde-2-Stand blockte auch die Alias-Form.
  Spec requirement: Expected Behavior „Alias auf commit gilt wie commit“.
  Conflict: Teilweise dokumentiert: `CHANGELOG.md` nennt „Heredoc-Prosa ohne Interpreter zählt nicht“. Das Wort „Prosa“ trifft auf Code nicht zu, `eval`, `source`, `.`, `exec` und `xargs` sind nicht als Interpreter geführt. Wegen der Dokumentation höchstens LOW.
  Reproduction (Alias `ci=commit`, gesperrter Zustand; Exit 0 und Commit; Abschnitt B): die fünf genannten Formen mit `git G ci --allow-empty -m x` im Body; Kontrollen → Exit 2: `bash <<'EOF'`, `sh <<'EOF'`, `cat <<'EOF' | bash`, `xargs -I{} sh -c '{}' <<'EOF'`.
  Remediation: `eval`, `source`, `.`, `exec`, `xargs` als Interpreter-Wörter führen (im Scratch geprüft, siehe F025; die Skript-Datei-Form `cat > file <<'EOF'` bleibt ein dokumentierter Preis) und die Formulierung im CHANGELOG anpassen.

Finding:
  ID: F029
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/git_alias.py:403
  Code reference: core/hooks/git_alias.py:406
  Code reference: core/hooks/git_alias.py:414
  Description: Varianten von F022 und F023 an den geänderten Stellen. (a) `taint_config` erkennt `-e` nur als eigenes Token (Zeile 406); git bündelt Kurzoptionen: `git config -ze`, `-ez` und `--local -ez` öffnen den Editor (`GIT_EDITOR`-Skript legt den Alias an) ohne Taint. (b) Der Schlüssel wird als erstes Nicht-Option-Token nach `config` bestimmt (Zeile 403): bei `git config --type path $K commit` ist das `path`, `$K` bleibt unbemerkt. (c) `env $N=$V git ci` und `env "$N=$V" git ci` setzen `GIT_CONFIG_GLOBAL` über Variablennamen ohne `export` (dokumentiert: Name aus Variable); `eval $'export TE\x52M=commit'` setzt eine `--config-env`-Variable über ANSI-C-Quoting in `eval` (dokumentiert: Name aus eval).
  Spec requirement: Abschnitt 5 (Taint (a), (c)), Known Limitations „verschleierte Config-Schreibzugriffe“.
  Conflict: (a) und (b) sind nicht dokumentiert, aber exotisch; (c) fällt mit der dokumentierten Rest-Grenze „Indirektion jenseits von `git config $K` und `export ${P}…=`“ zusammen. Deshalb LOW.
  Reproduction (Alias entsteht im selben Aufruf; Exit 0 und Commit; Abschnitt E): `GIT_EDITOR=<ed.sh> git config -ze && git G ci …`, `… git config -ez …`, `… git config --local -ez …`; `K=alias.ci; git config --type path $K commit && git G ci …`; `N=GIT_CONFIG_GLOBAL; V=<datei>; env $N=$V git G ci …`; `eval $'export TE\x52M=commit'; git G --config-env=alias.ci=TERM ci …` (Hook-Umgebung mit `TERM=xterm`). Kontrolle → Exit 2: `git config -e`.
  Remediation: gebündelte Kurzoptionen auswerten (ein Token `-[A-Za-z]*e[A-Za-z]*` mit einem einzelnen Bindestrich, wenn `config` im Segment steht), den Schlüssel als erstes Token mit `.` oder `$` nach `config` suchen oder jedes Token mit Shell-Syntax als Schlüssel werten.

#### Bewertung der Nachbesserung (Änderung gegen Befund)

| Änderung | Urteil |
|----------|--------|
| Umleitungen und Operanden-Tabelle `_OPTVAL` in `_head`/`_stellungen`, `_ARG` mit Vorzeichen | wirksam für alle Runde-2-Formen; von 59 Starter- und Umleitungsformen blocken 49 für alle drei Namensarten (plausibel, Laufzeit, Punkt), 10 lassen Laufzeitnamen durch (A-Starter, `.5`, lange Optionen, `&>`): F027 |
| `.` im Plausibilitätsmuster, Ausnahme für Punkt-Namen bei offenem Verzeichnis und hinter A-Startern | schließt `mywrap git a.b` bei bekanntem Verzeichnis; die Ausnahme selbst öffnet `sudo -u root git a.b` und `cd "$D" && taskset 1 git a.b` (F027) |
| `help.autocorrect` im Aufruf gesetzt wirkt auch für Erwähnungen | wirksam (`mywrap git -c help.autocorrect=immediate comit` blockt) |
| gestrichelte Form lexer-basiert über `_all_tokens` | erkennt alle Quoting- und `sh -c`-Formen; verliert die Argumente (F026) |
| `_UNQUOTE`-Zählung für `--config-env` und `CDPATH` (einmal je Befehl) | wirksam (F020, F021); Rest nur dokumentierte Indirektion |
| Optionspräfixe ab 3 Zeichen für `--template` und `--edit` | wirksam; gebündelte Kurzoptionen nicht (F029) |
| Taint für `git config $K` und `export`, `declare`, `typeset`, `readonly`, `local` mit `$`/`{` im Namen | wirksam; Reste `--type path $K`, `env $N=$V` (F029, dokumentiert) |
| `strip_heredoc_bodies` vor dem Resolver | behebt die Prosa-Falschblöcke (F024), öffnet aber F025 (HIGH) und F028 (LOW, dokumentiert) |

#### Messwerte

**Über-Erkennung** (Korpus `scratchpad/bash_corpus.json`: 1 572 echte Bash-Befehle, 743 mit „git“; gesperrter Zustand; kein Befehl wird ausgeführt):

| Übergang (alt / R2 / neu) | Anzahl |
|---------------------------|--------|
| 0 / 0 / 0 | 1 454 |
| 0 / 2 / 0 (R2 blockte, neu frei) | 16 |
| 0 / 2 / 2 | 39 |
| 2 / 2 / 2 | 63 |
| alt blockt, neu nicht | 0 |
| neu blockt, R2 nicht | 0 |

Zusatzblöcke gegenüber ALT: 39 (2,5 %; Runde 2: 55). Davon enthalten 30 Heredoc und Alias-Text, 7 Alias-Text ohne Heredoc, 2 sind `python3 - <<'EOF'`-Skripte (der Interpreter hält den Body sichtbar, Kommentar mit „git isn't“ bzw. „git directory“); keiner ist ohne Heredoc und ohne Alias- bzw. git-Syntax-Text. Der Tech-Lead-Lauf (`corpus_diff.py`) liefert dieselben Zahlen: {(0,0): 1470, (0,2): 39, (2,2): 63}. Weitere Korpora: 388 Doku- und Testbefehle → 0 Zusatzblöcke; 186 echte Commit- und PR-Nachrichten-Befehle → 0 (Runde 2: 2); 128 absichtlich stressende „typische“ Befehle → 10 (Runde 2: 18): Heredoc-Skripte mit `.sh` oder `python3` auf der Öffner-Zeile (4), `echo it's git time`, `ls ~/.gitconfig; echo git done`, `cd "$D" && echo git done` und drei `cd` auf ein offenes oder nicht vorhandenes Verzeichnis mit Nicht-Builtin (laut AC-3 gewollt). Alltäglich bleiben (a) Heredoc-Prosa in Skripten mit Interpreter-Opener und (b) `cd "$D" && echo git done`; die Häufigkeit in realen Korpora ist niedrig. Für sich allein wäre das kein BROKEN.

**Laufzeit** (Hook-Timeout 300 s laut `hooks/hooks.json`):

| Eingabe | neu | alt |
|---------|-----|-----|
| Korpus 1 572 Befehle, Median / p95 / Maximum | 0,094 / 0,181 / 0,29 s | 0,090 / 0,176 / 0,35 s |
| `git commit -m x # ` + 50 000 × `git ` (Runde 1: 368 s) | 1,45 s | 1,16 s |
| 50 000 × `git` ohne Commit (neu Exit 2, Arbeitsgrenze) | 1,96 s | 0,39 s |
| `git st;` × 20 000 (neu Exit 2) | 1,90 s | 0,42 s |
| 200 KB Prosa-Zeilen in einem Heredoc (neu gestrippt, Exit 0) | 1,57 s | 1,17 s |
| 20 000 verschachtelte `bash -c`, `eval`, `sudo -u x`, `find -exec` | 2,92 / 1,95 / 1,91 / 3,13 s | 2,90 / 1,86 / 1,78 / 2,63 s |
| `a = !git a; git a; …` × 100 | 0,08 s | 0,05 s |
| ein einzelnes Token ohne Leerzeichen, 100 / 200 / 400 KB | 2,8 / 9,8 / 37,4 s | 2,5 / 9,4 / 34,9 s (vorbestehend quadratisch im Lexer) |
| unbalancierte Anführungszeichen, 100 / 200 / 400 KB (naive Zerlegung, neu Exit 2) | 2,4 / 9,1 / 34,5 s | 0,7 / 2,4 / 8,7 s |

Der 50 000-Token-Fall liegt weiter deutlich unter 3 s, die Laufzeit wächst linear mit der Zahl der git-Token; die Nachbesserung ändert die Laufzeit nicht merklich (gegenüber Runde 2 gleiche Größenordnung in jeder Zeile). Beim unbalancierten Anführungszeichen bleibt der neue Pfad rund 4 × langsamer als der alte, beide sind quadratisch (500 KB: 53 s gegen 14 s); Befehle dieser Größe sind unrealistisch — kein Fund.

#### Nachweise ohne Fund (Runde 3)

- Alle Runde-1- und Runde-2-Reproduktionen laufen gegen den neuen Stand mit demselben Ergebnis wie in Runde 2, außer den geschlossenen F018–F024; unverändert Exit 0 sind nur die dokumentierten oder vorbestehenden Fälle: F015 (Parität alt = neu), die Reste von F017 (Glob-Ziel, `$(git rev-parse --git-dir)/config`, Skript ohne Pfadnennung), `su -c '…'`, `runuser -l -c '…'`, `script -c '…'` mit Befehlsstring (der wörtliche Commit läuft im alten Gate ebenso durch), `nsenter -w<dir>` (dokumentierte Rest-Grenze unbekannter Starter) und der unzerlegbare Befehl mit `git -c … commit` (Fail-open aus #1431).
- Modul-Docstring und CHANGELOG nennen die Rest-Grenzen jetzt ausdrücklich (`firejail --private-cwd=B git ci`, `mywrap git $(echo ci)`, Indirektion jenseits von `git config $K` und `export ${P}…=`, Heredoc-Prosa ohne Interpreter); `docs/WORKFLOW_GUIDE.md`, `CLAUDE.md` und `README.md` unverändert und stimmig. Die Zusage „Optionswerte und Operanden bekannter Starter sowie Umleitungen halten die Befehlsposition“ gilt für die Tabelle, nicht für A-Starter (F027).
- Vorbestehend, nicht #281 (ALT = R2 = NEU = Exit 0): dieselbe Öffner-Attrappe versteckt `touch .claude/user_approved_validation_x` vor Schritt 3a (`scan_cmd = strip_heredoc_bodies(command)`, `bash_gate.py:670`), die Marker-Datei entsteht (Abschnitt B, `r3_marker.out`). Gleiche Ursache wie F025 (`hook_utils.py:624`); ein Fix in `strip_heredoc_bodies` selbst würde 3a, 3b, 4 und den Resolver zugleich schließen. Als eigenes Issue melden.
- Die Tests der Datei enthalten keinen Fall für die Klassen F025–F029 (Öffner-Attrappen, argumentlose gestrichelte Zeile, A-Starter mit Optionswert, gebündeltes `-e`); die Wächter `adv-F024-bash-heredoc` und `adv-F024-sh-heredoc` prüfen nur Interpreter am Kopf.
- Bewusst nicht als Fund gewertet (Known Limitations bzw. Parität): `bash -lc` (#298), externe `git-<name>` (#297), Whitelist-Gefälle (#296), `source` einer Datei, Shell-Funktion `git`, Tiefe > 2, bedingtes `cd`, Unterbefehl aus stdin, unbekannte Starter mit Verzeichnis- oder Benutzerwechsel, ältere git-Versionen.

#### Checkliste: alle 27 Punkte (10 Expected Behavior und AC-1 bis AC-17)

Punkte mit einem offenen Fund stehen unten als `Result: DISPROVEN` mit Verweis auf das Finding; alle anderen als Confirmation.

Confirmation:
  AC: Expected Behavior 1 — Input (Befehl, cwd und Umgebung des Hooks, Workflow-State, Alias-Konfiguration am Ort des Aufrufs)
  Code reference: core/hooks/bash_gate.py:683
  Code reference: core/hooks/git_alias.py:278
  Evidence: `_alias_view(command)` läuft genau einmal nach dem Stop-Lock; der Resolver nimmt `os.getcwd()` und `os.environ` des Hooks und spielt `-C`, `cd`, `-c`, `--config-env`, `--git-dir`, `--work-tree` und freigegebene Präfix-Zuweisungen nach (`context`, ab Zeile 278). AC-3 gilt in allen vier Formen; Fuzz ctx (Seeds 6 und 7, 600 Fälle) 0 Bypässe; `CDPATH` mit gesplittetem Namen ist geschlossen (F021). Welcher TEXT des Befehls ausgewertet wird, steht unter Punkt 9 (F025).
  Status: CONFIRMED

Confirmation:
  AC: Expected Behavior 2 — Output (Exit 0 oder 2, Alias-Zeile auf stderr nur bei Erkennung über die Sicht, Block-Meldungen unverändert, `resolve_git_aliases` liefert eine `GitAliasView`)
  Code reference: core/hooks/bash_gate.py:767
  Code reference: core/hooks/git_alias.py:422
  Evidence: Hook-Fuzz 2 × 600: Exit nur 0 oder 2, kein Traceback. Die Zeile `Commit erkannt über Alias: …` kommt nur bei nicht wörtlichem Commit (`bash_gate.py:768–769`, `_alias_notice` Zeile 641); 5c- und 3a-Texte unverändert (AC-1, AC-6). `resolve_git_aliases` liefert immer eine `GitAliasView` und wirft nie (120 000 Fuzz-Eingaben, 0 Ausnahmen; Rückfall Zeilen 437–440).
  Status: CONFIRMED

Confirmation:
  AC: Expected Behavior 3 — Side effects (höchstens drei lesende Abfragen, nur für Nicht-Builtins, schreibt nichts, führt nie Code aus dem Befehlstext aus)
  Code reference: core/hooks/git_alias.py:321
  Code reference: core/hooks/git_alias.py:74
  Evidence: Heißer Pfad über 20 Aufrufformen: Builtins 0 Prozesse, `git st` genau eine Abfrage, vierter Kontext unresolved (Budget, AC-9). Die Abfrage `git config -z --get-regexp ^(alias\..*|help\.autocorrect)$` ist lesend; `GIT_TRACE2*=0` (Zeile 74, Anwendung Zeile 331) hält den Hook vom Schreiben ab (F012 bleibt geschlossen). 14 Varianten mit Code-Ausführungsversuch: kein Sentinel. AC-11: keine `GIT_TRACE`-Datei, `./git` nie ausgeführt. Die neuen Punkt-Namen kosten höchstens eine Abfrage je Kontext.
  Status: CONFIRMED

Confirmation:
  AC: Expected Behavior 4 — Builtins (nie nachgeschlagen, nie überschattet; Alias-Namen case-insensitiv, Builtin-Namen exakt)
  Code reference: core/hooks/git_alias.py:256
  Code reference: core/hooks/git_alias.py:346
  Evidence: `sub in GIT_BUILTINS` beendet den Aufruf ohne Abfrage (Zeile 256); die Kette sucht `"alias." + name.lower()` nur, solange der Name kein Builtin ist (Zeile 346). Zähler: 0 Prozesse für `git status`, `-C . status`, `--no-pager log`, `GIT_DIR=… status`, `env X=1 diff`, `add`, `stage`, `push`, `worktree`, `rev-parse`, `config`, Ketten. AC-4: `git CI` und `git STATUS` mit Alias blocken wie in git 2.43; AC-8: `alias.status=commit` wirkt für `git status` nicht.
  Status: CONFIRMED

Checklist point 5 — Expected Behavior „Unterbefehl“ (ein erst zur Laufzeit feststehender Unterbefehl, auch in Alias-Werten und Shell-Rümpfen, wird ohne Abfrage als unresolved geprüft)
  Result: DISPROVEN — Finding F027
  Code reference: core/hooks/git_alias.py:63
  Evidence: Hinter `sudo -u root`, `sudo -n -u root`, `runuser -u root --` sowie `timeout .5`/`1e1`/`infinity`, `ionice --class best-effort`, `stdbuf --output L`, `flock --wait 5 F`, `exec -a foo` und `&>/dev/null` wird `git $CMD` bzw. `git $(echo ci)` nicht geprüft (Exit 0, echte bash committet). Alle Formen der Runde 2 und AC-15 gelten wörtlich; an Kopf, hinter `timeout 5`, `timeout -s KILL 5`, `flock F`, `nice -n +5`, `>/dev/null` und `2>/dev/null` blockt der Laufzeitname.

Checklist point 6 — Expected Behavior „Alias auf commit“ (gilt wie commit: lokal, global, `include.path`, `-c`, `--config-env`, Umgebung, Ketten, Optionen im Alias-Wert; seine Argumente bestimmen die #259-Commit-Menge, begleitendes `add`/`stage` zählt auch über Alias und Rumpf)
  Result: DISPROVEN — Findings F025, F026, F027
  Code reference: core/hooks/git_alias.py:354
  Evidence: F026: `!git-commit -a -m`, `--all` und Pfadangaben im Rumpf zählen in Phase 7 nicht mehr zur Commit-Menge (Exit 0 statt 2; Runde 2 blockte). F025: die Alias-Form des Commits wird unsichtbar, sobald eine Öffner-Attrappe in einer Zeile davor steht. F027: `sudo -u root git a.b`. Alle in den ACs genannten Quellen a–h, Ketten, Optionen im Alias-Wert und die Commit-Menge über `commit -a`, `add`, `stage` und `!git commit …` gelten wörtlich.

Confirmation:
  AC: Expected Behavior 7 — Shell-Aliase (Rumpf wird auf Commit, Marker-Schreiben und Secrets geprüft)
  Code reference: core/hooks/bash_gate.py:705
  Code reference: core/hooks/git_alias.py:353
  Evidence: Die Rümpfe `!git commit`, `!git-commit` in 17 Schreibweisen (Quoting, `sh -c`, `eval`, absoluter Pfad, Heredoc im Rumpf, `xargs`, `sudo`, `env -i`) und `!touch …user_approved…` werden erkannt (Exit 2, Marker-Datei entsteht nicht); `!echo hi` und `!ls git-hooks` bleiben frei (AC-6, F019 geschlossen). Die Commit-MENGE aus dem Rumpf steht unter Punkt 6 (F026).
  Status: CONFIRMED

Checklist point 8 — Expected Behavior „Kontext“ (nachgespielter Kontext; Alias-Änderung im selben Befehl, im Befehl benannte oder geschriebene Konfigurationsdatei und unbestimmbarer Kontext machen spätere Nicht-Builtins unresolved)
  Result: DISPROVEN — Findings F025, F027, F029
  Code reference: core/hooks/git_alias.py:403
  Evidence: Zeilen, die eine Öffner-Attrappe versteckt, liefern dem Resolver weder `git config alias…` noch `cd`, `export` oder Quellen (F025); `cd "$D" && taskset 1 git a.b` ignoriert den offenen Kontext (F027 b); gebündeltes `git config -ze`, `--type path $K` und `env $N=$V` bleiben ohne Taint (F029). Die Formen der Spec und der Runde 2 gelten wörtlich (AC-3, AC-7 a–d); der reihenfolgeunabhängige Taint und das cd-Modell halten im Fuzz (taint und ctx, 1 200 Fälle, 0 Bypässe).

Checklist point 9 — Expected Behavior „Fehlerrichtung“ (was sich nicht sicher auflösen lässt, wird wie ein Commit geprüft; Wirkung nur, wo auch ein wörtlicher Commit geprüft würde)
  Result: DISPROVEN — Findings F025 und F027
  Code reference: core/hooks/bash_gate.py:638
  Evidence: Was `strip_heredoc_bodies` versteckt, wird weder aufgelöst noch als unresolved geführt: Fail-open statt Fail-safe, obwohl das wörtliche Gegenstück blockt (F025). Erwähnungen mit Laufzeit- oder Punkt-Namen hinter A-Startern erreichen `view.unresolved` nie (F027). Der Zweig `bash_gate.py:703–705` behandelt `view.unresolved` wie einen Commit; die Klausel „nur wo ein wörtlicher Commit geprüft würde“ gilt.

Confirmation:
  AC: Expected Behavior 10 — Invarianz (bei leerer Sicht verhält sich `bash_gate.py` wie zuvor, `_is_whitelisted` sieht keine Aliase)
  Code reference: core/hooks/bash_gate.py:629
  Code reference: core/hooks/bash_gate.py:218
  Evidence: 900 Läufe ALT gegen NEU (450 Befehlsketten, gesperrt und ohne Workflow): 0 Abweichungen. Auf dem Korpus von 1 572 Befehlen gibt es keinen Fall „alt blockt, neu nicht“. `_NO_VIEW` (Zeile 626) ist die leere Sicht, `_is_whitelisted` (Zeile 218) ist unverändert (AC-13).
  Status: CONFIRMED

Confirmation:
  AC: AC-1 — lokales `alias.ci=commit`, `git ci -m x` im gesperrten Zustand
  Code reference: core/hooks/bash_gate.py:703
  Code reference: tests/test_git_alias_commit_gate_281.py:303
  Evidence: acverify AC-1: Exit 2, stderr enthält „Adversary verdict missing or not VERIFIED“ und `git ci → git commit`. Die Reproduktion aus #281 steht im Wortlaut; F025 beschreibt Umgebungen, in denen sie durchrutscht (Öffner-Attrappe in einer Zeile davor).
  Status: CONFIRMED

Confirmation:
  AC: AC-2 — Alias-Quellen a–h
  Code reference: core/hooks/git_alias.py:278
  Code reference: tests/test_git_alias_commit_gate_281.py:343
  Evidence: acverify AC-2a–h alle bestanden (global, `include.path`, inline `-c`, `GIT_CONFIG_COUNT`/`KEY_0`/`VALUE_0`, `--config-env` mit Präfix, `env GIT_CONFIG_GLOBAL`, `GIT_CONFIG` ignoriert, letzter Wert gewinnt); die Quoting-Varianten von `--config-env` sind geschlossen (F020).
  Status: CONFIRMED

Confirmation:
  AC: AC-3 — Kontext nachspielen (`-C`, `cd`, `bash -c`, `cd "$X"`)
  Code reference: core/hooks/git_alias.py:385
  Code reference: tests/test_git_alias_commit_gate_281.py:424
  Evidence: acverify AC-3 in allen vier Formen Exit 2 (Alias nur in Repo B, cwd in A); `cd "$X"` macht den Unterbefehl unresolved; `CDPATH` mit gesplittetem Namen ist geschlossen (F021).
  Status: CONFIRMED

Confirmation:
  AC: AC-4 — Alias-Namen case-insensitiv, Builtin exakt
  Code reference: core/hooks/git_alias.py:346
  Code reference: tests/test_git_alias_commit_gate_281.py:453
  Evidence: acverify AC-4: `git CI -m x` mit `alias.ci=commit` und `git STATUS -m x` mit `alias.status=commit` Exit 2; entspricht echtem git 2.43.
  Status: CONFIRMED

Confirmation:
  AC: AC-5 — Kette, Optionen im Alias-Wert, Schleife
  Code reference: core/hooks/git_alias.py:342
  Code reference: tests/test_git_alias_commit_gate_281.py:484
  Evidence: acverify AC-5a–c: `alias.c2=ci` mit `alias.ci=commit`, `alias.cx="-c user.name=zz commit"` und die Schleife `l1=l2`, `l2=l1` je Exit 2; bei der Schleife nennt stderr Grund und Ausweg.
  Status: CONFIRMED

Confirmation:
  AC: AC-6 — Shell-Aliase (Commit im Rumpf, Marker, harmlos)
  Code reference: core/hooks/bash_gate.py:705
  Code reference: tests/test_git_alias_commit_gate_281.py:523
  Evidence: acverify AC-6: `!git commit` Exit 2; `!touch .claude/user_approved_validation_x` Exit 2 mit der Marker-Meldung aus 3a und ohne dass die Datei entsteht; `!echo hi` Exit 0. Die Quoting-Varianten des gestrichelten Builtins sind geschlossen (F019).
  Status: CONFIRMED

Confirmation:
  AC: AC-7 — Änderungen im selben Aufruf (Taint)
  Code reference: core/hooks/git_alias.py:398
  Code reference: tests/test_git_alias_commit_gate_281.py:599
  Evidence: acverify AC-7a, b, d Exit 2, AC-7c Exit 0 (`git config user.name y && git st`, kein Taint). Optionsabkürzungen (`--t`, `--te`, `--ed`) und `git config $K` sind geschlossen (F022, F023); Rest F029.
  Status: CONFIRMED

Confirmation:
  AC: AC-8 — harmlose Aliase und Builtin-Schatten
  Code reference: core/hooks/git_alias.py:256
  Code reference: tests/test_git_alias_commit_gate_281.py:625
  Evidence: acverify AC-8: `git st`, `git lg`, `git status` (mit `alias.status=commit`) alle Exit 0; die Erwähnungs-Wächter `grep -rn git core/`, `echo git is great`, `cd "$D" && grep git README.md` bleiben frei.
  Status: CONFIRMED

Confirmation:
  AC: AC-9 — Builtins kosten keine Abfrage, Cache und Budget
  Code reference: core/hooks/git_alias.py:321
  Code reference: tests/test_git_alias_commit_gate_281.py:635
  Evidence: acverify AC-9: vier Builtin-Befehle null Abfragen; `git st && git lg` genau eine; der vierte Kontext ist unresolved (Budget drei). Arbeitsgrenze: `tests/test_git_alias_commit_gate_281.py:866`.
  Status: CONFIRMED

Confirmation:
  AC: AC-10 — Abfrage scheitert (rc 128)
  Code reference: core/hooks/git_alias.py:331
  Code reference: tests/test_git_alias_commit_gate_281.py:677
  Evidence: acverify AC-10: `git st` gesperrt Exit 2 mit „nicht auflösbar“ und Ausweg, `git status` Exit 0 (Builtin, keine Abfrage), `git st` ohne aktiven Workflow Exit 0.
  Status: CONFIRMED

Confirmation:
  AC: AC-11 — Abfrage führt nie fremden Code aus
  Code reference: core/hooks/git_alias.py:329
  Code reference: tests/test_git_alias_commit_gate_281.py:707
  Evidence: acverify AC-11: `GIT_TRACE=<pfad> git -c alias.ci=commit ci` und `./git ci` Exit 2; die Datei unter `<pfad>` entsteht nicht, das Sentinel des `./git` nicht; der Runner bekommt weder `GIT_TRACE*` noch `GIT_CONFIG`. Dazu 14 Code-Ausführungsversuche ohne Sentinel.
  Status: CONFIRMED

Confirmation:
  AC: AC-12 — #259-Commit-Menge folgt den Alias-Argumenten
  Code reference: core/hooks/bash_gate.py:492
  Code reference: tests/test_git_alias_commit_gate_281.py:750
  Evidence: acverify AC-12: Phase 7, VERIFIED, Dialog zitiert nur B: `git ci` Exit 0 (Index-Form), `git cam msg` (`commit -a -m`) Exit 2 mit C in stderr, `git a NEU.py && git ci` und `git s NEU.py && git ci` Exit 2 mit NEU.py. Unzerlegbarer Rumpf → größte Menge (`bash_gate.py:505`). Die Variante mit gestrichelter Form im Rumpf steht unter F026.
  Status: CONFIRMED

Confirmation:
  AC: AC-13 — Whitelist ruft den Resolver nie auf
  Code reference: core/hooks/bash_gate.py:218
  Code reference: tests/test_git_alias_commit_gate_281.py:769
  Evidence: acverify AC-13: `_is_whitelisted("git ci -m x")` mit einem auf eine werfende Funktion gepatchten Resolver liefert False ohne Fehler; die Whitelist wertet nur den Originaltext.
  Status: CONFIRMED

Confirmation:
  AC: AC-14 — Resolver-Ausnahme und fehlende Hilfsdatei
  Code reference: core/hooks/git_alias.py:437
  Code reference: core/hooks/bash_gate.py:633
  Evidence: acverify AC-14: (a) Ausnahme im Resolver → Sicht unresolved, wenn ein Nicht-Builtin gesehen wurde, sonst leer (Rückfall Zeilen 437–440); (b) Hook-Kopie ohne `git_alias.py`: `git st` Exit 0 wie bisher, stderr-Hinweis auf die fehlende Datei (`bash_gate.py:633–637`).
  Status: CONFIRMED

Confirmation:
  AC: AC-15 — nicht bestimmbarer Unterbefehl (unzerlegbar oder Laufzeitname)
  Code reference: core/hooks/git_alias.py:228
  Code reference: tests/test_git_alias_commit_gate_281.py:853
  Evidence: acverify AC-15: `git ci -m $'it\'s'` Exit 2, `git status $'it\'s'` Exit 0, `CMD=commit; git $CMD -m x` Exit 2; 18 Varianten der naiven Zerlegung alle Exit 2. Laufzeitnamen hinter A-Startern und exotischen Optionen stehen unter F027.
  Status: CONFIRMED

Confirmation:
  AC: AC-16 — Doku-Anker
  Code reference: docs/WORKFLOW_GUIDE.md:213
  Code reference: CLAUDE.md:56
  Code reference: README.md:382
  Code reference: CHANGELOG.md:77
  Evidence: Die Fast-Path-Zeile der `bash_gate.py`-Übersicht nennt die Alias-Auflösung (WORKFLOW_GUIDE Zeilen 213–214); `CLAUDE.md` (Baum Zeile 56, „Wichtige Dateien“ Zeile 441) und `README.md` (Baum Zeile 382) führen `git_alias.py` als Hilfsmodul ohne Hook; `CHANGELOG.md` nennt unter `[Unreleased]` #281, die neuen Block-Fälle samt Rest-Grenzen und den Nebeneffekt von `git stage`. Doku-Tests der Datei grün (`pytest -k`: 5 passed).
  Status: CONFIRMED

Confirmation:
  AC: AC-17 — GIT_BUILTINS gegen die installierte git-Version
  Code reference: core/hooks/git_alias.py:31
  Code reference: tests/test_git_alias_commit_gate_281.py:907
  Evidence: git 2.43.0 installiert: `git --list-cmds=builtins` und `GIT_BUILTINS` sind identisch (140 = 140), der Test fordert nur die Teilmenge.
  Status: CONFIRMED

#### Hinweise an den Tech Lead (nicht verdict-relevant)

- Die Remediation-Prototypen liegen in Scratch-Kopien unter `/tmp/claude-0/-home-user-agent-os-openspec/76054b3f-0401-5941-9b95-6f771556ea2e/scratchpad/adv/fix4*` (Repo unberührt). Alle drei Patches zusammen halten die 283 Tests der Datei grün, ändern die Über-Erkennung auf dem Korpus nicht (1 572 Befehle: 39 Zusatzblöcke wie im Repo; 128 „typische“: 10) und schließen im Heredoc-Fuzz alle 250 Läufe (neuer Stand: 35 Bypässe): F025 (quote-, kommentar- und arithmetikbewusste Heredoc-Sicht, nur zitierter Begrenzer, Interpreter-/eval-/source-Wort auf der Öffner-Zeile hält den Body sichtbar, Terminator muss existieren), F026 (angehängte Zeile mit den Argumenten des Segments) und F027 (A-Starter und Optionsschreibweisen in `_OPTVAL`, `_ARG` für `.5`, `1e1`, `0x5`, `infinity`). Sie sind Hinweise, keine Vorgabe (Belege: Abschnitt J).
- Die Ursache von F025 ist, dass `strip_heredoc_bodies` für Daten-Scans gebaut wurde (Schritte 3a, 3b, 4) und dort Fehlurteile in Kauf nimmt, während der Resolver ein Fail-safe-Gate ist. Wenn der Resolver wieder den vollen Text sieht, kehren die Prosa-Falschblöcke zurück (Korpus 55 statt 39 Zusatzblöcke, Runde-2-Stand).
- Nach CLAUDE.md gilt bei BROKEN: gezielter Fix, höchstens eine weitere Adversary-Runde; ein zweites BROKEN eskaliert an den User. Der PO hat nach Runde 2 bereits ein BROKEN gehört; mit F025 liegt ein neuer, kleiner und erprobt behebbarer Befund vor, der den Stand seit Runde 2 verschlechtert (Runde 2: 0 Bypässe dieser Klasse).

#### Abschluss Runde 3

Die Nachbesserung schließt F019, F020, F021, F023 (bis auf dokumentierte Reste) und F024 und lässt Reste bei F018 und F022 (F027, F029). Sie öffnet aber mit der Heredoc-Sicht für den Resolver einen neuen, undokumentierten Bypass der #281-Reproduktion (F025, HIGH): Eine Öffner-Attrappe wie `echo '<<X'` oder `echo $((1<<N))` in einer Zeile davor versteckt jeden Alias-Commit der Folgezeilen; das wörtliche `commit` blockt, die echte bash committet, der Runde-2-Stand blockte. Dazu die Regression F026 (Phase 7 zählt `-a`, `--all` und Pfade in `!git-commit …` nicht mehr) und F027 (`sudo -u root git $CMD`, Punkt-Namen hinter A-Startern). Alle 17 ACs gelten in ihrem Wortlaut; vier Expected-Behavior-Punkte (5, 6, 8 und 9) sind widerlegt. Die Behebung ist klein und im Scratch erprobt. Die Sektion „Herkunft der Vorbedingungen“ steht unverändert weiter oben im Protokoll (vor diesem Verdict).

═══════════════════════════════════════
VERDICT: BROKEN
═══════════════════════════════════════
Findings: F025 (HIGH), F026, F027 (MEDIUM), F028, F029 (LOW)
Tests: 283 passed in der Datei, 1842 passed und 28 skipped in der vollen Suite, 0 failed
Checklist: 23/27 Punkte bewiesen (4 Expected-Behavior-Punkte widerlegt: F025–F027, F029)

## Geprüfte Dateien

- sha256:7e1f7b67b2d69cca79992632288699b77028206468959fda41489041d6e84868  CHANGELOG.md
- sha256:8a50d46875ad8c3dbddf0fc39c1c6f0305d275fdfa924a6ef2e8dc8f1f9b52a7  CLAUDE.md
- sha256:5621e3de0bb3ddb848dec73c38b822fb167c08c560d729de4a63358de53d7f4d  README.md
- sha256:1fa9b98d686ae8d7f67ae8516bd2be8f58544bcc4d5f39dd4b09b1bae8e7ba3b  core/hooks/bash_gate.py
- sha256:8dcd654537c226426ab1370d165a7a6b957122040aabfa34d410d76c636304dd  core/hooks/git_alias.py
- sha256:fe55f687b30bb6a563808b8b6d870713c083fddde274848146813621b03d802b  core/hooks/hook_utils.py
- sha256:c6e5dd899186ddd39ae1f910c976584774431647e5f44e678bcd90d3c5661905  docs/WORKFLOW_GUIDE.md
- sha256:5467130211415dca3de199fb58d31f51ecb83c4a4c089e927514ecb53fa8be95  tests/test_git_alias_commit_gate_281.py
