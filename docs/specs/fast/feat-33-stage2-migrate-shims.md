# Mini-Spec: feat-33-stage2-migrate-shims (Stufe 2 von Issue #33)

## Problem
`migrate_to_plugin.py --apply` hat zwei Lücken, die Stufe 3 (Kopien-Entfernung in
Consumer-Projekten) unsicher machen:

1. **6 Framework-Dateien fehlen in `CORE_HOOKS`** und bleiben nach `--apply` als
   tote Kopien liegen: `claude_md_protection.py`, `edit_verify.py`,
   `post_implementation_gate.py`, `secrets_guard.py`, `tdd_enforcement.py`,
   `worktree_write_guard.py`.
2. **`hook_utils.py` und `config_loader.py` würden blind gelöscht**, obwohl
   projekteigene Hooks sie importieren (verifiziert in gregor_zwanzig:
   `renderer_mail_gate.py:38` — ein registrierter PreToolUse-Bash-Hook! — sowie
   `track_token_usage.py`, `plan_validator.py` u.a.). Löschen würde dort **jede
   Bash-Ausführung brechen**.

## Was ändert sich (`migrate_to_plugin.py`)

1. `CORE_HOOKS` wird um die 6 fehlenden Dateien ergänzt.
2. Neue Kategorie `SHIM_HOOKS = {"hook_utils.py", "config_loader.py"}`: Diese werden
   bei `--apply` NICHT gelöscht, sondern durch einen **dünnen Shim** ersetzt, der
   das echte Modul aus der installierten Plugin-Version lädt und alle öffentlichen
   Attribute re-exportiert:
   - Erste Zeile Marker: `# openspec-shim: resolves to installed plugin version`
   - Auflösung des Plugin-Pfads via `~/.claude/plugins/installed_plugins.json`
     (gleiche Logik wie das Skill-Snippet aus Stufe 1: Key `agent-os-openspec@*`,
     user-scope bevorzugt, Existenz-Check)
   - Laden via `importlib.util.spec_from_file_location`, dann
     `globals().update(...)` — funktioniert für `import hook_utils` UND
     `from hook_utils import X`
   - Wenn das Plugin nicht auflösbar ist: `ImportError` mit klarer Meldung
     ("agent-os-openspec plugin not installed — install it or restore local hooks")
     statt stillem Fehlverhalten
3. Idempotenz: Läuft `--apply` erneut, werden vorhandene Shims (Marker in erster
   Zeile) erkannt und unverändert gelassen (kein Doppel-Shim, kein Löschen).
4. Dry-Run-Ausgabe listet die Shim-Ersetzungen als eigene Kategorie
   ("will be replaced by plugin shim").

Zusätzlich: `CHANGELOG.md`-Eintrag, Version 3.7.0 → 3.8.0 (MINOR, neue Fähigkeit).

## Was darf sich nicht ändern
- Verhalten OHNE `--apply` (Dry-Run) bleibt read-only.
- Die bestehende Command-Datei-Bereinigung (Alias-Marker-Logik aus #24/3.5.0)
  bleibt unverändert.
- Projektspezifische Hooks (nicht in CORE_HOOKS/MODULE_HOOKS/SHIM_HOOKS) werden
  weiterhin nie angefasst.

## Manuelle Test-Schritte
1. Dry-Run gegen gregor_zwanzig: listet 12+6 entfernbare Dateien + 2 Shim-Kandidaten,
   ändert nichts.
2. (Stufe 3, separater Schritt — hier NICHT ausführen.)

## Inline-Tests (werden während Implementierung geschrieben)
- [ ] Fixture: tmp-Projekt mit Framework-Kopien + einem projekteigenen Hook, der
      `import hook_utils` nutzt; Fake-HOME mit installed_plugins.json auf ein
      Fake-Plugin-Verzeichnis mit echtem `hook_utils.py`-Inhalt.
- [ ] `--apply` entfernt alle 18 CORE_HOOKS-Dateien, ersetzt die 2 SHIM_HOOKS durch
      Shims (Marker vorhanden), lässt den projekteigenen Hook liegen.
- [ ] Der projekteigene Hook läuft NACH der Migration erfolgreich (Subprozess mit
      Fake-HOME, importiert via Shim aus dem Fake-Plugin).
- [ ] Zweiter `--apply`-Lauf: idempotent (Shims unverändert, keine Fehler).
- [ ] Plugin nicht installiert (leeres Fake-HOME): Shim wirft ImportError mit
      klarer Meldung.
