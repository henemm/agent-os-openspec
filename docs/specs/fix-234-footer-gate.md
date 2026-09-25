---
entity_id: fix-234-footer-gate
type: bugfix
created: 2026-09-25
updated: 2026-09-25
status: draft
version: "1.0"
tags: [stop-hook, footer-gate, workflow, phase-listener, determinism]
---

# Footer-Gate — deterministische Prüfung der ❗Du-Fußzeile

## Approval

- [ ] Approved

## Purpose

Die ❗Du-Fußzeile am Ende jeder Claude-Antwort ist die einzige Zeile, die der PO als „das
tippe ich jetzt" liest. Ein neuer Stop-Hook (`core/hooks/footer_gate.py`) prüft diese Zeile
**mechanisch** gegen den deterministisch aus dem Workflow-State berechneten Pflicht-Schritt
(`workflow.next_step()`) und erzwingt bei einer Abweichung eine Korrektur — statt, wie die
vier Vorgänger-Fixes (#174/#209/#213/#221), erneut nur den Prompt-Text zu verschärfen. Issue
#234.

## Source

- **File:** `core/hooks/footer_gate.py` (neu)
- **Identifier:** `main()`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py::next_step()` | Funktion | deterministische Quelle des korrekten Pflicht-Schritts |
| `core/hooks/workflow.py::expected_footer_command()` (neu) | Funktion | dünne Hülle: `next_step()` + `issue_number()`, dieselbe Quelle wie `status_note()` |
| `core/hooks/hook_utils.py::resolve_active_workflow()` | Funktion | Auflösung des aktiven Workflow-Namens (worktree-aware) |
| `core/hooks/hook_utils.py::framework_disabled()` | Funktion | Fail-open-Schalter, wenn das Framework für das Projekt abgeschaltet ist |
| `hooks/hooks.json` | Config | Registriert den neuen Hook auf dem Event `Stop` |
| `core/hooks/phase_listener.py::_stop_lock_path()` | Vorbild | Muster für eine worktree-lokale Zustandsdatei unter `.claude/` |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/footer_gate.py` | CREATE | Stop-Hook: Fußzeile gegen `next_step()` prüfen, fail-open, Schleifenschutz (~110 LoC) |
| `hooks/hooks.json` | MODIFY | Event `Stop` registrieren (~8 LoC) |
| `core/hooks/workflow.py` | MODIFY | `expected_footer_command(data)` als dünne Hülle um `next_step()` + `issue_number()` (~12 LoC) |
| `tests/test_footer_gate_234.py` | CREATE | AC-Tests: Treffer, alle Fail-open-Fälle, Schleifenschutz (~130 LoC) |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]` |
| `.claude-plugin/plugin.json` | MODIFY | Versionsbump (siehe ADR) |

### Estimated Changes

~+260 / -0 LoC, knapp über dem 250-LoC-Scoping-Limit — fast ausschließlich Testcode
(`tests/test_footer_gate_234.py`, ~130 der ~260 Zeilen). Wird der Rahmen enger geprüft,
fliegt **zuerst der Test-Umfang** (z. B. Zusammenlegen mehrerer Fail-open-Fälle in
parametrisierte Tests), **nicht** die Fail-open-Logik selbst — die trägt das Risiko dieser
Änderung (sie läuft bei jedem Turn-Ende in jedem Konsumenten-Projekt). Reicht das Kürzen
nicht, wird ein LoC-Override angefordert statt die Fail-open-Abdeckung zu kürzen.

## Implementation Details

Ablauf von `footer_gate.py::main()` (Stop-Hook):

1. Payload von stdin lesen, `last_assistant_message` extrahieren. `framework_disabled()`
   zuerst prüfen → bei `True` sofort Exit 0, kein weiterer Schritt.
2. In `last_assistant_message` die **letzte** Zeile suchen, die mit `❗ Du:` oder `‼️ Du:`
   beginnt (Regex über alle Zeilen, letzter Treffer gewinnt — konsistent mit der
   `status_note()`-Regel „GENAU EINE Zeile ganz am Ende"). Keine solche Zeile gefunden →
   Exit 0.
3. Aus dieser Zeile den ersten `/<befehl>`-Token extrahieren (Regex `/[a-zA-Z][\w-]*`).
   Kein Slash-Token gefunden → Exit 0 (die Zeile markiert dann einen Freitext-Schritt wie
   „Freigabe der Spec", das Gate prüft nur Slash-Befehle).
4. Aktiven Workflow über `hook_utils.resolve_active_workflow()` auflösen, `workflows/<name>.json`
   lesen. Kein aktiver Workflow, Datei fehlt, JSON kaputt/unlesbar → Exit 0 (Try/Except um den
   gesamten State-Zugriff, keine Ausnahme darf den Hook zum Absturz bringen).
5. `workflow.expected_footer_command(data)` aufrufen. Liefert dies `None` oder einen Wert ohne
   führenden Slash (z. B. `phase8_complete` → `None`, `phase3_spec` mit vorhandener Spec →
   „Freigabe der Spec (Stichwort: approved)") → Exit 0.
6. Beide Slash-Befehle vergleichen (Basisbefehl ohne Issue-Suffix, also `/40-tdd-red` vs.
   `/40-tdd-red #12`-Präfix). Identisch → Exit 0. Verschieden →
   **Schleifenschutz zuerst prüfen** (Schritt 7), dann ggf. blocken.
