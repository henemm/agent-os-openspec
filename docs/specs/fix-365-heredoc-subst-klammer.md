---
entity_id: fix-365-heredoc-subst-klammer
type: bugfix
created: 2026-10-05
updated: 2026-10-05
status: draft
version: "1.0"
tags: [strip-heredoc-bodies, secrets-guard, bash-gate, befehlsersetzung, bash-3-2, differenztest, sicherheitsluecke]
test_targets: ["tests/test_heredoc_strip_357.py", "tests/test_heredoc_bash_oracle_357.py"]
---

# Heredoc in Befehlsersetzung wird nie mehr aus dem Scan entfernt (#365)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue #365** — `strip_heredoc_bodies`: bash 3.2 beendet die Befehlsersetzung an einer Body-Zeile mit Klammer, der Folgebefehl bleibt ungeprüft.

Vorgeschichte: #64/#75, #276/#356, #357 (#362). Dritter Befund derselben Klasse („bash beendet die Ersetzung früher, als der Scanner annimmt"): zuerst `E)"`, jetzt `y)"`.

## Purpose

`hook_utils.strip_heredoc_bodies` entfernt seit #362 den Body eines Heredocs in einer Befehlsersetzung (`gh pr create --body "$(cat <<'EOF' … )"`) aus dem Prüftext von `bash_gate` und `secrets_guard`. bash 3.2 (`/bin/bash`, `/bin/sh` auf macOS) parst die Ersetzung ohne Kenntnis des Heredocs, beendet sie an einer unausgeglichenen `)` im Body (gefolgt von einem `"` später im Body) und führt die folgenden Zeilen als Befehle aus — der Scanner hat sie als „Daten" entfernt, kein Gate sieht sie. Künftig wird ein Heredoc-Body innerhalb `$( … )` nie mehr entfernt; die Klasse ist damit geschlossen, nicht nur die Schreibweise `y)"`.

## Source

- **File:** `core/hooks/hook_utils.py` — **Identifier:** `_heredoc_bodies` (`$(`-Zweig), `strip_heredoc_bodies` (Signatur unverändert)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/bash_gate.py` (Aufrufer, unverändert) | module | Prüft den gestrippten Befehl; Angriffstests laufen per stdin gegen den echten Hook |
| `core/hooks/secrets_guard.py` (Aufrufer, unverändert) | module | Wie oben |
| `core/hooks/secret_egress_guard.py` (Aufrufer, unverändert) | module | Nutzt dieselbe Funktion; Regressionslauf |
| `tests/heredoc_bash_oracle.py` | Testhelfer | Differenztest gegen echte bash; Generator wird erweitert |
| `tests/test_heredoc_bash_oracle_357.py` | Test | Feste CI-Stichprobe (Seeds 11, 357) mit bash 5.2 |
| `tests/test_bash_gate_freetext_fixes_64_75.py` | Test | Regression: Commit-Body-Test `test_command_substitution_heredoc_commit_allowed` |
| `/bin/bash` 3.2.57 | CLI | Lokaler Zeuge für die Ausführung der Folgezeile |

## Scope

- **Affected Files:**
  - Code: `core/hooks/hook_utils.py`
  - Tests: `tests/test_heredoc_strip_357.py`, `tests/heredoc_bash_oracle.py`
  - Doku: `CHANGELOG.md` (nur `[Unreleased]`, kein Versions-Bump)
- **Estimated Changes:** Produktivcode ca. −30/+5 LoC, Tests ca. +60 LoC → insgesamt unter 120 LoC, 4 Dateien (innerhalb der Scoping-Limits)

## Implementation Details

Referenz für die Analyse und Reproduktion: `docs/context/fix-365-heredoc-subst-klammer.md`.

1. **`hook_utils._heredoc_bodies`:** Im `$(`-Zweig wird `ok = False` gesetzt — ein Heredoc in einer Befehlsersetzung wird immer voll gescannt. Die dann toten Hilfen `_HEREDOC_SAFE_OUTER`, `_segment_command_word` und `subst_ok` werden gelöscht, aber nur, wenn eine Suche (Grep über das ganze Repo) keine weitere Verwendung findet; sonst bleiben sie stehen. Alle übrigen Wege (Heredocs außerhalb von Ersetzungen) und die Fail-closed-Logik (`_HeredocUnsure`, Präfix-Prüfung `E)`) bleiben unverändert.
2. **`tests/test_heredoc_strip_357.py`:** `DATA["commit_message"]` und `DATA["pr_body"]` wandern in eine neue Gruppe „Heredoc in Befehlsersetzung bleibt im Scan" (Erwartung: Body bleibt im strip-Ergebnis). Neue Angriffstests mit `y)"` prüfen das strip-Ergebnis sowie `bash_gate` und `secrets_guard` per stdin. `terminator_with_paren_in_subst` bleibt.
3. **`tests/heredoc_bash_oracle.py`:** Der Generator maskiert Body-Zeilen mit `)`, `(` oder Quote nicht mehr mit `#` (Stelle ca. Z. 59), sondern erzeugt sie unmaskiert, sodass Differenztest (lokal bash 3.2, CI bash 5.2) die Klasse sieht. Die Öffner-Formen (ca. Z. 111–113) bleiben; für Öffner in Ersetzungen müssen Folgezeilen im strip-Ergebnis sichtbar bleiben.
4. **`CHANGELOG.md`:** Eintrag unter `[Unreleased]` → `### Fixed`.

