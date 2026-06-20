---
entity_id: user_initiated_bug_workflow
type: feature
created: 2026-06-20
updated: 2026-06-20
status: draft
version: "1.0"
tags: [workflow, bugs, enforcement, token-efficiency]
test_targets:
  - core/hooks/phase_listener.py
  - core/hooks/workflow.py
---

# User-Initiated Bug Workflow

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** (noch nicht erstellt)

## Purpose

`workflow.py start --type bug` darf nur ausgeführt werden, wenn der User den
Bug-Workflow explizit angefordert hat — durch `/00-bug` oder eine gleichwertige
explizite Aussage. Claude darf den Fast-Track nicht eigenmächtig wählen.

Ohne diese Einschränkung kann Claude `--type bug` jederzeit selbst aufrufen
und damit alle schweren Phasen (Spec, TDD, Adversary) umgehen — auch für
Änderungen, die eigentlich einen Feature-Workflow bräuchten.

## Abhängigkeiten

| Komponente | Typ | Abhängigkeit |
|-----------|-----|-------------|
| `phase_listener.py` | Hook | Erkennt User-Initiierung, setzt Flag-Datei |
| `workflow.py` | CLI | Prüft Flag-Datei bei `--type bug`; löscht sie nach Verbrauch |

## Implementierungsdetails

### 1. Flag-Datei

```
.claude/bug_workflow_requested.json
{
  "created": "2026-06-20T10:30:00",
  "source": "/00-bug"          ← oder "user_phrase"
}
```

- Liegt in `.claude/` (kein Git-Tracking nötig, bereits in .gitignore via
  `settings.local.json`-Logik; alternativ explizit in .gitignore eintragen)
- TTL: **10 Minuten** — nach Ablauf gilt sie als nicht vorhanden
  (belegt durch sudo default 5 min, CIS-Benchmark max 15 min, OAuth state nonce 5 min)
- Wird von `workflow.py start --type bug` nach erfolgreicher Prüfung **atomar gelöscht**
  (rename in `.claude/bug_workflow_consumed.json` vor dem Lesen → TOCTOU-sicher)

### 2. `phase_listener.py` — Flag setzen

Neue Erkennung in `main()`, vor dem Workflow-Read:

```python
BUG_WORKFLOW_TRIGGER_PHRASES = [
    "/00-bug",
    "bug workflow", "bug-workflow",
    "fast track", "fast-track bug",
]

def _set_bug_workflow_flag(source: str) -> None:
    flag = _root / ".claude" / "bug_workflow_requested.json"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(json.dumps({"created": datetime.now().isoformat(), "source": source}))

# In main():
for phrase in BUG_WORKFLOW_TRIGGER_PHRASES:
    if phrase in message.lower():
        _set_bug_workflow_flag(phrase)
        print(f"Bug-Workflow angefordert. Starte mit: workflow.py start <name> --type bug",
              file=sys.stderr)
        break
```

Konfigurierbar via `openspec.yaml → bug_workflow.trigger_phrases`.

### 3. `workflow.py` — Flag prüfen und verbrauchen

In `cmd_start()`, nach dem `--type bug`-Parse:

```python
if workflow_type == "bug":
    flag_path = find_project_root() / ".claude" / "bug_workflow_requested.json"
    flag_valid = False
    consumed_path = find_project_root() / ".claude" / "bug_workflow_consumed.json"
    if flag_path.exists():
        try:
            # Atomic consume: rename first, then read — eliminates TOCTOU
            flag_path.rename(consumed_path)
            flag_data = json.loads(consumed_path.read_text())
            created = datetime.fromisoformat(flag_data["created"])
            age_min = (datetime.now() - created).total_seconds() / 60
            if age_min <= 10:
                flag_valid = True
            consumed_path.unlink(missing_ok=True)
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            pass
    if not flag_valid:
        print(
            "BLOCKED: Bug-Workflow muss vom User angefordert werden.\n"
            "Tippe /00-bug um den Bug-Analyse-Flow zu starten.",
            file=sys.stderr,
        )
        sys.exit(1)
```

### 4. Konfiguration in `openspec.yaml`

```yaml
bug_workflow:
  require_user_initiation: true   # false → kein Flag-Check (Opt-out für Teams)
  flag_ttl_minutes: 10
  trigger_phrases:
    - "/00-bug"
    - "bug workflow"
    - "fast track"
```

