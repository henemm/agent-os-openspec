# Context: fix-365-heredoc-subst-klammer

## Request Summary
`hook_utils.strip_heredoc_bodies` (seit #362/3.36.1) entfernt den Body eines Heredocs in einer
Befehlsersetzung (`gh pr create --body "$(cat <<'EOF' … )"`). bash 3.2 beendet die Ersetzung aber
schon an einer Body-Zeile mit unausgeglichener `)`, führt danach folgende Zeilen als Befehle aus —
der Scanner hat sie als Body entfernt, `bash_gate` und `secrets_guard` sehen sie nicht (#365).

## Reproduktion (2026-10-05, Stand origin/main f5cb1c1, echter Hook per stdin)
Skripte im Scratchpad: `repro365.py`, `shell_orakel365.py`, `trigger365.py`.

| Fall | strip behält Leak-Zeile? | secrets_guard | bash_gate |
|------|--------------------------|---------------|-----------|
| `gh pr create … "$(cat <<'EOF'` / `x` / `y)"` / **Leak** / `EOF` / `)"` | nein | **Exit 0** | **Exit 0** |
| dasselbe mit `echo "$(…` statt gh | nein | **Exit 0** | **Exit 0** |
| Kontrolle: Body-Zeile `EOF)"` (F001 aus #357) | ja | Exit 2 | Exit 2 |
| Kontrolle: `echo hi` + Leak | – | Exit 2 | Exit 2 |

**Welche Shell führt die Zeile wirklich aus** (Sonde = Datei anlegen, nicht `echo`, sonst druckt `cat` den Text):

| Shell | `x="$(cat <<'EOF'` / `y)"` / Sonde / `EOF` |
|-------|---------------------------------------------|
| /bin/bash 3.2.57 | **führt aus** |
| /bin/sh (bash 3.2, POSIX) | **führt aus** |
| zsh, dash | führen nicht aus |
| bash 5.x | **nicht prüfbar** (kein bash 5, kein docker; CI läuft auf ubuntu-latest = bash 5.2) |

Das Bash-Werkzeug dieser Sitzung läuft unter zsh — betroffen sind Nutzer mit bash 3.2/`sh` als Ausführer.

**Auslöser genau** (Tabelle `trigger365.py`): eine **unausgeglichene** `)` im Body, gefolgt von einem `"`
irgendwo später im Body. Harmlos: `y)` ohne späteres `"`, balancierte `(y)`, Markdown-Links `[l](url)`,
ein Apostroph davor (`it's a)` schluckt bis zum nächsten `'`). Gleiches Verhalten bei `x="$(`, `echo "$(`
und `git commit -m "$(`.

**Echte Texte lösen es kaum aus:** 0 von 120 gemergten PR-Texten dieses Repos führen in bash 3.2 eine
Folgezeile aus. Das Risiko ist ein selten, aber real auslösbarer Fall (absichtlich oder durch Text wie
`1) … "x"`), kein Alltag.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/hook_utils.py:1014-1130` | `_heredoc_bodies`: `$(`-Zweig (`subst_ok`, `_HEREDOC_SAFE_OUTER`, `_segment_command_word`) setzt `ok=True` für Bodies in `"$(cat <<'E'` hinter git/gh/echo/printf — Ort des Fixes |
| `core/hooks/hook_utils.py:1171` | `strip_heredoc_bodies` (Signatur bleibt) |
| `core/hooks/bash_gate.py:845`, `secrets_guard.py:163`, `secret_egress_guard.py:454` | Aufrufer, unverändert |
| `tests/test_heredoc_strip_357.py` | `DATA["commit_message"]`, `DATA["pr_body"]` erwarten Stripping in `$(`; `terminator_with_paren_in_subst` |
| `tests/heredoc_bash_oracle.py` | Differenztest; Generator maskiert `)`/`(`/Quote-Zeilen mit `#` (Z. ~59) und zeigt deshalb diese Lücke nie; Öffner-Formen Z. 111–113 |
| `tests/test_heredoc_bash_oracle_357.py` | feste CI-Stichprobe (Seeds 11, 357), läuft mit bash 5.2 auf ubuntu |
| `tests/test_bash_gate_freetext_fixes_64_75.py:162` | Commit-Body-Test (`test_command_substitution_heredoc_commit_allowed`) |

## Existing Patterns
- Der Scanner ist fail-closed (`_HeredocUnsure` → Befehl unverändert). Zusätzliche Vorsicht: Body-Zeile mit Endwort-Präfix → unsicher (Fall `E)`).
- Die #53-Freitext-Ausnahme (shlex, `-m`/`--body`) in `secrets_guard` und `bash_gate` überspringt `"$(cat <<'EOF' … )"` als ein Wort — daher ist `git commit -m` / `gh … --body` auch ohne Stripping nur teilweise vor Fehlalarmen geschützt (siehe Messung).

## Dependencies
- Upstream: `re` (Standardbibliothek). Downstream: `bash_gate`, `secrets_guard`, `secret_egress_guard`, also jeder Bash-Aufruf in allen Projekten.

## Existing Specs
- Keine Entity-Spec. Historie: #64/#75, #276/#356, #357 (#362), Prüfprotokolle und Vorarbeit an #365 (Kommentar mit Patch und Angriffstests aus dem abgebrochenen Workflow fix-357-heredoc-scan).

## Risks & Considerations
- Gate-Code, HIGH: Gegenprüfung mindestens 2 Runden.
- Dritter Befund der Klasse „bash beendet die Ersetzung früher als die Heuristik" (#357: `E)"`, jetzt `y)"`). Jede Klasse-Korrektur zeigte bisher die nächste Variante → Fix so wählen, dass er die Klasse schließt, nicht eine Schreibweise.
- bash-5-Verhalten ist lokal nicht prüfbar; CI (bash 5.2) ist der einzige Zeuge. Der Differenztest sieht die Lücke aber nicht, solange sein Generator `)`-Zeilen mit `#` maskiert.

## Analysis

### Type
Bug (Sicherheitslücke im Scan: zu viel entfernt → echter Befehl ungeprüft).

### Root Cause
`_heredoc_bodies` sucht das Ende des Bodys nur als exakte Terminator-Zeile (plus Präfix-Prüfung für `E)`).
Der Scanner nimmt an, dass der Body bis dahin reiner Text ist, weil er das Heredoc selbst versteht.
bash 3.2 versteht das Heredoc innerhalb von `$( … )` aber nicht: sein alter Parser zählt Klammern und
Quotes im Rohtext, schließt die Ersetzung an der ersten unausgeglichenen `)` und führt den Rest als
Befehle aus. Ein Body, den der Scanner als „Daten" entfernt (`ok=True` nur im Zweig `"$(` hinter
git/gh/echo/printf), kann so echten Code enthalten.

### Recherche
Bash-Referenz (Command Substitution): Bei der Form `$(command)` führt bash den Befehl aus und ersetzt;
ältere Versionen parsen den Text in der Ersetzung ohne Kenntnis eingebetteter Heredocs, deshalb das
bekannte Verhalten, dass `)` in einem Heredoc-Body die Ersetzung beendet. Der bash-5.2-Hinweis im
Scanner (`E)` beendet in `$(…)`) ist derselbe Mechanismus. Eine belastbare Quelle zum genauen bash-5.x-
Verhalten für `y)"` habe ich nicht; Prüfung deshalb per Differenztest auf CI (bash 5.2) und lokal (3.2).

### Alternativen
Zahlen: 120 gemergte PR-Texte als `gh pr create`-Body durch `bash_gate`; „Fehlalarm" = Block, den der
aktuelle Stand nicht auslöst.

| Weg | Fehlalarme (PR-Texte) | Bewertung |
|-----|-----------------------|-----------|
| **A: Bodies in `$( … )` nie entfernen (Empfehlung)** | 11 von 120 (9 %), nur bei `gh pr/issue …` mit Gate-Wörtern im Text (geschützter Pfad, Marker, `.env`); `git commit -m` unberührt (Git-Schnellpfad, 0) | Schließt die ganze Klasse inkl. bash-5-Unbekannten, keine Heuristik, Code wird kürzer (`subst_ok`, `_HEREDOC_SAFE_OUTER`, `_segment_command_word` entfallen). Ausweg bei Fehlalarm: `--body-file` (Claude wählt ihn selbst, kein Eingriff für Henning). Kippt die Entscheidung aus #362, den `"$(cat <<'E'`-Body von gh/git/echo/printf zu entlasten. |
| B: nur entfernen, wenn Body keine `)`→`"`-Folge hat | ca. 5 % | Beruht auf meiner Auslöser-Tabelle (nur bash 3.2 belegt); löst die nächste bash-Variante nicht. Zeichenregeln, die Quotes nachbilden, verweigern bei Apostrophen 24 % und sind nicht kürzer. |
| C: genaue Nachbildung des bash-3.2-Klammerzählers | 24 % (unnötig verweigert) bei 0 Fehlstellen an echten Texten | Ein halber Shell-Parser — genau der Weg, der in #276/#357 dreimal scheiterte. Verworfen. |
| D: nur dokumentieren + Differenztest erweitern | 0 | Lässt die belegte Lücke offen. Der Test-Teil ist trotzdem Pflicht (siehe unten). |
| Ohne Scanner: `gh pr create`-Texte nur über `--body-file` zulassen | – | Ändert den Arbeitsablauf aller Projekte; Regel müsste in `bash_gate` stehen, nicht im Scanner. Eigenes Thema. |

„Ohne Sprachmodell geht es" — alles Regel/Regex, kein Modell nötig; ein Modell wäre hier keine Alternative.
Gekippte frühere Entscheidung: #362-Annahme „ein `"$(cat <<'E'`-Body hinter git/gh/echo/printf ist zweifelsfrei Daten".

### Technischer Ansatz (Empfehlung A)
1. `hook_utils._heredoc_bodies`: Im `$(`-Zweig immer `ok = False`; die dann toten Hilfen
   (`_HEREDOC_SAFE_OUTER`, `_segment_command_word` nur noch falls anderweitig genutzt prüfen) entfernen.
   Die übrigen Wege (Datei/stdin-Konsumenten außerhalb von Ersetzungen) bleiben unverändert.
2. Tests: `tests/test_heredoc_strip_357.py` — `DATA["commit_message"]` und `DATA["pr_body"]` verschieben
   in neue Gruppe „Heredoc in Befehlsersetzung bleibt im Scan"; neuer Angriffstest `y)"` (aus dem Patch an
   #365) über beide Hooks und strip-Ergebnis; `terminator_with_paren_in_subst` bleibt.
3. Differenztest: `tests/heredoc_bash_oracle.py` — Body-Zeilen mit unausgeglichener `)` und `"` ohne
   `#`-Maskierung ergänzen, damit CI (bash 5.2) und lokal (3.2) die Klasse sehen; Öffner Z. 111–112
   behalten (jetzt: Folgezeilen müssen sichtbar bleiben).
