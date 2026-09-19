# Context: fix-140-po-decision-gates

## Request Summary

Issue #140: Zwei Probleme untergraben den Zweck der Freigabe-Interaktion für einen
nicht-technischen PO. (1) Nach "approved" muss der User `/tdd-red` und danach
`/50-implement` jeweils selbst abtippen, obwohl dabei keine neue Entscheidung fällt
— die Entscheidung ist mit "approved" schon getroffen. (2) Der 3.18.0-Pflichtblock
"Wo ich für dich entschieden habe" ist nur eine Prompt-Instruktion; live wurde
beobachtet, dass er fehlte und der Freigabe-Text stattdessen Entwickler-Jargon
enthielt, den ein PO nicht bewerten kann.

## Related Files

| File | Relevance |
|------|-----------|
| `core/hooks/phase_listener.py` | Verarbeitet `approved`/`go`-Keywords. Zeile ~276: setzt `spec_approved=True`, `current_phase=phase4_approved`, gibt nur `"You may now run /tdd-red"` aus — keine automatische Weiterleitung. GREEN-Approval (`go`) analog für `phase6_implement`/`phase6b_adversary`, setzt zusätzlich einen Freigabe-Marker (`user_approved_validation_<name>`) für `post_implementation_gate.py`. |
| `skills/40-tdd-red/SKILL.md`, `skills/50-implement/SKILL.md` | `disable-model-invocation: true` — verhindert Skill-Tool-Aufruf durch Claude, User muss den Slash-Befehl selbst tippen. |
| `skills/60-validate/SKILL.md`, `skills/70-deploy/SKILL.md`, `skills/80-workflow/SKILL.md`, `skills/81-add-artifact/SKILL.md`, `skills/99-reset/SKILL.md` | Ebenfalls `disable-model-invocation: true`, aber andere Kategorie: `60-validate` = echte manuelle Nutzertests, `70-deploy` = Produktions-Risiko, `80-workflow`/`81-add-artifact`/`99-reset` = Meta-/State-Operationen (nicht Teil dieses Issues, siehe "Nicht-Ziele"). |
| `core/commands/30-write-spec.md`, `core/commands/40-tdd-red.md`, `core/commands/50-implement.md` | Parallel zu `skills/*/SKILL.md` gepflegte Command-Dateien (kein 1:1-Duplikat, siehe Diff-Befund unten). Enthalten je einen `/clear`-Reentry-Checkpoint-Block ("Next command"-Hinweis, getestet von `test_clear_checkpoint_blocks.py`): `30-write-spec.md → /40-tdd-red`, `40-tdd-red.md → /50-implement`, `50-implement.md → /60-validate`. `30-write-spec.md` trägt zusätzlich den 3.18.0-Block "Wo ich für dich entschieden habe" als PFLICHT-Prompt-Instruktion (nur Text, kein Hook-Check). |
| `setup.py::generate_command_aliases()` | Liest `disable-model-invocation` aus `skills/<name>/SKILL.md`, um pro Skill zu entscheiden: `true` → voller SKILL.md-Inhalt wird in die generierte `.claude/commands/<name>.md`-Alias-Datei eingebettet (Skill-Tool-Weg würde am Gate scheitern); `false` → dünner Text-Redirect. Eine Änderung des Flags bei `40-tdd-red`/`50-implement` ändert also auch, WIE die Alias-Datei für diese beiden Skills generiert wird. |

## Existing Patterns

- **3.18.0-Präzedenzfall** (`core/commands/30-write-spec.md`): Freigabe-relevante
  Information wird destilliert, nicht aus fester Template-Sektion — funktioniert
  auch bei lokal abweichenden `spec-writer`-Templates. Reine Prompt-Instruktion,
  bewusst kein Hook-Gate ("Der Block wird aus dem Inhalt der Spec destilliert").
- **Blanket-Regel seit 3.2.0** (CHANGELOG): `disable-model-invocation: true` für
  TDD/Implement/Validate/Deploy — "nur User-Trigger", ohne pro-Phase dokumentierte
  Begründung. Diese Recherche hat keine tiefere Rationale in Commits/Issues
  gefunden als die Blanket-Aussage selbst.
- **`/clear`-Reentry-Checkpoints** (Issue #103/#104, siehe Memory
  `project_clear_reentry_switch_fix.md`): jede Phasen-Datei endet mit einem Block,
  der den nächsten Befehl nennt — Testabdeckung in `test_clear_checkpoint_blocks.py`
  über `LATE_PHASE_FILES = ["40-tdd-red.md", "50-implement.md"]` und ein
  Paar-Mapping `(Datei, nächster Befehl)`.

## Dependencies

- **Upstream:** `phase_listener.py` (UserPromptSubmit-Hook) ist der einzige Ort,
  der `approved`/`go` interpretiert und Phasenübergänge auslöst.
