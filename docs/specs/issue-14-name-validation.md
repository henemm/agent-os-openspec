---
entity_id: issue_14_name_validation
type: bug
created: 2026-06-29
updated: 2026-06-29
status: draft
version: "1.0"
tags: [security, validation, test-coverage, workflow, scope-guard]
test_targets:
  - core/hooks/workflow.py
  - core/hooks/edit_gate.py
  - core/hooks/bash_gate.py
  - core/hooks/config_loader.py
  - tests/test_workflow_name_validation.py
  - tests/test_gate_coverage.py
---

# Issue #14: Workflow-Namen-Validierung + fehlende Testabdeckung

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** https://github.com/henemm/agent-os-openspec/issues/14

## Purpose

Zwei Lücken schließen, die bei der Plugin-Migration entstanden sind:

1. **Sicherheit:** Workflow-Namen fließen unvalidiert in Dateipfade und Glob-Ausdrücke. Ein Name wie `../../etc/x` traversiert außerhalb des Workflows-Verzeichnisses. Ein Name mit `*` verfälscht Log-Datei-Suchen.

2. **Testabdeckung:** 8 Testklassen aus gregor_zwanzig wurden bei der Migration gelöscht, ohne gleichwertige Tests hier anzulegen. Der Code lebt jetzt in diesem Plugin — die Tests müssen hier existieren.

## Abhängigkeiten

| Komponente | Typ | Abhängigkeit |
|-----------|-----|-------------|
| `workflow.py` | Fix + Feature | `_validate_name()` hinzufügen; `cmd_status()` um Override-Anzeige erweitern |
| `edit_gate.py` | Fix | `_check_acceptance_criteria()` um Längencheck + Legacy-Stichtag erweitern |
| `config_loader.py` | Feature | `get_scope_loc_config()` als saubere API hinzufügen |
| `tests/test_workflow_name_validation.py` | Neu | Tests für Namensvalidierung + AMBIGUOUS-Block |
| `tests/test_gate_coverage.py` | Neu | Tests für AC-Format, LoC-Delta, Docs-Durchlass, Config-API, Status-Anzeige |

## Implementierungsdetails

### 1. `_validate_name()` in `workflow.py`

Whitelist-Regex: nur `[a-zA-Z0-9_-]`, Länge 1–64 Zeichen. Ablehnung bei `/`, `..`, Glob-Metazeichen (`*`, `?`, `[`, `]`, `{`, `}`).

```python
import re as _re

_NAME_RE = _re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

def _validate_name(name: str) -> None:
    """Reject names that would escape the workflows dir or corrupt glob patterns."""
    if not _NAME_RE.fullmatch(name):
        print(
            f"INVALID workflow name: {name!r}\n"
            "Allowed: letters, digits, hyphens, underscores (1–64 chars).\n"
            "Rejected: / .. * ? [ ] { }",
            file=sys.stderr,
        )
        sys.exit(1)
```

Aufrufe: in `cmd_start()` nach dem Parsen von `name`, in `cmd_switch()` nach `name = args[0]`.

### 2. `cmd_status()` — Override-Anzeige in `workflow.py`

```python
# Bestehend:
loc_delta = data.get("loc_delta_current", "+0")
print(f"LoC Delta: {loc_delta}")

# Neu: Override-Limit anzeigen wenn gesetzt
loc_override = data.get("loc_limit_override")
if loc_override:
    print(f"LoC Delta: {loc_delta}/{loc_override} (override)")
else:
    print(f"LoC Delta: {loc_delta}")
```

### 3. `_check_acceptance_criteria()` in `edit_gate.py`

Zwei Ergänzungen:

**a) Längencheck:** Jeder `AC-N`-Eintrag muss ≥ 30 Zeichen Beschreibungstext haben (nach dem `AC-N:`-Prefix).

**b) Legacy-Stichtag:** Specs, die vor `ac_format_required_since` (aus config) erstellt wurden, werden durchgelassen. Stichtag wird aus `config_loader.get_ac_format_required_since()` gelesen (gibt `None` zurück, wenn nicht konfiguriert → kein Legacy-Check).

