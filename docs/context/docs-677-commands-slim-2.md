# Context: docs-677-commands-slim-2

## Request Summary
Schnitt 2 von #674 (Epic #649): `core/commands/30-write-spec.md` (14 544 B), `00-intake.md` (12 568 B) und `80-workflow.md` (10 931 B) zusammen um mindestens 40 % kürzen (38 043 B → ≤ 22 825 B). Ablauf und Pflichtschritte bleiben, Hintergrund wandert wörtlich nach `docs/befehle/<befehl>.md`. Kein Gate-Verhalten ändert sich.

## Related Files
| File | Relevance |
|------|-----------|
| core/commands/30-write-spec.md, 00-intake.md, 80-workflow.md | zu kürzende Befehlstexte |
| docs/befehle/50-implement.md, 60-validate.md | Vorbild aus #674 Schnitt 1 |
| tests/test_commands_slim_674.py | Größenwächter; Budgets der drei Dateien senken, LINKED erweitern |
| skills/*/SKILL.md | Generat (`scripts/sync_skills.py`) |
| core/hooks/workflow.py:2787, scripts/ci_spec_gate.py:275 | nennen „/30-write-spec Step 3b“ — Überschrift muss bleiben |

## Pin-Tests (Wortlaute, die bleiben müssen)
- 30-write-spec: test_ampel_kalibrierung_485 (AskUserQuestion, „nie per Auswahldialog“), test_clear_checkpoint_blocks (Checkpoint-Gerüst, gleich wie 10-context), test_cloud_agents_577 (Agent-Aufrufe spec-writer/spec-validator/po-briefer ohne model=, Fallback-Modell), test_config_additiv_622 (Planungsabsatz), test_context_stop_658/test_kontext_haushalt/test_auto_chain_flat_662/test_kette_auto_clear_489 (Kontext-Haushalt-Absatz), test_foreground_checkers_83 (spec-validator-Aufruf run_in_background=false), test_spec_ampel_470 (auto-approve, AUTO_APPROVE=done/human), test_setup_alias_sync_150 ({{OPENSPEC_VERSION}}), test_skills_sync (Briefing-Marker, MARKER_EXEMPT, „genau einmal…“, Wiedereinstieg „in 2 Sätzen“), test_wakeup_blocks.
- 00-intake: test_intake_bugs_250a1 (Bug-Abschnitt nach Regex `^#{2,3} .*Bugs?`, vor „### 2. Score präsentieren“, „Ursache bekannt … ≤3 Dateien … Low“, zwei start-Blöcke), test_intake_two_tracks_254 („mindestens {MIN_ROUNDS}“, kein „1 Runde“), test_adversary_risk_342 (Risiko-Zeile, „eine Runde“, `adversary_dialog.py risk`), test_autonomy_kette_472 (Immer-menschlich-Zeile, „ohne Rückfrage“, „sofort“, „Fast Track nur bei Summe 0“, STOP/Ursache unklar in 2500 Zeichen nach AUTONOMY=auto), test_auftrag_551, test_spur_591 („### 1a.“-Abschnitt mit --spur/spur:<name>/Epic), test_session_register_docs_120_121 (claim vor Score), test_issue_claim_461 (--uebernehmen, registrier), test_config_additiv_622, test_spec_ampel_470 (Auto-Modus + Briefing in 600 Zeichen), test_plan_kopf_612 (issue-brief), test_zeitschaetzung_620 (--score, workflow.py estimate).
- 80-workflow: test_handoff_667/668 (handoff, --mark, --start, HANDOFF_DONE, MARKED, WARN), test_issue_claim_461, test_skills_sync (Wiedereinstieg).
- Global: test_endzustand_550, test_guard_quote_vs_write_276 („workflow.py find 42“), test_no_tmp_paths, test_vorlagen_klartext_597, test_agent_dispatch_drift_279.

## Existing Patterns
- #674 Schnitt 1: Befehl behält Ablauf + gepinnte Wortlaute, Satz „Hintergrund: `docs/befehle/<befehl>.md` (Plugin-Ordner)“; Doku mit gleichnamigen `##`-Abschnitten, Text wörtlich verschoben.

## Dependencies
- Upstream: sync_skills.py (Marker-Block, Pfad-Ersetzung), release_check.py.
- Downstream: jede Sitzung lädt die Skills; Hooks verweisen auf „Step 3b“.

## Risks & Considerations
- −40 % bei dichten Pins schwer; 00-intake enthält viel gepinnten Text. Ausweg: Erläuterungen (Mini-Spec-Vorlage, Modell-Tabelle, Stufen-Tabelle, Planungsdetails) verschieben.
- 00-intake hat zwei „### 1c.“-Überschriften; Bug-Regex greift erste Überschrift mit „Bug“ — Reihenfolge beachten.
- 30-write-spec ist MARKER_EXEMPT (eigener Briefing-Marker).
- Umfangsgrenze 250 Zeilen je Workflow (Produktivzeilen).

## Analyse (kurz, Summe 1)
Abschnittsgrößen gemessen. Budgets (−41 % zusammen, 38 043 → ≤ 22 528 B):
- `30-write-spec.md` ≤ 8 704 B: Step 0 auf Kernbefehle, „Hängende Subagenten“, „Agent-Typen und Fallback“-Erläuterung, Step-3b-Begründung, Step-4b-Erläuterung, Freigabe-Ausgabe-Erläuterung und „After Approval“-Details nach `docs/befehle/30-write-spec.md`. Bleiben: Überschrift „Step 3b“ (Hooks verweisen), Agent-Aufrufe samt Fallback-Zeile, Checkpoint-Gerüst, Kontext-Haushalt-Absatz, Planungsabsatz, AskUserQuestion-Verbot.
- `00-intake.md` ≤ 8 192 B: Erläuterungen zu Scoring/Tiefe, 1a-Details (Auftrag-Besitz, ALTAUFTRAG), 1c-Issue-Kurzfassung-Details, Registrierung am Issue, Zeitschätzungs-Beispiele, Modell-Empfehlung, Stufen-Tabelle, Mini-Spec-Vorlage nach `docs/befehle/00-intake.md`. Bleiben alle gepinnten Sätze; Reihenfolge der Überschriften (1a, Bugs vor „### 2. Score präsentieren“) unverändert.
- `80-workflow.md` ≤ 5 632 B: Referenzteil (Workflow Phases, State Architecture, Code Modification Rules, Audit Trail, Execution Log, Automatic Phase Detection, QA Gate, Migration, Retro-Beispiele) nach `docs/befehle/80-workflow.md`; Befehlsübersicht und handoff/queue/Wiedereinstieg bleiben.
- Test: `tests/test_commands_slim_674.py` Budgets senken, `LINKED` um die drei Befehle erweitern; neuer Test `tests/test_commands_slim_677.py` für Summe ≤ 22 825 B (−40 %).
