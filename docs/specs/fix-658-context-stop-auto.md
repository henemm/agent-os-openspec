---
entity_id: fix-658-context-stop-auto
type: bugfix
created: 2026-11-25
updated: 2026-11-25
status: draft
version: "1.0"
workflow: fix-658-context-stop-auto
tags: [kontext, token, hooks, workflow, herdr, auto-modus]
---

# Kontext-Halt nur dort, wo `/clear` automatisch kommt (Issue #658)

## Approval

- [ ] Approved

## Purpose

Im Auto-Modus (`OPENSPEC_AUTONOMY=auto`) hielt `CONTEXT_CUT=on` die Phasenkette an und verlangte vom PO `/clear` plus Folgebefehl, auch in Sitzungen ohne Herdr (z. B. Cloud), in denen das niemand automatisch ausführt. Diese Änderung trennt Messfakt und Entscheidung: `workflow.py context` liefert zusätzlich `CONTEXT_STOP=on|off`, und die Phasen-Befehle halten nur noch bei `CONTEXT_STOP=on` an. Der Halt greift damit nur im Modus `manual` oder wenn Herdr das Auto-`/clear` ausführt.

## Source

- **File:** `core/hooks/workflow.py`, `core/hooks/hook_utils.py`, `core/hooks/herdr_bridge.py`, `core/hooks/post_bash.py`, `core/commands/10-context.md` bis `50-implement.md`
- **Identifier:** `workflow.cmd_context`, `workflow.cmd_autoclear`, `hook_utils.context_stop_applies` (neu), `hook_utils.context_cut_note`, `herdr_bridge.auto_clear_active` (neu), `post_bash._track_context`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.autonomy_mode` | function | Quelle für `auto`/`manual` (lazy Import im Helfer) |
| `herdr_bridge._pane`, `herdr_bridge.auto_clear_enabled` | function | Herdr-Erkennung; neu gebündelt in `auto_clear_active()` |
| `herdr_bridge._context_cut_active` (#598) | function | spiegelt die CUT-Bedingung für den Stop-Hook; bleibt unverändert |
| `workflow.auftrag_autark_open` (#551) | function | Autark setzt CUT schon auf off, bleibt vorrangig |
| `hook_utils.effective_context_threshold` (#557) | function | wirksame Schwelle; `CONTEXT_THRESHOLD` bleibt erhalten |
| `scripts/sync_skills.py` | tool | `skills/` nach Befehlstext-Änderung neu erzeugen |
| `docs/specs/feat-kontext-haushalt.md`, `fix-557-kontext-grundlast.md`, `feat-551-auftragsliste.md`, `fix-598-autoclear-kontextschnitt.md` | spec | Grundlage |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/herdr_bridge.py | MODIFY | `auto_clear_active()` = `_pane() and auto_clear_enabled()` |
| core/hooks/hook_utils.py | MODIFY | `context_stop_applies(root=None)`; `context_cut_note` mit dritter Variante (auto ohne Auto-/clear), Normal-Wortlaut verweist auf `CONTEXT_STOP=on` |
| core/hooks/workflow.py | MODIFY | `cmd_context`: letzte Zeile `CONTEXT_STOP=on\|off`, bei CUT=on/STOP=off `CONTEXT_REASON=AUTO_NO_CLEAR`; `cmd_autoclear` nutzt `auto_clear_active()` |
| core/hooks/post_bash.py | MODIFY | Hinweisvariante nach derselben Regel |
| core/commands/10-context.md, 20-analyse.md, 30-write-spec.md, 40-tdd-red.md, 50-implement.md | MODIFY | Absatz liest `CONTEXT_STOP=on` |
| skills/*, .claude/agents | REGENERATE | `python3 scripts/sync_skills.py` |
| tests/test_context_stop_658.py | CREATE | Regressionstests zu allen AC |
| tests/test_kontext_haushalt.py, test_kontext_grundlast_557.py, test_auftrag_551.py | MODIFY | exakte Zeilenlisten um `CONTEXT_STOP`; Absatz-Test auf `CONTEXT_STOP=on`; Test-Env `OPENSPEC_AUTONOMY`, `HERDR_ENV`, `HERDR_PANE_ID` explizit |
| CLAUDE.md, README.md, setup.py (Hinweistext) | MODIFY | Doku Kontext-Haushalt Regel 1 |
| CHANGELOG.md, .claude-plugin/plugin.json, CLAUDE.md (Version) | MODIFY | Version 4.22.1 |

Nicht geändert: `config.yaml` (Änderungen an der wirksamen Gate-Config werden vermieden), `herdr_bridge._context_cut_active`, die CUT-Messung selbst.

### Estimated Changes

- Files: 1 neu, 8 Code/Test geändert, 5 Befehlstexte, Generat, Doku
- LoC: ca. +200/-30 (ohne Generat)
- Risk Level: MEDIUM (Hook-Code in allen Konsumenten; Verhalten ändert sich nur im Fall auto ohne Herdr-Auto-Clear)

## Implementation Details

1. **`herdr_bridge.auto_clear_active()`.** Gibt `_pane() and auto_clear_enabled()` zurück (fail-open `False`). `cmd_autoclear` ruft den Helfer statt der Einzelprüfungen, Ausgabe unverändert.
2. **`hook_utils.context_stop_applies(root=None) -> bool`.** `True`, wenn `autonomy_mode() != "auto"` oder `herdr_bridge.auto_clear_active()`. Imports lazy. Wirft einer der Aufrufe, liefert der Helfer `True` (STOP folgt CUT, bisheriges Verhalten).
3. **`cmd_context`.** Ausgabe wie bisher (`CONTEXT_TOKENS`, `CONTEXT_CUT`, `CONTEXT_THRESHOLD` bzw. `CONTEXT_REASON=AUTARK`). Bei CUT=on und STOP=off folgt nach `CONTEXT_THRESHOLD` die Zeile `CONTEXT_REASON=AUTO_NO_CLEAR`. Zuletzt immer `CONTEXT_STOP=on|off`: `on` genau dann, wenn CUT=on und `context_stop_applies()`. Autark: CUT ist off, also STOP=off. Exit immer 0.
4. **`context_cut_note`.** Dritte Variante für auto ohne Auto-/clear: Kette nicht anhalten, weiterarbeiten, Nachschlagen an Teilagenten abgeben, Claude Code komprimiert automatisch, Stand laufend auf der Platte sichern. Der Normal-Wortlaut sagt: Im Auto-Modus den nächsten Skill nicht selbst aufrufen (`workflow.py context` -> `CONTEXT_STOP=on`). `post_bash.py` wählt die Variante nach `context_stop_applies()`; Autark-Wortlaut bleibt.
5. **Befehlstexte 10 bis 50.** Der Absatz „Vor dem Selbstaufruf zusätzlich `workflow.py context`" liest `CONTEXT_STOP=on`: Folge-Skill nicht selbst aufrufen, Turn mit Checkpoint und ❗Du-Zeile `/<folge> #<N>` beenden, Hinweis „Default 100.000 Token" bleibt. Bei `CONTEXT_STOP=off` (auch `CONTEXT_REASON=AUTO_NO_CLEAR`) die Kette selbst fortsetzen.
6. **Doku und Version.** CLAUDE.md (Kontext-Haushalt Regel 1), README.md, Hinweistext in `setup.py`, CHANGELOG, Version 4.22.1; danach `python3 scripts/sync_skills.py`.

