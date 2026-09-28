# Context: fix-260-observable-surface

## Request Summary

Die Schlussfrage „Soll ich den Code committen?" in `core/commands/60-validate.md` soll nur noch
gestellt werden, wenn der Arbeitsstand überhaupt eine beobachtbare Oberfläche hat. Die Prüfung ist
deterministisch (Regeln, kein Modell), arbeitet auf der tatsächlich geänderten Dateiliste aus `git`
und bleibt im Zweifel streng — der PO wird gefragt.

Zweite Hälfte von #147 (Teilauftrag 2 von 4 aus #250). Hälfte 1 ist mit PR #264 ausgeliefert
(v3.33.0): die beiden PO-Tastendrücke nach der Freigabe sind weg. Hier sitzt das restliche Risiko.

## Related Files

| File | Relevance |
|------|-----------|
| `core/commands/60-validate.md` | Z. 230 „Soll ich den Code committen?" — die eine Stelle, an der die Prüfung hängt. Frontmatter-Sperre ist seit Hälfte 1 gelöst |
| `skills/60-validate/SKILL.md` | **Generiert** aus `core/commands/60-validate.md`. Nach jeder Änderung `python3 scripts/sync_skills.py`, sonst blockt `scripts/release_check.py:197–202` den Release |
| `.claude/commands/60-validate.md` | Seit Hälfte 1 nur noch 6-Zeilen-Redirect — **keine** Nachführung nötig |
| `core/hooks/hook_utils.py` | 986 Z., Zielort für `has_observable_surface()`. Kein CLI-Einstieg. Importiert **kein** `subprocess` (Z. 16–22) — muss wie in `bash_gate.py` lokal in der Funktion passieren |
| `core/hooks/workflow.py` | 1855 Z. Dispatch über das `COMMANDS`-Dict (Z. 1813–1839) + `main()` mit `sys.argv[1]`. Neuer Unterbefehl = ein `cmd_*`-Handler plus ein Dict-Eintrag. Kein argparse |
| `config.yaml` | 346 Z., Zielort für Block `observable_surface:`. Vorbild: `e2e_scope` Z. 178–190 |
| `core/hooks/bash_gate.py` | Z. 122–125 Default-Musterlisten als Modul-Konstanten, Z. 444–462 `_detect_e2e_scope()` — Muster für „Config-Wert mit Konstanten-Fallback" |
| `scripts/ci_spec_gate.py` | Z. 123–134 `_changed_files_from_git()`: `git merge-base <base> HEAD` → `git diff --name-only <ref>...HEAD`. Die im Repo vorhandene Basis-Stand-Ermittlung, direkt übertragbar |
| `core/hooks/config_loader.py` | Z. 128–157 `load_config()` mit `lru_cache`. Merged Defaults + `config.yaml` + `settings.local.json` — **nicht** die Modul-Configs |
| `modules/home-assistant/hooks/lovelace_screenshot_gate.py` | Z. 81–83 `is_lovelace_file()`: `'lovelace/' in path and path.endswith('.yaml')`, verlangt Vorher/Nachher-Screenshots |
| `modules/ios-swiftui/config.yaml` | Z. 20–23 führt `.xcstrings`, `.xcassets/`, `Localizable.strings` unter `always_allowed` — genau die Dateien, die sichtbaren Text ändern |
| `docs/context/fix-147-validierung-abstufen.md` | Die vollständige Analyse inklusive Befunde N1–N10 des `analysis-challenger` vom 2026-09-27 |
| `docs/specs/fix-147-validierung-abstufen.md` | Spec der ersten Hälfte, enthält ADR-0147 (Konvention: ADR-Nummer = Issue-Nummer → hier ADR-0260) |

## Existing Patterns

- **Musterlisten-Config mit Konstanten-Fallback:** Modul-Konstante als Default, Wert aus
  `config.get("<block>", {}).get("<key>", DEFAULT)`, Treffer über `re.search`. Beleg:
  `bash_gate.py` Z. 122–125 und Z. 444–462. `config_loader.get_default_config()` (Z. 195 ff.)
  enthält `e2e_scope` bewusst **nicht** — die Defaults leben im Code, nicht in der Default-Config.
