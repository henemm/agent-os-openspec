---
entity_id: fix-134-approval-marker-binding
type: bugfix
created: 2026-09-30
updated: 2026-09-30
status: draft
version: "1.0"
tags: [post-implementation-gate, phase-listener, approval-marker, hash-binding]
test_targets: ["tests/test_post_implementation_gate_marker_binding.py"]
---

# post_implementation_gate: Freigabe-Marker an den Prüflauf binden statt an den Workflow-Namen (#134)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #134 — `post_implementation_gate`: Freigabe-Marker ist nur nach Workflow-Namen
  benannt — eine alte Freigabe entsperrt einen neuen Lauf.

## Purpose

`post_implementation_gate.py` verlangt nach 15 Minuten Implementierungszeit eine menschliche
Freigabe, bevor weitere Code-Edits erlaubt sind. Die Freigabe wird heute als leere Datei
`user_approved_validation_<workflow>` geschrieben und nur auf Existenz geprüft — ohne Bezug zum
konkreten Prüflauf. Ein Marker, der seinen Workflow überlebt (9 Belegexemplare im Arbeitsbaum,
siehe Issue), entsperrt jeden späteren Workflow desselben Namens beim allerersten Code-Edit, ohne
dass ein Mensch die neuen Änderungen gesehen hat. Diese Spec bindet den Marker an den `created`-
Zeitstempel des aktuell lebenden `pending_validation_<name>.json`-Locks — dasselbe Muster, das
#131 bereits für den Adversary-Dialog etabliert hat.

## Source

- **File:** `core/hooks/post_implementation_gate.py` — **Identifier:** `main()`, Zeile 136–139
  (Freigabe-Prüfung)
- **File:** `core/hooks/phase_listener.py` — **Identifier:** GREEN-Handler, Zeile 492–499
  (Marker-Erzeugung)
- **File:** `core/hooks/hook_utils.py` — **Identifier:** neu `pending_validation_lock_path`,
  `read_pending_validation_lock`, `approval_marker_path`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.log_gate_event` (über `block()` automatisch, sonst explizit) | function | Ablehnung eines Markers nachvollziehbar machen (AC-5) |
| `hook_utils.find_project_root` | function | Unverändert genutzt für Lock-/Marker-Pfade |
| `hook_utils.framework_disabled` | function | Unverändert — Bypass ohne Workflow bleibt bestehen |
| Muster aus #131 (`adversary_dialog.py`, Hash-/Identitätsbindung statt Alters-Prüfung) | prior art | Vorlage für diesen Fix |

## Scope

- **Affected Files:**
  - Code: `core/hooks/post_implementation_gate.py`, `core/hooks/phase_listener.py`,
    `core/hooks/hook_utils.py`
  - Tests: `tests/test_post_implementation_gate_marker_binding.py` (neu — erste Testdatei für
    dieses Modul)
  - Doku: `CHANGELOG.md` (Abschnitt `[Unreleased]`) — Routine-Pflicht, zählt nicht gegen das
    4-Dateien-Scope-Limit der Code-/Testdateien
- **Estimated Changes:** ~+90/−10 LoC (Großteil in der neuen Testdatei)

## Implementation Details

**1. `hook_utils.py` — drei kleine, gemeinsam genutzte Helper** (ersetzen die bisherigen privaten
Funktionen `_lock_path`/`_read_lock`/`_approval_path` aus `post_implementation_gate.py`, damit
`phase_listener.py` sie nicht dupliziert oder aus einem fremden Modul importiert):

```python
def pending_validation_lock_path(project_root: Path, wf_name: str) -> Path:
    return project_root / ".claude" / f"pending_validation_{wf_name}.json"

