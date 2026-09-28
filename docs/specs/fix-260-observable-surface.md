---
entity_id: fix-260-observable-surface
type: module
created: 2026-09-27
updated: 2026-09-27
status: draft
version: "1.0"
tags: [validation, git, config]
workflow: fix-260-observable-surface
test_targets: ["tests/test_observable_surface_260.py"]
---

# Beobachtbare Oberfläche erkennen — Schlussfrage in /60-validate abstufen (Issue #260)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #260 — Zweite Hälfte von #147 (Teilauftrag 2 von 4 aus #250). Hälfte 1 ist mit
  PR #264 ausgeliefert (v3.33.0): die beiden PO-Tastendrücke nach der Freigabe (`/50-implement`,
  `/60-validate`) sind weg. Issue #260 trägt das restliche Risiko dieses Vorhabens: die
  Schlussfrage „Soll ich den Code committen?" in `core/commands/60-validate.md` wird heute immer
  gestellt, auch wenn eine Änderung ausschließlich Hooks, Tests oder interne Doku betrifft — für
  diesen Fall gibt es nichts Sichtbares, das der PO beurteilen könnte. Die Prüfung muss
  deterministisch sein (Regeln statt Modell, siehe „Regeln vor Modell" in den globalen
  Zusammenarbeitsregeln) und im Zweifel streng bleiben.

## Purpose

`has_observable_surface()` entscheidet anhand der tatsächlich geänderten Dateiliste aus `git`,
ob ein Arbeitsstand überhaupt eine für den PO beobachtbare Oberfläche verändert. Nur wenn das
sicher verneint werden kann, entfällt die Schlussfrage in `/60-validate` und Claude kündigt
stattdessen an, den Code jetzt festzuschreiben. In jedem anderen Fall — inklusive jeder Form von
Unsicherheit — bleibt die Rückfrage bestehen. Die Funktion ersetzt keine bestehende Prüfung,
sondern ergänzt die bereits vorhandene Autonomie-Ausnahme in `/60-validate` um eine zweite,
unabhängige Bedingung.

## Source