- **Basis-Stand:** `merge-base <base> HEAD`, dann `diff --name-only <merge-base>...HEAD`.
  Beleg: `ci_spec_gate.py` Z. 123–134. Dort fail-open mit Warnung — hier muss dieselbe Stelle
  fail-**closed** werden.
- **CLI-Unterbefehl in `workflow.py`:** Handler `cmd_<name>(args: list)`, Eintrag im `COMMANDS`-Dict.
  Kein argparse, kein Hilfstext-Generator.
- **Tests:** `tests/test_*.py`, pytest, kein `conftest.py`. Gates werden als **Subprozess** mit
  gesetztem `cwd` getestet, weil `config_loader.load_config()` und `find_project_root()`
  `lru_cache`-behaftet sind (belegt und begründet in `tests/test_loc_gate_config_source_153.py`
  Docstring). Für `has_observable_surface()` heißt das: ein echtes Wegwerf-Repo je Testfall.

## Dependencies

- **Upstream:** `git` (merge-base, diff, ls-files, symbolic-ref), `config_loader.load_config()`,
  `hook_utils.find_worktree_root()` — die Messung muss im Worktree stattfinden, nicht im Hauptrepo
  (gleiche Fehlerklasse wie #96/#144/#155, dokumentiert in `bash_gate._measurement_root()`).
- **Downstream:** `core/commands/60-validate.md` (und damit `skills/60-validate/SKILL.md`) ist der
  einzige Aufrufer. Kein Hook ruft die Funktion, kein Gate blockt daran.
- **Nicht abhängig von #247:** Die Dateiliste kommt aus `git`, nicht aus `affected_files`.

## Existing Specs

- `docs/specs/fix-147-validierung-abstufen.md` — erste Hälfte, ADR-0147, Begründung des
  Gesamtvorhabens
- `docs/specs/fix-140-po-decision-gates.md` — der Beschluss, der mit #147 teilweise revidiert wurde
- Zum Dachvorgang #250 existiert **keine** Spec unter `docs/specs/` — der Befund F1/R4 („`workflow_type`
  wird in `/00-intake` gesetzt, bevor ein Diff existiert") ist nur im Issue-Text von #250/#260
  festgehalten

## Risks & Considerations

- **R1 (Hauptrisiko, = N9):** Die Default-Musterlisten wirken in Fremdprojekten. Ein generisches
  `\.yaml$` unter `non_surface_patterns` verschluckt Home-Assistant-Dashboards; ein generisches
  „Ressourcen"-Muster verschluckt `.strings`/`.xcstrings`. Die Default-`non_surface_patterns`
  dürfen **keine** pauschale YAML- oder Ressourcen-Regel enthalten.
- **R2 (= N7):** `all([])` ist `True`. Wörtlich gebaut liefert „jede Datei trifft
  `non_surface_patterns`" bei leerer Liste „keine Oberfläche" — das Gegenteil von streng. Leere
  Liste muss **zuerst** geprüft werden. Eigener Test, vor dem Surface-Treffer-Fall.
- **R3 (= N8):** Es gibt keinen gespeicherten Basis-Stand (`merge-base|base_commit|base_sha` findet
  nichts in `workflow.py`). `git diff HEAD` ist in Phase 7 leer, weil dort schon eingecheckt ist →
  stiller Fehlschluss in die unsichere Richtung. Basis muss konfigurierbar
  (`observable_surface.base_branch`) **und** automatisch erkennbar sein
  (`git symbolic-ref refs/remotes/origin/HEAD`), Fallback streng — sonst ist die Funktion in jedem
  `master`/`develop`-Projekt dauerhaft streng und damit nutzlos.
- **R4 (= N4):** Zwei Listen sind Pflicht. Der PO-Block entfällt nur, wenn **jede** Datei in
  `non_surface_patterns` trifft **und keine** in `surface_patterns`. Unbekannte Endung, leere Liste,
  `git`-Fehler, Config-Ladefehler → streng.
- **R5 (= N10):** `is_code_file()` (Z. 680–688) ist die falsche Achse und darf nicht wiederverwendet
  werden. „Code" ≠ „Oberfläche": ein `.swift`-Service hat keine, eine `.strings`-Datei hat eine.
- **R6:** `config_loader` merged Modul-Configs nicht. Modulprojekte müssen ihre `surface_patterns`
  selbst in die Projekt-`config.yaml` eintragen — gehört dokumentiert, nicht stillschweigend.
- **R7:** Die Schlussfrage hat schon eine Ausnahme („dokumentierte Autonomie",
  `60-validate.md` Z. 198–212). Die neue Prüfung stellt sich **daneben**, nicht dagegen.
- **R8 (Prozess):** Skill-Drift. `skills/60-validate/SKILL.md` ist generiert; ohne
  `scripts/sync_skills.py` blockt `release_check.py` — und `skills/` nie direkt editieren.

## Type

Feature (Standard Track, Score 3: Scope Medium, Blast Radius High, Unsicherheit Low)

---

## Analysis

Stand 2026-09-27. Der `analysis-challenger` hat den technischen Entwurf angegriffen (Befunde
C1–C8, Verdict NEEDS REVIEW); C4 und C6 wurden am Code nachgeprüft und bestätigt. Zwei Fragen
gingen an den PO, beide sind entschieden (siehe „PO-Entscheidungen").

### Type

Feature (Standard Track). Kein Bug — es gibt kein Fehlverhalten, sondern eine Frage, die zu oft
gestellt wird.

### PO-Entscheidungen 2026-09-27

- **E1 — Befehlstexte gelten als beobachtbare Oberfläche.** Reine Hook-, Test- und
  Doku-Änderungen laufen ohne Rückfrage durch. Ändert sich der Text, den der PO beim Tippen
  eines Slash-Befehls liest (`core/commands/*.md`, `.claude/commands/*.md`,
  `skills/*/SKILL.md`, `CLAUDE.md`), wird gefragt. Begründung: diesen Text kann der PO lesen
  und beurteilen, Python-Hooks nicht.
  **Folge:** Die DoD-Zeile in #260 („Reine Hook-/Test-/Doku-Änderung in diesem Repo →
  Schlussfrage entfällt") wird in der Spec präzisiert — „Doku" schließt Befehlsdefinitionen
  ausdrücklich **nicht** ein. Damit ist C1 aufgelöst; C2 bleibt bewusst bei „Hooks = unsichtbar".
- **E2 — Eine Auslieferung, nicht zwei.** Die Überschreitung der Scoping-Limits (7 Dateien,
  ca. +420 LoC) ist akzeptiert, weil die Teile einzeln nutzlos sind (Funktion ohne Aufrufer
  ändert nichts, Aufrufer ohne Funktion bricht) und ~200 der Zeilen die von der DoD geforderten
  Tests sind. Ohne Tests, generierte Datei und CHANGELOG: 4 Dateien, ~185 LoC — innerhalb der
  Grenze.

### Affected Files (with changes)

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | `has_observable_surface() -> tuple[bool, str]`, Helfer für Basis-Stand und Dateiliste, zwei Default-Musterlisten als Modul-Konstanten. `subprocess` lokal in der Funktion importieren (Modul importiert es nicht, Z. 16–22) |
| `core/hooks/workflow.py` | MODIFY | Handler `cmd_observable_surface(args)` + Eintrag `"observable-surface"` im `COMMANDS`-Dict (Z. 1813–1837). Kein argparse |
| `config.yaml` | MODIFY | Block `observable_surface:` mit `enabled`, `surface_patterns`, `non_surface_patterns`, `base_branch` + Kommentar, dass Modulprojekte eigene `surface_patterns` ergänzen müssen (R6) |
| `core/commands/60-validate.md` | MODIFY | Pflicht-Aufruf als fenced bash-Block vor der Zusammenfassung; Ersatztext für alle vier Kombinationen Oberfläche × Autonomie (C8); Z. 230 Schlussfrage wird bedingt |
| `skills/60-validate/SKILL.md` | MODIFY (generiert) | `python3 scripts/sync_skills.py` — nie direkt editieren, sonst blockt `scripts/release_check.py:197–202` den Release (R8) |
| `tests/test_observable_surface_260.py` | CREATE | Je ein Test pro Vertragsschritt + die vier DoD-Fälle. Subprozess mit eigenem Wegwerf-Repo je Fall, weil `load_config()`/`find_project_root()` `lru_cache` tragen |
| `CHANGELOG.md` | MODIFY | Eintrag unter [Unreleased] |

**Nicht angefasst:** `.claude/commands/60-validate.md` (seit Hälfte 1 nur 6-Zeilen-Redirect),
`core/hooks/bash_gate.py` (kein Gate — siehe verworfene Alternative V4),
`config_loader.get_default_config()` (Defaults leben im Code, nicht in der Default-Config —
Vorbild `e2e_scope`).

### Scope Assessment

- Files: 7 (4 davon inhaltlich, 1 generiert, 1 Test, 1 CHANGELOG)
- Estimated LoC: +420/-5 — davon ~200 Tests, ~35 generiert
- Risk Level: **MEDIUM** — die Default-Musterlisten wirken in Fremdprojekten (iOS/SwiftUI,
  Home Assistant). Jeder Fehler zeigt sich dort als *fehlende* Rückfrage, also stumm. Deshalb
  ist jede Abweichung vom Erwarteten auf „streng" gelegt und die Surface-Liste enthält die
  Modul-Muster vorsorglich mit.

### Technical Approach

**Vertrag `hook_utils.has_observable_surface() -> tuple[bool, str]`**

`True` = „hat oder könnte haben" → PO wird gefragt (streng). `False` = „sicher keine" → die
Schlussfrage entfällt. Zweites Element ist die Begründung für die CLI-Ausgabe. Die Reihenfolge
der Prüfungen ist Teil des Vertrags, nicht Implementierungsdetail:

1. Config-Block vorhanden, aber unbrauchbar geformt (Musterlisten keine Liste aus Strings,
   `base_branch` kein String) → `(True, "config-invalid")`
2. `enabled` ist falsch → `(True, "disabled")`
3. Messwurzel = `find_worktree_root() or find_project_root()` — die Messung findet im Worktree
   statt, nicht im Hauptrepo (Fehlerklasse #96/#144/#155)
4. Basis-Stand nicht auflösbar → `(True, "no-base")`
5. Irgendein `git`-Aufruf mit Rückgabecode ≠ 0 → `(True, "git-error")`
6. Dateiliste **leer** → `(True, "empty-list")` — muss **vor** 7 und 8 stehen, weil `all([])`
   `True` ist (R2/N7)
7. Irgendeine Datei trifft `surface_patterns` → `(True, "<datei> trifft surface")`
8. **Jede** Datei trifft `non_surface_patterns` → `(False, "alle N Dateien ohne Oberfläche")`
9. Sonst (unbekannte Endung) → `(True, "<datei> unbekannt")`

**Basis-Stand (R3/N8, Formulierung nach C3):** erst `observable_surface.base_branch` aus der
Config, wenn gesetzt; sonst der **stdout-Wert** von `git symbolic-ref --short
refs/remotes/origin/HEAD`. Es gibt **keinen** literalen Rückfallwert wie `"origin/main"` — ist
der Befehl erfolglos oder sein stdout leer, greift sofort Schritt 4 (streng). Danach `git
merge-base <base> HEAD`; Rückgabecode ≠ 0 oder leerer stdout → streng. Damit sind detached HEAD,
Repo ohne Remote und unabhängige Historie abgedeckt.

**Dateiliste — Vereinigung aus vier Quellen,** weil in Phase 7 je nach Stand alles oder nichts
eingecheckt ist: `git diff --name-only <merge-base>...HEAD`, `git diff --name-only --cached`,
`git diff --name-only`, `git ls-files --others --exclude-standard`.

**Default-`surface_patterns`** (wirken in allen Projekten; eine zu breite Surface-Liste macht
die Prüfung nur strenger, nie lockerer — deshalb sind die Modul-Muster vorsorglich enthalten,
obwohl `config_loader` Modul-Configs nicht merged, R6):
`(^|/)core/commands/.*\.md$`, `(^|/)\.claude/commands/.*\.md$`, `(^|/)skills/[^/]+/SKILL\.md$`,
`(^|/)CLAUDE\.md$` (E1) · `(^|/)lovelace/.*\.ya?ml$` (HA-Dashboards, N9) ·
`\.(strings|xcstrings)$`, `\.xcassets/` (iOS sichtbarer Text und Bildmaterial, N10).

**Default-`non_surface_patterns`:** `^docs/`, `^tests?/`, `(^|/)test_[^/]+\.py$`,
`(^|/)[^/]+_test\.(py|go|js|ts)$`, `(^|/)[^/]+Tests?\.swift$`, `^core/hooks/`, `^scripts/`,
`^\.github/`, `(^|/)(CHANGELOG|README|CONTRIBUTING)\.md$`, `(^|/)\.gitignore$`,
`(^|/)\.editorconfig$`.
**Bewusst NICHT enthalten** (C1/R1/N9/N10): kein pauschales `\.md$`, kein pauschales
`^\.claude/`, keine YAML-Regel, keine „Ressourcen"-Regel. Was keine Liste trifft, ist
„unbekannt" und damit streng (Schritt 9) — diese Regel trägt die gesamte Sicherheit des leeren
`surface_patterns`-Falls und braucht deshalb einen eigenen Test, damit ein späteres Refactoring
sie nicht stillschweigend umdreht.

**`is_code_file()` (Z. 680–688) wird nicht wiederverwendet** (R5/N10): „Code" ist die falsche
Achse. Ein `.swift`-Service hat keine Oberfläche, eine `.strings`-Datei hat eine.

**CLI `workflow.py observable-surface`** — Ausgabe auf stdout, Rückgabecode immer 0:

```
OBSERVABLE_SURFACE=yes|no
REASON=<begründung>
FILES=<anzahl geprüft>
ROOT=<messwurzel>
CONFIG=<quelle laut config_source_note()>
```

Die Zeilen `ROOT=`/`CONFIG=` sind die Antwort auf C6: `load_config()` löst über
`find_project_root()` auf den **Haupt**-Ordner auf (`hook_utils.py:725–744`), die Messung läuft
dagegen im Worktree. Ein `observable_surface`-Eintrag, der nur im Worktree steht — also auch
der, den dieser Vorgang selbst schreibt — wirkt erst nach dem Zusammenführen. Ohne diese Zeilen
wiederholt sich #153 unter neuem Namen; `config_loader.config_source_note()` (Z. 90) ist das
etablierte Vorbild, `edit_gate.py:379–380` der bestehende Aufrufer.

**Anbindung in `core/commands/60-validate.md`** — der Aufruf steht als fenced bash-Block
(Vorbild Z. 172–174), mit dem ausdrücklichen Satz, dass keine eigene Einschätzung den Aufruf
ersetzt. Fehlt die Zeile `OBSERVABLE_SURFACE=no` in der Ausgabe — aus welchem Grund auch immer,
auch bei Absturz oder ausgebliebenem Aufruf — wird gefragt. Die vier Kombinationen mit der
bestehenden Autonomie-Ausnahme (Z. 198–212, R7/C8) werden wörtlich ausgeschrieben:

| Oberfläche | Autonomie dokumentiert | Schlusszeile |
|---|---|---|
| `yes` | nein | „Soll ich den Code committen?" — unverändert wie heute |
| `yes` | ja | Ankündigung „schreibe fest und deploye", Kette im selben Turn (heute schon so) |
| `no` | nein | **neu:** Ankündigung „schreibe jetzt fest", keine Frage |
| `no` | ja | Ankündigung „schreibe fest und deploye" — identisch zur Zeile darüber |

Die Autonomie-Regel sticht also; die neue Prüfung wirkt in genau einer der vier Zeilen.

### Dependencies

- **Upstream:** `git` (`merge-base`, `diff`, `ls-files`, `symbolic-ref`),
  `config_loader.load_config()` + `config_source_note()`, `hook_utils.find_worktree_root()`
- **Downstream:** `core/commands/60-validate.md` → `skills/60-validate/SKILL.md` ist der
  **einzige** Aufrufer. Kein Hook ruft die Funktion, kein Gate blockt daran
- **Nicht abhängig von #247** (Dateiliste aus `git`, nicht aus `affected_files`)

### Geprüfte Alternativen

- **V1 (gewählt):** Zwei Musterlisten + git-Dateiliste, im Zweifel streng.
- **V2 — nur eine Liste (`surface_patterns`), Frage entfällt wenn keine Datei trifft.** Weniger
  Konfiguration, aber unbekannte Endungen fielen dann auf „keine Oberfläche" — fail-open in
  genau die Richtung, die weh tut. Verworfen.
- **V3 — leere Default-Listen, jedes Projekt trägt selbst ein.** Maximal sicher, aber ohne
  Projektarbeit wirkungslos: dieses Repo hätte keinen Nutzen, bis jemand die Listen schreibt.
  Verworfen, weil der Nutzen dann nur auf dem Papier steht.
- **V4 — `bash_gate.py` erzwingt den Nachweis, dass die Prüfung lief** (Vorbild
  `check_dialog_evidence`, C5b). Wäre technisch der stärkere Zwang, baut aber eine neue
  Sperrmechanik für eine Prüfung, die nur eine Frage *unterdrückt* statt etwas zu erlauben —
  ein Ausfall des Nachweises würde einen Commit blocken, obwohl der sichere Zustand „einfach
  fragen" ist. Verworfen; als eigener Vorgang nachzuholen, falls sich zeigt, dass der Aufruf in
  der Praxis übersprungen wird.
- **V5 — Pflichtfeld „Observable Surface: ja/nein" in der Spec,** erzwungen wie AC-N.
  Ehrlichste Quelle, verlagert die Entscheidung aber auf einen Menschen, der sie vergessen kann
  — dieselbe Falle wie das tote `is_new_ui`. Verworfen nach „Regeln vor Modell", bleibt
  dokumentierte Option.
- **V6 — Abstufung am `workflow_type`.** In #250 (F1/R4) verworfen: wird in `/00-intake`
  gesetzt, bevor überhaupt ein Diff existiert.

### Aus dem Challenger übernommen / bewusst anders entschieden

| Befund | Umgang |
|---|---|
| C1 (`\.md$`/`^\.claude/` schlucken Befehlstexte) | **übernommen** — Pauschalen entfernt, Befehlstexte in `surface_patterns` (E1) |
| C2 (`^core/hooks/` ist in diesem Repo sichtbar) | **bewusst anders** — Hooks bleiben „unsichtbar". Ihre Wirkung kann der PO am Text nicht beurteilen; genau dort ist die Frage leer |
| C3 (Basis-Stand-Formulierung) | **übernommen** — Wert ist der stdout, es gibt keinen literalen Rückfall |
| C4 (`config-error` unerreichbar) | **übernommen und am Code bestätigt** (`config_loader.py:146–152`): kaputtes YAML wirft nicht, es warnt und fällt auf Code-Defaults zurück. Schritt 1 prüft daher die **Form** des geladenen Blocks — das ist erreichbar und testbar. Der stille YAML-Rückfall wird in der Spec benannt und als hinnehmbar begründet (Code-Defaults sind selbst streng) |
| C5 (nichts erzwingt den Aufruf) | **teils übernommen** — fenced Block + „keine eigene Einschätzung ersetzt den Aufruf" + fehlende Zeile ⇒ fragen. Gate: siehe V4 |
| C6 (Config-Quelle unsichtbar, #153-Wiederholung) | **übernommen und am Code bestätigt** — `ROOT=`/`CONFIG=` in der CLI-Ausgabe |
| C7 (Testbarkeit Schritt 1) | mit C4 gelöst — Formprüfung ist als Subprozess-Test baubar |
| C8 (Autonomie × Oberfläche) | **übernommen** — alle vier Kombinationen wörtlich in `60-validate.md` |

### Test Plan (Umriss für /30-write-spec)

Je ein Subprozess-Test mit eigenem Wegwerf-Repo: Schritt 1 Formfehler · Schritt 2
`enabled: false` · Schritt 4 kein `origin/HEAD` und kein `base_branch` · Schritt 5
`git`-Fehler · Schritt 6 leere Liste (**vor** dem Surface-Fall) · Schritt 7 Surface-Treffer ·
Schritt 8 alles unsichtbar (reine Hook-/Test-Änderung in diesem Repo → `no`, DoD) · Schritt 9
unbekannte Endung · `lovelace/x.yaml` → `yes` (DoD) · `Localizable.strings` und `de.xcstrings`
→ `yes` (DoD) · `core/commands/60-validate.md` → `yes` (E1) · unversionierte Datei allein →
wird gesehen.

### ADR

ADR-0260 (Konvention: ADR-Nummer = Issue-Nummer). Zu begründen: warum die Erkennung
deterministisch aus `git` kommt statt aus Buchführung, warum im Zweifel streng, warum Hooks als
unsichtbar und Befehlstexte als sichtbar gelten (E1), und dass ADR-0147 damit nicht gekippt,
sondern vervollständigt wird.

### Open Questions

Keine. Die beiden Entscheidungen E1 und E2 sind vom PO getroffen (2026-09-27).