`require_user_initiation: false` als Opt-out für Projekte, die die Einschränkung
nicht wollen (z.B. reine Entwickler-Tools ohne Orchestrator-Pattern).

## Expected Behavior

- **Input:** User tippt `/00-bug` → Phase Listener setzt Flag → User startet
  `workflow.py start BUG-42 --type bug` → Flag vorhanden + frisch → Workflow
  startet, Flag wird gelöscht
- **Block-Fall:** Claude ruft `workflow.py start X --type bug` ohne vorherige
  User-Initiierung auf → BLOCKED
- **TTL-Ablauf:** Flag älter als 30 min → BLOCKED (User muss erneut `/00-bug`
  tippen)
- **Opt-out:** `require_user_initiation: false` → kein Flag-Check

## Architektur-Notiz: Warum keine Env-Var

Die naheliegende Alternative wäre eine Env-Var (`OPENSPEC_BUG_INTENT_TS`), die
der Hook setzt und `workflow.py` liest. Das funktioniert in dieser Architektur
nicht: Hooks sind kurzlebige Subprozesse — `os.environ['X'] = ...` propagiert
nie zum Claude-Code-Elternprozess. Deshalb verwendet das Framework bereits
`settings.local.json` für `OPENSPEC_ACTIVE_WORKFLOW`. settings.local.json
überlebt jedoch Session-Neustarts, was dem Intent-Token-Prinzip widerspricht
(alter Intent = kein Intent). Die Datei mit TTL ist der korrekte Kompromiss.

## Error Handling

- Flag-Datei nicht lesbar (Permissions) → fail-open: Flag gilt als ungültig → BLOCKED
- `rename` schlägt fehl (z.B. Cross-Device) → OSError gefangen → Flag gilt als ungültig → BLOCKED
- `datetime`-Parse-Fehler im Flag → Flag gilt als ungültig → BLOCKED
- `require_user_initiation` nicht in Config → Default `true`

## Acceptance Criteria

- **AC-1:** Given User tippt `/00-bug` / When phase_listener läuft / Then `bug_workflow_requested.json` existiert mit `created` und `source: "/00-bug"`
- **AC-2:** Given Flag vorhanden + < 30 min alt / When `workflow.py start X --type bug` / Then Workflow startet, Flag wird gelöscht
- **AC-3:** Given kein Flag vorhanden / When `workflow.py start X --type bug` / Then BLOCKED mit Hinweis auf `/00-bug`
- **AC-4:** Given Flag > 30 min alt / When `workflow.py start X --type bug` / Then BLOCKED (TTL abgelaufen)
- **AC-5:** Given `require_user_initiation: false` in config / When `workflow.py start X --type bug` ohne Flag / Then Workflow startet (Opt-out aktiv)
- **AC-6:** Given User tippt "fast track bug" / When phase_listener läuft / Then Flag gesetzt (alternative Trigger-Phrase)

## Test Plan

```bash
# AC-1: Flag wird gesetzt
echo '{"user_message": "/00-bug"}' | python3 core/hooks/phase_listener.py
cat .claude/bug_workflow_requested.json  # → JSON mit created + source

# AC-2: Workflow startet mit gültigem Flag
echo '{"user_message": "/00-bug"}' | python3 core/hooks/phase_listener.py
python3 core/hooks/workflow.py start TEST-BUG-1 --type bug
# → Startet; Flag danach gelöscht: ls .claude/bug_workflow_requested.json → nicht gefunden

# AC-3: Kein Flag → BLOCKED
rm -f .claude/bug_workflow_requested.json
python3 core/hooks/workflow.py start TEST-BUG-2 --type bug
# → exit 1, BLOCKED-Meldung

# AC-4: Veraltetes Flag → BLOCKED
python3 -c "
import json; from datetime import datetime, timedelta
from pathlib import Path
p = Path('.claude/bug_workflow_requested.json')
p.write_text(json.dumps({'created': (datetime.now()-timedelta(minutes=31)).isoformat(), 'source': 'test'}))
"
python3 core/hooks/workflow.py start TEST-BUG-3 --type bug
# → exit 1, BLOCKED

# Cleanup
python3 core/hooks/workflow.py list | grep TEST-BUG && \
  rm -f .claude/workflows/TEST-BUG-*.json .claude/bug_workflow_requested.json
```

## Changelog

- 2026-06-20: Initial spec erstellt