- **File:** `core/hooks/hook_utils.py`
- **Identifier:** neue Funktion `has_observable_surface() -> tuple[bool, str]`
- **File:** `core/hooks/workflow.py`
- **Identifier:** neuer Unterbefehl `observable-surface`, Handler `cmd_observable_surface(args)`
- **File:** `core/commands/60-validate.md`
- **Identifier:** Abschnitt unmittelbar vor der Schlussfrage „Soll ich den Code committen?"

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `config_loader.load_config()` / `config_loader.config_source_note()` | function | Liefert den `observable_surface`-Config-Block; `config_source_note()` macht sichtbar, dass Config-Werte immer aus dem Hauptrepo geladen werden, auch in Worktree-Sitzungen (dieselbe Fehlerklasse wie #153) |
| `hook_utils.find_worktree_root()` / `hook_utils.find_project_root()` | function | Messwurzel = Worktree zuerst — die Dateiliste muss im tatsächlichen Arbeitsbaum ermittelt werden, nicht im Hauptrepo (Fehlerklasse #96/#144/#155) |
| `git` (`merge-base`, `diff --name-only`, `ls-files --others --exclude-standard`, `symbolic-ref --short refs/remotes/origin/HEAD`) | Systemwerkzeug | Einzige Quelle der geänderten Dateiliste und des Basis-Stands — keine eigene Buchführung (kein Spec-Feld, kein `workflow_type`) |
| `scripts/ci_spec_gate.py::_changed_files_from_git()` | bestehendes Muster | Vorbild für die Basis-Stand-Ermittlung (`merge-base` → `diff --name-only`); dort fail-open mit Warnung, hier bewusst fail-closed |
| `core/hooks/bash_gate.py` (`E2E_*_PATTERNS`, `_detect_e2e_scope()`) | bestehendes Muster | Vorbild „Musterliste als Modul-Konstante mit Config-Override über `config.get(...)`" |
| `docs/specs/fix-147-validierung-abstufen.md` (ADR-0147) | Spec | Hälfte 1 desselben Issues #147 — ADR-0260 vervollständigt ADR-0147, kippt es nicht |
| `core/commands/60-validate.md` → `skills/60-validate/SKILL.md` | Downstream-Aufrufer | Einziger Aufrufer des neuen CLI-Unterbefehls. `skills/60-validate/SKILL.md` ist generiert (`python3 scripts/sync_skills.py`) und wird nie direkt editiert |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/hook_utils.py` | MODIFY | `has_observable_surface() -> tuple[bool, str]` plus Helfer für Basis-Stand und Dateiliste; zwei Default-Musterlisten als Modul-Konstanten. `subprocess` wird lokal in der Funktion importiert (das Modul importiert es heute nicht, Z. 16–22) |
| `core/hooks/workflow.py` | MODIFY | Handler `cmd_observable_surface(args)` + Eintrag `"observable-surface"` im `COMMANDS`-Dict (Z. 1813–1837). Kein argparse, Muster wie alle übrigen `cmd_*`-Handler |
| `config.yaml` | MODIFY | Neuer Block `observable_surface:` mit `enabled`, `surface_patterns`, `non_surface_patterns`, `base_branch`, plus Kommentar, dass Modulprojekte ihre eigenen `surface_patterns` selbst ergänzen müssen (Modul-Configs werden von `config_loader` nicht gemerged) |
| `core/commands/60-validate.md` | MODIFY | Pflicht-Aufruf als fenced bash-Block vor der Zusammenfassung; die Schlussfrage wird bedingt anhand `OBSERVABLE_SURFACE=yes|no` und der bestehenden Autonomie-Ausnahme formuliert (vier Kombinationen, siehe Implementation Details) |
| `skills/60-validate/SKILL.md` | MODIFY (generiert) | Entsteht ausschließlich durch `python3 scripts/sync_skills.py` aus `core/commands/60-validate.md` — **nie direkt editieren**, sonst blockt `scripts/release_check.py:197–202` den Release |
| `tests/test_observable_surface_260.py` | CREATE | Je ein Subprozess-Test pro Vertragsschritt (1–9) und pro DoD-Fall, jeweils mit eigenem Wegwerf-Git-Repo |
| `CHANGELOG.md` | MODIFY | Neuer Eintrag unter `[Unreleased]` |

**Nicht angefasst:** `.claude/commands/60-validate.md` — seit Hälfte 1 (#147/PR #264) nur noch ein
6-Zeilen-Thin-Redirect, keine Nachführung nötig. `core/hooks/bash_gate.py` bleibt unverändert
(kein neues Gate, siehe verworfene Alternative V4 im ADR unten). `config_loader.get_default_config()`
bleibt unverändert — die Default-Musterlisten leben als Modul-Konstanten im Code, nicht in der
eingebauten Default-Config (Vorbild: `e2e_scope`).

### Estimated Changes

- Files: 7
- LoC: +420/−5

**Scoping-Limit-Überschreitung:** 7 Dateien und +420 LoC liegen über der Hausregel (max. 4–5
Dateien, ±250 LoC). Das ist durch PO-Entscheidung E2 (2026-09-27) gedeckt: Funktion ohne
Aufrufer ändert nichts, Aufrufer ohne Funktion bricht — die Teile sind einzeln nutzlos und dürfen
deshalb nicht getrennt ausgeliefert werden. Rund 200 der +420 Zeilen sind die von der Definition
of Done geforderten automatischen Tests; ohne Tests, generierte Datei und CHANGELOG-Eintrag
verbleiben 4 Dateien mit ca. 185 LoC fachlicher Handarbeit — innerhalb der Grenze.

## Implementation Details

### Vertrag `hook_utils.has_observable_surface() -> tuple[bool, str]`

Rückgabe `(True, grund)` heißt „hat oder könnte eine beobachtbare Oberfläche haben" → die
Schlussfrage bleibt. `(False, grund)` heißt „sicher keine" → die Schlussfrage entfällt. Das
zweite Element ist die menschenlesbare Begründung für die CLI-Ausgabe. **Die Reihenfolge der
neun Prüfungen ist Vertragsbestandteil, nicht Implementierungsdetail** — insbesondere muss die
leere Dateiliste (Schritt 6) vor dem Surface- und dem Non-Surface-Fall (Schritt 7/8) geprüft
werden, weil `all([])` in Python `True` liefert und ein wörtlich gebautes „jede Datei trifft
`non_surface_patterns`" bei leerer Liste sonst fälschlich „keine Oberfläche" ergäbe:

1. Der Config-Block `observable_surface` ist vorhanden, aber unbrauchbar geformt (`surface_patterns`
   oder `non_surface_patterns` ist keine Liste aus Strings, `base_branch` ist gesetzt aber kein
   String) → `(True, "config-invalid")`.
2. `observable_surface.enabled` ist falsch → `(True, "disabled")`.
3. Messwurzel bestimmen: `find_worktree_root() or find_project_root()` — die Messung findet im
   tatsächlichen Arbeitsbaum statt, nicht zwingend im Hauptrepo (Fehlerklasse #96/#144/#155).
4. Basis-Stand nicht auflösbar → `(True, "no-base")`.
5. Irgendein `git`-Aufruf liefert einen Rückgabecode ≠ 0 → `(True, "git-error")`.
6. Die ermittelte Dateiliste ist **leer** → `(True, "empty-list")`. Muss vor Schritt 7 und 8
   geprüft werden (siehe oben).
7. Irgendeine Datei trifft `surface_patterns` → `(True, "<datei> trifft surface")`.
8. **Jede** Datei trifft `non_surface_patterns` → `(False, "alle N Dateien ohne Oberfläche")`.
9. Sonst (mindestens eine Datei mit unbekannter Endung, die weder Surface noch Non-Surface
   trifft) → `(True, "<datei> unbekannt")`.

### Basis-Stand-Ermittlung

Erst `observable_surface.base_branch` aus der Config, falls gesetzt. Sonst der **stdout-Wert**
von `git symbolic-ref --short refs/remotes/origin/HEAD`. Es gibt **keinen** literalen
Rückfallwert wie `"origin/main"` — ist der Befehl erfolglos oder sein stdout leer, greift sofort
Schritt 4 (streng). Erst danach `git merge-base <base> HEAD`; ein Rückgabecode ≠ 0 oder leerer
stdout führt ebenfalls zu Schritt 4/5 (streng). Damit sind detached HEAD, ein Repo ohne Remote
und eine unabhängige Historie abgedeckt, ohne dass die Funktion in einem Fremdprojekt ohne
`main`/`master`-Konvention dauerhaft auf einem falschen Rückfallwert operiert.

### Dateiliste — Vereinigung aus vier `git`-Quellen

Je nach Stand der Phase 7 ist alles, nichts oder nur ein Teil eingecheckt. Die Dateiliste ist
deshalb die Vereinigung aus:

1. `git diff --name-only <merge-base>...HEAD`
2. `git diff --name-only --cached`
3. `git diff --name-only`
4. `git ls-files --others --exclude-standard`

Quelle 4 stellt sicher, dass eine neu angelegte, aber noch unversionierte Datei gesehen wird —
ohne sie würde ein reiner Neuanlage-Fall (noch kein `git add`) fälschlich als „keine Änderung"
erscheinen.

### Default-`surface_patterns` (Modul-Konstante, Config kann überschreiben)

```
(^|/)core/commands/.*\.md$
(^|/)\.claude/commands/.*\.md$
(^|/)skills/[^/]+/SKILL\.md$
(^|/)CLAUDE\.md$
(^|/)lovelace/.*\.ya?ml$
\.(strings|xcstrings)$
\.xcassets/
```

Die ersten vier Muster setzen PO-Entscheidung E1 um: Befehlstexte, die der PO beim Tippen eines
Slash-Befehls liest, gelten als beobachtbare Oberfläche. Die letzten drei Muster stammen aus den
existierenden Modul-Konventionen (`modules/home-assistant/hooks/lovelace_screenshot_gate.py`,
`modules/ios-swiftui/config.yaml` → `always_allowed`) und sind vorsorglich als Default enthalten,
obwohl `config_loader` Modul-Configs nicht automatisch mergt: eine zu breite `surface_patterns`-
Liste macht die Prüfung nur strenger, nie lockerer.

### Default-`non_surface_patterns` (Modul-Konstante, Config kann überschreiben)

```
^docs/
^tests?/
(^|/)test_[^/]+\.py$
(^|/)[^/]+_test\.(py|go|js|ts)$
(^|/)[^/]+Tests?\.swift$
^core/hooks/
^scripts/
^\.github/
(^|/)(CHANGELOG|README|CONTRIBUTING)\.md$
(^|/)\.gitignore$
(^|/)\.editorconfig$
```

**Bewusst NICHT enthalten:** kein pauschales `\.md$`, kein pauschales `^\.claude/`, keine
generische YAML-Regel, keine generische „Ressourcen"-Regel. Eine Datei, die keine der beiden
Listen trifft, ist „unbekannt" und damit streng (Schritt 9) — diese Regel trägt die gesamte
Sicherheit des leeren `surface_patterns`-Falls und braucht deshalb einen eigenen Test, damit ein
späteres Refactoring sie nicht stillschweigend umdreht.

### `is_code_file()` wird nicht wiederverwendet

`hook_utils.is_code_file()` (Z. 680–688) prüft die falsche Achse: „Code" ist nicht dasselbe wie
„Oberfläche". Ein `.swift`-Service ist Code, hat aber keine beobachtbare Oberfläche; eine
`.strings`-Datei ist kein Code im üblichen Sinn, hat aber sehr wohl eine. `has_observable_surface()`
führt deshalb eigene, unabhängige Musterlisten statt `is_code_file()`-Aufrufe zu verzweigen.

### CLI `workflow.py observable-surface`

Ausgabe ausschließlich auf stdout, Rückgabecode **immer 0** (die Funktion liefert eine Auskunft,
kein Gate-Urteil):

```
OBSERVABLE_SURFACE=yes|no
REASON=<begründung aus dem Vertrag>
FILES=<Anzahl geprüfter Dateien>
ROOT=<Messwurzel>
CONFIG=<Quelle laut config_loader.config_source_note()>
```

Die Zeilen `ROOT=`/`CONFIG=` beheben dieselbe Fehlerklasse wie Issue #153:
`config_loader.load_config()` löst über `find_project_root()` bewusst auf den **Haupt**-Ordner
auf, die Messung selbst läuft dagegen im Worktree (`hook_utils.py:725–744`). Ein
`observable_surface`-Eintrag, der nur lokal im Worktree steht — auch der, den dieser Vorgang
selbst in `config.yaml` schreibt — wirkt deshalb erst nach dem Zusammenführen in den Hauptordner.
Ohne diese beiden Zeilen wiederholt sich #153 unter neuem Namen.

### Anbindung in `core/commands/60-validate.md`

Der Aufruf steht als fenced bash-Block vor der Zusammenfassung, mit dem ausdrücklichen Satz, dass
keine eigene Einschätzung Claudes den Aufruf ersetzt. Fehlt die Zeile `OBSERVABLE_SURFACE=no` in
der Ausgabe — aus welchem Grund auch immer, auch bei Absturz oder ausgebliebenem Aufruf — gilt
das als „Oberfläche vorhanden" und die Schlussfrage bleibt bestehen. Die bereits bestehende
Autonomie-Ausnahme (Abschnitt „Autonomen Weiterlauf prüfen", Z. 205–219) besteht unverändert
daneben, nicht anstelle dieser Prüfung. Daraus ergeben sich vier Kombinationen:

| Oberfläche | Autonomie dokumentiert | Schlusszeile |
|---|---|---|
| `yes` | nein | „Soll ich den Code committen?" — unverändert wie heute |
| `yes` | ja | Ankündigung „schreibe fest und deploye", Kette im selben Turn (heute schon so) |
| `no` | nein | **neu:** Ankündigung „schreibe jetzt fest", keine Rückfrage |
| `no` | ja | Ankündigung „schreibe fest und deploye" — identisch zur Zeile darüber |

Die Autonomie-Regel sticht also; die neue Prüfung wirkt in genau einer der vier Zeilen (Oberfläche
`no`, Autonomie nicht dokumentiert).

## Expected Behavior

- **Input:** Der aktuelle Arbeitsbaum (Worktree) mit seiner `git`-Historie gegenüber dem
  aufgelösten Basis-Stand, sowie der `observable_surface`-Config-Block aus `config.yaml`
  (Haupt-Repo-Auflösung).
- **Output:** `has_observable_surface()` liefert `(bool, str)`; `workflow.py observable-surface`
  gibt die fünf Zeilen aus „CLI" oben auf stdout aus und beendet sich immer mit Code 0.
  `core/commands/60-validate.md` formuliert die Schlusszeile gemäß der Vier-Kombinationen-Tabelle.
- **Side effects:** Keine. Die Funktion liest ausschließlich (Config, `git`-Zustand) und schreibt
  nichts in den Workflow-State. Kein Hook ruft sie auf, kein Gate blockt an ihr — sie unterdrückt
  ausschließlich eine Rückfrage, sie erlaubt nichts.

## Known Limitations

- **Kaputtes YAML in `config.yaml` wirft nicht, sondern fällt still auf die Code-Defaults
  zurück** (`config_loader.py:146–152`: `except Exception` protokolliert nur eine Warnung).
  Schritt 1 des Vertrags kann diesen Fall deshalb nicht als eigenen `config-invalid`-Fehler
  erreichen — er prüft stattdessen die **Form** des tatsächlich geladenen Blocks. Das ist
  hinnehmbar, weil die Code-Defaults selbst streng sind (`enabled: true`, die oben dokumentierten
  Musterlisten): ein kaputtes YAML führt nicht zu einem lockeren, sondern zu einem sicheren
  Verhalten.
- **`config_loader` merged keine Modul-Configs.** `modules/home-assistant/config.yaml` und
  `modules/ios-swiftui/config.yaml` fließen nicht automatisch in den `observable_surface`-Block
  ein. Ein Modulprojekt muss seine eigenen `surface_patterns` (bzw. Ergänzungen dazu) selbst in
  die Projekt-`config.yaml` eintragen — das steht als Kommentar im neuen Config-Block, ist aber
  keine automatische Vererbung.
- **`load_config()` löst auf den Hauptordner auf, die Messung läuft im Worktree.** Ein
  Config-Eintrag, der nur lokal in einem Worktree existiert, wirkt für `has_observable_surface()`
  nicht, bis er in den Hauptordner gemergt ist. Die Zeilen `ROOT=`/`CONFIG=` in der CLI-Ausgabe
  machen diese Diskrepanz sichtbar, verhindern sie aber nicht.
- **Nichts erzwingt den Aufruf technisch.** Der fenced bash-Block in `core/commands/60-validate.md`
  ist eine Anweisung an Claude, kein Gate. Ein vollständig ausgebliebener Aufruf ist — anders als
  bei der fehlenden Zeile `OBSERVABLE_SURFACE=no`, die als „streng" gilt — nicht technisch
  blockierbar, ohne ein neues Hook-Gate zu bauen (siehe verworfene Alternative V4 im ADR unten).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Eine reine Hook-/Test-/Doku-Änderung in diesem Repo — **wobei „Doku" laut PO-Entscheidung
  E1 ausdrücklich Befehlsdefinitionen NICHT einschließt** (`core/commands/*.md`,
  `.claude/commands/*.md`, `skills/*/SKILL.md`, `CLAUDE.md` gelten als Oberfläche, nicht als
  unsichtbare Doku) — löst die Schlussfrage „Soll ich den Code committen?" nicht mehr aus;
  Claude kündigt stattdessen an, den Code jetzt festzuschreiben
- [ ] Eine Änderung an `lovelace/*.yaml` (Home-Assistant-Dashboard) löst die Schlussfrage weiterhin aus
- [ ] Eine Änderung an `.strings`/`.xcstrings` (iOS-Lokalisierung, sichtbarer Text) löst die
  Schlussfrage weiterhin aus
- [ ] Die Prüfung ist vollständig regelbasiert (kein Sprachmodell im Entscheidungspfad) und bleibt
  in jedem Zweifelsfall — unbekannte Dateiendung, kein auflösbarer Basis-Stand, `git`-Fehler,
  fehlerhaft geformter oder deaktivierter Config-Block — streng: die Schlussfrage wird gestellt
- [ ] Der Block `observable_surface:` in `config.yaml` ist dokumentiert — mit Kommentar zu jedem
  der vier Schlüssel und dem ausdrücklichen Hinweis, dass Modulprojekte (iOS/SwiftUI,
  Home Assistant) ihre eigenen `surface_patterns` in die Projekt-`config.yaml` eintragen
  müssen, weil `config_loader` Modul-Configs nicht merged (R6)
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (voller Regressionslauf grün, inklusive
  `python3 scripts/sync_skills.py --check`)

## Acceptance Criteria

- **AC-1:** Given ein Wegwerf-Git-Repo mit `config.yaml` → `observable_surface.surface_patterns`
  ist eine Zeichenkette statt einer Liste / When `has_observable_surface()` aufgerufen wird /
  Then liefert es `(True, "config-invalid")`.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-2:** Given ein Wegwerf-Git-Repo mit `observable_surface.enabled: false` / When
  `has_observable_surface()` aufgerufen wird / Then liefert es `(True, "disabled")`, unabhängig
  vom Inhalt der geänderten Dateien.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-3:** Given ein Wegwerf-Git-Repo ohne `origin`-Remote, ohne gesetztes `base_branch` in der
  Config und mit `detached HEAD` / When `has_observable_surface()` aufgerufen wird / Then liefert
  es `(True, "no-base")`.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-4:** Given ein Wegwerf-Git-Repo, in dem der zur Basis-Ermittlung nötige `git`-Aufruf einen
  Rückgabecode ≠ 0 liefert (z. B. `merge-base` gegen eine nicht existierende Referenz) / When
  `has_observable_surface()` aufgerufen wird / Then liefert es `(True, "git-error")`.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-5:** Given ein Wegwerf-Git-Repo, in dem gegenüber dem Basis-Stand keine einzige Datei
  geändert, gestaged oder unversioniert vorhanden ist / When `has_observable_surface()`
  aufgerufen wird / Then liefert es `(True, "empty-list")` — und dieser Fall wird **vor** dem
  Surface-Treffer-Fall (AC-6) geprüft, sodass eine leere Liste niemals über `all([])` fälschlich
  als „keine Oberfläche" durchgeht.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-6:** Given ein Wegwerf-Git-Repo mit genau einer geänderten Datei, die `surface_patterns`
  trifft, neben beliebig vielen Dateien, die `non_surface_patterns` treffen / When
  `has_observable_surface()` aufgerufen wird / Then liefert es `(True, "<datei> trifft surface")`.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-7:** Given ein Wegwerf-Git-Repo, in dem ausschließlich Dateien unter `core/hooks/` und
  `tests/` geändert sind (reine Hook-/Test-Änderung, keine davon trifft `surface_patterns`) /
  When `has_observable_surface()` aufgerufen wird / Then liefert es
  `(False, "alle N Dateien ohne Oberfläche")`.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-8:** Given ein Wegwerf-Git-Repo mit einer geänderten Datei unbekannter Endung, die weder
  `surface_patterns` noch `non_surface_patterns` trifft (z. B. `data/export.csv`) / When
  `has_observable_surface()` aufgerufen wird / Then liefert es `(True, "<datei> unbekannt")`.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-9:** Given ein Wegwerf-Git-Repo mit einer geänderten Datei `lovelace/dashboard.yaml` /
  When `has_observable_surface()` aufgerufen wird / Then liefert es `(True, ...)`.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-10:** Given ein Wegwerf-Git-Repo mit geänderten Dateien `Localizable.strings` und
  `de.xcstrings` / When `has_observable_surface()` aufgerufen wird / Then liefert es für beide
  Dateitypen `(True, ...)`.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-11:** Given ein Wegwerf-Git-Repo mit einer geänderten Datei `core/commands/60-validate.md`
  / When `has_observable_surface()` aufgerufen wird / Then liefert es `(True, ...)` (PO-Entscheidung
  E1: Befehlstexte gelten als Oberfläche, nicht als Doku).
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-12:** Given ein Wegwerf-Git-Repo mit genau einer neu angelegten, noch nicht mit `git add`
  versehenen Datei (`git ls-files --others --exclude-standard` liefert sie, `git diff` nicht) /
  When `has_observable_surface()` aufgerufen wird / Then wird diese Datei in die geprüfte
  Dateiliste aufgenommen und fließt in die Entscheidung ein.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-13:** Given ein beliebiger der obigen Fälle / When `python3 core/hooks/workflow.py
  observable-surface` in diesem Wegwerf-Repo ausgeführt wird / Then enthält stdout genau die
  fünf Zeilen `OBSERVABLE_SURFACE=`, `REASON=`, `FILES=`, `ROOT=`, `CONFIG=` in dieser
  Reihenfolge, und der Rückgabecode ist 0.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-14:** Given `core/commands/60-validate.md` nach Umsetzung / When der fenced bash-Block vor
  der Zusammenfassung eine Ausgabe **ohne** die Zeile `OBSERVABLE_SURFACE=no` liefert (fehlende
  Zeile, Absturz, oder `OBSERVABLE_SURFACE=yes`) und keine dokumentierte Autonomie vorliegt /
  Then enthält der Befehlstext die ausdrückliche Anweisung, in diesem Fall die Schlussfrage
  „Soll ich den Code committen?" zu stellen, statt zu übergehen.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

## Test Plan

Pytest gibt es nur im projekteigenen venv, `pyyaml` ist Pflicht (sonst brechen Testmodule schon
beim Einsammeln ab):

```
/opt/homebrew/bin/python3.13 -m venv "$SCRATCHPAD/venv"
"$SCRATCHPAD/venv/bin/pip" install pytest pyyaml
"$SCRATCHPAD/venv/bin/pytest" tests/test_observable_surface_260.py -q
```

Alle Tests laufen als **Subprozess mit eigenem Wegwerf-Git-Repo pro Fall** (`git init` in
`tmp_path`, gezielte Commits/Working-Tree-Änderungen, dann `python3 <repo>/core/hooks/workflow.py
observable-surface` mit `cwd=tmp_path`). Begründung: `config_loader.load_config()` und
`hook_utils.find_project_root()` tragen `@lru_cache(maxsize=1)` — ein In-Prozess-Test mit
mehreren Konfigurationsständen in derselben Python-Session würde den gecachten Stand des ersten
Falls für alle folgenden Fälle wiederverwenden. Belegt und begründet im Docstring von
`tests/test_loc_gate_config_source_153.py`, das für dieselbe Fehlerklasse bereits denselben
Subprozess-Ansatz nutzt.

- `pytest tests/test_observable_surface_260.py -k config_invalid` (AC-1)
- `pytest tests/test_observable_surface_260.py -k disabled` (AC-2)
- `pytest tests/test_observable_surface_260.py -k no_base` (AC-3)
- `pytest tests/test_observable_surface_260.py -k git_error` (AC-4)
- `pytest tests/test_observable_surface_260.py -k empty_list` (AC-5)
- `pytest tests/test_observable_surface_260.py -k surface_match` (AC-6)
- `pytest tests/test_observable_surface_260.py -k all_non_surface` (AC-7)
- `pytest tests/test_observable_surface_260.py -k unknown_extension` (AC-8)
- `pytest tests/test_observable_surface_260.py -k lovelace` (AC-9)
- `pytest tests/test_observable_surface_260.py -k strings_xcstrings` (AC-10)
- `pytest tests/test_observable_surface_260.py -k commands_md` (AC-11)
- `pytest tests/test_observable_surface_260.py -k untracked_file` (AC-12)
- `pytest tests/test_observable_surface_260.py -k cli_output_format` (AC-13)
- `pytest tests/test_observable_surface_260.py -k validate_asks_without_no_line` (AC-14)
- Regressionslauf: `pytest tests/ -q`
- Drift-Check (Pflicht wegen generierter Datei): `python3 scripts/sync_skills.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** ADR-0260 (Konvention: ADR-Nummer = Issue-Nummer, wie ADR-0147 und ADR-0234)
- **Rationale:**
  1. **Deterministisch aus `git`, nicht aus Buchführung.** Kandidaten wie ein Spec-Feld
     „Observable Surface: ja/nein" oder das bestehende `is_new_ui`-Feld verlagern die
     Entscheidung auf einen Menschen, der sie vergessen kann — exakt dieselbe Falle, die
     `is_new_ui` in der Praxis bereits nutzlos gemacht hat. `workflow_type` scheidet aus, weil er
     in `/00-intake` gesetzt wird, bevor überhaupt ein Diff existiert. Die tatsächlich geänderte
     Dateiliste aus `git` ist dagegen immer vorhanden und kann nicht vergessen werden.
  2. **Im Zweifel streng.** Jede Form von Unsicherheit (fehlerhafte Config, kein Basis-Stand,
     `git`-Fehler, leere Dateiliste, unbekannte Endung) liefert `True` — die Rückfrage bleibt. Der
     einzige Weg zu `False` ist ein positiver Nachweis, dass jede einzelne geänderte Datei
     nachweislich keine Oberfläche berührt. Eine falsch unterdrückte Rückfrage wäre ein stiller
     Fehler, der erst beim PO auffiele, wenn er ihn nicht mehr erwartet; eine unnötig gestellte
     Rückfrage kostet nur einen Tastendruck.
  3. **Hooks gelten als unsichtbar, Befehlstexte als sichtbar (PO-Entscheidung E1).** Der PO kann
     den Text beurteilen, den er beim Tippen eines Slash-Befehls liest — `core/commands/*.md`,
     `.claude/commands/*.md`, `skills/*/SKILL.md`, `CLAUDE.md`. Einen Python-Hook kann er nicht
     lesen und bewerten; dort wäre die Rückfrage inhaltsleer. Diese Asymmetrie ist bewusst und
     nicht dieselbe wie „Code vs. Doku" — Befehlstexte sind formal Doku-Dateien (`.md`), gelten
     hier aber als Oberfläche.
  4. **ADR-0147 wird vervollständigt, nicht gekippt.** ADR-0147 hat die beiden PO-Tastendrücke
     nach der Freigabe abgeschafft und die Erkennung der beobachtbaren Oberfläche ausdrücklich als
     „Hälfte 2, eigener Auftrag mit eigener Gegenprüfung" ausgenommen. Diese Spec liefert genau
     diesen zweiten Teil und ändert an den Festlegungen aus ADR-0147 nichts.

  **Verworfene Alternativen:**
  - **V2 — nur eine Liste (`surface_patterns`), Rückfrage entfällt wenn keine Datei trifft.**
    Unbekannte Dateiendungen fielen dann auf „keine Oberfläche" — fail-open in genau die
    Richtung, die weh tut. Verworfen.
  - **V3 — leere Default-Listen, jedes Projekt trägt selbst ein.** Maximal sicher, aber ohne
    Projektarbeit wirkungslos: dieses Repository hätte ohne fremde Vorarbeit keinen Nutzen.
    Verworfen.
  - **V4 — ein neues Hook-Gate erzwingt den Nachweis, dass die Prüfung lief** (Vorbild
    `adversary_dialog.check_dialog_evidence` aus #253). Wäre technisch der stärkere Zwang, baut
    aber eine neue Sperrmechanik für eine Prüfung, die nur eine Rückfrage *unterdrückt* statt
    etwas zu *erlauben* — ein Ausfall des Nachweises würde einen Commit blocken, obwohl der
    sichere Zustand ohnehin „einfach fragen" ist. Verworfen; als eigener Vorgang nachzuholen,
    falls sich in der Praxis zeigt, dass der Aufruf übersprungen wird.
  - **V5 — Pflichtfeld in der Spec, erzwungen wie eine Acceptance Criterion.** Verlagert die
    Entscheidung auf einen Menschen, der sie vergessen kann — dieselbe Falle wie `is_new_ui`.
    Verworfen nach „Regeln vor Modell".
  - **V6 — Abstufung am `workflow_type`.** Wird in `/00-intake` gesetzt, bevor überhaupt ein Diff
    existiert, und kann deshalb nichts über die tatsächlich geänderten Dateien aussagen.
    Verworfen.

## Changelog

- 2026-09-27: Initial spec created (Issue #260, Hälfte 2 von #147, Teilauftrag 2 von 4 aus #250)