## Expected Behavior

- **Input:** `OPENSPEC_AUTONOMY`, Herdr-Umgebung (`HERDR_ENV`, `HERDR_PANE_ID`), `herdr.auto_clear`, Messdatei, offener autarker Auftrag
- **Output:** `workflow.py context` endet immer mit `CONTEXT_STOP=on|off`; `on` nur bei CUT=on und (Modus `manual` oder Herdr-Auto-Clear aktiv)
- **Side effects:** keine neue Config, kein neues Gate; reine Auskunft, Exit 0

## Known Limitations

- Ohne Herdr läuft die Kette im Auto-Modus bei großem Kontext weiter; Ausgleich sind Teilagenten und die automatische Komprimierung von Claude Code. Grundsätzlich löst das Epic #649.
- Ein alter Befehlstext, der noch `CONTEXT_CUT` liest, verhält sich wie bisher; Plugin und Befehlstexte kommen gemeinsam aus einer Version.
- Reine Auskunft: ob Claude anhält, erzwingt kein Hook (außer dem Herdr-Stop-Hook #598).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Eine Cloud-Sitzung im Auto-Modus ohne Herdr läuft über die Kontext-Schwelle hinweg weiter, ohne dass der PO `/clear` und einen Folgebefehl tippen muss
- [ ] Im Modus `manual` und unter Herdr mit Auto-Clear hält die Kette an der Schwelle weiterhin an
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, `skills/` ohne Drift, Version 4.22.1 veröffentlicht)

## Acceptance Criteria

- **AC-1:** Given Auto-Modus ohne Herdr-Pane und ohne Auto-Clear, Kontext über der Schwelle / When `workflow.py context` läuft / Then lautet die Ausgabe `CONTEXT_CUT=on`, `CONTEXT_REASON=AUTO_NO_CLEAR` und als letzte Zeile `CONTEXT_STOP=off`, Exit 0
  - Test: tests/test_context_stop_658.py::test_auto_without_herdr_stop_off_with_reason

- **AC-2:** Given Auto-Modus mit aktivem Herdr-Pane und eingeschaltetem Auto-Clear, Kontext über der Schwelle / When `workflow.py context` läuft / Then lautet die letzte Zeile `CONTEXT_STOP=on` und `CONTEXT_REASON=AUTO_NO_CLEAR` fehlt
  - Test: tests/test_context_stop_658.py::test_auto_with_herdr_auto_clear_stop_on

