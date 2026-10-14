# Context: feat-439-spec-freeze-teilhash

## Request Summary
Issue #439: Seit #230 ist die ganze Spec nach der Freigabe gesperrt; einziger Ausweg ist
"override" (öffnet 1 h alle Gates). Künftig soll nur der vom PO freigegebene Teil
(Purpose, Scope, DoD, AC-Text, ADR) gesperrt und gehasht werden; Begleittext (Frontmatter,
`- Test:`-Zeilen, Known Limitations, Implementation Details, Changelog) bleibt ohne Token
änderbar, Änderungen daran werden im State protokolliert. "override" öffnet den Spec-Freeze
nicht mehr; Änderungen am Freigegebenen → zurück nach phase3_spec.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/edit_gate.py:580-601` | Schritt 1d Spec-Freeze: blockt jede Edit/Write auf `spec_file` ab phase4_approved, Override-Token als Ausweg |
| `core/hooks/edit_gate.py:236-282` | `_find_workflow_by_spec_file`, `_approved_phases` — Workflow-Zuordnung der Spec (live JSON, kein Archiv) |
| `core/hooks/workflow.py:784-786` | `spec_sha256(content)` — SHA-256 über den GANZEN Text (utf-8) |
| `core/hooks/workflow.py:950-1000` | `_check_po_briefing` — Aktualitätsprüfung `entry.spec_sha256 != spec_sha256(spec)` → "PO-Briefing ist veraltet" |
| `core/hooks/workflow.py:1020-1075` | Transition-Checks: `_check_po_briefing` bei jeder Transition ≥ phase4_approved (inkl. phase8_complete) |
| `core/hooks/workflow.py:~1500-1560` | `cmd_set_briefing` — berechnet Hash, speichert im State, stempelt `spec_file`/`spec_sha256` in Briefing-Frontmatter (`stamp_briefing_frontmatter`) |
| `core/hooks/phase_listener.py:548` | Freigabe-Phrase ruft `_check_po_briefing` |
| `scripts/ci_spec_gate.py:286-330` | `_check_briefing`: vergleicht Frontmatter-`spec_sha256` mit `hashlib.sha256(read_bytes())` — eigene Hash-Implementierung (Bytes, nicht `workflow.spec_sha256`) |
| `core/hooks/hook_utils.py:621` | `extract_ac_entries` — section-gebundener AC-Parser, verwirft eingerückte `- Test:`-Sub-Bullets (wiederverwendbar für "AC-Text ohne Test-Zeilen") |
| `core/hooks/override_token.py` | Override-Token (TTL, pro Workflow / `__infra__` / global) |
| `templates/spec_template.md` | Abschnitte: Approval, GitHub Issue, Purpose, Source, Dependencies, Scope, Implementation Details, Expected Behavior, Error Handling, Known Limitations, Definition of Done, Acceptance Criteria (mit `- Test: *(populated after TDD RED phase)*`), Test Plan, ADR, Changelog |
| `core/agents/docs-updater.md:37-48` | Regel "freigegebene Specs schreibgeschützt (#230)" — muss angepasst werden |
| `core/commands/60-validate.md:170` | Hinweis zum Spec-Hash/docs-updater |
| `tests/test_edit_gate_spec_freeze_230.py` | 8 Tests zum #230-Freeze, u.a. `test_edit_with_override_allowed` (wird durch #439 umgedreht) |
| `tests/test_po_briefing_gate.py`, `tests/test_ci_spec_gate.py`, `tests/test_workflow_resolution_consolidation.py` | Prüfen `spec_sha256` = SHA über Gesamttext; Fixtures erzeugen Hash selbst |

## Existing Patterns
- Section-gebundenes Markdown-Parsing per Regex/State-Machine (`extract_ac_entries`, `_briefing_section_body`, `check_adr_content`) — eine Quelle, CI-Gate importiert `workflow.py`/`hook_utils` statt Regeln zu duplizieren.
- CI-Gate lädt `workflow.py` per `_load_hook_module(root, "workflow")` aus `core/hooks` oder `.claude/hooks`; ältere Projekt-Kopien werden per `getattr`-Fallback unterstützt (Muster bei `po_briefing_max_words`).
- Edit-Gate-Schritte sind nummeriert; 1d muss VOR den Always-Allowed-Schritten (2/2b) stehen, sonst winkt `docs/`/`\.md$` die Spec durch.
- State-Protokolle als Listen im Workflow-JSON (z.B. `test_artifacts`, Phase-Transitions).

## Dependencies
- Upstream: `hook_utils` (State-Lesen, AC-Parser), `override_token`, `workflow.PHASES`, `config_loader` (`po_briefing_gate`).
- Downstream: Freigabe-Phrase (phase_listener), alle Transitionen ≥ phase4, CI-Spec-Gate in Konsumenten-Projekten (setup.py installiert `ci_spec_gate.py` + Workflow-YAML), 50 bestehende Briefings mit Gesamt-Hash in `docs/briefings/`.

## Existing Specs
- `docs/specs/fix-230-spec-freeze-after-approval.md` — Vorgänger (Gesamt-Freeze)
- `docs/specs/fix-144-briefing-worktree-path.md` — Briefing-Pfadauflösung
- PO-Briefer/CI-Gate (3.20/3.21) — siehe CHANGELOG

## Risks & Considerations
- **Edit-Gate sieht nur den Edit, nicht das Ergebnis:** Für Edit muss der neue Inhalt simuliert werden (old_string→new_string, `replace_all`), für MultiEdit alle Edits, für Write der volle Inhalt; dann Teil-Hash alt vs. neu vergleichen. Fehlt/scheitert die Simulation → fail-closed (blocken).
- **Abschnitts-Zuordnung muss robust sein:** Überschriften-Varianten (`##`/`###`, Zusatztext, Groß/Klein), deutsche Titel (z.B. "Architektur-Entscheidung (ADR)"), unbekannte Abschnitte. Unbekannte Abschnitte: Default "freigabe-relevant" (fail-closed) oder "beweglich"? → Analyse-Entscheidung. Expected Behavior, Error Handling, Test Plan, Source, Dependencies, Approval, GitHub Issue sind im Issue nicht zugeordnet.
- **Umgehung durch Verschieben:** Text aus einem freigegebenen Abschnitt in "Known Limitations" verschieben, oder neue Überschrift einfügen, die einen freigegebenen Abschnitt zerteilt — Teil-Hash muss das erkennen (Abschnittsgrenzen sind Teil des Hashes).
- **`- Test:`-Zeilen unter AC:** müssen aus dem Hash fallen, aber nur eingerückte Sub-Bullets unter einem AC — `extract_ac_entries` hat diese Logik schon.
- **Migration:** Bestehende Briefings/State-Einträge tragen Gesamt-Hash. Bis zur nächsten Freigabe gültig lassen → Hash-Version unterscheidbar machen (z.B. `spec_hash_v: 2` oder Präfix), alter Hash = Gesamt-Hash-Vergleich.
- **CI-Gate hashed Bytes, workflow.py Text** — bei der Umstellung auf eine gemeinsame Funktion vereinheitlichen; CI-Gate in Konsumenten-Projekten kann eine ältere `workflow.py` laden → Fallback nötig.
- **Override-Semantik ändert sich (Breaking):** `test_edit_with_override_allowed` dreht um; CLAUDE.md/docs-updater/60-validate-Texte anpassen. Notausgang für echte Notfälle bleibt: Rücksprung nach phase3_spec (#405 setzt Freigaben dabei zurück).
- **Bash-Weg** (sed auf Spec) ist durch #230 schon nicht abgedeckt — außerhalb des Scopes, nur dokumentieren.
- **Spur der beweglichen Änderungen** (Zeitpunkt, Abschnitt) im State: Schreibzugriff aus einem PreToolUse-Hook auf den Workflow-State — Schutz-/Integritätsregeln für State-Dateien (#416/#422) beachten.

## Analysis

### Type
Feature (Änderung eines bestehenden Kern-Gates, Breaking: override öffnet den Spec-Freeze nicht mehr)

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | Neue `frozen_spec_sha256(content)` (eine Quelle); `set-briefing` stempelt Doppelhash; `_check_po_briefing` vergleicht Teil-Hash, Legacy = Gesamt-Hash; `set-briefing` nach Freigabe erlaubt, wenn Legacy-Hash exakt zum aktuellen Inhalt passt (Neu-Stempel ohne neue Freigabe) |
| `core/hooks/hook_utils.py` | MODIFY | Section-Splitter (H2-Grenzen, Code-Fences ignorieren, Alias-Matching) |
| `core/hooks/edit_gate.py` | MODIFY | Schritt 1d: neuen Inhalt simulieren (Edit/MultiEdit/Write), Teil-Hash aktuelle Datei vs. simulierte Fassung; gleich → weiter, verschieden → block mit Rücksprung-Anleitung; Override-Ausnahme entfällt |
| `core/hooks/edit_verify.py` | MODIFY | Spur: nach erfolgreichem Edit an beweglichen Teilen Eintrag (Zeit, Abschnitt) im Workflow-State über gehärtete State-API (#416/#422) |
| `scripts/ci_spec_gate.py` | MODIFY | Teil-Hash über `workflow.frozen_spec_sha256` (getattr-Fallback auf Byte-Gesamthash für ältere Projekt-Kopien) |
| `templates/spec_template.md` | MODIFY ggf. | Hinweis welche Abschnitte nach Freigabe beweglich sind |
| `core/agents/docs-updater.md`, `core/commands/60-validate.md`, `CLAUDE.md`, `CHANGELOG.md`, `skills/` (sync) | MODIFY | Texte zu #230-Freeze/override anpassen |
| `tests/test_edit_gate_spec_freeze_230.py` | MODIFY | `test_edit_with_override_allowed` dreht um |
| `tests/test_spec_freeze_partial_hash_439.py` | CREATE | Neue Tests (Hash-Klassifikation, Umgehungen, Gate, Legacy, CI, Spur) |
| `tests/test_po_briefing_gate.py`, `tests/test_ci_spec_gate.py`, `tests/test_workflow_resolution_consolidation.py` | MODIFY | Fixtures auf neuen Stempel/Legacy-Pfad |

### Scope Assessment
- Files: ~10 Code/Test + Doku
- Estimated LoC: +450..650 (davon ~250 Tests) / -30
- Risk Level: HIGH (Kern-Gate edit_gate, Briefing-Gate, CI-Gate; ein Klassifikationsfehler im Hash = Gate-Bypass) → 2 Adversary-Runden

### Technical Approach (Entscheidungen, Tech Lead)
1. **Klassifikation fail-closed:** Eingefroren ist alles, was nicht explizit beweglich ist. Beweglich: Frontmatter; H2-Abschnitte `Known Limitations`, `Implementation Details` / `Implementierungsdetails`, `Changelog`, `Approval` (wird vom System gestempelt). Matching: H2 normalisiert (lowercase, Klammerzusatz ab `(` weg, Whitespace kollabiert) gegen kleine en/de-Alias-Tabelle. H3 gehört zum H2. `## ` innerhalb von Code-Fences ist keine Überschrift. Gezählt in docs/specs: Known Limitations 61, Implementation Details 57, Changelog 66, Implementierungsdetails 10; "Bekannte Einschränkungen" kommt nicht vor.
2. **AC-Abschnitt:** komplett eingefroren, ausgenommen NUR eingerückte Zeilen, die mit `- Test:` beginnen (+ deren Fortsetzungszeilen). NICHT `extract_ac_entries` wiederverwenden — der verwirft alle eingerückten Sub-Bullets; ein AC mit eingerückten `- Given/When/Then` würde sonst beweglich (Bypass). Heute nutzt keine Spec diese Form (grep = 0), die Regel muss es trotzdem abdecken.
3. **Test Plan: eingefroren.** Er enthält laut Template Testbefehle, Testnamen stehen in den `- Test:`-Zeilen → Issue-Akzeptanz "Testname ändern ohne override" bleibt erfüllt. Im Spec-Block "Wo ich für dich entschieden habe" ausweisen.
4. **Hash-Form:** Zeilenenden normalisieren (`\r\n`→`\n`), Überschriftenzeilen und Klassifikation gehen in den Hash ein → Verschieben von Text in einen beweglichen Abschnitt oder Zerteilen eines eingefrorenen Abschnitts durch eine neue bewegliche Überschrift ändert den Hash.
5. **Stempel-Format = Doppelstempel (C2), nicht `v2:`-Präfix:** `ci_spec_gate.py` wird per `setup.py` als Kopie in Konsumenten-Repos committet und erneuert sich nur per `--update`, das Plugin (Stempel-Schreiber) aber automatisch. Mit Präfix im selben Feld würde jede alte CI-Kopie jedes neue Briefing als veraltet melden. Daher: `spec_sha256` bleibt Gesamt-Hash (alte CI-Kopien funktionieren weiter; sie werten Änderungen an beweglichen Teilen allerdings weiterhin als "veraltet" — bekannte Einschränkung bis `setup.py --update`), neues Feld `spec_frozen_sha256` = Teil-Hash. Neue Gates prüfen bevorzugt das neue Feld; fehlt es (Legacy) → Gesamt-Hash-Vergleich.
6. **Migration ohne Schreiben im Gate:** Workflows mit Legacy-Stempel: `set-briefing` wird nach Freigabe erlaubt, wenn der gespeicherte Gesamt-Hash exakt zum aktuellen Inhalt passt (Inhalt nachweislich identisch → keine neue Freigabe nötig); schreibt dann den Doppelstempel. Das Edit-Gate schreibt nichts.
7. **Edit-Gate-Referenz:** Teil-Hash der aktuellen Datei vs. simulierte neue Fassung — NICHT gegen den gespeicherten Stempel (#230 friert auch Workflows ohne Briefing ein: Fast Track / Gate aus). Stempel prüft weiterhin `_check_po_briefing` bei Transitionen.
8. **Simulation:** Edit = exakter `str.replace` (count 1 bzw. `replace_all`), MultiEdit sequentiell, Write = voller Inhalt. old_string nicht gefunden / mehrdeutig ohne replace_all / Lesefehler → block (fail-closed) mit Hinweis "Edit präzisieren oder Write verwenden". (Claude Codes Anführungszeichen-Normalisierung kann Fehlblocks erzeugen — dokumentierter, sicherer Fehlermodus.)
9. **Block-Meldung:** "Das ändert, was freigegeben wurde → `workflow.py phase phase3_spec`, neues Briefing, neue Freigabe". Rücksprung ist vorhanden: `_validate_transition` erlaubt Rückwärts-Transitionen, `_reset_approvals_on_backstep` (#405) setzt Freigaben zurück. Override öffnet den Freeze nicht mehr (weder Workflow- noch `__infra__`- noch globales Token).
10. **Spur:** `edit_verify.py` (PostToolUse, nur wenn Edit tatsächlich auf Disk) hängt `{ts, sections}` an eine State-Liste (z.B. `spec_post_approval_edits`) an — nur über gehärtete State-API. Bash/sed-Wege: außerhalb des Scopes (seit #230 ungedeckt), dokumentieren; eingefrorene Änderungen per Bash fängt `_check_po_briefing` bei der nächsten Transition ab.

### Dependencies
- Upstream: `hook_utils` (State-Lesen/atomares Schreiben), `workflow.PHASES`, `config_loader` (`po_briefing_gate`), `override_token` (wird für 1d nicht mehr konsultiert).
- Downstream: phase_listener (Freigabe-Phrase → `_check_po_briefing`), alle Transitionen ≥ phase4, CI-Spec-Gate (auch committete Kopien in Konsumenten-Repos), ~50 bestehende Briefings mit Gesamt-Hash (bleiben gültig).
- Reihenfolge: (1) Splitter + `frozen_spec_sha256` + Unit-Tests → (2) `set-briefing`/`_check_po_briefing` inkl. Legacy + Neu-Stempel → (3) CI-Gate mit Fallback → (4) edit_gate 1d → (5) Spur in edit_verify → (6) Doku/Template/CHANGELOG/sync_skills.

### Open Questions
- Keine blockierenden. Tech-Lead-Entscheidungen 1–10 werden in der Spec im Block "Wo ich für dich entschieden habe" ausgewiesen (insb. Test Plan eingefroren, Approval beweglich, Doppelstempel statt Präfix, override öffnet den Freeze nicht mehr).
