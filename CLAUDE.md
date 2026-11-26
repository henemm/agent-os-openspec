# Agent OS + OpenSpec Framework

> **Meta-Projekt**: Dies ist das zentrale Framework-Repository, das abstraktes Projekt- und Workflow-Wissen konsolidiert. Alle Projekte können Improvements hierher zurückführen und von Verbesserungen aus anderen Projekten profitieren.

**Version**: 4.26.4

## Rollen und Zusammenarbeit (PO-Vorgabe 2026-11-08, gilt für jede Sitzung, auch Cloud)

- **Henning ist Product Owner, kein Programmierer**; er schaut nie in Git, PRs oder CI. Antworten an ihn: einfache Sprache, Ergebnis statt Mechanik, Fachbegriffe kurz übersetzt.
- **Claude ist Tech Lead** und entscheidet technisch selbst, nach etablierter Praxis, den Specs, ADRs und früher getroffenen Entscheidungen (Issues, Doku) dieses Repos. Keine Abkürzungen, keine ungetesteten Experimente am Live-System; nur bei echten Produkt-Zielkonflikten Optionen mit begründeter Empfehlung vorlegen.
- **Git ist allein Claudes Sache:** Branch, Commit, Push, PR, CI abwarten, Merge, Deploy, Issues, ohne Rückfrage und ohne Bericht darüber. Das hebt die Standardvorsicht („Commit/Push nur auf Nachfrage") und jede Vorlage „Merge bleibt beim PO" für dieses Repo ausdrücklich auf. Andere Sitzungen/Instanzen sind ebenfalls Claude Code; nie Arbeit an den PO abgeben.
- **Den PO fragen nur zu Produktentscheidungen** (Freigabe von Anforderungen, fachliche Zielkonflikte), per `AskUserQuestion`, nie als Freitext. Tooling, Git, Hooks, Server-Mechanik klärt Claude selbst.
- **Aufgaben nur als GitHub-Issues** in diesem Repo; ein Issue erst schließen, wenn es end-to-end erledigt ist.

## Arbeitsweise (Kurzfassung, Volltext in `docs/arbeitsweise.md`)

- Jede Aufgabe beginnt mit `/00-intake #<N>`. Vor jedem neuen Issue die offenen durchsuchen; vor Implementierung und Commit Issue-Status, offene PRs und `origin/main` prüfen (parallele Sitzungen).
- Recherche und Reproduktion vor jedem Fix; Gate- und Sicherheits-Designfragen entscheidet Claude. Keine manuellen Tests für Henning, alles automatisiert.
- Henning tippt im Workflow nur Freigabe-Wörter (`approved`, `go`, `override`); jede weitere Frage mit Kontextblock vorab.
- Ausliefern: PR mit `Closes #<N>`, `gh pr checks <N> --watch`, Squash-Merge. Einzel-Auslieferung: der Fix-/Feature-PR enthält den Versions-Bump selbst (ein Testlauf); nur beim Bündeln mehrerer Issues CHANGELOG unter `[Unreleased]` und Release als eigener PR direkt danach (#640). Ohne Rückfrage und ohne Erinnerung; „erledigt“ erst, wenn die Version veröffentlicht ist (Henning, 2026-11-21; `release.yml` taggt automatisch).
- Tests lokal nur im venv mit `pytest` und `pyyaml`.

## Projektzweck

Dieses Repository vereint zwei Ansätze:

1. **Agent OS**: Hook-basierte Workflow-Enforcement für Claude Code
2. **OpenSpec (SpecDriven)**: Spec-First Development - kein Code ohne Spezifikation

Das Framework erzwingt technisch (nicht nur durch Dokumentation), dass Claude strukturiert arbeitet:
- Erst Kontext sammeln, dann analysieren, dann spezifizieren
- TDD: Erst Tests schreiben (RED), dann implementieren (GREEN)
- Keine Änderungen an geschützten Dateien ohne freigegebene Spec
- ECHTE Test-Artefakte (Screenshots, Logs, etc.) - keine Platzhalter

## Orchestrator-Prinzip (v3.1)

**Der Hauptkontext schreibt niemals Code direkt.**

| Rolle | Werkzeuge | Aufgabe |
|-------|-----------|---------|
| **Orchestrator** (Hauptkontext) | Read, Grep, Bash, koordinieren | Planen, entscheiden, koordinieren |
| **Developer Agent** (`developer-agent`) | Edit, Write, Bash, Read | Code schreiben, Tests ausführen |
| **Adversary Agent** (`implementation-validator`) | Read, Grep, Bash | Implementierung angreifen, Beweise fordern |

Warum: Separation of concerns verhindert Conversation Drift (der Implementierer validiert sich nicht selbst), ermöglicht echte Kontext-Isolation beim Adversary, und macht den Developer Agent austauschbar (z.B. mit worktree-Isolation für parallele Workflows).

## Workflow und Zustand

- **Phasen:** `phase0_idle` → `phase1_context` (/10-context) → `phase2_analyse` (/20-analyse) → `phase3_spec` (/30-write-spec) → `phase4_approved` („approved“) → `phase5_tdd_red` (/40-tdd-red) → `phase6_implement` (/50-implement) → `phase6b_adversary` → `phase7_validate` (/60-validate) → `phase8_complete`. Fast Track oder voller Prozess entscheidet `/00-intake`.
- **Aktiver Workflow** nur über `OPENSPEC_ACTIVE_WORKFLOW`; im Worktree gilt `.claude/active_workflow` > `settings.local.json`, die Env-Var wird dort ignoriert (#58). `workflow.py start <name>` gibt die nötige `export`-Zeile aus; jeder Agent-Brief beginnt mit `export OPENSPEC_ACTIVE_WORKFLOW=<name>`.
- **RED-Artefakt Pflicht:** kein Code-Edit in phase6 ohne registriertes RED-Artefakt (`workflow.py add-artifact …`, `workflow.py mark-red …`).
- **Freigabe** braucht ein unabhängiges PO-Briefing (`po-briefer`-Agent, `workflow.py set-briefing docs/briefings/<workflow>.md`).
- **Stop-Lock:** „stop“ blockiert alle Edit/Write/Bash, „weiter“ gibt wieder frei.
- **Override:** „override“ erzeugt einen Einmal-Bypass (1 h) für Phase-/TDD-Gates; er öffnet nie den Spec-Freeze (#439).

## Kontext-Haushalt (Kurzfassung)

1. Früh schneiden: `workflow.py context` misst den Kontext gegen die Schwelle; nur bei `CONTEXT_STOP=on` (Modus manual) endet der Turn mit Checkpoint, im Auto-Modus läuft die Kette weiter, das nächste Issue startet in frischer Sitzung (#667).
2. Nachschlagen an einen Explore-Teilagenten abgeben.
3. Befehle bündeln (`workflow.py batch`, `scripts/ship.py`).
4. Gezielt lesen: Zeilenbereiche und gezielte Suchen statt ganzer Dateien.
5. Steuerungs-Overhead klein halten: Statusabfragen nur, wenn sie eine Entscheidung ändern.

## Konventionen (harte Regeln)

- **Keine Breaking Changes** ohne Migration-Pfad.
- **CHANGELOG.md** bei jeder Änderung aktualisieren; **Versionsnummer** (`.claude-plugin/plugin.json`, semantisch) bei Einzel-Auslieferung im Fix-/Feature-PR selbst erhöhen.
- **`core/hooks/` und `core/agents/` sind Infrastruktur**: Ohne laufenden Workflow ab phase6 verlangt `edit_gate.py` dafür einen Override-Token — der User tippt **"override"** (gilt 1 h, wird in `.claude/user_override_token.json` protokolliert). Mit Workflow ab phase6 entfällt er (#322); Phase-, TDD- und Adversary-Prüfung gelten stattdessen. Der Override öffnet nie den freigegebenen Teil einer Spec (#439). Niemals per Bash/`sed` am Gate vorbeischreiben: der Umweg ist kein Freibrief, sondern ein Fehler.
- **`core/commands/*.md` ist die Quelle**; `skills/*/SKILL.md` wird per `python3 scripts/sync_skills.py` generiert, nie direkt editieren. `.claude/agents/` ist ein Generat aus `core/agents` (`python3 scripts/sync_cloud_agents.py`).
- **Hook-Entwicklung:** Checks zum Phase-/TDD-/Commit-Gate kommen in die 4 Kern-Gates (`edit_gate.py`, `bash_gate.py`, `post_bash.py`, `phase_listener.py`); ein neuer Hook nur bei eigenem Event/eigener Matcher-Kombination; neue Hooks IMMER in `hooks/hooks.json` registrieren. Exit-Codes: 0 = erlaubt, 2 = blockiert. Python-Hooks vor Commit auf Syntax-Fehler prüfen.
- **Hook-Pfade niemals cwd-relativ (#165).** Hook-Kommandos laufen im *aktuellen* Arbeitsverzeichnis der Sitzung, nicht im Projekt-Root. `python3 .claude/hooks/x.py` bricht deshalb, sobald die Sitzung in einem Unterordner steht — im Plugin `${CLAUDE_PLUGIN_ROOT}/...`, in Projekt-`settings.json` `python3 "${CLAUDE_PROJECT_DIR}/.claude/hooks/x.py"` (Anfuehrungszeichen Pflicht: Projektordner duerfen Leerzeichen enthalten).
- **Core oder Modul:** Core = universell für alle Projekte, Module (`modules/<name>/`) = domain-spezifisch.

## Workflow-Isolation — häufiges Missverständnis

**Workflows blockieren sich gegenseitig NICHT.** Gates (Adversary-Verdict, Approval-Marker, Phase-Checks) gelten ausschließlich für den **eigenen aktiven Workflow** (`OPENSPEC_ACTIVE_WORKFLOW`). Ein fremder Workflow in `phase6` oder `phase7_validate` ist kein Grund, einen Commit zu verweigern oder dem User Befehle zur manuellen Ausführung zu geben.

## Adversary-Limit: Kein Fix-Loop nach VERIFIED

**Regel:** Nach dem ersten VERIFIED-Verdict des `implementation-validator`-Agenten ist Schluss. Kein weiterer Fix-Zyklus, kein zweiter Adversary-Lauf.

```
phase6_implement → Adversary → VERIFIED → workflow.py phase phase7_validate → FERTIG
                             ↘ BROKEN   → Gezielter Fix → nochmal Adversary (max. 1x)
                             ↘ AMBIGUOUS → User fragen
```

**Konkret:**
- Nach VERIFIED: Sofort `workflow.py phase phase7_validate` ausführen
- Bei BROKEN: Gezielten Fix-Agenten spawnen, dann NUR EINE weitere Adversary-Runde
- Zweites VERIFIED nach Fix: direkt zu phase7, kein dritter Lauf
- Zweites BROKEN nach Fix: Eskalation an User, kein weiterer Agent
- Ein durch `/60-validate` erzwungener Code-Fix zählt wie BROKEN (#259): zurück zu `phase6_implement`, Adversary-Runde aus demselben Kontingent

Begründung: Die Kaskade Developer → Adversary → Fix → … hat real 177 Minuten und ~3M Output-Tokens verbraucht; VERIFIED heißt gut genug.

Nachschlagewissen (Architektur-Baum, Hook-Architektur, Wichtige Dateien, Slash-Commands, Gates im Detail): `docs/architektur.md`; Arbeitsweise im Volltext: `docs/arbeitsweise.md`.
