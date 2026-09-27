# Context: feat-250-prozess-abstufung

> Vorgang **#250** — „Prozess-Overhead: die drei Stufen existieren, werden aber nicht
> durchgesetzt" (fasst #147, #182, #88). Einstufung aus `/00-intake`: **Full Process**
> (Scope High, Blast Radius High, Unsicherheit High — Summe 6).
> Erhoben am 2026-09-26. Alle Zeilennummern beziehen sich auf `main` @ `0c67b5c`.

## Request Summary

Der Prozess kennt drei Aufwandsstufen (`feature-fast`, `feature`, `bug`), setzt sie aber nicht
durch: Kleine Änderungen laufen denselben Weg wie große. Drei Maßnahmen sind gebündelt —
**A** die pauschale PO-Rückfrage in der Validierung abstufen, **B** eine Aufwandsbremse pro
Stufe einführen, **C** die 26 Weckruf-Pflichtblöcke auf einen Rückfall je Phase reduzieren.

## Related Files

### Teil A — Abstufung der Validierung (#147)

| Datei | Relevanz |
|---|---|
| `skills/60-validate/SKILL.md` | **Kernbefund.** Frontmatter `disable-model-invocation: true` — dadurch kann der Ablauf die Validierung nicht selbst aufrufen, der PO muss sie tippen. Derselbe Flag steht auf `50-implement`, `70-deploy`, `80-workflow`, `81-add-artifact`, `99-reset`; alle anderen Skills stehen auf `false` |
| `core/commands/60-validate.md` | 250 Zeilen. Endet mit „Soll ich den Code committen?" (Z. 243) — zweite PO-Rückfrage. Enthält bereits eine ausgearbeitete Ausnahme für dokumentierte Projekt-Autonomie beim Deploy (Z. 200–213), die als Muster für A dienen kann |
| `core/hooks/workflow.py` Z. 947–1013 (`_validate_transition`) | **Wichtig: `phase7_validate` ist gar kein Gate.** Der Sprung nach `phase8_complete` verlangt nur ein `VERIFIED`-Verdict. Die Sperre in A ist rein textlich/Flag-basiert, nicht im Hook-Code |
| `core/hooks/post_implementation_gate.py` | Dritte PO-Rückfrage: nach 15 Minuten Wanduhr in `phase6_implement` blockiert jeder weitere Edit bis zum „go" des PO (Z. 47, 160–184). Bypass-Phasen: `phase6b_adversary`, `phase7_validate`, `phase8_complete` |
| `core/hooks/phase_listener.py` Z. 478–481 | Feld `is_new_ui` wird gesetzt, wenn der PO „neues ui" schreibt — **existierender, aber rein manueller** Kandidat für das Signal „es gibt etwas Beobachtbares" |
| `core/commands/00-intake.md` Z. 114 | Die Zeile, die die Pauschalität dokumentiert: `| Manuelle Validierung | ✅ immer | ✅ immer | ✅ immer |` |
| `core/hooks/alias_sync.py` Z. 40, 107 | Liest den Flag und entscheidet über Vollbett- vs. Verweis-Alias — jede Flag-Änderung wirkt auch hier |

### Teil B — Aufwandsbremse (#182)

