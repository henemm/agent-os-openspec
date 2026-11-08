# Context: fix-545-path-normalize

## Request Summary
Issue #545: Die Pfad-Sperren in `edit_gate.py` (und, wie sich zeigt, `bash_gate.py`) vergleichen
den rohen Pfad per Substring/Regex. Schreibweisen wie `.claude//settings.json` oder
`./.claude/./settings.json` treffen kein Muster und fallen danach durch eine Freigabe-Regel
(`.json` always-allowed). Ziel: Pfad vor dem Vergleich normalisieren, damit jede Schreibweise
dieselbe Sperre bzw. dieselbe #543-Ausnahme trifft.

Kontext und Analyse in einem Durchgang (Intake-Summe 3).

## Reproduktion (origin/main eab24f1, Wegwerf-Projekt, Write mit `disableAllHooks: true` bzw. `echo x > <pfad>`)

| Pfad | edit_gate | bash_gate |
|---|---|---|
| `.claude/settings.json` | 2 | 2 |
| `.claude//settings.json` | **0** | **0** |
| `./.claude/./settings.json` | **0** | **0** |
| `.claude/../.claude/settings.json` | 2 (Substring bleibt zufällig) | 2 |
| `.claude//settings.local.json` | **0** | (nicht geschützt) |
| `.claude/./active_workflow` | **0** | (nicht geschützt) |
| `.claude//workflows/x.json` | **0** | **0** |
| `./.claude/./workflows/x.json` | **0** | **0** |