7. Schleifenschutz: `.claude/footer_gate_state.json` (worktree-lokal nach demselben Muster wie
   `phase_listener.py::_stop_lock_path()`) enthält eine Kennung des zuletzt korrigierten Turns.
   Stimmt sie mit der aktuellen Turn-Kennung überein → Exit 0 (keine zweite Korrektur für
   denselben Turn). Zusätzlich, falls im Payload vorhanden: `stop_hook_active` auswerten und
   bei `True` ebenfalls Exit 0 erzwingen (defensiver Zusatz, kein tragendes Kriterium — siehe
   Known Limitations). Sonst: Kennung in die Zustandsdatei schreiben, `block()` mit Exit 2 und
   einer stderr-Meldung, die beide Befehle nennt: „Fußzeile nennt `/<falsch>`, korrekt ist
   `/<richtig>`. Gib die Fußzeile erneut mit dem korrekten Befehl aus."

`workflow.py::expected_footer_command(data)`:

```python
def expected_footer_command(data: dict) -> "str | None":
    """Erwarteter Fußzeilen-Befehl — dieselbe Quelle wie status_note() (#234)."""
    step = next_step(data)
    if not step or not step.startswith("/"):
        return step  # None oder Freitext-Schritt (z.B. "Freigabe der Spec ...")
    issue = issue_number(data.get("name", ""))
    return f"{step} #{issue}" if issue else step
```

## Expected Behavior

- **Input:** Die Stop-Hook-Payload von Claude Code (`last_assistant_message`, ggf.
  `stop_hook_active`) plus der worktree-lokale Workflow-State unter `.claude/workflows/`.
- **Output:** Exit 0 in allen Fällen außer dem einen Treffer-Fall (Fußzeilen-Befehl ≠
  erwarteter Befehl, beide vorhanden, noch keine Korrektur für diesen Turn) → dort Exit 2 mit
  einer stderr-Meldung, die den falschen und den korrekten Befehl nennt.
- **Side effects:** Schreibt bei einer Korrektur eine Zeile in
  `.claude/footer_gate_state.json` (Turn-Kennung des korrigierten Turns). Keine anderen
  Zustandsänderungen — insbesondere kein Eingriff in `workflows/<name>.json`.

## Known Limitations

- **(a) Kurzzeitig sichtbare falsche Fußzeile:** Laut Claude-Code-Hook-Dokumentation läuft
  `Stop` **nach** der Anzeige beim User. Die falsche Fußzeile ist deshalb kurz sichtbar, bevor
  Exit 2 den Turn fortsetzt und eine korrigierte Nachricht folgt. Das Gate kann die bereits
  angezeigte Nachricht nicht rückwirkend ändern (`MessageDisplay` ist laut Doku display-only).
