---
entity_id: fix-147-validierung-abstufen
type: feature
created: 2026-09-27
updated: 2026-09-27
status: draft
version: "1.1"
tags: [gates, skills, po-decision, aliases]
workflow: fix-147-validierung-abstufen
---

# PO-Tastendrücke nach Freigabe abschaffen (Issue #147, Hälfte 1 von #250)

## Approval

- [ ] Approved

## Purpose

Nach der Spec-Freigabe muss der PO heute zweimal einen Slash-Befehl selbst eintippen —
`/50-implement` nach der TDD-RED-Phase und `/60-validate` nach der Implementierung —,
obwohl an beiden Stellen keine neue Entscheidung fällt: Die Entscheidung ist mit
`approved` bzw. mit `go` bereits getroffen. Diese Spec liefert **Hälfte 1** von Issue
#147 (PO-Entscheidung vom 2026-09-27, siehe ADR unten): Sie schafft genau diese zwei
Tastendrücke ab, indem sie den Skill-Tool-Selbstaufruf freischaltet und die
Übergangs-Anweisungen von „warte auf den User" auf „ruf dich selbst auf" umstellt.
Die dahinterliegende Validierungs-**Phase** (vier automatische Prüfagenten,
docs-updater, Regressionslauf) bleibt inhaltlich unverändert. Die Erkennung, ob eine
Änderung überhaupt eine beobachtbare Oberfläche hat, ist **Hälfte 2** (Issue #260) und
nicht Teil dieser Spec.

## Source

- **File:** `core/commands/40-tdd-red.md`
- **Identifier:** Abschnitt „## Next Step" — Satz „**NICHT** selbst mit der
  Implementierung beginnen. Warte bis der User `/50-implement` tippt."
- **File:** `core/commands/50-implement.md`
- **Identifier:** Step 6 „User-Freigabe der GREEN-Ergebnisse (PFLICHT)" und Abschnitt
  „## Next Step" — Sätze „Danach folgt die Ausgabe an den User — dann **STOPP**." und
  „**NICHT** selbst mit der Validierung beginnen. Warte bis der User `/60-validate`
  tippt."
- **File:** `skills/50-implement/SKILL.md`, `skills/60-validate/SKILL.md`
- **Identifier:** YAML-Frontmatter-Feld `disable-model-invocation`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/alias_sync.py` (`embeds_full_skill`, `alias_content`, `skill_names`, `find_stale_aliases`) | bestehendes Modul | Einzige Quelle für den Soll-Inhalt einer `.claude/commands/<name>.md`-Datei. Nach dem Flag-Flip liefert `alias_content()` für `50-implement`/`60-validate` automatisch den 6-Zeilen-Thin-Redirect statt der Vollkopie — ohne Code-Änderung an `alias_sync.py` selbst. `find_stale_aliases()` vergleicht genau gegen dieses Soll und ist bereits für den Fall gebaut, dass ein Skill von gesperrt auf entsperrt wechselt (Docstring dort wörtlich). |
| `scripts/sync_skills.py` (`extract_frontmatter`, `expected_skills`, Versions-Marker) | bestehendes Skript | Erzeugt `skills/<name>/SKILL.md` aus `core/commands/<name>.md`. **Wichtig:** `extract_frontmatter()` übernimmt das YAML-Frontmatter (inkl. `disable-model-invocation`) unverändert aus der jeweils schon vorhandenen `SKILL.md` — nicht aus `core/commands/`, dort existiert dieses Feld gar nicht. Der Flag-Flip muss deshalb direkt in `skills/50-implement/SKILL.md` und `skills/60-validate/SKILL.md` erfolgen (siehe Korrektur in „Implementation Details"). Zusätzlich hängt das Skript an jede erzeugte `SKILL.md` einen Versions-Marker an — ein Versionsbump ändert dadurch mechanisch **alle 16** Dateien unter `skills/`, nicht nur die drei fachlich betroffenen. |
| `setup.py::refresh_command_aliases()` | bestehende Funktion | Erneuert ausschließlich bereits vorhandene, markierte, veraltete Alias-Dateien in `<scope>/.claude/commands/` gegen `alias_content()` — legt laut Docstring **nie** eine neue Datei an (deshalb auch für `~` unbedenklich, Issue #87). Aufgerufen über `python3 setup.py . --refresh-aliases`, holt in einem Rutsch sowohl die beiden jetzt entsperrten Vollkopien (`50-implement`, `60-validate` → Thin-Redirect) als auch die vier weiterhin gesperrten (`70-deploy`, `80-workflow`, `81-add-artifact`, `99-reset` → aktualisierter Versions-Marker) nach. |
| `scripts/release_check.py` (`check_readme_version`, `check_version_match`) | bestehendes Skript | `check_readme_version` bricht ab, wenn `README.md` nicht dieselbe Version wie `plugin.json` nennt; `check_version_match` verlangt einen datierten (nicht `[Unreleased]`) obersten CHANGELOG-Eintrag, der mit `plugin.json` übereinstimmt. Beides bindet den Versionsbump dieser Spec direkt an drei Dateien. |
| `tests/test_readme_version_195.py` | bestehender Test | `test_readme_matches_plugin_manifest` schlägt fehl, wenn `README.md` Z. 5 nicht auf den neuen Versionsstand mitgezogen wird. |
| `tests/test_setup_alias_sync_150.py`, `tests/test_setup_command_aliases.py` | bestehende Tests | Parametrisieren generisch über die aktuell in `skills/` liegenden Dateien und decken den Flag-Flip dadurch automatisch ab — mit einer Ausnahme: `test_updates_existing_marker_file_for_disabled_model_invocation_skill` (Z. 88/96) verwendet `50-implement` hart codiert als Beispiel für einen weiterhin gesperrten Skill. Dieses Beispiel muss auf einen nach dem Flip noch gesperrten Skill (`70-deploy`) umgestellt werden, sonst bricht der Test (siehe Scope). |
| `tests/test_clear_checkpoint_blocks.py` | bestehende Tests | Prüft die `/clear`-Checkpoint-Blöcke in `core/commands/*.md` strukturell. Muss unverändert grün bleiben — die neuen Chaining-Anweisungen stehen außerhalb dieser Blöcke, exakt wie bei fix-140. |
| `tests/test_skill_stop_instruction.py` | bestehender Test (wird umgedreht) | Prüfte bisher die Existenz der STOPP-Sätze; nach dieser Spec prüft er umgekehrt die Existenz und Position der Chaining-Anweisungen. |
| `core/hooks/bash_gate.py` (Commit-Gate, Z. 636–660), `core/hooks/edit_gate.py` (RED-Artefakt-Pflicht, Z. 530), `core/hooks/workflow.py::_validate_transition` (Z. 947–1014) | bestehende Hooks, **unverändert** | Belegen, dass die eigentliche Durchsetzung (Commit nur mit VERIFIED, Code-Edit nur mit registrierten RED-Artefakten) nie am getippten Slash-Befehl hing — der Flag-Flip kann diese Gates nicht umgehen, weil sie ihn nie geprüft haben. |
| `docs/specs/fix-140-po-decision-gates.md` | bestehende Spec | Baut denselben Mechanismus für den vorherigen Übergang (`approved` → `/40-tdd-red`) und begründet zugleich, warum `/50-implement`/`/60-validate` dort bewusst ausgenommen wurden — diese Begründung wird hier teilweise revidiert (siehe ADR). |

## Scope

| File | Change Type | Description |
|------|-------------|-------------|
| `skills/50-implement/SKILL.md` | MODIFY | Frontmatter direkt editieren: `disable-model-invocation: true` → `false`. Body wird danach per `sync_skills.py` aus `core/commands/50-implement.md` neu erzeugt. |
| `skills/60-validate/SKILL.md` | MODIFY | Frontmatter direkt editieren: `disable-model-invocation: true` → `false`. Body wird danach per `sync_skills.py` neu erzeugt (unverändert, nur Versions-Marker aktualisiert). |
| `skills/*/SKILL.md` (alle 16 Skills) | MODIFY (mechanisch) | Versions-Marker `⚙ /<name> · agent-os-openspec <version>` ändert sich mit dem Bump auf 3.33.0 — Nebenwirkung von `python3 scripts/sync_skills.py`, kein fachlicher Eingriff außer bei den zwei oben genannten Dateien. |
| `core/commands/40-tdd-red.md` | MODIFY | STOPP-Satz im Abschnitt „## Next Step" durch Chaining-Anweisung ersetzen (Übergang zu `/50-implement`), außerhalb des `/clear`-Checkpoint-Blocks. |
| `core/commands/50-implement.md` | MODIFY | Zwei Stellen im Abschnitt „## Next Step": „dann **STOPP**." sowie den STOPP-Satz für `/60-validate` durch Chaining-Anweisung ersetzen, außerhalb des `/clear`-Checkpoint-Blocks, unverändert **nach** Adversary-VERIFIED-Vorbedingung und Step 6 (GREEN-Freigabe `go`). |
| `.claude/commands/50-implement.md` | MODIFY | Vollkopie (373 Z.) → 6-Zeilen-Thin-Redirect. Soll-Inhalt ist ausschließlich `alias_sync.alias_content("50-implement", skill_text)`, erzeugt durch `python3 setup.py . --refresh-aliases`, nicht von Hand getippt. |
| `.claude/commands/60-validate.md` | MODIFY | Vollkopie (282 Z.) → 6-Zeilen-Thin-Redirect. Soll-Inhalt ausschließlich `alias_sync.alias_content("60-validate", skill_text)`, ebenfalls über `--refresh-aliases`. |
| `.claude/commands/70-deploy.md`, `.claude/commands/80-workflow.md`, `.claude/commands/81-add-artifact.md`, `.claude/commands/99-reset.md` | MODIFY (mechanisch) | Bleiben Vollkopien (ihre Skills bleiben gesperrt), aber ihr eingebetteter Versions-Marker ändert sich mit dem Bump — durch denselben `--refresh-aliases`-Lauf nachgeführt, kein Handediting. |
| `tests/test_skill_stop_instruction.py` | MODIFY | Umkehr: prüft danach die Chaining-Anweisungen (Existenz + Position nach Phasenwechsel) für `40-tdd-red` UND `50-implement`, statt der STOPP-Sätze. Cross-Datei-Konsistenz Skill↔Command bleibt geprüft. |
| `tests/test_repo_own_aliases_147.py` | CREATE | (a) `alias_sync.find_stale_aliases(skills_dir, commands_dir, loaded_version=None)` liefert eine leere Liste (deckt alle sechs betroffenen Alias-Dateien in einem Vertrag ab). (b) Verbotene Doku-Formulierungen („User tippt /50-implement", „Manuelle Validierung") kommen in den unten genannten Doku-Dateien nicht mehr vor. |
| `tests/test_setup_command_aliases.py` | MODIFY | `test_updates_existing_marker_file_for_disabled_model_invocation_skill` nutzt `70-deploy` statt `50-implement` als Beispiel für einen weiterhin gesperrten Skill (sonst bricht der Test nach dem Flag-Flip, siehe Dependencies). |
| `README.md` | MODIFY | Z. 5 (`**Version**: 3.32.0` → `3.33.0`) sowie kurze Ergänzung am Workflow-Diagramm/der Command-Tabelle, dass `/50-implement`/`/60-validate` jetzt automatisch verkettet werden. |
| `CLAUDE.md` | MODIFY | Z. 5 (`**Version**: 3.32.0` → `3.33.0`) — kein Test erzwingt das, aber es ist die erste Zeile jeder Sitzung. |
| `docs/WORKFLOW_GUIDE.md` | MODIFY | Z. 386 „User tippt /50-implement" → automatischer Selbstaufruf; Z. 153/469 „Manuelle Validierung"/„Manuelle Tests" → entfällt (die Phase ist automatisiert, siehe N2 in der Analyse). |
| `core/commands/00-intake.md` | MODIFY | Tabellenzeile Z. 114: „Manuelle Validierung ✅ immer" → „Validierung ✅ immer". |
| `CHANGELOG.md` | MODIFY | Neuer Eintrag unter `## [3.33.0] - 2026-09-27` (datiert, **nicht** unter `[Unreleased]` — `release_check.py::check_version_match` lehnt einen `[Unreleased]`-Kopf ab). |
| `.claude-plugin/plugin.json` | MODIFY | Versionsbump `3.32.0` → `3.33.0` (MINOR, additiv). |

**Estimated Changes:** ≈ +90/−690 LoC an fachlicher Handarbeit (davon −655 gelöschte
Vollkopien in `.claude/commands/`), plus mechanische Versions-Marker-Aktualisierung in
allen 16 `skills/*/SKILL.md` und den vier verbleibenden gesperrten
`.claude/commands/*.md`-Kopien (je eine Zeile, erzeugt durch `sync_skills.py` bzw.
`setup.py --refresh-aliases`, kein Bestandteil des von Hand geschriebenen Deltas — im
Review als ein 20-Dateien-Nebeneffekt-Diff erkennbar, nicht als 20 eigenständige
Änderungen). Risiko **niedrig**: kein Hook-Code wird geändert, keine neue Logik
entsteht; Commit-Gate, RED-Artefakt-Pflicht, GREEN-Freigabe und Adversary-Dialog
bleiben vollständig unangetastet (siehe Dependencies und ADR).

## Implementation Details

### 1. Flag-Flip — direkt in den Skill-Dateien, nicht in `core/commands/`

Korrektur zur ursprünglichen Annahme: `core/commands/50-implement.md` und
`core/commands/60-validate.md` haben **kein** YAML-Frontmatter (geprüft, kein Treffer
für `disable-model-invocation` in beiden Dateien). `disable-model-invocation` ist reine
Skill-Metadaten und existiert nur in `skills/<name>/SKILL.md`. `scripts/sync_skills.py`
(`extract_frontmatter`) liest das Frontmatter beim Regenerieren aus der **bereits
vorhandenen** `SKILL.md` und schreibt es unverändert zurück — der Body kommt aus
`core/commands/`, das Frontmatter nicht. Der Flag-Flip erfolgt deshalb — wie schon bei
`skills/40-tdd-red/SKILL.md` in fix-140 — als direkte Bearbeitung der beiden
`SKILL.md`-Dateien:

```yaml
---
description: "Implement (TDD GREEN)"
disable-model-invocation: false
---
```

(analog für `skills/60-validate/SKILL.md`).

### 2. Chaining `/40-tdd-red` → `/50-implement`

In `core/commands/40-tdd-red.md`, Abschnitt „## Next Step", ersetzt eine
Chaining-Anweisung den Satz „**NICHT** selbst mit der Implementierung beginnen. Warte
bis der User `/50-implement` tippt." — nach dem Vorbild aus
`docs/specs/fix-140-po-decision-gates.md` Abschnitt „### 2.":

> Ohne `/clear` in derselben Session: Rufe den Skill `50-implement` jetzt sofort selbst
> auf — warte nicht auf eine weitere User-Eingabe, die registrierten RED-Artefakte sind
> bereits die Voraussetzung, keine zusätzliche Entscheidung steht mehr aus.
>
> Mit `/clear` dazwischen: Der Checkpoint-Block oben zeigt den regulären Wiedereinstieg
> über den expliziten Befehl `/50-implement #<N>`.

Die Anweisung steht **nach** „### Ausgabe B: Negativ-Block" (dieselbe Position wie der
bisherige STOPP-Satz) — also außerhalb des `/clear`-Checkpoint-Blocks
(„### Checkpoint prüfen" bis „### Ausgabe B"), damit `test_clear_checkpoint_blocks.py`
strukturell unangetastet bleibt.

### 3. Chaining `/50-implement` → `/60-validate`

In `core/commands/50-implement.md` betrifft das zwei Stellen im Abschnitt
„## Next Step":

- „Wenn Adversary VERIFIED (oder AMBIGUOUS mit User-OK): … Danach folgt die Ausgabe an
  den User — dann **STOPP**." → „… Danach folgt die Ausgabe an den User, danach rufst
  du `/60-validate` selbst auf (siehe unten)."
- „**NICHT** selbst mit der Validierung beginnen. Warte bis der User `/60-validate`
  tippt." → dieselbe Zwei-Fälle-Formulierung wie in Punkt 2, für `60-validate`.

**Die Vorbedingung ändert sich nicht:** Der Selbstaufruf ist weiterhin erst erlaubt,
nachdem (a) der Adversary-Dialog stattgefunden hat und das Verdict VERIFIED lautet
(bzw. AMBIGUOUS mit ausdrücklicher User-Entscheidung — Circuit Breaker bei 3
Iterationen bleibt bestehen) und (b) der PO die GREEN-Ergebnisse aus Step 6 mit `go`
freigegeben hat. Der Flag-Flip ersetzt nur den Tastendruck, der auf diese beiden
Stationen folgt — er schafft keinen Weg an ihnen vorbei.

### 4. Versionsbump zieht 16 generierte Skills und alle sechs Alias-Dateien nach

`.claude-plugin/plugin.json` wird von 3.32.0 auf 3.33.0 gehoben (MINOR, additiv). Das
wirkt weiter als nur auf diese eine Datei:

- `README.md` Z. 5 (`**Version**: 3.32.0`) und `CLAUDE.md` Z. 5 (dieselbe Zeile)
  müssen auf 3.33.0 mitgezogen werden. Für `README.md` erzwingt das
  `scripts/release_check.py::check_readme_version` sowie
  `tests/test_readme_version_195.py::test_readme_matches_plugin_manifest`; für
  `CLAUDE.md` gibt es keinen Test, sie ist aber die erste Zeile jeder Sitzung und wird
  deshalb ebenfalls angepasst.
- `scripts/sync_skills.py` hängt an jede erzeugte `SKILL.md` einen Versions-Marker
  (`⚙ /<name> · agent-os-openspec <version>`) an. Ein Bump ändert dadurch **alle 16**
  Dateien unter `skills/`, nicht nur die drei fachlich betroffenen — rein mechanisch,
  ein `python3 scripts/sync_skills.py`-Lauf nach dem Versionsbump erledigt das für alle
  auf einmal.
- Weil sich der Versions-Marker in jedem Skill ändert, weichen danach auch die
  Vollkopien der weiterhin gesperrten Skills von ihrem Soll ab:
  `.claude/commands/70-deploy.md`, `80-workflow.md`, `81-add-artifact.md`,
  `99-reset.md`. AC-7 verlangt eine leere Ergebnisliste von `find_stale_aliases()` für
  JEDEN Skill — ohne Nachführung wäre die neue Prüfung schon bei ihrer Einführung rot.

**Reihenfolge ist Pflicht**, sonst wird gegen ein veraltetes Soll erneuert:

1. Flag-Flip in `skills/50-implement/SKILL.md` / `skills/60-validate/SKILL.md`
   (Abschnitt 1) und Chaining-Anweisungen in `core/commands/` (Abschnitte 2/3).
2. `python3 scripts/sync_skills.py` (Body + Frontmatter-Erhalt für alle Skills, jetzt
   mit den neuen Chaining-Anweisungen und noch der alten Versionsnummer).
3. Versionsbump in `.claude-plugin/plugin.json`, `README.md`, `CLAUDE.md`,
   `CHANGELOG.md` (neuer, datierter Eintrag `## [3.33.0] - 2026-09-27`).
4. `python3 scripts/sync_skills.py` erneut ausführen — jetzt mit der neuen Version im
   Marker, betrifft alle 16 `skills/*/SKILL.md`.
5. `python3 setup.py . --refresh-aliases` (Scope: dieses Repository) — erneuert
   ausschließlich bereits vorhandene, markierte, veraltete Alias-Dateien
   (`setup.py::refresh_command_aliases`, nutzt `alias_sync.find_stale_aliases` gegen
   genau das Soll aus `alias_content()`). Das deckt in einem Rutsch sowohl die beiden
   jetzt entsperrten Vollkopien (`50-implement`, `60-validate` → Thin-Redirect) als
   auch die vier weiterhin gesperrten (`70-deploy`, `80-workflow`, `81-add-artifact`,
   `99-reset` → aktualisierte Vollkopie mit neuem Versions-Marker) ab. Es wird dabei
   keine Alias-Datei von Hand editiert und keine neue Datei angelegt
   (`refresh_command_aliases` legt laut Docstring „NIE eine Datei an" — sicher auch für
   `~`, Issue #87).

### 5. Testumbau

`tests/test_skill_stop_instruction.py` wird nicht gelöscht, sondern umgedreht: Er
beweist danach für **beide** Übergänge (`40-tdd-red`→`50-implement` UND
`50-implement`→`60-validate`), dass auf dem Skill-Tool-Pfad (der ausschließlich
`skills/*/SKILL.md` liest, nie `core/commands/*.md`) die jeweilige
Chaining-Anweisung vorhanden ist und **nach** dem zugehörigen Phasenwechsel steht
(`$WF phase phase6_implement` bzw. `$WF phase phase7_validate`) — dieselbe
Positionslogik wie zuvor, mit umgekehrtem Vorzeichen. Die
Skill-↔Command-Konsistenzprüfung bleibt erhalten, jetzt für die Chaining-Sätze statt
für die STOPP-Sätze.

`tests/test_repo_own_aliases_147.py` (neu) deckt zwei bislang ungeprüfte Lücken ab:
(a) `alias_sync.find_stale_aliases(skills_dir, commands_dir, loaded_version=None)`
liefert eine leere Liste — derselbe Vertrag, den `setup.py::refresh_command_aliases`
selbst nutzt, hier aber gegen die tatsächlichen Dateien in diesem Repository statt
gegen `tmp_path` geprüft. Die bestehenden Alias-Tests vergleichen nur gegen frisch
erzeugte `tmp_path`-Dateien (`tests/test_setup_alias_sync_150.py` Z. 51–64), und
`scripts/release_check.py` prüft nur `skills/` gegen `core/commands/`, nie die
repo-eigenen Alias-Dateien — genau in dieser Lücke waren die beiden Vollkopien
verrottet. (b) die drei angepassten Doku-Stellen enthalten die Formulierungen „User
tippt /50-implement" bzw. „Manuelle Validierung"/„Manuelle Tests" nicht mehr.

`tests/test_setup_command_aliases.py::test_updates_existing_marker_file_for_disabled_model_invocation_skill`
hat `50-implement` bisher hart codiert als Beispiel für einen Skill mit
`disable-model-invocation: true`. Nach dem Flag-Flip trifft das nicht mehr zu, der Test
würde den falschen Zweig prüfen und fehlschlagen. Das Beispiel wird auf `70-deploy`
umgestellt (bleibt nach dieser Spec weiterhin gesperrt) — eine Zeile, keine
Logikänderung.

### 6. Doku

`README.md`, `docs/WORKFLOW_GUIDE.md` (Z. 47, 51, 129, 153, 386, 468–469),
`core/commands/00-intake.md` (Z. 114) werden so angepasst, dass `/50-implement` und
`/60-validate` nicht mehr als vom PO zu tippender Schritt bzw. als „manuelle
Validierung" beschrieben sind — die Phase besteht faktisch aus vier automatischen
Prüfagenten und dem docs-updater (siehe Purpose). `CHANGELOG.md` bekommt den unter
Abschnitt 4 beschriebenen datierten `[3.33.0]`-Eintrag, `.claude-plugin/plugin.json`
den Versionsbump.

## Expected Behavior

- **Input:** Der Workflow ist in `phase5_tdd_red` mit registrierten RED-Artefakten,
  Claude schließt die Phase ab (kein `/clear` dazwischen).
- **Output:** Claude ruft den Skill `50-implement` selbst über das Skill-Tool auf, ohne
  dass der User `/50-implement` eingibt. Nach VERIFIED-Verdict und GREEN-Freigabe
  (`go`) ruft Claude analog den Skill `60-validate` selbst auf, ohne dass der User
  `/60-validate` eingibt.
- **Side effects:** `setup.py::generate_command_aliases()` erzeugt für `50-implement`
  und `60-validate` ab sofort Thin-Redirect-Aliase statt Full-Embed-Aliase (automatische
  Folge des Flag-Flips). Keine Änderung an `core/hooks/bash_gate.py`,
  `edit_gate.py`, `tdd_enforcement.py` oder `workflow.py::_validate_transition` — alle
  bestehenden Gates (Commit nur mit VERIFIED, Edit nur mit RED-Artefakten) bleiben exakt
  wie vorher.

## Known Limitations

- **Issue #260 ist bewusst nicht Teil dieser Spec.** Die Erkennung, ob eine Änderung
  überhaupt eine beobachtbare Oberfläche hat (Musterlisten `surface_patterns`/
  `non_surface_patterns`, Konfigurationsblock in `config.yaml`, bedingte Schlussfrage in
  `/60-validate`), trägt laut PO-Entscheidung vom 2026-09-27 das gesamte Risiko für
  Fremdprojekte und wird als eigener Auftrag mit eigener Gegenprüfung ausgeliefert.
  Diese Spec ändert an der Schlussfrage „Soll ich den Code committen?" in
  `core/commands/60-validate.md` nichts.
- **Wirkungsnachweis ist mechanisch, nicht durch Selbstaufruf in dieser Sitzung.** Der
  Flag-Flip wirkt auf das Skill-Tool erst, wenn der Harness die Plugin-Kopie neu
  einliest; die laufende Sitzung arbeitet gegen den bei Sitzungsstart eingefrorenen
  Stand, und die Liste aufrufbarer Skills steht für eine Sitzung fest. Der Nachweis
  erfolgt deshalb über Dateizustand (Frontmatter, Alias-Soll, Position der
  Chaining-Anweisung im generierten Skill) und den umgedrehten Regressionstest — nicht
  durch einen Selbstaufruf im selben Lauf. `fix-140-po-decision-gates.md` hat für
  denselben Mechanismus dieselbe Beweisform genutzt.
- **Asymmetrie zu `60-validate` ist beabsichtigt.** `60-validate` selbst bekommt keinen
  weiteren Auto-Chaining-Übergang (es ist die letzte automatische Phase vor der
  Commit-Entscheidung) — die PO-Beteiligung dort (Schlussfrage „Soll ich den Code
  committen?") bleibt unverändert und ist nicht Gegenstand dieser Spec.
- **Parallele Auslieferung #253 hebt die Version bewusst nicht an.** Issue #253 läuft
  parallel und lässt `plugin.json`/`CHANGELOG.md` unangetastet, um Merge-Kollisionen zu
  vermeiden. Diese Spec hebt die Version dagegen auf 3.33.0 an (nötig, weil der
  Versions-Marker und `release_check.py` das verlangen). Treffen beide Auslieferungen
  aufeinander, kollidieren `plugin.json`, `README.md`, `CLAUDE.md` und die
  Versions-Marker in allen 16 `skills/*/SKILL.md` textuell. Das ist beherrschbar (rein
  mechanischer Merge-Konflikt in Versionszeilen, kein inhaltlicher Widerspruch), aber
  wer zuletzt mergt, muss den Versions-Marker erneut mit `sync_skills.py` +
  `--refresh-aliases` durchlaufen lassen.
- **Blast Radius:** `skills/50-implement/SKILL.md` und `skills/60-validate/SKILL.md`
  sind Kern-Gate-Dateien, wirksam für alle Konsumenten-Projekte beim nächsten
  Plugin-Update. Risiko ist gering, weil ausschließlich der Selbstaufruf-Mechanismus
  geändert wird — Commit-Gate, RED-Artefakt-Pflicht und Adversary-Dialog bleiben
  unverändert (siehe Dependencies).

## Definition of Done

Fertig ist diese Änderung, wenn ein nicht-technischer Product Owner nach der
Spec-Freigabe **keinen Workflow-Befehl mehr selbst eintippen muss**. Die einzigen
Momente, an denen er noch etwas tut, sind: die Freigabe der Spec (`approved`), das
`go` zu den fertigen GREEN-Ergebnissen, und — falls der Adversary-Dialog AMBIGUOUS
liefert — die Entscheidung, wie damit umgegangen wird. Konkret:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Nach `go` folgt die Validierung erkennbar ohne weiteren Tastendruck des PO — er
  sieht nur noch die Ergebnis-Zusammenfassungen der Phasen, keine Aufforderung, selbst
  `/50-implement` oder `/60-validate` einzugeben
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (voller Regressionslauf grün,
  inklusive `scripts/release_check.py` und `scripts/sync_skills.py --check`)

## Acceptance Criteria

- **AC-1:** Given `skills/50-implement/SKILL.md` und `skills/60-validate/SKILL.md` vor
  der Umsetzung mit `disable-model-invocation: true` / When das Frontmatter beider
  Dateien nach Umsetzung gelesen wird / Then steht in beiden exakt
  `disable-model-invocation: false`.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-2:** Given `core/commands/` und `skills/` nach Umsetzung / When
  `python3 scripts/sync_skills.py --check` bzw. `python3 scripts/release_check.py`
  ausgeführt wird / Then meldet keines der beiden Skripte Drift.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-3:** Given `core/commands/40-tdd-red.md` und das daraus erzeugte
  `skills/40-tdd-red/SKILL.md` / When beide Dateien nach Umsetzung gelesen werden /
  Then enthalten beide die Chaining-Anweisung für den Übergang zu `/50-implement`, sie
  steht im Skill **nach** `$WF phase phase6_implement`, und der Satz „**NICHT** selbst
  mit der Implementierung beginnen. Warte bis der User `/50-implement` tippt." kommt in
  keiner der beiden Dateien mehr vor.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-4:** Given `core/commands/50-implement.md` und das daraus erzeugte
  `skills/50-implement/SKILL.md` / When beide Dateien nach Umsetzung gelesen werden /
  Then enthalten beide die Chaining-Anweisung für den Übergang zu `/60-validate`, sie
  steht im Skill **nach** `$WF phase phase7_validate`, und der Satz „**NICHT** selbst
  mit der Validierung beginnen. Warte bis der User `/60-validate` tippt." kommt in
  keiner der beiden Dateien mehr vor.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-5:** Given `core/commands/50-implement.md` und `skills/50-implement/SKILL.md`
  nach Umsetzung / When die Reihenfolge der Abschnitte geprüft wird / Then steht die
  Vorbedingung „Adversary-Verdict VERIFIED (oder AMBIGUOUS mit User-Entscheidung) UND
  GREEN-Freigabe `go` durch den User" unverändert **vor** der neuen
  Chaining-Anweisung — der Selbstaufruf ersetzt nur den Tastendruck danach, keine der
  beiden Stationen.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-6:** Given die Chaining-Anweisungen aus AC-3/AC-4 in `core/commands/40-tdd-red.md`
  und `core/commands/50-implement.md` / When die Dateien nach Umsetzung gelesen werden /
  Then stehen beide Anweisungen außerhalb der Abschnitte „### Checkpoint prüfen
  (Anweisung an dich — nicht ausgeben)" bis „### Ausgabe B: Negativ-Block (mindestens
  eine Vorbedingung verletzt)" — die `/clear`-Checkpoint-Blöcke bleiben strukturell
  identisch zum Vorher-Stand.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-7:** Given `skills/` und `.claude/commands/` in diesem Repository nach
  Umsetzung (inkl. Versionsbump und `python3 setup.py . --refresh-aliases`) / When
  `alias_sync.find_stale_aliases(skills_dir, commands_dir, loaded_version=None)`
  aufgerufen wird / Then liefert der Aufruf eine leere Liste — für jeden Skill
  entspricht `.claude/commands/<name>.md` exakt `alias_content(name, skill_text)`,
  insbesondere sind `50-implement.md` und `60-validate.md` jetzt Thin-Redirects und
  `70-deploy.md`/`80-workflow.md`/`81-add-artifact.md`/`99-reset.md` tragen den
  aktuellen Versions-Marker.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-8:** Given `tests/test_setup_command_aliases.py` nach Anpassung des
  hartcodierten Beispiels auf `70-deploy` / When
  `pytest tests/test_setup_command_aliases.py tests/test_setup_alias_sync_150.py`
  ausgeführt wird / Then laufen beide Dateien grün, ohne dass ihre generische
  Parametrisierungslogik verändert wurde.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-9:** Given `README.md`, `docs/WORKFLOW_GUIDE.md` und `core/commands/00-intake.md`
  nach Umsetzung / When die Dateien nach den Formulierungen „User tippt /50-implement",
  „Manuelle Validierung" und „Manuelle Tests, Integration-Tests, UI-Checks" durchsucht
  werden / Then kommt keine dieser Formulierungen mehr vor.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-10:** Given `.claude-plugin/plugin.json`, `README.md`, `CLAUDE.md` und
  `CHANGELOG.md` nach Umsetzung / When `python3 scripts/release_check.py` ausgeführt
  wird / Then meldet es Version `3.33.0` konsistent zwischen `plugin.json` und
  `README.md` (`check_readme_version`) sowie einen datierten, mit `plugin.json`
  übereinstimmenden obersten CHANGELOG-Eintrag (`check_version_match`, kein
  `[Unreleased]`-Kopf), und `CLAUDE.md` Z. 5 nennt ebenfalls `3.33.0`.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*
- **AC-11:** Given der volle Testlauf nach Umsetzung / When
  `pytest tests/ -q` ausgeführt wird / Then läuft die gesamte Suite grün, ohne dass
  ein bestehender Test außer den in dieser Spec genannten angepasst werden musste.
  - Test: *(wird nach der TDD-RED-Phase eingetragen)*

## Test Plan

Pytest gibt es nur im projekteigenen venv, `pyyaml` ist Pflicht (sonst brechen drei
Testmodule schon beim Einsammeln ab):

```
/opt/homebrew/bin/python3.13 -m venv "$SCRATCHPAD/venv"
"$SCRATCHPAD/venv/bin/pip" install pytest pyyaml
"$SCRATCHPAD/venv/bin/pytest" tests/ -q
```

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_skill_stop_instruction.py` (AC-3, AC-4, AC-5, AC-6)
- `pytest tests/test_repo_own_aliases_147.py` (AC-7, AC-9)
- `pytest tests/test_clear_checkpoint_blocks.py` (AC-6, Regressionsschutz)
- `pytest tests/test_setup_command_aliases.py tests/test_setup_alias_sync_150.py` (AC-1, AC-2, AC-8)
- `pytest tests/test_skills_sync.py` (AC-2, Regressionsschutz)
- `pytest tests/test_readme_version_195.py` (AC-10, README-Version)
- `python3 scripts/release_check.py` (AC-2, AC-10 — die README-Prüfung dort deckt den
  Versionsbump mit ab)
- Volle Regressionssuite: `pytest tests/ -q` (AC-11)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** ADR-0147
- **Rationale:** Diese Spec revidiert teilweise einen Beschluss aus
  `docs/specs/fix-140-po-decision-gates.md` (Z. 92–100): Dort wurde begründet, dass
  `/50-implement` und `/60-validate` manuell bleiben, weil `/50-implement` „echten
  Produktivcode schreibt und Subagenten dafür spawnt — eine reale Handlung mit
  Konsequenzen, keine Formsache" und `/60-validate` „echte manuelle Nutzertests"
  verlangt. Beide Prämissen halten der Prüfung nicht mehr stand: (1) Die Durchsetzung
  hängt nachweislich nie am Tastendruck — `bash_gate.py` blockt `git commit` ohne
  VERIFIED-Verdict unabhängig davon, ob ein Slash-Befehl getippt wurde, `edit_gate.py`
  verlangt registrierte RED-Artefakte unabhängig vom Aufrufweg, und
  `workflow.py::_validate_transition` hat für `phase7_validate` überhaupt keine
  Bedingung. (2) Die Annahme „`/60-validate` verlangt echte manuelle Nutzertests"
  trifft nicht mehr zu: die Phase besteht aus vier automatischen Prüfagenten und dem
  docs-updater, kein Testauftrag an den PO. Was bleibt und **nicht** revidiert wird:
  Der Übergang `approved` → `/40-tdd-red` aus fix-140 bleibt exakt wie dort gebaut,
  ebenso das Prinzip, dass eine reale Entscheidung (Spec-Freigabe, GREEN-Freigabe `go`,
  AMBIGUOUS-Klärung) an eine explizite User-Eingabe gebunden bleibt — nur der reine
  Tastendruck ohne neue Entscheidung entfällt. Kein neuer Hook, kein neuer
  State-Mechanismus; die Nummer ADR-0147 folgt der Konvention aus
  `docs/specs/fix-234-footer-gate.md` (ADR-Nummer = Issue-Nummer).

## Changelog

- 2026-09-27: Initial spec erstellt (Issue #147, Hälfte 1 von #250, nach PO-Entscheidung
  zur Zweiteilung mit #260).
- 2026-09-27: Nachträge zur Versionsanhebung ergänzt: 16 generierte Skills und die vier
  verbleibenden gesperrten Vollkopien (`70-deploy`, `80-workflow`, `81-add-artifact`,
  `99-reset`) werden durch den Versions-Marker mitgezogen; `CLAUDE.md` und
  `README.md`-Versionszeile in den Scope aufgenommen; Reihenfolge Flag-Flip →
  `sync_skills.py` → Versionsbump → `sync_skills.py` → `setup.py --refresh-aliases`
  festgeschrieben; AC-7 auf `alias_sync.find_stale_aliases()` umgestellt statt
  Nachbau derselben Logik; AC-10 (Versionskonsistenz) neu ergänzt; Known Limitation zur
  parallelen, versionsneutralen Auslieferung #253 ergänzt.
