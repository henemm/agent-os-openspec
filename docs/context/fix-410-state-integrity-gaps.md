# Context: fix-410-state-integrity-gaps

## Request Summary
Issue #410 (inkl. Kommentar „Teil 4“): Weitere Bash-Schreibweisen, mit denen Prüfung 3b in
`core/hooks/bash_gate.py` geschützten Zustand nicht erkennt, schließen. Gemeinsames Ziel: kein Weg
per Bash an geschütztem Zustand vorbei, ohne dass 3b blockt.

## Getroffene Richtungsentscheidungen (Tech Lead, 2026-10-09)
Henning (PO): „Handle als mein Tech Lead der nach Best Practise Regeln entscheidet.“ Damit gilt:

| Teil | Entscheidung | Begründung |
|------|--------------|------------|
| 1 Glob ohne `.json` | schließen | versehentlich auslösbar (`cp .claude/workflows/fix* …`) |
| 2 Config-Datei | **sperren**, Freigabe per „override“ | Ein Prüfer, den der Geprüfte selbst abschalten kann, ist keiner (gleiches Prinzip wie Workflow-State) |
| 3 Prüfung an der Quelle | **bauen, eigenes Ticket** mit Leser-Liste | CERT POS01-C; ≥8 Dateien, sprengt Scoping-Limit |
| 4/F001 `/.`, `/..` | schließen | versehentlich auslösbar |
| 4/F003 Ordner-Verweis nach `cd .claude` | schließen | versehentlich auslösbar |
| 4/F002 `.claude//workflows` | schließen (billig: `/+`) | |
| 4/F004 Ordner/Verweis in getrennten Segmenten, xargs/find/tar | Known Limitation, verweist auf Teil-3-Ticket | Kehrseite der Fehlalarm-Vermeidung |

Die Analyse prüft diese Richtung mit Daten (Alternativen siehe Risiken) und darf sie begründet kippen.

