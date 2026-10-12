# Context: fix-405-424-workflow-ausgaenge

## Request Summary
#405: Nach Rücksprung zur Spec wird die erneute Freigabe nicht erkannt, weil `spec_approved` stehen bleibt.
#424: Nach einer Analyse mit Entscheidung „nichts bauen“ gibt es keinen vorgesehenen Ausgang; die Fußzeile erzwingt `/20-analyse`.
PO-Vorgabe (2026-10-12): #405 muss nicht im vollen Workflow umgesetzt werden.

## #405 — Befund (nachgestellt)
Reproduktion im Wegwerf-Projekt (Skript im Scratchpad, `repro405.py`): Workflow in `phase6_implement` mit `spec_approved=true`, `green_approved=true`.
1. `workflow.py phase phase3_spec` → Phase wechselt, beide Flags bleiben `true`.
2. Prompt `approved` → Listener meldet „Spec ist bereits freigegeben. Zustand unverändert.“, Phase bleibt `phase3_spec`.

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/workflow.py:1305 `cmd_phase` | Rücksprung setzt keine Flags zurück (Ursache) |
| core/hooks/workflow.py:1012 `_validate_transition` | erlaubt Rücksprünge ohne Prüfung (Z. 1042); bei stehendem `spec_approved` passiert auch `phase phase4_approved` ohne neue Freigabe |
| core/hooks/workflow.py:1372 `_is_approved` | liest `spec_approved` oder Phasenindex |
| core/hooks/phase_listener.py:536 | Freigabe wirkt nur bei `phase3_spec` und nicht `spec_approved` |
| core/hooks/phase_listener.py:608-650 | `green_approved` analog |
| tests/test_write_log_phases_111.py | Vorlage für hermetische Subprozess-Tests (workflow.py + phase_listener.py) |

## #424 — Befund (aus Code gelesen, noch nicht nachgestellt)
- `expected_footer_command` (workflow.py:196) → `next_step()` leitet den Schritt nur aus der Phase ab; `phase2_analyse` ergibt immer `/20-analyse`.
- `cmd_abandon` (workflow.py:1702) existiert, ist aber nirgends verlinkt; `core/commands/99-reset.md` ruft nur `finish`.

## Existing Patterns
- Gate-Felder sind per `set-field` gesperrt (`_SET_FIELD_PROTECTED`, workflow.py:1352); Zustandswechsel laufen über eigene Befehle.
- Briefing ist per `spec_sha256` an die Spec gebunden; Alternative für #405: Freigabe ebenso an den Hash binden.

## Risks & Considerations
- `core/hooks/` ist Infrastruktur: Edit ohne laufenden Workflow ab phase6 braucht „override“.
- Rücksprung unter `phase4_approved` muss `spec_approved` zurücksetzen; unter `phase6_implement` zusätzlich `green_approved`. Der Adversary-/Briefing-Stand bleibt bewusst unberührt.
- Bestehende Tests, die `spec_approved` voraussetzen (test_gate_coverage, test_status_note_325 u. a.), müssen grün bleiben.
- Umfang #405: ca. 8 Zeilen in `cmd_phase` + 1 Testdatei. #424: eigener Zuschnitt (workflow.py, 99-reset.md, Skills-Sync, Tests).

## Analysis

### Type
Bugfix (zwei Workflow-Lücken, gemeinsames Ziel: der Zustandsautomat hat für Rücksprung und „nichts bauen“ keinen sauberen Weg).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | #405: `cmd_phase` setzt bei Rücksprung vor `phase4_approved` `spec_approved=False`, vor `phase6_implement` zusätzlich `green_approved=False`. #424: Befehl `no-build --reason`, setzt `no_build_reason` (in `_SET_FIELD_PROTECTED`); `next_step()` nennt dann `/99-reset` |
| core/commands/99-reset.md | MODIFY | Ohne `spec_file` (oder mit `no_build_reason`) `abandon --reason` statt `finish`; Begründung aus dem Feld oder erfragen |
| skills/99-reset/SKILL.md | GENERATE | `python3 scripts/sync_skills.py` (nie von Hand) |
| tests/test_rueckspruung_405.py | CREATE | Subprozess-Test nach Vorlage test_write_log_phases_111.py: Rücksprung → Flags zurück → `approved` → `phase4_approved` |
| tests/test_no_build_exit_424.py | CREATE | Fußzeile nennt `/99-reset` nach `no-build`; `abandon` archiviert; ohne Marker bleibt `/20-analyse` |

