---
entity_id: fix-140-po-decision-gates
type: feature
created: 2026-09-18
updated: 2026-09-19
status: draft
version: "1.1"
tags: [gates, phase-listener, skills, po-decision]
workflow: fix-140-po-decision-gates
---

# PO-Entscheidungsgates kalibrieren (Issue #140)

## Approval

- [ ] Approved

## Purpose

Issue #140 beschreibt zwei Probleme, die den Zweck der Freigabe-Interaktion für einen
nicht-technischen PO untergraben: (1) Nach "approved" muss der User zusätzlich noch
`/40-tdd-red` selbst abtippen, obwohl dabei keine neue Entscheidung fällt — die
Entscheidung ist mit "approved" bereits getroffen. (2) Der bestehende Pflicht-Block
"Wo ich für dich entschieden habe" (seit 3.18.0) ist reine Prompt-Instruktion und kann
Entwickler-Jargon enthalten, den ein PO nicht bewerten kann.

Diese Spec adressiert **nur noch Teil (1)**: automatisiert genau den Übergang, der
keine echte Entscheidung mehr trägt. Teil (2) ist zwischenzeitlich durch das
unabhängige PO-Briefing (3.20.0, `core/agents/po-briefer.md`) bereits gelöst — der
PO liest dort den wörtlich zitierten, unabhängig geprüften Briefing-Text statt der
Orchestrator-Zusammenfassung; eine zusätzliche Jargon-Verbotsliste für Letztere wäre
doppelte Prüflogik für zwei verschiedene Autoren gewesen (siehe Known Limitations).

## Source

- **File:** `skills/40-tdd-red/SKILL.md`
- **Identifier:** YAML-Frontmatter-Feld `disable-model-invocation`
- **File:** `core/commands/30-write-spec.md`
- **Identifier:** Abschnitt "## After Approval"

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/phase_listener.py` | bestehender Hook (UserPromptSubmit) | Interpretiert `approved`/`go`, setzt `spec_approved=True` und `current_phase=phase4_approved`. Bleibt in dieser Spec **unverändert** — kein Hook-Code wird angefasst. |
| `setup.py::generate_command_aliases()` / `_is_model_invocable()` | bestehende Funktion | Liest `disable-model-invocation` aus `SKILL.md`, um zwischen Full-Embed- und Thin-Redirect-Alias zu entscheiden. Der Flag-Flip bei `40-tdd-red` ändert automatisch, welchen Alias-Typ diese Funktion für dieses Skill erzeugt — ohne Code-Änderung in `setup.py` selbst. |
| `tests/test_setup_command_aliases.py` | bestehende Tests | Generische Parametrisierung über `_is_model_invocable()` deckt den Flag-Flip bei `40-tdd-red` automatisch ab, ohne Testcode-Änderung. |
| `tests/test_clear_checkpoint_blocks.py` | bestehende Tests | Prüft den `/clear`-Checkpoint-Block in `30-write-spec.md`. Muss unverändert grün bleiben — die neue Anweisung darf den Checkpoint-Block strukturell nicht antasten. |
| `core/commands/40-tdd-red.md` | bestehende Datei | Enthält die STOPP-Anweisung ("NICHT selbst mit der Implementierung beginnen"), die den zweiten Übergang (`/40-tdd-red → /50-implement`) bewusst manuell hält. Bleibt unverändert. |
| `skills/50-implement/SKILL.md` | bestehende Datei | `disable-model-invocation: true` bleibt unverändert — dieser Übergang ist NICHT Teil des Scopes. |
| `core/agents/po-briefer.md` (3.20.0) | bestehender Agent | Löst den ursprünglich mitgeplanten Teil (2) bereits unabhängig und hart-gegated — kein Teil dieser Spec, nur Abgrenzungsgrund. |

## Scope

- **Affected Files:** `skills/40-tdd-red/SKILL.md` (Flag-Flip), `core/commands/30-write-spec.md` (Auto-Chaining-Anweisung), `tests/test_skill_stop_instruction.py` (neuer Regressionstest für die aus dem Adversary-Fund F001 entstandene STOPP-Absicherung), `CHANGELOG.md`, `.claude-plugin/plugin.json` (Versionsbump)
- **Estimated Changes:** ~40 LoC (nach Entfernen des ursprünglich mitgeplanten Teils B)

## Implementation Details

### 1. `skills/40-tdd-red/SKILL.md` — Flag-Flip

```yaml
---
description: "Write failing tests (RED phase)"
disable-model-invocation: false
---
```

Dies ist die **notwendige** Voraussetzung, nicht nur eine hinreichende: Ohne den
Flag-Flip bleibt der Selbstaufruf über das Skill-Tool technisch unmöglich — eine
reine Prompt-Instruktion ("ruf jetzt `/40-tdd-red` auf") ändert daran nichts, weil das
Skill-Tool-Gate hart blockt, solange `disable-model-invocation: true` gesetzt ist.
`40-tdd-red` erhält dadurch exakt die Alias-Strategie (Thin-Redirect statt
Full-Embed), die für alle anderen bereits model-invocable Skills produktiv im Einsatz
ist — kein neuer Mechanismus, kein neuer Redirect/Embed-Mismatch (Historie #55/#56/#87).

### 2. `core/commands/30-write-spec.md` — Auto-Chaining nach Freigabe

Im Abschnitt "## After Approval", **zwischen** Schritt 3 ("Next: `/40-tdd-red` to
write failing tests") und der Überschrift "Nach der Freigabe kannst du dem User
zusätzlich den Kontext-Reset anbieten" — also **außerhalb** des
`/clear`-Checkpoint-Blocks (Instruktions-/Ausgabe-Abschnitte ab "### Checkpoint
prüfen"), damit `test_clear_checkpoint_blocks.py` strukturell unangetastet bleibt:

> Ohne `/clear` in derselben Session: Rufe den Skill `40-tdd-red` jetzt sofort selbst
> auf — warte nicht auf eine weitere User-Eingabe, die Freigabe ("approved") ist
> bereits die Entscheidung.
>
> Mit `/clear` dazwischen: Der Checkpoint-Block unten zeigt den regulären
> Wiedereinstieg über den expliziten Befehl `/40-tdd-red #<N>`.

