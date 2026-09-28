---
entity_id: fix-259-adversary-diff-binding
type: bugfix
created: 2026-09-27
updated: 2026-09-28
status: draft
version: "1.0"
workflow: fix-259-adversary-diff-binding
tags: [adversary, commit-gate, phase8, diff-binding, coverage-gate]
test_targets: ["tests/test_adversary_coverage_gate_259.py"]
---

# Adversary-Dialog-Nachweis an die tatsächliche Änderungsmenge binden (#259)

## Approval

- [x] Approved

## GitHub Issue

- **Issue:** #259 — Folge-Issue zu #253 / PR #255. Commit-Gate und Phase 8 prüfen ein
  gestempeltes Dialog-Artefakt nur auf Form, Mindest-Runden und Hash-Frische der zitierten
  Dateien (#131), nicht darauf, ob es überhaupt die Änderung abdeckt, die gerade übernommen
  wird (F001, reproduziert). Dazu zwei kleinere Härtungen aus demselben Issue: F003
  (Verdict-Erkennung per Substring statt geparstem Wert) und F004 (Namens-Fallback, der bei
  leerem Workflow-Namen einen generischen, erratbaren Standardpfad prüft).

## Purpose

Ein Workflow kann heute ein fremdes, völlig unbeteiligtes Dialog-Protokoll registrieren (das
eines anderen Workflows, das nur dessen eigene Dateien zitiert und hasht) und damit Commit-Gate
und Phase 8 öffnen, obwohl kein Adversary die tatsächlich committete Änderung je gesehen hat —
reproduziert in Issue #259 (Workflow B übernimmt Workflow As Protokoll, staged `src/module_b.py`,
Commit und Phase-8-Übergang gelingen). Diese Spec bindet den Nachweis an die Änderungsmenge:
jede Code-Datei, die committet werden soll (Commit-Gate) bzw. seit einer definierten Basis im
Arbeitsbaum geändert ist (Phase 8), muss im Protokoll per `Code reference:` zitiert und im
`## Geprüfte Dateien`-Hash-Block gebunden sein — sonst zählt weder ein `VERIFIED`- noch ein
`AMBIGUOUS`+Override-Verdict. Im selben Zug wird die Verdict-Erkennung von einer Substring-Suche
auf einen strukturiert geparsten Wert umgestellt (F003) und der Namens-Fallback bei leerem
Workflow-Namen geschlossen (F004).

## Source

- **File:** `core/hooks/adversary_dialog.py` — **Identifier:** neu `coverage_gate_enabled`,
  `dialog_verdict`, `phase8_code_files`, CLI-Unterbefehl `required-files`; erweitert
  `check_dialog_evidence`, `find_dialog_artifact`
- **File:** `core/hooks/bash_gate.py` — **Identifier:** `_require_dialog_evidence`, neue
  Hilfsfunktionen für die Commit-Menge und die Teilstaging-Prüfung
- **File:** `core/hooks/workflow.py` — **Identifier:** `cmd_start`, `_validate_transition`
  (Phase-8-Block)
- **File:** `core/hooks/hook_utils.py` — **Identifier:** neu `is_gated_code_path`; hierher
  umgezogen `CODE_EXTENSIONS`, `ALWAYS_ALLOWED_DIRS`, `ALWAYS_ALLOWED_PATTERNS`
- **File:** `core/hooks/edit_gate.py` — **Identifier:** `main()` (Klassifikation bezieht ihre
  Konstanten jetzt aus `hook_utils`, Kontrollfluss unverändert)