- **(b) Fehlende Fußzeile wird nicht erzwungen:** v1 prüft nur eine **vorhandene** `❗ Du:`-
  Zeile gegen den erwarteten Befehl. Eine ganz fehlende Fußzeile feuert das Gate nicht — sonst
  würde jeder Zwischen-Turn ohne Fußzeile (freie Rückfragen, Zwischenmeldungen) blockieren.
- **(c) Copy-Modus registriert den Hook nicht:** `setup.py::generate_settings_json()`
  registriert derzeit nur 4 Hooks (`edit_gate`, `bash_gate`, `post_bash`, `phase_listener`)
  und kein `Stop`-Event. Diese Drift ist als **Issue #236** ausgelagert und **ausdrücklich
  nicht Teil dieser Änderung** — im Copy-Modus installierte Projekte bekommen das Footer-Gate
  vorerst nicht.
- **(d) Blast Radius:** Der Hook läuft bei **jedem** Turn-Ende in **jedem** Konsumenten-Projekt
  im Plugin-Modus. Deshalb ist Fail-open die tragende Anforderung dieser Spec, nicht die
  Erkennungsrate — siehe die Fail-open-Acceptance-Criteria unten.
- **`stop_hook_active` ist ein unbelegter Zusatz:** Ob dieses Feld im Stop-Payload dieser
  Claude-Code-Version tatsächlich vorkommt, war in der Recherche nicht abschließend klärbar.
  Es wird, falls vorhanden, defensiv ausgewertet, ist aber **nicht** Voraussetzung für den
  Schleifenschutz — der eigene Zähler in `footer_gate_state.json` trägt die Garantie allein.
  Die empirische Klärung erfolgt in `/40-tdd-red`.
- **Widerspruch in der Fußzeilen-Textquelle bleibt bestehen (#235, nicht in diesem Scope):**
  `scripts/sync_skills.py:103-107` und `core/commands/40-tdd-red.md:158` widersprechen sich
  weiterhin (siehe Analyse). Das Gate prüft und korrigiert das Symptom mechanisch, senkt aber
  nicht die Fehlerrate, mit der die falsche Fußzeile überhaupt erst entsteht.

## Nicht in diesem Scope

- **#235** — Widerspruch in `scripts/sync_skills.py:103-107` (mit „wörtlich von dort") und
  `core/commands/40-tdd-red.md:158` (hartkodierte Phase im Ausgabeblock).
- **#236** — Copy-Modus (`setup.py::generate_settings_json()`) registriert weder den neuen
  `Stop`-Hook noch mehrere bestehende Hooks/Events.
- **#237** — `secret_egress_guard.py` blockt `/dev/null` und das Sitzungs-Scratchpad, obwohl die
  eigene Fehlermeldung das Scratchpad als richtiges Ziel nennt.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Eine Antwort mit falscher Fußzeile (Befehl ≠ `workflow.next_step()`) wird von Claude
      innerhalb desselben Turns korrigiert, bevor der PO reagieren muss — beobachtbar am
      Exit-2-Verhalten des Hooks in `tests/test_footer_gate_234.py`, nicht an einer manuellen
      Session
- [ ] Kein bestehender Workflow-Turn ohne diesen Bug-Symptom wird durch das Gate blockiert
      (alle Fail-open-ACs grün)
- [ ] `CHANGELOG.md` und `.claude-plugin/plugin.json` sind aktualisiert
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, insbesondere
      `tests/test_workflow_*.py` und `tests/test_phase_listener_*.py`)

## Acceptance Criteria

- **AC-1:** Given ein aktiver Workflow steht in `phase6_implement` (`next_step()` liefert
  `/50-implement #234`) UND die letzte `❗ Du:`-Zeile der Antwort nennt `/40-tdd-red` / When
  `footer_gate.py` mit dieser Payload läuft / Then liefert der Hook Exit 2, und stderr enthält
  sowohl `/40-tdd-red` als auch `/50-implement`.
  - Test: `tests/test_footer_gate_234.py::test_mismatch_blocks_with_both_commands_in_stderr`
- **AC-2:** Given derselbe Workflow-State wie AC-1 UND die letzte `❗ Du:`-Zeile nennt bereits
  korrekt `/50-implement #234` / When `footer_gate.py` läuft / Then liefert der Hook Exit 0.
  - Test: `tests/test_footer_gate_234.py::test_matching_footer_exits_zero`