def read_pending_validation_lock(lock_path: Path) -> "dict | None":
    if not lock_path.exists():
        return None
    try:
        return json.loads(lock_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

def approval_marker_path(project_root: Path, wf_name: str) -> Path:
    return project_root / ".claude" / f"user_approved_validation_{wf_name}"
```

**2. `post_implementation_gate.py` — Inhaltsprüfung statt Existenzprüfung.** Die privaten
Funktionsdefinitionen entfallen zugunsten eines Imports aus `hook_utils` (Aliase, damit alle
bestehenden Aufrufstellen unverändert bleiben:
`from hook_utils import pending_validation_lock_path as _lock_path, read_pending_validation_lock
as _read_lock, approval_marker_path as _approval_path, log_gate_event`). Die Prüfreihenfolge in
`main()` ändert sich:

```python
lock = _read_lock(lock_path)          # jetzt VOR der Marker-Prüfung gelesen

if approval_path.exists():
    try:
        marker_content = approval_path.read_text().strip()
    except OSError:
        marker_content = None

    if lock is not None and marker_content == str(lock.get("created")):
        # Freigabe passt exakt zum aktuell lebenden Prüflauf
        _clear_lock(lock_path, approval_path)
        allow()
    elif lock is None:
        # Marker überlebte seinen Workflow (Kern von #134) — verwerfen,
        # NICHT als Freigabe werten. Faellt unten in den "kein Lock"-Zweig.
        approval_path.unlink(missing_ok=True)
        log_gate_event(
            "post_implementation_gate", "Edit",
            f"Verworfener Freigabe-Marker ohne aktiven Pruflauf-Lock (Workflow: {wf_name}).",
        )
    else:
        # Marker existiert, passt aber zu einem anderen (aelteren) Lauf
        approval_path.unlink(missing_ok=True)
        block(
            f"BLOCKED [post_implementation_gate]: Freigabe-Marker passt nicht zum aktuellen "
            f"Pruflauf (Workflow: {wf_name}).\n"
            f"  Der Marker stammt von einem frueheren Lauf und gilt nicht mehr.\n"
            f"  Neue Freigabe noetig: User tippt 'go', 'freigabe' oder 'approved'."
        )

if lock is None:
    _write_lock(lock_path, wf_name)
    allow()

# ... Batch-Fenster-Logik unverändert (nutzt weiterhin `lock`)
```

Round-Trip-Sicherheit: `created` ist `time.time()` (float). Sowohl Schreiben (`str(lock["created"])`
in `phase_listener.py`) als auch Lesen (`str(lock.get("created"))` hier) laufen über denselben
`json.loads` → `str(float)`-Pfad — Python garantiert dafür verlustfreies Round-Tripping.

**3. `phase_listener.py` — GREEN-Handler schreibt den Lock-Zeitstempel, nicht mehr `touch()`.**

```python
try:
    lock_path = pending_validation_lock_path(_root, wf_data['name'])
    lock = read_pending_validation_lock(lock_path)
    if lock is not None and "created" in lock:
        approval_path = approval_marker_path(_root, wf_data['name'])
        approval_path.parent.mkdir(parents=True, exist_ok=True)
        approval_path.write_text(str(lock["created"]))
        print(f"Post-implementation gate entsperrt für '{wf_data['name']}'.", file=sys.stderr)
    # Kein Lock vorhanden (Freigabe vor dem ersten Edit) → bewusst KEIN Marker,
    # fail-closed statt Sonderfall auf der Lese-Seite (#134 Risiko-Notiz).
except OSError:
    pass
```

Import-Zeile ergänzt um `pending_validation_lock_path, read_pending_validation_lock,
approval_marker_path` aus `hook_utils`.

**4. Docstring in `post_implementation_gate.py`** (Zeile 22–23) wird von "Marker, leer" auf
"Marker, Inhalt = `created`-Zeitstempel des Locks zum Zeitpunkt der Freigabe" korrigiert.

## Expected Behavior

- **Input:** Vorhandensein und Inhalt von `.claude/user_approved_validation_<name>` sowie
  Vorhandensein und `created`-Feld von `.claude/pending_validation_<name>.json`.
- **Output:** `post_implementation_gate.py`: Exit 0 (erlaubt) oder Exit 2 (`BLOCKED: ...`).
  `phase_listener.py`: unverändert Exit 0, Seiteneffekt ist der Marker-Inhalt.
- **Side effects:** Marker- und Lock-Datei werden bei passender Freigabe gelöscht (wie bisher);
  bei verworfenem Marker wird nur der Marker gelöscht, der (fehlende) Lock bleibt unangetastet;
  jede Ablehnung eines Markers erzeugt einen Eintrag in `.claude/gate-events.jsonl`.

## Error Handling

- Marker existiert, ist aber nicht lesbar (`OSError`, z. B. Berechtigungsproblem) → wie ein
  Mismatch behandelt: verwerfen und blockieren (fail-closed), kein Absturz.
- `pending_validation_<name>.json` existiert, ist aber kein valides JSON → `read_pending_validation_lock`
  liefert `None` (vorbestehendes Verhalten, unverändert) → Marker-Prüfung nimmt denselben Zweig
  wie "kein Lock" (AC-2).
- Schreibfehler beim Anlegen des Markers in `phase_listener.py` (`OSError`) → wie bisher still
  abgefangen; GREEN-Freigabe selbst bleibt wirksam (`green_approved` im State), nur das Gate
  entsperrt sich beim nächsten Edit nicht automatisch — Nutzer sieht dann die reguläre
  Blockade-Meldung erneut.

## Known Limitations

- Zwei parallele Workflows mit identischem Namen kann es laut Architektur ohnehin nicht geben
  (ein Name ist immer nur einmal gleichzeitig aktiv) — der Fix behandelt daher nur den
  sequenziellen Wiederverwendungsfall (altes Workflow-Ende, neuer Start, gleicher Name).
- Das begleitende Hygiene-Thema aus Issue #134 ("9 Marker liegen dauerhaft im Arbeitsbaum, weil
  sie in `.gitignore` fehlen und `cmd_cleanup_stale_locks` sie nicht erreicht") ist **nicht**
  Teil dieses Fixes — die Marker dürfen liegen bleiben, sie wirken nur nicht mehr fälschlich.
  Eigenständiges Folge-Issue laut Kontext-Dokument.
- Ein bewusst manipulierter Marker (Inhalt von Hand auf den aktuellen `created`-Wert gesetzt)
  besteht die Prüfung weiterhin — `bash_gate.py`s Tier-2-Schutz (blockt das Anlegen der
  Marker-Datei per Bash am Dateinamen) bleibt die einzige Verteidigung gegen diesen Fall und ist
  von diesem Fix unverändert.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Marker aus einem abgeschlossenen Workflow entsperrt einen neu gestarteten Workflow
      gleichen Namens **nicht mehr** beim ersten Code-Edit (Kern-Reproduktion aus #134)
- [ ] Der reguläre Freigabe-Weg (User sagt "go"/"approved" im Batch-Fenster) funktioniert
      weiterhin ohne Zusatzschritt
- [ ] Jede Ablehnung eines Markers erzeugt einen Eintrag in `.claude/gate-events.jsonl`
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein `user_approved_validation_<name>`-Marker, dessen Inhalt nicht zum
  `created`-Wert des aktuellen `pending_validation_<name>.json` passt (z. B. Marker eines
  früheren, bereits ersetzten Locks) / When ein Code-Edit in `phase6_implement` läuft / Then
  Exit 2, Marker wird gelöscht, Meldung verlangt eine neue Freigabe, Lock bleibt bestehen.
  - Test: `test_ac1_stale_marker_content_mismatch_blocks_and_discards`

- **AC-2:** Given ein Marker, zu dem kein `pending_validation_<name>.json` (mehr) existiert /
  When das Gate läuft / Then wird der Marker verworfen (gelöscht) statt als Freigabe gewertet;
  das Gate verhält sich wie beim allerersten Edit eines unbekannten Workflows (legt einen
  frischen Lock an, Exit 0).
  - Test: `test_ac2_marker_without_lock_discarded_and_treated_as_fresh`

- **AC-3:** Given eine echte Freigabe im laufenden Batch-Fenster — Marker-Inhalt entspricht
  exakt dem `created`-Wert des aktuell lebenden Locks / When der nächste Code-Edit kommt / Then
  Exit 0, Lock und Marker werden gelöscht — der reguläre Weg bleibt unverändert bedienbar.
  - Test: `test_ac3_matching_marker_clears_lock_and_allows`

- **AC-4:** Given ein alter Marker eines abgeschlossenen Workflows und ein neu gestarteter
  Workflow mit demselben Namen (noch kein eigener Lock) / When dessen erster Code-Edit kommt /
  Then greift das Gate wie bei einem unbekannten Workflow — **kein** automatisches Entsperren
  trotz des alten Markers. Das ist die Kern-Reproduktion aus #134.
  - Test: `test_ac4_reused_workflow_name_stale_marker_does_not_unlock_new_run`

- **AC-5:** Given ein durch AC-1 oder AC-2/AC-4 verworfener/abgelehnter Marker / When das Gate
  ihn verarbeitet / Then enthält `.claude/gate-events.jsonl` danach eine zusätzliche Zeile mit
  `hook == "post_implementation_gate"` und einer `reason`, die den jeweiligen Grund nennt
  (Mismatch bzw. "ohne aktiven Pruflauf-Lock").
  - Test: `test_ac5_rejected_marker_is_logged_to_gate_events` (Mismatch-Fall und Lock-loser Fall)

- **AC-6:** Given eine GREEN-Freigabe (User sagt "go"/"freigabe"/"approved") in
  `phase6_implement` oder `phase6b_adversary` **mit** einem aktuell existierenden
  `pending_validation_<name>.json` / When `phase_listener.py` die Nachricht verarbeitet / Then
  enthält der geschriebene Marker als Textinhalt genau den `created`-Wert dieses Locks (kein
  leerer Touch mehr).
  - Test: `test_ac6_green_approval_writes_lock_created_value_into_marker`

- **AC-7:** Given eine GREEN-Freigabe **ohne** existierenden `pending_validation_<name>.json`
  (seltener Randfall: Freigabe kommt, bevor der erste Edit einen Lock angelegt hat) / When
  `phase_listener.py` die Nachricht verarbeitet / Then wird **kein** Marker geschrieben
  (fail-closed) — `green_approved` im Workflow-State wird trotzdem gesetzt.
  - Test: `test_ac7_green_approval_without_lock_writes_no_marker`

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `python3 -m pytest tests/test_post_implementation_gate_marker_binding.py -q` (AC-1 bis AC-7,
  End-to-End über die echten Hook-Skripte als Subprozess, analog
  `tests/test_phase_listener_dropped_approval_90.py`)
- Regressionslauf: `python3 -m pytest tests/ -q`
- Drift-Checks: `python3 scripts/sync_skills.py --check`,
  `python3 scripts/ci_spec_gate.py --base origin/main`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Keine neue Architektur — dasselbe Bindungs-Muster wie #131 wird auf einen
  zweiten Marker-Typ angewendet. Eine Festlegung: die drei Helper (`pending_validation_lock_path`,
  `read_pending_validation_lock`, `approval_marker_path`) leben in `hook_utils.py`, nicht in
  `post_implementation_gate.py`, weil jetzt zwei Hooks (Schreiber `phase_listener.py`, Leser
  `post_implementation_gate.py`) exakt dasselbe Pfad-/Format-Verständnis brauchen — eine
  Divergenz zwischen den beiden würde die Lücke wieder öffnen. Geprüfte Alternative (in der
  Analyse verworfen): Freigabe-Status als Feld direkt in der Lock-Datei statt als zweite Datei —
  sauberer, aber `bash_gate.py`s Tier-2-Schutz müsste dann das Schreiben *innerhalb* der
  Lock-Datei absichern statt nur einen Dateinamen zu blocken; das fasst eine zweite,
  unabhängige Sicherheitsgrenze an und sprengt den Rahmen dieses Tickets.

## Changelog

- 2026-09-30: Initial spec created