- **AC-3:** Given Modus `manual` (mit oder ohne Herdr), Kontext über der Schwelle / When `workflow.py context` läuft / Then lautet die letzte Zeile `CONTEXT_STOP=on`
  - Test: tests/test_context_stop_658.py::test_manual_mode_stop_on

- **AC-4:** Given Kontext unter der Schwelle in jedem Modus / When `workflow.py context` läuft / Then lauten `CONTEXT_CUT=off` und `CONTEXT_STOP=off`, ohne `CONTEXT_REASON=AUTO_NO_CLEAR`
  - Test: tests/test_context_stop_658.py::test_below_threshold_cut_and_stop_off

- **AC-5:** Given ein offener autarker Auftrag (#551) im Auto-Modus über der Schwelle / When `workflow.py context` läuft / Then bleibt es bei `CONTEXT_CUT=off` und `CONTEXT_REASON=AUTARK`, und die letzte Zeile lautet `CONTEXT_STOP=off`
  - Test: tests/test_context_stop_658.py::test_autark_stop_off

- **AC-6:** Given der Entscheidungs-Helfer wirft einen Fehler und CUT ist on / When `workflow.py context` läuft / Then folgt `CONTEXT_STOP` dem Wert von `CONTEXT_CUT` (`on`), Exit 0
  - Test: tests/test_context_stop_658.py::test_helper_error_stop_follows_cut

- **AC-7:** Given die Hinweis-Ausgabe von `post_bash.py` über der Schwelle / When Auto-Modus ohne Herdr-Auto-Clear, Modus manual oder Herdr-Auto-Clear gilt / Then sagt der Hinweis im ersten Fall „weiterarbeiten" samt Teilagenten und automatischer Komprimierung ohne Halt-Aufforderung, in den beiden anderen Fällen nennt er `CONTEXT_STOP=on` als Halt-Signal
  - Test: tests/test_context_stop_658.py::test_post_bash_note_wording_per_variant

- **AC-8:** Given die Befehlstexte 10-context bis 50-implement (und ihre erzeugten Skills) / When der Absatz zum Kontext-Schnitt gelesen wird / Then verweist er auf `CONTEXT_STOP=on` für den Halt mit ❗Du-Zeile und auf die Fortsetzung bei `CONTEXT_STOP=off`, nicht mehr auf `CONTEXT_CUT=on` als Halt-Auslöser
  - Test: tests/test_context_stop_658.py::test_phase_commands_read_context_stop

- **AC-9:** Given Herdr-Pane aktiv, Auto-Clear an bzw. aus, autark bzw. nicht / When `workflow.py autoclear` läuft / Then bleibt die Ausgabe (`AUTO_CLEAR=on|off` samt Grund) identisch zum Stand vor der Änderung
  - Test: tests/test_context_stop_658.py::test_autoclear_output_unchanged

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden, ohne Netzwerk, Messdatei und Config per `tmp_path`; Test-Env setzt `OPENSPEC_AUTONOMY` sowie `HERDR_ENV`/`HERDR_PANE_ID` explizit, weil die Cloud-Umgebung `OPENSPEC_AUTONOMY=auto` vorgibt):

- `pytest tests/test_context_stop_658.py` (RED zuerst, dann GREEN)
- Bestandstests mit angepassten Zeilenlisten: `pytest tests/test_kontext_haushalt.py tests/test_kontext_grundlast_557.py tests/test_auftrag_551.py tests/test_autoclear_kontextschnitt_598.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/hook_utils.py core/hooks/post_bash.py core/hooks/workflow.py core/hooks/herdr_bridge.py`
- `python3 scripts/sync_skills.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** `CONTEXT_CUT` bleibt reiner Messfakt (der Herdr-Stop-Hook #598 spiegelt dieselbe Bedingung); die Entscheidung „Kette anhalten" bekommt eine eigene Zeile an einer Stelle (`workflow.py context`), die Befehlstexte lesen nur sie. Additiv, fail-open (Fehler im Helfer ergibt das bisherige Verhalten), ohne Gate-Wirkung, reversibel durch Rückkehr der Befehlstexte zu `CONTEXT_CUT`.
- **Alternative 1, `CONTEXT_CUT` umdeuten:** verworfen. Das vermischt Messung und Entscheidung, bricht die #598-Spiegelbedingung des Stop-Hooks und nimmt dem Hinweis die Unterscheidung zwischen „Kontext groß" und „Halt nötig".
- **Alternative 2, Absatz streichen und nur `AUTO_CLEAR` lesen:** verworfen. Sie verliert die vom Issue verlangte Ein-Zeilen-Regel, lässt den Modus `manual` ohne Halt-Signal und gibt dem post_bash-Hinweis keine Entscheidungsstelle.

## Changelog

- 2026-11-25: Initial spec created
