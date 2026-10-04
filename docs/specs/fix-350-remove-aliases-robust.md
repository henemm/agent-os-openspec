---
entity_id: fix-350-remove-aliases-robust
type: bugfix
created: 2026-10-04
updated: 2026-10-04
status: draft
version: "1.0"
tags: [alias-sync, remove-aliases, robustheit, kurzbefehle, setup]
test_targets: ["tests/test_alias_robust_350.py"]
---

# Kurz-Befehle: Entfernen und Auffrischen trotz unerwarteter Dateien (#350)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #350 (Folge der Gegenprüfung von #251). Befunde F001 (MEDIUM), F002 (LOW), F003 (LOW) aus `docs/artifacts/feat-251-kurzbefehle/adversary-dialog.md`.

## Purpose

`setup.py --remove-aliases` bricht komplett ab, sobald in `.claude/commands/` eine `.md`-Datei liegt, die sich nicht als UTF-8 lesen lässt: `find_aliases` ruft `read_text()` ungeschützt, die Ausnahme beendet den Lauf, es wird nichts entfernt. Derselbe Defekt steckt in `find_stale_aliases` und `find_removed_aliases`: `setup.py --refresh-aliases` stürzt ab, und der Session-Banner (`session_banner.py`) verwirft wegen seines `except Exception: continue` die Warnung für den ganzen Bereich, sobald eine einzelne Datei kaputt ist. Dazu zwei kleine Randfehler: Die „Kept“-Liste zeigt Verzeichnisse und hängende Symlinks namens `x.md`, und `--global` ohne `--remove-aliases` wird stillschweigend ignoriert; außerdem erkennt `_frontmatter_close` ein Frontmatter mit CRLF-Zeilenenden oder Leerzeichen hinter `---` nicht, sodass der Marker auf der Altposition landet. Diese Spec macht das Werkzeug gegen solche Dateien robust. Eine unlesbare Datei wird nie gelöscht und nie als Alias behandelt.

## Source

- **File:** `core/hooks/alias_sync.py` — `_frontmatter_close`, `find_aliases`, `find_stale_aliases`, `find_removed_aliases`; `setup.py` — `remove_command_aliases`, `main`
- **Analyse:** `docs/context/fix-350-remove-aliases-robust.md` (Root Cause, Alternativen)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/alias_sync.py` | Modul | Alias-Erkennung; Hauptänderung |
| `setup.py` | Modul | Kept-Liste, Warnung bei `--global` |
| `core/hooks/session_banner.py` | Modul | Aufrufer von `find_stale_aliases`/`find_removed_aliases`; bleibt unverändert |
| `core/hooks/migrate_to_plugin.py` | Modul | Vorbild: `try: read_text() except: continue` (Zeile 506) |
| `tests/test_alias_remove_251.py` | Test | Muster (`setup.py` als echter Prozess mit Test-Home); Regressionsschutz |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/alias_sync.py` | MODIFY | Lese-Helfer `_read_or_none`, in den drei `find_*` benutzt; `_frontmatter_close` vergleicht ohne Zeilenende-/Leerraum-Reste |
| `setup.py` | MODIFY | Kept-Liste nur mit `is_file()`; Warnung auf stderr bei `--global` ohne `--remove-aliases` |
| `tests/test_alias_robust_350.py` | CREATE | je Teil ein Test, beide Fehlerrichtungen |
| `CHANGELOG.md` | MODIFY | Eintrag nur unter `[Unreleased]`, kein Versions-Bump |

### Estimated Changes

