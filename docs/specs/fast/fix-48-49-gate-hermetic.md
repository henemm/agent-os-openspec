# Mini-Spec: fix-48-49-gate-hermetic

Zwei kleine Fixes, gebündelt (beide heute live aufgetreten, Ursachen verifiziert).

## Was ändert sich

**#48 — edit_gate ORCHESTRATOR_FILES-Sperre** (`core/hooks/edit_gate.py:55-59, 275-282`):
1. Der Substring-Match `if of in file_path` trifft fälschlich auch die GLOBALE
   User-Konfiguration `~/.claude/settings.json` (außerhalb jedes Projekts). Fix:
   Pfade unterhalb von `Path.home() / ".claude"` sind von der
   ORCHESTRATOR_FILES-Sperre ausgenommen (die Sperre schützt Projekt-Dateien vor
   Developer-Agenten, nicht die globale Claude-Konfiguration). Vorsicht: Projekte
   können unter `~/...` liegen — die Ausnahme gilt exakt für `~/.claude/...`,
   nicht für `~/irgendein-projekt/.claude/...`.
2. Der Block feuert vor der Override-Prüfung und ist damit nie überschreibbar —
   die Fehlermeldung empfiehlt zugleich einen Weg (update-config Skill), der
   identisch geblockt wird. Fix: Vor dem `block()` in Schritt 1b wird der
   User-Override-Token geprüft (gleiche Funktion, die die Infra-Sperre nutzt:
   `override_token.has_valid_token`) — bei gültigem Token wird die Datei
   freigegeben (Token wird dabei wie bei der Infra-Sperre konsumiert/behandelt,
   exakt deren bestehendem Muster folgen, siehe Schritt "Infrastructure file"
   im selben Hook).

**#49 — session_singleton_guard-Tests nicht hermetisch** (`tests/test_session_singleton_guard.py`):
`_do_guard()` liest echten Projekt-Zustand: `_has_override_token()` (heute live:
ein realer User-Override-Token ließ 3 Block-Tests fälschlich "allow" sehen) und
`_locks_dir()` via `find_project_root()`. Fix: Die betroffenen Tests (mind. die 3
Block-Tests `test_guard_edit/write/bash_blocked_in_main_repo`, plus Durchsicht
aller weiteren Tests der Datei auf dieselbe Lücke) mocken `_has_override_token`
auf `False` und lenken `_locks_dir` (bzw. `find_project_root`) auf `tmp_path` —
Muster analog zu den #35-Fixes. KEINE Änderung an
`core/hooks/session_singleton_guard.py` selbst (reines Test-Problem).

Zusätzlich: `CHANGELOG.md`-Eintrag, Version 3.8.0 → 3.8.1 (PATCH).

## Was darf sich nicht ändern
- #48: Projekt-lokale `.claude/settings.json`/`settings.local.json`/`active_workflow`
  bleiben ohne Override weiterhin gesperrt (Kern-Schutzfunktion unverändert).
- #48: Ohne gültigen Override-Token bleibt auch die globale Datei... NEIN —
  Korrektur: die globale `~/.claude/`-Ausnahme gilt IMMER (auch ohne Token),
  der Token-Bypass gilt für die Projekt-Dateien. Beide Mechanismen unabhängig.
- #49: Das Laufzeit-Verhalten des Guards ändert sich nicht (nur Tests).

## Manuelle Test-Schritte
1. Edit auf `~/.claude/settings.json` (via update-config-Kontext) → nicht mehr geblockt.
2. Edit auf Projekt-`.claude/settings.json` ohne Token → weiterhin geblockt;
   mit frischem "override" → erlaubt.
3. Testsuite mit existierendem echten Override-Token im Projekt → die 3
   Guard-Tests bleiben grün.

## Inline-Tests (werden während Implementierung geschrieben)
- [ ] edit_gate: globaler `~/.claude/settings.json`-Pfad wird nicht geblockt
      (hermetisch: HOME/Path.home gemockt).
- [ ] edit_gate: Projekt-`.claude/settings.json` ohne Token → Block (Bestand).
- [ ] edit_gate: Projekt-`.claude/settings.json` mit gültigem Token → erlaubt.
- [ ] Guard-Tests: mit künstlich vorhandenem Override-Token im echten Projekt-Root
      laufen die 3 Block-Tests weiterhin grün (Beweis der Hermetik).
