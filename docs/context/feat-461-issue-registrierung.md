# Context: feat-461-issue-registrierung

## Request Summary
Issue #461, Auftrag des PO vom 24.11.2026 (dritter Kommentar): Umsetzung der verpflichtenden
Registrierung je Issue, rechnerübergreifend. Jede Sitzung, die an einem Issue arbeitet, muss
sichtbar machen, dass sie daran arbeitet, wo sie läuft (iMac, Server, Cloud) und wie sie zu
erreichen ist. Doppelstarts werden erkannt. Der Eintrag lebt mit der Arbeit, nicht mit der
Sitzungs-ID. Die Ortswahl (#585) und die herdr-Anzeige (eigenes Issue in henemm-infra) folgen
später und sind nicht Teil dieses Workflows. Weg über GitHub, unabhängig vom Claude-Konto
(iMac und Server laufen mit verschiedenen Konten; `claude --teleport` hilft daher nicht).

Ursprünglicher Issue-Text (Dateien je Sitzung, Spalte „Dateien“, Überschneidungen,
verwaiste Einträge) bleibt der Hintergrund; der Auftrag vom 24.11. setzt den Schwerpunkt auf
die Registrierung am Issue.

## Related Files
| File | Relevance |
|------|-----------|
| core/hooks/workflow.py `cmd_start` (~3189) | Einhängepunkt der Pflicht-Registrierung, vor `_atomic_write(wf_file, data)` |
| core/hooks/workflow.py `cmd_switch` (~3537) | Wiederaufnahme ohne Start, muss Registrierung prüfen |
| core/hooks/workflow.py `cmd_complete`/`finish` (~4111), `cmd_abandon` (~4155) | `complete` zu früh zur Freigabe (Auslieferung steht aus); `abandon` gibt frei |
| core/hooks/workflow.py `cmd_ship_status` (~4373) | Freigabe bei `done`/`skipped` |
| core/hooks/workflow.py `fetch_issue_title` (~1769) | Muster für `gh api` mit Timeout, fail-open, Logdatei |
| core/hooks/workflow.py `cmd_sessions` (~5655) | lokale Übersicht; kann Registrierungsstand anzeigen |
| core/hooks/next_suggestion.py `_gh_json` (~310) | zweites `gh api`-Muster mit Deadline |
| core/hooks/session_singleton_guard.py | lokales Register (`.claude/session-locks/`), `claim`, `CLAUDE_CODE_REMOTE`-Erkennung, `HERDR_ENV`/`HERDR_PANE_ID`, `cleanup` löscht ohne Grundprüfung |
| core/hooks/mention_guard.py | gh-Schreibbefehle mit `@name` blocken – Kommentartext darf kein nacktes `@` enthalten |
| core/commands/00-intake.md, 10-context.md, 80-workflow.md, 99-reset.md | rufen `workflow.py start` auf; Befehlstexte ggf. anpassen, `skills/` per `scripts/sync_skills.py` |
| config.yaml | Kill-Switch / Schalter für die neue Pflicht |
| scripts/sync_cloud_hooks.py, cloud_bootstrap | Cloud-Sitzungen führen `workflow.py` aus dem Repo/Pin aus – Pflicht im Code greift dort |

## Existing Patterns
- GitHub-Zugriff immer per `gh api repos/{owner}/{repo}/…`, mit Timeout, fail-open, Fehler in
  `.claude/*.log`; abgekoppelter Hintergrundabruf (`_spawn_issue_title_fetch`).
- Lokaler State als JSON mit `atomic_write_json`; Cache-Dateien `.claude/issue_titles*.json`.
- Kill-Switches in `config.yaml` (`<gate>.enabled`) plus Umgebungsvariable `OPENSPEC_…=0`.
- Ort-Erkennung: `CLAUDE_CODE_REMOTE == "true"` → Cloud; herdr über `HERDR_ENV=1`,
  `HERDR_PANE_ID`, Workspace-Name; Rechnername per `socket.gethostname()` / `platform.system()`.
- `ship_status` (`open|running|done|failed|skipped`) markiert das Ende der Auslieferung (#612).

## Dependencies
- Upstream: `gh` CLI mit Token (lokal vorhanden; Cloud: GitHub-Zugriff über die Cloud-Umgebung,
  nicht geprüft), Netz.
- Downstream: alle Konsumenten-Projekte (frieda-reist, gregor_zwanzig, loose-ends, …) – jeder
  `workflow.py start` wird betroffen; öffentliche Repos (Kommentare sind öffentlich).

## Existing Specs
- `docs/specs/feat-106-session-register.md` – lokales Session-Register
- `docs/specs/fix-120-121-session-register.md` – Register-Doku/Claims
- `docs/specs/session-singleton-guard.md` – Worktree-Pflicht

## Risks & Considerations
- **Blast Radius hoch:** `cmd_start` ist der Eingang jedes Workflows in jedem Projekt. Ohne Netz
  oder ohne `gh`-Zugang darf die Arbeit nicht komplett stehen; Verhalten muss bewusst
  entschieden werden (z. B. Start mit Warnung + Nachholen, oder Block mit Ausweg).
- **Öffentliche Repos:** Kommentar ohne Pfade, Adressen, Links, Sitzungs-Geheimnisse; kein `@`.
- **Doppelstart-Rennen:** schreiben, neu lesen, frühester gültiger Eintrag (nur
  `authorAssociation == OWNER`) gewinnt; Verlierer bricht ab und räumt seinen Eintrag.
- **Lebensdauer:** über `/clear` hinweg (an Workflow/Issue gebunden), Freigabe bei
  `ship-status done|skipped`, `abandon`, geschlossenem Issue; nicht bei `complete`.
- **Verwaiste Einträge:** Übernahme nur nach Prüfung (Sitzung läuft noch? offener PR?).
- **Tests:** `gh` muss in Tests ersetzbar sein (Fake-`gh` im PATH, wie bestehende Tests).
- **Workflows ohne Issue-Nummer:** keine Registrierung möglich – Verhalten festlegen.
- Lärm am Issue: ein Kommentar je Arbeit, Stand-Aktualisierung per Bearbeiten statt neuer Kommentare.

## Analysis

### Type
Feature (Auftrag PO 24.11.2026: verpflichtende Registrierung je Issue, rechnerübergreifend über GitHub)

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/issue_claim.py | CREATE | Utility (kein Hook, wie `herdr_bridge.py`): Eintrag am Issue lesen/anlegen/bearbeiten/freigeben per `gh api`, Ort/Erreichbarkeit ermitteln, Kommentartext bauen, Gewinner bei Doppelstart bestimmen |
| core/hooks/workflow.py | MODIFY | `cmd_start` (vor `_atomic_write`): registrieren, bei fremdem gültigem Eintrag abbrechen; `cmd_switch`: Eintrag prüfen/nachholen; `cmd_abandon`, `cmd_ship_status done/skipped`: freigeben; Phasenwechsel: Arbeitsstand abgekoppelt nachtragen; neuer Befehl `claim` (status/übernehmen/nachholen); `sessions`: Spalte Registrierung |
| config.yaml | MODIFY | Abschnitt `issue_claim:` (`enabled`, `timeout_seconds`, `location_label`) |
| tests/conftest.py | MODIFY | `OPENSPEC_ISSUE_CLAIM=0` autouse, damit die ~19 bestehenden Start-Tests nie echtes `gh` rufen |
| tests/test_issue_claim_461.py | CREATE | Fake-`gh` im PATH (Muster `test_release_tested_proof_633.py`): Start registriert, Doppelstart, offline, ohne Issue, Freigabe, Übernahme, Nicht-OWNER ignoriert, kein `@`/Pfad im Text |
| core/commands/00-intake.md, 10-context.md, 80-workflow.md | MODIFY | Hinweis auf Abbruch bei fremder Registrierung + Übernahme; `skills/` per `scripts/sync_skills.py` |
| CHANGELOG.md, .claude-plugin/plugin.json, CLAUDE.md (Tabelle Wichtige Dateien) | MODIFY | Version 4.21.0, Doku |

### Scope Assessment
- Files: ~8 (+ generierte skills)
- Estimated LoC: +450 / -10 (davon ~250 Tests)
- Risk Level: HIGH — `cmd_start` ist der Eingang jedes Workflows in jedem Konsumenten-Projekt; Netzaufruf im Startpfad

### Technical Approach (Entscheidungen Tech Lead)
1. **Eigenes Modul `issue_claim.py`**, `workflow.py` (5775 Zeilen) ruft nur auf. Kein neuer Hook: die Pflicht sitzt im Code von `start`/`switch`, damit sie unabhängig vom Befehlstext greift (auch `/10-context`, Cloud mit Repo-Hooks).
2. **Eintrag = ein Kommentar je Arbeit am Issue**, erkennbar an verstecktem Marker `<!-- openspec-claim v1 id=<zufall> -->` plus maschinenlesbarem Block (Ort, Sitzungsname = Workflow-Name, Beginn UTC, Phase, Status aktiv/freigegeben/zurückgezogen/übernommen). Aktualisierung per PATCH desselben Kommentars (keine Benachrichtigungsflut). Kein `@`, keine Pfade, keine Links, keine Rechner-Adressen.
3. **Doppelstart:** schreiben → neu lesen → gültig sind nur Marker-Kommentare mit `authorAssociation == OWNER`, Status aktiv, Issue offen; der früheste (createdAt, dann Kommentar-ID) gewinnt. Verlierer setzt seinen Kommentar auf „zurückgezogen“, `start` bricht mit Klartext ab (wer, wo, seit wann, wie erreichbar), ohne Workflow-Datei zu schreiben. Ausweg `start … --uebernehmen` (fremder Eintrag → „übernommen“).
4. **Ort:** `CLAUDE_CODE_REMOTE=true` → „Cloud“; sonst `issue_claim.location_label` (lokal je Rechner, z. B. „iMac“/„Server“), Fallback nach `platform.system()` („Mac“/„Linux-Rechner“). Erreichbarkeit: herdr (`HERDR_ENV=1`) → „herdr“, Cloud → „Sitzungsliste des Claude-Kontos, Antwort am Issue“, sonst „Terminal“.
5. **Lebensdauer an der Arbeit:** Kommentar-ID im Workflow-State (`issue_claim`), nicht an der Sitzungs-ID → überlebt `/clear`/`switch`. Freigabe bei `ship-status done/skipped` und `abandon`; nicht bei `complete`. Geschlossenes Issue gilt beim Lesen als frei.
6. **Ohne Netz / ohne `gh` / Zeitlimit:** Start läuft weiter mit deutlicher Warnung, State `issue_claim.status=pending`; `switch` und der nächste Phasenwechsel holen nach (fail-open, sonst stünde jede Arbeit ohne Netz). Doppelstart-Schutz entfällt dann (Known Limitation).
7. **Ohne Issue-Nummer:** keine Registrierung, einzeilige Notiz; kein Block.
8. **Arbeitsstand:** bei Phasenwechsel abgekoppelt (Hintergrundprozess wie `_spawn_issue_title_fetch`), kein Warten.
9. **Verwaist:** `claim status` zeigt Alter des fremden Eintrags und offene Pull Requests zum Issue; Übernahme nur explizit, nie automatisch.
10. **Abschaltung:** `issue_claim.enabled` (Default an) + `OPENSPEC_ISSUE_CLAIM=0`.

### Befunde, die gegen den Plan sprechen
- Netzaufruf (Zeitlimit ~8 s) bei jedem `start`; gemildert durch Zeitlimit und fail-open.
- Cloud-Sitzungen haben nicht sicher `gh`/Token → dort ggf. nur Warnung; aus dieser Sitzung nicht prüfbar (Known Limitation, Nachweis später in echter Cloud-Sitzung).
- Öffentliche Konsumenten-Repos: Kommentar ist öffentlich → nur Ort-Etikett, Workflow-Name, Zeit, Phase.
- Ein Start offline umgeht den Doppelstart-Schutz.

### Out of Scope (Folge-Issue)
- Spalte „Dateien“ und Überschneidungen in `sessions`, Aufräumen alter lokaler Einträge (ursprünglicher Issue-Text) → eigenes Issue, damit #461 mit der Registrierung abschließt.
- Ortswahl (#585), herdr-Anzeige (henemm-infra).
- Arbeit ohne Workflow (reine Doku/Issue-Pflege) hat keinen Einhängepunkt.

### Dependencies
- `gh` CLI mit Token, Netz; `hook_utils.workflow_issue_number`, `config_loader`.
- Downstream: alle Konsumenten über Plugin-Update; bestehende Start-Tests (conftest-Isolation nötig).

### Open Questions
- Keine offene Produktfrage (Umsetzung ohne Rückfragen beauftragt; Entscheidungen oben vom Tech Lead).
