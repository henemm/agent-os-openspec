# Mini-Spec: fix-gate-bugs-26-38-34

Drei kleine, unabhängige Wächter-Fehler, gebündelt in einem Fast-Track (je ein
gezielter Fix + Test, Code-Stellen vorab verifiziert).

## Was ändert sich

**#26 — Rebase-Check prüft falschen Branch** (`core/hooks/bash_gate.py:383-391`):
`git fetch` und `git rev-list --count HEAD..origin/main` laufen mit `cwd=_root`
(Hauptrepo). Liegt das Hauptrepo-`main` hinter `origin/main`, blockt der Hook jeden
Commit in JEDEM Worktree — auch wenn der Worktree-Branch aktuell ist. Fix: beide
git-Aufrufe laufen im tatsächlichen Aufrufkontext (`Path.cwd()`), denn dort findet
der zu prüfende Commit statt. `_root` bleibt für Workflow-State-Zugriffe unberührt.

**#38 — Fremder stale Workflow kapert Datei-Ownership** (`core/hooks/edit_gate.py:313-315`):
`_find_workflow_for_file()` (Match über `affected_files` ALLER nicht-archivierten
Workflows) läuft VOR `_read_active_workflow()`. Ein nie abgeschlossener, verwaister
Workflow-State übersteuert damit den aktiven Workflow. Fix: Priorität tauschen —
der explizit aktive Workflow gewinnt immer; das `affected_files`-Matching bleibt nur
als Fallback, wenn KEIN aktiver Workflow auflösbar ist (deckt sich mit CLAUDE.md:
"Gates gelten ausschließlich für den eigenen aktiven Workflow").

**#34 — override-ambiguous wirkt nicht im Phase-Abschluss** (`core/hooks/workflow.py:445-448`):
`_validate_transition()` verlangt für `phase8_complete` ausschließlich
`VERIFIED`-Prefix; das von `cmd_override_ambiguous` gesetzte Feld
`adversary_ambiguous_override` wird ignoriert — der dokumentierte Pfad
(AMBIGUOUS + Override) kann nie abgeschlossen werden. Fix: Transition zusätzlich
erlauben, wenn Verdikt mit `AMBIGUOUS` beginnt UND `adversary_ambiguous_override`
gesetzt ist — exakt dieselbe Regel, die `bash_gate.py:414` beim Commit-Gate bereits
anwendet (dort ebenfalls ohne TTL-Prüfung; Konsistenz vor neuer Logik).

Zusätzlich: `CHANGELOG.md`-Eintrag, Version 3.6.1 → 3.6.2 (PATCH).

## Was darf sich nicht ändern
- #26: Kein-Netz-Verhalten (silent skip) und Block-Meldungstext bleiben gleich.
- #38: Verhalten ohne aktiven Workflow (Fallback auf Datei-Ownership) bleibt gleich.
- #34: VERIFIED-Pfad und Ablehnung von AMBIGUOUS OHNE Override bleiben gleich;
  BROKEN bleibt immer blockiert.

## Manuelle Test-Schritte
1. Worktree aktuell, Hauptrepo-main veraltet → Commit im Worktree wird NICHT geblockt.
2. Aktiver Workflow + fremder stale State, der dieselbe Datei listet → Edit wird
   gegen den AKTIVEN Workflow validiert.
3. Workflow mit AMBIGUOUS-Verdikt: `override-ambiguous "Grund"` → danach
   `phase phase8_complete` und `complete` funktionieren; ohne Override weiterhin Block.

## Inline-Tests (werden während Implementierung geschrieben)
- [ ] #26: Zwei-Repo-Fixture (Hauptrepo hinter origin, Worktree aktuell) → kein Block;
      Gegenprobe: Worktree selbst hinter origin → Block bleibt.
- [ ] #38: Aktiver Workflow gewinnt gegen fremden affected_files-Match;
      Fallback ohne aktiven Workflow unverändert.
- [ ] #34: AMBIGUOUS+Override → Transition erlaubt; AMBIGUOUS ohne Override → Block;
      BROKEN+Override → weiterhin Block.