- Files: 4 (3 Produktiv/Doku, 1 Test)
- LoC: ca. +90 / −6 (Produktivcode ca. 35, Tests ca. 55). Spec/Kontext/Briefing zählen im LoC-Gate zusätzlich (#294).
- Risiko: MEDIUM — `core/hooks/` ist Infrastruktur, Gegenprüfung mit hohem Risiko (mind. 2 Runden); die Änderung ist rein defensiv, das Verhalten für lesbare Dateien bleibt gleich.

## Implementation Details

**F001 — Lese-Helfer.** `_read_or_none(path) -> str | None` liest `path.read_text()` und fängt `OSError` und `UnicodeDecodeError` (letztere ist ein `ValueError`, daher beides ausdrücklich): Ergebnis dann `None`. `find_aliases`, `find_stale_aliases` (für die Alias-Datei **und** die SKILL.md) und `find_removed_aliases` verwenden ihn; bei `None` wird die Datei übersprungen. Eine unlesbare Datei ist damit nie ein Alias, wird nie gelöscht und nie als veraltet gemeldet. Sie erscheint in `setup.py` automatisch als `Kept:`, weil sie eine Datei ist und nicht in der Alias-Liste steht — kein Sonderzweig nötig.

**F002 — Kept-Liste und Warnung.** Die Kept-Liste in `remove_command_aliases` nimmt nur Einträge mit `is_file()`. Ein Verzeichnis `x.md` und ein hängender Symlink erscheinen nicht. In `main` wird bei `--global` ohne `--remove-aliases` eine Zeile auf stderr ausgegeben (`WARNING: --global wirkt nur zusammen mit --remove-aliases und wird ignoriert.`), der Lauf geht normal weiter, Exit-Code bleibt unverändert.

**F003 — Frontmatter-Erkennung.** `_frontmatter_close` vergleicht jede Zeile mit `line.rstrip() == "---"`, statt exakt `== "---"` und `lines.index("---", 1)`. Damit werden `---\r` (CRLF) und `---  ` erkannt. `alias_content` fügt den Marker dann hinter dem Frontmatter ein; die Zeilenenden der Datei bleiben dabei erhalten (der Marker selbst wird mit `\n` angefügt, wie bisher). `is_alias_file` profitiert automatisch.

**Ohne Modell geht es?** Ja — reine Dateiprüfung und Zeilenvergleich, die Nulllinie ist die Regel.

**Alternativen:**

- **A (gewählt): Gemeinsamer Lese-Helfer in allen drei `find_*`.** Gleiche Ursache, gleiche Zeile, gleiche Testdatei; schließt zusätzlich den Banner-Defekt und den `--refresh-aliases`-Absturz.
- **B: Nur `find_aliases` beheben** (Ticket-Wortlaut) und die zwei anderen als Hinweis vermerken. Etwa 10 LoC weniger, lässt aber zwei belegte Folgefehler stehen. Verworfen.
- **C: `read_text(errors="replace")`.** Keine Kodierungsausnahme, aber `PermissionError` bleibt ungefangen, und eine Fremddatei mit Marker würde gelöscht. Verworfen.
- **D: `--global` ohne `--remove-aliases` als harter Fehler (Exit 2).** Sauberer, bricht aber Skripte, die das Flag bisher folgenlos mitgaben. Warnung gewählt.
- **E: Ticket schließen, nichts tun.** F001 richtet echten Schaden an; F002/F003 sind mit je 2–4 Zeilen billig und im Ticket zugesagt. Verworfen.

## Expected Behavior

- **Input:** `setup.py --remove-aliases [--global]` bzw. `--refresh-aliases` mit einem `.claude/commands/`-Ordner, der neben echten Aliasen unerwartete Einträge enthält.
- **Output:** Alle lesbaren markierten Aliase werden wie bisher entfernt; unlesbare Dateien bleiben stehen und stehen unter `Kept:`; Verzeichnisse und hängende Symlinks namens `*.md` tauchen nicht in `Kept:` auf; Schlusszeile `Command aliases: N removed, M kept.` stimmt mit den Zeilen darüber überein.
- **Side effects:** Keine neuen Dateien, keine neuen Abhängigkeiten. Nur die stderr-Warnung ist neu.

| Zustand von `.claude/commands/` | Heute | Soll |
|---|---|---|
| Alias `10-context.md` + nicht-UTF-8-Datei `kaputt.md` | Absturz, nichts entfernt | `Removed: 10-context.md`, `Kept: kaputt.md`, Exit 0 |
| Verzeichnis `ordner.md/` | `Kept: ordner.md` | nicht gelistet |
| Hängender Symlink `link.md` | `Kept: link.md` | nicht gelistet |
| `setup.py <proj> --global` (ohne `--remove-aliases`) | stumm | Warnung auf stderr, sonst unverändert |
| Skill mit CRLF-Frontmatter | Marker auf Altposition (Zeile 1) | Marker hinter dem Frontmatter |
| Frontmatter mit `---` plus Leerzeichen | Marker auf Altposition | Marker hinter dem Frontmatter |

## Known Limitations

- Eine nicht lesbare Datei, die in Wahrheit ein Alias ist, wird nicht entfernt (sichere Richtung: lieber stehen lassen als Fremdes löschen). Der Nutzer löscht sie von Hand.
- Die Warnung bei `--global` ist kein Fehler: Skripte laufen weiter.
- **Verteilung:** wirkt in Konsumenten-Projekten erst nach dem Plugin-Update.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] `--remove-aliases` und `--refresh-aliases` laufen mit einer unlesbaren Datei im Ordner durch, ohne etwas Fremdes zu löschen
- [ ] Die Kept-Liste enthält nur echte Dateien, und die `--global`-Warnung erscheint
- [ ] Frontmatter mit CRLF und mit Leerzeichen wird erkannt, der Marker steht hinter dem Frontmatter
- [ ] Keine bestehende Funktion ist kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given ein Befehlsordner mit einem markierten Alias und einer nicht UTF-8-lesbaren `.md`-Datei / When `setup.py --remove-aliases` läuft / Then endet der Lauf mit Exit 0, der Alias ist entfernt, die unlesbare Datei besteht weiter und steht unter `Kept:`, und die Schlusszeile zählt `1 removed, 1 kept`
  - Test: `tests/test_alias_robust_350.py::test_remove_aliases_ueberlebt_unlesbare_datei`
