# Mini-Spec: Fußzeile darf nicht entfallen, wenn Claude selbst im Turn die Phase wechselt (#221)

## Problem

Live-Beispiel (gregor_zwanzig, Workflow `refactor-2276-s6e-versand-wertprops`):

```
[Analyse-Text …]

Workflow steht jetzt in Phase 3 (Spec). Nächster Schritt: /30-write-spec.
```

Keine `❗`/`ℹ️`-Zeile, keine `ℹ️ Status`-Zeile, nicht einmal die `⚙`-Zeile — obwohl die
Instruktion ausdrücklich verlangt, dass die `⚙`-Zeile *immer* die letzte Zeile ist, „auch
wenn die übrigen Zeilen entfallen".

Rekonstruiert per Workflow-JSON: Der Phasenwechsel `phase2_analyse → phase3_spec` geschah
**innerhalb desselben Turns**, in dem die zitierte Nachricht geschrieben wurde (Claude rief
`workflow.py phase phase3_spec` selbst per Bash auf, nachdem die Analyse fertig war). Der
`status_note()`-Hinweis wird aber nur beim **Start** eines Turns (UserPromptSubmit)
injiziert und spiegelte zu diesem Zeitpunkt noch die ALTE Phase. Weder `status_note()` noch
`marker_block()` sagen etwas darüber, was zu tun ist, wenn die eigene Aktion im selben Turn
den Hinweis überholt hat — vermutlich deshalb wurde der Widerspruch nicht aufgelöst, sondern
die komplette Fußzeile weggelassen.

## Was ändert sich

- `core/hooks/workflow.py::status_note` und `scripts/sync_skills.py::marker_block`: neuer
  Satz, der den Fall explizit klärt: Hat *diese* Nachricht selbst per `workflow.py phase
  <x>` (oder `complete`) die Phase gewechselt, gilt für Schritt/Phase in der Fußzeile der
  NEUE, selbst herbeigeführte Stand — nicht der ggf. veraltete Hook-Hinweis. Die
  Marker-Zeilen entfallen dafür NIE aus diesem Grund; die `⚙`-Zeile bleibt in jedem Fall die
  letzte Zeile.
- `skills/*/SKILL.md` neu generiert (`sync_skills.py`).
- Erforderliche Literale bleiben erhalten (von bestehenden Tests geprüft): `` `❗ Du: …` ``,
  `ℹ️ Nichts zu tun:`, `danach: /<befehl> #<N>`, `‼️`, Reihenfolge ❗Du/ℹ️ → ℹ️Status → ⚙.

## Was darf sich nicht ändern

- Format/Reihenfolge der drei Fußzeilen bleibt unverändert.
- `30-write-spec` bleibt `MARKER_EXEMPT`.
- Keine neue Logik/kein neuer Hook — reine Text-/Instruktionspräzisierung, konsistent mit
  #209/#213 (Enforcement per Stop-Hook bleibt bewusst zurückgestellt, siehe #177).

## Acceptance Criteria

- **AC-1:** Given `status_note()`-Text, When gelesen, Then klärt er, dass ein selbst
  herbeigeführter Phasenwechsel im selben Turn den NEUEN Stand für die Fußzeile verlangt,
  nie deren Weglassen.
- **AC-2:** Given `marker_block()`-Text, When gelesen, Then sagt er dieselbe Klarstellung.
- **AC-3:** Given bestehende Tests zu Reihenfolge/Pflicht-Wörtern/Literalen, When sie nach
  der Änderung laufen, Then bleiben sie grün.
- **AC-4:** Given `sync_skills.py --check`, When es nach der Änderung läuft, Then meldet es
  „Skills synchron".

## Manuelle Test-Schritte

1. `workflow.status_note({...})` ausgeben und lesen: enthält die neue Klarstellung.
2. `skills/20-analyse/SKILL.md` nach dem Sync öffnen: Marker-Abschnitt enthält dieselbe
   Klarstellung.

## Test Plan

- Volle Suite `python3 -m pytest tests/`.
- `python3 scripts/sync_skills.py --check`.
