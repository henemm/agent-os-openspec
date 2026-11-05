---
entity_id: feat-525-auto-ship
type: feature
created: 2026-11-05
updated: 2026-11-05
status: draft
version: "1.0"
workflow: feat-525-auto-ship
tags: [autonomy, auto-mode, validate, pr, merge, po-no-git]
---

# Auto-Modus: Claude erstellt PR, wartet auf CI und mergt (Issue #525)

## Approval

- [ ] Approved

## Purpose

Der PO hat mit Git nichts zu tun und will nie einen PR erstellen oder mergen. Trotzdem endete die Abschlussmeldung von #521 mit „❗ Du: PR … erstellen lassen oder selbst mergen“: Seit 4.5.4 bleiben Merge und PR im Auto-Modus beim PO, sofern nicht die Projekt-`CLAUDE.md` eine Git-Policy enthält. Künftig gilt im Auto-Modus (`autonomy.mode: auto`) für alle Projekte: Nach `phase8_complete` legt Claude den PR an, wartet auf grüne CI und mergt selbst. Bei roter CI repariert Claude oder meldet das Problem in Alltagssprache, nie mit einem Git-Auftrag an den PO. Ein Config-Schalter `autonomy.ship: false` schaltet das ab; der Default ist an. Deploy bleibt getrennt (`deploy.autonomous`).

## Source

