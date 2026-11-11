---
entity_id: feat-577-cloud-agents
type: feature
created: 2026-11-11
updated: 2026-11-11
status: draft
version: "1.0"
workflow: issue-577-cloud-agents
tags: [agents, cloud, plugin-consumers, setup, token-cost, model-routing]
---

# Framework-Agenten in Cloud-Sitzungen (Issue #577)

## Approval

- [ ] Approved

## Purpose

In Cloud-Sitzungen (Claude Code on the web) gibt es keine Plugins (#520). Die Framework-Agenten (`implementation-validator`, `po-briefer`, `spec-writer` usw.) fehlen dort als Agent-Typen und starten als `general-purpose`. Das erbt das teure Hauptmodell (Opus), und jeder Agent liest seine 20–27 k Zeichen lange Definition erst per `cat` nach. Künftig liegen die Agenten als echte Projekt-Agenten in `.claude/agents/`: im Framework-Repo erzeugt `scripts/sync_cloud_agents.py` sie als markierte Kopien aus `core/agents/`, bei Plugin-Konsumenten mit Cloud-Pin schreibt `setup.py` (`--cloud-gates`, `--update`) dieselben Kopien. Das Modell kommt dann aus dem Frontmatter jedes Agenten. Die Befehle starten benannte Agenten in Werkzeug-Syntax ohne `model` und geben für den Notfall (Typ fehlt) ein Fallback mit ausdrücklichem Modell an; anonyme Starts tragen immer ein `model`.

## Source

- **File:** `scripts/sync_cloud_agents.py` (neu), `scripts/release_check.py`, `setup.py`, `core/commands/{20-analyse,30-write-spec,50-implement,60-validate,01-feature,82-test}.md`, `templates/agent_orchestration.md`
- **Identifier:** `sync_cloud_agents.AGENT_MARKER`, `sync_cloud_agents.render_agent`, `sync_cloud_agents.plan`, `sync_cloud_agents.sync`, `sync_cloud_agents.check` (neu); `release_check.check_cloud_agents` (neu); `setup._cloud_agent_plan` (neu), `setup._cloud_gate_plan`, `setup.apply_cloud_gates`, `setup.refresh_cloud_gates`, `setup.update_project` (geändert: `sync_dir` für `core/agents` nur im Copy-Modus)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/agents/*.md` | source | einzige Quelle der Agenten-Definitionen (Frontmatter `name`, `model`, `tools`) |
| `core/hooks/alias_sync.py` (`ALIAS_MARKER`, `refresh_aliases`) | module | Vorbild der Marker-Regel: nur markierte Dateien erneuern/entfernen, unmarkierte nie anfassen und melden |
| `scripts/sync_cloud_hooks.py` (#520) | script | Vorbild für Generator, `--check`, `--root` und Release-Check-Zeile |
| `setup._cloud_gate_plan`, `setup._write_changed`, `setup.resolve_cloud_pin` (#522) | functions | Konsumenten-Rollout; Agent-Kopien laufen im selben Plan mit |
| `scripts/sync_skills.py` | script | erzeugt `skills/*/SKILL.md` aus `core/commands`; nach den Befehlsänderungen neu ausführen |
| `tests/test_agent_dispatch_drift_279.py` | test | erkennt Dispatch per Agent-Name; muss nach den Befehlsänderungen grün bleiben |
| Claude-Code-Agent-Loader | upstream | lädt `.claude/agents/` auch in der Cloud (Teil des Klons); Vorrang bei gleichem Namen: project vor plugin; Modellwahl: Aufruf-`model` > Frontmatter > Hauptsitzung |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| scripts/sync_cloud_agents.py | CREATE | Erzeugt `.claude/agents/<name>.md` aus `core/agents/<name>.md` als Kopie mit Marker nach dem Frontmatter; `--check` (Drift, Exit 1), `--root`; entfernt veraltete markierte Dateien, fasst unmarkierte nie an und meldet sie; Funktionen für den Konsumenten-Plan |
| .claude/agents/*.md (14) | CREATE | Generat im Framework-Repo (Kopie, kein Symlink) |
| scripts/release_check.py | MODIFY | Zeile „Cloud-Agenten“ neben „Cloud-Hooks“ (Vorab- und Voll-Check) |
| setup.py | MODIFY | `_cloud_agent_plan`; `_cloud_gate_plan`/`apply_cloud_gates`/`refresh_cloud_gates` schreiben markierte Kopien, entfernen veraltete markierte, melden unmarkierte gleichnamige mit „Skipped“; `update_project` überspringt `sync_dir` für `core/agents` im Plugin-Modus |
| core/commands/30-write-spec.md | MODIFY | spec-writer, spec-validator, po-briefer als benannte Typen in Werkzeug-Syntax; Fallback-Regel |
| core/commands/50-implement.md | MODIFY | developer-agent, implementation-validator wie oben; Explore mit `model` |
| core/commands/60-validate.md | MODIFY | docs-updater als Typ; anonyme `general-purpose`-/`Explore`-Starts mit ausdrücklichem `model` |
| core/commands/20-analyse.md | MODIFY | bug-intake als Typ; anonyme Explore-/Plan-Starts mit ausdrücklichem `model` |
| core/commands/01-feature.md, core/commands/82-test.md | MODIFY | feature-planner bzw. test-runner als Typ mit Fallback |
| templates/agent_orchestration.md | MODIFY | Regel „benannter Typ ohne `model`; Fallback `general-purpose` mit `model`“ |
| skills/*/SKILL.md | MODIFY | Generat neu (`python3 scripts/sync_skills.py`) |
| tests/test_cloud_agents_577.py | CREATE | Tests zu allen AC unten |
| CHANGELOG.md, CLAUDE.md | MODIFY | Eintrag unter `[Unreleased]`; Architektur-/Dateitabelle |

### Estimated Changes

- Files: 2 neu handgeschrieben (Skript, Test) + 14 Generat, rund 11 geändert, dazu Skills-Generat
- LoC: +420/-40 (ohne Generate)
- Risk Level: HIGH (Rollout in Konsumenten-Projekte über `setup.py`, Befehlstexte aller Agent-Starts) → 2 Adversary-Runden

## Implementation Details

**Kopie statt Symlink, Marker statt Vertrauen.** Eine Quelle (`core/agents`), je Agent eine Kopie `.claude/agents/<name>.md`. Der Marker `AGENT_MARKER` (HTML-Kommentar, z. B. `<!-- openspec-cloud-agent: generated from core/agents, do not edit -->`) steht direkt hinter dem schließenden `---` des Frontmatters, das unverändert bleibt (`name`, `model`, `tools`). Hat eine Quelle kein Frontmatter, wird der Marker als erste Zeile gesetzt (Vorbild `alias_sync`). Das Generat ist damit identisch zur Quelle bis auf die eine Markerzeile.

**`scripts/sync_cloud_agents.py`:** `render_agent(text) -> str` (Marker einfügen), `plan(src_dir, dst_dir) -> (writes, removals, skipped)` als reine Berechnung, `sync(root)` schreibt nur Abweichendes, `check(root) -> (bool, str)` liefert Drift ohne zu schreiben. CLI wie `sync_cloud_hooks.py`: ohne Schalter schreiben, `--check` mit Exit 1 bei Drift, `--root <pfad>`. Regeln je Zieldatei:

- fehlt: schreiben (`--check`: Drift „fehlt“)
- vorhanden und markiert, Inhalt weicht ab: überschreiben (`--check`: Drift „abweichend“)
- vorhanden und markiert, ohne Quelle in `core/agents`: entfernen (`--check`: Drift „veraltet“)
- vorhanden und nicht markiert (Eigenbau, Modul-Agent): nie überschreiben, nie löschen, als „Skipped: <name> (eigene Datei)“ melden; `--check` zählt das nicht als Drift

**Release-Check:** `release_check.check_cloud_agents(root=None)` ruft `sync_cloud_agents.check` (Default: das Repo, aus dem die Skripte stammen, wie `check_cloud_hooks`) und steht als Zeile „Cloud-Agenten“ direkt hinter „Cloud-Hooks“ in beiden Check-Listen; Drift blockt das Release.

**Konsumenten (`setup.py`):** `_cloud_agent_plan(project_path)` nutzt `sync_cloud_agents.plan(CORE_DIR / "agents", project_path / ".claude" / "agents")`. `_cloud_gate_plan` hängt die Schreibaufträge an die Liste (Baustein, `settings.json`, Kopien); `apply_cloud_gates` und `refresh_cloud_gates` entfernen zusätzlich veraltete markierte Kopien und geben „Skipped“-Zeilen für unmarkierte gleichnamige Dateien aus. Gilt nur im Plugin-Modus mit Cloud-Pin, also dort, wo `--cloud-gates` bzw. `--update` schon heute den Cloud-Baustein pflegen. Plugin-Projekte ohne Pin bleiben unverändert (lokal laufen die Plugin-Agenten). Copy-Modus bleibt unverändert: dort kopiert `install` und `update_project` `core/agents` weiterhin ohne Marker über `sync_dir`/Manifest.

**Kein Flip-Flop im `--update`:** Im Plugin-Modus würde `sync_dir(core/agents → .claude/agents)` unmarkierte Kopien schreiben, die der Cloud-Plan wieder markiert (und Manifest-`.new`-Dateien erzeugen). Deshalb läuft `sync_dir` für `core/agents` nur noch, wenn `plugin` falsch ist (Muster wie bei `hooks`/`commands`, #562/#566). Im Plugin-Modus erneuert ausschließlich `refresh_cloud_gates` die Agenten.

**Doppelregistrierung lokal wird hingenommen:** Mit Plugin plus Projekt-Kopie gibt es lokal `implementation-validator` und `agent-os-openspec:implementation-validator`. Ein Aufruf startet genau einen Agenten (kein Doppelstart); die Projekt-Variante hat Vorrang und ist inhaltsgleich. Die Befehle nennen den unqualifizierten Namen. Keine `permissions.deny`-Regeln, weil das Verhalten mit Plugin-Namespace nicht dokumentiert ist.

**Befehlstexte:** Jeder Aufruf eines benannten Agenten steht in Werkzeug-Syntax `Agent(subagent_type="<name>", run_in_background=…, prompt="…")` ohne `model`; das Modell regiert das Frontmatter. Je Befehl steht einmal die Fallback-Regel: Typ nicht verfügbar → `agent-os-openspec:<name>`; auch der fehlt → `Agent(subagent_type="general-purpose", model="<Frontmatter-Modell>", …)` und die Definition (`core/agents/<name>.md` bzw. `.claude/agents/<name>.md`) zuerst lesen. Das genannte Fallback-Modell muss dem Frontmatter-`model` des Agenten entsprechen. Anonyme Starts (`general-purpose`, `Explore`, `Plan`) tragen immer `model="<haiku|sonnet|opus>"`. Zuordnung: spec-writer sonnet, spec-validator haiku, po-briefer sonnet, developer-agent opus, implementation-validator sonnet, docs-updater sonnet, bug-intake haiku, feature-planner sonnet, test-runner haiku.

**Skills:** Nach den Befehlsänderungen `python3 scripts/sync_skills.py` ausführen; `release_check` („Skills“) blockt Drift.

## Test Plan

### Automated Tests (TDD RED)

Echte Dateien in `tmp_path`, Aufruf des Skripts per `subprocess` bzw. Import, `setup.py` gegen ein Plugin-Modus-Projekt mit Pin (Aufbau wie `tests/test_cloud_gates_522.py`). Kein Mock von Dateisystem oder git.

- [ ] Test 1: GIVEN `core/agents` WHEN `sync_cloud_agents.sync` läuft THEN gleicht jede Kopie der Quelle bis auf die eine Markerzeile
- [ ] Test 2: GIVEN ein Ziel mit fehlender, abweichender und veralteter markierter Datei WHEN `--check` läuft THEN Exit 1 mit je einer Meldung, und nach `sync` Exit 0
- [ ] Test 3: GIVEN eine unmarkierte Datei mit Namen eines Agenten und eine ohne Quelle WHEN `sync` läuft THEN bleiben beide byte-gleich, Meldung „Skipped“
- [ ] Test 4: GIVEN eine markierte Datei ohne Quelle WHEN `sync` läuft THEN ist sie entfernt
- [ ] Test 5: GIVEN `release_check` WHEN `check_cloud_agents` auf sauberem und auf driftendem Ziel läuft THEN (True, …) bzw. (False, …) und die Zeile „Cloud-Agenten“ steht in `main`
- [ ] Test 6: GIVEN ein Plugin-Modus-Projekt WHEN `setup.py --cloud-gates` bzw. `--update` mit Pin läuft THEN liegen markierte Kopien in `.claude/agents/`; ohne Pin und im Copy-Modus gilt das Alte
- [ ] Test 7: GIVEN ein Plugin-Modus-Projekt mit Pin WHEN `--update` zweimal läuft THEN keine `.new`-Dateien, zweiter Lauf ändert kein Byte
- [ ] Test 8: GIVEN `core/commands` WHEN die Befehlstexte geparst werden THEN nennt jeder benannte Agent die Werkzeug-Syntax, sein Fallback-Modell stimmt mit dem Frontmatter überein, und jeder anonyme Start hat ein `model`
- [ ] Test 9: GIVEN `skills/` WHEN `sync_skills.check` läuft THEN keine Drift

Regression: `pytest tests/` (insbesondere `test_cloud_hooks_520.py`, `test_cloud_gates_522.py`, `test_release_check_93.py`, `test_agent_dispatch_drift_279.py`, Alias-Tests #562), `python3 scripts/sync_cloud_agents.py --check`, `python3 scripts/release_check.py --no-tests`.

## Acceptance Criteria

- **AC-1:** Given `core/agents/*.md` / When `sync_cloud_agents.sync` in ein leeres Zielverzeichnis läuft / Then entsteht je Quelle genau eine Kopie, deren Inhalt der Quelle bis auf eine einzige Markerzeile nach dem Frontmatter entspricht (Frontmatter mit `name`, `model`, `tools` unverändert) und das auch im Framework-Repo unter `.claude/agents/` eingecheckt ist
  - Test: tests/test_cloud_agents_577.py::test_generated_copy_equals_source_except_marker

- **AC-2:** Given ein Ziel mit fehlender, inhaltlich abweichender und veraltet markierter Datei (Quelle entfernt) / When `sync_cloud_agents.py --check` läuft / Then Exit 1 mit je einer Meldung „fehlt“, „abweichend“, „veraltet“, schreibt nichts, und nach `sync` Exit 0
  - Test: tests/test_cloud_agents_577.py::test_check_detects_missing_diverged_and_stale

- **AC-3:** Given eine unmarkierte Datei im Ziel (gleichnamig zu einem Agenten bzw. ohne Quelle, etwa ein Modul-Agent), die nicht als unveränderte Framework-Kopie im Manifest steht (Ausnahme: AC-15) / When `sync` und `--check` laufen / Then bleibt sie byte-gleich erhalten, wird als „Skipped“ gemeldet, und `--check` zählt sie nicht als Drift
  - Test: tests/test_cloud_agents_577.py::test_unmarked_files_never_overwritten_or_deleted

- **AC-4:** Given eine markierte Datei im Ziel, deren Quelle in `core/agents` nicht (mehr) existiert / When `sync` läuft / Then ist die Datei entfernt, markierte Dateien mit Quelle bleiben
  - Test: tests/test_cloud_agents_577.py::test_stale_marked_files_are_removed

- **AC-5:** Given `scripts/release_check.py` / When der Vorab- und der Voll-Check laufen / Then enthält die Ausgabe die Zeile „Cloud-Agenten“ direkt hinter „Cloud-Hooks“, sie ist grün bei synchronem `.claude/agents/` und rot mit Hinweis auf `python3 scripts/sync_cloud_agents.py` bei Drift
  - Test: tests/test_cloud_agents_577.py::test_release_check_has_cloud_agents_line

- **AC-6:** Given ein Plugin-Modus-Projekt mit Cloud-Pin / When `setup.py <projekt> --cloud-gates` läuft / Then liegen alle Agenten als markierte Kopien in `.claude/agents/`, die Ausgabe nennt sie unter „Geschrieben“, ein veraltet markierter wird entfernt, eine unmarkierte gleichnamige Datei bleibt unverändert mit „Skipped“, und ein zweiter Lauf ändert kein Byte
  - Test: tests/test_cloud_agents_577.py::test_cloud_gates_writes_marked_agent_copies

- **AC-7:** Given ein Plugin-Modus-Projekt mit Cloud-Pin und veralteten Agent-Kopien / When `setup.py <projekt> --update` läuft / Then werden die markierten Kopien erneuert; ohne gesetzten Pin schreibt `--update` im Plugin-Modus keine Agenten, und `--cloud-gates` bleibt für Copy-Modus-Projekte abgewiesen
  - Test: tests/test_cloud_agents_577.py::test_update_with_pin_refreshes_copies_without_pin_does_not

- **AC-8:** Given ein Plugin-Modus-Projekt mit Pin / When `setup.py <projekt> --update` zweimal läuft / Then schreibt `update_project` `core/agents` nicht mehr per `sync_dir`/Manifest: keine `.new`-Dateien, keine Manifest-Einträge für `.claude/agents/*`, die Kopien bleiben markiert (kein Flip-Flop) und der zweite Lauf ändert nichts
  - Test: tests/test_cloud_agents_577.py::test_update_in_plugin_mode_does_not_flip_flop

- **AC-15:** Given ein Plugin-Modus-Projekt (mit oder ohne Pin), dessen `.claude/agents/<name>.md` unmarkiert ist und dessen SHA-256 dem Eintrag in `.claude/framework_manifest.json` entspricht (vom Framework installiert, lokal unverändert, z. B. nach Umstieg vom Copy-Modus) / When `setup.py <projekt> --update` läuft / Then wird die Datei durch die markierte Kopie ersetzt, ihr Manifest-Eintrag entfernt und die Übernahme gemeldet; eine unmarkierte Datei mit abweichendem Hash oder ohne Manifest-Eintrag bleibt byte-gleich und wird als „Skipped“ gemeldet
  - Test: tests/test_cloud_agents_577.py::test_update_adopts_unchanged_manifest_copies

- **AC-16:** Given ein Plugin-Modus-Projekt ohne Pin mit vorhandenen markierten Kopien / When `setup.py <projekt> --update` läuft / Then werden die vorhandenen markierten Kopien auf den Stand von `core/agents` gebracht und veraltete markierte entfernt, fehlende Kopien aber nicht neu angelegt (erneuern, nie anlegen — wie bei den Kurzbefehlen, #566)
  - Test: tests/test_cloud_agents_577.py::test_update_without_pin_refreshes_existing_marked_only

- **AC-9:** Given ein Copy-Modus-Projekt / When `setup.py <projekt>` installiert und `--update` läuft / Then wird `core/agents` weiterhin ohne Marker nach `.claude/agents` kopiert und über das Manifest aktualisiert, wie vor dieser Änderung
  - Test: tests/test_cloud_agents_577.py::test_copy_mode_agents_unchanged

- **AC-10:** Given `core/commands/*.md` / When die Befehlstexte geprüft werden / Then startet jeder Befehl die Agenten spec-writer, spec-validator, po-briefer, developer-agent, implementation-validator, docs-updater, bug-intake, feature-planner und test-runner in Werkzeug-Syntax `subagent_type="<name>"` ohne `model`-Parameter, und kein Befehl nennt mehr die Prosa-Form `general-purpose/<modell>` mit „Du bist der <name> Agent“ für diese Agenten
  - Test: tests/test_cloud_agents_577.py::test_commands_name_agents_in_tool_syntax_without_model

- **AC-11:** Given die Befehle aus AC-10 / When die Fallback-Regel gelesen wird / Then nennt jeder dieser Befehle für jeden von ihm gestarteten benannten Agenten die Kette `agent-os-openspec:<name>` und danach `general-purpose` mit `model="<m>"`, wobei `<m>` dem `model:` im Frontmatter von `core/agents/<name>.md` entspricht
  - Test: tests/test_cloud_agents_577.py::test_fallback_model_matches_agent_frontmatter

- **AC-12:** Given `core/commands/*.md` / When alle Starts mit `general-purpose`, `Explore` oder `Plan` geprüft werden / Then trägt jeder ein ausdrückliches `model="haiku|sonnet|opus"`
  - Test: tests/test_cloud_agents_577.py::test_anonymous_agent_starts_carry_explicit_model

- **AC-13:** Given `templates/agent_orchestration.md` und `skills/` / When gelesen bzw. `sync_skills.check` läuft / Then enthält das Template die Regel „benannter Typ ohne `model`, Fallback `general-purpose` mit `model`“, und `skills/*/SKILL.md` stimmen mit dem Generat aus `core/commands` überein
  - Test: tests/test_cloud_agents_577.py::test_skills_in_sync_and_template_documents_rule

- **AC-14:** Given `CHANGELOG.md` und `CLAUDE.md` / When gelesen / Then enthält `[Unreleased]` einen Eintrag mit `#577`, und die Architektur-/Dateitabelle in `CLAUDE.md` nennt `scripts/sync_cloud_agents.py` und `.claude/agents/`
  - Test: tests/test_cloud_agents_577.py::test_changelog_and_claude_md_document_feature

## Known Limitations

- Agent-Texte nennen `.claude/hooks/...`; im Framework-Repo liegen die Hooks unter `core/hooks/`. Bestehend und unverändert: die Agenten lasen bisher denselben Text per `cat`.
- Modul-Agenten (iOS, Home Assistant) werden im Plugin-Modus weder lokal noch in der Cloud ausgeliefert (bestehend). Eine unmarkierte Modul-Kopie in `.claude/agents/` hat Vorrang und wird nie überschrieben.
- Lokal mit Plugin stehen die Agenten doppelt in der Agent-Liste (`<name>` und `agent-os-openspec:<name>`), das kostet etwas Kontext, startet aber nie zwei Agenten pro Aufruf.
- `developer-agent` und `user-story-planner` stehen bewusst auf `opus`; dort spart die Änderung nur das `cat` der Definition, kein Modell.
- Ob Claude die Werkzeug-Syntax in den Befehlen immer als `subagent_type`-Parameter umsetzt, ist nicht mechanisch erzwingbar; die Tests sichern den Befehlstext, nicht das Laufzeitverhalten.
- Plugin-Konsumenten ohne Cloud-Pin bekommen keine Kopien (lokal laufen die Plugin-Agenten); wer die Cloud nutzt, führt einmal `setup.py --cloud-gates` aus und committet die Dateien.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] `.claude/agents/` im Framework-Repo ist erzeugt und eingecheckt, `python3 scripts/sync_cloud_agents.py --check` ist grün (AC-1, AC-2)
- [ ] Markierte Kopien werden erneuert und entfernt, unmarkierte nie angefasst (AC-3, AC-4); unveränderte Framework-Kopien aus dem Manifest werden übernommen, ohne Pin nur vorhandene markierte erneuert (AC-15, AC-16)
- [ ] `release_check.py` zeigt die Zeile „Cloud-Agenten“ und blockt Drift (AC-5)
- [ ] `setup.py --cloud-gates` und `--update` mit Pin schreiben die Kopien ohne Flip-Flop und ohne `.new`-Dateien; Copy-Modus unverändert (AC-6 bis AC-9)
- [ ] Alle Befehle nennen benannte Agenten in Werkzeug-Syntax, Fallback-Modelle stimmen mit dem Frontmatter überein, anonyme Starts haben ein `model` (AC-10 bis AC-12)
- [ ] `skills/` ist synchron, `templates/agent_orchestration.md`, `CHANGELOG.md` und `CLAUDE.md` sind aktualisiert (AC-13, AC-14)
- [ ] Jede Acceptance Criterion ist durch einen automatischen Test belegt
- [ ] Regressionslauf `pytest tests/` ist grün

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Kein neues Gate und keine neue Regel; die vorhandenen Agenten bekommen für Cloud-Sitzungen einen zweiten Ladeweg, abgeleitet aus der einen Quelle `core/agents` (Muster #520 und #522: Generat, `--check`, Release-Check). Entscheidung 1: Kopie mit Marker statt Symlink. Ein Symlink `.claude/agents → ../core/agents` wäre im Framework-Repo driftfrei, aber ob Claude Code Symlinks in `.claude/agents` befolgt, ist nicht dokumentiert, und Konsumenten bräuchten ohnehin Kopien. Der Marker (wie `alias_sync`) trennt Generat von Eigenbauten: nur Markiertes wird erneuert oder entfernt, lokale und Modul-Agenten bleiben unangetastet. Entscheidung 2: Doppelregistrierung lokal hinnehmen (Plugin plus Projekt-Kopie). Die Projekt-Variante hat Vorrang, ist inhaltsgleich, und ein Aufruf startet genau einen Agenten; der Preis ist ein zusätzlicher Listeneintrag. Verworfen: (a) `permissions.deny: Agent(<plugin>:<name>)` zum Ausblenden der Plugin-Varianten, weil Syntax und Wirkung mit Namespace nicht dokumentiert sind und ein Fehlgriff Agenten ganz sperren könnte; (b) Agenten nur über das Setup-Skript der Umgebung installieren, weil es außerhalb des Repos liegt und nicht versioniert ist; (c) nur die Befehle ändern (Modell als Parameter an `general-purpose`), weil die Definition dann weiter per `cat` nachgelesen wird und Typ und Frontmatter-Modell fehlten; (d) `sync_dir`/Manifest für `core/agents` auch im Plugin-Modus behalten, weil Manifest-Kopie (unmarkiert) und Cloud-Plan (markiert) sich bei jedem `--update` gegenseitig überschrieben und `.new`-Dateien erzeugten. Reversibel: Skript, Zeile im Release-Check und die Kopien lassen sich entfernen; die Befehle laufen mit der Fallback-Kette weiter.

## Changelog

- 2026-11-11: Initial spec created
- 2026-11-11: AC-15/AC-16 ergänzt, AC-3 eingegrenzt. Befund aus der Umsetzung: Copy-Modus-Projekte, die auf das Plugin umgestiegen sind, haben unmarkierte, im Manifest geführte Agent-Kopien; ohne Übernahme veralteten sie, weil `--update` sie im Plugin-Modus nicht mehr per `sync_dir` erneuert
