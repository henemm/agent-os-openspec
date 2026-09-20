# Fast Track: Offene Pflicht-Schritte dürfen nicht optional klingen (3.25.0)

## Problem

Live beobachtet (gregor_zwanzig, #1761, 2026-09-20): Der Workflow stand in Phase 7 von 8, die
Abschlussnachricht las sich wie „Arbeit erledigt“ und nannte den offenen Pflicht-Schritt als
Option („bei Bedarf `/60-validate #1761`“). Die Phase-Anleitung selbst ist eindeutig (nummerierte
Pflicht-Schritte) — der Satz entstand in einer frei formulierten Nachricht **nach** dem Ende der
Phase, wo keine Anleitung mehr greift. Der PO kann einen liegengebliebenen Workflow so nicht
erkennen.

Zweiter, unabhängiger Fund: Befehle behandeln einen Aufrufparameter (`/60-validate #1761`)
nirgends. Claude Code hängt getippte Argumente zwar immer als `ARGUMENTS: …` an (belegt:
code.claude.com/docs/en/skills.md), aber ohne Anweisung improvisiert Claude den Wiedereinstieg.

**Korrektur beim Bauen:** Von den ursprünglich genannten neun Befehlen hatte `60-validate` den
Abschnitt bereits (Kopfabschnitt „Wiedereinstieg via Issue-Nummer"). Tatsächlich betroffen sind
acht: 10-context, 70-deploy, 80-workflow, 81-add-artifact, 82-test, 83-user-story, 90-retro,
99-reset.

## Scope

- `core/hooks/phase_listener.py`: Statusvermerk an Claude bei aktivem Workflow
- `scripts/sync_skills.py` bzw. `core/commands/*.md`: Sprachregel für Abschlussmeldungen
- Die neun Befehle ohne Parameter-Behandlung: Wiedereinstiegs-Schritt analog `50-implement.md`
- Nicht enthalten: Parameterweitergabe der Kurzbefehle (nicht defekt), Kopiermodus (#150)

## Definition of Done

Solange ein Workflow nicht in Phase 8 steht, nennt jede Abschlussmeldung den nächsten Schritt als
Pflicht samt Phasenstand, und jeder Befehl kommt mit `#<Nummer>` als Wiedereinstieg zurecht.

## Acceptance Criteria

- **AC-1:** Given ein aktiver Workflow vor Phase 8, When der User eine Nachricht schickt, Then erhält Claude vom Hook Workflow-Name, Phase (x von 8) und den korrekten nächsten Pflicht-Schritt — in `phase5_tdd_red` also `/50-implement`, sobald RED markiert ist, gleich ob per `mark-red` oder `mark-ui-red`.
- **AC-2:** Given ein aktiver Workflow in Phase 8 oder gar kein Workflow, When der User eine Nachricht schickt, Then wird kein Statusvermerk angehängt.
- **AC-3:** Given ein Workflow vor Phase 8, When Claude einen Arbeitsstand meldet, Then nennt die Meldung eine Statuszeile mit Phasenstand und nächstem Schritt und vermeidet „fertig“, „abgeschlossen“, „erledigt“ sowie „bei Bedarf“ oder „optional“ für diesen Schritt.
- **AC-4:** Given einer der neun Befehle ohne Parameter-Behandlung, When er als `/<befehl> #<N>` aufgerufen wird, Then löst er den Workflow über `workflow.py switch` von der Platte auf und bestätigt den Stand, statt zu raten.
- **AC-5:** Given der Statusvermerk wird erzeugt, When der Workflow-State fehlt oder defekt ist, Then bleibt der Hook still und blockiert die Eingabe nicht.
- **AC-6:** Given ein Feature-Workflow in `phase5_tdd_red`, dessen RED-Nachweis ausschliesslich per `mark-ui-red` erbracht wurde, When ein Phasenwechsel nach `phase6_implement` oder weiter angestossen wird, Then laesst `_validate_transition` ihn durch — ohne jeden RED-Nachweis bleibt der Wechsel weiterhin mit der RED-Meldung blockiert und die Phase unveraendert.

## Entscheidungen beim Bauen

- **Ausgabekanal des Vermerks:** stdout, Exit 0. Bei `UserPromptSubmit` landet stdout im Kontext;
  stderr sieht Claude nicht — die bestehenden Hook-Meldungen (Warnungen) bleiben deshalb auf
  stderr, der Vermerk ist der einzige stdout-Text. Kein JSON, damit ein versehentliches `print`
  nichts zerstört.
- **Auch bei injizierten Turns:** Der Vermerk wird vor dem frühen Ausstieg für
  Notification-Turns (Issue #46) ausgegeben — der Fundfall war ein Loop-Aufwacher. Die
  Keyword-Erkennung bleibt dort unverändert abgeschaltet.
- **Phasen-Nummerierung:** eigene Tabelle `PHASE_NUMBERS` statt `PHASES.index()`. Die Liste
  enthält `phase0_idle` und `phase6b_adversary`; der Index hätte `phase7_validate` als
  „Phase 8 von 8" ausgewiesen — also genau den Fundfall als fertig dargestellt.
- **Zwei phasenabhängige Sonderfälle:** `phase3_spec` nennt das Freigabewort statt eines Befehls,
  sobald eine Spec-Datei im State steht; `phase5_tdd_red` nennt `/50-implement`, sobald RED
  markiert ist. Dafür zählen **beide** Marker gleichwertig — `mark-red` setzt `red_test_done`,
  `mark-ui-red` setzt `ui_test_red_done` —; sonst bliebe ein reiner UI-Workflow fälschlich bei
  `/40-tdd-red` stehen.
- **Korrektur:** Die ursprüngliche Begründung, beide Marker zählten „wie an allen anderen
  RED-Abfragen in `workflow.py` auch" gleich, stimmte nicht. Bis 3.25.0 wich genau eine Stelle ab:
  das **Phasen-Gate** `_validate_transition` (`core/hooks/workflow.py`, RED-Check vor
  `phase6_implement`) fragte nur `red_test_done` ab. Die übrigen fünf Abfragen ORten beide Marker
  bereits: `edit_gate.py:486`, `tdd_enforcement.py:191` sowie in `workflow.py` `cmd_write_log`,
  `_retro_hints` und die Qualitätssignale in `cmd_retro`. (Das in 3.25.0 neu hinzugekommene
  `next_step()` ORt ebenfalls beide — siehe Punkt davor.)
- **Bestandsfehler mitbehoben (F004, Adversary-Runde 2):** Weil `cmd_mark_ui_red` nur
  `ui_test_red_done` setzt und kein Test-Artefakt anlegt, kam ein Workflow, der diesen
  dokumentierten Kurzweg nutzte, nie aus `phase5_tdd_red` heraus — der Statusvermerk hätte korrekt
  auf `/50-implement` gezeigt, das Gate hätte den Wechsel aber verweigert. Keine 3.25.0-Regression,
  sondern ein älterer Fehler; auf ausdrückliche Entscheidung des Users in diesem Change
  mitbehoben (ein Einzeiler, siehe AC-6).
- **Der Stop-Lock-Turn bleibt still:** Sagt der User „stop", steigt `phase_listener.py` beim
  Setzen des Locks aus, bevor der Vermerk erzeugt wird — ein Not-Aus soll nicht mit einer
  Aufforderung zum nächsten Schritt beantwortet werden. Das gilt nur für den auslösenden Turn;
  jede Folgenachricht bei weiterhin aktivem Lock bekommt den Vermerk ganz normal.
- **Sprachregel zentral** im Marker-Block von `scripts/sync_skills.py` (Statuszeile über der
  Marker-Zeile), nicht in 16 Dateien. `30-write-spec` bleibt wie bisher ausgenommen. Die
  Statuszeile trägt dieselbe Formulierung wie der Hook („Nächster Pflicht-Schritt:"), damit
  „wörtlich übernehmen" auch wörtlich möglich ist.
- **`/clear`-Regel bewusst eingegrenzt:** Sie gilt für frei formulierte Arbeitsstandsmeldungen —
  dort entstand der Fundfall. Die wörtlich vorgegebenen Übergabe-Blöcke (`Ausgabe A` in den fünf
  Checkpoint-Befehlen) nennen `/clear` absichtlich vor dem Folgebefehl und bleiben unangetastet;
  eine pauschale Regel hätte sich mit ihnen widersprochen.
- **`/90-retro` weicht bewusst ab:** Es analysiert einen archivierten Workflow. `switch` gilt nur
  für laufende Workflows — der Abschnitt sucht deshalb in `.claude/workflows/_archive/` und
  arbeitet mit `retro <name>` weiter; läuft der Workflow noch, wird das zuerst gemeldet.
- **`/83-user-story`:** Das Argument ist normalerweise ein Thema. Nur ein rein numerisches
  Argument wird als Issue behandelt.
- **`/00-intake`, `/00-bug`, `/01-feature` bewusst ohne:** Dort existiert noch kein Workflow-State,
  den eine Nummer auflösen könnte.

## Test Plan

- Neue Tests für den Statusvermerk in `tests/` (AC-1, AC-2, AC-5), inklusive Fehlerrobustheit
- `tests/test_skills_sync.py`: Wiedereinstiegs-Abschnitt in allen betroffenen Skills vorhanden (AC-4)
- `tests/test_red_marker_phase_gate_f004.py`: Phasenwechsel mit nur `ui_test_red_done`, nur
  `red_test_done`, nur Artefakt bzw. ohne jeden Nachweis (AC-6) — als Subprozess über das
  `phase`-Kommando, damit auch der Zustand auf der Platte belegt ist
- Volle Suite grün, `sync_skills.py --check` synchron
- AC-3 ist eine Anweisung an das Modell und wird in der nächsten gregor-Phase beobachtet