4. Messung als Beleg in die Spec: 11/120 vs. 0/120, 0/120 reale Auslöser.
5. `CHANGELOG.md` unter `[Unreleased]`.

### Affected Files
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | `$(`-Zweig: nie entfernen; tote Hilfen löschen |
| `tests/test_heredoc_strip_357.py` | MODIFY | DATA-Fälle umhängen, `y)"`-Angriffstests |
| `tests/heredoc_bash_oracle.py` | MODIFY | `)`-/Quote-Zeilen im Body unmaskiert erzeugen |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` |

`bash_gate.py`, `secrets_guard.py`, `secret_egress_guard.py` bleiben unverändert.

### Scope Assessment
- Files: 4 (1 Code, 2 Tests, Changelog); Estimated LoC: ca. −30/+25 Code, +60 Test → unter 120
- Risk Level: HIGH (Gate-Code) → Adversary 2 Runden, Gegenprüfung mit echter bash 3.2 UND CI-bash-5.2-Nachweis
- Der Differenztest-Teil ist Pflicht und nicht verhandelbar: ohne ihn bleibt die Klasse unsichtbar.

### Open Questions
- Keine technische Frage offen. Produkt-Hinweis für den PO: Empfehlung A kostet bei `gh pr create` mit
  Gate-Wörtern im Text etwa jeden elften Aufruf einen Fehlalarm (Claude weicht auf `--body-file` aus).
  Wer weniger Reibung will, nimmt Weg B (ca. 5 %) und akzeptiert, dass nur die belegte Variante geschlossen wird.
- Korrektur zur Vorarbeit an #365: Der Kommentar dort nannte „kein neuer Fehlalarm" nur für `.env` und
  `git commit`; für `gh pr create` mit geschütztem Pfad im Text stimmt das nicht (gemessen).
