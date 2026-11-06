# Context: fix-schritte-ueberspringen

## Request Summary
Der PO berichtet, dass Claude in Sessions wiederholt Workflow-Schritte überspringt. Eine betroffene Session nennt drei Ursachen im Plugin: (1) der Text eines Slash-Befehls kam nicht an („Skill loaded, instructions unchanged“), (2) `workflow.py phase phase7_validate` ließ sich ohne Adversary-Nachweis setzen, (3) der Fußzeilen-Hook korrigierte die ❗Du-Zeile ohne Begründung. Der PO stellt klar: Das Problem ist generell, nicht an `/50-implement` gebunden.

## Reproduktion (diese Cloud-Session, 2026-11-06)
- Aufruf des Skills `50-implement` lieferte exakt zwei Zeilen: den Alias-Marker und `/agent-os-openspec:50-implement`. Kein Befehlstext. Ursache: `.claude/commands/<name>.md` ist ein Text-Redirect auf den Plugin-Skill; Cloud-Sitzungen laden keine Plugins (README „Cloud sessions“, #520), der Redirect zeigt ins Leere.
- Betroffen sind alle 11 Aliase mit `disable-model-invocation: false` (00-intake, 01-feature, 10-context, 20-analyse, 30-write-spec, 40-tdd-red, 50-implement, 60-validate, 82-test, 83-user-story, 90-retro). Die vier Vollkopien (70-deploy, 80-workflow, 81-add-artifact, 99-reset) tragen den Text selbst.
- `workflow._validate_transition`: Adversary-Verdict und Dialog-Nachweis werden erst bei `tgt_idx >= phase8_complete` geprüft (core/hooks/workflow.py:1862ff). Der Wechsel `phase6b_adversary → phase7_validate` prüft nur RED-Artefakte.
- `footer_gate.py` blockt mit „FUSSZEILE FALSCH: Fußzeile nennt X, korrekt ist Y. Gib die Fußzeile erneut … aus.“ — ohne Phase und ohne Grund (core/hooks/footer_gate.py, `block(...)` am Ende von `main`).

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/alias_sync.py | `alias_content()` erzeugt den Soll-Inhalt der Kurz-Aliase (Text-Redirect vs. Vollkopie); einzige Quelle für setup.py und session_banner.py |
| setup.py | `generate_command_aliases`, `refresh_command_aliases` schreiben die Aliase; nutzt alias_sync |
| .claude/commands/*.md | Die 15 committeten Aliase dieses Repos (Cloud-Sitzungen laden sie, aber kein Plugin) |
| core/hooks/workflow.py | `_validate_transition` (Zeile ~1797): Gate-Prüfungen je Zielphase; `cmd_phase`; `NEXT_STEP`, `next_step()`, `expected_footer_command()` |
| core/hooks/adversary_dialog.py | `check_dialog_evidence`, `phase8_code_files`, `coverage_gate_enabled` — Nachweisprüfung, die Phase 8 und Commit-Gate teilen |
| core/hooks/footer_gate.py | Stop-Hook; `_expected_command(name)` liest State, `main()` blockt per `block(...)` |
| core/hooks/bash_gate.py | Commit-Gate 5c nutzt dieselbe `check_dialog_evidence` — fing den Fehler der berichteten Session erst beim Commit |
| core/commands/50-implement.md | Setzt `phase phase7_validate` nach VERIFIED (Zeile 326) |
| core/commands/60-validate.md | Prerequisites nennen Adversary; Gate-Wirkung (#253/#259) beschreibt bisher nur Phase 8 und Commit |
| scripts/sync_skills.py | Erzeugt skills/*/SKILL.md aus core/commands; Hook-Pfad-Aufloesung (SETUP_BLOCK) via CLAUDE_PLUGIN_ROOT / installed_plugins.json / .claude/hooks |
| tests/test_alias_marker_position_251.py, test_alias_robust_350.py, test_alias_sync_robust_400.py, test_session_banner.py | Bestehende Alias-Tests (Marker-Position, Erkennung, Version) |
| tests/test_spec_content_gate_521.py::test_later_phase_transition_not_blocked, tests/test_effort_budget_250b.py::test_budget_never_blocks_a_transition | Setzen heute `phase phase7_validate` ohne Verdict — müssen mit dem neuen Gate ein Nachweis-Fixture bekommen oder auf phase6b zielen |
| tests/test_spec_freeze_partial_hash_439.py (`_dialog_text`, stamp + add-artifact + qa_gate) | Vorbild für ein gültiges Dialog-Nachweis-Fixture |

## Existing Patterns
- Gate-Prüfungen hängen an `tgt_idx >= PHASES.index(...)` in `_validate_transition`; Phase-8-Block: Verdict → `check_dialog_evidence(changed_files)` (#253/#259) → `_evidence_reason` (#447). Fast Track (`feature-fast`) prüft nur Freigabe + Evidence.
- Fail-open ist die tragende Anforderung des footer_gate; Meldungstext wird aktuell nicht getestet (kein Test enthält „FUSSZEILE FALSCH“).
- Aliase: Marker direkt nach dem Frontmatter (#251); `is_alias_file`, `alias_version` (nur Vollkopien), `find_stale_aliases`. Thin Redirects liefern `alias_version() is None`.
- Claude-Code-Doku (geprüft 2026-11-06, code.claude.com/docs/en/skills.md): Inline-Bash `` !`cmd` `` bzw. ```` ```! ```` -Block wird VOR dem Senden an Claude ausgeführt und ersetzt; `${CLAUDE_PROJECT_DIR}` ist als Substitution verfügbar; `allowed-tools: Bash(...)` genehmigt den Befehl vor, sonst bricht der Aufruf außerhalb des Auto-Modus ab. Cloud-Sitzungen laden `.claude/commands/` (Teil des Klons), aber keine Plugins (`enabledPlugins`).

## Dependencies
- Upstream: `hook_utils` (resolve_active_workflow, read_state_json), `config_loader`, `adversary_dialog` (Nachweis), `workflow.next_step`.
- Downstream: `session_banner.py` (Alias-Refresh, Version), `setup.py` (Alias-Erzeugung), `scripts/release_check.py` (Skills-Drift, Cloud-Hooks), `bash_gate.py` Commit-Gate (teilt check_dialog_evidence), alle Konsumenten-Projekte mit Aliasen.

## Existing Specs
- `docs/specs/short-command-aliases.md` — Kurz-Aliase (#87)
- Specs zu #253 (Dialog-Nachweis), #259 (Abdeckung), #234 (footer_gate), #520 (Cloud-Hooks) in `docs/specs/`

## Risks & Considerations
- Alias-Umbau trifft jedes Konsumenten-Projekt beim nächsten `--refresh-aliases`/Banner-Refresh; Inline-Bash im Alias braucht `allowed-tools`, sonst bricht der Befehl im Default-Permission-Modus ab.
- Gate in Phase 7: bestehende Workflows, die in phase6b stehen, brauchen ab jetzt den Nachweis vor Phase 7 (gewollt; Migration dokumentieren). Fast Track bleibt unverändert.
- Footer-Meldung: fail-open muss bleiben; zusätzliche Daten (Phase) dürfen keinen neuen Ausnahmepfad öffnen.
