# Context: feat-333-bug-typ-entfernen

## Request Summary
Issue #333 (#250 Teil A, Stufe A2): Den Workflow-Typ `bug` aus den Hooks entfernen, die Doku-Reste aus A1
bereinigen, zwei Tests aus A1 schärfen und `/00-bug` ganz löschen. Ein Ticket, ein Workflow (PO-Entscheid
2026-10-03). DoD laut Issue: kein Hook, Befehl oder Doku-Text kennt noch einen Bug-Schnellweg; Vollsuite grün.

## Related Files

### Hooks (Typ `bug`)
| File | Stelle | Relevanz |
|------|--------|----------|
| `core/hooks/workflow.py` | 881 | PO-Briefing-Gate: `("feature-fast", "bug")` übersprungen |
| `core/hooks/workflow.py` | 951–952 | `_validate_transition`: `bug` → keinerlei Vorbedingungen (`return None`) |
| `core/hooks/workflow.py` | 1061–1095 | `cmd_start`: Usage-Text, Typ-Whitelist, `bug` startet in phase6 mit `spec_approved`/`red_test_done` = True, Ausgabe `[BUG fast-track …]` |
| `core/hooks/workflow.py` | 1603, 1692 | Retro-/Report-Ausgabe: `bug` zählt als Fast-Track (kein TDD-Hinweis, „– (fast-track)") |
| `core/hooks/edit_gate.py` | 666–668 | TDD-Gate: `is_fast` für `bug`/`feature-fast`, konfigurierbar über `bug_fix.require_tdd` |
| `core/hooks/bash_gate.py` | 891–893 | Commit-Gate 5c: kein Adversary-Verdict für `bug`/`feature-fast` |
| `core/hooks/adversary_dialog.py` | 678, 769–781 | `_FAST_TRACK_TYPES = ("bug", "feature-fast")` für das Vorbedingungs-Gate (#286) |
| `config.yaml` | 191–195 | Abschnitt `bug_fix:` (`require_tdd`, `max_files`) mit Kommentar „Activated via --type bug". `max_files` wird nirgends im Code gelesen. |

Nicht betroffen: `config_loader.py:239` `bug_fix_blocker` (generisches Modul-Flag, kein Workflow-Typ);
`modules/ios-swiftui/config.yaml:49` `workflows.bug_fix` (verweist auf das Prozessdokument
`workflows/bug-fix-workflow.md`, kein `--type bug`); `tests/test_edit_gate_ac_check.py:77` (`type: bugfix` im Spec-Frontmatter).

### `/00-bug` (Löschung)
| File | Relevanz |
|------|----------|
| `core/commands/00-bug.md` | Quelle, seit A1 nur Hinweis (8 Zeilen) |
| `skills/00-bug/SKILL.md` | generiert; `sync_skills.py` synct nur Namen, die als Befehl UND Skill existieren → Verzeichnis muss von Hand mit weg |
| `.claude/commands/00-bug.md` | versionierter Kurz-Alias im Repo selbst |
| `README.md:157`, `CLAUDE.md:60` und `:449`, `setup.py:733` und `:774`, `docs/WORKFLOW_GUIDE.md:484` | Tabellenzeilen/Erwähnungen |
| `tests/test_skills_sync.py:270` | `REENTRY_EXEMPT` enthält `00-bug` |
| `tests/test_skill_path_resolution.py:192–214` | erwartet `["00-bug", "01-feature"]` als Skills ohne Wiedereinstieg |
| `tests/test_intake_bugs_250a1.py` | AC-4 (`BUG`-Datei gelesen auf Modulebene, Z.12) und AC-8 erwarten, dass `/00-bug` existiert |

### Doku-Reste (Issue Teil 2)
| File | Stelle | Inhalt |
|------|--------|--------|
| `docs/WORKFLOW_GUIDE.md` | 201 | „Keine RED-Artefakte? → BLOCK (außer bug/feature-fast)" |
| `docs/WORKFLOW_GUIDE.md` | 268 | `bug-intake`-Agent mit Auslöser `/00-bug` |
| `docs/WORKFLOW_GUIDE.md` | 340–344 | Abschnitt „Bug-Fix (`--type bug`)" |
| `docs/WORKFLOW_GUIDE.md` | 483 | `/00-intake`: „Track wählen (bug / feature-fast / feature)" |
| `docs/WORKFLOW_GUIDE.md` | 511–512 | Config-Tabelle `bug_fix.require_tdd`, `bug_fix.max_files` |
| `README.md` | 93–97 | Bug-Beispiel startet `workflow.py start "bug-…"` VOR `/00-intake` |

### Tests mit `workflow_type: bug` (müssen nachgezogen werden)
| File | Stelle | Nutzung |
|------|--------|---------|
| `tests/test_bash_gate_erkennung_299.py` | 283, 320 | `bug` als Weg, Gate 5c zu umgehen, damit 5b isoliert geprüft wird |
| `tests/test_adversary_evidence_gate_253.py` | 547 | parametrisiert `["bug", "feature-fast"]` |
| `tests/test_bash_gate_worktree_commit_155.py` | 76–84 | `bug` lässt Adversary-Prüfung aus |
| `tests/test_adversary_coverage_gate_259.py` | 385–400, 719–737 | parametrisiert `bug` neben `feature-fast` |
| `tests/test_red_marker_phase_gate_f004.py` | 18 | nur Docstring |
| `tests/test_po_briefing_gate.py` | 293 | Fast-Track-Ausnahme mit `bug` |
| `tests/test_precondition_section_gate.py` | 363 | Schleife über `("bug", "feature-fast")` |
| `tests/test_workflow_finish_alias.py` | 38–45 | `bug`, um Vorbedingungen für `finish` auszuschalten |
| `tests/test_intake_bugs_250a1.py` | 25, 53–56 | Issue Teil 3: Z.25 tautologisch (`index("Bugs")` trifft Zeile 3); AC-5-Suche `Manuell testen` ohne `re.I` |

## Existing Patterns
- Fast-Track wird überall per Tupel-Vergleich `workflow_type in ("bug", "feature-fast")` erkannt; nach dem Entfernen bleibt nur `== "feature-fast"`. Ein gemeinsames Konstanten-Tupel existiert nur in `adversary_dialog.py`.
- Tests, die ein Gate „ausschalten" wollen, nutzen `bug`, weil es am meisten freigibt. `feature-fast` ist der naheliegende Ersatz, gibt aber weniger frei: `_validate_transition` prüft bei `feature-fast` die Spec-Freigabe ab phase4.
- Gelöschte Befehle: Es gibt bisher keinen Präzedenzfall. `sync_skills.py` und `alias_sync.find_stale_aliases` iterieren nur über existierende Skills.

## Dependencies
- Upstream: `hook_utils.resolve_active_workflow`, `config_loader` (liest `bug_fix`).
- Downstream: Konsumenten-Projekte. Deren `.claude/workflows/*.json` und `_archive/` können `workflow_type: "bug"` enthalten. Lokal (Haupt-Repo und Archiv, 15 Dateien) gibt es keinen einzigen `bug`-Workflow.

## Existing Specs
- `docs/specs/bug-fix-fast-track.md` – ursprüngliche Spec des `bug`-Typs (Historie, wird nicht geändert)
- `docs/specs/user-initiated-bug-workflow.md` – Historie
- `docs/specs/feat-250-teil-a1-intake-einziger-eingang.md` – A1, Vorstufe; legt fest „Hooks kennen `bug` bis A2"
- `docs/specs/short-command-aliases.md` – Alias-Mechanik (#87)

## Risks & Considerations
1. **Altbestand muss lesbar bleiben (Issue-Vorgabe).** Ein Workflow-JSON mit `workflow_type: "bug"` darf `status`, `switch`, `finish`, Retro und Gates nicht zum Absturz bringen. Offen ist, welches Verhalten ein laufender alter `bug`-Workflow bekommt:
   - (a) wie `feature`, also volle Gates: blockiert ihn hart in phase6 ohne RED/Spec;
   - (b) wie `feature-fast`;
   - (c) eine klare Meldung.

   Lokal existiert keiner. Bei Konsumenten ist das unbekannt.
2. **Verwaiste Kurz-Aliase.** `~/.claude/commands/00-bug.md` und projektlokale `.claude/commands/00-bug.md` zeigen nach der Löschung auf einen nicht mehr existierenden Skill `/agent-os-openspec:00-bug`. `find_stale_aliases` erkennt das nicht, weil es nur über existierende Skills iteriert. Das Banner warnt also nicht, und `--refresh-aliases` räumt nicht auf. Auf diesem Rechner existieren beide Dateien. Entscheidung in der Analyse: Verwaiste Aliase erkennen und entfernen, oder als bekannte Grenze dokumentieren.
3. **`start --type bug`** soll klar abgelehnt werden, mit Hinweis auf `/00-intake` bzw. `feature-fast`, statt der generischen Meldung „Unknown workflow type".
4. **`bug_fix.require_tdd`** wirkt nach der Entfernung nur noch auf `feature-fast`. Der Schlüssel muss entweder umbenannt (Migrationsfrage für Konsumenten-Configs) oder unverändert als Fast-Track-Schalter gelassen werden. `max_files` ist toter Konfig-Schlüssel.
5. **Scoping:** Rund 25 Dateien, überwiegend Einzeiler und Löschungen. Laut PO bleibt es ein Ticket.
6. **Bekannte Gate-Fallen:** Das LoC-Gate zählt Spec/Kontext als Code (#294). Das installierte Plugin 3.34.0 verlangt ohne #322 trotzdem Override für `core/hooks` (Memory).
7. **CHANGELOG** unter [Unreleased] mit dem A1-Eintrag zusammenführen: Dessen Satz „Die Hooks kennen den Typ `bug` bis A2 weiter" wird ersetzt.

## Analysis

### Type
Feature (Rückbau, Folgearbeit aus #250 A1)

### Entscheidungen (technisch, vom Tech Lead getroffen)
1. **Altbestand `workflow_type: "bug"`: keine Sonderbehandlung.** Alle Stellen vergleichen per `==`/`in`.
   `wf_type` hat in Retro und Report den Default `"feature"` (workflow.py:1564, 1635). Nichts stürzt ab.
   Ein alter `bug` fällt in den feature-Pfad und durchläuft damit die vollen Gates. Für einen laufenden
   alten Workflow gibt es ein Rezept im CHANGELOG: `workflow.py set-field workflow_type feature-fast`.
   `cmd_set_field` (Z.1208) lässt den Schlüssel zu. Ob bash_gate den Aufruf als State-Manipulation
   blockt, wird in der Spec geprüft. Lokal gibt es keinen `bug`-Workflow.
2. **`start --type bug`** wird mit eigener Meldung abgelehnt: Typ entfernt, Bugs laufen über
   `/00-intake`, Kleinkram über `--type feature-fast`. Folgendes entfällt: Usage-Text Z.1061,
   Whitelist Z.1063, Zweige Z.1075–1079 und Z.1090–1091.
3. **Config:** `edit_gate.py:668` liest `fast_track.require_tdd` und nimmt `bug_fix.require_tdd` ein
   Release lang als Rückfall (CHANGELOG-Hinweis). `bug_fix.max_files` wird nirgends gelesen und entfällt
   ersatzlos (config.yaml, WORKFLOW_GUIDE).
4. **Verwaiste Kurz-Aliase:** Die feste Liste `REMOVED_SKILLS = ("00-bug",)` steht in `alias_sync.py`,
   dazu eine neue Funktion `find_removed_aliases`. Sie meldet nur markierte Alias-Dateien, deren Name in
   der Liste steht. `setup.py --refresh-aliases` löscht sie, `session_banner.py` warnt. Eine generische
   Erkennung „markierter Alias ohne Skill" wurde verworfen: Ein älteres Setup würde sonst Aliase von
   Skills löschen, die nur eine neuere Version kennt.
5. **Tests**, die `bug` nur zum Ausschalten von Gates nutzen:
   - `test_bash_gate_erkennung_299`, `test_bash_gate_worktree_commit_155`: `bug` → `feature-fast`. Das
     JSON wird direkt geschrieben, `_validate_transition` greift nicht.
   - `test_adversary_evidence_gate_253:547`, `test_adversary_coverage_gate_259:385–400` und `:719–737`,
     `test_precondition_section_gate:363`: Parametrisierungszeile `bug` streichen.
   - `test_po_briefing_gate:293` (Test 11): auf `feature-fast` umstellen. Die Fixture hat Spec und Freigabe.
   - `test_workflow_finish_alias:38–45`: Fixture umbauen. `cmd_complete` ruft
     `_validate_transition(phase8)`, feature-fast verlangt `spec_file` (existierende Datei),
     `spec_approved`, ADR und Briefing. `_check_adr` und `_check_po_briefing` werden in der Spec geklärt.
   - `test_intake_bugs_250a1`: Das Lesen der `BUG`-Datei auf Modulebene (Z.12) und AC-8 entfallen bzw.
     werden zu „`/00-bug` existiert nicht mehr". Die Tautologie Z.25 entfällt. Die AC-5-Suche bekommt
     `re.I`.
   - `test_skills_sync:270` (`REENTRY_EXEMPT`), `test_skill_path_resolution:192–214`: `00-bug` streichen.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `bug` aus Gate 881/951, `cmd_start`, Retro 1603, Report 1692 |
| core/hooks/edit_gate.py | MODIFY | `is_fast` nur feature-fast, `fast_track.require_tdd` + Rückfall |
| core/hooks/bash_gate.py | MODIFY | Gate 5c nur feature-fast |
| core/hooks/adversary_dialog.py | MODIFY | `_FAST_TRACK_TYPES = ("feature-fast",)` |
| core/hooks/alias_sync.py | MODIFY | `REMOVED_SKILLS`, `find_removed_aliases` |
| core/hooks/session_banner.py | MODIFY | Warnzeile für entfernte Aliase |
| setup.py | MODIFY | Refresh löscht entfernte Aliase; Z.733/774 Text |
| config.yaml | MODIFY | `bug_fix` → `fast_track.require_tdd` |
| core/commands/00-bug.md, skills/00-bug/, .claude/commands/00-bug.md | DELETE | `/00-bug` weg |
| README.md, CLAUDE.md, docs/WORKFLOW_GUIDE.md, CHANGELOG.md | MODIFY | Doku-Reste, A1-Eintrag zusammenführen |
| tests/ (11 Dateien) | MODIFY | siehe Entscheidung 5, plus neue Tests für Ablehnung, Rückfall und entfernte Aliase |

### Scope Assessment
- Files: ~27, überwiegend Einzeiler und Löschungen. PO-Entscheid: ein Ticket, ein Workflow.
- Estimated LoC: +90 / −150. Hook-Code ~25 Zeilen, Alias-Erkennung ~45 samt Tests.
- Risk Level: MEDIUM. Es greift in alle vier Kern-Gates ein, aber nur durch Entfernen eines Zweigs. Das Risiko liegt in Tests, die `bug` als Gate-Schalter nutzen.

### Technical Approach / Reihenfolge
1. Hooks und Config mit Rückfall. 2. `start`-Ablehnung. 3. Tests umstellen. 4. `/00-bug` samt
abhängigen Tests löschen. 5. Alias-Erkennung samt Test. 6. Doku und CHANGELOG. 7. Vollsuite.

### Alternative (verworfen)
`bug` bleibt als versteckter Alias für `feature-fast` erhalten. Dafür bräuchte es keine Test-Umbauten
und kein Rezept. Das widerspricht aber der DoD „kein Hook kennt noch einen Bug-Schnellweg“, und der Typ
bliebe als stille Hintertür bestehen. Gekippt würde A1/#250: Bugs laufen ausschließlich über `/00-intake`.

### Open Questions
- [ ] Blockt bash_gate `set-field workflow_type` (State-Integrity)? Wird in der Spec geprüft; wenn ja,
  bekommt das Rezept einen anderen Weg (Neustart über `/00-intake`).
- [ ] Bekannte Gate-Fallen: Das LoC-Gate (#294) zählt die Doku mit. Für `core/hooks` braucht das
  installierte Plugin 3.34.0 ein Override.