- **Downstream:**
  - `setup.py::generate_command_aliases()` liest das Flag aus `skills/*/SKILL.md`.
  - `migrate_to_plugin.py::_find_removable_command_files()` erkennt generierte
    Alias-Dateien über einen Inhalts-Marker, unabhängig vom Flag — nicht betroffen.
  - `post_implementation_gate.py` verlangt den `user_approved_validation_<name>`-
    Marker, der aktuell nur durch die GREEN-Phrase (`go`) gesetzt wird — falls
    Auto-Chaining nach TDD-RED eingeführt wird, muss dieser Marker-Mechanismus
    unangetastet bleiben (betrifft `phase6_implement`, nicht `phase5_tdd_red`).

## Existing Specs

- `docs/specs/short-command-aliases.md` — Design-Doc zum Alias-Mechanismus,
  erklärt Embed-vs-Redirect-Unterscheidung über `disable-model-invocation`.

## Betroffene Tests (müssen bei Änderung mitgeplant werden)

- `tests/test_setup_command_aliases.py` — `_is_model_invocable()` liest das Flag
  direkt aus `SKILL.md`; AC-3b prüft expliziten Full-Embed-Fall für
  `50-implement` (aktuell `disable-model-invocation: true`).
- `tests/test_clear_checkpoint_blocks.py` — Checkpoint-Paare
  `("30-write-spec.md", "/40-tdd-red")`, `("40-tdd-red.md", "/50-implement")`,
  `("50-implement.md", "/60-validate")`; `LATE_PHASE_FILES` enthält beide
  betroffenen Dateien.
- `tests/test_skill_path_resolution.py` — nutzt `skills/50-implement/SKILL.md`
  als Referenzdatei für Pfad-Resolution-Snippets (Setup-Block), unabhängig vom
  Flag, aber Datei wird ohnehin verändert.
- `tests/test_artifact_types.py` — referenziert `adversary_dialog` im Kontext
  von Skill `50-implement`, inhaltlich nicht vom Flag betroffen, aber Datei im
  Blickfeld behalten.

## Analysis

### Type
Feature (Gate-Kalibrierung, keine Fehlerbehebung im engeren Sinn)

### Korrektur der Issue-Prämisse (wichtigster Analyse-Befund)

Das Issue nahm an, `approved→/40-tdd-red` UND `/40-tdd-red→/50-implement` seien
beide reine Formsache. Für den zweiten Übergang widerspricht die bestehende
Code-Basis das explizit: `core/commands/40-tdd-red.md:189` weist Claude an,
NICHT selbst mit der Implementierung zu beginnen, sondern auf `/50-implement`
zu warten. Begründung: TDD-RED schreibt nur Testdateien (reversibel,
ungefährlich); `/50-implement` schreibt echten Produktivcode und spawnt
Subagenten dafür — dieselbe Risikokategorie wie die bereits als Nicht-Ziel
anerkannten `60-validate`/`70-deploy` (reale Handlung statt Formsache).

**Entscheidung: asymmetrische Lösung.** Nur `approved→/40-tdd-red`
automatisieren. `/40-tdd-red→/50-implement` bleibt unverändert manuell.

### Affected Files (with changes)

| File | Change Type | Description |
|------|-------------|-------------|
| `skills/40-tdd-red/SKILL.md` | MODIFY | `disable-model-invocation: true` → `false` |
| `core/commands/30-write-spec.md` | MODIFY | (a) "## After Approval": Anweisung "ruf `40-tdd-red` direkt selbst über das Skill-Tool auf, warte nicht auf User-Eingabe" — außerhalb des `/clear`-Checkpoint-Blocks (Zeilen 204-216), damit `test_checkpoint_structure_identical_across_files` nicht bricht. (b) Pflicht-Block "Wo ich für dich entschieden habe": explizite Verbotsliste (Code-Identifier, Dateipfade, Bibliotheks-/API-Namen, LoC-Zahlen) + PO-Selbst-Check-Anweisung ergänzen. |
| `core/commands/40-tdd-red.md` | MODIFY (optional) | Kurzer Hinweis Step 0, dass der Skill nun auch automatisch nach Freigabe läuft — keine Verhaltensänderung nötig |
| `tests/test_write_spec_jargon_guard.py` | CREATE (optional) | Reiner Präsenz-Check: Verbotsliste/Selbst-Check-Text in `30-write-spec.md` vorhanden — kann keine Semantik prüfen, verhindert aber regressives Wegfallen |

