# Kontext: Selbst-erklärende Gate-Block-Meldungen

## Auslöser

In einem abhängigen Projekt (`gregor_zwanzig`) wurden ~1,9 Mio Token verbrannt,
weil ein Gate wiederholt blockte und die Block-Meldung nicht verriet, *warum*.
Die Ursache lag im Plumbing (Workflow-Auflösung) und musste über ~30 Schritte
manuell ergraben werden.

## Befund (Ist-Zustand im Meta-Framework)

### 1. Workflow-Auflösung — bereits weitgehend vereinheitlicht
- Alle vier Gates lesen den aktiven Workflow über **eine** geteilte Funktion
  `get_active_workflow_name()` in `core/hooks/hook_utils.py` (Zeile 158).
  Quelle: Env-Var `OPENSPEC_ACTIVE_WORKFLOW` → Fallback `settings.local.json`.
- Der `.active`-Symlink ist als Auflösungsquelle abgeschaltet (`workflow.py`,
  Doku in CLAUDE.md). Das "schreibt A, liest B" der Original-Diagnose ist hier
  also strukturell entschärft.

### 2. Residual-Drift (Symlink-Reste)
Trotz "Symlink abgeschaltet" hängen noch `.active`-Symlink-Referenzen in:
- `bash_gate.py:146`
- `edit_gate.py:199` (nur zum Schreiben von `loc_delta_current` für Status)
- `phase_listener.py:86` (+ Docstring behauptet noch Symlink-Fallback)
- `post_bash.py:79`
Code und Doku driften → Cleanup nötig, aber nicht die Wurzel.

### 3. Block-Meldungen — Kontext fehlt (eigentlicher Hebel)
Alle relevanten `block(...)`-Aufrufe:

**edit_gate.py**
- `:274` "No active workflow for {name}" — sagt nicht, welcher Name aufgelöst wurde / wo gesucht wurde
- `:282` "Phase {phase} does not allow code edits" — kein Workflow-Name, kein Token-Status
- `:299` "No RED test artifacts" — kein Workflow-Name
- `:309` LoC-Fehler — zeigt bereits Delta vs. Limit (gutes Vorbild), aber kein Workflow/Token

**bash_gate.py**
- `:318` "Adversary verdict missing or not VERIFIED" — kein Workflow-Name, kein Ist-Verdict
- `:308` "verdict is AMBIGUOUS"

### 4. Token-API (vorhanden, nutzbar)
`core/hooks/override_token.py` → `has_valid_token(workflow_name=None) -> bool`,
TTL 1h, Multi-Workflow. Liefert genau den "Token gültig?"-Status für die Meldung.

## Zielbild

Jede blockende Gate-Meldung trägt einen einheitlichen Diagnose-Suffix, der die
Ursache direkt sichtbar macht — z.B.:
`[wf=selfexplaining-gates (env) | token=keins | phase=phase3_spec]`
bzw. bei LoC zusätzlich `delta=+312/limit 250`.

Prinzip: **Hook erzwingt Sichtbarkeit** statt "Claude möge sich erinnern".
Ein gemeinsamer Helper in `hook_utils.py` baut den Suffix → genau eine Wahrheit,
von beiden Gates genutzt.

## Scope

- IN: Diagnose-Suffix-Helper + Einbau in edit_gate/bash_gate Block-Meldungen;
  Symlink-Reste-Cleanup + Doku-Sync.
- OUT: Änderung der Workflow-Auflösungs-Logik selbst (ist korrekt);
  gregor_zwanzig-Config (GZ_ACTIVE_WORKFLOW → OPENSPEC_ACTIVE_WORKFLOW) —
  das ist Sache der gregor-Instanz (separate MQ-Nachricht).

## Referenzdateien

- `core/hooks/hook_utils.py` (get_active_workflow_name, Helper-Ziel)
- `core/hooks/edit_gate.py` (Block-Stellen)
- `core/hooks/bash_gate.py` (Block-Stellen)
- `core/hooks/override_token.py` (has_valid_token)
- `core/hooks/phase_listener.py`, `post_bash.py` (Symlink-Reste)
