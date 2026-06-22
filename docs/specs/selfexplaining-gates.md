---
entity_id: selfexplaining_gates
type: feature
created: 2026-06-22
updated: 2026-06-22
status: draft
version: "1.0"
tags: [enforcement, hooks, diagnostics, dx, token-waste]
test_targets:
  - core/hooks/hook_utils.py
  - core/hooks/edit_gate.py
  - core/hooks/bash_gate.py
  - core/hooks/phase_listener.py
  - core/hooks/post_bash.py
---

# Selbst-erklärende Gate-Block-Meldungen

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** (noch nicht erstellt)

## Purpose

Wenn ein Gate (`edit_gate.py` / `bash_gate.py`) eine Aktion blockiert, soll die
Block-Meldung **selbst** die Ursache nennen: welchen Workflow das Gate aufgelöst
hat (und aus welcher Quelle), ob ein Override-Token gültig ist, und — wo
relevant — den Ist-vs-Soll-Wert (LoC-Delta, Adversary-Verdict).

**Motivation:** In `gregor_zwanzig` wurden ~1,9 Mio Token verbrannt, weil ein
Gate wiederholt blockte und die Meldung die Ursache nicht enthielt — sie musste
über ~30 Schritte im Plumbing ergraben werden. Steht die Ursache in der Meldung,
kann weder Mensch noch Agent Token mit Suchen verbrennen.

Prinzip: **Der Hook erzwingt Sichtbarkeit**, statt darauf zu hoffen, dass Claude
sich an die Plumbing-Interna erinnert.

Begleitend wird die **Symlink-Drift** bereinigt: Der `.active`-Symlink ist als
Workflow-Auflösungsquelle offiziell abgeschaltet (siehe `workflow.py`, CLAUDE.md),
aber Reste hängen noch in vier Hooks. Code und Doku werden synchronisiert, damit
genau **eine Wahrheit** für "welcher Workflow ist aktiv" gilt.

## Abhängigkeiten

| Komponente | Typ | Abhängigkeit |
|-----------|-----|-------------|
| `hook_utils.get_active_workflow_name()` | bestehend | wird um Quellen-Info erweitert |
| `hook_utils.gate_diagnostics()` | **neu** | gemeinsamer Diagnose-Suffix-Builder |
| `override_token.has_valid_token()` | bestehend | liefert Token-Status für Suffix |
| `edit_gate.py` / `bash_gate.py` | bestehend | Block-Meldungen anreichern |
| `phase_listener.py` / `post_bash.py` | bestehend | Symlink-Reste entfernen |

## Implementierungsdetails

### 1. Quellen-bewusste Auflösung (`hook_utils.py`)

`get_active_workflow_name()` wird auf einen neuen Kern `resolve_active_workflow()`
umgestellt, der zusätzlich die Quelle zurückgibt. Verhalten bleibt identisch:

```python
def resolve_active_workflow() -> tuple[str, str]:
    """Return (name, source). source ∈ {'env', 'settings', 'none'}."""
    name = os.environ.get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
    if name:
        return name, "env"
    try:
        settings_path = find_project_root() / ".claude" / "settings.local.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
            name = settings.get("env", {}).get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
            if name:
                return name, "settings"
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return "", "none"


def get_active_workflow_name() -> str:
    """Unverändertes Verhalten — delegiert an resolve_active_workflow()."""
    return resolve_active_workflow()[0]
```

### 2. Diagnose-Suffix-Builder (`hook_utils.py`, neu)

Eine einzige Funktion, von beiden Gates genutzt → genau eine Wahrheit:

