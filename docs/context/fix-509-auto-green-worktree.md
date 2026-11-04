# Kontext: fix-509-auto-green-worktree (Issue #509)

## Anfrage (PO, 2026-11-04)

Der PO hat #509 an den Tech Lead (Claude) übergeben und „autonom“ als Arbeitsweise gesetzt. Damit sind die technischen Entscheidungen, auch Umfang und Ort der Lösung, an den Tech Lead delegiert.

## Issue #509 in Kurzform

`workflow.py auto-green` antwortet in einer Worktree-Sitzung mit

```
AUTO_GREEN=human
REASON=GREEN-Artefakt fehlt, ist keine regulaere Datei oder liegt ausserhalb des Projekts
```

obwohl das registrierte GREEN-Artefakt existiert. Beobachtet in `gregor_zwanzig` mit Plugin 4.4.9. Folge: Die automatische GREEN-Freigabe (#471) greift in Worktrees nie, jede Sitzung fällt auf die manuelle Freigabe („go“) zurück.

Ursache laut Issue: `_green_artifact_file()` löst relative Pfade gegen `find_project_root()` auf. Diese Funktion liefert in einem Worktree bewusst den Hauptrepo-Root (richtig für den geteilten Workflow-State). `docs/artifacts/` ist in Konsumenten-Projekten gitignored und liegt physisch nur im Worktree. Vorschlag: denselben Worktree-zuerst-Fallback nutzen wie `tdd_enforcement._resolve_artifact_path` (#1478 Teil 1), eine Quelle statt Kopie, und die Projektgrenze gegen den Worktree-Root prüfen, wenn die Datei dort liegt.

## Befund im Code (Stand 4.5.0, Commit e2382d3)

**Fehlerstelle**

- `core/hooks/workflow.py:3464–3482` `_green_artifact_file(rel)`: `root = find_project_root()` (Z. 3470), relativer Pfad wird `root / candidate` (Z. 3473–3474), Grenze `resolved.relative_to(root.resolve())` (Z. 3478). Kein Worktree-Fallback.
- Einziger Aufrufer: `_auto_green_decision()` (Z. 3493–3547), Aufruf Z. 3517, Meldung Z. 3518–3520. `cmd_auto_green` (Z. 3550) fängt alles fail-closed ab.

**Vorhandene Worktree-zuerst-Auflösung im selben Modul (die Quelle für die Lösung)**

- `workflow.py:57–71` `_worktree_root_if_any()`: Worktree-Root (Ordner mit `.git`-DATEI) ab `cwd`, sonst `None`.
- `workflow.py:74–85` `_worktree_first_root(rel)`: Worktree-Root, wenn `rel` dort existiert, sonst `find_project_root()`. Schon genutzt für Spec (`_read_spec_content` Z. 1295–1300, Z. 1188) und PO-Briefing (`_briefing_path_inside_project` Z. 198–207, `cmd_set_briefing` Z. 2407, Z. 1581). Dort prüft der Briefing-Pfad die Grenze bereits gegen genau diese Wurzel.

**Gleiches Muster in anderen Modulen (jeweils korrekt, aber Kopien)**

- `core/hooks/tdd_enforcement.py:162–181` `_resolve_artifact_path` (#1478 Teil 1): Worktree zuerst über `hook_utils._find_worktree_root()`, sonst Projekt-Root. Keine Symlink-/Grenzprüfung (prüft nur Existenz, Größe, Alter, Inhalt).
- `core/hooks/adversary_dialog.py:1058–1069` `_resolve_artifact_path` plus `_outside_roots` (Z. 1094–1099): Worktree zuerst, Grenze gegen Worktree- ODER Projekt-Root.
- `core/hooks/hook_utils.py:1520–1539` `find_project_root()` (löst Worktrees auf den Hauptrepo-Root auf), `1909–1926` `find_worktree_root()`, `1929–1945` `_find_worktree_root()` (Spiegel von `workflow._worktree_root_if_any`).

**Weitere Stellen in `workflow.py` mit demselben Fehler: keine.**

- Briefing (`auto-approve`, `set-briefing`, `_read_current_briefing`) und Spec nutzen schon `_worktree_first_root`.
- `cmd_add_artifact` / `cmd_remove_artifact` lesen keine Dateien.
- Die Transition nach `phase6_implement` (Z. 1691–1696) zählt nur Einträge, liest keine Datei.
- `find_project_root()` für `.claude/workflows/`, `_log`, Session-Locks und `is_stop_locked` (Z. 3540) ist richtig: geteilter State liegt im Hauptrepo.
- `evidence_gate.py` nutzt `find_project_root()` nur für die Config.

**Nachgestellt (Scratchpad, echter Ordneraufbau, kein Mock)**

Hauptrepo mit `.git`-Ordner, Worktree unter `.claude/worktrees/wt` mit `.git`-Datei, worktree-lokales `.claude/active_workflow`, State im Hauptrepo, GREEN-Log nur im Worktree unter `docs/artifacts/demo/green.log`, `cwd` = Worktree:

- Datei nur im Worktree → `AUTO_GREEN=human`, Meldung wie im Issue.
- Dieselbe Datei zusätzlich im Hauptrepo → `AUTO_GREEN=done`.

Der Fehler ist damit bestätigt: Es entscheidet allein, ob unter dem Hauptrepo-Root zufällig eine Datei liegt.

## Sicherheitsrahmen (#471)

Die Prüfung in `_green_artifact_file` hat drei Schutzzwecke, die erhalten bleiben müssen:

1. Kein Symlink (`os.lstat` + `S_ISREG`, Datei wird vorher nicht gelesen).
2. Keine Datei außerhalb der zulässigen Wurzel (nach `resolve(strict=True)`).
3. Kein Gerät, FIFO oder Ordner (nur reguläre Datei).

Die Lösung erweitert nur die zulässige Wurzel um den eigenen Worktree der Sitzung. Der Worktree ist der Arbeitsbaum, in dem die Sitzung ohnehin schreibt; er ist keine fremde Quelle.

## Entscheidung (Tech Lead, vom PO delegiert)

- **Ort:** Nur `workflow.py::_green_artifact_file`. Sie nutzt das im selben Modul vorhandene `_worktree_first_root` (wie Spec und Briefing). Keine neue Kopie der Worktree-Erkennung.
- **Nicht im Umfang:** Die drei Kopien des Worktree-zuerst-Musters (`tdd_enforcement`, `adversary_dialog`, `workflow`) in eine Funktion in `hook_utils.py` zusammenführen. Das greift in zwei weitere Gates ein (RED-Artefakt-Prüfung, Adversary-Beleg) und braucht eine eigene Spec und eigene Gegenprüfung. Vorschlag: Folge-Issue.
- **Absolute Pfade:** zulässig innerhalb des Worktree-Roots oder des Projekt-Roots (wie `adversary_dialog._outside_roots`), damit ein absolut registrierter Pfad ins Hauptrepo in einer Worktree-Sitzung nicht neu abgelehnt wird.
