# Context: feat-589-naechster-vorschlag

## Request Summary

Meldet ein Workflow „fertig“ (Schlusszeile `✅ Erledigt: …` aus `workflow.py endstate`), soll er einen möglichst intelligenten Vorschlag für die Arbeit nach `/clear` machen: Befehl `/00-intake #<N>` plus kurze Begründung (Issue #589, Sub-Issue von Epic #431).

Auswahl-Rangfolge (PO-Entscheidungen):
1. Epic: offene Sub-Issues derselben Eltern-Aufgabe
2. Meilenstein: offene Aufgaben desselben GitHub-Meilensteins
3. Spur: neu einzuführen, beim Start der Sitzung/des Auftrags gesetzt; herdr zeigt sie nur an (State-Autorität beim Framework)
4. Verwandte Aufgabe: „Folge zu #N“ / „aus #N“ / Verweis auf die erledigte
5. Sonst: wichtigste offene Aufgabe (`priority:high` > `medium` > `low`)

Innerhalb einer Stufe: Meilenstein vor ohne Meilenstein, früher fälliger Meilenstein zuerst, dann Priorität. Ausschlüsse: `status:deferred`, von anderer Sitzung beanspruchte Issues (Session-Register), die erledigte selbst. Autarker Auftrag (`.claude/auftrag.json`, `--autark`): nächste Aufgabe derselben Spur beginnt ohne Zutun (Kette wie #551); sonst nur Vorschlag. Ohne Netz/`gh`: fail-open, heutige Schlusszeile.

## Related Files

| Pfad:Zeile | Relevanz |
|------------|----------|
| `core/hooks/workflow.py:378-380` | `END_DONE`, `END_WAITING`, `END_YOU` (Zeilen-Vorlagen). `END_DONE` endet auf „Du kannst /clear ausführen und das nächste Issue starten.“ |
| `core/hooks/workflow.py:383-397` | `END_STATE_RULE`: Regeltext für Claude (drei Formen, GENAU EINE Zeile am Ende). Muss um den Vorschlag ergänzt werden, falls die Form sich ändert |
| `core/hooks/workflow.py:406-425` | `_end_state_final`: Fälle abgebrochen / ohne Code-Änderung / fertig / fertig und deployt, alle mit `END_DONE` (Art `done`). Hier hängt der Vorschlag an |
| `core/hooks/workflow.py:469-475` | `_end_state_queue(number, autark)`: heutiger Fall „Auftrag hat nächstes Issue“ (⏳ autark, sonst `❗ Du: /00-intake #N — nächstes Issue aus deinem Auftrag`). Vorbild für den Vorschlags-Fall |
| `core/hooks/workflow.py:478-505` | `end_state(...)`: reine Funktion, KEIN Config-/Netzzugriff (Kopfkommentar). Parameter `queue_next`, `autark`, `self_driven`; Eigen-Nummer wird ausgeschlossen (#555). Vorschlag muss als weiterer Parameter von außen kommen (z. B. `suggest`), damit die Funktion rein bleibt |
| `core/hooks/workflow.py:520-538` | `queue_end_args(data)`: gemeinsame Quelle für `endstate`, Plan und Seitenleiste; liest `read_auftrag()`, wirft nie. Natürlicher Ort für einen zusätzlichen Schlüssel (Vorschlag) |
| `core/hooks/workflow.py:541-565` | `render_plan(...)`: Schlusszeile = `end_state(...)["line"]`, mit `queue`-Parameter; Plan-Schluss und `endstate` müssen identisch bleiben (Spec fix-550) |
| `core/hooks/workflow.py:282-314` | `next_step(data)`: nächster Pflichtschritt der Phasen, `None` in Phase 8 |
| `core/hooks/workflow.py:317-330` | `expected_footer_command(data)`: dünne Hülle um `next_step` + Issue-Nummer; liefert in Phase 8/erledigt `None`, d. h. footer_gate prüft dort nichts |
| `core/hooks/workflow.py:3286` | `_status_target(ref)`: lädt aktiven oder archivierten Workflow (für `endstate #N`) |
| `core/hooks/workflow.py:3332-3347` | `cmd_endstate`: ruft `end_state(..., **queue_end_args(data))`, druckt `ENDSTATE=` und `FOOTER=`. Zusatz-Zeile (z. B. `SUGGEST=`) und Netzabfrage gehören hierher (nur im Kommando, nicht in der reinen Funktion) |
| `core/hooks/workflow.py:3001-3040` | `cmd_complete`: archiviert, hakt Issue im Auftrag ab (`auftrag_mark_done`, 3036-3040). Danach läuft `endstate` |
| `core/hooks/workflow.py:3971-4051` | `_print_queue`, `cmd_queue` (`list`/`add`/`done`/`clear`): `NEXT=`, `PROMPT=/00-intake #N`; Auftragsdatei-Pflege |
| `core/hooks/workflow.py:3955-3956` | `QUEUE_AUTARK_SUFFIX`: Text „autark: … kein Halt für /clear“ |
| `core/hooks/workflow.py:723-815` | Issue-Titel-Cache und `fetch_issue_title`: bestehendes `gh api`-Muster (siehe Existing Patterns) |
| `core/hooks/workflow.py:2175` | `cmd_start`: Ort, an dem eine „Spur“ beim Sitzungs-/Workflow-Start gesetzt werden könnte |
| `core/hooks/workflow.py:3683-3701` | `_read_session_entries()`: liest `.claude/session-locks/*.json`; Feld `issue` (Komma-Liste), `issue_source` (`claim`), `workflow`, `phase`; `cmd_sessions --json` (4231) gibt sie roh aus |
| `core/hooks/session_singleton_guard.py:465-492` | `_claim_holds`: Claim-Lebensdauer; `claim --issue N[,M]` schreibt Feld `issue` |
| `core/hooks/hook_utils.py:2825-2935` | Auftragsdatei: `auftrag_settings` (Kill-Switch), `read_auftrag`, `write_auftrag`, `auftrag_open_issues`, `auftrag_autark_open`, `auftrag_mark_done`, `auftrag_note_text`. `_normalize_auftrag` (2853-2868) kennt nur `issues[{n,status}]`, `autark`, `note`, `created`, `updated` (unbekannte Felder wie `spur` werden beim Normalisieren verworfen, müssten dort ergänzt werden) |
| `core/hooks/footer_gate.py:31-32` | `DU_LINE_RE`: nur Zeilen „❗/‼ Du:“ zählen als Marker. `✅`-Zeilen werden nie geprüft |
| `core/hooks/footer_gate.py:132-153` | `_footer_commands(message)`: alle Slash-Befehle der LETZTEN ❗Du-Zeile |
| `core/hooks/footer_gate.py:236-285` | `main`: ohne ❗Du-Zeile `exit 0`; sonst Abgleich mit `expected_footer_command`; Phase-8-Fall (`expected` None) ebenfalls `exit 0` |
| `core/hooks/herdr_bridge.py:188-222` | `build_report`: Tokens `workflow, issue, phase, step, next, state`; `state` aus `end_state(...)["kind"]` über `STATE_TOKENS` (82). Anzeige-Ort für eine Spur: zusätzlicher Token `lane`/`spur` |
| `core/hooks/herdr_bridge.py:292-293, 347-380` | Positiv-/Negativmarker, `has_clear_marker` (nur noch Hilfsfunktion) |
| `core/hooks/herdr_bridge.py:490, 526-590` | `MANUAL_COMMANDS = ("99-reset",)`; `maybe_auto_clear`: löst nur aus, wenn `expected_footer_command(data)` mit `/` beginnt UND in der ❗Du-Zeile steht UND `auto_clear_boundary` (`workflow.py autoclear`, 3789-3812) gesetzt ist. Im Phase-8-/✅-Fall: `expected` ist `None` → Skip „kein Slash-Befehl als nächster Schritt“ |
| `core/commands/60-validate.md:422-444` | „Abschluss: Endzustand melden“ inkl. Kette bei offenem Auftrag (Erkennung über Textteil „aus deinem Auftrag“, Zeile 438-444) |
| `core/commands/00-intake.md:52-65` | Abschnitt 1a „Mehr-Issue-Auftrag sichern (#551)“, `queue add … --autark` |
| `core/commands/70-deploy.md`, `core/commands/99-reset.md` | ebenfalls Endzustand-Verweise (per grep `endstate` prüfen) |
| `skills/*/SKILL.md` | GENERIERT aus `core/commands/*.md` (`python3 scripts/sync_skills.py`); Drift blockt Release, `tests/test_auftrag_551.py::test_command_texts_and_skills_in_sync` (680) prüft |
| `scripts/sync_skills.py` | `marker_block` enthält dieselbe Fußzeilen-Regel wie `END_STATE_RULE` (beide nennen nur die drei Formen) |
| `scripts/ship.py:52, 257-262` | `gh`-Aufruf (`_gh`, Timeout 300) mit `shutil.which("gh")`-Prüfung und fail-open-Meldung (Präzedenz) |
| `config.yaml:336-340` | Abschnitt `auftrag:` (`enabled`), Kill-Switch-Muster „nur Literal `false`“; `config.yaml:349-370` `herdr:`; `config.yaml:373-378` `autonomy:` |

## Existing Patterns

- **Endzustand-Quelle ist eine reine Funktion** `end_state()` (Zeile 478): kein Config-/Netz-Zugriff; Aufrufer (`cmd_endstate`, `render_plan`-Aufrufer, `herdr_bridge.build_report`) füttern sie über `queue_end_args()`. Ein Netz-Vorschlag darf Plan und Seitenleiste nicht bei jedem Refresh blockieren (Seitenleiste/Plan laufen häufig) — Abfrage daher nur in `cmd_endstate` (einmal pro Abschluss) und das Ergebnis ggf. in den archivierten State/Cache schreiben, den Plan/Sidebar nur lesen.
- **Auftragskette #551/#555:** `_end_state_queue` liefert ⏳ (autark) bzw. `❗ Du: /00-intake #N — nächstes Issue aus deinem Auftrag` (nicht autark). `60-validate.md` erkennt die Kette am Teilstring „aus deinem Auftrag“. Ein neuer Vorschlags-Text braucht einen eigenen, stabilen Erkennungs-Teilstring (oder ein maschinenlesbares `NEXT=`/`SUGGEST=`-Feld in der `endstate`-Ausgabe), sonst greift die Befehlslogik falsch.
- **GitHub-Zugriff:** ausschließlich per `gh api` (REST), `subprocess.run([...], capture_output, text, timeout=8, cwd=find_project_root(), stdin=DEVNULL)`, `shutil.which("gh")`-Prüfung, `TimeoutExpired` und `returncode != 0` abgefangen, Fehler nach `.claude/issue_titles.log` (rotierend, `_log_issue_title_failure`), Cache `.claude/issue_titles.json` mit Sperre (`herdr_bridge._pp_flock`) und `atomic_write_json`. Abgekoppelter Hintergrundabruf: `_spawn_issue_title_fetch` (`Popen`, `start_new_session`). `{owner}/{repo}`-Platzhalter in `gh api` wird von gh selbst aufgelöst. GraphQL ist in Cloud-Sitzungen gesperrt (`gh issue view` scheitert mit HTTP 403) — nur REST nutzen.
- **Session-Register lesen:** `_read_session_entries()` (3683) ohne Liveness-Filter; Liveness (PID, `last_seen`) liegt in `session_singleton_guard.py`. Der `issue`-Wert kann eine Komma-Liste sein (`120,121`) und wird beim Verfall des Claims aus dem Workflow-Namen neu abgeleitet. Eigene Sitzung muss beim Ausschluss herausgefiltert werden (`session_id`).
- **Kill-Switch:** Abschnitt in `config.yaml`, nur Literal `false` schaltet ab; Lesefunktion mit try/except (`auftrag_settings`, `hook_utils.py:2833`); eigener Abschnitt z. B. `next_suggestion:` mit `enabled`, `timeout_s`.
- **Skills-Sync:** Befehlstexte in `core/commands/*.md` ändern, dann `python3 scripts/sync_skills.py`; Konsumenten bekommen die Texte über `setup.py --update`.
- **State-Dateien:** nur über `read_state_text`/`atomic_write_text` mit Wurzel (#416/#422); Auftrag und `issue_titles.json` liegen im Haupt-Repo `.claude/`, gitignoriert.

## Dependencies

**Upstream (was der Vorschlag braucht):**
- `gh` + Authentifizierung (REST). Lokal geprüft: `gh api repos/.../issues/589` liefert `labels`, `milestone`, `sub_issues_summary`, `parent_issue_url`; `gh api repos/.../issues/589/parent` liefert Eltern-Issue (hier #431); `gh api repos/.../issues/429/sub_issues` listet Sub-Issues samt `state`; `gh api "repos/.../milestones?state=open"` liefert `number,title,due_on,open_issues`; `gh api "repos/.../issues?state=open&per_page=100"` liefert Issues mit Labels, Meilenstein, Body (40 offen, 100er-Seite reicht heute; für Konsumenten `--paginate` bzw. Obergrenze bedenken). Alles REST, kein GraphQL.
- Session-Register (`.claude/session-locks/*.json`), Auftragsdatei (`.claude/auftrag.json`), `workflow_issue_number(data)` für die erledigte Nummer (auch aus archiviertem State, `endstate <N>`).
- Labels in diesem Repo: `epic`, `priority:critical|high|medium|low`, `status:deferred`, `type:*`, `quick-win`, `security`, `spec-proposal` (Prioritätsreihenfolge laut PO: high > medium > low; `critical` ist ein Zusatz, vermutlich vor high).
- Meilensteine existieren: #1 „Workflow: Token-Verbrauch senken“ (fällig 2026-11-06, 0 offen), #2 „3.41 — Schutzlücken & Freigaben“ (fällig 2026-10-26, 2 offen), #3 „Q4 2026 — Nachweise fälschungssicher“ (fällig 2026-12-18, 3 offen). Der Hinweis „milestones-API nicht erlaubt“ aus dem Auftrag trifft in dieser Sitzung NICHT zu: `gh api repos/henemm/agent-os-openspec/milestones?state=open` lief fehlerfrei; Suche `search/issues … milestone:*` liefert ebenfalls ein Ergebnis (5). Issue #589 selbst hat keinen Meilenstein.
- Epics: Label `epic` plus Sub-Issue-Beziehung (z. B. #429 `epic`, 3 Sub-Issues: #417, #411 geschlossen, #574 offen; #431 ist Eltern-Issue von #589). Verschachtelung möglich (Sub-Issue kann selbst Eltern sein).

**Downstream (was sich ändert / betroffen ist):**
- `workflow.py endstate`-Ausgabe (neue Zeile/Zusatz im `FOOTER=`), `END_DONE`/`END_STATE_RULE` und der gespiegelte `marker_block` in `scripts/sync_skills.py` (bei Formänderung beide anpassen).
- Plan-Schlusszeile (`render_plan`) und Seitenleisten-Token `state` (Identitätsregel Plan = `endstate`).
- `core/commands/60-validate.md` (Abschluss-Abschnitt, Kette), ggf. `00-intake.md` (Spur setzen, Abschnitt 1a), `70-deploy.md`, `99-reset.md`; danach `skills/*/SKILL.md` neu erzeugen.
- Autarke Kette: Claude startet nach `✅`/`⏳` selbst `/00-intake #M`; Auftrag (`.claude/auftrag.json`) braucht ggf. Feld `spur` (und `_normalize_auftrag` muss es durchreichen), sonst gehen unbekannte Felder verloren.
- `footer_gate.py` / `herdr_bridge.maybe_auto_clear`: siehe Risks.
- `config.yaml` (neuer Abschnitt/Kill-Switch), `setup.py` (kopiert Config-Vorlage/Hooks in Konsumenten), `CHANGELOG.md` unter `[Unreleased]`.

## Existing Specs

- `docs/specs/fix-550-endzustand.md`: Endzustand (done/waiting/you), Identität Plan = `endstate`, Fußzeilen-Regel.
- `docs/specs/feat-551-auftragsliste.md`: Auftragsliste, Kette, autark; Dependencies-Tabelle nennt `end_state` (~395-462), `cmd_endstate`, `queue_end_args`-Vorläufer.
- `docs/specs/fix-555-nacharbeit-endzustand.md`: Eigen-Nummer-Ausschluss, `self_driven` (⏳ statt ❗ im Auto-Modus), `queue_end_args`.
- `docs/specs/*588*`: existiert (noch) nicht im Verzeichnis (Issue #588 „Seitenleiste meldet Erledigt zu früh“; vor Spec-Arbeit Issue-Status und offene PRs prüfen).
- Tests: `tests/test_endzustand_550.py`, `tests/test_auftrag_551.py` (u. a. `test_end_state_with_queue_and_plan_matches_endstate` 499, `test_autark_keeps_chain_going` 570, `test_without_autark_queue_behaviour_unchanged` 605, `test_command_texts_and_skills_in_sync` 680, `test_kill_switch_disables_everything` 704), `tests/test_nacharbeit_555.py`, `tests/test_footer_gate_234.py` (`test_matching_footer_exits_zero` 142, `test_expected_footer_command_matches_next_step_plus_issue` 224), `tests/test_herdr_sidebar_466.py`, `tests/test_herdr_plan_pane_476.py`, `tests/test_skills_sync.py`. Tests lokal nur im venv mit `pytest` und `pyyaml`; GitHub-Aufrufe in Tests per gefaktem `gh` (PATH) bzw. Monkeypatch.

## Risks & Considerations

1. **footer_gate:** Eine `✅ Erledigt …`-Zeile wird von `DU_LINE_RE` (footer_gate.py:31) nie als Marker erkannt, `expected_footer_command` ist in Phase 8 `None`; ein zusätzlicher `/00-intake #M`-Vorschlag in der ✅-Zeile stört das Gate daher NICHT. Gefahr nur, wenn der Vorschlag als `❗ Du:`-Zeile ausgegeben wird (so macht es heute der nicht-autarke Auftragsfall, `_end_state_queue`): dann ist `expected` weiterhin `None` (Workflow archiviert bzw. Phase 8) → ebenfalls `exit 0`. Bei NOCH laufendem Workflow in Phase 7 mit anderem Folgebefehl bliebe der Check scharf. Regel: ein einzelner, GENAUER Zeilenmarker am Ende (END_STATE_RULE), also entweder die ✅-Zeile erweitern (z. B. `✅ Erledigt: … Vorschlag nach /clear: /00-intake #M — <Grund>`) oder Zeile bleibt `✅` und der Vorschlag steht in derselben Zeile, nie zusätzlich als zweite Schlusszeile.
2. **Auto-/clear:** `maybe_auto_clear` bricht im Fertig-Fall ab („kein Slash-Befehl als nächster Schritt“, herdr_bridge.py:553-556), `MANUAL_COMMANDS` hält Abschlussbefehle manuell. Ein Vorschlag darf Auto-/clear also nicht neu auslösen; will man das für autarke Ketten, wäre das eine eigene Entscheidung (im autarken Auftrag gibt es bewusst keinen Halt für `/clear`, Claude startet `/00-intake #M` selbst).
3. **Erkennung der Kette in `60-validate.md`:** Sie hängt am Text „aus deinem Auftrag“. Neuer Vorschlags-Text muss eindeutig unterscheidbar sein (Vorschlag ≠ Auftrag) und darf in nicht-autarkem Modus keine Kette starten. Maschinenlesbare Zusatzzeile in `endstate` (z. B. `SUGGEST_ISSUE=M`, `SUGGEST_REASON=…`, `SUGGEST_SOURCE=epic|milestone|lane|related|priority`) ist robuster als Textsuche.
4. **Reinheit/Performance:** `end_state` ist rein und wird von Plan/Seitenleiste häufig aufgerufen; Netzabruf dort würde jede Anzeige verlangsamen. Ergebnis einmal in `cmd_endstate` ermitteln (Timeout ~8 s wie `fetch_issue_title`, bei Bedarf mehrere REST-Aufrufe bündeln), cachen (z. B. `.claude/next_suggestion.json`) und bei Fehler fail-open die heutige Zeile liefern. Plan und `endstate` müssen für denselben Zustand dieselbe Zeile ausgeben.
5. **Mehrere REST-Aufrufe:** Eltern (`/issues/N/parent`), Sub-Issues des Eltern-Issues, Meilenstein-Issues (`issues?milestone=<n>&state=open`), offene Issues mit Labels (Priorität/`status:deferred`) und Bodys (Verweissuche „Folge zu #N“/„aus #N“). Das sind 3 bis 5 Aufrufe; Rate-Limit und Zeitlimit beachten; offene Liste einmal laden und lokal filtern (Priorität, deferred, Meilenstein, Body-Regex). Verweissuche per Regex auf `Body` (`Folge zu #N`, `aus #N`, `#N` allgemein) kann False Positives liefern (viele Bodys erwähnen Nummern); streng auf die genannten Muster beschränken. Heute enthalten 16 offene Issues „Folge zu“ oder „aus #<Zahl>“, also relevant.
6. **Präzedenz `gh` in Hooks:** Vorhanden in `core/hooks/workflow.py` (`fetch_issue_title`, `shutil.which("gh")`, Timeout, fail-open, Log) und `scripts/ship.py`. Es gibt also Präzedenz, aber nur fail-open und optional; `setup.py` setzt `gh` nicht voraus. Konsumenten ohne `gh`/Netz/Auth dürfen nichts verlieren: Kette (#551) und heutige `✅`-Zeile bleiben dann unverändert. Beachtenswert: `{owner}/{repo}`-Platzhalter wird nur in einem Git-Repo mit GitHub-Remote aufgelöst.
7. **Reihenfolge Auftrag vs. neue Regeln:** Ein offener Auftrag (#551) hat heute Vorrang (`_end_state_queue`). Der neue Vorschlag sollte nur greifen, wenn der Auftrag KEIN nächstes Issue hat (sonst konkurrieren zwei „nächste“-Quellen). Zu klären in der Analyse: Soll die Spur zusätzlich die Auftragsreihenfolge beeinflussen (Auftragsliste ist PO-geordnet, also nein).
8. **Spur neu einführen:** Speicherort offen (Workflow-State-Feld `lane`/`spur`, `auftrag.json`-Feld, oder beides; Auftrag überlebt `/clear`, Workflow-State nicht über den Workflow hinaus). `_normalize_auftrag` verwirft unbekannte Felder; Auftrag ist ein einziges Objekt je Projekt, eine Spur je Sitzung bräuchte Sitzungs-Bezug (Session-Register-Eintrag, `claim`). Setzen beim Start (`cmd_start` 2175, `/00-intake`, `queue add --lane`). herdr zeigt nur an (`build_report`-Token), State bleibt im Framework. Ob die Spur eine Freitext-Bezeichnung oder ein Epic-Verweis ist, ist eine Entwurfsfrage (Rangstufe 3 steht nach Epic und Meilenstein, ist also nur für Aufgaben ohne Eltern/Meilenstein relevant).
9. **Ausschluss „von anderer Sitzung beansprucht“:** `.claude/session-locks` liegt im Haupt-Repo (geteilt), `issue`-Feld ist Komma-Liste oder aus Workflow-Name abgeleitet; Sitzungen mit toter PID (Liveness) dürfen nicht blockieren (Bekannte Einschränkung Issue #122: PID-Recycling). Eigene Session ausnehmen. Gleiches gilt für Issues mit offenem PR (nicht gefordert, aber im Hinweis „offene PRs prüfen“ der Arbeitsweise erwähnt).
10. **Sortierung:** Innerhalb einer Stufe: Meilenstein vor ohne, früher fälliger zuerst (`due_on`; Meilensteine ohne `due_on` nachrangig), dann Priorität (`critical` > `high` > `medium` > `low` > ohne Label), dann Issue-Nummer als stabiler Tie-Breaker. `epic`-Issues selbst sind keine vorzuschlagenden Arbeitseinheiten (Container); als Vorschlag nur Sub-Issues bzw. Nicht-Epics.
11. **Kein Breaking Change:** Ausgabeformat von `endstate` (`ENDSTATE=`, `FOOTER=`) bleibt abwärtskompatibel; bestehende Tests erwarten die heutigen Zeilen (z. B. `END_DONE`-Text in `test_endzustand_550.py`). `CHANGELOG.md` nur unter `[Unreleased]`, keine Versionsnummer in Feature-PR.
12. **Verwandt/Konflikt:** #588 (Seitenleiste meldet „Erledigt“ zu früh) berührt dieselben Stellen (`build_report` `state`, `end_state`); vor Umsetzung Stand von #588 und offene PRs prüfen (parallele Sitzungen), um Merge-Konflikte in `workflow.py` zu vermeiden. Änderungen an `core/hooks/` erfordern Override bzw. laufenden Workflow ab phase6.

## Analysis

### Type
Feature (Framework-Erweiterung, Core). Kein Breaking Change: Ausgabe von `endstate` bleibt ohne Vorschlag unverändert.

### Befunde gegen den Plan
- `endstate` wird nirgends aus einem Hook aufgerufen (nur Befehlstexte 60-validate/70-deploy/80-workflow, Claude ruft es per Bash). Netz in `cmd_endstate` ist damit zulässig (einmal je Abschluss, Timeout 8 s, fail-open). Nicht zulässig ist Netz in `end_state`, `render_plan` und `herdr_bridge.build_report`: beide laufen bei jeder Anzeige/Aktualisierung (herdr_bridge.py:217 ruft `end_state(**queue_end_args)`).
- Identitätsregel Plan = `endstate` (Spec fix-550): Soll der Vorschlag in der Plan-Schlusszeile erscheinen, muss er über `queue_end_args` in `end_state` kommen, nicht nur in `cmd_endstate`. Lösung: `end_state` bekommt einen Parameter `suggest` (rein, nur Textbau im Fall done); `queue_end_args` liest ihn ausschließlich aus dem Cache `.claude/next_suggestion.json` (kein Netz); `cmd_endstate` füllt den Cache vorher per `fetch`. Plan/Seitenleiste zeigen den Vorschlag damit erst nach `endstate`; vorher die heutige Zeile (akzeptabel, kein Widerspruch). Die Seitenleiste braucht den Vorschlag nicht (Token `state` bleibt `done`); `end_state()["kind"]` bleibt `done`.
- Cache: Rohdaten (offene Issues, Eltern, Meilensteine) cachen, nicht das Ergebnis; `choose` mit Session-Register (`_read_session_entries`, ohne Liveness-Filter, Komma-Liste im Feld `issue`, eigene `session_id` ausnehmen; tote PIDs ggf. über Liveness-Helfer aus session_singleton_guard filtern) läuft bei jedem Lesen frisch, sonst veraltet die Beanspruchung.
- REST-Daten tragen die Rangfolge: `issues/N/parent` (Epic), `issues/<parent>/sub_issues` (Geschwister, `state`), `issues?state=open&per_page=100` (Labels, `milestone` inkl. `due_on`, Body), `milestones?state=open`. Achtung: die Issue-Liste enthält auch PRs (Schlüssel `pull_request` filtern) und ist auf 100 gedeckelt (Konsumenten: Paginierung/Obergrenze; bei Überschreitung ohne Fehler abschneiden). `epic`-Container und Geschwister mit offenen Sub-Issues (Verschachtelung) ausschließen bzw. nur Blätter vorschlagen. `critical > high > medium > low > ohne` ist umsetzbar; Meilenstein-`due_on` fehlt teils (nachrangig). Body-Regex für „related“ streng, nur `Folge zu #N`, `aus #N`, `Follow-up (to|of) #N`; das Verweisen der erledigten Nummer reicht nicht allein (Rauschen). Zusätzlich sinnvoll: Ausschluss von Issues mit offenem PR (zweiter Call `pulls?state=open`, Branch/Body `#N`) — optional.
- `_normalize_auftrag` (hook_utils.py:2853-2868) verwirft unbekannte Felder: `spur` muss dort ergänzt werden (sonst geht sie beim ersten `write_auftrag` verloren). Der Auftrag ist ein Objekt je Projekt, keine Spur je Sitzung: eine Spur wäre also pro Projekt, nicht pro Sitzung. Das ist bei parallelen Sitzungen (je Worktree) eine Schwäche.
- Autark: `_end_state_queue` und die Kette in 60-validate (Teilstring „aus deinem Auftrag“) greifen unverändert, wenn `endstate` die Nummer vorher per `queue`-Logik (`write_auftrag`) anhängt; Reihenfolge in `cmd_endstate`: Cache/fetch → ggf. anhängen → `queue_end_args` neu → `end_state`. Das Anhängen ist ein Schreibzugriff in einem eigentlich lesenden Kommando (`endstate` wird bei jedem erneuten Aufruf wiederholt): idempotent halten (Nummer schon im Auftrag → nichts tun, geschlossene erledigte nie neu anhängen).
- #588 (Seitenleiste meldet Erledigt zu früh) berührt `build_report`/`end_state`; Stand und offene PRs vor dem Start prüfen. Mein Plan fasst `build_report` nur für die optionale Spur-Anzeige an, Teil A nicht.
- Konsumenten ohne `gh`/Auth: `shutil.which("gh")` + returncode-Prüfung, dann kein Vorschlag, Zeile unverändert. Tests ohne Netz: gefaktes `gh` per PATH-Stub oder Monkeypatch von `fetch`; `choose` ist rein und wird tabellarisch getestet (kein Mock nötig).
- Kill-Switch `next_suggestion.enabled` nur Literal `false` (Muster `auftrag_settings`); `timeout_s` und `cache_ttl_s` mit Defaults.

### Affected Files
| Datei | Change Type |
|---|---|
| `core/hooks/next_suggestion.py` | neu: `choose` (rein), `fetch` (REST, fail-open), Cache lesen/schreiben, Settings |
| `core/hooks/workflow.py` | `end_state(suggest=)` + Textbau in `_end_state_final`-Fall done; `queue_end_args` liest Cache; `cmd_endstate` fetch, `SUGGEST_ISSUE=`/`SUGGEST_SOURCE=`, Autark-Anhängen |
| `core/commands/60-validate.md` | Abschluss: Vorschlag wörtlich ausgeben, Kette nur bei „aus deinem Auftrag“ |
| `scripts/sync_skills.py` + `skills/*/SKILL.md` | `marker_block` ggf. (Zeilenform bleibt „eine Zeile“), Skills neu erzeugen |
| `config.yaml` | neuer Abschnitt `next_suggestion:` |
| `CHANGELOG.md` | [Unreleased] |
| `tests/test_next_suggestion_589.py` | neu |
| Teil B (Spur): `hook_utils.py` (`_normalize_auftrag`), `workflow.py` (`queue add --spur`, `spur`), `herdr_bridge.py` (`build_report`), `00-intake.md`, Tests |

### Scope Assessment
Gesamt: ca. 9-10 Dateien (mit generierten Skills mehr), ca. 450-550 LoC inkl. Tests (Modul ~200, workflow ~80, Rest ~40, Tests ~250). Überschreitet 5 Dateien/250 LoC klar. Empfehlung Aufteilung:
- **Teil A (dieses Issue #589):** `next_suggestion.py` mit Stufen Epic, Meilenstein, verwandt, Priorität (Slot für Spur als optionaler Parameter, `spur=None`), `end_state`-Zusatz, `cmd_endstate`, Autark-Anhängen (Epic/Meilenstein), Config, 60-validate, CHANGELOG, Tests. Auch das ist ca. 7 Dateien; mit Skill-Generat knapp über 5, aber ein zusammenhängender Schnitt, nicht weiter teilbar ohne unbrauchbare Zwischenstände.
- **Teil B (Folge-Issue, Sub-Issue von #431):** Spur (`_normalize_auftrag`, `queue add --spur`/`spur`, GitHub-Label `spur:<name>`, herdr-Anzeige, `00-intake.md`), Autostart für Spur. Eigener Wert, eigene Designfrage (Spur je Projekt vs. je Sitzung).

### Technical Approach (Empfehlung)
Teil A wie oben beschrieben, mit diesen Anpassungen am Entwurf:
1. Vorschlag in `end_state` als reiner Parameter `suggest={"n","source","reason"}`; Netz ausschließlich in `cmd_endstate`; `queue_end_args` liest nur den Cache. Zeile: eine einzige `✅`-Zeile mit Zusatz (kein zweites ❗-Zeile; footer_gate/Auto-/clear bleiben unberührt, da `expected_footer_command` in Phase 8 `None` ist und `MANUAL_COMMANDS`/Slash-Prüfung greifen).
2. Maschinenlesbar `SUGGEST_ISSUE=`, `SUGGEST_SOURCE=`, `SUGGEST_REASON=` in `endstate`-Ausgabe (nur bei Vorschlag); 60-validate erkennt die Kette weiter am Auftrags-Teilstring, nicht am Vorschlag.
3. Priorität Auftrag > Vorschlag: nur wenn `queue_next` leer.
4. Fail-open auf jeder Stufe; Cache atomar (`atomic_write_text`), TTL kurz (Vorschlag 5 min), Schlüssel erledigte Nummer.
5. Autark-Anhängen idempotent; Quellen Epic/Meilenstein (Spur erst in Teil B).

### Dependencies
`gh` (optional), `hook_utils.read_auftrag/write_auftrag`, `_read_session_entries`, `workflow_issue_number`, bestehende Tests fix-550/551/555 (Zeilenform unverändert ohne Vorschlag), Stand #588.

### Open Questions
1. **Produktfrage (PO):** Soll ein autarker Auftrag nach Epic/Meilenstein automatisch das nächste Issue starten, oder nach dem PO-Wortlaut nur innerhalb derselben Spur (#589-Text: „nächste Aufgabe derselben Spur beginnt ohne Zutun“)? Epic-/Meilenstein-Autostart läuft sonst unbegrenzt durch ganze Epics. Empfehlung: in Teil A nur Vorschlag, Autostart erst mit Spur (Teil B) bzw. nur Epic; Tech-Lead-Entscheidung genügt, wenn der PO-Text wörtlich gilt.
2. Technisch: Spur je Projekt (Auftrag) oder je Sitzung (Session-Register)? Entscheidet Teil B.
3. Ausschluss Issues mit offenem PR: ja/nein (zusätzlicher REST-Call). Empfehlung: ja, wenn `pulls`-Call im Timeout-Budget bleibt.
4. Label `spec-proposal` und Issues, die PO-Entscheidung brauchen, als Autostart-Kandidaten? Empfehlung: ausschließen.

### Entscheidungen Tech Lead (2026-11-12)
- **Aufteilung:** Dieser Workflow liefert Teil A (Vorschlag nach Epic → Meilenstein → verwandt → Priorität, Autark-Fortsetzung). Teil B (freie Spur `spur:<name>`, Setzen, herdr-Anzeige) ist Issue #591. `choose()` bekommt `spur=None` bereits jetzt.
- **Autostart bei autark:** gilt für Quelle Epic und Meilenstein. Begründung: PO-Entscheidung „Spur = zuerst Epic in GitHub“ und Ergänzung „Meilensteine berücksichtigen“; Epic/Meilenstein sind damit die Spur. Begrenzt durch die Größe von Epic/Meilenstein. Bei `related`/`priority` nur Vorschlag. Keine Produktfrage offen.
- **Ausschlüsse zusätzlich:** Issues mit Label `epic`, Eltern mit offenen Sub-Issues, PRs, Issues mit offenem PR, `status:deferred`, `spec-proposal`.
- **Netz nur in `cmd_endstate`**, Rohdaten-Cache; `end_state`/Plan/Seitenleiste lesen nur den Cache.
