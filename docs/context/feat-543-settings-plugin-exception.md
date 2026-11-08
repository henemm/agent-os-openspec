# Context: feat-543-settings-plugin-exception (#543)

## Anfrage
Die projektlokale `.claude/settings.json` ist im Edit-Gate (`core/hooks/edit_gate.py`, Schritt 1b,
`ORCHESTRATOR_FILES`) komplett gesperrt. Die PO-Vorgabe vom 2026-11-08 verlangt aber, dass Plugins
und Marketplaces, die ein Repo braucht, in dessen `.claude/settings.json` stehen (Cloud-Sitzungen
laden sie nur von dort). Gewünscht ist eine enge Ausnahme nur für `enabledPlugins` und
`extraKnownMarketplaces`.

## Betroffener Code
- `core/hooks/edit_gate.py:55-60` — `ORCHESTRATOR_FILES` (`settings.json`, `settings.local.json`,
  `active_workflow`).
- `core/hooks/edit_gate.py:829-855` — Schritt 1b: Ausnahme `~/.claude/` (#48), Override-Token gibt
  frei, sonst Block mit Hinweis „update-config Skill verwenden" (der Skill läuft in dieselbe Sperre).
- `core/hooks/edit_gate.py:345-438` — vorhandene Simulation des neuen Dateiinhalts für den
  Spec-Freeze (`_simulate_spec_write`: Write/Edit/MultiEdit, inkl. Varianten beim leeren
  `new_string`, Zeitbudget, fail-closed). Wiederverwendbar für den Inhaltsvergleich.
- Nach 1b folgt für `.json` die Always-Allowed-Regel (Schritt 2) — fällt 1b nicht, wird die Datei
  ohnehin erlaubt. Die Ausnahme muss also nur den Block auslassen, nicht selbst freigeben.
- `tests/test_edit_gate_orchestrator_files.py` — bestehende hermetische Tests zu #48 (Fake-HOME,
  Fake-Projekt, Subprozess). Vorlage für die neuen Tests.

## Risiken
- `settings.json` steuert Hooks, Permissions, Env und `disableAllHooks` — jede Lücke im Vergleich
  wäre ein Gate-Bypass. Deshalb: Vergleich auf geparstem JSON, alle Schlüssel außer den zwei
  erlaubten müssen exakt gleich bleiben; jeder Zweifel (nicht lesbar, kaputtes JSON, doppelte
  Schlüssel, Symlink, Simulation scheitert) → Sperre wie bisher.
- `settings.local.json` und `active_workflow` bleiben unberührt gesperrt.

## Analyse (kurz, Summe 2)
Ein Datei-Change in `edit_gate.py` (~50 LoC) plus neue Tests. Bekanntes Muster (Simulation aus dem
Spec-Freeze). Keine neue Architektur, kein neuer Hook.