- **AC-3:** Given kein aktiver Workflow ist auflösbar (`resolve_active_workflow()` liefert
  `("", "none")`) UND die Antwort enthält eine `❗ Du:`-Zeile mit einem Slash-Befehl / When
  `footer_gate.py` läuft / Then liefert der Hook Exit 0.
  - Test: `tests/test_footer_gate_234.py::test_no_active_workflow_exits_zero`
- **AC-4:** Given der aktive Workflow steht in `phase8_complete` / When `footer_gate.py` läuft
  / Then liefert der Hook Exit 0 (`expected_footer_command()` liefert `None`), unabhängig
  davon, welcher Befehl in der `❗ Du:`-Zeile steht.
  - Test: `tests/test_footer_gate_234.py::test_phase8_complete_exits_zero`
- **AC-5:** Given die Workflow-JSON-Datei ist syntaktisch kaputt (ungültiges JSON) oder nicht
  lesbar / When `footer_gate.py` läuft / Then liefert der Hook Exit 0 (kein unbehandelter
  Absturz, keine Exception propagiert nach außen).
  - Test: `tests/test_footer_gate_234.py::test_corrupt_workflow_state_exits_zero`
- **AC-6:** Given `framework_disabled()` liefert `True` (z. B. `OPENSPEC_FRAMEWORK=off`) UND
  ein aktiver Workflow mit abweichender Fußzeile existiert / When `footer_gate.py` läuft /
  Then liefert der Hook Exit 0, ohne den Workflow-State überhaupt zu lesen.
  - Test: `tests/test_footer_gate_234.py::test_framework_disabled_exits_zero`
- **AC-7:** Given `last_assistant_message` enthält keine Zeile, die mit `❗ Du:` oder
  `‼️ Du:` beginnt (z. B. eine `ℹ️ Nichts zu tun:`-Zeile oder gar keine Marker-Zeile) UND ein
  aktiver Workflow mit einem anderen Pflicht-Schritt existiert / When `footer_gate.py` läuft /
  Then liefert der Hook Exit 0.
  - Test: `tests/test_footer_gate_234.py::test_no_du_line_exits_zero`
- **AC-8:** Given der aktive Workflow steht in `phase3_spec` mit gesetztem `spec_file`
  (`next_step()` liefert den Freitext-Schritt „Freigabe der Spec (Stichwort: approved)", kein
  Slash-Präfix) UND die `❗ Du:`-Zeile nennt einen beliebigen Slash-Befehl / When
  `footer_gate.py` läuft / Then liefert der Hook Exit 0.
  - Test: `tests/test_footer_gate_234.py::test_non_slash_next_step_exits_zero`
- **AC-9:** Given derselbe Turn wie in AC-1 (bereits einmal mit Exit 2 korrigiert, Turn-Kennung
  in `footer_gate_state.json` vermerkt) UND `footer_gate.py` läuft ein zweites Mal für
  denselben Turn mit erneut abweichender Fußzeile / When der Hook läuft / Then liefert er
  Exit 0 (keine zweite Korrektur desselben Turns).
  - Test: `tests/test_footer_gate_234.py::test_second_run_same_turn_exits_zero`
- **AC-10:** Given `workflow.expected_footer_command(data)` wird direkt mit einem State
  aufgerufen, der `current_phase="phase6_implement"` und `name="fix-234-footer-command"`
  gesetzt hat / When die Funktion läuft / Then liefert sie exakt `"/50-implement #234"` —
  dieselbe Ausgabe, die `status_note()` für denselben State in der Fußzeilen-Anweisung
  referenziert.
  - Test: `tests/test_footer_gate_234.py::test_expected_footer_command_matches_next_step_plus_issue`

## Test Plan

Automatische Tests, subprocess-basiert gegen `core/hooks/footer_gate.py` (Stil identisch zu
`tests/test_phase_listener_agent_handback_141.py`: `_make_project()` legt einen Workflow unter
`.claude/workflows/<name>.json` an, `_run_hook()` ruft den Hook als Subprozess mit einer
Stop-Payload `{"last_assistant_message": ..., "stop_hook_active": ...}` auf):