## Reproduktion (2026-10-09, echter Gate-Subprozess, aktiver Workflow, Stand `bc6784a` = origin/main)
Sanity: `cp docs/a.json .claude/workflows/b.json` → Exit 2. Alle folgenden → **Exit 0** (Lücke):
```
cp|ln|mv .claude/workflows/fix* docs/x/          # Teil 1
echo x > .claude/config.yaml                     # Teil 2
echo x > config.yaml ; sed -i s/a/b/ config.yaml ; sed -i s/a/b/ openspec.yaml   # Teil 2 (echte Orte!)
cp -r docs/w/. .claude/workflows/. ; rsync -a docs/w/ .claude/workflows/.         # F001
cd .claude && ln -s workflows ../w ; pushd .claude; ln -s workflows ../w         # F003
ln -s .claude//workflows d                       # F002
ls .claude/workflows | xargs ln -s               # F004
```
Gegenproben (müssen frei bleiben, sind frei): `ls .claude/workflows/fix*`, `cat config.yaml`,
`grep enabled config.yaml`, `ls .claude && rm docs/x`.
Probe-Skript: Scratchpad `probe.py` (Liste oben ist vollständig, Skript ist wegwerfbar).

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/bash_gate.py` | Prüfung 3b (~Z. 980–992); `PROTECTED_FILE_PATTERNS` (Z. 56), `PROTECTED_DIR_TOKEN_PATTERNS` (Z. 69), `_LINK_COMMAND_RE` (Z. 76), `_writes_state_dir` (Z. 280), `_redirects_to_protected` (Z. 296), `_cd_into_claude` / `_cd_context_protected` (Z. 322–354), `_has_write_indicator` (Z. 443), `_matches_file_token` (Z. 456) |
| `core/hooks/config_loader.py` | Wo die Config wirklich liegt: `CONFIG_NAMES = openspec.yaml, config.yaml, .openspec.yaml`, je im Root oder unter `.claude/`; `find_config_file(root)` (öffentlich) liefert die tatsächlich geladene Datei. Root-`config.yaml` ohne Plugin-Block gehört der App und wird übergangen (#372) |
| `core/hooks/edit_gate.py` | Edit/Write-Schutz: `PROTECTED_STATE_FILES` (Z. 44), `ORCHESTRATOR_FILES` mit Override-Freigabe (Z. 48, 554–566). Config-Datei ist dort **auch nicht** geschützt |
| `core/hooks/override_token.py` | `has_valid_token(name)`; bash_gate nutzt es bereits in `_any_override_token()` (Z. 882) für das Dependency-Gate |
| `core/hooks/qa_gate.py` | Z. 544: Vorbild „Prüfung an der Quelle“ (`S_ISREG`, `st_nlink == 1`) für Teil 3 |
| `tests/test_bash_gate_ln_state_407.py` | Testmuster aus #407 (echter Subprozess, beide Fehlerrichtungen) — Vorlage für neue Tests |
| `tests/test_bash_gate_false_positives.py`, `test_bash_gate_erkennung_299*.py`, `test_gate_fixes_26_38_34.py`, `test_secret_egress_*` u. a. | Regressionsnetz gegen Fehlalarme; alle müssen grün bleiben |
| `docs/specs/fix-407-ln-state-integrity.md`, `docs/artifacts/fix-407-ln-state-integrity/adversary-dialog.md` | Vorgänger-Spec und Befunde F001–F004 |
| `setup.py` Z. 813–840 | Konsumenten bekommen `openspec.yaml` im Root |

## Existing Patterns
- 3b blockt nur bei `workflow_enforced`; Verweis-Befehle und Ordner-Token nur bei aktivem Workflow (#407 AC-9).
- Pfad-Erkennung über Datei-Token (`_matches_file_token`), Freitext-Flags (`-m`, `--body`) ausgenommen (#53/#64); bei `sh -c`/`eval`/Parse-Fehler Roh-Scan.
- Lesen bleibt frei, gesperrt wird nur Pfad-Token **und** Schreib-/Verweis-Indikator im selben Segment.
- Override-Freigabe existiert im edit_gate für Orchestrator-Dateien und im bash_gate fürs Dependency-Gate — **nicht** in 3b (3b ist heute ohne Ausweg, Begründung: State nur über `workflow.py`).

## Dependencies
- Upstream: `hook_utils` (Freitext-Flags, aktiver Workflow), `config_loader`, `override_token`, `shlex`.
- Downstream: jeder Bash-Aufruf in jedem Konsumenten-Projekt (Plugin- und Copy-Modus).

## Existing Specs
- `docs/specs/fix-407-ln-state-integrity.md` — direkt vorausgehend.
- `docs/specs/bash-gate-false-positive-fix.md` — Fehlalarm-Grenzen.

## Risks & Considerations
- **Teil 2 ist nicht „`.claude/config.yaml`“:** die echte Datei heißt je Projekt anders (`openspec.yaml` im Root bei Konsumenten, `config.yaml` im Root hier im Framework-Repo, oder unter `.claude/`). Ein Namensmuster `config.yaml` träfe App-Configs (#372). Kandidat: die von `find_config_file()` aufgelöste Datei schützen (plus die `.claude/`-Varianten).
- **Teil 2 braucht einen Ausweg:** 3b kennt kein Override. Sperre ohne Freigabe würde legitime Kill-Switch-Änderungen auf Wunsch des PO unmöglich machen. Kandidat: wie Dependency-Gate/edit_gate `override` akzeptieren — nur für die Config, nicht für den State.
- **Teil 2, Edit-Weg:** Edit/Write auf die Config ist heute ebenfalls frei. Nur Bash zu sperren wäre halb; ob edit_gate mitgezogen wird, entscheidet die Analyse (Scoping: dann 4 Dateien inkl. Tests).
- **Framework-Repo selbst:** Root-`config.yaml` ist hier Vorlage *und* Live-Config; Template-Pflege würde künftig „override“ brauchen. In Worktree-Sitzungen löst die Config auf den Hauptordner auf; die Worktree-Kopie ist eine normale versionierte Datei (Memory „Worktree-Config erreicht Main-Repo nicht“).
- **Fehlalarme:** Glob-Erkennung darf `ls`/`cat`/`grep` auf `.claude/workflows/*` nicht treffen; `cat config.yaml` muss frei bleiben.
- **Alternative zu Teil 2:** Config offen lassen und Kill-Switch-Nutzung nur protokollieren (gate-events.jsonl) — schwächer, aber ohne Reibung für den PO.
- Scoping-Limit (4–5 Dateien, ±250 LoC) — bei Teil 2 mit Edit-Weg knapp.

## Analysis

### Type
Bug (Lücken in Prüfung 3b und im Schutz der wirksamen Gate-Konfiguration)

### Recherche (2026-10-09)
- Sperrlisten auf Shell-Befehlstext gelten als grundsätzlich umgehbar: CVE-2024-6091 (AutoGPT, `/bin/./whoami` umgeht Sperrliste — exakt die Klasse von F001), CVE-2026-32973 (Glob-Normalisierung), Studien Juni 2026: 69–98 % realer Sperrlisten lückenhaft. Quellen: https://opencve.alliance.unm.edu/cve/CVE-2024-6091, https://db.gcve.eu/vuln/CVE-2026-32973, https://codex.danielvaughan.com/2026/07/26/guardfall-shellsieve-denylist-fragility-coding-agents-codex-cli-os-level-sandbox-defence/
- Folgerung: Textprüfung nur für versehentlich auslösbare Schreibweisen härten; vorsätzliche Umgehung löst die Prüfung an der Quelle (#416).

### Neuer Befund: Teil 2 betrifft die WIRKSAME Config im Haupt-Ordner (Versuch 2026-10-09)
Probe-Skript Scratchpad `probe_main_cfg.py`, echte Hook-Subprozesse, cwd = Worktree, aktiver Workflow:
```
echo x > /<main>/config.yaml                                   -> singleton=0 egress=0 bash_gate=0
sed -i '' s/enabled: true/enabled: false/ /<main>/config.yaml  -> 0 0 0
sed -i '' s/a/b/ ../../../config.yaml                          -> 0 0 0
echo x > config.yaml   (Worktree-Kopie)                        -> 0 0 0
```
Gegenprobe `echo x > ~/elsewhere.txt` -> egress Exit 2 (Wächter läuft). Ursache: `find_project_root()` ist worktree-transparent, der Egress-Wächter zählt den Haupt-Ordner zur Sicherheitszone; `worktree_write_guard` deckt nur Edit/Write.
- Die Worktree-Kopie ist **unkritisch**: config_loader liest absichtlich aus dem Haupt-Ordner (config_loader.py Z. 195–235), eine Änderung wirkt erst nach Merge (Review + CI). Im Framework-Repo wird sie legitim gepflegt (z. B. #345).
- Kritisch ist nur die **wirksame** Datei im Haupt-Ordner: dort kann eine Worktree-Sitzung per Bash jeden Kill-Switch umlegen.
- Allgemeiner Bash-Schreibzugriff aufs Hauptrepo (nicht nur Config) → eigenes Ticket #417.

### Entscheidungen (Tech Lead, nach Daten — kippt die Teil-2-Vorentscheidung)
| Teil | Entscheidung |
|------|--------------|
| 1 Glob | schließen: erstes Muster in `PROTECTED_FILE_PATTERNS` um Glob im letzten Pfadteil erweitern (`(?:[^\s]*\.json` oder `[^\s/]*[*?[][^\s]*)`). Nicht naives `[^\s]*`. |
| 2 Config | **Variante B statt „Config-Datei sperren“:** nur die wirksame Config schützen = `find_config_file(find_project_root())`. Bash-Segment mit Schreib-Indikator, dessen Datei-Token (gegen cwd aufgelöst, `resolve()`) auf genau diese Datei zeigt → Exit 2; Ausweg `override` (`_any_override_token`). Worktree-Kopie bleibt frei. Gilt unabhängig vom aktiven Workflow (Kill-Switches wirken auch ohne). Edit/Write ist schon durch `worktree_write_guard` bzw. Worktree-Pflicht abgedeckt → keine Änderung am edit_gate. |
| F001/F002 | schließen: `PROTECTED_DIR_TOKEN_PATTERNS` → `\.claude(?:/+workflows)?(?:/+\.{1,2})*/*` vor dem bestehenden Lookahead |
| F003 | schließen: neue kleine Funktion `_dir_token_in_cd_context`: nach `cd/pushd .claude[/workflows]` zählt ein bare `workflows`- oder `.`-Token mit `_has_write_indicator(seg, links=True)` |
| F004 | Known Limitation, Verweis auf #416 |
| 3 | eigenes Ticket #416 (Leser-Liste, CERT POS01-C) |

Verworfene Alternativen: (A) Config-Name pauschal sperren + override — Reibung bei legitimer Template-Pflege, schützt die Worktree-Kopie, die gar nicht wirkt. (C) offen lassen — durch Versuch widerlegt, die wirksame Datei ist per Bash erreichbar. (D) nur protokollieren — erkennt, verhindert nicht; ggf. später als Ergänzung.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | Teil 1 Regex, F001/F002 Regex, F003 `_dir_token_in_cd_context`, Teil 2 `_writes_effective_config` + Block mit override-Ausweg |
| `tests/test_bash_gate_state_integrity_410.py` | CREATE | echte Subprozess-Tests, beide Fehlerrichtungen je Teil (Muster: `test_bash_gate_ln_state_407.py`) |
| `CHANGELOG.md` | MODIFY | [Unreleased] |
| `docs/specs/fix-410-state-integrity-gaps.md` | CREATE | Spec inkl. Known Limitation F004 |

### Scope Assessment
- Files: 3 Code/Doku + Spec
- Estimated LoC: +~200 / -~5 (bash_gate ~55, Tests ~140, Changelog ~5)
- Risk Level: MEDIUM — bash_gate läuft bei jedem Bash-Aufruf in jedem Konsumenten-Projekt; Fehlalarm-Regression möglich

### Fehlalarm-Gegenproben (müssen frei bleiben)
`ls .claude/workflows/fix*`, `cat .claude/workflows/x.json`, `cd .claude && ls workflows`, `cd .claude/worktrees/x && cp a b`, `ls .claude && rm docs/x`, `cat config.yaml`, `grep enabled /<main>/config.yaml`, `sed -i s/a/b/ config.yaml` im Worktree (Kopie, nicht wirksam), `workflow.py`-Aufrufe.
Hinnehmbarer Fehlalarm: `cat .claude/workflows/fix* > docs/x` (Glob + Umleitung) — Alternative `workflow.py status`.
Regressionsnetz: `test_bash_gate_ln_state_407.py`, `test_bash_gate_false_positives.py`, `test_bash_gate_erkennung_299*.py`, `test_bash_gate_freetext_fixes_64_75.py`, `test_gate_fixes_26_38_34.py`.

### Technical Approach / Reihenfolge
1. RED: Tests für Teil 1, 2, F001–F003 + Gegenproben
2. Regex-Änderungen (Teil 1, F001/F002)
3. F003
4. Teil 2: wirksame Config auflösen (lazy, nur wenn ein Segment einen Schreib-Indikator hat — geringe Kosten pro Bash-Aufruf), Token gegen cwd auflösen, override prüfen
5. Regressionsnetz + Vollsuite

### Open Questions
- Keine PO-Fragen offen (Teil-2-Richtung ist Tech-Lead-Entscheidung, Memory „Gate-Designfragen selbst entscheiden“).