**Keine Pflicht-Änderung:** `tests/test_setup_command_aliases.py` (generische
Parametrisierung über `_is_model_invocable()` deckt den Flag-Flip automatisch
ab; AC-3b ist hartcodiert auf `50-implement`, bleibt unberührt) und
`tests/test_clear_checkpoint_blocks.py` (sofern der `/clear`-Checkpoint-Block
strukturell unverändert bleibt). `core/hooks/phase_listener.py` bleibt
unverändert — eine Kontext-Injektion direkt im Hook wäre ein unverifizierter
Mechanismus (kein `hookSpecificOutput.additionalContext` im Repo verwendet)
und ist kein Bestandteil dieser Spec.

### Scope Assessment
- Files: 2 Pflicht (`skills/40-tdd-red/SKILL.md`, `core/commands/30-write-spec.md`), 2 optional
- Estimated LoC: ~65-95
- Risk Level: MEDIUM (Kern-Gate-Datei, aber durch asymmetrische Eingrenzung und automatische Testabdeckung risikoarm umgesetzt)

### Technical Approach

**Problem 1:** Flag-Flip `disable-model-invocation: false` bei `40-tdd-red`
ist notwendig (nicht nur hinreichend) — ohne ihn bleibt Selbstaufruf technisch
unmöglich, unabhängig von jeder Prompt-Formulierung. Eine reine
Prompt-Instruktion ("Next: /40-tdd-red") ohne Flag-Flip ändert nichts, weil
das Skill-Tool-Gate hart blockt. Robust gegenüber den historischen
Redirect/Embed-Bugs (#55/#56/#87), weil `40-tdd-red` dadurch exakt die
Alias-Strategie bekommt, die für alle anderen 15+ model-invocable Skills
bereits produktiv ist — kein neuer Mismatch.

**Problem 2:** Reine Prompt-Verschärfung, kein Hook-Gate. Es gibt keinen
Hook-Typ, der Assistant-Prosa vor der Anzeige an den User prüfen könnte
(`PreToolUse`/`PostToolUse`/`UserPromptSubmit` sehen das nicht; ein
`Stop`-Hook käme erst nach der Anzeige). Identifier-Heuristiken hätten zudem
False Negatives (Jargon ohne Code-Form) und False Positives (legitime
Eigennamen je Konsumenten-Projekt) — würde die 3.18.0-Kompatibilitätsanforderung
("funktioniert auch bei abweichenden Templates") verletzen.

### Open Questions
- [ ] Optionaler `test_write_spec_jargon_guard.py` — mitnehmen oder auf später verschieben?
- [ ] Kontext-Injektion in `phase_listener.py` als späteres Add-on — separates Issue oder ganz verwerfen?

## Risks & Considerations

- **Zwei fast unabhängige Teilprobleme mit unterschiedlichem Reifegrad:**
  Problem 1 (redundanter Tastendruck) ist mechanisch klar lösbar; Problem 2
  (Jargon/PO-Sprache absichern) hat noch keine erprobte Lösung — reine
  Prompt-Verschärfung vs. zusätzlicher (Heuristik-)Hook-Check muss in der
  Analyse-Phase gegeneinander abgewogen werden.
- **Flag-Wechsel hat Doppelwirkung:** `disable-model-invocation` steuert sowohl
  das Claude-Code-Skill-Tool-Gate als auch `setup.py`s Alias-Generierung. Eine
  Änderung für `40-tdd-red`/`50-implement` erfordert Anpassung von
  `test_setup_command_aliases.py` (Embed→Redirect-Erwartung) UND Prüfung, ob ein
  dünner Text-Redirect für ein neu model-invocable Skill überhaupt sauber
  funktioniert (Historie: #55/#56/#87 drehten sich genau um diese Redirect-
  vs-Embed-Unterscheidung — Vorsicht vor Regression).
- **`/clear`-Reentry-Checkpoints kollidieren mit Auto-Chaining:** Wenn
  `/40-tdd-red` nach "approved" automatisch läuft, wird der
  Checkpoint-Hinweis "Next: /40-tdd-red" in `30-write-spec.md` ggf. obsolet oder
  muss umformuliert werden — `test_clear_checkpoint_blocks.py` würde dann
  fehlschlagen und braucht eine bewusste Anpassung, kein Kollateralschaden.
- **Blast Radius:** Kern-Gate-Änderung, wirkt auf alle Konsumenten-Projekte
  (gregor_zwanzig, oebb-nightjet-monitor, henemm-infra, henemm-n8n,
  henemm-website, henemm-security) beim nächsten Plugin-Update.
- **Nicht-Ziele (aus Issue-Scope-Vorschlag):** `60-validate` (echte manuelle
  Nutzertests) und `70-deploy` (Produktions-Risiko) bleiben unverändert —
  andere Risikokategorie, kein "reine Formsache"-Fall. `80-workflow`,
  `81-add-artifact`, `99-reset` sind Meta-/State-Operationen, nicht Teil der
  im Issue beschriebenen Freigabe-Kette — nur erwähnen, falls die Analyse
  ergibt, dass dieselbe Logik dort ebenfalls zutrifft.
