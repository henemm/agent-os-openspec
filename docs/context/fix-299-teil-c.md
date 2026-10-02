# Context: fix-299-teil-c

## Request Summary

Rest von Sammel-Issue #299 (Epic #200) nach Teil A (PR #320) und Teil B (PR #321). Offen laut
Issue-Kommentar „Weiter offen": zwei vorbestehende Umgehungen der State-Integrity-Prüfung (3b, aus
#316), die Kommentar-Apostroph-Lücke (#319), ein Prüfauftrag zu Aliasen aus
`GIT_CONFIG_PARAMETERS`/`--config-env`, und die Option „CI-Gate für gestempelten Adversary-Nachweis"
(bewerten, nicht zwingend bauen). #316 und #319 sind als Issues geschlossen (in #299 zusammengeführt),
ihre Befunde leben nur im #299-Kommentar „Randfälle aus der Adversary-Prüfung von Teil A".

Vorarbeit: `docs/context/fix-299-bash-gate-erkennung.md` (Teil A/B, Bedrohungsmodell, Alternativen).
Bedrohungsmodell unverändert: versehentliches Umgehen verhindern; vorsätzliche Verschleierung ist
Known Limitation, Backstop ist der Phase-8-Übergang.

## Related Files

| File | Relevance |
|------|-----------|
| `core/hooks/bash_gate.py` (847 Z.) | `main()` 3a Marker-Schutz (Z. 723), 3b State-Integrity (Z. 737–739), `_protected_outside_whitelist` (Z. 242), `_references_protected`/`_matches_file_token` (Z. 259/356), `_has_real_redirect` (Z. 314), `PROTECTED_FILE_PATTERNS` (Z. 55), `WRITE_INDICATORS` (Z. 99) |
| `core/hooks/hook_utils.py` | `_git_lex` (Z. 312, `commenters = ""` → Apostroph im `#`-Kommentar lässt den Lexer scheitern, `None`), `_git_segments` (Z. 394), `_is_git_separator`, `strip_heredoc_bodies` (Z. 806), `_repo_aliases`/`_inline_aliases`/`_resolve_alias` (Z. 98–153, Teil B), `_GIT_OPTS_WITH_VALUE` (enthält `--config-env`) |
| `tests/test_bash_gate_erkennung_299.py`, `…_teil_b.py` | Sandbox-Muster (Subprozess gegen echtes Gate, Wegwerf-Repo, Workflow phase6), Vorlage für Teil-C-Tests |
| `tests/test_bash_gate_false_positives.py`, `…freetext_fixes_64_75.py` | Regressionsschutz gegen Über-Erkennung |
| `scripts/ci_spec_gate.py`, `.github/workflows/spec-gate.yml` | Vorbild für die CI-Gate-Option |
| `core/hooks/adversary_dialog.py` | `check_dialog_evidence`, Hash-Block — Grundlage eines CI-Nachweises |

## Die Restfälle (laut #299-Kommentar, vor Analyse noch NICHT am Gate nachgestellt)

| Fall | Beobachtung laut Issue | Stelle im Code |
|------|------------------------|----------------|
| `cd .claude/workflows && echo x > <wf>.json` | Exit 0 | `PROTECTED_FILE_PATTERNS` verlangt Ordner + `.json` in einem Token; nach `cd` steht nur `<wf>.json` |
| `git status > <state>`, `workflow.py status > <state>`, `git status > <marker>` | Exit 0 | Pfad steht im whitelisted Segment → `_protected_outside_whitelist` zählt ihn nicht; Umleitungsziel wird nicht gesondert geprüft |
| `git status && sed -i … <state> # don't` | Exit 0 (mit `# dont` Exit 2) | `_git_lex` scheitert am Apostroph im Kommentar → `_git_segments` = None → Teilstring-Rückfall `_is_whitelisted` „irgendein Treffer" |
| Alias aus `GIT_CONFIG_PARAMETERS` / `--config-env=alias.x=VAR` | nicht geprüft | `_inline_aliases` kennt nur `-c alias.…`; `--config-env` steht in `_GIT_OPTS_WITH_VALUE` (wird übersprungen, nicht ausgewertet) |
| CI-Gate Adversary-Nachweis | Option | `ci_spec_gate.py` prüft nur committete Dateien; `adversary-dialog.md` liegt unter `docs/artifacts/…` |