| Datei | Relevanz |
|---|---|
| `core/hooks/adversary_dialog.py` Z. 30–33, 250–252 | Existierender Circuit Breaker: `MAX_ITERATIONS = 3`, `MIN_ROUNDS`. **Nicht** nach Stufe differenziert, wirkt nur im Dialog-Dokument, blockiert nichts |
| `core/hooks/workflow.py` Z. 548–566 (`_log_phase_transition`) | Schreibt `phase_log` mit `entered_at`, `exited_at`, `duration_min` — **die Zeitmessung existiert bereits**, wird aber nur rückblickend in `/90-retro` ausgewertet |
| `core/hooks/workflow.py` Z. 588+ (`record_transition`) | Die einzige Stelle, die einen Phasenwechsel protokolliert (Issue #111) — der natürliche Einhängepunkt für eine Budget-Prüfung |
| `core/hooks/workflow.py` Z. 1316–1354 (`cmd_write_log`) | Ausführungsprotokoll nach `.claude/workflows/_log/<datum>_<name>.yaml`. Führt `override_used`, `adversary_fix_loop_iterations`, `scope_loc_delta` — **aber keine Gesamtdauer** |
| `core/hooks/workflow.py` Z. 1545–1570 (`_retro_hints`) | Hinweislogik bei Fix-Loops und überlanger Phase (>35 % der Gesamtzeit) — vorhandenes Muster für Schwellwert-Warnungen |
| `config.yaml` | Top-Level-Blöcke: `workflow`, `strict_code_gate`, `tdd`, `adversary_gate`, `adr_gate`, `po_briefing_gate`, `ci_spec_gate`. Jedes Gate hat ein `enabled`-Kill-Switch — ein `effort_budget`-Block fügt sich ein |
| `core/hooks/bash_gate.py` Z. 636–665 | Commit-Gate, prüft Verdict; Fast-Track (`bug`, `feature-fast`) ausgenommen. Zeigt das etablierte Muster „Gate + Override + Diagnose-Text" |

### Teil C — Weckruf-Pflichtblöcke (#88)

| Datei | Vorkommen `ScheduleWakeup` | Intervalle |
|---|---|---|
| `core/commands/20-analyse.md` | 3 (Z. 71, 86, 107) | 180, 180, 300 s |
| `core/commands/30-write-spec.md` | 3 (Z. 99, 116, 148) | 300, 180, 240 s |
| `core/commands/50-implement.md` | 3 (Z. 87, 125, 218) | 180, 600, 300 s |
| `core/commands/60-validate.md` | 4 (Z. 62, 118, 144, 166) | 180, 300, 300, 300 s |
| Die vier zugehörigen generierten Skill-Dateien | 13 (generiert) | identisch |

**Summe 26** — deckt sich exakt mit der Zählung im Vorgang. Alle 13 Quell-Blöcke tragen die
Überschrift „**TIMEOUT-PFLICHT — sofort nach dem Spawn**", alle liegen bei 180–600 s.

## Existing Patterns

**Das Skill-Verzeichnis ist generiert, nicht gepflegt.** `scripts/sync_skills.py` erzeugt jede
Skill-Datei aus `core/commands/<name>.md`. Erhalten bleibt nur das YAML-Frontmatter
(`description`, `disable-model-invocation`) — das sind Skill-Metadaten ohne Gegenstück in
`core/commands`. `scripts/release_check.py` Z. 197–202 prüft Drift und bricht ab.
→ Änderungen am Fließtext gehören nach `core/commands/`, Flag-Änderungen direkt ins Frontmatter.

**Jedes Gate hat ein Kill-Switch und ist milde bei Config-Fehlern.** `_check_po_briefing`
(Z. 855–918) ist die Referenz: `enabled: false` schaltet ab, `skip_fast_track` nimmt
Fast-Track aus, ein Config-Ladefehler lässt das Gate AN (lenient), jede Blockade liefert einen
Handlungshinweis mit konkretem Befehl.

**Stufen-Ausnahmen laufen über `workflow_type`.** Gültige Werte: `feature`, `bug`,
`feature-fast` (`workflow.py` Z. 1033). Fast-Track wird an fünf Stellen ausgenommen:
`bash_gate.py:640`, `edit_gate.py:540`, `workflow.py:880`, `:954`, `:1566`.
→ Eine neue Stufen-Differenzierung hat ein etabliertes Vorbild.

**Selbstaufruf einer Phase ist ein gelöstes Problem.** `docs/specs/fix-140-po-decision-gates.md`
hat genau das für `/40-tdd-red` gemacht: Flag von `true` auf `false`, plus Auto-Chaining-Anweisung
im Vorgänger-Befehl, plus Regressionstest `tests/test_skill_stop_instruction.py`, der die
STOPP-Absicherung festnagelt. Das ist der Bauplan für Teil A.

## Dependencies

**Upstream (was A/B/C benutzen):** `config_loader.load_config`, `hook_utils`
(`find_project_root`, `block`, `allow`, `framework_disabled`), `workflow.read_active_workflow_fast`,
`override_token.has_valid_token`.

**Downstream (was davon abhängt):**
- `scripts/sync_skills.py` + `scripts/release_check.py` — jede Befehlsänderung muss neu generiert werden, sonst bricht die Freigabeprüfung
- `setup.py` Z. 1010–1017 und `core/hooks/alias_sync.py` — beide lesen `disable-model-invocation`
- 11 Testdateien berühren `core/commands` oder das Skill-Verzeichnis: `test_clear_checkpoint_blocks.py`, `test_skills_sync.py`, `test_skill_stop_instruction.py`, `test_setup_command_aliases.py`, `test_setup_alias_sync_150.py`, `test_session_banner.py`, `test_skill_path_resolution.py`, `test_release_check_93.py`, `test_migrate_command_cleanup.py`, `test_migrate_custom_commands_160.py`, `test_session_register_docs_120_121.py`
- **Kein einziger Test prüft heute die Weckruf-Blöcke** (Suche nach `ScheduleWakeup` in `tests/` → leer). Teil C braucht einen neuen Test, sonst wächst die Zahl wieder
- Alle abhängigen Projekte, die `setup.py --update` fahren

## Existing Specs

| Spec | Bezug |
|---|---|
| `docs/specs/fix-140-po-decision-gates.md` | **Direktes Vorbild für Teil A** — Flag-Flip + Auto-Chaining + Regressionstest für `/40-tdd-red` |
| `docs/specs/bug-fix-fast-track.md` | Wie die `bug`-Stufe ihre Ausnahmen bekommen hat |
| `docs/specs/fix-131-adversary-dialog-hash-binding.md` | Adversary-Dialog-Mechanik, die Teil B begrenzen soll |
| `docs/specs/adr-reflection-gate.md`, `docs/specs/selfexplaining-gates.md` | Muster für neue Gates: Kill-Switch, Diagnose-Text |
| `docs/specs/phase-token-logging.md` | Wie Phasen-Ereignisse protokolliert werden — relevant für die Budget-Freigabe im Protokoll |

## Baseline-Messwerte (aus dem Archiv, nicht geschätzt)

`workflow.py retro fix-237-egress-guard-scratchpad`:

| Phase | Dauer |
|---|---|
| phase1_context | 16,6 min |
| phase2_analyse | 406,6 min |
| phase3_spec | 510,4 min |
| phase4_approved | 0,3 min |
| phase5_tdd_red | 16,8 min |
| phase6_implement / 6b_adversary (3 Durchläufe) | 39,8 / 20,8 · 10,5 / 69,9 · 5,6 / 6,2 min |
| phase7_validate | 13,7 min |
| **Gesamt** | **1117,2 min** (≈ 18,6 h Wanduhr) |

Vergleichswerte: `fix-234-footer-command` 250 min, `fix-relative-hook-paths` 180 min.

## Risks & Considerations

**R1 — Wanduhr ist als Budget-Maß untauglich (belegt).** Der Vorgang schlägt
`max_hours: 0.5 / 3 / 8` vor. Die Baseline zeigt: `phase2_analyse` 407 min und `phase3_spec`
510 min sind zusammen 82 % der Gesamtzeit — das ist überwiegend Wartezeit auf den PO, nicht
Arbeit. Ein Stundenbudget würde bei jeder Mittagspause feuern. Der Vorgang nennt selbst
6 Stunden Arbeitszeit; die Wanduhr sagt 18,6. Belastbare Maße wären Aktivitätszähler:
Adversary-Runden, `fix_loop_iterations`, Wiedereintritte in eine Phase (hier 3× `phase6_implement`),
Zahl der Agenten-Starts.

**R2 — Es gibt schon eine Wanduhr-Bremse, und sie hat genau dieses Problem.**
`post_implementation_gate.py` blockiert nach 15 Minuten in `phase6_implement`. Bei 39,8 min
in der Baseline hat sie mitten in der Umsetzung eine PO-Freigabe erzwungen. Bevor ein zweites
Zeitbudget entsteht, gehört diese Stelle mit bewertet.

**R3 — Das Budget darf die Prüfung nicht abwürgen.** Der Vorgang warnt selbst: bei „max 3 Runden"
wäre in der Baseline die dritte Gegenprüfung blockiert worden — und genau die hat bestätigt, dass
die Sicherheitslücke zu ist. Eine Bremse, die den Fund verhindert, ist schlimmer als keine.
Alternative 2 des Vorgangs (nur Sichtbarkeit statt Blockade) hat hier belastbaren Vorteil.

**R4 — Das Signal für „nichts Beobachtbares" ist noch offen.** Drei Kandidaten: die Stufe aus
`/00-intake`, ein Spec-Feld, oder die Art der geänderten Dateien. Das existierende Feld
`is_new_ui` ist rein manuell (PO schreibt „neues ui") und damit als Sperr-Kriterium unzuverlässig —
Vergessen führt zur falschen Richtung (Validierung entfällt, obwohl es Oberfläche gibt).
Sichere Richtung: standardmäßig validieren, nur bei positivem Nachweis der Abwesenheit auslassen.

**R5 — Umfang über der Hausregel.** Teil A berührt ≈ 4 Dateien plus Tests, Teil B ≈ 4 plus Tests,
Teil C 4 Quelldateien + 4 generierte + 1 neuer Test. Zusammen sicher über 10 Dateien und über
±250 LoC. Der Schnitt in Teilaufträge gehört in `/20-analyse`.

**R6 — Meta-Risiko.** Geändert wird die Durchsetzungs-Mechanik selbst, mit der dieser Vorgang
arbeitet. Ein Fehler kann künftige Abläufe blockieren oder — schlimmer — stillschweigend
öffnen. Jede Lockerung braucht einen Test, der belegt, dass der **strenge** Fall weiterhin greift,
nicht nur dass der milde durchläuft.

**R7 — Die Prämisse von Teil A ist teilweise überholt.** Der Vorgang sagt, `/60-validate`
verlange manuelle Validierung durch den PO. Im Hook-Code tut es das nicht — `phase7_validate`
ist kein Gate. Es sind drei prompt- und flag-getriebene Rückfragen: der erzwungene Tastendruck
`/50-implement`, der erzwungene Tastendruck `/60-validate`, und die Schlussfrage „Soll ich den
Code committen?". Das ist eine gute Nachricht: Teil A braucht voraussichtlich **keine
Hook-Änderung**.

**R8 — Belegbarkeit der letzten Abnahme-Bedingung.** Die Bedingung „#245 und #246 laufen
nachweislich kürzer als #237" ist mit dem heutigen Ausführungsprotokoll nicht prüfbar: es führt
`completed_at`, aber keine Dauer. Entweder kommt ein Dauer-Feld dazu, oder der Nachweis stützt
sich auf `workflow.py retro` aus dem Archiv. Zu entscheiden in der Analyse.

---

# Analysis

> Erstellt in `/20-analyse` am 2026-09-26. Alle Befunde am Code im Worktree `issue-250`
> (HEAD `c4a6214`) verifiziert — keine Übernahme aus dem Vorgangstext.

## Type

**Feature** (Prozess-/Framework-Änderung, kein Defekt). Drei Teilmaßnahmen A/B/C.

## Verifizierte Befunde

### F1 — Der State kennt nur ZWEI Stufen, nicht drei (neu, entscheidungsrelevant)

`core/commands/00-intake.md` startet **Standard Track (Z. 79) und Full Process (Z. 86) mit
demselben Befehl**: `workflow.py start [name] --type feature`. Gültige Werte sind nur
`feature`, `bug`, `feature-fast` (`workflow.py:1034`).

→ **Kein Hook kann Standard von Full Process unterscheiden.** Ein „Budget pro Stufe" mit drei
Zeilen (`fast` / `standard` / `full`), wie der Vorgang es vorschlägt, ist heute mechanisch
nicht umsetzbar. Das ist eine **Vorbedingung für Teil B**, die im Vorgang nicht benannt ist.

### F2 — Die Stufen-Tabelle verspricht, was die Maschine nicht hält

`00-intake.md` Z. 114 ff.:

| Zeile in der Tabelle | Was der Code tut |
|---|---|
| `Adversary: Standard 1 Runde / Full 2+` | `adversary_dialog.py:34` `MIN_ROUNDS = 2` als harter **Boden**, ohne jede `workflow_type`-Kenntnis (grep: kein Treffer). Eine einzelne Runde ist unmöglich. |
| `Manuelle Validierung ✅ immer / ✅ immer / ✅ immer` | Korrekt — und genau das ist Teil A. |
| `TDD RED ❌ inline (Fast)` | Greift, `workflow.py:954` nimmt `feature-fast` aus. |

### F3 — Der schnelle Weg wird nicht umgangen, er wird nie gewählt

`workflow.py retro-list` über das Archiv:

| Workflow | Typ | Gesamt |
|---|---|---|
| fix-237-egress-guard-scratchpad | `feature` | 1117 min |
| fix-234-footer-command | `feature` | 250 min |
| fix-relative-hook-paths | `feature` | 180 min |

**Drei von drei** echten Bugfixes liefen als `feature`. Kein einziger Fast Track. Die Diagnose
des Vorgangs („die Stufen werden nicht durchgesetzt") ist genauer zu fassen: Es gibt keinen
Mechanismus, der eine gewählte Stufe *verletzt* — es gibt nur keinen, der die Stufe nach der
Wahl noch **spürbar** macht.

### F4 — `affected_files` ist ein toter Briefkasten → als Signal für Teil A ungeeignet

Das Feld wird in **11 Befehlen gelesen und angezeigt**, von `spec-writer` und
`30-write-spec.md` als „Liste aus Analyse" erwartet — aber **kein Codepfad und kein Befehl
füllt es**. Der einzige Schreibweg `set-affected-files` steht nur als Beispiel in
`80-workflow.md`. Beleg im echten Protokoll `2026-09-26_fix-237-...yaml`:
`scope_files_changed: 0` bei `scope_loc_delta: +182`.

Das ist bereits als **#247** erfasst (offen). → Teil A darf nicht auf `affected_files` bauen,
sonst hängt #250 an #247. Deterministische Alternative: die Dateiliste des laufenden
Arbeitsstands direkt aus `git` (Namensliste gegen HEAD plus unversionierte Dateien) — immer
vorhanden, keine Buchführung nötig.

### F5 — `is_new_ui` wird gesetzt, nie gelesen

`phase_listener.py:481` setzt das Feld, `workflow.py:537` initialisiert es. Grep über alle
Hooks, Befehle und Skripte: **keine einzige Leseposition.** Toter Code, als Sperr-Kriterium
unbrauchbar (bestätigt R4).

### F6 — `phase7_validate` ist kein Gate (bestätigt R7)

`workflow.py::_validate_transition` (Z. 947–1014) prüft: `context_file` ab phase2,
`spec_file`/`spec_approved`/ADR/Briefing ab phase4, RED-Artefakte ab phase6, VERIFIED-Verdict
ab phase8. **Für `phase7_validate` selbst: nichts.** Teil A braucht keine Hook-Änderung.

Die PO-Pflicht in Teil A besteht aus genau **drei Zeremonien**, alle prompt-/flag-getrieben:

1. erzwungener Tastendruck `/50-implement` (`skills/50-implement/SKILL.md`: `disable-model-invocation: true`)
2. erzwungener Tastendruck `/60-validate` (`skills/60-validate/SKILL.md`: `true`)
3. die Schlussfrage „Soll ich den Code committen?" (`core/commands/60-validate.md` Z. 243)

Alle drei widersprechen bereits der globalen Hausregel („PRs werden eigenständig gemergt.
Keine Merge-Frage. Niemals." / „Henning bekommt nie einen Shell-Befehl zum Eintippen").
**Teil A stellt damit keine neue Produktentscheidung dar, sondern beseitigt einen
Regelwiderspruch.**

### F7 — Es gibt bereits eine undifferenzierte Wanduhr-Bremse (bestätigt R2)

`post_implementation_gate.py`: `_BATCH_WINDOW_S = 15 * 60` in `phase6_implement`,
`_BYPASS_PHASES = {phase6b_adversary, phase7_validate, phase8_complete, phase0_idle}`.
Grep nach `workflow_type` / `feature-fast` in dieser Datei: **kein Treffer** — das Gate gilt
für alle Stufen gleich. Bei 39,8 min in der Baseline hat es mitten in der Umsetzung eine
PO-Freigabe erzwungen.

### F8 — R8 ist ohne Codeänderung erledigt

`workflow.py retro <name>` liest das Archiv-JSON und gibt **Typ und Gesamtdauer** aus
(verifiziert: `fix-234-footer-command` → `Typ: feature`, `Gesamt: 250.1 min`). Das Dauer-Feld
in `cmd_write_log` ist für die letzte Abnahme-Bedingung **nicht nötig**; der Nachweis
„#245/#246 kürzer als #237" führt über `retro` aus dem Archiv. Die in R8 offen gelassene
Frage ist damit entschieden: **kein neues Protokollfeld.**

### F9 — Die 26 Weckruf-Blöcke widersprechen der Werkzeugdokumentation selbst

26 Vorkommen bestätigt (13 in `core/commands/{20-analyse,30-write-spec,50-implement,60-validate}.md`,
13 in den generierten `skills/`), alle 180–600 s, alle unter der Überschrift
„**TIMEOUT-PFLICHT — sofort nach dem Spawn**". Kein Test prüft sie (Suche in `tests/` → leer).

Die Werkzeugbeschreibung von `ScheduleWakeup` sagt: das Werkzeug dient der Selbsttaktung im
`/loop`-Modus, und *„Do NOT schedule a short-interval wakeup to poll for background work you
started — when harness-tracked work finishes, you are re-invoked automatically, so polling is
wasted. Instead schedule a long fallback (1200s+)"*.

In dieser Analyse live beobachtet: Der Strategie-Agent meldete sich nach **144 s** selbst
zurück. Der von `20-analyse.md` Z. 107 vorgeschriebene 300-s-Weckruf wäre ins Leere gelaufen.
Er wurde deshalb bewusst nicht gesetzt — die Pflicht ist im Normalbetrieb wirkungslos, was die
vorletzte Abnahme-Bedingung des Vorgangs wörtlich verbietet.

## Affected Files (nach Teilauftrag)

### Teilauftrag 1 → #88 (Teil C, Weckrufe)

| Datei | Change | Beschreibung |
|---|---|---|
| `core/commands/20-analyse.md` | MODIFY | 3 Blöcke → 1 Rückfall ≥1200 s je Phase |
| `core/commands/30-write-spec.md` | MODIFY | 3 Blöcke → 1 |
| `core/commands/50-implement.md` | MODIFY | 3 Blöcke → 1 |
| `core/commands/60-validate.md` | MODIFY | 4 Blöcke → 1 |
| `skills/{20-analyse,30-write-spec,50-implement,60-validate}/SKILL.md` | GENERATE | `scripts/sync_skills.py`, nie Hand-Edit |
| `tests/test_wakeup_blocks.py` | CREATE | Obergrenze 1 Block je Befehl, Intervall ≥1200, Wort „TIMEOUT-PFLICHT" verboten |
| `CHANGELOG.md`, `.claude-plugin/plugin.json` | MODIFY | Eintrag + Versionsbump |

**Logik-Dateien: 5.** Umfang ≈ −40/+90 LoC. Risiko **niedrig** (Text, keine Gate-Logik).

### Teilauftrag 2 → #147 (Teil A, Validierung abstufen)

| Datei | Change | Beschreibung |
|---|---|---|
| `skills/50-implement/SKILL.md` | MODIFY | `disable-model-invocation: false` |
| `skills/60-validate/SKILL.md` | MODIFY | `disable-model-invocation: false` |
| `core/commands/40-tdd-red.md` | MODIFY | Auto-Chaining nach GREEN → `/50-implement` (Vorbild `fix-140`) |
| `core/commands/60-validate.md` | MODIFY | Schlussfrage → Ankündigung; Oberflächen-Prüfung vor dem PO-Block |
| `core/hooks/hook_utils.py` | MODIFY | Helfer `has_observable_surface()` — Dateiliste aus `git` gegen Musterliste |
| `config.yaml` | MODIFY | Block `observable_surface:` mit `enabled`, `patterns`, projektüberschreibbar |
| `tests/test_observable_surface.py` | CREATE | **Strenger Fall zuerst:** UI-Pfad in der Liste → Validierung bleibt Pflicht |
| `CHANGELOG.md`, `.claude-plugin/plugin.json` | MODIFY | Eintrag + Versionsbump |

**Logik-Dateien: 5** (+2 Frontmatter-Flips, +2 Buchführung). Umfang ≈ +130/−25 LoC.
Risiko **mittel** (R6: Lockerung an der Durchsetzungsmechanik).

### Teilauftrag 3 → neuer Vorgang (F1, Vorbedingung für B)

| Datei | Change | Beschreibung |
|---|---|---|
| `core/hooks/workflow.py` | MODIFY | Dritter Stufenwert, damit Standard ≠ Full im State |
| `core/commands/00-intake.md` | MODIFY | Full Process startet mit eigenem Typ; Tabelle auf F2 korrigiert |
| `core/hooks/adversary_dialog.py` | MODIFY | `MIN_ROUNDS` stufenabhängig, damit „Standard = 1 Runde" wahr wird |
| `tests/test_workflow_stages.py` | CREATE | Drei Stufen unterscheidbar; bestehende Fast-Track-Ausnahmen unverändert |

**Logik-Dateien: 4.** Umfang ≈ +90 LoC. Risiko **mittel**.

### Teilauftrag 4 → #182 (Teil B, Aufwandsbremse — reduziert)

| Datei | Change | Beschreibung |
|---|---|---|
| `core/hooks/workflow.py` | MODIFY | `record_transition()` meldet Stufe, verbrauchte Zeit, Runden, Wiedereintritte |
| `core/hooks/post_implementation_gate.py` | MODIFY | `_BATCH_WINDOW_S` stufenabhängig statt pauschal 15 min |
| `config.yaml` | MODIFY | `effort_budget:` je Stufe, mit `enabled`-Kill-Switch |
| `tests/test_effort_budget.py` | CREATE | Strenger Fall (Feature weiter gebremst) UND milder Fall |
| `CHANGELOG.md`, `.claude-plugin/plugin.json` | MODIFY | Eintrag + Versionsbump |

**Logik-Dateien: 4.** Umfang ≈ +140 LoC. Risiko **hoch** (R3/R6).

## Scope Assessment

| | Dateien (Logik) | LoC | Risiko |
|---|---|---|---|
| Gesamt in einem Auftrag | 18 | ≈ +450/−65 | hoch |
| **Geschnitten** | 5 / 5 / 4 / 4 | je ≤ 155 | niedrig / mittel / mittel / hoch |

Ein Auftrag verletzt die Hausregel (4–5 Dateien, ±250 LoC) um das Dreifache. Jeder der vier
Teilaufträge liegt darin.

## Technical Approach (Empfehlung)

**Reihenfolge: C → A → F1 → B.**

1. **C zuerst**, weil risikofrei und weil es Ballast aus genau den zwei Befehlsdateien
   entfernt, die A anschließend anfasst. C qualifiziert sich selbst als Fast Track und führt
   damit vor, was #250 fordert.
2. **A als zweites** — der größte spürbare Einzelposten, ohne Hook-Änderung (F6), mit fertigem
   Bauplan (`fix-140`: Flag-Flip + Auto-Chaining + Regressionstest).
3. **F1 als drittes**, weil ohne dritte Stufe im State jede Stufen-Differenzierung in B ins
   Leere greift.
4. **B zuletzt und reduziert.**

### Signal für „nichts Beobachtbares" (Teil A) — Entscheidung

Nicht `workflow_type` (wird gesetzt, wenn die Unsicherheit am größten ist), nicht `is_new_ui`
(F5: nie gelesen), nicht `affected_files` (F4: nie gefüllt, und es würde #250 an #247 hängen),
auch kein neues Spec-Feld (dieselbe Vergessens-Falle wie `is_new_ui`).

**Sondern: die tatsächlich geänderte Dateiliste aus `git`,** geprüft gegen eine
projektüberschreibbare Musterliste in `config.yaml`. Deterministisch, immer vorhanden, keine
Buchführung — „Regeln vor Modell". Richtung nach R4: **Default ist validieren.** Nur wenn die
Liste **keinen** Treffer hat und die Musterliste geladen werden konnte, entfällt der
inhaltslose PO-Block. Fehler beim Laden, leere Liste, unbekannte Endung → streng.

Was A **nicht** abschafft: die Validierungs-**Phase**. Die vier Prüf-Agenten, der
Regressionslauf und der Scope-Check laufen weiter. Weg fällt nur die Aufforderung an den PO,
etwas anzusehen, das es nicht gibt — und der Tastendruck, der keine Entscheidung trägt.

### Aufwandsbremse (Teil B) — Empfehlung: Sichtbarkeit + Rückfrage, keine Blockade der Prüfung

Belegt untauglich: ein Stundenbudget als Blockade (R1 — 82 % der Baseline sind PO-Wartezeit;
F7 — es existiert schon eine solche Bremse und sie hat genau diesen Fehler) und ein hartes
`max_adversary_rounds` (R3 — die dritte Runde fand die CRITICAL-Lücke).

Belastbar sind **Aktivitätszähler**, alle bereits im State vorhanden: `fix_loop_iterations`,
Wiedereintritte je Phase aus `phase_transitions`, Adversary-Runden aus dem Dialogdokument.
Vorschlag: `record_transition()` meldet bei jedem Phasenwechsel Stufe, verbrauchte Zeit und
Zählerstände; bei Überschreitung des Stufen-Budgets **eine Rückfrage an den PO**,
protokolliert — aber die Gegenprüfung wird nie abgeschnitten. Stattdessen wird die
**bestehende** Bremse (F7) stufenabhängig gemacht, statt eine zweite daneben zu stellen.

Hinweis zur Abnahme-Bedingung „Überschreitet ein Workflow sein Budget, wird der PO gefragt
statt still weitergearbeitet": Sie bleibt erfüllt. Nicht erfüllt wird die Lesart „der Ablauf
stoppt hart" — das ist die PO-Entscheidung unten.

## Dependencies

- `scripts/sync_skills.py` → `scripts/release_check.py` bricht bei Drift ab: nach jeder
  Änderung an `core/commands/` neu generieren (betrifft C und A)
- `setup.py` Z. 1010–1017 und `core/hooks/alias_sync.py` Z. 40, 107 lesen
  `disable-model-invocation` → der Flag-Flip in A ändert die Alias-Strategie automatisch
  (Thin-Redirect statt Full-Embed), ohne Codeänderung; Historie #55/#56/#87 beachten
- `tests/test_setup_command_aliases.py`, `tests/test_setup_alias_sync_150.py`,
  `tests/test_skill_stop_instruction.py`, `tests/test_clear_checkpoint_blocks.py` müssen
  unverändert grün bleiben
- **#247 blockiert nichts**, solange A die `git`-Dateiliste nutzt statt `affected_files`
- Pytest nur im eigenen venv mit `pytest` **und** `pyyaml` (sonst stiller Leerlauf)

## PO-Entscheidungen (2026-09-26, bestätigt)

- [x] **Schnitt:** vier getrennte Aufträge in der Reihenfolge **#88 → #147 → #254 → #182**,
      jeder mit eigener Spec und eigener Auslieferung. Keine Bündelung.
- [x] **Teil B Härtegrad:** **Rückfrage bei Überschreitung, protokolliert — die Gegenprüfung
      wird nie abgeschnitten.** Zusätzlich wird die bestehende 15-Minuten-Bremse
      (`post_implementation_gate.py`, F7) stufenabhängig gemacht, statt eine zweite daneben zu
      stellen. Eine harte Blockade ist ausdrücklich verworfen (R3).

## Open Questions

Keine offenen Fragen. Die nächste Spec (`/30-write-spec`) betrifft ausschließlich
**Teilauftrag 1 → #88** (Weckruf-Blöcke); die Teilaufträge 2–4 bekommen je eine eigene Spec
in einem eigenen Workflow.
