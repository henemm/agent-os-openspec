# Context: feat-470-spec-ampel

## Request Summary
Teil B von #468: Im Auto-Modus gibt eine Ampel im unabhängigen PO-Briefing die Spec frei (grün → automatisch, rot → PO). Setzt #469 voraus (`autonomy_mode()`, `record_approval()`, `approvals`).
Gesamtanalyse und Gate-Inventar: `docs/context/feat-468-autonomie-modus.md`.

## PO-Entscheidungen
- Ampel: grün → automatische Freigabe, rot → PO wie bisher (`approved`)
- Fast Track im Auto-Modus: Briefing (mit Ampel) erzwingen
- `auto` gilt NUR aus der wirksamen `config.yaml`/`openspec.yaml` (Hauptordner, `config_loader.find_config_file(find_project_root())`); `settings.local.json` darf `auto` nicht setzen (nicht schreibgeschützt — Adversary-Fund F003 aus #469). Schreibschutz der wirksamen Config: `bash_gate.py:598 _writes_effective_config` (#410/#418), Ausweg nur Override-Token
- Fake-Grün: Hash-Bindung des Briefings (`briefing_sha256`), Audit-Eintrag via `record_approval`, Auflistung automatischer Freigaben in der Abschlussmeldung; Urheberschaft des Briefings bleibt Known Limitation

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py` | `autonomy_mode()` (#469, liest heute `load_config()` inkl. settings.local.json → anpassen), `record_approval()`, `cmd_set_briefing` (:~1625-1690, schreibt `data["po_briefing"]` mit `spec_sha256`/`spec_frozen_sha256`), `_check_po_briefing` (:957, Fast-Track-Ausnahme :1014-1016 `skip_fast_track`), `_check_adr` (:686), `next_step` (:170, phase3 → „Freigabe der Spec (Stichwort: approved)“), `status_note` (:216), `record_transition`, `_SET_FIELD_PROTECTED`, `COMMANDS` |
| `core/hooks/phase_listener.py:513-575` | Referenz-Ablauf der menschlichen Freigabe (ADR → Briefing → `spec_approved=True` → `record_transition(...,"approval")` → `current_phase="phase4_approved"`) — bleibt unverändert |
| `core/agents/po-briefer.md` | Pflichtabschnitte (:69-99), Regeln (:118) → neuer Abschnitt `## Ampel` |
| `core/hooks/herdr_bridge.py:164-166` | Freitext-Schritt → `next=approved`; Auto-Schritt → `next=auto` |
| `core/commands/30-write-spec.md` | Step 3b/4 und Freigabe-Ausgabe (:161-201) → Verzweigung auf `AUTO_APPROVE` |
| `core/commands/00-intake.md:124-161` | Fast Track: „Spec + User-Freigabe immer“, kein Briefing |
| `scripts/ci_spec_gate.py` / `workflow.check_briefing_content` (:856) | ignoriert unbekannte Abschnitte → `## Ampel` CI-neutral |
| `skills/*/SKILL.md` | generiert via `scripts/sync_skills.py` |

## Analysis
- `autonomy_mode()` auf wirksame Config-Datei umstellen (YAML direkt laden, ohne Local-Overrides); fail → manual
- `po-briefer.md`: Abschnitt `## Ampel` mit genau einer Zeile `Ampel: grün` oder `Ampel: rot`; rot bei Abweichung vom Ticket, Scope-Frage, offener Entscheidung, AC ohne Test, vager AC; im Zweifel rot. Grün nur, wenn „Kritische Anmerkungen“ keine offene Entscheidung verlangt (Formulierung festlegen)
- Parser `parse_ampel(text) -> "green"|"red"`: genau ein Abschnitt, genau eine Zeile, akzeptiert grün/gruen/green; alles andere → red
- `set-briefing`: speichert zusätzlich `ampel` und `briefing_sha256`
- `workflow.py auto-approve` → stdout `AUTO_APPROVE=done|human` + `REASON=…`, Exit 0, fail-closed. Reihenfolge: Modus auto → phase3_spec + spec_file + noch nicht freigegeben → `_check_adr` → `_check_po_briefing` → Briefing-Datei frisch lesen, Hash = registrierter `briefing_sha256` → `parse_ampel` == green → gemeinsamer Helfer `_apply_spec_approval(data, trigger="auto")` (gleiche Wirkung wie Listener) → `record_approval(data,"spec","auto",…, evidence{briefing, briefing_sha256, spec_sha256, ampel})` → speichern
- Fast Track + Auto: `_check_po_briefing` ignoriert `skip_fast_track`, wenn Modus auto (Briefing Pflicht)
- `next_step`: phase3_spec + spec_file + Modus auto + `po_briefing.ampel == green` → „Auto-Freigabe der Spec (workflow.py auto-approve)“; sonst unverändert
- `status_note`: im Auto-Fall keine ❗Du-Pflicht für diesen Schritt (Formulierung prüfen; footer_gate bleibt fail-open bei Freitext)
- `herdr_bridge`: Schritt beginnt mit „Auto-“ → `next=auto`
- `30-write-spec.md`: nach Step 4 `auto-approve`; `AUTO_APPROVE=done` → Briefing als Info ausgeben (inkl. Hinweis „automatisch freigegeben“) und `40-tdd-red` selbst aufrufen; sonst bisherige Freigabe-Ausgabe
- `00-intake.md`: Fast Track im Auto-Modus mit Briefing
- `phase_listener.py` unverändert; `approved` funktioniert weiterhin

## Risks
- Fake-Grün (Known Limitation, s. o.)
- Drift zwischen Listener- und Auto-Freigabe → gemeinsamer Helfer oder Drift-Test
- Bestehende Briefings ohne Ampel → im Auto-Modus rot (human), im manual-Modus egal
- CI-Gate darf durch `## Ampel` nicht kippen (Test)
- Scope: workflow.py, po-briefer.md, herdr_bridge.py, 30-write-spec.md (+Skill), 00-intake.md (+Skill), CHANGELOG, Tests — über dem 5-Dateien-Richtwert, aber zusammenhängend
