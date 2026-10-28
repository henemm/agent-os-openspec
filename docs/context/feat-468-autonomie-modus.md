# Context: feat-468-autonomie-modus

## Request Summary
Issue #468: Im Auto-Modus sollen menschliche Freigaben entfallen, wo unabhängige Prüfer grün sind. Unabhängigkeit (po-briefer, implementation-validator) und CI-Spec-Gate bleiben.

## PO-Entscheidungen
- Schalter: `config.yaml` → `autonomy.mode: manual|auto`, Default `manual`, projektweit
- Spec-Freigabe: „Ampel“ — po-briefer stuft grün/rot ein; grün → automatisch, rot → Mensch
- Automatisch im Auto-Modus: GREEN „go“, Intake-Track, Commit-Frage, Workflow-Kette
- Annahme (in Spec bestätigen): immer menschlich bleiben AMBIGUOUS, zweites BROKEN/Circuit Breaker, Override, Deploy, Stop-Lock

## Kernbefunde (Analyse 2026-10-28)
- Alle Spec-Gates hängen an `spec_approved` → `phase4_approved`; `phase_listener.py:513-575` ist nur ein Setter (sieht nur User-Prompts). Auto-Pfad braucht neuen Setter in `workflow.py`, Listener bleibt unverändert.
- `green_approved` wird von keinem Gate gelesen; echtes GREEN-Gate ist Lock/Marker in `post_implementation_gate.py` (:93-97, :201-235). Marker darf nur der Listener schreiben (`bash_gate.py:64-65,110-113`).
- `ci_spec_gate.py` verlangt keine Freigabe-Evidenz; `check_briefing_content` (:856) ignoriert unbekannte Abschnitte → neuer `## Ampel`-Abschnitt CI-neutral.
- Kette teils schon autonom („Ohne /clear: rufe Skill selbst auf“): 30→40 (:198-201), 40→50 (:171-174), 50→60 (:372-376). Lücken: 00→10, 10→20 (`10-context.md:99ff`), 20→30 (`20-analyse.md:131ff`).
- `footer_gate` ist bei Freitext-Schritt fail-open (`_expected_command` → None) → kein Code nötig.
- `status_note` (`workflow.py:216`, :237-246) verlangt immer eine ❗Du-Zeile → im Auto-Modus anpassen.
- `herdr_bridge.py:164-166` mappt Freitext auf `next=approved`.
- `override-ambiguous` (`workflow.py:1785`) prüft keinen User-Token — „AMBIGUOUS bleibt menschlich“ ist nur Text.
- Circuit Breaker ist Text; `fix_loop_iterations` (:1394) zählt, blockt nicht; Budget-Rückfrage (#250/#341) existiert.

## Gate-Inventar
| Gate | Stelle |
|---|---|
| Spec-Freigabe setzen | `phase_listener.py:513-575` (ADR :520-523, `_check_po_briefing` :529-533, `spec_approved` :549, `record_transition(...,"approval")` :558, Phase :571) |
| GREEN setzen | `phase_listener.py:603-641` |
| Transition-Prüfung | `workflow.py:1055 _validate_transition` (Spec :1098-1105, feature-fast :1062-1074, Verdict :1118-1126) |
| ADR / Briefing | `_check_adr` :686, `_check_po_briefing` :957, `set-briefing` :1579 |
| Selbstfreigabe-Schutz | `_SET_FIELD_PROTECTED` :1433-1450, `_reset_approvals_on_backstep` :1367 |
| Texte | `00-intake.md:68-92,124-161`; `30-write-spec.md:37,161-201,247`; `50-implement.md:138-167,299-303`; `60-validate.md:208-283` |

## Vorgeschlagenes Design
- `workflow.py autonomy` → `AUTONOMY=auto|manual` (nur Literal `auto` schaltet; Absturz = manual); `autonomy` in `PLUGIN_CONFIG_KEYS`
- `workflow.py auto-approve` → `AUTO_APPROVE=done|human` + `REASON=` (fail-closed): Modus auto, phase3_spec, ADR + Briefing-Gate, Ampel frisch aus Briefing-Datei (genau eine Zeile `Ampel: grün|gruen|green` in `## Ampel`, sonst rot), Querprüfung „Kritische Anmerkungen = Keine“, Transition wie Listener (gemeinsamer Helfer `_apply_spec_approval`), `record_transition(...,"auto")`
- `set-briefing` speichert `ampel` + `briefing_sha256`; `auto-approve` prüft Hash neu
- `po-briefer.md`: Pflichtabschnitt `## Ampel`, „im Zweifel rot“
- GREEN: `post_implementation_gate.py` im Auto-Modus kein Lock (kein Fake-Marker); `workflow.py auto-green` (Audit, Voraussetzung GREEN-Artefakt + red_test_done)
- `next_step`/`status_note`/herdr: Auto-Schritt als Freitext, `next=auto`
- Audit: `approvals: []` append-only `{gate, by, mode, at, reason, evidence}`, in `_SET_FIELD_PROTECTED`; Anzeige in `status` und `/60-validate`
- Commands: 00/10/20/30/40/50/60 verzweigen auf `AUTONOMY=auto`; `deploy.autonomous` bleibt getrennt; Skills via `scripts/sync_skills.py`

## Risiken
1. Fake-Grün durch Orchestrator nicht deterministisch verhinderbar (edit_gate unterscheidet Agent/Orchestrator nicht) → Hash-Bindung, Audit, Sichtbarkeit, CI; als Known Limitation
2. Fast Track hat per Default kein Briefing → keine Ampel
3. Track-Selbstbestätigung kann zu niedrig bewerten → Fast Track umgeht Briefing/Adversary
4. `override-ambiguous` ohne Token-Prüfung
5. Config-Flip mitten im Workflow → live lesen, Modus pro Audit-Eintrag mitschreiben
6. Stop-Lock blockt Auto-Schritte über bash_gate (Test ergänzen)

## Umfang
Über Framework-Limit (>5 Dateien, >250 LoC). Vorschlag Schnitt A→B→C→D:
- A Fundament: config, config_loader, `autonomy`-CLI, `approvals`-Audit
- B Ampel + Auto-Spec-Freigabe: po-briefer, workflow (set-briefing, auto-approve, next_step/status_note), herdr_bridge, 30-write-spec
- C Auto-GREEN: post_implementation_gate, auto-green, 50-implement
- D Kette/Intake/Commit: 00, 10, 20, 40, 60 (Text)