```python
def gate_diagnostics(workflow: dict | None = None, **extra) -> str:
    """Bracketed diagnostics for block messages.

    Beispiel: '[wf=feature-login (env) | token=keins | phase=phase6_implement]'
    Fail-safe: jede Teilinfo, die nicht ermittelbar ist, wird zu '?' —
    der Builder wirft nie.
    """
    name, source = resolve_active_workflow()
    parts = [f"wf={name or '—'} ({source})"]
    try:
        from override_token import has_valid_token
        parts.append("token=gültig" if has_valid_token(name or None) else "token=keins")
    except Exception:
        parts.append("token=?")
    if workflow:
        parts.append(f"phase={workflow.get('current_phase', '?')}")
    for key, value in extra.items():
        parts.append(f"{key}={value}")
    return "[" + " | ".join(parts) + "]"
```

### 3. Einbau in `edit_gate.py`

Suffix an die ursachenrelevanten Block-Meldungen anhängen:

| Zeile (ca.) | bisher | neu (Suffix angehängt) |
|------|--------|------------------------|
| 274 | `No active workflow for {name}. Start with /context.` | `… {gate_diagnostics()}` |
| 282 | `Phase {phase} does not allow code edits. Need phase6_implement+.` | `… {gate_diagnostics(workflow)}` |
| 299 | `No RED test artifacts. Run /tdd-red first.` | `… {gate_diagnostics(workflow)}` |
| 309 | `LoC delta {total} exceeds limit {max_loc}. …` | `… {gate_diagnostics(workflow, delta=f"+{total}", limit=max_loc)}` |

Hinweis: Zeile 274 ("No active workflow") ist genau der Fall, der in gregor den
Deadlock auslöste — hier macht `wf=— (none)` bzw. `wf=X (settings)` die
Auflösungsquelle sofort sichtbar.

### 4. Einbau in `bash_gate.py`

| Zeile (ca.) | bisher | neu |
|------|--------|-----|
| 308 | `Adversary verdict is AMBIGUOUS. …` | `… {gate_diagnostics(wf, verdict="AMBIGUOUS")}` |
| 318 | `Adversary verdict missing or not VERIFIED. …` | `… {gate_diagnostics(wf, verdict=<ist-verdict oder 'keins'>)}` |

`wf` ist das bereits in `_read_active_workflow()` geladene Dict; der Ist-Verdict
steht darin unter `adversary_verdict`.

### 5. Symlink-Drift-Cleanup

Der `.active`-Symlink ist als Auflösungsquelle abgeschaltet. Reste entfernen:

- **`edit_gate.py:~199`** — `loc_delta_current` wird derzeit über den Symlink
  geschrieben. Stattdessen direkt in `wf_dir / f"{name}.json"` schreiben
  (`name` aus `get_active_workflow_name()`). Kein Symlink mehr.
- **`bash_gate.py:~146`** — toten `.active`-Lesepfad entfernen.
- **`post_bash.py:~79`** — `.active`-Fallback entfernen, nur noch
  `get_active_workflow_name()`.
- **`phase_listener.py:~86`** — `.active`-Fallback entfernen; Docstring (Zeile
  ~73-77) korrigieren, der noch "2. .active symlink (single-session default)"
  behauptet.

Damit gilt für **alle** Hooks dieselbe Auflösungsregel wie in `workflow.py`.

### 6. Was NICHT geändert wird (bewusst, OUT of scope)

- Die Workflow-Auflösungs-**Logik** selbst (env → settings) ist korrekt und bleibt.
- `migrate_state.py` schreibt `.active` weiterhin (v2→v3-Migration) — das ist ein
  Einmal-Migrationsschritt, kein Auflösungspfad, und bleibt unberührt.
- `gregor_zwanzig`-Config (`GZ_ACTIVE_WORKFLOW` → `OPENSPEC_ACTIVE_WORKFLOW`):
  separate MQ-Nachricht an die gregor-Instanz, kein Framework-Code.

## Expected Behavior

- **Edit blockiert, kein aktiver Workflow** → Meldung endet mit
  `[wf=— (none) | token=keins]` → Auflösungsquelle sofort sichtbar.
- **Edit blockiert in falscher Phase** → Meldung endet mit
  `[wf=feature-x (env) | token=keins | phase=phase3_spec]`.