Skript: Scratchpad `repro.py` (nicht im Repo); die Fälle werden RED-Tests.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/edit_gate.py:47` | `PROTECTED_STATE_FILES` — Schritt 1 (`if pf in file_path`, Z. ~920) gleiche Schwäche: Workflow-State (Phase/Verdict) per `.claude//workflows/<wf>.json` schreibbar |
| `core/hooks/edit_gate.py:57` | `ORCHESTRATOR_FILES` — Schritt 1b (`if of not in file_path`, Z. ~948), Kern von #545 |
| `core/hooks/edit_gate.py:~1018` | Schritt 4 Infrastruktur (`if infra in file_path`) — gleiche Schwäche für `.claude//hooks/x.py` (Override-Pflicht umgehbar; spätere Phase/TDD-Prüfungen greifen evtl. noch) |
| `core/hooks/edit_gate.py:~922-931` | Vorbild: Beleg-Prüfung (#447/#448) prüft `normpath` ODER `resolve()` |
| `core/hooks/edit_gate.py:~500-520` | `_settings_plugin_change_reason` (#543): lehnt unsaubere Pfade (`..`, `./`, `//`, abschl. `/`) bewusst ab → Grund „Pfad nicht eindeutig" |
| `core/hooks/bash_gate.py:57` | `PROTECTED_FILE_PATTERNS` (Regex auf rohe Tokens) |
| `core/hooks/bash_gate.py:1367-1402` | `_is_sensitive` / `_matches_file_token` — Token-Vergleich ohne Normalisierung; auch von Secrets-Prüfung (`_references_sensitive_file`) und Ordner-/Glob-Mustern genutzt |
| `core/hooks/bash_gate.py:297` | `_redirects_to_protected` — Umleitungsziel roh per `re.search` |
| `core/hooks/bash_gate.py:1059-1080` | Vorbild: `_proof_path_hit_one` prüft normpath ODER aufgelöst |
| `tests/test_edit_gate_settings_plugins_543.py:322-341` | `_UNCLEAN`-Liste: `{p}/.claude//settings.json` ist `xfail(strict, reason="#545")` → muss nach Fix als normaler Fall laufen (xfail entfernen) |
| `tests/test_edit_gate_orchestrator_files.py` | #48-Tests (Home-Ausnahme `~/.claude/...`, Override) — dürfen nicht regressieren |
| `tests/test_bash_gate_false_positives.py` | False-Positive-Schutz Bash-Gate (#53/#64) — darf nicht regressieren |

## Existing Patterns
- **normpath ODER resolve, nie nur einer** (ADR 2 in `docs/specs/feat-448-proof-lock-bypass.md`):
  nur `resolve()` verliert den Schutz, wenn ein Zustandsordner selbst ein Symlink ist; nur
  `normpath` übersieht Symlinks. Treffer, wenn eine der Varianten das Muster trifft — der rohe
  Pfad bleibt zusätzlich im Vergleich (Varianten vergrößern nur die Treffermenge).
- Ausnahmen (`try/except (OSError, RuntimeError, ValueError)`) um `resolve()`; Varianten, die
  nicht berechnet werden können, fallen weg, der rohe Vergleich bleibt.
- #48: Home-Ausnahme `~/.claude/...` arbeitet bereits auf dem aufgelösten Pfad.

## Dependencies
- Upstream: `os.path.normpath`, `os.path.expanduser`, `pathlib.Path.resolve`.
- Downstream: alle Konsumenten-Projekte (Hooks laufen in jedem Turn); die CI-Tests
  `tests/test_edit_gate_*`, `tests/test_bash_gate_*`.

## Existing Specs
- `docs/specs/infra/feat-543-settings-plugin-exception.md` — Plugin-Ausnahme, F003 unsaubere Pfade
- `docs/specs/feat-448-proof-lock-bypass.md` — Normalisierungs-Vorbild (ADR 2)
- `docs/specs/fix-407-ln-state-integrity.md`, `docs/specs/fix-410-state-integrity-gaps.md` — Bash-State-Integrity
- `docs/specs/fast/fix-48-49-gate-hermetic.md` — Orchestrator-Sperre, Home-Ausnahme

## Analyse / Lösungsrichtung
1. **edit_gate.py:** eine Hilfsfunktion liefert die Vergleichsvarianten eines `file_path`
   (roh, `normpath(expanduser)` mit `/`, aufgelöst). Schritte 1, 1b und 4 prüfen
   „Muster in irgendeiner Variante". Home-Ausnahme (#48) bleibt unverändert auf dem aufgelösten Pfad.
2. **#543-Ausnahme:** bleibt wie spezifiziert — unsaubere Schreibweisen bekommen sie nicht
   (fail-closed, F003) und werden jetzt mit dem Grund „Pfad nicht eindeutig" geblockt statt
   durchgewunken. Das ist mit dem Issue-AC „folgt der #543-Ausnahme" gemeint: dieselben
   Regeln für jede Schreibweise. Die saubere Schreibweise bleibt erlaubt. `xfail` in `_UNCLEAN` entfällt.
3. **bash_gate.py:** Tokens zusätzlich lexikalisch normalisiert (`normpath(expanduser)`) gegen
   die Muster prüfen (in `_matches_file_token` und `_redirects_to_protected`). Roh bleibt im
   Vergleich → nur mehr Treffer, keine neuen Lücken. Kein `resolve()` je Token in Bash (bestehende
   Symlinks auf `.claude` werden schon beim Anlegen per `ln` geblockt, #407) — als Known Limitation.

## Risks & Considerations
- **False Positives Bash:** mehr Treffer durch Normalisierung, z. B. `.claude/hooks/..` wird
  zu `.claude` (Zustandsordner-Token). Das ist inhaltlich korrekt (der Pfad IST `.claude`),
  aber neu. `tests/test_bash_gate_false_positives.py` muss grün bleiben.
- **Secrets:** `_matches_file_token` dient auch der Secrets-Prüfung — Normalisierung dort macht
  sie nur strenger (z. B. `cat ./config/./.env`).
- **Raw-Scan-Fallback** (`sh -c`, `eval`, kaputte Quotes): `normpath` auf ganzen Befehlsstring
  ist rein lexikalisch über `/`; zusätzlich zum Rohstring geprüft, nie stattdessen.
- **Fail-open-Charakter:** Ausnahmen in der Variantenberechnung dürfen nicht zum Absturz
  (Exit 1 = durchgelassen) führen — Varianten in `try` kapseln.
- **Infra-Schritt 4:** zusätzlich gefixt, sonst bleibt dieselbe Lücke eine Ebene tiefer.
- **Außerhalb des Umfangs:** `bash_gate.py` schützt `settings.local.json` und `active_workflow`
  gar nicht als Muster (bewusst schmaler, eigene Frage); `PROTECTED_STATE_FILES` in Bash deckt
  `.claude/workflows/*.json` ab. Kein neues Muster in diesem Fix.
- **Risiko-Stufe Adversary:** hoch (Gate-Code) → mind. 2 Dialog-Runden.