## Existing Patterns

- Tier-2-Marker-Schutz (3a): `cd .claude && touch user_approved_…` wird pfadunabhängig geblockt —
  Vorbild für „cd in geschützten Ordner macht den Rest geschützt".
- Zerlegung per `shlex` mit `punctuation_chars`; nicht zerlegbar ⇒ konservativer/fail-open Rückfall
  (Drei-Fälle-Regel).
- Tests als Subprozess gegen das echte Gate (beide Fehlerrichtungen: Umgehung blockt, Fehlalarm nicht).
- Kein Modell: alles deterministische Token-/Regelarbeit.

## Dependencies

- Upstream: `hook_utils` (Lexer, Segmente), `config_loader`.
- Downstream: jedes Konsumenten-Projekt (jeder Bash-Aufruf passiert das Gate; Über-Blockierung
  stoppt Arbeit, Unter-Blockierung öffnet #253/#259).

## Existing Specs

- `docs/specs/fix-299-bash-gate-erkennung.md` (Teil A), Teil B lief ohne Spec (`Spec-Gate: skip`).
- `docs/specs/fix-253-…`, `fix-259-…` (Adversary-Nachweis, Abdeckung) — Grundlage der CI-Option.

## Risks & Considerations

- Kommentare abtrennen ist selbst eine Shell-Parsing-Aufgabe: `#` in Quotes, `$#`, `${#x}`,
  `git log --grep=#1431`, `a#b` sind KEINE Kommentare. Zu weit gefasst → Fehlalarme oder neue Umgehung
  (Kommentar-Attrappe, vgl. F025 Heredoc-Attrappe aus PR #291).
- Umleitungsziel-Prüfung im whitelisted Segment: `git log > out.txt` muss weiter erlaubt bleiben,
  nur geschützte Ziele blocken.
- `cd`-Regel: `cd .claude/workflows` allein ist harmlos; blockieren soll erst Schreib-Indikator danach.
- Zugriff auf Config aus Worktree: Kill-Switches nicht setzbar (Memory `worktree-config-erreicht-main-repo-nicht`).
- Scoping ±250 LoC / 4–5 Dateien: Posten 1–3 voraussichtlich ~80–150 LoC Prod + Tests; CI-Gate (Posten 4)
  würde allein ein neues Script + Workflow-Datei + setup.py-Anbindung bedeuten → eigenes Issue.
- `core/hooks/` ist Infrastruktur; mit laufendem Workflow ab phase6 entfällt der Override (#322).
- Workflow-Artefakte (Spec, Kontext, Briefing) zählen im LoC-Gate als Code (Memory
  `loc-gate-zaehlt-workflow-docs-als-code`, #294).

## Offene Punkte für /20-analyse

1. Alle Restfälle am echten Gate nachstellen (Reproduktion vor Ursache), inkl. Kontrollfälle.
2. Recherche vor Analyse: Bash-Kommentar-Grammatik (wann beginnt ein Kommentar), `GIT_CONFIG_PARAMETERS`
   und `--config-env` laut git-Doku.
3. Alternative bewerten: Zustand statt Text prüfen (State-Dateien per Hash/mtime vor/nach dem Befehl
   vergleichen im PostToolUse) — würde #316 als Klasse schließen; CI-Gate für Adversary-Nachweis.
4. Entscheidung, was als eigenes Issue ausgegliedert wird (CI-Gate).

## Analysis

### Type
Bugfix (Sammel-Issue #299, Teil C) — Erkennungslücken in `bash_gate`, alle vorbestehend.

### Recherche (vor Reproduktion)
- Bash-Handbuch, Comments: `#` beginnt nur am **Wortanfang** (nicht in Quotes, nicht in `a#b`, `$#`, `${#x}`) einen Kommentar bis Zeilenende. https://www.gnu.org/software/bash/manual/html_node/Comments.html
- git: `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n` sind offizielle Umgebungsvariablen (git ≥ 2.31); `GIT_CONFIG_PARAMETERS` ist interner Mechanismus (`-c` setzt ihn). https://lore.kernel.org/all/X9NzE5+LNYqG1s+o@ncase/T/

### Reproduktion am echten Gate (Wegwerf-Repo, Workflow phase6) — 21 Fälle
| Fall | Ist | Soll |
|------|-----|------|
| `cd .claude/workflows && echo x > <wf>.json` (auch `sed -i`, `python -c open(..)`) | 0 | 2 |
| `git status > <state>`, `workflow.py status > <state>`, `git status > <marker>` | 0 | 2 |
| `git status && sed -i … <state> # don't` | 0 | 2 (mit `# dont`: 2) |
| `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci … git ci -m x` | 0 | 2 |
| `export GIT_CONFIG_COUNT=…; git ci`, `GIT_CONFIG_PARAMETERS="'alias.ci=commit'" git ci`, `X=commit git --config-env=alias.ci=X ci` | 0 | 2 |
| Kontrollen: `cd .claude/workflows`, `cd … && ls`, `git log > out.txt`, `git status 2>&1`, `git status \| tee out.txt`, `git status # don't panic`, `git log --grep='#1431'`, `echo "it's" > out.txt` | 0 | 0 (ok) |

Zusatz (git selbst geprüft): Aliase aus allen drei Env-Wegen wirken wirklich (`git ci` committet), und `git config --get-regexp ^alias\.` **sieht** sie — aber nur, wenn die Variable im Prozess des Gates steht. Zuweisung *im Befehl* (`VAR=… git`, `export`, `--config-env`) erreicht die Teil-B-Abfrage nie.

### Ursachen (Code-Stellen)
1. **cd + relativer Name:** `PROTECTED_FILE_PATTERNS` verlangt Ordner + `.json` in einem Token; nach `cd` steht nur `<wf>.json` (bash_gate.py:55, `_references_protected` Z. 259).
2. **Umleitungsziel im whitelisted Segment:** `_protected_outside_whitelist` (Z. 242) zählt nur nicht-whitelisted Segmente; das Ziel einer Umleitung im whitelisted Segment wird nie gesondert geprüft.
3. **Kommentar-Apostroph:** `_git_lex` (hook_utils.py:312) setzt `commenters = ""`; der Apostroph im Kommentar lässt den Lexer scheitern → `_git_segments` = None → Teilstring-Rückfall `_is_whitelisted` „irgendein Treffer“ (bash_gate.py:228).
4. **Env-Aliase:** `_inline_aliases` (hook_utils.py:121) kennt nur `-c alias.…`; `--config-env` steht in `_GIT_OPTS_WITH_VALUE` (übersprungen, nicht ausgewertet); `VAR=…`-Präfix und `export` werden nicht gelesen.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | `_strip_shell_comments` (wortanfangs-`#`, quote-bewusst, bei Unklarheit unverändert) vor `_git_lex` |
| core/hooks/bash_gate.py | MODIFY | (1) cd-Kontext, (2) Umleitungsziele aller Segmente gegen Schutzmuster |
| tests/test_bash_gate_erkennung_299_teil_c.py | CREATE | Subprozess-Tests gegen echtes Gate, beide Fehlerrichtungen (Tabelle oben) |
| CHANGELOG.md | MODIFY | [Unreleased] |

### Scope Assessment
- Posten 1–3: 4 Dateien, ca. +90 LoC Produktion, +110 Tests (≈200, im Limit; Spec/Kontext zählen laut #294 zusätzlich).
- Posten 4 (Env-Aliase) würde auf ≈ +330 LoC reißen → eigenes Issue (siehe unten).
- Risk Level: MITTEL — `_git_lex` wird von allen Gate-Prüfungen genutzt; Kommentar-Abtrennung ist selbst Shell-Parsing (Fehlalarm- und Attrappen-Risiko, vgl. F025).

### Technical Approach (Regeln, kein Modell — „Ohne Modell geht es nicht, weil …“ entfällt: alles ist Token-/Regelarbeit)
1. Kommentare: eigener kleiner Scanner, `#` zählt nur außerhalb von Quotes/Escapes und direkt nach Zeilenanfang, Leerraum oder `; & | ( )`. Bei unausgewogenen Quotes bleibt der Befehl unverändert (fail-open wie heute). Zeilenumbruch beendet den Kommentar.
2. Umleitungsziele: im Lexer-Token-Strom folgt auf einen Umleitungsoperator mit `>` das Ziel-Token; passt es auf Schutzmuster (State/Marker), blockt 3b — unabhängig davon, ob das Segment whitelisted ist. `git log > out.txt` bleibt frei.
3. cd-Kontext: `cd`/`pushd` auf ein Ziel, das eine `.claude`-Komponente enthält, macht jede **spätere** `.json`-Referenz mit Schreib-Indikator im selben Befehl zur geschützten Referenz (Roh-Scan, damit auch `python -c "open('x.json','w')"` fällt). `cd` allein bleibt harmlos.

### Alternativen (Pflicht)
- **A: Zustand statt Text prüfen** (State-Dateien vor/nach dem Befehl hashen, PostToolUse): würde #316 als Klasse schließen. Verworfen für jetzt: `workflow.py phase` ändert den State legitim; eine Unterscheidung „legitim/Umgehung“ braucht einen Beglaubigungsweg (z. B. Signatur) = neues Design, ≫ 250 LoC. Hätte zudem nur Erkennung nach der Tat. Bedrohungsmodell bleibt „versehentlich“; 3b-Fälle sind ohnehin konstruiert. Gekippt würde: ADR „Gate prüft Befehlstext“.
- **B: Die vier Lücken als Known Limitation dokumentieren** (kein Code). Vertretbar für 3b (Absicht nötig), schwächer für #319 (`don't` im Kommentar ist **unabsichtlich** realistisch und hebt dann die ganze Whitelist-Prüfung auf) → Kommentar-Fix wird gebaut, 3b-Härtung ist günstig mitgenommen.
- **C: Rückfall `_is_whitelisted` bei unzerlegbarem Befehl auf „nicht whitelisted“ drehen** (statt Kommentare zu parsen): einfacher, aber Fehlalarm bei jedem harmlosen unbalancierten Befehl → Drei-Fälle-Regel (fail-open) verletzt. Verworfen.
- **Env-Aliase:** Alternative zur Befehlsanalyse: `VAR=…`-Präfix/`export`/`--config-env` mit `alias.*`-Schlüssel schlicht als „unaufgelöster Alias“ behandeln (Unterbefehl = Aliasname ⇒ Commit-verdächtig). Klein, aber eigene Entscheidung.
- **CI-Gate für Adversary-Nachweis:** Bewertung — sinnvoll, weil es genau „Zustand statt Text“ ist und der einzige Schutz, der lokale Hook-Umgehung überlebt (Spec-Gate beweist das Muster). Kosten: neues Script (Dialog-Artefakt + `## Geprüfte Dateien`-Hash-Block gegen PR-Dateien prüfen, Funktionen aus `adversary_dialog` wiederverwenden), Workflow-Datei, setup.py-Anbindung, `Adversary-Gate: skip`-Trailer für Teil-A/B-artige PO-Ausnahmen. Das ist ein eigenes Feature, nicht Teil C.

### Dependencies
`hook_utils._git_lex` ← `bash_gate` (3a/3b/Commit-Gate), `git_subcommands`, `git_head_subcommands`; Änderung an der Kommentar-Behandlung wirkt auf alle. Regressionsschutz: `tests/test_bash_gate_false_positives.py`, `…freetext_fixes_64_75.py`, Teil-A/B-Tests.

### Open Questions
- [ ] PO: Aufteilung wie oben (C = Posten 1–3; Env-Aliase und CI-Gate je eigenes Issue) bestätigen — Empfehlung: ja.
