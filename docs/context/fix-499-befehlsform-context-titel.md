# Kontext + Analyse: fix-499-befehlsform-context-titel (Issues #499, #500, #492)

PO-Auftrag: „Fix die drei Issues ohne Rückfragen an mich.“

## #499 — Auto-/clear tippt Kurzbefehl, der ohne Aliase nicht existiert
- Beleg (E2E #497 Szenario E, Plugin per `--plugin-dir`, Opus): nach `/clear` tippte Herdr `/20-analyse #999` → TUI „Unknown command: /20-analyse“. Mit `setup.py <projekt> --command-aliases` lief es.
- Quelle des Befehlstexts: `workflow.expected_footer_command()` → Vermerk `auto_clear_boundary.command` (`workflow.py` `_note_transition_boundary`/`_record_auto_clear_boundary`) → `herdr_bridge.maybe_auto_clear` → Runner `run_auto_clear` → `agent prompt <pane> <command>`.
- Fix-Richtung: Beim Senden (Runner bzw. `maybe_auto_clear`) die im Projekt/Benutzer existierende Form wählen: Kurz-Alias, wenn `<projekt>/.claude/commands/<name>.md`, `<projekt>/.claude/skills/<name>/SKILL.md`, `~/.claude/commands/<name>.md` oder `~/.claude/skills/<name>/SKILL.md` existiert (Claude Code löst diese Orte auf), sonst Plugin-Form `/agent-os-openspec:<name>`. Die ❗Du-Fußzeile/footer_gate bleiben unverändert (footer_gate akzeptiert die Kurzform; Anzeige für den PO).
- Zusatz (Adversary #497 F002): bei `no_build_reason` ist der Folgebefehl `/99-reset #N` — Auto-/clear soll `/99-reset` NIE automatisch tippen (Workflow-Abschluss bleibt menschlich).

## #500 — /10-context nennt `set-field context_file` nicht
- Beleg (E2E #497 Szenario E): `workflow.py phase phase2_analyse` → „context_file not set — run /context first“ (`workflow.py` `_validate_transition` ~„context_file not set“). `core/commands/10-context.md` Step 3 legt `docs/context/<workflow>.md` an, Step 4 macht nur den Phasenwechsel.
- Fix: Step 3/4 ergänzt `python3 .claude/hooks/workflow.py set-field context_file docs/context/[workflow-name].md` vor dem Phasenwechsel (Pfad-Konvention der übrigen Befehle beibehalten; Plugin-Form `${_H}` falls dort verwendet — prüfen, wie 10-context sonst workflow.py aufruft). Danach `python3 scripts/sync_skills.py`. Test: Befehlstext und Skill enthalten den Schritt vor `phase phase2_analyse`.

## #492 — Issue-Kurztitel (Folge aus #490)
- F001 (security): `short_title` lässt Steuerzeichen/ANSI aus der gh-Ausgabe durch → nicht druckbare Zeichen entfernen.
- F003: Cache-Werte ungeprüft → in `_with_issue_title` erneut durch `short_title` (Zeilenumbrüche weg).
- F002: Cache ohne Lock → Read-Modify-Write unter kurzer Sperre (wie `_pp_flock` in herdr_bridge) oder Merge beim Schreiben.
- Zusatz (PO-Beobachtung, Titel fehlte bei #234): `fetch_issue_title` nutzt `gh issue view` (GraphQL). Belegt hier im Container: GraphQL gesperrt (HTTP 403), REST `gh api repos/{owner}/{repo}/issues/N --jq .title` liefert den Titel. → auf REST umstellen (`{owner}/{repo}` von gh aus dem Remote aufgelöst). Fehlschläge in ein Log schreiben (z. B. `.claude/issue_titles.log`, rotierend, fail-open), damit eine fehlende Titelzeile diagnostizierbar ist.

## Abnahme
- Unit-Tests je Punkt (RED zuerst).
- Echter E2E: `scripts/e2e_auto_clear.sh` neues Szenario F = wie E/A', aber OHNE installierte Kurz-Aliase (nur `--plugin-dir`) → nach `/clear` läuft `/agent-os-openspec:20-analyse #999` (bzw. Testdouble) wirklich; Szenario E (echter 10-context, Opus) läuft jetzt OHNE Hilfs-CLAUDE.md-Regel zum context_file durch.
- `/99-reset` als Folgebefehl → kein Auto-Tippen (Unit-Test).
