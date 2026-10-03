---
entity_id: feat-333-bug-typ-entfernen
type: module
created: 2026-10-03
updated: 2026-10-03
status: draft
version: "1.0"
tags: [bug, rueckbau, hooks, alias, "#333", "#250"]
---

# Typ `bug` aus den Hooks entfernen, `/00-bug` löschen, Doku-Reste bereinigen (#333, #250 Teil A, Stufe A2)

## Approval

- [ ] Approved

## Purpose

A1 (#250) hat `/00-intake` zum einzigen Eingang gemacht und `/00-bug` zu einem bloßen Hinweis
zurückgebaut. Die Hooks kennen den Workflow-Typ `bug` aber weiter: Er überspringt Spec, TDD-Rot,
Gegenprüfung und Briefing. Damit bleibt ein stiller Schnellweg ohne Nachweise bestehen. Diese
Änderung entfernt den Typ `bug` aus allen Kern-Gates, löscht `/00-bug` samt Kurz-Aliasen und räumt
die Doku-Reste aus A1 auf. Danach gilt für jede Aufgabe derselbe Weg: `feature` oder `feature-fast`.

## Source

- **File:** `core/hooks/workflow.py`, `core/hooks/edit_gate.py`, `core/hooks/bash_gate.py`,
  `core/hooks/adversary_dialog.py`, `core/hooks/alias_sync.py`, `core/hooks/session_banner.py`, `setup.py`,
  `config.yaml`
- **Identifier:** `cmd_start`, `_validate_transition`, `_check_po_briefing`, TDD-Gate (`is_fast`),
  Commit-Gate 5c, `_FAST_TRACK_TYPES`, `REMOVED_SKILLS`, `find_removed_aliases`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `docs/specs/feat-250-teil-a1-intake-einziger-eingang.md` | Spec | Vorstufe A1; legt fest „Hooks kennen `bug` bis A2" |
| `docs/specs/bug-fix-fast-track.md` | Spec | ursprüngliche Spec des Typs `bug`; bleibt als Historie unverändert |
| `core/hooks/alias_sync.py` | Modul | gemeinsame Quelle für Erzeugen (`setup.py`) und Erkennen (`session_banner.py`) von Kurz-Aliasen |
| `scripts/sync_skills.py` | Script | synct nur Namen, die als Befehl UND Skill existieren; `skills/00-bug/` muss deshalb von Hand mit weg |
| `core/hooks/config_loader.py` | Modul | liefert `fast_track` und `bug_fix` aus `config.yaml` |

## Scope

- **Affected Files (~27):** Hooks `core/hooks/workflow.py`, `edit_gate.py`, `bash_gate.py`,
  `adversary_dialog.py`, `alias_sync.py`, `session_banner.py`; `setup.py`, `config.yaml`; gelöscht:
  `core/commands/00-bug.md`, `skills/00-bug/SKILL.md`, `.claude/commands/00-bug.md`; Doku: `README.md`,
  `CLAUDE.md`, `docs/WORKFLOW_GUIDE.md`, `CHANGELOG.md`; Tests (11 bestehende Dateien angepasst):
  `test_bash_gate_erkennung_299`, `test_adversary_evidence_gate_253`, `test_bash_gate_worktree_commit_155`,
  `test_adversary_coverage_gate_259`, `test_red_marker_phase_gate_f004`, `test_po_briefing_gate`,
  `test_precondition_section_gate`, `test_workflow_finish_alias`, `test_intake_bugs_250a1`,
  `test_skills_sync`, `test_skill_path_resolution`; neu: ein Testmodul `tests/test_bug_typ_entfernt_333.py`
- **Estimated Changes:** ca. +90 / −150 LoC; Hook-Code ca. 25 Zeilen, Alias-Erkennung samt Tests ca. 45.
- **Scoping-Entscheid (PO, 2026-10-03):** Die Änderung überschreitet das Limit von 4–5 Dateien bewusst.
  Der PO hat ausdrücklich entschieden: ein Ticket, ein Workflow, keine Teilung. Die meisten Dateien sind
  Einzeiler, Streichungen oder Löschungen; das gemeinsame Ziel ist „der Typ `bug` und seine Spuren
  verschwinden".

## Implementation Details

Reihenfolge: 1. Hooks und Config mit Rückfall, 2. `start`-Ablehnung, 3. Tests umstellen, 4. `/00-bug`
samt abhängigen Tests löschen, 5. Alias-Erkennung samt Test, 6. Doku und CHANGELOG, 7. Vollsuite.

1. **`workflow.py`**
   - `_check_po_briefing`: Ausnahme nur noch für `feature-fast` (`data.get("workflow_type") == "feature-fast"`).
   - `_validate_transition`: der Zweig `workflow_type == "bug"` → `return None` entfällt.
   - Retro-Ausgabe (~Z.1603) und Report (~Z.1692): `bug` zählt nicht mehr als Fast-Track.
   - `cmd_start`: Usage-Text und Typ-Whitelist führen nur `feature` und `feature-fast`; die
     phase6-Startzweige für `bug` (`spec_approved`/`red_test_done` = True, Ausgabe `[BUG fast-track …]`)
     entfallen. Wird `--type bug` übergeben, endet `start` mit Exit 1 und der Meldung: „Typ `bug`
     wurde entfernt (#333). Fehler laufen über /00-intake; Kleinkram über `--type feature-fast`."
     Diese Meldung ist eigenständig und ersetzt für `bug` die generische „Unknown workflow type"-Zeile.
2. **`edit_gate.py`:** `is_fast` gilt nur für `feature-fast`. Der Schalter liest
   `fast_track.require_tdd` aus der Config und fällt, wenn dieser Schlüssel fehlt, auf
   `bug_fix.require_tdd` zurück (ein Release lang; CHANGELOG-Hinweis). Fehlt beides, gilt der bisherige
   Default.
3. **`bash_gate.py`:** Commit-Gate 5c überspringt das Adversary-Verdict nur noch bei `feature-fast`.
4. **`adversary_dialog.py`:** `_FAST_TRACK_TYPES = ("feature-fast",)`.
5. **`config.yaml`:** Abschnitt `bug_fix:` wird zu `fast_track: require_tdd`. `bug_fix.max_files`
   wird nirgends gelesen und entfällt ersatzlos. Der Kommentar „Activated via --type bug" entfällt.
   Nicht angefasst werden `config_loader.py` `bug_fix_blocker` (generisches Modul-Flag),
   `modules/ios-swiftui/config.yaml` `workflows.bug_fix` (verweist auf ein Prozessdokument) und das
   Spec-Frontmatter `type: bugfix`.
6. **`/00-bug` löschen:** `core/commands/00-bug.md`, `skills/00-bug/` (Verzeichnis), `.claude/commands/00-bug.md`.
   Tabellenzeilen und Erwähnungen in `README.md` (Z.157), `CLAUDE.md` (Z.60, Z.449), `setup.py`
   (Z.733, Z.774), `docs/WORKFLOW_GUIDE.md` (Z.484) fallen weg. `REENTRY_EXEMPT` in
   `tests/test_skills_sync.py` und die Erwartung in `tests/test_skill_path_resolution.py` verlieren `00-bug`.
7. **Verwaiste Kurz-Aliase:** `alias_sync.py` bekommt `REMOVED_SKILLS = ("00-bug",)` und
   `find_removed_aliases(commands_dir)`. Die Funktion meldet nur Dateien, deren Name in der Liste steht
   UND die über `is_alias_file` als Framework-Alias markiert sind (eine eigene, unmarkierte
   `00-bug.md` des Nutzers bleibt unberührt). `setup.py --refresh-aliases` löscht diese Dateien und gibt
   sie aus; `session_banner.py` warnt mit einer Zeile, wie viele entfernte Aliase im Projekt und im
   Home-Verzeichnis liegen und dass `--refresh-aliases` sie aufräumt. Eine generische Erkennung
   „markierter Alias ohne Skill" wurde verworfen: ein älteres Setup würde Aliase von Skills löschen,
   die nur eine neuere Plugin-Version kennt.
8. **Doku-Reste (`docs/WORKFLOW_GUIDE.md`, `README.md`):** Z.201 „außer bug/feature-fast" → „außer
   feature-fast"; Z.268 `bug-intake`-Auslöser `/00-bug` → `/00-intake`; Z.340–344 Abschnitt „Bug-Fix
   (`--type bug`)" entfällt; Z.483 „Track wählen (bug / feature-fast / feature)" → zwei Stufen;
   Config-Tabelle Z.511–512 `bug_fix.require_tdd` → `fast_track.require_tdd`, `bug_fix.max_files`
   entfällt; README Z.93–97 Bug-Beispiel beginnt mit `/00-intake`, nicht mit `workflow.py start`.
9. **Tests umstellen** (Typ `bug` diente dort nur als Gate-Schalter):
   - `test_bash_gate_erkennung_299` (Z.283, 320) und `test_bash_gate_worktree_commit_155` (Z.76–84):
     `bug` → `feature-fast`; das State-JSON wird direkt geschrieben, `_validate_transition` greift nicht.
   - `test_adversary_evidence_gate_253` (Z.547), `test_adversary_coverage_gate_259` (Z.385–400, 719–737),
     `test_precondition_section_gate` (Z.363): Parametrisierungswert `bug` streichen.
   - `test_po_briefing_gate` (Z.293, Test 11): auf `feature-fast` umstellen; die Fixture hat Spec und Freigabe.
   - `test_red_marker_phase_gate_f004` (Z.18): nur Docstring, Wort `bug` streichen.
   - `test_workflow_finish_alias`: Fixture auf `feature-fast` umbauen (siehe Test Plan).
   - `test_intake_bugs_250a1`: Lesen der `BUG`-Datei auf Modulebene und AC-8 entfallen bzw. werden zu
     „`/00-bug` existiert nicht mehr"; die tautologische Zeile 25 (`index("Bugs")` trifft schon Zeile 3)
     entfällt; die AC-5-Suche nach „Manuell testen" bekommt `re.I`.
10. **CHANGELOG** unter `[Unreleased]`: Der A1-Satz „Die Hooks kennen den Typ `bug` bis A2 weiter" wird
    ersetzt durch die Entfernung. Der Eintrag enthält das Rezept für laufende Alt-Workflows:
    `workflow.py set-field workflow_type feature-fast` und den Hinweis auf den Config-Rückfall.

## Expected Behavior

- **Input:** `workflow.py start x --type bug`.
  **Output:** Exit 1 mit eigener Meldung (Typ entfernt, Verweis auf `/00-intake` und `--type feature-fast`);
  es wird kein Workflow angelegt.
- **Input:** Altbestand, ein Workflow-JSON mit `"workflow_type": "bug"` (Archiv oder laufend).
  **Output:** `status`, `switch`, `finish`, Retro und Report laufen ohne Absturz. Der Typ erhält keine
  Sonderbehandlung (alle Vergleiche per `==`/`in`, `wf_type` hat in Retro und Report den Default
  `feature`) und fällt in den `feature`-Pfad: volle Gates. Ein laufender alter `bug`-Workflow kann damit
  in phase6 ohne RED und Spec blockieren.
- **Rezept für laufende Alt-Workflows:** `workflow.py set-field workflow_type feature-fast`.
  Geprüft: `bash_gate` blockt den Aufruf nicht, weil `workflow.py` in der Whitelist der
  State-Integrity-Prüfung steht (`core/hooks/bash_gate.py` ~Z.110); `cmd_set_field` (`workflow.py` ~Z.1208)
  akzeptiert jeden Schlüssel. Lokal (Haupt-Repo und Archiv, 15 Dateien) existiert kein `bug`-Workflow.
- **Input:** `/00-bug` aufgerufen.
  **Output:** Der Befehl existiert nicht mehr; Bugs laufen über `/00-intake`.
- **Side effects:** Ein Kurz-Alias `00-bug.md` (mit Marker) in `~/.claude/commands/` oder
  `<Projekt>/.claude/commands/` wird vom Banner gemeldet und von `setup.py --refresh-aliases` gelöscht.
  `edit_gate` liest `fast_track.require_tdd` und fällt auf `bug_fix.require_tdd` zurück.

## Known Limitations

- Ein laufender Alt-Workflow mit Typ `bug` bekommt volle Gates; das Rezept (`set-field … feature-fast`)
  steht nur im CHANGELOG, nicht in einer Laufzeitmeldung. Bei Konsumenten-Projekten ist unbekannt, ob
  solche Workflows existieren.
- Der Rückfall auf `bug_fix.require_tdd` gilt nur ein Release lang; danach wird der alte Schlüssel ignoriert.
- Verwaiste Aliase mit anderem Namen als `00-bug` oder ohne Marker werden nicht erkannt.
- Der Banner warnt nur, wenn die Sitzung ihn lädt; `--refresh-aliases` muss ausgeführt werden.
- `docs/specs/bug-fix-fast-track.md` und `docs/specs/user-initiated-bug-workflow.md` beschreiben den
  überholten Schnellweg; sie bleiben als Historie unverändert.
- Das LoC-Gate zählt Spec, Kontext und Briefing als Produktivcode (#294); das installierte Plugin 3.34.0
  verlangt für `core/hooks` ohne #322 weiter ein Override.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Kein Hook, kein Befehl und kein Doku-Text kennt noch einen Bug-Schnellweg (Typ `bug`, `--type bug`,
      `/00-bug`), ausgenommen Historie (`docs/specs/bug-fix-fast-track.md`, CHANGELOG-Verlauf)
- [ ] `workflow.py start … --type bug` wird mit einer verständlichen Meldung abgelehnt, die auf `/00-intake`
      und `feature-fast` verweist
- [ ] Ein altes Workflow-JSON mit Typ `bug` lässt sich weiter lesen, wechseln und abschließen
- [ ] Verwaiste `00-bug`-Aliase werden im Banner gemeldet und von `--refresh-aliases` entfernt
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Vollsuite grün)

## Acceptance Criteria

- **AC-1:** Given die Hook-Quellen / When nach dem Typ `bug` als Workflow-Typ gesucht wird / Then
  vergleichen `workflow.py`, `edit_gate.py`, `bash_gate.py` und `adversary_dialog.py` nirgends mehr gegen
  `"bug"`, und `adversary_dialog._FAST_TRACK_TYPES == ("feature-fast",)`
  - Test: `tests/test_bug_typ_entfernt_333.py::test_hooks_know_no_bug_type`
- **AC-2:** Given `workflow.py start x --type bug` / When der Befehl läuft / Then endet er mit Exit 1, die
  Meldung nennt `/00-intake` und `feature-fast` (nicht die generische „Unknown workflow type"-Zeile), und
  es wird keine Workflow-Datei angelegt
  - Test: `tests/test_bug_typ_entfernt_333.py::test_start_type_bug_is_rejected_with_pointer`
- **AC-3:** Given ein Workflow-JSON mit `workflow_type: "bug"` / When `status`, `switch`, `finish` und der
  Retro-Report laufen / Then stürzt keiner ab (Exit 0 bzw. nur reguläre Gate-Meldung, kein Traceback);
  der Typ wird wie `feature` behandelt
  - Test: `tests/test_bug_typ_entfernt_333.py::test_legacy_bug_workflow_json_does_not_crash`
- **AC-4:** Given eine Config mit `fast_track.require_tdd` bzw. nur mit `bug_fix.require_tdd` / When
  `edit_gate` für einen `feature-fast`-Workflow entscheidet / Then gilt `fast_track.require_tdd`,
  und fehlt es, gilt `bug_fix.require_tdd` als Rückfall
  - Test: `tests/test_bug_typ_entfernt_333.py::test_edit_gate_reads_fast_track_with_bug_fix_fallback`
- **AC-5:** Given `config.yaml` / When sie gelesen wird / Then enthält sie `fast_track.require_tdd`, aber
  weder den Abschnitt `bug_fix` noch den Schlüssel `max_files`
  - Test: `tests/test_bug_typ_entfernt_333.py::test_config_has_fast_track_and_no_bug_fix_max_files`
- **AC-6:** Given das Repo / When `core/commands/00-bug.md`, `skills/00-bug/` und `.claude/commands/00-bug.md`
  geprüft werden / Then existiert keine der drei Quellen mehr, und `sync_skills.py --check` meldet keinen Drift
  - Test: `tests/test_intake_bugs_250a1.py::test_00_bug_is_removed` und
    `tests/test_intake_bugs_250a1.py::test_generated_skills_are_in_sync`
- **AC-7:** Given `REMOVED_SKILLS` in `alias_sync.py` und ein Verzeichnis mit einem markierten
  `00-bug.md`, einem unmarkierten `00-bug.md` und einem markierten Alias eines nicht gelisteten Namens /
  When `find_removed_aliases` läuft / Then meldet sie nur das markierte `00-bug.md`; `setup.py
  --refresh-aliases` löscht genau diese Datei und lässt die beiden anderen unberührt; `session_banner.py`
  gibt eine Warnzeile aus
  - Test: `tests/test_bug_typ_entfernt_333.py::test_find_removed_aliases_only_marked_listed_names`,
    `::test_refresh_aliases_deletes_only_removed_marked_alias` und `::test_banner_warns_about_removed_aliases`
- **AC-8:** Given `docs/WORKFLOW_GUIDE.md`, `README.md`, `CLAUDE.md` und `setup.py` / When nach `--type bug`,
  `bug_fix.require_tdd`, `bug_fix.max_files`, „bug / feature-fast / feature", `/00-bug` und dem
  Bug-Fix-Abschnitt gesucht wird / Then kommt nichts davon mehr vor, und das README-Bug-Beispiel beginnt
  mit `/00-intake`
  - Test: `tests/test_bug_typ_entfernt_333.py::test_docs_have_no_bug_fast_track_left`
- **AC-9:** Given `tests/test_intake_bugs_250a1.py` / When die Tests laufen / Then liest das Modul keine
  `BUG`-Datei mehr, enthält keine tautologische `index("Bugs")`-Prüfung, und die Suche nach
  „Manuell testen" ist case-insensitiv (`re.I`)
  - Test: `tests/test_intake_bugs_250a1.py::test_no_bug_fast_track_left_in_commands_or_skills`
    (inhaltlich geschärft)
- **AC-10:** Given `CHANGELOG.md` / When der Abschnitt `[Unreleased]` gelesen wird / Then enthält er den
  Eintrag zur Entfernung samt Rezept `set-field workflow_type feature-fast` und Rückfall-Hinweis, und der
  Satz „Die Hooks kennen den Typ `bug` bis A2 weiter" steht nicht mehr darin
  - Test: `tests/test_bug_typ_entfernt_333.py::test_changelog_replaces_a1_sentence`
- **AC-11:** Given alle umgestellten Tests (`bug` → `feature-fast` bzw. Parametrisierung gestrichen) /
  When die Vollsuite läuft / Then ist sie grün
  - Test: `pytest tests/` (Vollsuite) sowie die 11 angepassten Dateien aus dem Test Plan

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- Neu `tests/test_bug_typ_entfernt_333.py` (AC-1 bis AC-5, AC-7, AC-8, AC-10): Quelltext-Prüfung der vier
  Hooks, `start --type bug` per Subprozess (hermetisch, `CLAUDE_PROJECT_DIR=tmp_path`, Muster
  `test_workflow_finish_alias.py`), Altbestand-JSON (`status`, `switch`, `finish`, Retro), Config-Rückfall,
  `find_removed_aliases` mit drei Fällen, `--refresh-aliases` im `tmp_path`, Banner-Warnzeile, Doku-Suche.
- `tests/test_intake_bugs_250a1.py` (AC-6, AC-9): `00-bug` existiert nicht mehr, `re.I`, Tautologie entfernt.
- `tests/test_workflow_finish_alias.py`: Fixture auf `feature-fast` umbauen. Gelesen in `workflow.py`:
  `cmd_complete` ruft `_validate_transition(data, "phase8_complete")`; für `feature-fast` verlangt das
  `spec_file` (gesetzt), `spec_approved` (True), dann `_check_adr` und `_check_po_briefing`. Konkrete Fixture:
  - `spec_file` zeigt auf eine **existierende** Datei, die der Test unter `tmp_path/docs/specs/x.md`
    anlegt; Inhalt mit Abschnitt `## Architektur-Entscheidung (ADR)` und Zeile `- **ADR-Nr.:** keine`
    (`_check_adr` liest die Datei via `_worktree_first_path`; fehlte die Datei, gäbe `_check_adr` None
    zurück, aber der Test soll den echten Pfad abdecken);
  - `spec_approved: true`;
  - **kein Briefing nötig:** `_check_po_briefing` gibt für `feature-fast` per Default `None` zurück
    (`po_briefing_gate.skip_fast_track` ist standardmäßig an); das Test-`tmp_path` hat keine Config, also
    gilt der Default — kein Kill-Switch nötig;
  - `current_phase`, `context_file`, Ausführungs-Log und übrige Felder wie bisher.
  Die Tests `test_finish_archives_like_complete` und `test_complete_still_works_unchanged` bleiben
  inhaltlich unverändert; nur die Fixture ändert sich.
- Umstellungen ohne neue Tests (AC-11): `test_bash_gate_erkennung_299`, `test_bash_gate_worktree_commit_155`,
  `test_adversary_evidence_gate_253`, `test_adversary_coverage_gate_259`, `test_po_briefing_gate`,
  `test_precondition_section_gate`, `test_red_marker_phase_gate_f004`, `test_skills_sync`,
  `test_skill_path_resolution`.
- Regression: `pytest tests/` komplett (AC-11), zusätzlich `python3 scripts/sync_skills.py --check`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Kein neues Strukturelement, sondern Rückbau eines Zweigs; die Alias-Erkennung ist eine
  feste Liste, kein neuer Mechanismus. Die Änderung kippt die Entscheidung aus
  `docs/specs/bug-fix-fast-track.md` (eigener Workflow-Typ `bug` ohne Spec, TDD-Rot und Gegenprüfung)
  endgültig und vollzieht den Teil von #250 A1, der „Hooks kennen `bug` bis A2" offenließ. Verworfene
  Alternative: `bug` bleibt als versteckter Alias für `feature-fast` erhalten. Das bräuchte weder
  Test-Umbauten noch ein Rezept für Altbestand, widerspricht aber der DoD „kein Hook kennt noch einen
  Bug-Schnellweg" und ließe den Typ als stille Hintertür bestehen. Gekippt würde damit die Linie aus
  A1/#250, dass Bugs ausschließlich über `/00-intake` laufen. Weitere verworfene Alternativen:
  eine Sonderbehandlung für Alt-`bug` wie `feature` mit Meldung oder wie `feature-fast` (mehr Code für
  einen lokal nicht vorhandenen Fall), und eine generische Erkennung „markierter Alias ohne Skill"
  (würde Aliase neuerer Plugin-Versionen löschen).

## Changelog

- 2026-10-03: Initial spec created
