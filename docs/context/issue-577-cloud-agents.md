# Context: issue-577-cloud-agents

## Request Summary
In Cloud-Sitzungen (keine Plugins, #520) fehlen die Framework-Agenten als Agent-Typen. `implementation-validator`, `po-briefer` usw. starten deshalb als `general-purpose` und erben Opus; dazu liest jeder Agent seine Definition (20–27 k Zeichen) per `cat` ein. Ziel: Agenten in der Cloud als echte Typen mit ihrem Frontmatter-Modell verfügbar machen, lokal keine Doppelregistrierung/Doppelstarts, Befehle mit Modell-Fallback.

## Related Files
| File | Relevance |
|------|-----------|
| `core/agents/*.md` (14 Dateien) | Quelle; Frontmatter `name`, `model` (sonnet/haiku/opus), `tools` |
| `agents` (Symlink → `core/agents`) | Plugin-Auslieferung: lokal als `agent-os-openspec:<name>` registriert |
| `scripts/sync_cloud_hooks.py` | Vorbild: erzeugt `.claude/settings.json`-Hooks aus `hooks/hooks.json`, `--check` für Drift, `--consumer` für Konsumenten |
| `scripts/release_check.py:205-235,292,351` | Drift-Checks `Skills`, `Cloud-Hooks` — neuer Check „Cloud-Agenten“ gehört daneben |
| `setup.py:944-1050` | `_cloud_gate_plan`, `_write_changed`, `apply_cloud_gates`, `refresh_cloud_gates` — Konsumenten-Rollout (`--cloud-gates`, `--update` mit Pin) |
| `setup.py:361-381, 1363` | Copy-Modus kopiert `core/agents` bereits nach `.claude/agents` (dort kein Cloud-Problem) |
| `core/hooks/alias_sync.py` | Vorbild Marker-Logik (`ALIAS_MARKER`): nur markierte Dateien erneuern, lokale Eigenbauten nie überschreiben |
| `core/commands/50-implement.md:93,226` | `Task (developer-agent/opus …)`, `Task (implementation-validator …)` — Typnamen ohne Fallback-Modell |
| `core/commands/30-write-spec.md:78-132` | spec-writer, spec-validator, po-briefer als `general-purpose/<model>` mit „Du bist der X Agent“ |
| `core/commands/60-validate.md:104-166` | 4x `general-purpose/haiku`, Fix-Agent und docs-updater `general-purpose/sonnet` |
| `core/commands/20-analyse.md:71`, `01-feature.md:3`, `82-test.md:3` | bug-intake, feature-planner, test-runner |
| `templates/agent_orchestration.md:99-123` | Referenz-Template für Dispatch-Muster |
| `skills/*/SKILL.md` | Generat aus `core/commands` (`scripts/sync_skills.py`) — nach Befehlsänderung neu erzeugen |
| `tests/test_cloud_hooks_520.py`, `tests/test_cloud_gates_522.py`, `tests/test_release_check_93.py` | Testmuster für Sync/Drift/Konsumenten-Rollout |

## Existing Patterns
- Generat + `--check` + Release-Check-Zeile (Skills, Cloud-Hooks): eine Quelle, Drift blockt Release.
- Konsumenten-Rollout über `setup.py --cloud-gates` / `--update` (nur Plugin-Modus mit Pin), `_write_changed` schreibt nur Abweichungen.
- Marker-Dateien (`alias_sync`): generierte Dateien tragen einen Marker; nur markierte werden erneuert/entfernt.
- Befehle geben das Modell bei `general-purpose` bereits an (`general-purpose/haiku|sonnet`); Lücke sind die direkt benannten Typen (`implementation-validator`, `developer-agent`, `test-runner`, `feature-planner`) ohne Fallback.

## Dependencies
- Upstream: Claude Code lädt Projekt-Agenten aus `.claude/agents/` (auch in der Cloud, da Teil des Repos); Plugin-Agenten nur lokal, namespaced.
- Downstream: alle Befehle, die Agenten starten; Konsumenten-Projekte im Plugin-Modus mit Cloud-Pin; `release_check.py`.

## Existing Specs
- `docs/specs/` zu #520 (Cloud-Hooks) und #522 (Cloud-Gates für Konsumenten) — gleiche Bauart.

## Risks & Considerations
- **Doppelregistrierung lokal:** Mit Plugin + `.claude/agents/` existieren `implementation-validator` und `agent-os-openspec:implementation-validator`. Inhalt identisch; Risiko: doppelte Agent-Liste (Kontext-Token), Modell startet uneinheitlich. Optionen: hinnehmen und Befehle auf den unqualifizierten Namen festlegen; oder Plugin-Varianten per Projekt-`permissions.deny` (`Agent(<plugin>:<name>)`) ausblenden — Syntax/Verhalten in der Analyse prüfen.
- **Framework-Repo:** Symlink `.claude/agents → ../core/agents` wäre driftfrei (Root-`agents`-Symlink funktioniert bereits); Konsumenten brauchen Kopien.
- **Lokale Eigenbauten bei Konsumenten** (z. B. Modul-Agenten iOS) dürfen nie überschrieben werden → Marker-Logik.
- **Pfade in Agent-Texten** (`.claude/hooks/...`) stimmen im Framework-Repo nicht (`core/hooks`) — bestehend, nicht Scope.
- `developer-agent` und `user-story-planner` stehen bewusst auf `opus` (CLAUDE.md: Implementation auf Opus) — Einsparung dort nur durch wegfallendes `cat`.
- Infrastruktur-Änderung (`setup.py`, `scripts/`, Befehle) → hohes Adversary-Risiko, 2 Runden.

## Analysis

### Type
Feature (Token-/Kostenhebel, Infrastruktur)

### Gesicherte Fakten (offizielle Claude-Code-Doku, geprüft 2026-11-11)
- Plugin-Agenten heißen `agent-os-openspec:<name>` (sub-agents, plugins/components).
- Projekt-Agenten aus `.claude/agents/` werden in Cloud-Sitzungen geladen („Part of the clone", cloud-environments); Plugins dort nicht.
- Vorrang bei gleichem Namen: managed > `--agents` > project > user > plugin.
- Modellwahl: `model`-Parameter des Aufrufs > Frontmatter `model` > `CLAUDE_CODE_SUBAGENT_MODEL` > Modell der Hauptsitzung. `general-purpose` ohne Parameter erbt also Opus.
- Nicht dokumentiert: ob Symlinks in `.claude/agents` befolgt werden; ob `permissions.deny: Agent(<plugin>:<name>)` mit Namespace greift → beides nicht nutzen.

### Ursachen (zwei, beide nötig)
1. In der Cloud fehlen die Typen → benannte Starts (`implementation-validator`, `developer-agent`) fallen auf `general-purpose` zurück und erben Opus.
2. Die Befehle schreiben das Modell nur als Prosa-Notation (`Task (general-purpose/sonnet, …)`); das kommt nicht verlässlich als `model`-Parameter an. Dazu „Du bist der X Agent" → Agent liest seine Definition per `cat` nach.

### Affected Files
| File | Change Type | Description |
|------|-------------|-------------|
| `scripts/sync_cloud_agents.py` | CREATE | Erzeugt `.claude/agents/<name>.md` aus `core/agents` als Kopie mit Marker (nach dem Frontmatter), `--check` (Drift), `--root`; entfernt veraltete markierte Dateien, fasst unmarkierte nie an; Funktion für den Konsumenten-Plan |
| `.claude/agents/*.md` (14) | CREATE | Generat im Framework-Repo (Kopie, kein Symlink) |
| `scripts/release_check.py` | MODIFY | Zeile „Cloud-Agenten" neben „Cloud-Hooks" (Pre- und Voll-Check) |
| `setup.py` | MODIFY | `_cloud_gate_plan`: markierte Agent-Kopien bei `--cloud-gates` und `--update` mit Pin, veraltete markierte entfernen, unmarkierte gleichnamige mit „Skipped" melden; `update_project`: `sync_dir` für `core/agents` im Plugin-Modus überspringen (sonst Flip-Flop markiert/unmarkiert + Manifest-`.new`) |
| `core/commands/30-write-spec.md` | MODIFY | spec-writer, spec-validator, po-briefer als benannte Typen; Fallback |
| `core/commands/50-implement.md` | MODIFY | developer-agent, implementation-validator: Typ + Fallback mit `model` |
| `core/commands/60-validate.md` | MODIFY | docs-updater als Typ; anonyme `general-purpose`-Starts mit ausdrücklichem `model` |
| `core/commands/20-analyse.md`, `01-feature.md`, `82-test.md` | MODIFY | bug-intake, feature-planner, test-runner: Typ + Fallback |
| `templates/agent_orchestration.md` | MODIFY | Regel „benannter Typ ohne `model`, Fallback `general-purpose` mit `model`" |
| `skills/*/SKILL.md` | MODIFY | Generat neu (`scripts/sync_skills.py`) |
| `tests/test_cloud_agents_577.py` | CREATE | Sync, Drift, Marker-Schutz, Konsumenten-Plan, `--update` ohne Flip-Flop, Befehlstexte (Fallback-Modell = Frontmatter je Agent) |
| `CHANGELOG.md`, `CLAUDE.md` | MODIFY | `[Unreleased]`; Architektur-/Dateitabelle |

### Scope Assessment
- Files: ~12 handgeschrieben + 14 Generat + Skills-Generat
- Estimated LoC: +420/-40 (ohne Generate)
- Risk Level: HIGH (Rollout in Konsumenten-Projekte über `setup.py`, Befehlstexte aller Agent-Starts) → 2 Adversary-Runden

### Technical Approach
1. **Spiegeln per Generat, nicht Symlink:** eine Quelle `core/agents`, Kopie mit Marker-Zeile, Drift blockt Release (Muster Skills/Cloud-Hooks). Frontmatter (`name`, `model`, `tools`) bleibt unverändert → Modell kommt aus der einzigen Quelle.
2. **Konsumenten (Plugin-Modus mit Cloud-Pin):** derselbe Generator im `_cloud_gate_plan`; Marker-Regel wie `alias_sync`: nur markierte Dateien erneuern/entfernen, unmarkierte (eigene oder Modul-Agenten) nie anfassen und melden. Copy-Modus unverändert (kopiert Agenten bereits, ohne Marker). Plugin-Projekte ohne Pin: unverändert (lokal laufen Plugin-Agenten).
3. **Doppelregistrierung lokal hinnehmen:** Plugin + Projekt-Kopie = zwei Listeneinträge, aber kein Doppelstart (ein Aufruf startet einen Agenten); Projekt-Variante hat Vorrang und ist inhaltsgleich. Keine Deny-Regeln (Namespace-Verhalten undokumentiert).
4. **Befehle:** Aufruf in Werkzeug-Syntax (`Agent(subagent_type="<name>", …)`) ohne `model` — Frontmatter regiert. Fallback-Regel einmal je Befehl: Typ fehlt → `agent-os-openspec:<name>`; fehlt auch der → `general-purpose` mit `model="<Frontmatter-Modell>"` und Definition lesen. Anonyme Starts (`general-purpose`, `Explore`, `Plan`) immer mit `model=`. Test bindet jedes genannte Fallback-Modell an das Frontmatter.

### Dependencies
- Upstream: Agent-Loader von Claude Code (`.claude/agents`), `alias_sync`-Marker-Muster, `sync_cloud_hooks`-Muster, `setup.resolve_cloud_pin`.
- Downstream: alle Befehle mit Agent-Starts, Konsumenten mit Cloud-Pin, `release_check.py`, `tests/test_agent_dispatch_drift_279.py` (Dispatch-Erkennung per Agent-Name bleibt erfüllt).

### Known Limitations / Out of Scope
- Agent-Texte nennen `.claude/hooks/...`; im Framework-Repo liegen die Hooks unter `core/hooks/` (bestehend, unverändert — die Agenten lasen bisher denselben Text per `cat`).
- Modul-Agenten (iOS, Home Assistant) im Plugin-Modus: weder lokal noch in der Cloud ausgeliefert (bestehend); eine unmarkierte Modul-Kopie in `.claude/agents` hat Vorrang und wird nicht überschrieben.
- Ob Claude die Prosa-Notation künftig als Parameter umsetzt, ist nicht mechanisch erzwingbar; der Test sichert nur den Befehlstext.

### Open Questions
- Keine an den PO (rein technisch; Entscheidungen oben nach etablierten Mustern getroffen).