- **File:** `core/hooks/qa_gate.py` — **Identifier:** `main()`, Checklist-Zweig

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `adversary_dialog.validate_dialog_artifact_ex` | function | Bestehende Formprüfung (Checkliste, Runden, Hash-Bindung aus #131) — 3-Tupel-Rückgabe bleibt unverändert, teilt sich künftig den Verdict-Parser mit `dialog_verdict` |
| `adversary_dialog.check_dialog_evidence` | function | Bleibt die einzige Regel für beide Gates, erweitert um einen optionalen `changed_files`-Parameter |
| `hook_utils.find_worktree_root` / `find_project_root` | function | Root-Auflösung für Mess-Root und Hash-Root (Muster aus #80/#96/#131) |
| `hook_utils.git_subcommands` | function | Erkennt ein im selben Bash-Aufruf gebündeltes `git add` (P4) |
| `override_token.has_valid_token` | function | Notbremse im Commit-Gate für Abdeckung, Teilstaging und Git-Fehler |
| `config_loader.load_config` | function | Kill-Switch `adversary_coverage_gate.enabled`, `strict_code_gate`-Überschreibung |
| git-CLI (`diff`, `ls-files`, `merge-base`, `rev-parse`) | external | Ermittlung von Commit- und Phase-8-Änderungsmenge |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | `CODE_EXTENSIONS`, `ALWAYS_ALLOWED_DIRS`, `ALWAYS_ALLOWED_PATTERNS` ziehen hierher um; neue Funktion `is_gated_code_path(file_path, config=None)` |
| `core/hooks/edit_gate.py` | MODIFY | Importiert die drei Konstanten aus `hook_utils` unter denselben Namen; Kontrollfluss und Verhalten unverändert |
| `core/hooks/adversary_dialog.py` | MODIFY | `coverage_gate_enabled`, `dialog_verdict`, `phase8_code_files`, CLI `required-files`; `check_dialog_evidence(wf, changed_files=None)`; F002-Pfadprüfung; F004-Fix |
| `core/hooks/bash_gate.py` | MODIFY | Commit-Menge und Teilstaging-Prüfung als Hilfsfunktionen; Anbindung in `_require_dialog_evidence` |
| `core/hooks/workflow.py` | MODIFY | `base_commit` in `cmd_start`; Phase-8-Block in `_validate_transition` bindet die Abdeckung |
| `core/hooks/qa_gate.py` | MODIFY | Nutzt `dialog_verdict` statt `"AMBIGUOUS" in cl_message` |
| `config.yaml` | MODIFY | Neuer Abschnitt `adversary_coverage_gate.enabled` (Kill-Switch, Default `true`) |
| `tests/test_adversary_coverage_gate_259.py` | CREATE | E2E über die echten Hook-Skripte: F001-Reproduktion, Basis-Matrix, Commit-Varianten, Fehlerfälle |
| `tests/test_adversary_evidence_gate_253.py` | MODIFY (ggf.) | Fixture-Anpassung nur falls die neue Abdeckungsprüfung sonst dort fälschlich anschlägt; Aussage der Tests bleibt unverändert |
| `core/commands/50-implement.md` | MODIFY | Step 8c: `required-files` ausführen und jede gelistete Datei per `Code reference:` zitieren; Gate-Wirkung um #259 ergänzt |
| `core/commands/60-validate.md` | MODIFY | Gate-Wirkung ergänzt; Step 2b: Auto-Fix nur für Nicht-Code, ein Code-Fix läuft über den BROKEN-Pfad |
| `core/agents/implementation-validator.md` | MODIFY | Step 3 nutzt die `required-files`-Liste; Step 6 nennt die Zitierpflicht für jede gelistete Datei |
| `CLAUDE.md` | MODIFY | Adversary-Hooks-Absatz (Abschnitt "Hooks" im Adversary System) und Klarstellung im Abschnitt "Adversary-Limit" |
| `docs/WORKFLOW_GUIDE.md` | MODIFY | Gate-Beschreibung um die Abdeckungsprüfung ergänzt |
| `skills/*/SKILL.md` | MODIFY (generiert) | `python3 scripts/sync_skills.py` nach den `core/commands/*.md`-Änderungen |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` mit Migrationshinweis für laufende Workflows |
| `docs/specs/fix-259-adversary-diff-binding.md` | CREATE | Diese Spec |

**Bewusst unverändert:**
- `core/commands/80-workflow.md` und `.claude/commands/80-workflow.md` — der bestehende
  `--checklist`-Hinweis aus #253 bleibt korrekt; die `.claude`-Datei ist eine per
  `setup.py . --refresh-aliases` generierte Vollkopie und wird nie von Hand editiert.
- `scripts/ci_spec_gate.py` — behält seine eigene, breitere Code-Definition für einen anderen
  Zweck (Spec-Pflicht im PR), unabhängig von `is_gated_code_path`.
- `tests/test_gate_fixes_26_38_34.py`, `tests/test_status_note_325.py`,
  `tests/test_workflow_finish_alias.py`, `tests/test_workflow_name_validation.py` — laut Analyse
  nicht betroffen (keine Code-Änderungsmenge bzw. Fast-Track-Fixtures ohne Adversary-Bezug);
  endgültig zeigt das der Regressionslauf der vollen Suite.

### Estimated Changes

- **Files:** 7 Produktivdateien (davon `qa_gate.py` und `config.yaml` mit wenigen Zeilen),
  1 neue Testdatei, 1 ggf. angepasste Bestandstestdatei, 6 Doku-Dateien plus generierte Skills.
- **LoC:** Produktiv ca. +300 bis +400 / −20, Tests ca. +500 bis +700, Doku ca. +80 bis +120.

**Budget-Überschreitung begründet:** Das Standardlimit (250 LoC Produktiv / 500 LoC Tests) reicht
wegen der zweistufigen Basis-Wahl aus Abschnitt "Phase-8-Basis" (zwei Kandidaten, Vorfahren-
Vergleich, vierstufige Rückfall-Kette) und der sechs zu unterscheidenden Commit-Formen nicht aus.
Die Ursache ist diese Basis-Logik, keine Aufblähung — eine Aufteilung entlang der Gate-Grenze
(erst Commit, später Phase 8) wurde verworfen, weil sie F001 für Phase 8 offen ließe. Bei der
Implementierung zu setzen, mit dieser Begründung im Commit-Bezug:

```bash
python3 .claude/hooks/workflow.py set-field loc_limit_override 450
python3 .claude/hooks/workflow.py set-field test_loc_limit_override 800
```

## Implementation Details

### 1. Gemeinsame Code-Klassifikation (E1)

`CODE_EXTENSIONS`, `ALWAYS_ALLOWED_DIRS` und `ALWAYS_ALLOWED_PATTERNS` ziehen unverändert (Werte
und Namen) von `edit_gate.py` nach `hook_utils.py` um. `edit_gate.py` importiert sie von dort unter
denselben Namen, sodass `edit_gate.CODE_EXTENSIONS` weiterhin auflöst; sein Kontrollfluss (Schritte
2/2b/3 in `main()`) bleibt unverändert — nur die Quelle der drei Konstanten ändert sich, nicht die
Logik, die sie anwendet. Das tote, aufruferlose `hook_utils.is_code_file` bleibt unangetastet.

Neu: `hook_utils.is_gated_code_path(file_path, config=None) -> bool` bildet exakt die Schritte
2/2b/3 von `edit_gate.py` nach — komponentenweiser Verzeichnis-Match (`d.rstrip("/") in
Path(file_path).parts`), Muster per `re.search(..., re.IGNORECASE)`, kleingeschriebene Endung
gegen die Endungsliste. Alle drei Listen sind per `strict_code_gate` in der übergebenen bzw.
geladenen Config überschreibbar — identisch zu `edit_gate.py`s eigenem Verhalten. Die Funktion
entscheidet ausschließlich "ist das eine Code-Datei nach der TDD-Gate-Definition" — Fragen wie
"liegt der Pfad im Projekt" (Schritt 1c in `edit_gate.py`) gehören nicht dazu, weil die neue
Abdeckungsprüfung ausschließlich Pfade betrachtet, die bereits aus `git diff`/`git ls-files`
stammen und damit zwangsläufig im Repository liegen.

`phase8_code_files` (`adversary_dialog.py`) und die Commit-Mengen-Funktion (`bash_gate.py`)
filtern jede ermittelte Rohmenge (Diff- bzw. `ls-files`-Ausgabe) durch `is_gated_code_path`,
bevor sie gegen den Dialog-Nachweis geprüft wird — dieselbe Definition von "Code", die bereits entscheidet, ob eine Datei Phase 6 und ein
RED-Artefakt verlangt.

### 2. Mess-Root, Git-Aufrufe und Pfadvergleich

Mess-Root bleibt das bestehende Muster: Worktree-Root, falls die Sitzung in einem Worktree läuft,
sonst das Hauptrepo (`_measurement_root()` in `bash_gate.py`, `_hash_root()` in
`adversary_dialog.py`). Neu ist, mit welchem `cwd` die git-Unterprozesse für die Änderungsmenge
laufen: nicht der Mess-Root selbst, sondern dessen mit `git rev-parse --show-toplevel`
aufgelöstes Ergebnis (dieser eine Aufruf läuft mit `cwd` = Mess-Root). Grund, empirisch geprüft:
`git diff --name-only` liefert Pfade immer relativ zum Toplevel, unabhängig vom `cwd`; `git
ls-files` liefert Pfade dagegen relativ zum Aufruf-`cwd`. Liegt der Mess-Root unterhalb des
echten Toplevels (`CLAUDE_PROJECT_DIR` zeigt in einem Monorepo auf einen Unterordner), weichen
beide Konventionen sonst auseinander. Laufen beide Kommandos mit `cwd` = Toplevel, liefern sie
einheitlich toplevel-relative Pfade.

Namenslisten laufen immer mit `-z` (NUL-getrennt): ohne `-z` quotet git jeden Pfad mit
Nicht-ASCII-Zeichen als C-String (z. B. `"s\303\274ss.py"`), was ohne eigenen Un-Escaper nicht
verlässlich zurückparsbar ist.

Verglichen werden aufgelöste absolute Pfade: die git-Seite als `<Toplevel>/<relativer-Pfad>`;
die Hash-Block-Seite unverändert, wenn absolut, sonst `_hash_root() / <pfad>` (bestehendes Muster
`_resolve_hash_path`). Beide Seiten laufen vor dem Vergleich durch `os.path.realpath` — das
bereinigt `.`/`..` und löst Symlinks auf, auch im Root-Präfix. Grund: `git rev-parse
--show-toplevel` liefert den physischen Pfad, `find_project_root()` per `CLAUDE_PROJECT_DIR`
dagegen den logischen (auf macOS z. B. `/var/…` gegenüber `/private/var/…`). Ohne Auflösung
meldete die Prüfung dort jede Datei fälschlich als nicht abgedeckt. Da beide Seiten gleich
aufgelöst werden, zeigt auch eine Symlink-Datei im Repo auf beiden Seiten auf dasselbe Ziel.

### 3. Commit-Menge (Commit-Gate)

Vier Fälle, je nach Aufrufform von `git commit` im geprüften Bash-Kommando:

- **Index (Normalfall):** `git diff --cached -z --name-only --diff-filter=d`; ohne HEAD gegen den
  leeren Baum (git-Standardverhalten für `--cached` in einem Repo ohne Commit).
- **`-a`/`--all` (auch gebündelt wie `-am`), leerer Index oder Pfadangabe:** zusätzlich zum
  Index `git diff -z --name-only --diff-filter=d HEAD` (Arbeitsbaum gegen HEAD); ohne HEAD nur
  der Index. Vereinigung, keine Ersetzung: Eine gestagte Änderung, deren Arbeitsbaum danach auf
  den HEAD-Stand zurückgesetzt wurde, fehlt im Arbeitsbaum-Vergleich, wird mit `-i`/`--include`
  oder begleitendem `git add` aber trotzdem committet.
- **`--amend`:** zusätzlich (Vereinigung) Index und Arbeitsbaum gegen `HEAD~1`
  (`git diff --cached … HEAD~1` und `git diff … HEAD~1`) — Obermenge aus bisherigem
  Commit-Inhalt plus Nachbesserung, auch wenn der Arbeitsbaum eine Datei des bisherigen Commits
  auf den `HEAD~1`-Stand zurücksetzt. Ohne `HEAD~1` (Amend des Wurzel-Commits) gilt dieselbe
  Menge wie ohne `--amend`.
- **`git add … && git commit …` im selben Bash-Aufruf** (erkannt über `"add" in
  hook_utils.git_subcommands(command)`): der Index spiegelt zum Hook-Zeitpunkt noch den Stand
  VOR dem `add`. Die Menge wird deshalb um `git ls-files -z --others --exclude-standard`
  (untrackte Dateien) erweitert, und ein sonst geltender Index-Modus wird auf den
  Arbeitsbaum-gegen-HEAD-Vergleich angehoben — sonst fehlte eine im selben Aufruf neu
  hinzugefügte, bis dahin untrackte Code-Datei in der Menge.

Erkennung von `-a` und Pfadangabe per Token-Analyse der `commit`-Argumente: jedes
Nicht-Options-Token, das nicht der Wert einer wertnehmenden Option ist (`-m`, `-F`, `-C`, `-c`,
`-t`, `--author`, `--date`, `--cleanup`, `--fixup`, `--squash`, `--trailer`), gilt als Pfadangabe,
ebenso alles nach `--`. `--amend` zählt nur als Options-Token der `commit`-Argumente (auch
abgekürzt, etwa `--amen`, das git akzeptiert), nie als Teil eines Optionswerts wie der
Commit-Nachricht. Jede Unsicherheit (Aufruf nicht zerlegbar, kein direkter `commit`-Aufruf) führt
zur größeren Menge, einschließlich Amend-Modus; eine Fehlklassifikation vergrößert die Menge nur,
sie verkleinert sie nie. Nach der Ermittlung: `--diff-filter=d` entfernt Löschungen, danach
filtert `is_gated_code_path` auf Code-Dateien.

### 4. Teilweise gestagt (Commit-Gate, E11)

Gilt nur, wenn der Commit-Inhalt aus dem Index kommt: kein `-a`, keine Pfadangabe, kein
begleitendes `git add` im selben Aufruf. Mit `--amend` gilt sie ebenfalls — auch dort committet
der Index-Stand, nicht der Arbeitsbaum. Geprüft wird die Schnittmenge aus (a) gestagten,
`is_gated_code_path`-gefilterten Dateien (`git diff --cached -z --name-only --diff-filter=d`) und
(b) Dateien mit zusätzlichen ungestagten Änderungen (`git diff -z --name-only`, Arbeitsbaum gegen
Index, ohne `--cached`). Jede Datei in dieser Schnittmenge blockt den Commit einzeln — der
geprüfte Hash im Dialog-Protokoll gilt für den Arbeitsbaum, committet würde aber der ältere
Index-Stand.

### 5. Phase-8-Menge und Basis-Wahl

**Zwei Kandidaten:**
- `M` = `merge-base(origin/main, HEAD)` — nur der lokale Ref, kein `git fetch`; existiert nicht
  ohne `origin/main` oder ohne gemeinsamen Vorfahren.
- `S` = das Workflow-Feld `base_commit` — nur gültig, wenn der Commit existiert UND
  `merge-base --is-ancestor S HEAD` gilt (S muss Vorfahre von HEAD sein).

**Regel:** `S` gewinnt, wenn `M` fehlt oder `M` Vorfahre von `S` ist (S ist der jüngere der
beiden). Sonst gewinnt `M` — auch wenn `S` und `M` unvergleichbar sind (Merge-Historie; siehe
Known Limitations). Das hält sowohl den Rebase-Fall (nach `git rebase origin/main` ist der alte,
gespeicherte `S` meist Vorfahre des neu berechneten `M` → `M` gewinnt, Upstream-Änderungen
zählen nicht mit) als auch den Mehrfach-Workflow-Fall (ein zweiter Workflow startet nach einem
ersten, noch nicht gemergten, auf demselben Branch; `M` bleibt unverändert und ist Vorfahre des
neuen, jüngeren `S` → `S` gewinnt, die Dateien des ersten Workflows zählen nicht mit) korrekt
auseinander.

**Rückfall-Kette**, falls kein Kandidat greift:
1. Nur `HEAD` (kein gültiger Kandidat: `base_commit` fehlt oder ist kein Vorfahre von `HEAD`,
   und `M` existiert nicht) — degradiert: nur Ungecommittetes zählt, die Meldung nennt den
   degradierten Rückfall.
2. Kein `HEAD` (Repo ohne Commit) — die Menge ist `git ls-files -z --cached --others
   --exclude-standard` (Index PLUS untrackte Dateien, nicht nur untrackte — sonst entgingen
   bereits gestagte, noch nie committete Dateien).
3. Kein Git-Arbeitsbaum überhaupt (kein Repo, leeres `.git`-Verzeichnis) — die Abdeckungsprüfung
   entfällt ersatzlos, die bestehende #253-Prüfung allein gilt unverändert weiter.

**Menge bei vorhandener Basis** (Kandidat oder nur-HEAD-Fall): `git diff -z --name-only
--diff-filter=d <basis>` (Arbeitsbaum gegen Basis) vereinigt mit `git ls-files -z --others
--exclude-standard` (untrackte Dateien; ein reiner `git diff <basis>` zeigt nie untrackte
Dateien). Danach `is_gated_code_path`-Filter.

### 6. Git-Fehler (E3a) — fail-closed sobald ein gültiger Arbeitsbaum feststeht

Strukturelles Fehlen (kein Repo, leeres `.git`, kein `origin/main`, kein `base_commit`, kein
`HEAD`) degradiert nur durch die Rückfall-Kette oben — es blockt nie. Ob überhaupt ein Repository
vorliegt, entscheidet bei gescheitertem `git rev-parse --show-toplevel` nicht die git-Ausgabe,
sondern ein Befund im Dateisystem, von der Wurzel aufwärts: ein `.git`-Verzeichnis mit `HEAD`,
eine `.git`-Datei, deren `gitdir:`-Ziel `HEAD` enthält (Worktree, Submodul), oder ein gesetztes
`GIT_DIR`. Mit einem solchen Befund ist das Scheitern ein git-Fehler (fail-closed, s. u.), ohne
ihn gibt es kein Repository. Sonst könnte ein vollständig scheiterndes git — etwa durch einen
Wrapper oder durch „dubious ownership“ — als „kein Repository“ durchgehen. Schlägt dagegen ein
git-Unterprozess in einem nachweislich gültigen Arbeitsbaum unerwartet fehl (Exit ungleich 0 oder
Exception, z. B. durch einen fehlerhaften `git`-Wrapper im `PATH`), blockt sowohl das Commit-Gate
als auch der Phase-8-Übergang mit einem Grund, der den fehlgeschlagenen Befehl nennt. Am
Commit-Gate hebt ein gültiger Override-Token diesen Block auf; Phase 8 kennt dafür keinen
Override (bestehende Linie: Phase 8 hat nie einen Override-Pfad gehabt).

### 7. Abdeckungsprüfung (E4)

`check_dialog_evidence(wf, changed_files=None)` — `changed_files`, falls übergeben, ist bereits
eine Liste per `os.path.realpath` aufgelöster absoluter Pfade (Abschnitt 2); die Funktion selbst löst
keine Pfade mehr auf, das übernehmen ihre Aufrufer (die Commit-Mengen-Funktion in `bash_gate.py`
bzw. `phase8_code_files` in `adversary_dialog.py`). Ablauf:

1. `find_dialog_artifact(wf)` — inklusive der neuen F002-Pfadprüfung (Abschnitt 8).
2. Existenzprüfung des gefundenen Pfads.
3. `validate_dialog_artifact_ex(path)` — unverändert (Checkliste, Runden, Verdict über den
   gemeinsamen Parser, Hash-Frische aus #131).
4. **Neu:** ist `changed_files` nicht `None`, muss jede seiner Dateien im letzten `##
   Geprüfte Dateien`-Block vorkommen (derselbe Block, den #131 bereits gegen Alterung prüft).
   Fehlt mindestens eine, ist der Nachweis nicht erbracht — die Meldung listet bis zu 10 fehlende
   Dateien.
5. Verdict-Widerspruchsprüfung (`VERIFIED` im State, aber nur `AMBIGUOUS` im Artefakt) — jetzt
   über `dialog_verdict` statt Substring-Suche (F003, Abschnitt 9).
6. `None` bei Erfolg, sonst der jeweilige Grund als Text — wie bisher fail-closed: ein interner
   Fehler wird zur Grund-Meldung, nie zur Exception.

### 8. F002 — Artefakt-Pfad muss innerhalb des Projekts liegen (E6)

Zusätzliche Prüfung in `find_dialog_artifact`/`check_dialog_evidence`, auf den jeweils
aufgelösten Pfad angewendet (registriert oder Standardpfad): der Pfad wird mit aufgelösten
Symlinks (`Path.resolve()`) geprüft und muss unterhalb der ebenso aufgelösten Worktree-Wurzel
oder Projekt-Wurzel liegen — sonst gilt der Nachweis als nicht erbracht, unabhängig davon, ob die
Datei inhaltlich gültig wäre. Die Prüfung läuft ausschließlich zur Gate-Zeit, nicht bei
`add-artifact` (eine Frühwarnung dort wäre reine UX und ist verworfen).

### 9. F003 — Strukturiert geparstes Verdict (E7)

Die bestehende Verdict-Erkennung aus `validate_dialog_artifact_ex` (drei Regex-Formen, `HOLDS` →
`VERIFIED`, letztes Vorkommen gewinnt) wird in einen gemeinsamen, privaten Parser ausgelagert.
Neue öffentliche Funktion `dialog_verdict(artifact_path) -> "VERIFIED" | "AMBIGUOUS" | "BROKEN" |
None`: liest die Datei, entfernt Fenced-Code-Blöcke (`_strip_fenced_code_blocks`), wendet den
gemeinsamen Parser an, liefert das normalisierte Verdict-Wort oder `None` (Datei nicht lesbar
bzw. kein Verdict gefunden). `validate_dialog_artifact_ex`s 3-Tupel-Rückgabe und ihre Meldungen
bleiben unverändert — nur ihre interne Verdict-Extraktion ruft jetzt denselben Parser auf.

Zwei Aufrufer wechseln von Substring-Suche auf den geparsten Wert:
- `check_dialog_evidence`s Widerspruchsprüfung: `dialog_verdict(str(path)) == "AMBIGUOUS"` statt
  `"AMBIGUOUS" in message`.
- `qa_gate.py`s Checklist-Zweig: `dialog_verdict(<checklist-artifact-pfad>) == "AMBIGUOUS"` statt
  `"AMBIGUOUS" in cl_message`.

### 10. F004 — Namens-Fallback bei leerem Workflow-Namen (E8)

`find_dialog_artifact`: ist `wf.get("name")` leer bzw. fehlt, wird **kein** Standardpfad mehr
geprüft (kein `docs/artifacts//adversary-dialog.md`) — nur ein per `test_artifacts` registriertes
Artefakt zählt dann noch. `check_dialog_evidence`s Meldung im "nichts gefunden"-Fall unterscheidet
diesen Fall vom normalen: bei leerem Namen lautet sie sinngemäß "… ohne Workflow-Namen gibt es
keinen Standardpfad" statt den generischen Platzhalter `<workflow>` in den Standardpfad
einzusetzen.

### 11. Kill-Switch (E9)

`coverage_gate_enabled() -> bool` liest `config.yaml` → `adversary_coverage_gate.enabled`
(Default `true`); nur ein ausdrückliches `false` schaltet ab — dasselbe nachsichtige Muster wie
bei `adr_gate`/`po_briefing_gate`/`framework_disabled` (fehlender Schlüssel, kaputte Config oder
Tippfehler lassen das Gate an). Ist der Schalter aus: `check_dialog_evidence` wird immer mit
`changed_files=None` aufgerufen (heutiges #253-Verhalten), die Teilstaging-Prüfung entfällt
komplett in `bash_gate.py`. Der Schalter umschließt **ausschließlich** die neue
Abdeckungs-/Teilstaging-Logik — die #253-Formprüfung samt Hash-Frische aus #131 sowie F002, F003
und F004 wirken unabhängig vom Schalterstand immer.

### 12. Bedienbarkeit — `required-files` (E10)

Neuer CLI-Unterbefehl in `adversary_dialog.py` neben `parse`/`validate`/`stamp`/`schema`. Löst
den aktiven Workflow über `hook_utils.resolve_active_workflow()` auf und liest dessen
State-Datei direkt (wie `bash_gate._read_active_workflow()`) — kein Modul-Level-Import von
`workflow.py`, um den bestehenden, einseitigen Importpfad (`workflow.py` importiert
`adversary_dialog` nur lokal innerhalb von `_validate_transition`) nicht umzukehren. Ruft
`phase8_code_files(wf)` auf und gibt aus:

- **stdout:** eine Datei pro Zeile, exakt in der Form, die `stamp_dialog_artifact` bzw. eine
  `Code reference:`-Zeile erwartet — relativ zu `_hash_root()`, wenn die Datei darunter liegt,
  sonst absolut.
- **stderr:** die verwendete Basis (welcher Kandidat gewonnen hat) und, falls zutreffend, der
  Degradations-Hinweis.

Exit 0 im Normalfall, auch wenn die Menge leer ist oder kein Git-Arbeitsbaum vorliegt (dann nur
ein erklärender stderr-Hinweis, keine stdout-Zeilen); Exit 1 bei Git-Fehler oder ohne aktiven
Workflow. `required-files` ignoriert den Kill-Switch bewusst: es zeigt immer, was Phase 8 bei
aktivem Gate prüfen würde, unabhängig vom aktuellen Schalterstand — es ist ein rein lesendes
Planungswerkzeug, kein Durchsetzungspunkt.

### 13. Anbindung in `bash_gate.py`

`_require_dialog_evidence` bleibt der einzige Aufrufer für das Commit-Gate. Ist
`coverage_gate_enabled()` wahr: die Commit-Menge (Abschnitt 3) wird ermittelt; ein Git-Fehler
darin blockt sofort (Abschnitt 6); sonst läuft `check_dialog_evidence(wf,
changed_files=<Menge>)`; zusätzlich läuft, wenn anwendbar, die Teilstaging-Prüfung (Abschnitt 4)
als eigener, unabhängiger Blockgrund. Ist der Schalter aus: nur `check_dialog_evidence(wf,
changed_files=None)`, keine Teilstaging-Prüfung. Jeder so gefundene Grund — die bestehenden
#253-Gründe, die neue Abdeckung, der Git-Fehler oder die Teilstaging-Meldung — wird wie bisher
von einem gültigen Override-Token aufgehoben; die Token-Prüfung selbst ändert sich nicht.

### 14. Anbindung in `workflow.py`

`cmd_start` schreibt zusätzlich `base_commit` = `HEAD` des Mess-Roots (Worktree-Root, falls
vorhanden, sonst Projekt-Root; `git rev-parse HEAD` mit `cwd` = dessen Toplevel), `null` ohne
`HEAD` — einheitlich für `feature`, `feature-fast` und `bug`, da die Fast-Track-Ausnahmen bereits
vollständig in `_validate_transition` greifen, bevor der Phase-8-Block je erreicht wird.

`_validate_transition`s Phase-8-Block ruft nach der bestehenden Verdict-/Override-Prüfung
`adversary_dialog.phase8_code_files(data)` auf (nur wenn `coverage_gate_enabled()`): liefert sie
eine Dateimenge, geht diese als `changed_files` in `check_dialog_evidence` ein; meldet sie "kein
Git-Arbeitsbaum", läuft `check_dialog_evidence(data, changed_files=None)` unverändert wie heute;
meldet sie einen Git-Fehler, blockt der Übergang direkt mit diesem Grund — ohne Override-Pfad,
wie bei Phase 8 schon immer. `cmd_complete` (und damit `finish`) braucht keine eigene Änderung:
es ruft bereits `_validate_transition(data, "phase8_complete")` auf, die neue Prüfung gilt daher
automatisch für alle drei Abschlusswege (`phase`, `complete`, `finish`).

### 15. `qa_gate.py`

Einzige Änderung: der `--checklist`-Zweig ersetzt `"AMBIGUOUS" in cl_message` durch einen
Vergleich mit `dialog_verdict(<checklist-artifact-pfad>)` (Abschnitt 9). Keine weitere Zeile
ändert sich.

### 16. Auto-Fix-Grenze in `/60-validate` (E5, reine Doku)

Step 2b darf nur Nicht-Code (nach `is_gated_code_path`) automatisch ändern. Braucht ein
Validierungsfund eine Code-Änderung, ist das kein Auto-Fix mehr, sondern läuft über den
BROKEN-Pfad: zurück zu `phase6_implement`, gezielter Fix, eine weitere Adversary-Runde — aus
demselben Kontingent wie jedes andere BROKEN-Verdict (Adversary-Limit in `CLAUDE.md`: höchstens
eine weitere Runde nach dem ersten Zyklus). Phase 8 erzwingt das ohnehin technisch, unabhängig
von der Doku: ändert ein Auto-Fix eine zitierte Datei, schlägt die Hash-Frische aus #131 an;
ändert er eine nicht zitierte Datei, schlägt die neue Abdeckungsprüfung an.

### 17. Ausnahmen (E12, kein neuer Code)

`bug` und `feature-fast` überspringen den gesamten Adversary-Block des Commit-Gates
(`bash_gate.py`, bestehende Typ-Prüfung) und den gesamten Verdict-/Nachweis-Block in Phase 8
(`workflow.py`, bestehender früher `bug`-Rückgabepfad bzw. `feature-fast`s engerer Prüfpfad) —
die neue Abdeckungs- und Teilstaging-Prüfung erben diese Ausnahme automatisch, ohne eigenen
Code, weil sie ausschließlich innerhalb dieser bestehenden Blöcke laufen. Ebenso prüft das
Commit-Gate den Adversary-Block nur in `phase6_implement`, `phase6b_adversary` und
`phase7_validate` (bestehender Phasen-Filter) — außerhalb dieser Phasen läuft die neue Prüfung
gar nicht erst an.

## Expected Behavior

- **Input:** Workflow-State (Name, Phase, Typ, `adversary_verdict`, `test_artifacts`,
  `base_commit`), das gefundene Dialog-Artefakt samt seinem letzten `## Geprüfte
  Dateien`-Hash-Block, sowie der aktuelle Git-Zustand im Mess-Root (Index, Arbeitsbaum, `HEAD`,
  `origin/main` falls vorhanden).
- **Output:** Commit-Gate — Exit 0 oder Exit 2 mit Grund (inklusive bis zu 10 nicht abgedeckten
  Dateinamen). Phase-8-Übergang (`phase`, `complete`, `finish`) — Erfolg oder Exit ungleich 0 mit
  demselben Grund-Format. `adversary_dialog.py required-files` — Dateiliste auf stdout,
  Basis-Information auf stderr, Exit 0 bzw. Exit 1 bei Git-Fehler oder fehlendem aktiven
  Workflow.
- **Side effects:** `workflow.py start` schreibt zusätzlich das Feld `base_commit` in den neuen
  Workflow-State. Alle übrigen Prüfungen sind rein lesend — keine weiteren Seiteneffekte.

## Error Handling

- **Abdeckung fehlt:** "Dialog-Nachweis deckt die Änderung nicht ab — nicht zitiert und gehasht:
  `<a>`, `<b>` (+N weitere)" (gekappt auf 10 Dateien). Weg: Dialog erneut führen, jede Datei aus
  `adversary_dialog.py required-files` per `Code reference:` zitieren, danach `stamp`.
- **Teilweise gestagt** (nur Commit-Gate): "teilweise gestagt: `<datei>` — geprüft wurde der
  Arbeitsbaum, committet würde der Index-Stand". Ausweg: `git add <datei>` oder `git commit -a`.
- **F002 — Artefakt außerhalb:** "Dialog-Artefakt liegt außerhalb von Projekt und Worktree:
  `<pfad>`".
- **F004 — kein Name:** "… ohne Workflow-Namen gibt es keinen Standardpfad".
- **Git-Fehler im gültigen Arbeitsbaum** (fail-closed): "Änderungsmenge nicht ermittelbar
  (`<befehl>`: `<fehler>`)".
- **Degradierter Rückfall** (Teil der Abdeckungs-Meldung, wenn nur `HEAD` als Basis diente):
  "Basis nur HEAD — kein `base_commit` und kein `origin/main`; bereits committete Änderungen sind
  nicht erfasst".
- Unerwarteter interner Fehler in einer der neuen Prüfungen → Block mit Fehlerklasse im Text,
  fail-closed wie die bestehende #253-Prüfung.
- **Ausweg Commit-Gate:** ein gültiger Override-Token hebt jeden Nachweis-Block auf — wie
  bisher die #253-Gründe (inklusive Hash-Prüfung), jetzt auch Abdeckung, Teilstaging, Git-Fehler
  und die F002-/F004-Gründe. Die Notbremse aus #253 bleibt damit unverändert (Abschnitt 13).
  **Ausweg Phase 8:** `config.yaml` → `adversary_coverage_gate.enabled: false`
  oder `workflow.py abandon` — Phase 8 kennt keinen Override-Token-Pfad.

## Known Limitations

- Ein selbst geschriebenes, danach selbst gestempeltes Protokoll besteht weiterhin — geprüft
  werden Form und jetzt zusätzlich Umfang, nicht die Urheberschaft (vorbestehend aus #253 KL 1).
- Ein Commit mit expliziter Pfadangabe zählt konservativ den gesamten Arbeitsbaum gegen `HEAD`
  plus den Index, nicht nur die angegebenen Pfade. Ebenso zählt bei `-a` oder reiner Pfadangabe
  eine gestagte, im Arbeitsbaum wieder zurückgenommene Datei mit, obwohl git sie dann nicht
  committet (Ausweg: die Datei vorher unstagen).
- Nur Workflows ohne gültigen `base_commit` (alt, oder durch einen Rebase umgeschrieben) in
  einem Repo ohne `origin/main` fallen auf "nur Ungecommittetes" zurück — die Meldung nennt
  diesen degradierten Rückfall ausdrücklich.
- Liegt auf demselben Branch ein früherer, noch nicht gemergter Workflow, und wurde danach
  rebased, kann dessen Diff je nach Vorfahren-Verhältnis von `S` und `M` mitzählen. Bei einem
  Worktree pro Workflow, wie empfohlen, tritt das nicht auf.
- Gelöschte Dateien sind nicht gebunden (sie lassen sich weder zitieren noch hashen); bei
  Umbenennungen zählt ausschließlich der neue Pfad.
- Ein `setup.py --update` mitten in einem laufenden Workflow macht die aktualisierten
  `.claude/hooks/*.py` zu Änderungen dieses Workflows. Framework-Updates sollten deshalb
  außerhalb laufender Workflows passieren.
- Der Basis-Branch ist wie in Abschnitt 5b des Commit-Gates fest `origin/main`. Ein
  konfigurierbarer Basis-Branch für beide Stellen zusammen wäre ein möglicher Folgeschritt.
- Das Adversary-Limit (höchstens eine weitere Runde nach dem ersten Zyklus) bleibt reine
  Prompt-Konvention — `fix_loop_iterations` zählt keine Rücksprünge `phase7_validate` →
  `phase6_implement`.
- `base_commit` ist per `workflow.py set-field base_commit <sha>` änderbar. Ein bewusst
  verschobener Start-Commit verkleinert die Phase-8-Menge — das ist derselbe vorsätzliche Weg wie
  bei einem selbst geschriebenen Protokoll (KL 1), keine neue Lücke.
- Pfade mit Leerzeichen lassen sich nicht zitieren (`Code reference:` erfasst nur `\S+`,
  vorbestehend aus #131) — eine solche Code-Datei blockiert dauerhaft; Ausweg sind Override-Token
  bzw. Kill-Switch.
- `git mv` im selben Aufruf und git-Aliase (z. B. `git ci`) werden von der `git add`-Erkennung
  (Abschnitt 3) nicht gezielt erfasst. Phase 8 fängt eine dadurch zunächst unterschätzte
  Commit-Menge trotzdem ab, weil sein Diff unabhängig vom Weg der Entstehung gegen die Basis
  misst.
- Rest-Risiko der Teilstaging-Prüfung: eine andere, bereits vorher teilweise gestagte Datei bleibt
  ungeprüft, wenn derselbe Bash-Aufruf zusätzlich ein `git add` für eine andere Datei enthält —
  in diesem Fall entfällt die Teilstaging-Prüfung für den gesamten Aufruf (Abschnitt 4).
- Vorsätzlich manipuliertes git ist über git-Aufrufe nicht erkennbar. Gemeint ist ein Wrapper, der
  gezielt nur einzelne Prüfaufrufe (`rev-parse --verify`, `merge-base`) scheitern lässt, `diff`
  und `commit` aber durchreicht, oder der Erfolg mit erfundener Ausgabe vortäuscht. Ein solcher
  Wrapper kann die Menge verkleinern — derselbe vorsätzliche Weg wie ein selbst geschriebenes
  Protokoll (KL 1). Realistische Ausfälle, bei denen git insgesamt scheitert (defekte
  Installation, „dubious ownership“), erfasst der Repo-Befund aus Abschnitt 6.
- Die Repo-Suche aus Abschnitt 6 ignoriert `GIT_CEILING_DIRECTORIES` und Dateisystemgrenzen, und
  eine unlesbare `.git`-Datei zählt als Befund (fail-closed). In solchen Umgebungen blockt ein
  gescheitertes `rev-parse`; am Commit-Gate hebt der Override-Token das auf, für Phase 8 bleibt
  der Kill-Switch.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Die F001-Reproduktion aus Issue #259 wird sowohl am Commit-Gate als auch am
      Phase-8-Übergang blockiert — nachgewiesen End-to-End über die echten Hook-Skripte
- [ ] Der dokumentierte Weg (`required-files` → Dialog → `stamp` → `add-artifact` →
      `qa_gate --checklist`) öffnet Commit und Phase 8 weiterhin ohne Zusatzschritt
- [ ] Regressionslauf `python3 -m pytest tests/ -q` ist grün
- [ ] `python3 scripts/sync_skills.py --check` und
      `python3 scripts/ci_spec_gate.py --base origin/main` sind grün
- [ ] Dogfooding: dieser Workflow selbst schließt Phase 8 unter der neuen Regel ab. Er wurde
      vor #259 gestartet, hat also kein `base_commit`; seine Basis ist deshalb
      `merge-base(origin/main, HEAD)`. Der Dialog zitiert und hasht jede Datei, die
      `required-files` listet (erwartet: die geänderten `core/hooks/*.py`)

## Acceptance Criteria

- **AC-1:** Given ein Workflow im Full Process mit `VERIFIED`-Verdict, dessen registriertes,
  gültig gestempeltes Dialog-Protokoll ausschließlich `src_A/module_a.py` zitiert und hasht,
  während `src/module_b.py` gestaged ist / When `bash_gate.py` einen `git commit` über die
  echten Hook-Skripte prüft / Then Exit 2, und die Meldung nennt `src/module_b.py` als nicht
  zitierte und nicht gehashte Datei.
  - Test: `test_ac1_foreign_dialog_does_not_cover_staged_file` — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-2:** Given denselben Zustand wie in AC-1 in `phase7_validate`, ohne dass zuvor committet
  wurde / When
  `workflow.py phase phase8_complete`, `workflow.py complete` bzw. `workflow.py finish`
  ausgeführt wird / Then ist der Exit-Code in allen drei Fällen ungleich 0, und stderr nennt
  `src/module_b.py`.
  - Test: `test_ac2_phase8_blocks_uncovered_change` (`phase phase8_complete`/`complete`/`finish`) — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-3:** Given ein Dialog-Protokoll, das jede tatsächlich geänderte Code-Datei per
  `Code reference:` zitiert und im `## Geprüfte Dateien`-Block hasht / When derselbe `git commit`
  geprüft und anschließend `workflow.py phase phase8_complete` ausgeführt wird / Then ist der
  Commit Exit 0 und der Phasenübergang gelingt, ohne zusätzlichen Schritt gegenüber dem
  heutigen, dokumentierten #253-Ablauf.
  - Test: `test_ac3_documented_path_with_required_files`; Regressionswächter `test_ac3_fully_cited_dialog_still_opens_commit_and_phase8` — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-4:** Given ein `VERIFIED`-Verdict mit vollständig zitiertem und gehashtem Dialog / When
  ein `git commit` in Index-Form, mit `-a`/`-am`, mit expliziter Pfadangabe, mit leerem Index,
  als `--amend` oder als gebündeltes `git add <neue-datei> && git commit` mit einer neuen, bis
  dahin untrackten Code-Datei geprüft wird / Then erfasst die Commit-Menge in jeder der sechs
  Formen jede Code-Datei, die so committet würde (bei `-a`, Pfadangabe, leerem Index und
  `--amend` bewusst als Obermenge): Ist eine solche Datei nicht zitiert, endet die Prüfung mit
  Exit 2 und ihrem Namen in der Meldung; ist sie zitiert und gehasht, mit Exit 0.
  - Test: `test_ac4_commit_set_covers_every_commit_form` (6 Commit-Formen plus die Varianten `amend-in-message`, `amend-boomerang`, `add-staged-reverted`, `include-staged-reverted`, `amend-index-at-head`, je × nicht zitiert/zitiert); `test_ac4_amend_only_as_real_commit_option` (`--amend` nur als Options-Token, nie im Nachrichtentext) — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-5:** Given ein Dialog, der alle geänderten Code-Dateien bis auf eine gelöschte, eine
  umbenannte und eine Nicht-Code-Datei zitiert / When Commit-Gate bzw. Phase 8 die
  Änderungsmenge bilden / Then zählt die gelöschte Datei nicht, die umbenannte zählt unter ihrem
  neuen Pfad, eine Nicht-Code-Datei (`docs/`, `tests/`, `scripts/`, `*.md`/`*.json`/`*.yaml`)
  zählt nicht, und eine per `strict_code_gate` erweiterte bzw. eingeschränkte Endungsliste wird
  entsprechend der Konfiguration angewendet.
  - Test: `test_ac5_rename_delete_and_non_code` (Commit/Phase 8), `test_ac5_strict_code_gate_extension_list_applies` (erweitert/eingeschränkt) — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-6:** Given eine Code-Datei, die teilweise gestagt ist (der gestagte Inhalt unterscheidet
  sich vom Arbeitsbaum-Inhalt) / When `git commit` ohne `-a`, ohne Pfadangabe und ohne
  begleitendes `git add` geprüft wird / Then Exit 2 mit dem Hinweis auf teilweises Staging und
  dem Dateinamen; bei `git commit -a` mit derselben Ausgangslage blockiert diese Prüfung nicht.
  - Test: `test_ac6_partially_staged_file_blocks_index_commit` (Index/`-a`) — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-7:** Given (a) ein frisch gestarteter Workflow, (b) ein Rebase auf einen neuen
  `origin/main` nach dem Start, (c) ein zweiter Workflow auf demselben Branch ohne Rebase nach
  einem ersten, (d) ein Repo ohne `origin/main`, (e) ein Repo ohne `HEAD`, (f) ein alter
  Workflow ohne `base_commit` und ohne `origin/main` sowie (g) eine Sitzung in einem
  Git-Worktree / When Phase 8 die Basis für die Änderungsmenge bestimmt / Then setzt
  `workflow.py start` in (a) das Feld `base_commit`; in (b) zählen die per Rebase hereingezogenen
  Upstream-Dateien nicht mit; in (c) zählen die Dateien des früheren Workflows nicht mit; in (d)
  gilt `base_commit`; in (e) zählen Index und untrackte Dateien; in (f) zählt nur
  Ungecommittetes, und die Meldung nennt den degradierten Rückfall; in (g) misst die Prüfung im
  Worktree, nicht im Hauptrepo.
  - Test: `test_ac7_start_records_base_commit` (a: `feature`/`bug`/`feature-fast`/ohne HEAD; g: Worktree), `test_ac7_phase8_base_selection` (b–g × eigene Datei nicht zitiert/fremde Datei zählt nicht) — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-8:** Given ein gültiger Git-Arbeitsbaum, in dem der Diff-Aufruf selbst oder jeder
  git-Aufruf einschließlich `rev-parse --show-toplevel` unerwartet fehlschlägt (z. B. über einen
  `git`-Wrapper im `PATH`, auch mit vorgetäuschter Meldung „not a git repository“) / When
  Commit-Gate oder Phase-8-Übergang geprüft werden / Then blockieren beide mit einem Grund, der
  den fehlgeschlagenen Befehl nennt; liegt dagegen gar kein Git-Repository bzw. nur ein leeres
  `.git`-Verzeichnis vor (kein Repo-Befund nach Abschnitt 6), entfällt die Abdeckungsprüfung
  ersatzlos, und beide Gates verhalten sich wie vor dieser Änderung.
  - Test: `test_ac8_git_failure_in_valid_worktree_blocks` (Commit/Phase 8 × Diff scheitert, jeder Aufruf scheitert, vorgetäuschtes „not a git repository“); `test_ac8_repo_marker_decides_not_git_output` (sieben Repo-Layouts); Regressionswächter `test_ac8_without_git_worktree_coverage_is_skipped` — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-9:** Given ein per `add-artifact` registriertes Dialog-Protokoll mit einem absoluten Pfad
  außerhalb von Projekt und Worktree bzw. mit einem Symlink, der nach außen zeigt / When das
  Protokoll als Nachweis geprüft wird / Then gilt der Nachweis als nicht erbracht; liegt
  dasselbe Protokoll dagegen im Worktree, wird es akzeptiert.
  - Test: `test_ac9_artifact_outside_project_is_rejected` (absolut/Symlink × Commit/Phase 8); Regressionswächter `test_ac9_artifact_inside_worktree_is_accepted` — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-10:** Given Meldungstext und tatsächliches Verdict eines gültigen Protokolls
  widersprechen sich im Wortlaut (Meldung von `validate_dialog_artifact_ex` per Test-Patch
  verändert: Protokoll mit Verdict `AMBIGUOUS`, Meldung ohne das Wort "AMBIGUOUS" — bzw.
  Protokoll mit Verdict `VERIFIED`, Meldung mit dem Wort "AMBIGUOUS") / When
  `check_dialog_evidence` bei `VERIFIED` im State bzw. `qa_gate.py --checklist` das Protokoll
  auswerten / Then entscheidet das geparste Verdict (`dialog_verdict`): Das
  `AMBIGUOUS`-Protokoll ergibt den Widerspruchs-Block bzw. ein `AMBIGUOUS`-Verdict im State, das
  `VERIFIED`-Protokoll weder Widerspruch noch `AMBIGUOUS`.
  - Test: `test_ac10_check_dialog_evidence_uses_parsed_verdict`, `test_ac10_qa_gate_checklist_uses_parsed_verdict`, `test_ac10_dialog_verdict_parses_structured_value` — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-11:** Given ein Workflow ohne Namen (leerer bzw. fehlender `name`-Wert) und eine Datei
  unter dem generischen Pfad `docs/artifacts/adversary-dialog.md` / When der Dialog-Nachweis
  gesucht wird / Then wird diese Datei nicht als Standardpfad akzeptiert, und die Meldung
  erklärt, dass ohne Workflow-Namen kein Standardpfad existiert, ohne dabei den literalen
  Platzhalter `<workflow>` zu enthalten.
  - Test: `test_ac11_no_default_path_without_workflow_name`, `test_ac11_nameless_workflow_generic_file_blocks` (Commit/Phase 8) — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-12:** Given `config.yaml` → `adversary_coverage_gate.enabled: false` und dieselbe
  F001-Ausgangslage wie in AC-1 / When Commit-Gate und Phase 8 geprüft werden / Then verhalten
  sich beide exakt wie vor dieser Änderung — der F001-Commit wird nicht wegen fehlender
  Abdeckung blockiert, die Teilstaging-Prüfung läuft nicht, während die #253-Hash-Prüfung sowie
  F002 bis F004 unverändert weiter wirken.
  - Test: `test_ac12_coverage_gate_enabled_only_explicit_false`, `test_ac12_kill_switch_only_covers_new_coverage` — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-13:** Given ein gültiger User-Override-Token für den Workflow bzw. ein Workflow vom Typ
  `bug` oder `feature-fast` / When das Commit-Gate wegen fehlender Abdeckung, Teilstaging oder
  eines Git-Fehlers blockieren würde / Then hebt der Override-Token bzw. die
  Fast-Track-Ausnahme diesen Block auf; für den Phase-8-Übergang existiert dafür kein
  Override-Pfad, und außerhalb der Phasen 6 bis 7 prüft das Commit-Gate die Abdeckung gar nicht
  erst.
  - Test: `test_ac13_commit_block_lifted_by_token_fast_track_or_phase`, `test_ac13_phase8_has_no_override_path` — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-14:** Given ein aktiver Workflow mit einer bekannten Phase-8-Änderungsmenge / When
  `python3 adversary_dialog.py required-files` ausgeführt wird / Then listet stdout genau die
  Dateien, die auch der Phase-8-Übergang prüft — je Zeile relativ zu `_hash_root()` bzw. absolut,
  wenn die Datei außerhalb davon liegt — während Basis-Information und ein etwaiger
  Degradations-Hinweis auf stderr erscheinen.
  - Test: `test_ac14_required_files_lists_exactly_the_phase8_set`, `test_ac14_required_files_reports_degraded_base_on_stderr`, `test_ac14_required_files_absolute_outside_hash_root`, `test_ac14_required_files_exit_codes` — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-15:** Given die bestehende Test-Suite für `edit_gate.py` (Verzeichnis-Match,
  Endungs-Liste, `strict_code_gate`-Überschreibung) / When `hook_utils.is_gated_code_path` die
  Klassifikation aus `edit_gate.py` übernimmt und `edit_gate.py` seine Konstanten von dort
  importiert / Then liefert `is_gated_code_path` auf einer Pfad-Tabelle (Code-Endung,
  freigestellter Ordner, freigestelltes Muster, Nicht-Code-Endung, `strict_code_gate`-Override)
  dieselben Entscheidungen wie die bisherigen edit_gate-Regeln, alle bestehenden
  edit_gate-Tests bleiben unverändert grün, und `edit_gate.CODE_EXTENSIONS` bleibt unter
  demselben Namen auflösbar.
  - Test: `test_ac15_is_gated_code_path_matches_edit_gate` (14 Pfade), `test_ac15_constants_have_single_source_in_hook_utils`; Regressionswächter `test_ac15_edit_gate_constants_keep_names_and_values` plus die bestehenden edit_gate-Tests — alle in `tests/test_adversary_coverage_gate_259.py`

- **AC-16:** Given die für #259 vorgesehenen Dokumentationsstellen (`/50-implement` Step 8c,
  `implementation-validator` Step 3 und 6, `/60-validate` Step 2b, `CLAUDE.md`,
  `docs/WORKFLOW_GUIDE.md`, `CHANGELOG.md`) / When die Implementierung abgeschlossen ist / Then
  beschreibt jede Stelle die Abdeckungsprüfung korrekt — darunter `required-files`, den
  BROKEN-Pfad für einen Code-Fix in `/60-validate` und den Migrationshinweis in
  `CHANGELOG.md` — und `python3 scripts/sync_skills.py --check` meldet keine Drift.
  - Test: `test_ac16_docs_describe_coverage_gate` (7 Doku-Stellen), `test_ac16_changelog_has_migration_note_for_259` — alle in `tests/test_adversary_coverage_gate_259.py`

## Test Plan

Automatische Tests (jeweils an eine oder mehrere Acceptance Criteria oben gebunden):

- `python3 -m pytest tests/test_adversary_coverage_gate_259.py -q` — neue Datei, End-to-End über
  die echten Hook-Skripte (`edit_gate.py`, `bash_gate.py`, `workflow.py`, `adversary_dialog.py`)
  mit echten Commits in einem Wegwerf-Repo, einem Bare-Repo als `origin` und `git worktree add`
  für die Worktree-Fälle (AC-1 bis AC-14). In derselben Datei: die Pfad-Tabelle für
  `is_gated_code_path` (AC-15) und Textprüfungen der Doku-Stellen (AC-16: `required-files` in
  `/50-implement` Step 8c und `implementation-validator`, BROKEN-Pfad in `/60-validate` Step 2b,
  Migrationshinweis in `CHANGELOG.md`).
- Bestandstests, die unverändert grün bleiben müssen (Fixture-Anpassung ohne Aussage-Änderung
  erlaubt): `tests/test_adversary_evidence_gate_253.py`, `tests/test_adversary_dialog_hash_binding_131.py`,
  `tests/test_qa_gate.py`, `tests/test_verdict_pipeline_77.py`, `tests/test_adversary_dialog_parse.py`.
- edit_gate-Regression (AC-15), unverändert grün: `tests/test_edit_gate_*.py`,
  `tests/test_gate_coverage.py`, `tests/test_selfexplaining_gates.py`.
- Regressionslauf: `python3 -m pytest tests/ -q`.
- Drift-/Server-Checks: `python3 scripts/sync_skills.py --check`,
  `python3 scripts/ci_spec_gate.py --base origin/main`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Keine neue Architektur — eine bestehende Prüfung wird um eine Dimension
  (Abdeckung der tatsächlichen Änderung) erweitert. Vier tragende Festlegungen:
  1. **Eine Regel, zwei Aufrufer, jetzt auch für die Abdeckung.** `check_dialog_evidence(wf,
     changed_files=None)` bleibt die einzige Prüf-Funktion für Commit-Gate und
     Phase-8-Übergang; die Abdeckungsprüfung erweitert sie um einen optionalen Parameter, statt
     eine zweite, parallele Prüfung in einem der beiden Aufrufer zu ergänzen. Nur die Ermittlung
     der jeweiligen Änderungsmenge bleibt zwangsläufig getrennt (Commit-Zeitpunkt vs.
     Diff-seit-Basis), weil beide etwas grundsätzlich anderes messen.
  2. **Eine Code-Definition für TDD-Gate und Nachweis-Gate.** `edit_gate.py`s Regeln
     (Endungsliste, Verzeichnis-Whitelist, Muster, per `strict_code_gate` überschreibbar) ziehen
     nach `hook_utils.is_gated_code_path` um; `edit_gate.py` delegiert verhaltensgleich. Damit
     gilt für die neue Abdeckungsprüfung exakt dieselbe Definition von "Code", die bereits
     entscheidet, ob eine Datei überhaupt Phase 6 und ein RED-Artefakt verlangt — zwei
     unabhängige "was ist Code"-Listen wären die nächste Drift-Quelle gewesen.
  3. **Basis-Wahl: der jüngere gültige Vorfahre von HEAD.** Der bei `workflow.py start`
     gespeicherte `base_commit` gewinnt nur, wenn er Vorfahre von HEAD ist und
     `merge-base(origin/main, HEAD)` fehlt oder Vorfahre von ihm ist; sonst gewinnt
     `merge-base` — auch bei unvergleichbarer Merge-Historie. Das trennt sowohl den Rebase-Fall (Upstream-Änderungen sollen nicht in der
     eigenen Änderungsmenge auftauchen) als auch den Mehrfach-Workflow-Fall (ein früherer, noch
     nicht gemergter Workflow auf demselben Branch soll nicht mitzählen) korrekt, ohne für jeden
     Fall eine eigene Sonderregel zu brauchen.
  4. **Der Kill-Switch umschließt nur die neue Abdeckung.** `adversary_coverage_gate.enabled:
     false` schaltet ausschließlich Änderungsmenge, Basis-Wahl, Abdeckungsvergleich und
     Teilstaging ab und lässt die bereits produktive #253-Prüfung (Formcheck, Hash-Bindung aus
     #131) sowie die eigenständigen Härtungen F002 bis F004 unangetastet — ein Projekt, das die
     neue, stärkere Regel (noch) nicht will, fällt auf den heutigen, bereits bewährten Stand
     zurück, nicht auf gar keine Prüfung.

## Changelog

- 2026-09-27: Initial spec created
- 2026-09-28: Vom PO freigegeben (`approved`); Testzeilen nach TDD RED eingetragen
- 2026-09-28: Präzisierung nach Adversary-Runde 2 (BROKEN, F101/F102), ohne neue Anforderung.
  §3: Die Commit-Menge vereinigt immer mit dem Index, statt ihn zu ersetzen. `--amend` zählt
  zusätzlich Index und Arbeitsbaum gegen `HEAD~1` und nur als Options-Token. §6: Der Repo-Befund
  im Dateisystem statt der git-Ausgabe entscheidet über „kein Repository“. AC-8 nennt den
  Totalausfall ausdrücklich. Zwei Known Limitations ergänzt, eine präzisiert. Testzeilen von AC-4
  und AC-8 nachgezogen.