Messung als Beleg (120 gemergte PR-Texte dieses Repos als `gh pr create`-Body durch `bash_gate`): heutiger Stand 0 Fehlalarme, Weg A 11 (9 %); reale Auslöser des bash-3.2-Fehlers in diesen Texten: 0 von 120.

## Expected Behavior

- **Input:** `gh pr create --title T --body "$(cat <<'EOF'` / `x` / `y)"` / `cat .env` / `EOF` / `)"`.
- **Output:** `strip_heredoc_bodies` behält die Zeile `cat .env`; `bash_gate` und `secrets_guard` blocken mit Exit 2.
- **Input (Kontrolle):** Heredocs außerhalb von Ersetzungen (`cat > datei <<'EOF'`), `git commit -m "$(cat <<'EOF' … )"`.
- **Output (Kontrolle):** Bisheriges Verhalten; Body außerhalb von Ersetzungen wird weiter entfernt, `git commit -m` läuft über den Git-Schnellpfad ohne Fehlalarm.
- **Side effects:** `gh pr/issue …` mit Gate-Wörtern (geschützter Pfad, Marker, `.env`) im Text eines Ersetzungs-Heredocs wird jetzt voll gescannt und kann blocken (siehe Known Limitations).

## Known Limitations

- **bash-5-Verhalten ist lokal nicht prüfbar.** Auf dem Entwicklungsrechner gibt es kein bash 5 und kein Docker. Der einzige Zeuge für bash 5.x ist die CI (ubuntu-latest, bash 5.2) über den Differenztest. Genau deshalb wird die ganze Klasse geschlossen statt einer nur unter 3.2 belegten Schreibweise.
- **Kosten von Weg A:** ca. 11 von 120 gemergten PR-Texten (9 %) lösen bei `gh pr/issue …` mit Gate-Wörtern im Text einen Fehlalarm aus. Ausweg: `--body-file` (den wählt Claude selbst; kein Eingriff für den PO). `git commit -m` ist nicht betroffen (Git-Schnellpfad), `secrets_guard` ebenfalls nicht.
- Die Ausführung der Folgezeile ist nur unter bash 3.2 und `/bin/sh` (bash 3.2, POSIX) belegt; zsh und dash führen sie nicht aus. Das Bash-Werkzeug der Sitzung läuft unter zsh.
- **Verworfene Alternativen:**
  - **B** (nur entfernen, wenn der Body keine `)`→`"`-Folge hat, ca. 5 % Fehlalarm): beruht auf einer nur für bash 3.2 belegten Auslöser-Tabelle, löst die nächste bash-Variante nicht — wieder eine Schreibweise statt der Klasse.
  - **C** (genaue Nachbildung des bash-3.2-Klammerzählers): ein halber Shell-Parser, genau der Weg, der in #276/#357 dreimal scheiterte; 24 % unnötig verweigert (Apostrophe).
  - **D** (nur dokumentieren und Differenztest erweitern): 0 Fehlalarme, lässt aber die belegte Lücke offen. Der Test-Teil ist trotzdem Bestandteil dieser Spec.
- Nicht Teil dieser Änderung: `gh pr create`-Texte generell nur über `--body-file` zuzulassen (würde den Arbeitsablauf aller Projekte ändern, gehört in `bash_gate`, nicht in den Scanner).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Die Leak-Zeile nach `y)"` (`gh pr create … --body "$(cat <<'EOF'` / `x` / `y)"` / `cat .env` / `EOF` / `)"`) wird von `bash_gate` und `secrets_guard` mit Exit 2 geblockt; die Kontrollfälle (`EOF)"`, `echo hi` plus Leak) bleiben geblockt, `git commit -m "$(cat <<'EOF' … )"` mit Gate-Wörtern im Text bleibt ohne Fehlalarm
- [ ] Der Differenztest-Generator erzeugt `)`-/Quote-Zeilen im Body ohne `#`-Maskierung, und der Lauf bleibt lokal (bash 3.2) und in der CI (bash 5.2) grün
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given `gh pr create --title T --body "$(cat <<'EOF'` mit Body-Zeilen `x`, `y)"`, `cat .env`, danach `EOF` und `)"` / When `bash_gate` und `secrets_guard` den Befehl per stdin prüfen / Then blocken beide mit Exit 2
  - Test: `tests/test_heredoc_strip_357.py::test_subst_heredoc_vorzeitiges_ende_y_klammer_wird_geblockt`
- **AC-2:** Given derselbe Befehl / When `strip_heredoc_bodies` ihn verarbeitet / Then bleibt die Zeile `cat .env` im Ergebnis (ebenso bei `echo "$(cat <<'EOF'` und `x="$(cat <<'EOF'`)
  - Test: `tests/test_heredoc_strip_357.py::test_subst_heredoc_body_bleibt_im_strip_ergebnis`