- **AC-2:** Given eine nicht lesbare Datei (Rechte entzogen) im Befehlsordner / When `find_aliases` läuft / Then wirft es nichts und liefert die Datei nicht als Alias
  - Test: `tests/test_alias_robust_350.py::test_find_aliases_ueberspringt_nicht_lesbare_datei`
- **AC-3:** Given ein Befehlsordner mit einer unlesbaren `.md`-Datei und einem veralteten markierten Alias / When `find_stale_aliases` und `find_removed_aliases` laufen / Then werfen sie nichts, und der veraltete bzw. entfernte Alias wird weiterhin gefunden (eine kaputte Datei blendet die Warnung für den Bereich nicht aus)
  - Test: `tests/test_alias_robust_350.py::test_stale_und_removed_finden_trotz_unlesbarer_datei`
- **AC-4:** Given ein Verzeichnis `ordner.md/` und ein hängender Symlink `link.md` im Befehlsordner / When `setup.py --remove-aliases` läuft / Then erscheinen beide nicht unter `Kept:` und werden nicht mitgezählt; eine echte unmarkierte Datei erscheint weiterhin
  - Test: `tests/test_alias_robust_350.py::test_kept_liste_nur_echte_dateien`
- **AC-5:** Given `setup.py <projekt> --global` ohne `--remove-aliases` / When der Aufruf läuft / Then steht eine Warnzeile auf stderr, die `--global` und `--remove-aliases` nennt, und der Exit-Code ist unverändert; mit `--remove-aliases --global` erscheint die Warnung nicht
  - Test: `tests/test_alias_robust_350.py::test_global_ohne_remove_aliases_warnt`
- **AC-6:** Given ein Skill-Text, dessen Frontmatter CRLF-Zeilenenden hat / When `alias_content` den Marker einsetzt / Then steht der Marker direkt hinter dem schließenden `---`, nicht in Zeile 1, und `is_alias_file` erkennt das Ergebnis
  - Test: `tests/test_alias_robust_350.py::test_frontmatter_mit_crlf_marker_hinter_frontmatter`
- **AC-7:** Given ein Skill-Text mit Leerzeichen hinter dem öffnenden und dem schließenden `---` / When `alias_content` den Marker einsetzt / Then steht der Marker direkt hinter dem Frontmatter
  - Test: `tests/test_alias_robust_350.py::test_frontmatter_mit_leerzeichen_nach_trennstrich`
- **AC-8:** Given Dateien ohne Frontmatter oder mit nicht geschlossenem Frontmatter / When `alias_content` läuft / Then bleibt das Verhalten unverändert (Marker in Zeile 1)
  - Test: `tests/test_alias_robust_350.py::test_ohne_geschlossenes_frontmatter_unveraendert`
- **AC-9:** Given der bestehende Testbestand / When die Regressionstests laufen / Then bleiben sie grün
  - Test: `tests/test_alias_remove_251.py`, `tests/test_alias_marker_position_251.py`, `tests/test_session_banner.py`, `tests/test_bug_typ_entfernt_333.py`, `tests/test_setup_alias_sync_150.py` (unverändert, Lauf grün)

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_alias_robust_350.py` (AC-1 bis AC-8; `setup.py` als echter Prozess mit Test-Home nach dem Muster aus `tests/test_alias_remove_251.py`, `alias_sync`-Funktionen direkt; unlesbar = Bytes `\xff\xfe` bzw. `chmod 000`; beide Fehlerrichtungen: Fremdes bleibt, Alias geht).
- RED-Nachweis: Vor der Implementierung schlagen AC-1 bis AC-7 fehl (Absturz bzw. falsche Ausgabe), AC-8 ist bereits grün.
- Regressionslauf (AC-9): die fünf genannten Dateien, danach die Vollsuite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Rein defensive Fehlerbehandlung innerhalb der bestehenden Entscheidung aus #251 (markierte Aliase entfernen, Fremdes nie anfassen); kein neues Muster, keine Abhängigkeit. Reflexion der Alternativen: (A) gemeinsamer Helfer — gewählt wegen gleicher Ursache und Folgefehlern; (B) nur `find_aliases` — verworfen, weil zwei belegte Folgefehler stehen blieben; (C) `errors="replace"` — verworfen, weil es Fremddateien löschbar macht; (D) harter Fehler bei `--global` — verworfen, weil es Skripte bricht. Keine frühere ADR wird gekippt.

## Changelog

- 2026-10-04: Initial spec created (#350, Folge von #251)