- `pytest tests/test_footer_gate_234.py`
  1. `test_mismatch_blocks_with_both_commands_in_stderr` (AC-1)
  2. `test_matching_footer_exits_zero` (AC-2)
  3. `test_no_active_workflow_exits_zero` (AC-3)
  4. `test_phase8_complete_exits_zero` (AC-4)
  5. `test_corrupt_workflow_state_exits_zero` (AC-5)
  6. `test_framework_disabled_exits_zero` (AC-6)
  7. `test_no_du_line_exits_zero` (AC-7)
  8. `test_non_slash_next_step_exits_zero` (AC-8)
  9. `test_second_run_same_turn_exits_zero` (AC-9) — ruft den Hook zweimal nacheinander mit
     identischer Turn-Kennung auf, prüft Exit 2 dann Exit 0
  10. `test_expected_footer_command_matches_next_step_plus_issue` (AC-10) — in-process gegen
      `workflow.expected_footer_command()`, kein Subprozess nötig

Regressions-Referenz (nicht Teil dieser neuen Datei, muss grün bleiben):
- `pytest tests/test_workflow_resolution_consolidation.py`
- `pytest tests/test_phase_listener_dropped_approval_90.py`
- Repo-weiter Lauf: `pytest tests/`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** ADR-0234
- **Rationale:** Erstmalige Nutzung des Hook-Events `Stop` in diesem Framework (bisher nur
  `SessionStart`, `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `SessionEnd`) und erstes
  Gate, das **nach** der Anzeige der Antwort beim User greift statt davor. Diese Abweichung von
  der bisherigen Architektur ist notwendig, weil jede Alternative, die vor der Anzeige
  greifen könnte (`UserPromptSubmit`, `PreToolUse`), laut Claude-Code-Doku die noch gar nicht
  generierte Antwort nicht einsehen kann — die Fußzeile existiert erst, wenn das Modell sie
  geschrieben hat.

  Verworfene Alternativen aus der Analyse:
  - **A — fünfte Textverschärfung:** Abgelehnt. Vier Vorläufer (#174/#209/#213/#221) haben
    exakt diesen Weg genommen und die Fehlerklasse jedes Mal in neuer Variante zurückgebracht.
  - **B — Widerspruch in `sync_skills.py`/`40-tdd-red.md` entfernen:** Notwendig, aber allein
    nicht ausreichend — senkt die Trefferquote des Fehlers, prüft aber nichts. Als **Issue
    #235** separat ausgelagert; kein Blocker für dieses Gate.
  - **C — zustandsändernde CLI-Kommandos geben `next_step()` direkt mit aus:** Verbessert die
    Zulieferung (das Modell läse die Konsequenz Sekunden vor dem Schreiben der Fußzeile), bleibt
    aber ungeprüfter Modell-Output — kein mechanisches Gate. Nicht gewählt, weil die Analyse
    (CLAUDE.md „Regeln vor Modell") einen deterministisch prüfenden Weg verlangt, sobald einer
    ohne unverhältnismäßigen Aufwand verfügbar ist.
  - **E — nichts tun:** Abgelehnt. Fünftes Auftreten derselben Fehlerklasse, kein Einzelfall.

  Konsequenz dieser Entscheidung: Die falsche Fußzeile bleibt laut Doku kurz sichtbar, bevor
  die Korrektur folgt (Known Limitation (a)) — echte *Prävention* vor der Anzeige ist mit den
  aktuell verfügbaren Hook-Events nicht erreichbar. Exit 2 auf `Stop` erzwingt laut Doku „continues
  the conversation", nicht das nachträgliche Ändern der bereits angezeigten Nachricht
  (`MessageDisplay` ist display-only). Versionsbump ist MINOR (neue Fähigkeit: erstmals ein
  `Stop`-Hook und ein neuer Mechanismus, kein reiner Bugfix ohne neues Verhalten) — konsistent
  mit der Repo-Konvention aus dem CHANGELOG (MINOR für neue Fähigkeiten wie 3.21.0
  CI-Spec-Gate, 3.22.0 Auto-Chaining).

## Changelog

- 2026-09-25: Initial spec created