- **File:** `core/hooks/workflow.py`, `core/commands/60-validate.md`
- **Identifier:** `auto_ship_enabled`, `cmd_auto_ship` (neu); Abschnitt „Auto-Modus prüfen“ und Abschlussvorlage in `60-validate.md` (geändert)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.autonomy_mode` (#469, #481) | function | Auto-Modus-Bestimmung; fail-closed auf manual |
| `workflow.trusted_config` (#470) | function | einzige Config-Quelle, nie `settings.local.json` |
| `workflow.cmd_autonomy`, `cmd_autoclear` | function | Vorbild für Auskunfts-Befehle (eine Zeile, Exit 0, kein Workflow nötig) |
| `core/commands/60-validate.md` (4.5.4) | command | enthält die bisherige Git-Policy-Regel, die im `off`-Fall unverändert bleibt |
| `scripts/sync_skills.py` | script | erzeugt `skills/60-validate/SKILL.md` aus dem Command; Drift blockt Release |
| `deploy.autonomous` | config | bleibt eigene, getrennte Deploy-Entscheidung |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `auto_ship_enabled()`, `cmd_auto_ship`, Eintrag `"auto-ship"` in der Kommando-Tabelle |
| core/commands/60-validate.md | MODIFY | Auto-Modus: Schritt `auto-ship` prüfen; bei `AUTO_SHIP=on` PR → CI → Merge; Abschlussvorlage und ❗Du-Regel ohne Git-Schritt |
| skills/60-validate/SKILL.md | MODIFY | generiert per `python3 scripts/sync_skills.py` |
| tests/test_auto_ship_525.py | CREATE | Tests zu allen AC |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased], nennt #525 und den Schalter `autonomy.ship: false` |

### Estimated Changes

- Files: 1 neu, 4 geändert (davon 1 generiert)
- LoC: +30 Code, +45/−10 Command-Text, +170 Test
- Risk Level: HIGH (automatischer Merge auf den Default-Branch in jedem Auto-Modus-Projekt)

## Implementation Details

**`auto_ship_enabled() -> bool`** in `workflow.py`: True nur, wenn `autonomy_mode() == "auto"` UND in `trusted_config()` nicht `autonomy.ship` ausdrücklich `False` ist. Nur ein echtes `False` schaltet ab; fehlender Schlüssel, andere Werte (auch String `"false"`) und eine kaputte Config lassen den Schalter an, solange der Modus auto ist. Jede Ausnahme bei der Modus-Bestimmung ergibt über `autonomy_mode` den Wert manual und damit aus. Gelesen wird nie `settings.local.json`, sondern nur `trusted_config()`; der Config-Schutz bleibt wirksam. Wirft nie.

**`cmd_auto_ship`** nach Vorbild `cmd_autonomy`: genau eine Zeile `AUTO_SHIP=on|off`, Exit immer 0, ohne aktiven Workflow. Eintrag `"auto-ship": cmd_auto_ship` in der Kommando-Tabelle.

**`core/commands/60-validate.md`**, Abschnitt Auto-Modus:

1. Neuer Schritt: `python3 .claude/hooks/workflow.py auto-ship` ausführen; nur die ausdrücklich gelesene Zeile `AUTO_SHIP=on` schaltet um, jede andere Ausgabe gilt als `off`.
2. Bei `AUTO_SHIP=on`: Nach Commit und Push des Feature-Branchs (Punkte 1 und 2 unverändert) im selben Turn den PR auf den Default-Branch anlegen (PR-Vorlage des Repos beachten), die CI abwarten (PR-Aktivität abonnieren statt Polling, wo verfügbar) und bei grüner CI und konfliktfreiem PR mergen, mit der im Repo üblichen Methode (an der Historie des Default-Branchs ablesbar, im Zweifel Squash); danach den Feature-Branch auf den neuen Stand bringen. Merge-Konflikt: Default-Branch in den Feature-Branch mergen, Konflikt lösen, Tests erneut laufen lassen, wieder warten. Rote CI: Ursache suchen und beheben (ein Code-Fix zählt als BROKEN-Pfad wie bisher) oder, wenn nicht aus diesem Änderungssatz behebbar, das Problem in Alltagssprache melden. Hat das Repo keine CI-Checks: Merge auf Basis der grünen lokalen Testsuite aus Phase 7. Schutzregeln (Pflicht-Reviews, Branch-Protection) werden nie umgangen, nie `--force`, rote CI nie überbrückt; verhindert eine Schutzregel den Merge, lautet die Meldung „wartet auf Prüfung durch einen Techniker“, ohne Git-Auftrag an den PO.
3. Bei `AUTO_SHIP=off` (Schalter aus oder manual): der 4.5.4-Text bleibt unverändert (Git-Policy der Projekt-`CLAUDE.md` sticht, sonst bleiben Merge und PR offen).
4. Abschlussvorlage bei `AUTO_SHIP=on`: Ergebnis (PR-Link, gemergt ja/nein, Merge-Commit) statt „Offen beim PO: Merge / PR“. Die Zeile „Offen beim PO“ nennt höchstens fachliche Abnahme oder Deploy. Die ❗Du-Zeile nennt nie einen Git-Schritt (PR, Merge, Push, Branch, Commit); ist für den PO nichts zu tun, gilt die vorgeschriebene ℹ️-Variante bzw. der nächste fachliche Schritt. Der Satz „Die ❗Du-Zeile nennt den nächsten PO-Schritt (Merge/PR prüfen)“ entfällt für den `on`-Fall.
5. Deploy bleibt unverändert beim PO bzw. bei `deploy.autonomous`; der Auto-Modus deployt nie.
6. Der Schalter `autonomy.ship: false` wird im Command-Text dokumentiert.

**`skills/60-validate/SKILL.md`** wird nicht von Hand editiert, sondern per `python3 scripts/sync_skills.py` neu erzeugt.

## Expected Behavior

- **Input:** Abschluss einer Validierung (`phase8_complete`) in einem Projekt mit `autonomy.mode: auto`
- **Output:** `workflow.py auto-ship` liefert `AUTO_SHIP=on`; Claude legt den PR an, wartet auf grüne CI, mergt und meldet das Ergebnis; keine ❗Du-Zeile und keine Abschlussmeldung nennt dem PO einen Git-Schritt
- **Side effects:** PR und Merge auf dem Remote; kein neuer Workflow-State, keine Config-Datei-Änderung

## Known Limitations

- `config.yaml` bekommt keinen Kommentar zu `autonomy.ship` (Config-Schutz, Änderung nur per „override“); der Schalter ist im Command-Text und im CHANGELOG dokumentiert.
- Die Merge-Methode wird heuristisch aus der Historie des Default-Branchs abgelesen, im Zweifel Squash.
- Das Warten auf die CI kann lang dauern; der Turn bleibt bis dahin offen, bzw. Claude wird über die PR-Aktivität geweckt.
- Ohne Zugang zu Remote oder GitHub kann Claude nicht mergen; das Problem wird in Alltagssprache gemeldet, ohne Git-Auftrag an den PO.
- Die Regel steht im Command-Text und wird von Claude befolgt, nicht von einem Hook erzwungen; ein Test belegt den Text, nicht das Verhalten im Lauf.
- Der Schalter wirkt nur im Auto-Modus; in manual bleibt alles wie bisher.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Im Auto-Modus nennt weder die ❗Du-Zeile noch die Abschlussmeldung einen Git-Schritt (PR, Merge, Push, Branch) für den PO
- [ ] `/60-validate` beschreibt im Auto-Modus: PR erstellen, CI abwarten, mergen; bei roter CI reparieren oder in Alltagssprache melden
- [ ] Der Schalter `autonomy.ship: false` schaltet ab, der Default ist im Auto-Modus an, Deploy bleibt getrennt
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf `pytest tests/` grün, Skill-Drift-Test grün)

## Acceptance Criteria

Testaufbau: `workflow.py auto-ship` als Subprozess in einem `tmp_path`-Projekt mit `config.yaml`, `OPENSPEC_AUTONOMY` gezielt gesetzt bzw. entfernt; Command-Text-Tests lesen `core/commands/60-validate.md` und `skills/60-validate/SKILL.md` als Datei. Kein Mock der Entscheidungsregel.

- **AC-1:** Given ein Projekt mit `autonomy.mode: auto` ohne `ship`-Schlüssel / When `workflow.py auto-ship` läuft / Then lautet die Ausgabe genau eine Zeile `AUTO_SHIP=on` bei Exit 0
  - Test: tests/test_auto_ship_525.py::TestAutoShipCli::test_auto_mode_without_ship_key_is_on

- **AC-2:** Given ein Projekt mit `autonomy.mode: auto` und `autonomy.ship: false` / When `workflow.py auto-ship` läuft / Then lautet die Ausgabe `AUTO_SHIP=off`
  - Test: tests/test_auto_ship_525.py::TestAutoShipCli::test_ship_false_is_off

- **AC-3:** Given ein Projekt mit `autonomy.mode: manual` bzw. ohne Config-Eintrag und ohne `OPENSPEC_AUTONOMY` / When `workflow.py auto-ship` läuft / Then lautet die Ausgabe `AUTO_SHIP=off`
  - Test: tests/test_auto_ship_525.py::TestAutoShipCli::test_manual_and_missing_config_are_off

- **AC-4:** Given ein Projekt ohne `autonomy`-Eintrag und die Umgebungsvariable `OPENSPEC_AUTONOMY=auto` / When `workflow.py auto-ship` läuft / Then lautet die Ausgabe `AUTO_SHIP=on`
  - Test: tests/test_auto_ship_525.py::TestAutoShipCli::test_env_auto_without_project_entry_is_on

- **AC-5:** Given `autonomy.ship: false` steht nur in `settings.local.json` und `autonomy.mode: auto` in der Projekt-Config / When `workflow.py auto-ship` läuft / Then bleibt die Ausgabe `AUTO_SHIP=on`, die lokale Datei schaltet nicht ab
  - Test: tests/test_auto_ship_525.py::TestAutoShipCli::test_ship_false_only_in_settings_local_does_not_disable

- **AC-6:** Given beliebige Zustände (kein Workflow, kaputte Config, `ship` als String `"false"`) / When `workflow.py auto-ship` läuft / Then endet der Aufruf mit Exit 0 und genau einer Ausgabezeile `AUTO_SHIP=on` oder `AUTO_SHIP=off`; nur ein echtes `false` schaltet ab
  - Test: tests/test_auto_ship_525.py::TestAutoShipCli::test_always_exit_zero_single_line

- **AC-7:** Given der Command-Text `core/commands/60-validate.md` / When gelesen / Then enthält er den Aufruf `workflow.py auto-ship`, die Zeile `AUTO_SHIP=on` und die Dokumentation des Schalters `autonomy.ship: false`
  - Test: tests/test_auto_ship_525.py::TestCommandText::test_calls_auto_ship_and_documents_switch

- **AC-8:** Given der Command-Text / When gelesen / Then beschreibt er bei `AUTO_SHIP=on` die Kette PR anlegen, CI abwarten, mergen, und bei roter CI beheben oder in Alltagssprache melden
  - Test: tests/test_auto_ship_525.py::TestCommandText::test_describes_pr_ci_merge_chain_and_red_ci

- **AC-9:** Given der Command-Text / When gelesen / Then verbietet er, Schutzregeln zu umgehen und `--force` zu nutzen, und regelt ein Repo ohne CI-Checks über die lokale Testsuite
  - Test: tests/test_auto_ship_525.py::TestCommandText::test_protection_rules_no_force_and_no_ci_fallback

- **AC-10:** Given der Command-Text / When gelesen / Then steht dort, dass die ❗Du-Zeile bei `AUTO_SHIP=on` nie einen Git-Schritt nennt, und „Offen beim PO: Merge / PR“ ist nicht mehr die Vorgabe für den `on`-Fall
  - Test: tests/test_auto_ship_525.py::TestCommandText::test_du_line_never_names_git_step_when_on

- **AC-11:** Given der Command-Text / When gelesen / Then bleibt für `AUTO_SHIP=off` der 4.5.4-Text zur Git-Policy der Projekt-`CLAUDE.md` erhalten
  - Test: tests/test_auto_ship_525.py::TestCommandText::test_off_case_keeps_git_policy_text

- **AC-12:** Given der Command-Text / When gelesen / Then sagt er weiter, dass der Auto-Modus nie deployt und `deploy.autonomous` eine eigene, getrennte Entscheidung bleibt
  - Test: tests/test_auto_ship_525.py::TestCommandText::test_deploy_stays_separate

- **AC-13:** Given `skills/60-validate/SKILL.md` und `core/commands/60-validate.md` / When `scripts/sync_skills.py --check` läuft / Then endet es mit Exit 0, der Skill ist synchron
  - Test: tests/test_auto_ship_525.py::test_skills_in_sync

- **AC-14:** Given `CHANGELOG.md` / When gelesen / Then steht ab `## [Unreleased]` (unter `[Unreleased]` oder in einem beliebigen Versionsabschnitt, release-fest wie #521) ein Eintrag, der `#525` nennt
  - Test: tests/test_auto_ship_525.py::test_changelog_mentions_525

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_auto_ship_525.py`
- `pytest tests/test_autonomy_schalter_469.py tests/test_autonomy_kette_472.py tests/test_kette_auto_clear_489.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/workflow.py`
- `python3 scripts/sync_skills.py --check`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung folgt dem bestehenden Muster aus #469/#489: ein Auskunfts-Befehl (`AUTO_SHIP=on|off`, fail-closed über `autonomy_mode` und `trusted_config`) und Command-Text als Steuerung für Claude. Kein neuer State, kein neues Gate, per Config-Schalter abschaltbar und durch Rückbau des Textes reversibel. Verworfen: (a) nur per Projekt-`CLAUDE.md`-Policy wie in 4.5.4 — vom PO verworfen, weil jedes Projekt die Zeile bräuchte und der PO sonst weiter Git-Aufträge bekommt; (b) neues Gate oder Hook, das mergt — Merge ist eine Handlung mit Netzwerk und Rechten, kein Prüfschritt, und gehört in den Command-Text, den Claude ausführt; (c) Default aus — vom PO entschieden: Default an im Auto-Modus.

## Changelog

- 2026-11-05: Initial spec created
