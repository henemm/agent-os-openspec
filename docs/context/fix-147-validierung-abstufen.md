# Context: fix-147-validierung-abstufen

## Request Summary

Issue #147 (Teilauftrag 2 von 4 aus #250): Die PO-Zeremonien am Ende des Workflows sollen
abgestuft werden. Wo eine Änderung keine beobachtbare Oberfläche hat, ist die Aufforderung an
den PO, etwas anzusehen, inhaltslos — und die beiden erzwungenen Tastendrücke
(`/50-implement`, `/60-validate`) tragen dort keine Entscheidung. Die Validierungs-*Phase*
selbst bleibt vollständig erhalten.

Vorarbeit: `docs/context/feat-250-prozess-abstufung.md` (vollständige Analyse, Befunde F1–F9,
PO-Entscheidungen vom 2026-09-26). Teilauftrag 1 (#88) ist ausgeliefert (3.32.0).

## Related Files

| File | Relevance |
|------|-----------|
| `skills/50-implement/SKILL.md` | `disable-model-invocation: true` (Z. 3) — erzwingt den Tastendruck `/50-implement`. Generiert aus `core/commands/50-implement.md` |
| `skills/60-validate/SKILL.md` | `disable-model-invocation: true` (Z. 3) — erzwingt den Tastendruck `/60-validate` |
| `core/commands/40-tdd-red.md` | Z. 189: „**NICHT** selbst mit der Implementierung beginnen. Warte bis der User `/50-implement` tippt." — die textuelle Hälfte der Sperre |
| `skills/40-tdd-red/SKILL.md` | Trägt dieselbe STOPP-Anweisung wortgleich (fix-140, Adversary-Fund F001) |
| `core/commands/50-implement.md` | Z. 289/340: dieselbe STOPP-Anweisung für den Übergang nach `/60-validate`. Step 6 (Z. 154) = „User-Freigabe der GREEN-Ergebnisse (PFLICHT)" |
| `core/commands/60-validate.md` | Z. 230: Schlussfrage „Soll ich den Code committen?"; Z. 198–212: bestehende Autonomie-Ausnahme; Z. 100–167: die vier Prüfagenten + docs-updater (bleiben) |
| `core/hooks/hook_utils.py` | 986 Z., Sammelstelle für geteilte Helfer (`extract_ac_entries`, `is_code_file`, `find_project_root`). Ziel für `has_observable_surface()`. **Kein CLI-Einstieg** |
| `core/hooks/workflow.py` | CLI-Dispatch `COMMANDS` (Z. 1803–1828) — der einzige Weg, wie ein Befehlsdokument eine Python-Prüfung aufrufen kann |
| `core/hooks/bash_gate.py` | Z. 122–124 `E2E_DOCS/FRONTEND/BACKEND_PATTERNS`, Z. 445–447 Config-Override `e2e_scope` — das vorhandene Muster für pfadbasierte Klassifikation |
| `config.yaml` | Zielort für den Block `observable_surface:` (Muster der bestehenden Blöcke: `enabled:` + Listen) |
| `core/hooks/post_implementation_gate.py` | `_BATCH_WINDOW_S = 15*60`, `_GATED_PHASES = {phase6_implement}` — die technische Hälfte der GREEN-Freigabe. **Nicht Teil dieses Auftrags** (F7 → #182) |
| `tests/test_skill_stop_instruction.py` | Prüft genau die STOPP-Anweisung, die hier wegfällt → **muss mit angepasst werden** (siehe N1) |
| `tests/test_clear_checkpoint_blocks.py` | Prüft die `/clear`-Checkpoint-Blöcke strukturell → Änderungen müssen außerhalb dieser Blöcke stehen (fix-140-Vorgehen) |
| `tests/test_setup_command_aliases.py`, `tests/test_setup_alias_sync_150.py` | Parametrisieren über `_is_model_invocable()` → Flag-Flip wird automatisch mitgetestet |
| `docs/specs/fix-140-po-decision-gates.md` | Bauplan **und** Gegenposition: begründet ausdrücklich, warum `/50-implement` und `/60-validate` manuell bleiben |

## Existing Patterns

- **Flag-Flip + Auto-Chaining + Regressionstest** — fix-140 hat genau das für den Übergang
  „Freigabe → `/40-tdd-red`" gemacht: Flag auf `false`, Chaining-Anweisung in der *vorherigen*
  Befehlsdatei, außerhalb des `/clear`-Checkpoint-Blocks, plus Regressionstest für die
  verbliebene Textsicherung.
- **Pfadbasierte Klassifikation mit Config-Override** — `bash_gate.py` `e2e_scope`: Default-Muster
  im Code, projektweise überschreibbar aus `config.yaml`, Zugriff über `config.get(...)`.
- **Befehlsdokument ruft Hook-Skript mit Unterbefehl** — `adversary_dialog.py parse|stamp`,
  `qa_gate.py`, `session_singleton_guard.py claim`. Es gibt kein Muster „Befehl importiert
  hook_utils direkt" — deshalb braucht die neue Prüfung einen CLI-Unterbefehl.
- **Zwei Dateien pro Befehl** — `core/commands/X.md` ist die Quelle, `skills/X/SKILL.md` wird mit
  `scripts/sync_skills.py` erzeugt; `scripts/release_check.py` bricht bei Drift ab.

## Dependencies

- **Upstream:** `config_loader.load_config()`, `git` (Dateiliste), `hook_utils.find_project_root()`
- **Downstream:** `setup.py::_is_model_invocable()` und `core/hooks/alias_sync.py` lesen
  `disable-model-invocation` → der Flag-Flip ändert die Alias-Strategie der beiden Befehle
  automatisch von Full-Embed auf Thin-Redirect (kein Code nötig; Historie #55/#56/#87)
- `scripts/sync_skills.py` nach jeder Änderung an `core/commands/` neu laufen lassen
- Pytest nur im eigenen venv mit `pytest` **und** `pyyaml`

## Existing Specs

- `docs/specs/fix-140-po-decision-gates.md` — der zu revidierende Beschluss (ADR-relevant)
- `docs/specs/fix-253-adversary-evidence-gate.md` — macht den Nachweis des unabhängigen Prüfers
  fälschungssicher; ausgeliefert wird er in einem eigenen Vorgang (Stand: wartet dort auf Phase 7)
- `docs/context/feat-250-prozess-abstufung.md` — Analyse, Befunde F1–F9, PO-Entscheidungen

## Neue Befunde dieser Phase (Abweichungen von der #250-Analyse)

### N1 — `tests/test_skill_stop_instruction.py` blockiert den Auftrag, statt ihn zu begleiten

Die #250-Analyse führt diesen Test unter „muss unverändert grün bleiben". Falsch: er prüft mit
drei String-Präsenz-Tests genau den Satz, den dieser Auftrag entfernt („**NICHT** selbst mit der
Implementierung beginnen. Warte bis der User `/50-implement` tippt."). Der Test *muss* Teil der
Änderung sein — er wird umgedreht: aus „der Satz muss da sein" wird „der Selbstaufruf ist erlaubt,
aber nur mit registrierten RED-Artefakten".

Sein Docstring benennt zugleich das echte Risiko: `edit_gate.py` prüft nur den Phasen-*Zustand*,
nicht ob der User `/50-implement` getippt hat. Die verbleibende technische Sperre ist die
RED-Artefakt-Pflicht (`edit_gate.py` + `tdd_enforcement.py`) — die ist unabhängig vom Tastendruck
und bleibt unangetastet.

### N2 — In `60-validate.md` gibt es keinen „PO testet manuell"-Block

Die Phase ist längst automatisiert (4 Prüfagenten + docs-updater). Die PO-Beteiligung besteht aus
genau zwei Dingen: dem erzwungenen Tastendruck und der Schlussfrage „Soll ich den Code
committen?". Eine Oberflächen-Prüfung kann also nur an *dieser* Frage hängen — es gibt keinen
Testauftrag-Block, der entfallen könnte.

Nebenbefund: Die Schlussfrage hat bereits eine Ausnahme („dokumentierte Autonomie", Z. 198–212) —
die neue Prüfung stellt sich daneben, nicht dagegen.

### N3 — `hook_utils.py` hat keinen CLI-Einstieg

Ein Befehlsdokument kann keine Python-Funktion importieren. Die Prüfung braucht deshalb einen
Unterbefehl in `workflow.py` (Muster wie `adversary_dialog.py parse`), der die Funktion aus
`hook_utils.py` aufruft. Kein neuer Hook, keine neue Datei.

### N4 — „Default ist validieren" braucht ZWEI Musterlisten, nicht eine

Mit nur einer Liste („hat Oberfläche") würde jede unbekannte Endung als „keine Oberfläche"
durchgehen — das Gegenteil des Sicherheitsprinzips. Nötig sind:
`surface_patterns` (sicher beobachtbar → streng) **und** `non_surface_patterns` (sicher nicht
beobachtbar). Der PO-Block entfällt nur, wenn **jede** geänderte Datei in
`non_surface_patterns` trifft und **keine** in `surface_patterns`. Alles andere — unbekannte
Endung, leere Liste, `git`-Fehler, Config-Ladefehler — bleibt streng.

### N5 — Die Dateiliste muss gegen den Basis-Stand gebildet werden, nicht gegen HEAD

In Phase 7 ist der Code laut Checkpoint-Block bereits eingecheckt; `git diff HEAD` wäre dann leer
und würde „keine Oberfläche" ergeben — ein stiller Fehlschluss in die unsichere Richtung. Die
Liste muss den gesamten Arbeitsstand des Vorgangs umfassen (Basis-Stand … HEAD, plus
uncommittete und unversionierte Dateien). Leere Ergebnisliste → streng.

## Risks & Considerations

- **R-A (Hauptrisiko, aus #250 R6):** Der Auftrag lockert die Durchsetzungsmechanik. Gegenmittel:
  zwei Musterlisten mit Fail-closed-Verhalten (N4), RED-Artefakt-Pflicht bleibt, GREEN-Freigabe
  („go") bleibt, Adversary-Dialog bleibt, Validierungsphase bleibt.
- **R-B:** Der Beschluss aus fix-140 wird teilweise revidiert (dort: „`/50-implement` schreibt
  echten Produktivcode — reale Handlung, keine Formsache"). Gehört als ADR-Reflexion in die Spec,
  nicht als stille Änderung.
- **R-C:** Selbstaufruf statt Tastendruck heißt: kein `/clear` zwischen den Phasen, also mehr
  Kontext in einer Sitzung. Der Checkpoint-Block muss deshalb erhalten bleiben (Wiedereinstieg
  nach `/clear` weiter möglich) — Chaining-Anweisung wie bei fix-140 *außerhalb* des Blocks.
- **R-D:** Die Musterlisten treffen auch Fremdprojekte (iOS/SwiftUI, Home Assistant). Defaults
  müssen dort streng ausfallen, wenn sie nichts erkennen (`.swift` ohne Hinweis auf eine View →
  unbekannt → streng).

## Type

Feature (Standard Track, Score 3: Scope Medium, Blast Radius High, Unsicherheit Low)

---

## Analysis

### Ergebnis der unabhängigen Gegenprüfung (`analysis-challenger`, 2026-09-27)

Verdict **NEEDS REVIEW** — die Kernmechanik hält, drei Ergänzungen sind vor der Spec nötig.

Unbestritten bestätigt (mit Code-Belegen des Prüfers):
- `_validate_transition` (`core/hooks/workflow.py` Z. 947–1014) hat für `phase7_validate` keine
  Bedingung → kein Hook-Eingriff nötig (F6/N2)
- Das Commit-Gate (`core/hooks/bash_gate.py` Z. 636–660) blockt `git commit` ohne
  VERIFIED-Verdict und prüft dabei **nie**, ob ein Slash-Befehl getippt wurde → der Flag-Flip
  kann es nicht umgehen
- RED-Artefakt-Pflicht (`edit_gate.py` Z. 530, `_validate_transition` Z. 998–1003) unabhängig
  vom Aufrufweg
- `footer_gate.py` Z. 181–194 erzwingt keine `❗ Du`-Zeile, prüft nur die vorhandene →
  Selbstaufruf blockiert dort nichts
- N1 (Testumkehr) und R-B (ADR-Revision von fix-140) korrekt und vollständig lokalisiert

### N6 (CRITICAL, vom Prüfer gefunden, selbst nachgeprüft) — Das eigene Repo trägt zwei Vollkopien mit derselben Sperre

`.claude/commands/50-implement.md` (373 Z.) und `.claude/commands/60-validate.md` (282 Z.) sind
**getrackte** Kurz-Alias-Dateien mit eigenem `disable-model-invocation: true` (je Z. 4). Ursache:
`core/hooks/alias_sync.py::embeds_full_skill()` (Z. 38–40) bettet bei gesetzter Sperre den
**kompletten** Skill-Text ein, weil ein Text-Redirect am Skill-Tool-Gate scheitern würde — im
Modul-Docstring dort selbst als „Diese Vollkopien veralten bei jedem Plugin-Update still"
benannt. Zum Vergleich: die nicht gesperrten Aliase (`20-analyse`, `40-tdd-red`) sind 6 Zeilen
lang.

Konsequenz ohne Nachführung: In genau diesem Repo (dem Dogfooding-Projekt) löst `/50-implement`
weiter auf die lokale Vollkopie mit der Sperre auf — der Auftrag wäre wirkungslos, obwohl alle
Tests grün sind, denn die Tests prüfen `skills/` und `tmp_path`-Generate, **nie** die
repo-eigenen Alias-Dateien (`tests/test_setup_alias_sync_150.py` Z. 51–64 vergleicht gegen
`tmp_path`; `scripts/release_check.py` Z. 191–203 prüft nur `skills/` gegen `core/commands/`).

Nebennutzen: Mit gelöster Sperre erzeugt `alias_content()` für beide den 6-Zeilen-Redirect —
rund 640 Zeilen still veraltender Vollkopie fallen weg und können nicht mehr driften.

### N7 (HIGH) — `all(...)` über eine leere Liste ist `True`, also das Gegenteil von „streng"

Die Anforderung „jede geänderte Datei trifft `non_surface_patterns`" wörtlich als
`all(map(...))` gebaut liefert bei leerer Dateiliste `True` → „keine Oberfläche" → PO-Block
entfällt. Genau der stille Fehlschluss, den N4/N5 verhindern sollen. Der Vertrag muss als Formel
in der Spec stehen, nicht als Prosa: **leere Liste zuerst prüfen und streng zurückgeben**, erst
danach die Musterlogik. Eigener Testfall, vor dem Surface-Treffer-Fall.

### N8 (HIGH) — Es gibt keinen gespeicherten Basis-Stand und `main` ist kein sicherer Default

Kein Treffer für `merge-base|base_commit|base_sha` in `core/hooks/workflow.py` — der Startpunkt
eines Vorgangs ist nirgends festgehalten. `bash_gate.py` Z. 404–440 vergleicht bewusst gegen
`HEAD`/`HEAD~1`, weil es nur den anstehenden Commit bewertet; für diese Frage reicht das nicht
(N5). Die Spec muss die Ermittlung des Basis-Stands ausschreiben und den Default-Branch
konfigurierbar bzw. automatisch erkennbar machen (`git symbolic-ref refs/remotes/origin/HEAD`,
Fallback streng). Sonst ist die Funktion in jedem Projekt mit `master`/`develop` dauerhaft
streng — sicher, aber nutzlos.

### N9 (HIGH, Blast Radius) — Konkrete Muster, die in Fremdprojekten falsch entscheiden

- `modules/home-assistant/hooks/lovelace_screenshot_gate.py` Z. 81–83 definiert
  `is_lovelace_file()` als `'lovelace/' in path and path.endswith('.yaml')` und verlangt dafür
  Vorher/Nachher-Screenshots — Dashboards sind dort die beobachtbarste Oberfläche überhaupt. Ein
  generisches `\.yaml$` in `non_surface_patterns` würde sie verschlucken. → **Default-Liste darf
  keine pauschale YAML- oder Config-Regel enthalten.**
- `core/hooks/config_loader.py` Z. 130–157 merged nur die Projekt-`config.yaml` plus lokale
  Overrides, **nicht** die Modul-Configs → Modulprojekte müssen ihre `surface_patterns` selbst
  ergänzen (wie bei `e2e_scope` üblich). Gehört in die Spec-Doku.
- iOS: `.strings`/`.xcstrings` (siehe `modules/ios-swiftui/commands/localize.md`) ändern direkt
  sichtbaren Text → dürfen nie unter ein generisches „Ressourcen"-Muster fallen. `.swift` ohne
  View-Hinweis bleibt „unbekannt" → streng. Korrekt, aber explizit zu dokumentieren.

### N10 (MEDIUM) — `is_code_file()` ist die falsche Achse

`core/hooks/hook_utils.py` Z. 680–688 kennt nur Backend-/App-Endungen. „Code" ≠ „Oberfläche"
(ein `.swift`-Service hat keine, eine `.strings`-Datei hat eine). Die Spec muss die
Wiederverwendung ausdrücklich ausschließen, damit der Developer Agent nicht abkürzt.

### Weitere Fundstellen, die mitgeführt werden müssen

| Datei:Zeile | Was dort steht | Anpassung |
|---|---|---|
| `.claude/commands/50-implement.md:4`, `.claude/commands/60-validate.md:4` | Vollkopie mit Sperre | **Ja** (N6) |
| `tests/test_skill_stop_instruction.py` (ganze Datei) | prüft den entfallenden Satz | **Ja** (N1) |
| `docs/WORKFLOW_GUIDE.md:47,51,129,153,386,468-469` | „User tippt /50-implement" | Ja, Doku |
| `README.md:124,128,159-160` | Befehle als PO-Schritte | Ja, Doku |
| `core/commands/00-intake.md:114` | Tabellenzeile „Manuelle Validierung ✅ immer" | Ja, Doku |
| `core/hooks/workflow.py:148-159` (`NEXT_STEP`), `:240-247` (`status_note`), `footer_gate.py:181-194` | Selbstaufruf bereits vorgesehen | **Nein** |
| `tests/test_clear_checkpoint_blocks.py:58` | struktureller Folgeschritt, nicht „wer tippt" | **Nein**, bleibt grün |

### Geprüfte Alternativen

1. **Nur die Schlussfrage abschaffen, beide Tastendrücke behalten.** Sicherste Variante, löst
   aber das im Vorgang gemeldete Problem nicht (der PO tippt weiter zwei Befehle, die keine
   Entscheidung tragen). Taugt als Rückfallebene, nicht als Ersatz.
2. **Fußzeile führt den Befehl selbst aus.** Keine echte Alternative: `disable-model-invocation:
   true` ist ein hartes Skill-Tool-Gate (`docs/specs/fix-140-po-decision-gates.md` Z. 69–72) —
   beschreibt genau das, was der Flag-Flip tut. Verworfen.
3. **Abstufung am Track (`workflow_type`) statt an der Dateiliste.** In #250 (F1/R4) verworfen:
   wird in `/00-intake` gesetzt, bevor ein Diff existiert. Bestätigt verworfen.
4. **Pflichtfeld „Observable Surface: ja/nein" in der Spec** statt Dateimuster, hart erzwungen
   wie AC-N durch PO-Briefing- und CI-Spec-Gate. Ehrlichste Quelle (Aussage aus dem
   freigegebenen Dokument statt Nachher-Heuristik), aber sie verlagert die Entscheidung auf
   einen Menschen, der sie vergessen kann — dieselbe Falle wie `is_new_ui` (F5), nur mit Gate
   davor. Verworfen nach „Regeln vor Modell": die Dateiliste ist deterministisch und braucht
   niemandes Zutun. Bleibt als dokumentierte Option.
5. **Ganz ohne Oberflächen-Erkennung: die Schlussfrage immer zur Ankündigung machen.** Spart
   Konfigurationsblock, Git-Logik und Testdatei (−1 Logikdatei). Verworfen: bei einer sichtbaren
   Änderung ist der Blick des PO vor dem Festschreiben der einzige Teil von Phase 7 mit echtem
   Inhalt — genau den würde diese Variante mit abschaffen.

### Affected Files (with changes)

| File | Change Type | Description |
|------|-------------|-------------|
| `skills/50-implement/SKILL.md` | GENERATE | Sperre → `false` (Quelle: `core/commands/50-implement.md`) |
| `skills/60-validate/SKILL.md` | GENERATE | Sperre → `false` |
| `skills/40-tdd-red/SKILL.md` | GENERATE | STOPP-Anweisung → Chaining |
| `.claude/commands/50-implement.md` | MODIFY | Vollkopie → 6-Zeilen-Redirect (N6) |
| `.claude/commands/60-validate.md` | MODIFY | Vollkopie → 6-Zeilen-Redirect (N6) |
| `core/commands/40-tdd-red.md` | MODIFY | STOPP → Selbstaufruf `/50-implement`, außerhalb des `/clear`-Blocks |
| `core/commands/50-implement.md` | MODIFY | STOPP → Selbstaufruf `/60-validate`; Sperre im Frontmatter |
| `core/commands/60-validate.md` | MODIFY | Sperre im Frontmatter; Schlussfrage nur noch bei beobachtbarer Oberfläche |
| `core/hooks/hook_utils.py` | MODIFY | `has_observable_surface()` — Formel nach N7, Basis-Stand nach N8 |
| `core/hooks/workflow.py` | MODIFY | CLI-Unterbefehl als Aufrufweg für Befehlsdokumente (N3) |
| `config.yaml` | MODIFY | Block `observable_surface:` — `enabled`, `surface_patterns`, `non_surface_patterns`, `base_branch` |
| `tests/test_validation_ceremony_147.py` | CREATE | Leere Liste → streng (zuerst), Surface-Treffer → streng, Unbekannt → streng, repo-eigene Aliase == `alias_content()` |
| `tests/test_skill_stop_instruction.py` | MODIFY | Umkehr: Chaining-Anweisung statt Wartesatz |
| `README.md`, `docs/WORKFLOW_GUIDE.md`, `core/commands/00-intake.md` | MODIFY | Doku: Befehle nicht mehr als PO-Tastendruck |
| `CHANGELOG.md`, `.claude-plugin/plugin.json` | MODIFY | Eintrag + Versionsbump |

### Scope Assessment

- Logik-Dateien: **6** (2 Hooks, 3 Befehlsdokumente, 1 Config)
- Generat/Alias/Doku/Tests: 11 weitere Dateien, davon 5 generiert
- LoC: ≈ +260 / −700 (die −640 aus N6 sind gelöschte Vollkopien, kein Handwerk)
- Risiko: **MEDIUM** — Lockerung an der Durchsetzungsmechanik, aber Commit-Gate,
  RED-Artefakt-Pflicht, GREEN-Freigabe und Adversary-Dialog bleiben unangetastet

Damit über den globalen Scoping-Limits (4–5 Dateien, ±250 LoC) → Schnitt-Entscheidung beim PO,
siehe Open Questions.

### PO-Entscheidung (2026-09-27)

- [x] **Zwei Auslieferungen.** Dieser Workflow liefert **Hälfte 1**: Flag-Flip, Auto-Chaining,
      Nachführung der repo-eigenen Aliase, Doku. Die Oberflächen-Erkennung samt Musterlisten und
      Konfigurationsblock ist **Hälfte 2** und liegt als **#260** vor (eigene Spec, eigene
      Gegenprüfung). Begründung: Hälfte 1 löst die im Vorgang gemeldete Beschwerde und ist fast
      reiner Text; Hälfte 2 trägt das gesamte Risiko für Fremdprojekte.

### Korrektur zu N6 nach Prüfung von #238/#242 (Schwere, nicht Inhalt)

Die repo-eigenen Vollkopien überschatten in **Worktree-Sitzungen nichts**: dort werden
projektlokale `.claude/commands/` überhaupt nicht geladen (belegt in #238 und in dieser Sitzung —
die Skill-Auflistung enthält ausschließlich die zehn globalen Thin-Redirect-Aliase plus `diary`,
keinen der sechs gesperrten Befehle). N6 bleibt damit Teil des Auftrags, aber als Altlast
(655 Zeilen still verrottende Kopie), nicht als Blocker. Die Alias-Ladeprobleme selbst gehören zu
#238/#242/#251 und werden hier nicht angefasst.

### Wirkungsnachweis — was in dieser Sitzung beweisbar ist und was nicht

Der Flag-Flip wirkt auf das Skill-Tool erst, wenn der Harness die Plugin-Kopie neu einliest. Die
laufende Sitzung arbeitet gegen den bei Sitzungsstart eingefrorenen Stand
(`~/.claude/plugins/cache/.../3.32.0`), und die Liste der aufrufbaren Skills steht für die Sitzung
fest. Der Nachweis ist deshalb mechanisch zu führen — Dateizustand, erzeugtes Alias-Soll,
Chaining-Anweisung im Skill, Umkehr des Regressionstests — nicht durch einen Selbstaufruf im
selben Lauf. Das ist kein Schlupfloch, sondern dieselbe Beweisform, die fix-140 für denselben
Mechanismus genutzt hat.

### Scope nach dem Schnitt (nur Hälfte 1)

- Logik-Dateien: **3** (`core/commands/40-tdd-red.md`, `core/commands/50-implement.md`,
  `core/commands/60-validate.md` — Frontmatter und Übergangsanweisungen)
- Generat: `skills/{40-tdd-red,50-implement,60-validate}/SKILL.md`,
  `.claude/commands/{50-implement,60-validate}.md`
- Tests: `tests/test_skill_stop_instruction.py` (Umkehr), neue Prüfung der repo-eigenen Aliase
- Doku: `README.md`, `docs/WORKFLOW_GUIDE.md`, `core/commands/00-intake.md`, `CHANGELOG.md`,
  `.claude-plugin/plugin.json`
- LoC: ≈ +90 / −690 (davon −655 gelöschte Vollkopien)
- Risiko: **NIEDRIG** — kein Hook-Code, keine neue Logik; die Durchsetzung (Commit-Gate,
  RED-Artefakte, GREEN-Freigabe, Adversary) bleibt vollständig unberührt

### Nach der Auslieferung selbst erledigen (nicht dem PO überlassen)

Der Versionsbump macht die zehn globalen Kurz-Befehls-Kopien unter `~/.claude/commands/`
veraltet. Der Sitzungs-Banner würde Henning dafür beim nächsten Start einen Befehl zum Eintippen
anbieten (`setup.py ~ --refresh-aliases`, #205) — das widerspricht der Hausregel. Claude führt
diesen Lauf deshalb nach der Auslieferung selbst aus. Ausschließlich `--refresh-aliases`, niemals
`--command-aliases` für `~` (#87: globale Aliase überschatten sonst Projektdateien).

### Open Questions

Keine.