- **AC-3:** Given ein Heredoc in `$( … )` hinter `git`, `gh`, `echo` oder `printf` mit beliebigem Body / When `strip_heredoc_bodies` ihn verarbeitet / Then wird der Body nie entfernt (Befehl unverändert), auch ohne Klammer-/Quote-Zeilen
  - Test: `tests/test_heredoc_strip_357.py::test_subst_heredoc_wird_nie_gestrippt`
- **AC-4:** Given die Kontrollfälle Body-Zeile `EOF)"` (F001 aus #357) und `echo hi` plus Leak-Zeile / When beide Hooks prüfen / Then blocken beide weiterhin mit Exit 2
  - Test: `tests/test_heredoc_strip_357.py::test_kontrollfaelle_bleiben_geblockt`
- **AC-5:** Given `git commit -m "$(cat <<'EOF' … )"` mit Gate-Wörtern (z. B. `.env`) im Text / When `bash_gate` und `secrets_guard` prüfen / Then kein Fehlalarm (Exit 0), und die Gegenprobe ohne Heredoc mit Leak-Zeile blockt (Exit 2)
  - Test: `tests/test_heredoc_strip_357.py::test_commit_message_in_subst_ohne_fehlalarm`
- **AC-6:** Given ein Heredoc außerhalb einer Befehlsersetzung (`cat > notiz.md <<'EOF'` mit Gate-Wort im Body) / When `strip_heredoc_bodies` ihn verarbeitet / Then wird der Body weiter entfernt (Bestandsverhalten aus #357 bleibt)
  - Test: `tests/test_heredoc_strip_357.py::test_heredoc_ausserhalb_befehlsersetzung_wird_weiter_entfernt`
- **AC-7:** Given die Datenfälle `commit_message` und `pr_body` aus `DATA` / When sie geprüft werden / Then liegen sie in der Gruppe „bleibt im Scan" und erwarten einen unveränderten Befehl
  - Test: `tests/test_heredoc_strip_357.py::test_data_gruppe_bleibt_im_scan`
- **AC-8:** Given der Differenztest-Generator mit festem Seed / When er Body-Zeilen erzeugt / Then kommen Zeilen mit unausgeglichener `)` und `"` ohne vorangestelltes `#` vor
  - Test: `tests/test_heredoc_bash_oracle_357.py::test_generator_erzeugt_unmaskierte_klammer_quote_zeilen`
- **AC-9:** Given die feste Stichprobe des Differenztests (Seeds 11, 357) mit erweitertem Generator / When er gegen die echte bash läuft / Then bleibt jede von bash ausgeführte Folgezeile im strip-Ergebnis sichtbar (grün lokal mit bash 3.2 und in der CI mit bash 5.2)
  - Test: `tests/test_heredoc_bash_oracle_357.py::test_feste_stichprobe_findet_keine_ausgefuehrte_folgezeile_im_strip`
- **AC-10:** Given die Hilfen `_HEREDOC_SAFE_OUTER`, `_segment_command_word`, `subst_ok` / When das Repo nach weiteren Verwendungen durchsucht wird / Then sind sie aus `hook_utils.py` entfernt, sofern sonst ungenutzt, und `strip_heredoc_bodies` behält die Signatur `(command: str) -> str`
  - Test: `tests/test_heredoc_strip_357.py::test_tote_helfer_entfernt_und_signatur_unveraendert`

> Die Test-Zuordnung steht bei der Spec-Erstellung; nach der Freigabe ist diese Datei eingefroren (#230).

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_heredoc_strip_357.py tests/test_heredoc_bash_oracle_357.py`
- Regression: `pytest tests/test_bash_gate_freetext_fixes_64_75.py tests/test_bash_gate_erkennung_299.py tests/test_secrets_guard*.py`
- Vollsuite vor dem Abschluss; die CI (bash 5.2) ist der Zeuge für bash 5.x.

Pflicht nach grünen Tests: Durchlauf des Nachstellfalls mit den echten Hooks (stdin) und mit `/bin/bash` 3.2 als Gegenprobe, dass die Sonde ausgeführt würde, aber geblockt wird.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Es existiert kein ADR-Verzeichnis (`docs/adr/` leer bzw. nicht vorhanden); die Entscheidungshistorie liegt in Issues (#276, #357, #362, #365). Inhaltlich kippt diese Änderung die #362-Annahme „ein `"$(cat <<'E'`-Body hinter git/gh/echo/printf ist zweifelsfrei Daten": bash 3.2 beendet die Ersetzung vor dem Heredoc-Ende, der Body kann Code enthalten. Begründung: Der Scanner kann das Ende der Ersetzung ohne Nachbildung der bash-Parser nicht bestimmen (Alternative C scheiterte schon in #276/#357); der Regelweg „nie entfernen" ist einfacher, kürzer (Code wird gelöscht) und schließt auch unbekannte bash-Varianten. Der Preis (ca. 9 % Fehlalarme bei `gh` mit Gate-Wörtern, Ausweg `--body-file`) ist ein Fehlalarm statt einer Umgehung. Kein Sprachmodell nötig.

## Changelog

- 2026-10-05: Initial spec created