### Scope Assessment
- Files: 5 (davon 1 generiert)
- Estimated LoC: +~140/-~5 (Tests ~90, Code ~35, Doku ~15)
- Risk Level: MEDIUM — `spec_approved` wird von `_is_approved` (#379), `_validate_transition` und dem Listener gelesen; ein Reset bei Rücksprung ändert, was nach einem Rücksprung als freigegeben gilt (gewollt, aber zentrale Gate-Logik).

### Technical Approach
Regelweg, kein Modell nötig.
- **#405:** Reset beim Rücksprung in `cmd_phase`. Das ist die kleinste Lösung und schließt beide Folgen aus dem Issue (neue Freigabe wird erkannt; alte Freigabe gilt nicht für geänderte Spec). Adversary-/Briefing-Stand bleibt unberührt; das Briefing ist ohnehin per `spec_sha256` an die Spec gebunden.
  *Alternative:* Freigabe an den Spec-Hash binden. Robuster gegen Spec-Änderungen ohne Rücksprung, aber neues Feld, neuer Vergleich in Listener und Gate, und der Rücksprung-Fall (gleiche Spec, bewusst neu freigeben) bleibt offen. Würde ADR #379 („Freigabe bleibt bei Rücksprung stehen“) nicht kippen, sondern ergänzen. Nicht empfohlen: mehr Fläche für denselben Nutzen.
- **#424:** Neuer Befehl `workflow.py no-build --reason "…"` hält die PO-Entscheidung „nichts bauen“ im State fest. `next_step()` liefert dann `/99-reset #N`; `/99-reset` ruft ohne Spec `abandon` auf (der Befehl existiert, ist nur nirgends verlinkt).
  *Alternative 1:* Fußzeile in `phase2_analyse` akzeptiert immer auch `/99-reset`. Kleiner (3 Zeilen), nimmt dem Hook aber die Aussagekraft: nach jedem Kontext-Schritt wäre Abbruch „korrekt“.
  *Alternative 2:* eigene Endphase „verworfen“. Sauber, aber Eingriff in `PHASES`, `PHASE_NUMBERS`, alle Phasenlisten — viel zu groß für den Nutzen.
  Empfehlung: Marker-Befehl; er ist ehrlich (Begründung Pflicht, wie bei `abandon`) und lässt die Phasenliste unberührt.

### Dependencies
- `footer_gate.py` und `status_note()` hängen beide an `next_step()` — eine Änderung dort wirkt auf beide, keine Doppelpflege.
- `skills/` wird generiert; Drift blockt das Release.
- Bestehende Tests mit gesetztem `spec_approved` (test_gate_coverage, test_status_note_325 u. a.) müssen grün bleiben; Rücksprünge in Fixtures prüfen.

### Befunde gegen den Plan
- #424 ist bisher nur aus dem Code gelesen, nicht nachgestellt; Nachstellen (Workflow in phase2, Fußzeile `/99-reset` → Gate lehnt ab) folgt in der RED-Phase.
- Rücksprung unter `phase4_approved` nimmt `_is_approved` die Freigabe: Edits an `spec_file` sind danach wieder erlaubt — gewollt, in der Spec als AC festhalten.
- `/99-reset` ist `disable-model-invocation`: den Abschluss tippt der PO; die Fußzeile muss ihn deshalb als `❗ Du:` nennen können.

### Open Questions
- [ ] Soll `no-build` nur in `phase1/phase2` erlaubt sein? (Empfehlung: ja — später gibt es Spec und Freigabe, dort gilt der normale Abschluss.)