```python
def _check_acceptance_criteria(workflow: dict) -> str | None:
    spec_file = workflow.get("spec_file")
    if not spec_file:
        return None
    spec_path = _root / spec_file
    if not spec_path.exists():
        return None

    # Legacy-Stichtag: Spec-Erstelldatum vs. Konfiguration
    try:
        from config_loader import get_ac_format_required_since
        cutoff = get_ac_format_required_since()
        if cutoff:
            import stat as _stat
            mtime = spec_path.stat().st_mtime
            from datetime import datetime, timezone
            created_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
            cutoff_dt = datetime.fromisoformat(cutoff).replace(tzinfo=timezone.utc)
            if created_dt < cutoff_dt:
                return None  # Legacy-Spec: durchlassen
    except Exception:
        pass  # Kein Cutoff konfiguriert oder Fehler → normaler Check

    content = spec_path.read_text()
    if "## Acceptance Criteria" not in content:
        return ("BLOCKED: Spec missing '## Acceptance Criteria' section. "
                "Add AC-1, AC-2, ... entries before implementing.")
    if not re.search(r"\bAC-\d+", content):
        return ("BLOCKED: '## Acceptance Criteria' has no AC-N entries. "
                "Format: '- **AC-1:** Given ... / When ... / Then ...'")

    # Längencheck: jeder AC-Eintrag ≥ 30 Zeichen Beschreibungstext
    for m in re.finditer(r'\bAC-\d+[:\s]+(.*)', content):
        desc = m.group(1).strip()
        if len(desc) < 30:
            return (
                f"BLOCKED: AC entry too short ({len(desc)} chars): '{desc[:50]}...'\n"
                "Each AC must have ≥ 30 chars of description text."
            )
    return None
```

### 4. `get_scope_loc_config()` in `config_loader.py`

```python
def get_scope_loc_config() -> tuple[int, list[str]]:
    """Return (max_loc_delta, loc_exclude_patterns) from config.

    Defaults: (250, []) when scope_guard section is absent.
    """
    cfg = load_config()
    scope = cfg.get("scope_guard", {})
    max_loc = int(scope.get("max_loc_delta", 250))
    excludes = list(scope.get("loc_exclude_patterns", []))
    return max_loc, excludes
```

`edit_gate._check_loc_delta()` nutzt diese Funktion statt direktem Config-Zugriff:

```python
from config_loader import get_scope_loc_config
max_loc, exclude_patterns = get_scope_loc_config()
```

## Expected Behavior

### Namensvalidierung
- **Input:** `workflow.py start "../../etc/x"` → Exit 1, Fehlermeldung
- **Input:** `workflow.py start "feat*glob"` → Exit 1, Fehlermeldung
- **Input:** `workflow.py start "my-feature-01"` → Workflow angelegt (Exit 0)

### AC-Format
- **Input:** Spec mit `AC-1: ok` (3 Zeichen) → BLOCKED (zu kurz)
- **Input:** Spec mit `AC-1: Given X / When Y / Then Z expected` (≥ 30 Zeichen) → kein Block
- **Input:** Legacy-Spec (Erstelldatum < Stichtag) → kein Block unabhängig von AC-Länge

### LoC-Delta Status
- **Input:** `loc_limit_override=500`, `loc_delta_current=+312` → Ausgabe: `LoC Delta: +312/500 (override)`
- **Input:** kein Override → Ausgabe: `LoC Delta: +312`

### AMBIGUOUS-Block
- **Input:** `adversary_verdict=AMBIGUOUS`, kein Override → `git commit` geblockt
- **Input:** `adversary_verdict=AMBIGUOUS` + gültiger Override-Token → `git commit` erlaubt
- **Input:** `adversary_verdict=AMBIGUOUS` + abgelaufener Token → `git commit` geblockt
- **Input:** `adversary_verdict=VERIFIED` → `git commit` erlaubt

## Acceptance Criteria