Der `/40-tdd-red → /50-implement`-Übergang bleibt bewusst unverändert manuell:
`disable-model-invocation: true` bei `skills/50-implement/SKILL.md` und die
STOPP-Anweisung in `core/commands/40-tdd-red.md` ("**NICHT** selbst mit der
Implementierung beginnen. Warte bis der User `/50-implement` tippt.") werden NICHT
angefasst. Begründung: TDD-RED schreibt nur Testdateien (reversibel, ungefährlich);
`/50-implement` schreibt echten Produktivcode und spawnt Subagenten dafür — dieselbe
Risikokategorie wie die bereits als Nicht-Ziel anerkannten `60-validate` (echte
manuelle Nutzertests) und `70-deploy` (Produktions-Risiko). Eine reale Handlung mit
Konsequenzen ist keine Formsache und bleibt an eine explizite User-Eingabe gebunden.

### 3. `tests/test_skill_stop_instruction.py` (neu — Adversary-Fund F001)

Der Flag-Flip in Punkt 1 aktiviert einen Skill-Tool-Selbstaufruf-Pfad, der
`skills/40-tdd-red/SKILL.md` liest — nicht `core/commands/40-tdd-red.md`. Die
STOPP-Anweisung, die den `/50-implement`-Übergang manuell hält, stand ursprünglich
nur im Command-Dokument. Deshalb steht sie jetzt wortgleich auch in
`skills/40-tdd-red/SKILL.md`, direkt hinter dem Phasenwechsel auf `phase6_implement`.
Vier Tests (String-Präsenz beider Anweisungsteile, Positions-Check relativ zum
Phasenwechsel, Cross-Datei-Konsistenz zwischen Skill und Command) sichern das gegen
künftige Drift ab.

### 4. CHANGELOG.md

Neuer Eintrag unter `[3.22.0]`, Abschnitt `### Added`.

### 5. Versionsbump

- `.claude-plugin/plugin.json`: Versionsbump auf `3.22.0` (MINOR, additiv, keine
  Breaking Changes; nächste freie Version nach dem inzwischen auf `3.21.0`
  fortgeschrittenen `main`).

## Expected Behavior

- **Input:** User schreibt "approved" als Antwort auf die Freigabe-Zusammenfassung
  von `/30-write-spec`, ohne `/clear` dazwischen.
- **Output:** `phase_listener.py` setzt `phase4_approved` (unverändert). Claude ruft
  danach eigenständig den Skill `40-tdd-red` über das Skill-Tool auf — der User muss
  `/40-tdd-red` nicht mehr selbst eingeben. Der `/40-tdd-red → /50-implement`-Übergang
  bleibt unverändert: Claude stoppt nach Phase 5 und wartet auf die explizite
  User-Eingabe `/50-implement`.
- **Side effects:** Keine Änderung an `core/hooks/phase_listener.py` oder anderen
  Hook-Dateien. `setup.py::generate_command_aliases()` erzeugt für `40-tdd-red` ab
  sofort einen Thin-Redirect-Alias statt eines Full-Embed-Alias (automatische Folge
  des Flag-Flips, keine Code-Änderung in `setup.py` nötig).

## Known Limitations

- **Ursprünglicher Teil (2) nicht mehr Teil dieser Spec:** Die Jargon-Verbotsliste
  für den Freigabe-Text wurde verworfen, weil das inzwischen gemergte unabhängige
  PO-Briefing (3.20.0) denselben Zweck bereits robuster erfüllt — durch einen
  separaten Agenten statt durch eine Selbst-Check-Instruktion an denselben
  Orchestrator, der die Spec auch geschrieben hat.
- **Asymmetrie zwischen den beiden Übergängen ist beabsichtigt, nicht inkonsistent:**
  `approved → /40-tdd-red` wird automatisiert, `/40-tdd-red → /50-implement` bleibt
  manuell, weil beide unterschiedliche Risikokategorien sind (reversible Testdateien
  vs. echter Produktivcode mit Subagenten-Spawn).
- **Blast Radius:** Kern-Gate-Datei (`skills/40-tdd-red/SKILL.md`), wirkt auf alle
  Konsumenten-Projekte beim nächsten Plugin-Update (gregor_zwanzig,
  oebb-nightjet-monitor, henemm-infra, henemm-n8n, henemm-website, henemm-security).
  Risiko ist durch die enge, einseitige Eingrenzung (nur ein Flag, nur ein
  Übergang) gering.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [x] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [x] Nach "approved" ruft Claude `/40-tdd-red` erkennbar ohne weiteren Tastendruck
  selbst auf — beobachtbar daran, dass kein Slash-Command mehr vom User verlangt wird
- [x] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün,
  inklusive der neu hinzugekommenen `test_po_briefing_gate.py`/`test_ci_spec_gate.py`)