- **Edit blockiert wegen LoC** → `[wf=feature-x (env) | token=keins | phase=phase6_implement | delta=+312 | limit=250]`.
- **Workflow nur in settings.local.json (Env-Var fehlt)** → `source=settings`
  macht den klassischen Stale-Env-Mismatch sichtbar.
- **Gültiger Override-Token vorhanden** → `token=gültig` (erklärt, falls trotzdem
  geblockt wird, dass das Gate token-unabhängig ist).
- **Commit blockiert, kein VERIFIED-Verdict** → `[wf=… | … | verdict=keins]`.

## Error Handling

- `gate_diagnostics()` wirft **nie** — jede nicht ermittelbare Teilinfo wird `?`.
  Ein Diagnose-Suffix darf einen ohnehin blockierenden Gate nie crashen lassen.
- `override_token`-Import schlägt fehl → `token=?`, kein Crash.
- `settings.local.json` defekt → `source=none` (wie bisher), kein Crash.

## Acceptance Criteria

- **AC-1:** Given kein aktiver Workflow (Env-Var + settings leer) / When edit_gate blockt mit "No active workflow" / Then Meldung enthält `[wf=— (none) | token=keins]`.
- **AC-2:** Given aktiver Workflow in phase3_spec / When edit_gate einen Code-Edit blockt / Then Meldung enthält Workflow-Name, `source`, `token`-Status und `phase=phase3_spec`.
- **AC-3:** Given LoC-Delta über Limit / When edit_gate blockt / Then Meldung enthält `delta=+N` und `limit=M`.
- **AC-4:** Given Workflow nur in settings.local.json (keine Env-Var) / When `resolve_active_workflow()` läuft / Then Rückgabe `(name, "settings")`.
- **AC-5:** Given `override_token` nicht importierbar (simuliert) / When `gate_diagnostics()` läuft / Then Rückgabe enthält `token=?` und wirft nicht.
- **AC-6:** Given irgendein Hook löst den aktiven Workflow auf / When kein `.active`-Symlink existiert / Then Auflösung funktioniert allein über Env-Var/settings (kein Hook liest mehr den Symlink).
- **AC-7:** Given `get_active_workflow_name()` (bestehende Aufrufer) / When aufgerufen / Then identisches Verhalten wie vorher (reiner Name-String).

## Test Plan

```bash
# AC-4 + AC-7: Auflösung mit Quelle
unset OPENSPEC_ACTIVE_WORKFLOW
python3 -c "import sys; sys.path.insert(0,'core/hooks'); \
import hook_utils as h; print(h.resolve_active_workflow()); print(repr(h.get_active_workflow_name()))"

# AC-1/AC-2: Diagnose-Suffix
OPENSPEC_ACTIVE_WORKFLOW=demo python3 -c "import sys; sys.path.insert(0,'core/hooks'); \
import hook_utils as h; print(h.gate_diagnostics({'current_phase':'phase3_spec'}))"

# AC-3: LoC mit Delta/Limit
python3 -c "import sys; sys.path.insert(0,'core/hooks'); \
import hook_utils as h; print(h.gate_diagnostics({'current_phase':'phase6_implement'}, delta='+312', limit=250))"

# AC-5: Token-Import-Fehler (Suffix bleibt robust) — via Monkeypatch im pytest
# AC-6: grep darf keine .active-Lesepfade mehr in den vier Hooks finden
! grep -n '"\.active"\|/ ".active"' core/hooks/edit_gate.py core/hooks/bash_gate.py \
    core/hooks/post_bash.py core/hooks/phase_listener.py

# End-to-End: echten Block provozieren und Suffix in stderr prüfen (pytest)
```

TDD-Artefakte (phase5): pytest-Datei `tests/test_selfexplaining_gates.py` mit
AC-1…AC-7, zuerst RED (gate_diagnostics existiert noch nicht).

## Changelog

- 2026-06-22: Initial spec erstellt (Auslöser: 1,9-Mio-Token-Verschwendung in gregor_zwanzig)
