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
