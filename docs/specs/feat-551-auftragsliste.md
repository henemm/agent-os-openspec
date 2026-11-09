---
entity_id: feat-551-auftragsliste
type: module
created: 2026-11-09
updated: 2026-11-09
status: draft
version: "1.0"
workflow: feat-551-auftragsliste
tags: [workflow, auftrag, queue, context, autoclear, banner]
---

# Auftragsliste auf der Platte: Mehr-Issue-Auftrag überlebt `/clear` (Issue #551)

## Approval

- [ ] Approved

## Purpose

Ein Mehr-Issue-Auftrag des PO („Setze 545, 547 und 548 komplett autark um …") steht heute nur im Chat. Beim `/clear` ist er weg; nur das erste Issue wurde fertig (#551). Künftig steht der Auftrag als Liste in einer Datei im Haupt-Repo, überlebt `/clear` und Worktree-Wechsel, wird beim Abschluss jedes Issues automatisch abgehakt und liefert den Endzustand (#550) und den Sitzungsstart: Ist ein Issue offen, weiß Claude, womit es weitergeht. Ist der Auftrag „autark", halten Kontext-Schnitt, `autoclear` und Checkpoint-Hinweise die Kette nicht mehr an (PO-Vorgabe 2026-11-09: kein Halt für `/clear`, stattdessen die automatische Komprimierung von Claude Code).

## Source

- **File:** `core/hooks/workflow.py`, `core/hooks/hook_utils.py`, `core/hooks/post_bash.py`, `core/hooks/session_banner.py`, `core/commands/00-intake.md`, `core/commands/60-validate.md`, `core/commands/70-deploy.md`, `config.yaml`, `.gitignore`
- **Identifier:** neu `auftrag_settings`, `auftrag_path`, `read_auftrag`, `write_auftrag`, `auftrag_open_issues`, `auftrag_autark_open`, `auftrag_mark_done`, `auftrag_note_text` (alle in `hook_utils.py`), `cmd_queue` (`workflow.py`); geändert `end_state` (~395-462), `cmd_complete` (~2913), `cmd_endstate` (~3217), `cmd_context` (~3791), `cmd_autoclear` (~3654), `status_note` (~543), `render_plan`, `context_cut_note` (~2640), `_track_context` (`post_bash.py` ~150), `build_output` (`session_banner.py` ~489)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.find_project_root` (~1521) | function | löst Worktrees auf das Haupt-Repo auf; Basis für `<root>/.claude/auftrag.json` |
| `hook_utils.read_state_text`, `atomic_write_text`, `UnsafeStateError` (~1676-1742) | function | Pflicht-Muster für neue Zustandsdateien (#416/#422): Verweis-Schutz, atomar |
| `hook_utils.context_budget_settings` (~2509) | function | Vorbild für den Kill-Switch (nur Literal `false` schaltet ab) |
| `workflow.workflow_issue_number(data)` | function | Issue-Nummer des abgeschlossenen Workflows für das Abhaken |
| `workflow.end_state`, `cmd_endstate`, `END_DONE`, `END_WAITING`, `END_YOU` (#550) | function | Endzustand; Plan-Schlusszeile und `endstate` bleiben dieselbe Quelle |
| `workflow.cmd_context`, `cmd_autoclear`, `hook_utils.context_cut_note` | function | Kontext-Schnitt und Auto-/clear, die im autarken Auftrag still bleiben |
| `workflow.status_note`, `session_banner.build_output` | function | Wiederaufnahme nach `/clear` oder neuer Sitzung |
| `scripts/sync_skills.py` | script | spiegelt `core/commands/*.md` nach `skills/*/SKILL.md` |
| `docs/specs/fix-550-endzustand.md` | spec | Regel „Plan-Schlusszeile und `endstate` sind identisch" gilt weiter |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/hook_utils.py | MODIFY | Auftrags-Hilfen (Pfad, sicheres Lesen/Schreiben, Kill-Switch, offene Nummern, `auftrag_autark_open`); `context_cut_note(tokens, threshold, autark=False)` mit autarker Variante |
| core/hooks/workflow.py | MODIFY | `cmd_queue` + CLI-Eintrag `queue`; `end_state(..., queue_next=None, autark=False)`; `cmd_complete` hakt ab; `cmd_endstate`/`render_plan` übergeben den Auftrag; `cmd_context` (`CONTEXT_CUT=off` + `CONTEXT_REASON=AUTARK`) und `cmd_autoclear` (`AUTO_CLEAR=off`) autark-bewusst; `status_note` nennt den Auftrag |
| core/hooks/post_bash.py | MODIFY | `_track_context` reicht die autarke Lage an `context_cut_note` durch |
| core/hooks/session_banner.py | MODIFY | offener Auftrag im `additionalContext` des SessionStart-Hooks |
| core/commands/00-intake.md | MODIFY | Mehr-Issue-Auftrag zuerst per `workflow.py queue add … [--autark]` sichern |
| core/commands/60-validate.md, core/commands/70-deploy.md | MODIFY | Abschluss: bei `ENDSTATE=waiting` mit offenem Auftrag `/00-intake #M` selbst aufrufen (Kette) |
| .gitignore | MODIFY | Eintrag `.claude/auftrag.json` |
| config.yaml | MODIFY | Abschnitt `auftrag:` mit `enabled: true` |
| skills/*/SKILL.md | REGENERATE | `python3 scripts/sync_skills.py` |
| tests/test_auftrag_551.py | CREATE | Regressionstests zu allen AC |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased], kein Versions-Bump |

Nicht Teil: Seitenleisten-Anzeige der Liste (herdr), Kontext-Schwelle relativ zum Grundkontext (eigenes Issue), Übergabenotiz #188, Lock bei parallelen Sitzungen (genau ein Auftrag je Projekt, eine Sitzung führt ihn).

### Estimated Changes

- Files: 1 neu (+ regenerierte Skills), ca. 10 geändert
- LoC: ca. +250/-20 Produktion, +250 Test
- Risk Level: MEDIUM (Kern-Hook `workflow.py` betroffen; aber additive Logik mit Kill-Switch, ohne Auftragsdatei unverändertes Verhalten)

## Implementation Details

**Ablage und Format.** Eine Datei `<root>/.claude/auftrag.json` mit `root = find_project_root()`. Damit liegt sie im Haupt-Repo, auch wenn der Aufruf aus einem Worktree kommt. Sie steht in `.gitignore`. Inhalt:

```json
{"issues": [{"n": 545, "status": "done"}, {"n": 547, "status": "open"}],
 "autark": true, "note": "Wortlaut des Auftrags", "created": "2026-11-09T10:00:00Z", "updated": "2026-11-09T10:05:00Z"}
```

Gelesen wird per `read_state_text`, geschrieben per `atomic_write_text(path, text, root=)`. `read_auftrag(root)` liefert ein normalisiertes Dict oder `None` (Datei fehlt, kaputtes JSON, falsche Form, `UnsafeStateError`, Kill-Switch aus); es wirft nie. Es gibt genau einen Auftrag je Projekt und keinen Lock.

**Kill-Switch.** `auftrag_settings(config=None) -> {"enabled": bool}` nach dem Muster von `context_budget_settings`: nur das Literal `false` unter `auftrag.enabled` schaltet ab, jeder Fehler ergibt `enabled: True`. Bei `enabled: false` liefert `read_auftrag` immer `None`, und alle Verbraucher (`complete`, `endstate`, Plan, `context`, `autoclear`, `status_note`, Banner, `context_cut_note`) verhalten sich wie ohne Datei. `config.yaml` bekommt `auftrag: {enabled: true}`.

**Hilfen in `hook_utils.py`.** `auftrag_open_issues(auftrag) -> list[int]` (offene Nummern in Listenreihenfolge), `auftrag_autark_open(root=None) -> bool` (Auftrag lesbar, `autark` ist `true` und mindestens ein Issue offen), `auftrag_mark_done(root, n) -> bool` (setzt `status` auf `done`, aktualisiert `updated`, schreibt atomar; `False` ohne Auftrag oder ohne diese Nummer), `auftrag_note_text(auftrag) -> str` (ein Satz für Hinweis und Banner, siehe unten). Alle fail-open.

**CLI `workflow.py queue`** (Eintrag in `COMMANDS`, damit auch `batch` es findet; wirkt ohne aktiven Workflow):

- `queue add <N…> [--autark] [--note "<text>"]`: hängt Nummern in der angegebenen Reihenfolge an den Auftrag an (legt ihn an, falls keiner existiert). Doppelte Nummern werden ignoriert; eine bereits erledigte Nummer wird wieder `open`. `--autark` setzt `autark: true` (ein späteres `add` ohne Flag nimmt es nicht zurück), `--note` ersetzt den Wortlaut. Eine kaputte Datei wird dabei durch einen neuen Auftrag ersetzt. Ungültige Nummern (nicht positiv-ganzzahlig) oder keine Nummer: Usage auf stderr, Exit 1.
- `queue` bzw. `queue list`: nur lesend.
- `queue done <N>`: hakt die Nummer ab; unbekannte Nummer: Meldung auf stderr, Exit 1.
- `queue clear`: löscht die Datei (idempotent).

Nach `add`, `done` und `clear` und bei `list` kommt dieselbe Ausgabe, Exit 0: `QUEUE=<offene Nummern, kommagetrennt>` (leer: `none`), `AUTARK=on|off`, `NEXT=<N>|none`. Bei offenem Auftrag folgt eine vierte Zeile `PROMPT=/00-intake #<NEXT>`; bei autarkem Auftrag ergänzt um ` (autark: Auftrag aus .claude/auftrag.json weiter abarbeiten, kein Halt für /clear)`. Ohne offenes Issue gibt es keine `PROMPT=`-Zeile. Bei ausgeschaltetem Kill-Switch gibt `queue` (und jeder Unterbefehl) genau `QUEUE=disabled` aus, Exit 0, und schreibt nichts.

**Abhaken.** `cmd_complete` ruft nach erfolgreichem Abschluss `auftrag_mark_done(root, workflow_issue_number(data))` in einem `try/except`; fehlender Auftrag, fehlende Issue-Nummer, kaputte Datei oder Kill-Switch ändern weder Ausgabe noch Exit-Code.

**Endzustand (#550).** `end_state(data, archived=False, deploy="off", autonomous=False, queue_next=None, autark=False)` bleibt rein (kein Config-, kein Dateizugriff). Nur wenn der Fall „Workflow fertig" (Art `done`, Phase 8 bzw. archiviert) vorliegt und `queue_next` eine Nummer M ist, gilt:

- `autark=True`: Art `waiting`, Zeile `⏳ Läuft noch: Claude startet #M aus deinem Auftrag. Du musst nichts tun, ich melde mich.`
- `autark=False`: Art `you`, Zeile `❗ Du: /00-intake #M — nächstes Issue aus deinem Auftrag`, `cmd` = `/00-intake #M`.

Ohne `queue_next` (leerer oder fehlender Auftrag) bleibt es beim ✅ wie bisher. Phasen vor 8, `waiting_on`-Vorrang und die Deploy-Fälle (`running`, `failed`, offen) bleiben unverändert. Ein gemeinsamer Helfer in `workflow.py` liest den Auftrag und liefert `queue_next` (erste offene Nummer, die nicht die des geprüften Workflows ist) und `autark`; `cmd_endstate` und `render_plan` rufen beide diesen Helfer auf, damit Plan-Schlusszeile und `FOOTER` identisch bleiben.

**Kette bei autarkem Auftrag.** Ist `auftrag_autark_open()` wahr:

- `cmd_context` gibt `CONTEXT_CUT=off` aus und zusätzlich die Zeile `CONTEXT_REASON=AUTARK`, auch wenn die Schwelle erreicht ist. `CONTEXT_TOKENS=` bleibt unverändert. Ohne autarken Auftrag erscheint die Zeile `CONTEXT_REASON=` nie, die Ausgabe ist byte-gleich wie bisher.
- `cmd_autoclear` gibt `AUTO_CLEAR=off` aus und schreibt den Grenz-Vermerk (`_record_auto_clear_boundary`) nicht.
- `context_cut_note(tokens, threshold, autark=False)`: bei `autark=True` lautet der Text weiterhin `KONTEXT-SCHWELLE: … Token (Schwelle …)`, enthält aber nicht „Turn beenden" bzw. „beende den Turn" und nennt stattdessen, dass der autarke Auftrag weiterläuft, Claude Code den Kontext automatisch komprimiert (`/compact`) und die Kette nicht für `/clear` angehalten wird; Nachschlagen an Explore-Teilagenten, Zeilenbereiche und `batch` bleiben als Spar-Hinweise. `post_bash._track_context` übergibt `autark=hook_utils.auftrag_autark_open()`.
- Menschliche Pflichtstopps bleiben unberührt: AMBIGUOUS, zweites BROKEN, Override, Deploy-Freigabe, Stop-Lock und Produktfragen halten die Kette weiterhin an.

**Wiederaufnahme.** `auftrag_note_text(auftrag)` liefert bei offenem Auftrag einen Satz der Form `Offener Auftrag (.claude/auftrag.json): offen #M1, #M2; nächstes Issue #M1 per /00-intake #M1; autark: kein Halt für /clear, Kette selbst fortsetzen.` (ohne `autark`-Teil, wenn nicht autark; mit dem `note`-Wortlaut, falls gesetzt). `status_note` hängt diesen Satz an den bestehenden Hinweis an (fail-open); `session_banner.build_output` nimmt ihn in den `additionalContext` auf, und zwar bei jeder Quelle (`startup`, `clear`, `resume`, `compact`), weil gerade nach `/clear` und `compact` der Auftrag sonst verloren ginge. Die sichtbare `systemMessage` bleibt unverändert. Ohne Auftrag ändert sich nichts.

**Befehlstexte.** `00-intake.md`: erteilt der PO mehrere Issues in einem Auftrag, wird vor dem ersten Workflow `python3 .claude/hooks/workflow.py queue add <N…> [--autark] [--note "<Wortlaut>"]` ausgeführt; `--autark` nur, wenn der PO „autark" bzw. „melde dich nur, wenn …" gesagt hat. `60-validate.md` und `70-deploy.md`: im Abschnitt „Abschluss: Endzustand melden" gilt nach `workflow.py endstate`: Steht dort `ENDSTATE=waiting` und `workflow.py queue` meldet ein `NEXT=M`, ruft Claude `/00-intake #M` selbst auf (Kette), statt die Zeile als Halt zu melden; bei `ENDSTATE=you` wird die ❗-Zeile wörtlich ausgegeben. Danach `python3 scripts/sync_skills.py`.

## Expected Behavior

- **Input:** `workflow.py queue …`, `workflow.py complete`, `endstate`, `plan`, `context`, `autoclear`, UserPromptSubmit-Hinweis, SessionStart-Banner, PostToolUse-Kontextmessung; Datei `.claude/auftrag.json`; Config `auftrag.enabled`
- **Output:** `QUEUE=`/`AUTARK=`/`NEXT=`/`PROMPT=`-Zeilen; Endzustand ✅/⏳/❗ passend zum Rest des Auftrags; `CONTEXT_CUT=off` + `CONTEXT_REASON=AUTARK` und `AUTO_CLEAR=off` bei autarkem offenem Auftrag; Auftragssatz in Statushinweis und Banner
- **Side effects:** neue gitignorierte Datei `.claude/auftrag.json` im Haupt-Repo (atomar geschrieben); `complete` hakt die Issue-Nummer ab. Ohne Auftrag und bei `auftrag.enabled: false` keinerlei Änderung des bisherigen Verhaltens.

## Known Limitations

- Claude Code kann `/compact` nicht von sich aus auslösen; der Ersatz ist die automatische Komprimierung von Claude Code. Eine Schwelle relativ zum Grundkontext (Cloud-Sitzungen liegen nach `/clear` schon bei ~100k) ist ein eigenes Issue.
- Genau ein Auftrag je Projekt, kein Lock: zwei parallele Sitzungen, die gleichzeitig `queue add` aufrufen, können sich überschreiben (letzter Schreiber gewinnt, jede Schreibung ist atomar). Ob ein Issue bereits geschlossen ist oder in einer anderen Sitzung läuft, prüft `queue` nicht; das bleibt Sache von `/00-intake`.
- Die Seitenleiste (herdr) zeigt den Auftrag nicht; `herdr_bridge.MANUAL_COMMANDS` und der manuelle Abschluss bleiben unverändert.
- Ob Claude die `queue`-Anweisungen aus den Befehlstexten ausführt (Sichern des Auftrags, Kette bei ⏳), erzwingt kein Hook; abgesichert sind nur Textinhalt und die Hook-/CLI-Logik per Test.
- Eine kaputte `auftrag.json` wird still wie „kein Auftrag" behandelt (fail-open); nur `queue add` ersetzt sie.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Mehr-Issue-Auftrag überlebt `/clear` und Worktree-Wechsel: `queue add 547 548 --autark` ist danach in `queue`, Statushinweis und Banner sichtbar, und der Abschluss von #547 hakt es ab und führt zu `/00-intake #548`
- [ ] Bei autarkem offenem Auftrag halten weder `CONTEXT_CUT`, `AUTO_CLEAR` noch der Kontext-Hinweis die Kette an; ohne Auftrag und mit `auftrag.enabled: false` ist das Verhalten unverändert
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, `sync_skills.py --check` ohne Drift)

## Acceptance Criteria

- **AC-1:** Given ein Projekt ohne Auftragsdatei / When `workflow.py queue add 547 548 --autark --note "komplett autark"`, danach `queue`, `queue done 547` und `queue clear` laufen / Then liefert `add` Exit 0 mit `QUEUE=547,548`, `AUTARK=on`, `NEXT=547` und einer Zeile `PROMPT=/00-intake #547 …`, `queue done 547` danach `QUEUE=548` und `NEXT=548`, und `queue clear` entfernt die Datei und liefert `QUEUE=none`, `AUTARK=off`, `NEXT=none` ohne `PROMPT=`; ungültige Nummern ergeben Exit 1
  - Test: tests/test_auftrag_551.py::test_queue_add_list_done_clear

- **AC-2:** Given ein Aufruf aus einem Worktree-Unterordner und aus dem Haupt-Repo / When `queue add 547` läuft / Then liegt die Datei unter `<Haupt-Repo>/.claude/auftrag.json` (nicht im Worktree), wird über `atomic_write_text` geschrieben (kein Temp-Rest, gültiges JSON mit `issues`, `autark`, `created`, `updated`) und `.gitignore` enthält den Eintrag `.claude/auftrag.json`
  - Test: tests/test_auftrag_551.py::test_auftrag_file_in_main_repo_atomic_and_gitignored

- **AC-3:** Given ein Auftrag mit offenen Issues 547 und 548 und ein Workflow `feat-547-x` / When `workflow.py complete` läuft / Then ist 547 im Auftrag `done` und 548 `open`; ohne Auftragsdatei oder mit kaputtem JSON läuft `complete` unverändert durch (Exit 0, Auftragsdatei bleibt unangetastet)
  - Test: tests/test_auftrag_551.py::test_complete_marks_issue_done_fail_open

- **AC-4:** Given ein abgeschlossener Workflow für Issue 547 / When `end_state` bzw. `workflow.py endstate` läuft / Then gilt: Auftrag leer oder fehlend gibt `✅ Erledigt`; offenes 548 mit `autark` gibt `⏳ Läuft noch: Claude startet #548 aus deinem Auftrag. Du musst nichts tun, ich melde mich.` (Art `waiting`); offenes 548 ohne `autark` gibt `❗ Du: /00-intake #548 — nächstes Issue aus deinem Auftrag` (Art `you`); und die Schlusszeile von `render_plan` ist in allen drei Fällen gleich dem `FOOTER`
  - Test: tests/test_auftrag_551.py::test_end_state_with_queue_and_plan_matches_endstate

- **AC-5:** Given ein offener autarker Auftrag und eine Kontextmessung über der Schwelle / When `workflow.py context` und `workflow.py autoclear` laufen und `hook_utils.context_cut_note(tokens, threshold, autark=True)` aufgerufen wird / Then steht `CONTEXT_CUT=off` mit `CONTEXT_REASON=AUTARK` und `AUTO_CLEAR=off` da, und der Hinweistext enthält weder „beende den Turn" noch „NICHT selbst aufrufen", dafür den Hinweis auf die automatische Komprimierung (`/compact`)
  - Test: tests/test_auftrag_551.py::test_autark_keeps_chain_going

- **AC-6:** Given kein Auftrag oder ein nicht autarker Auftrag oder ein vollständig abgehakter Auftrag / When dieselben Aufrufe (`context` über der Schwelle, `autoclear`, `context_cut_note` ohne `autark`) laufen / Then ist die Ausgabe unverändert (`CONTEXT_CUT=on`, keine Zeile `CONTEXT_REASON=`, bisheriger KONTEXT-SCHWELLE-Text mit „beende den Turn")
  - Test: tests/test_auftrag_551.py::test_without_autark_queue_behaviour_unchanged

- **AC-7:** Given ein offener Auftrag mit nächstem Issue 548 / When `status_note` für einen aktiven Workflow und `session_banner.build_output` (Quellen `startup`, `clear` und `compact`) laufen / Then nennen `status_note` und der `additionalContext` des Banners das nächste Issue `#548`, den Weg `/00-intake #548` und bei autarkem Auftrag den Hinweis „autark"; ohne Auftrag sind beide Ausgaben gleich wie ohne diese Änderung
  - Test: tests/test_auftrag_551.py::test_status_note_and_banner_mention_open_queue

- **AC-8:** Given `core/commands/00-intake.md`, `60-validate.md` und `70-deploy.md` sowie die zugehörigen `skills/*/SKILL.md` / When sie gelesen werden / Then enthält `00-intake.md` die Anweisung `workflow.py queue add`, enthalten `60-validate.md` und `70-deploy.md` die Kette `/00-intake #M` bei `ENDSTATE=waiting` mit Auftrag, und die Skills sind synchron (`scripts/sync_skills.py --check` ohne Drift)
  - Test: tests/test_auftrag_551.py::test_command_texts_and_skills_in_sync

- **AC-9:** Given `auftrag.enabled: false` in der Config und eine vorhandene autarke Auftragsdatei / When `queue`, `queue add 549`, `complete`, `endstate`, `context`, `autoclear`, `status_note`, Banner und `context_cut_note` laufen / Then meldet `queue` `QUEUE=disabled` (Exit 0, keine Schreibung), und alle anderen Aufrufe verhalten sich wie ohne Auftrag (✅, `CONTEXT_CUT=on` ohne `CONTEXT_REASON=`, kein Auftragssatz)
  - Test: tests/test_auftrag_551.py::test_kill_switch_disables_everything

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden, ohne Netzwerk, Datei-I/O im `tmp_path`):
- `pytest tests/test_auftrag_551.py` (RED zuerst, dann GREEN)
- Bestandstests mit Wortlaut-Pins: `pytest tests/test_kontext_haushalt.py tests/test_clear_checkpoint_blocks.py tests/test_kette_auto_clear_489.py tests/test_autoclear_boundary_495.py tests/test_autoclear_transition_497.py tests/test_autonomy_kette_472.py tests/test_status_note_325.py tests/test_endzustand_550.py tests/test_session_banner.py tests/test_skills_sync.py tests/test_skill_stop_instruction.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/workflow.py core/hooks/hook_utils.py core/hooks/post_bash.py core/hooks/session_banner.py`
- `python3 scripts/sync_skills.py --check` (keine Drift in `skills/`)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Der Auftrag ist projektweiter Zustand und gehört daher wie `issue_titles.json` und `workflows/` in `<Haupt-Repo>/.claude/` (nicht in den Workflow-State, der nur sein eigenes Issue kennt, und nicht in den Chat, der beim `/clear` verloren geht). `end_state()` bleibt eine reine Funktion; die Aufrufer lesen den Auftrag und übergeben ihn als Parameter, wie schon `deploy` und `autonomous` (#550). „Autark" wirkt nur als Ketten-Regel (kein Halt für `/clear`), nicht als Aktivierung von Auto-Ship oder Auto-Approve; menschliche Pflichtstopps bleiben. Rein additiv und fail-open mit Kill-Switch `auftrag.enabled`, reversibel durch Löschen der Datei oder Abschalten des Schalters.

## Changelog

- 2026-11-09: Initial spec created (Tech-Lead-Entscheidung aus `docs/context/feat-551-auftragsliste.md`)
