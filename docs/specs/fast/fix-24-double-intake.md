# Mini-Spec: Fix #24 — 2x /00-intake im Command-Menü

## Was ändert sich
- `skills/00-intake/SKILL.md` und `skills/90-retro/SKILL.md` neu anlegen (fehlten seit der v3.2-Plugin-Migration; core/commands/00-intake.md und 90-retro.md wurden nie zu Skills migriert)
- `migrate_to_plugin.py`: neue Funktion `_find_removable_command_files()` + Migrations-Schritt, der `.claude/commands/*.md`-Dateien entfernt, die einen gleichnamigen Plugin-Skill haben (Duplikat-Ursache)
- Cleanup der Altlasten: `~/.claude/commands/*.md` (global, 16 Dateien) und `/home/hem/gregor_zwanzig/.claude/commands/00-intake.md` + `90-retro.md` (projekt-lokal) löschen — `e2e-verify.md` und `README.md` in gregor_zwanzig bleiben unangetastet (keine Plugin-Skill-Entsprechung)
- CHANGELOG.md unter [Unreleased] eintragen

## Was darf sich nicht ändern
- Keine anderen Skills/Commands anfassen
- `e2e-verify.md`/`README.md` in gregor_zwanzig bleiben erhalten
- Kein Löschen von Dateien ohne exakte Namens-Übereinstimmung mit einem Plugin-Skill

## Manuelle Test-Schritte
1. `skills/00-intake/` und `skills/90-retro/` existieren mit valider SKILL.md (Frontmatter + Inhalt)
2. `python3 migrate_to_plugin.py /home/hem/gregor_zwanzig` (Dry-Run) zeigt `00-intake.md` und `90-retro.md` als entfernbar, aber NICHT `e2e-verify.md`/`README.md`
3. Nach `--apply`: Dateien in gregor_zwanzig und global gelöscht, Slash-Command-Menü zeigt `/00-intake` nur noch 1x

## Inline-Test (wird während Implementierung geschrieben)
- [ ] `migrate_to_plugin.py` Dry-Run-Test: `_find_removable_command_files()` liefert exakt die erwarteten Dateien für ein Test-Projekt mit gemischtem `.claude/commands/`-Inhalt
