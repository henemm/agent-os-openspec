# Fast Track: Zwei Stufen statt drei — Stufen-Tabelle auf den Code zurückschneiden (#254, Teil von #250)

## Problem

`/00-intake` dokumentiert drei Aufwandsstufen (Fast Track, Standard, Full Process). Der Workflow-State
kennt nur zwei (`feature-fast`, `feature`); Standard und Full Process starten beide mit
`--type feature`, kein Hook kann sie unterscheiden. Die Tabelle verspricht zudem „Adversary: 1 Runde"
für Standard, obwohl `adversary_dialog.MIN_ROUNDS = 2` für jede Stufe ein harter Boden ist. Die
Workflow-Auswertung (1.958 Workflows) bestätigt: der Standardweg hat Fixkosten von rund 3 Stunden,
eine dritte Stufe ohne Mechanik ändert daran nichts.

## Entscheidung (Alternative aus #254)

Statt einer dritten Stufe im State wird die Stufen-Tabelle auf das zurückgeschnitten, was der Code
tut: **zwei Stufen** — Fast Track (`feature-fast`) und voller Prozess (`feature`). Die Tiefe im
vollen Prozess (Kontext/Analyse kurz oder getrennt, Modellwahl) bleibt eine **Anweisung nach Score**,
kein Zustand im State. Die Aufwandsbremse (Teilauftrag in #250) kennt damit zwei Stufen.

## Scope

- `core/commands/00-intake.md`: Scoring, „Workflow starten", Modell-Empfehlung und Track-Unterschiede
  auf zwei Stufen; Adversary „mindestens 2 Runden" (Wert aus `MIN_ROUNDS`).
- `skills/00-intake/SKILL.md`, `skills/30-write-spec/SKILL.md`: generiert (`scripts/sync_skills.py`).
- `core/commands/30-write-spec.md`, `README.md`, `CLAUDE.md`: Bezeichnung „Standard / Full Process"
  → „voller Prozess".
- `CHANGELOG.md` unter [Unreleased].
- **Nicht enthalten:** Hook-Code (`workflow.py`, `adversary_dialog.py`) bleibt unverändert; keine
  stufenabhängige `MIN_ROUNDS`; die Aufwandsbremse selbst.

## Definition of Done

Kein Text im Framework verspricht mehr als drei Stufen oder eine einzelne Adversary-Runde. Die
Quelle und die generierten Skills sind synchron.

## Acceptance Criteria

- **AC-1:** Given `core/commands/00-intake.md`, Then enthält sie keine Zusage „1 Runde" für Adversary.
- **AC-2:** Given der Wert `MIN_ROUNDS` in `adversary_dialog.py`, Then nennt `00-intake.md` genau
  diese Mindestzahl („mindestens N Runden").
- **AC-3:** Given der Abschnitt „Workflow starten", Then gibt es genau zwei `workflow.py start`-Blöcke
  (`feature-fast` und `feature`), keinen zweiten mit demselben Typ.
- **AC-4:** Given `00-intake.md`, README, `30-write-spec.md` und `CLAUDE.md`, Then kommt „Full Process"
  als Stufenname nicht mehr vor.
- **AC-5:** Given Quelle und generierte Skills, Then meldet `scripts/sync_skills.py --check` keinen
  Drift.

## Test Plan

`tests/test_intake_two_tracks_254.py`: Textprüfungen zu AC-1 bis AC-5. Hook-Verhalten bleibt durch
die bestehende Suite abgedeckt (unverändert). Wirkung auf das Verhalten von Claude lässt sich nicht
automatisch prüfen; sie zeigt erst die Workflow-Auswertung (Dauer je Typ) nach einigen Wochen.