## Acceptance Criteria

- **AC-1:** Given `skills/40-tdd-red/SKILL.md` mit `disable-model-invocation: false`
  und ein Workflow in `phase4_approved` / When der User "approved" schreibt (ohne
  `/clear` dazwischen) / Then ruft Claude den Skill `40-tdd-red` selbst über das
  Skill-Tool auf, ohne auf eine weitere User-Eingabe zu warten.
  - Test: *(Datei-Zustands-Check, Laufzeitverhalten nicht automatisiert prüfbar)*
- **AC-2:** Given ein Workflow in `phase5_tdd_red` mit registrierten RED-Artefakten /
  When Claude die Phase abschließt / Then bleibt der Übergang zu `/50-implement`
  manuell: `skills/50-implement/SKILL.md` behält `disable-model-invocation: true`,
  und sowohl `core/commands/40-tdd-red.md` als auch `skills/40-tdd-red/SKILL.md`
  enthalten die Anweisung "**NICHT** selbst mit der Implementierung beginnen. Warte
  bis der User `/50-implement` tippt."
  - Test: `pytest tests/test_skill_stop_instruction.py`
- **AC-3:** Given die neue Anweisung zum Auto-Chaining in
  `core/commands/30-write-spec.md` / When die Datei nach Umsetzung gelesen wird /
  Then steht diese Anweisung außerhalb der Abschnitte "### Checkpoint prüfen
  (Anweisung an dich — nicht ausgeben)" bis "### Ausgabe B: Negativ-Block" — der
  `/clear`-Checkpoint-Block bleibt strukturell identisch zum Vorher-Stand.
  - Test: `pytest tests/test_clear_checkpoint_blocks.py`
- **AC-4:** Given der volle Testlauf nach Umsetzung / When `pytest
  tests/test_setup_command_aliases.py tests/test_clear_checkpoint_blocks.py -v`
  ausgeführt wird / Then laufen beide Dateien grün, **ohne dass ihr Testcode
  angepasst wurde** (Regressionsschutz explizit verifizieren, nicht nur annehmen).
  - Test: `pytest tests/test_setup_command_aliases.py tests/test_clear_checkpoint_blocks.py`
- **AC-5:** Given `CHANGELOG.md` / When die Datei nach Umsetzung gelesen wird / Then
  enthält sie einen `[3.22.0]`-Eintrag unter `### Added`, der Issue #140 und den
  Flag-Flip bei `40-tdd-red` erwähnt.
  - Test: *(manuelle Sichtprüfung, kein automatischer Test für Freitext-Changelog)*
- **AC-6:** Given `.claude-plugin/plugin.json` / When die Datei nach Umsetzung
  gelesen wird / Then ist der Wert des Felds `"version"` exakt `"3.22.0"`.
  - Test: *(manuelle Sichtprüfung)*

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_skill_stop_instruction.py` (AC-2)
- `pytest tests/test_clear_checkpoint_blocks.py` (AC-3, AC-4)
- `pytest tests/test_setup_command_aliases.py` (AC-4)
- Volle Regressionssuite: `pytest tests/ -v`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Es wird kein neues Architektur-Pattern eingeführt, sondern ein
  bestehendes Gate (Freigabe-Interaktion nach TDD-Phasenmodell) kalibriert — analog
  zum bereits etablierten 3.18.0-Präzedenzfall im selben Command. Kein neuer Hook,
  kein neuer State-Mechanismus, keine Änderung an `core/hooks/`.

## Changelog

- 2026-09-18: Initial spec erstellt (Issue #140 — beide Teile geplant)
- 2026-09-19: Teil (2) (Jargon-Verbotsliste) verworfen — durch das zwischenzeitlich
  gemergte unabhängige PO-Briefing (3.20.0) bereits abgedeckt. Rebase auf
  `origin/main` (3.21.0 → Versionsbump auf 3.22.0). Definition of Done und Test
  Plan als neue Pflicht-Sektionen ergänzt (Template-Änderung aus 3.20.0).
