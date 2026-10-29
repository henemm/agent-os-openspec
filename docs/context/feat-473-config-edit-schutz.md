# Context: feat-473-config-edit-schutz

## Request Summary
Issue #473 (Adversary-Fund F011 aus #470): Die wirksame Gate-Config ist nur gegen Bash-Schreibzugriffe geschützt (`bash_gate._writes_effective_config`, #410/#418), nicht gegen Edit/Write/MultiEdit; außerdem kann eine neue, vorrangige Config-Datei angelegt werden. Im Auto-Modus (#470) könnte ein Agent so `autonomy.mode: auto` setzen. Muss vor der Nutzung des Auto-Modus geschlossen sein.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/config_loader.py:35` | `CONFIG_NAMES = ["openspec.yaml", "config.yaml", ".openspec.yaml"]` |
| `core/hooks/config_loader.py:142` | `_find_config_file(root)`: Suchreihenfolge je Name erst `root/<name>` (Root-`config.yaml` ohne Plugin-Block wird übergangen, #372), dann `root/.claude/<name>` → 6 Kandidaten |
| `core/hooks/bash_gate.py:598` | `_writes_effective_config`: vergleicht Schreibziele nur mit der aktuell wirksamen Datei (`find_config_file(find_project_root())`, hook_utils-Wurzel); Worktree-Kopie bleibt frei; Ausweg Override-Token (Schritt 1b, :1741) |
| `core/hooks/edit_gate.py:~640-760` | Reihenfolge: Protected State (1) → Orchestrator-Files (1b, Override-Token) → outside project (1c) → Spec-Freeze (1d) → always-allowed dirs/patterns (2/2b, u. a. `.yaml`?) → kein Code (3) → Infra (4). Config-Schutz muss vor 1c/2/3 greifen, sonst winkt „kein Code“ YAML durch |
| `core/hooks/workflow.py` | `trusted_config()` (#470) — gleiche Wurzel |
| `tests/test_bash_gate_config_lock_418.py` | Muster für Config-Lock-Tests |

## Analysis
- Gemeinsame Funktion (z. B. `hook_utils.protected_config_paths(root)` oder in config_loader): Menge der geschützten Pfade unter der vertrauenswürdigen Wurzel `hook_utils.find_project_root()`:
  - die wirksame Datei (`find_config_file(root)`), falls vorhanden
  - jeder Kandidat, der in der Suchreihenfolge VOR der wirksamen Datei liegt (bzw. alle 6, wenn keine wirksame existiert) — Anlegen würde ihn wirksam machen
  - Ausnahme: existierende Root-`config.yaml`, die App-Config ist (#372, kein Plugin-Block) — bleibt frei, außer der neue Inhalt enthielte einen Plugin-Block (für Write prüfbar über `content`, für Edit über simulierten Inhalt; sonst fail-closed blocken)
- Vergleich über `resolve()` (Symlinks, `..`), Worktree-Kopien lösen auf andere Dateien → frei (Konsistenz mit #410)
- `edit_gate.py`: neuer Schritt direkt nach 1 (vor 1b/1c), Ausweg nur Override-Token (wie bash_gate 1b); Meldung analog
- `bash_gate.py`: `_writes_effective_config` auf dieselbe Pfadmenge erweitern (Anlegen vorrangiger Datei per Bash)
- `.claude/settings.local.json` bleibt frei (seit #470 im Auto-Pfad wirkungslos)
- Risiken: Fehlalarm bei App-`config.yaml` (#372); Framework-Repo selbst editiert `config.yaml` als Template — im Main-Repo nur mit Override (wie Bash heute), im Worktree frei; fail-closed vs. fail-open: Gate darf bei Fehler in der Pfadermittlung nicht alle Edits blocken → bei Exception nur den Config-Schritt überspringen? Entscheidung: fail-open wie bash_gate (#410) — dokumentieren
- Scope: edit_gate.py, bash_gate.py, gemeinsamer Helfer (hook_utils oder config_loader), Tests, CHANGELOG