- **AC-1:** Given `workflow.py start "../../etc/x"` / When Ausführung / Then Exit 1, Meldung enthält "INVALID workflow name"
- **AC-2:** Given `workflow.py start "feat*"` / When Ausführung / Then Exit 1, Meldung enthält "INVALID workflow name"
- **AC-3:** Given `workflow.py start "valid-name-01"` / When Ausführung / Then Exit 0, Workflow-JSON angelegt
- **AC-4:** Given `workflow.py switch "../../x"` / When Ausführung / Then Exit 1 (auch switch validiert)
- **AC-5:** Given Spec mit AC-Einträgen < 30 Zeichen / When `edit_gate` in phase6 / Then BLOCKED mit Längenangabe
- **AC-6:** Given Spec erstellt vor ac_format_required_since / When `edit_gate` in phase6 / Then kein Block (Legacy)
- **AC-7:** Given `loc_limit_override=500` in Workflow-State / When `workflow.py status` / Then Ausgabe enthält "/500 (override)"
- **AC-8:** Given `adversary_verdict=AMBIGUOUS` ohne Override / When `git commit` / Then BLOCKED
- **AC-9:** Given `adversary_verdict=AMBIGUOUS` + gültiger Token / When `git commit` / Then kein Block
- **AC-10:** Given `get_scope_loc_config()` ohne openspec.yaml / When Aufruf / Then returns (250, [])
- **AC-11:** Given `get_scope_loc_config()` mit `max_loc_delta: 400` in openspec.yaml / When Aufruf / Then returns (400, ...)
- **AC-12:** Given `edit_gate` + `docs/specs/foo.md`-Edit + LoC > Limit / When Ausführung / Then kein Block (ALWAYS_ALLOWED_PATTERNS)

## Test Plan

**Datei 1: `tests/test_workflow_name_validation.py`**

```
TestValidateName (6 Tests):
  - Traversal-Name wird abgelehnt (../../etc)
  - Glob-Metazeichen werden abgelehnt (*)
  - Gültige Namen werden akzeptiert (my-feature, FEAT_001)
  - Leerer Name wird abgelehnt
  - Zu langer Name (>64 Zeichen) wird abgelehnt
  - cmd_start() ruft _validate_name() auf (Subprocess-Test)

TestAmbiguousBlock (4 Tests):
  - AMBIGUOUS ohne Override → blockt
  - AMBIGUOUS + gültiger Token → lässt durch
  - AMBIGUOUS + abgelaufener Token → blockt wieder
  - VERIFIED/BROKEN/None → blocken nie (nur AMBIGUOUS hat die Logik)
```

**Datei 2: `tests/test_gate_coverage.py`**

```
TestSpecAcFormat (7 Tests):
  - Kein Acceptance-Criteria-Abschnitt → BLOCKED
  - Abschnitt vorhanden, kein AC-N → BLOCKED
  - AC-N vorhanden, Beschreibung < 30 Zeichen → BLOCKED
  - AC-N vorhanden, Beschreibung ≥ 30 Zeichen → kein Block
  - Mehrere ACs: einer < 30 Zeichen → BLOCKED
  - Legacy-Spec (Erstelldatum < Stichtag) → kein Block
  - Stichtag nicht konfiguriert → normaler Check greift

TestEditGateLive (2 Subprocess-Tests):
  - Phase-6-Edit auf Spec ohne AC → blockt (Exit 2)
  - Edit auf docs/specs/foo.md → nicht geblockt (ALWAYS_ALLOWED)

TestGetLocDelta (6 Tests):
  - Zählt eingefügte + gelöschte Zeilen korrekt
  - Schließt .po-Dateien aus (loc_exclude_patterns)
  - Schließt Binärdateien aus (- - filename)
  - Kein git-Repo → fail-soft (kein Block)
  - Timeout → fail-soft (kein Block)
  - Delta = 0 → kein Block

TestCheckLocDelta (4 Tests):
  - Delta > Limit → BLOCKED mit Delta und Limit in Meldung
  - loc_limit_override im State hebt Limit auf
  - Delta < Limit → kein Block
  - E2E via Subprocess: edit_gate.py blockt bei Delta > 250

TestScopeConfig (2 Tests):
  - Ohne openspec.yaml → (250, [])
  - Mit max_loc_delta: 400 und loc_exclude_patterns → (400, [...])

TestStatusLocOverride (1 Test):
  - workflow.py status zeigt "/500 (override)" bei loc_limit_override=500
```

## Changelog

- 2026-06-29: Initial spec erstellt (Issue #14)
