# Context: fix-issue-30-31-bash-gate-false-positives

## Request Summary
Issues #30 und #31: `core/hooks/bash_gate.py` blockiert harmlose, nicht-state-verändernde Bash-Kommandos fälschlich als "Freigabe-/Erfolgs-Marker-Manipulation". Zwei kombinierte Ursachen: (1) `_has_real_redirect()` erkennt `2>&1` (Stderr-zu-Stdout-Umleitung) fälschlich als Datei-Write-Redirect (#31), (2) `APPROVAL_MARKER_PATTERNS` matcht auf den gesamten rohen Kommando-String statt nur auf tatsächliche Datei-/State-Referenzen — Freitext-Erwähnungen von z.B. `adversary_verdict` in Commit-/PR-Texten lösen den Block aus, obwohl keine State-Datei berührt wird (#30, Teil 2).

Beide Bugs wurden in dieser Session bereits live reproduziert: Der `gh pr create`-Befehl für PR #32 wurde blockiert, weil der PR-Body das Wort `adversary_verdict` als Freitext enthielt UND `cat <<EOF` (Heredoc zum Aufbau des Body-Strings) als Write-Indicator gewertet wurde.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/bash_gate.py` | Enthält beide Bugs: `_has_real_redirect()` (Zeile 154-178, aktuelle Zeilennummern ggf. abweichend — siehe Implementierungsdetails), `APPROVAL_MARKER_PATTERNS`/`_references_approval_marker()` (Zeile 60-65, 142-143), kombiniert angewendet in `main()` Schritt 3a (Zeile ~287-300) |

## Existing Patterns
- `_has_write_indicator()` kombiniert `WRITE_INDICATORS`-Regex-Liste (statische Muster wie `rm\s`, `mv\s`, `cat\s*<<`, `python3?\s+-c`) mit `_has_real_redirect()` (Shell-Redirect-Erkennung via `shlex`).
- `_has_real_redirect()` nutzt bereits `shlex.split()` um Redirects innerhalb von quoted Strings korrekt zu ignorieren (das war der Fix für einen früheren False-Positive, siehe Docstring-Kommentar "haeufigste False-Positive der State-Integrity-Regel"). Die `2>&1`-Erkennung wurde dabei nicht mitbedacht.
- `_references_approval_marker()` ist ein reiner `re.search()` über den gesamten rohen `command`-String — keine Unterscheidung zwischen "Marker-Text als Datei-Pfad referenziert" und "Marker-Text als Freitext in Anführungszeichen/Commit-Message erwähnt".
- Schritt 3a in `main()` kombiniert `_references_approval_marker(command) and _has_write_indicator(command)` — beide Prüfungen sind unabhängig voneinander auf den gesamten String angewendet, ohne zu verifizieren, dass der Write-Indicator tatsächlich AUF den referenzierten Marker/Pfad wirkt (kausale Entkopplung).
- Git-Kommandos sind bereits explizit ausgenommen (`is_git_command`-Check, Zeile ~286-287) — genau mit der Begründung "eine Commit-Message oder Doku DARF die Marker-Namen erwaehnen". `gh pr create` ist aber kein `git `-Kommando und fällt nicht unter diese Ausnahme, obwohl dieselbe Begründung (Freitext in einem PR-Body, keine Datei-Manipulation) genauso zutrifft.

## Zusätzlicher, verwandter Fund (nicht Teil von #30/#31, separat zu behandeln)
Bei der Recherche zu dieser Session wurde ein drittes, strukturell identisches False-Positive-Muster live reproduziert: Schritt 3b (`_references_protected(command) and _has_write_indicator(command)`) blockierte einen reinen Lese-Befehl (`cat <fremdes-repo>/.claude/settings.json | python3 -c "..."`), weil `PROTECTED_FILE_PATTERNS` unverankert auf jeden Vorkommen von `.claude/settings.json` im String matcht (auch in einem fremden Projekt-Pfad) UND `python3\s+-c` als Write-Indicator zählt, obwohl der `-c`-Code nur von Stdin liest. Gleiche Wurzelursache (Freitext-/Pfad-Matching ohne kausale Verknüpfung mit dem tatsächlichen Ziel), aber ein eigener Bug — sollte als separates Issue verfolgt werden, nicht in diesen Fix mit hineingezogen werden (Scope-Disziplin).

## Dependencies
- Upstream: keine — `bash_gate.py` ist ein PreToolUse-Hook, wird von der Harness bei jedem Bash-Tool-Aufruf ausgeführt.
- Downstream: Jeder Bash-Aufruf eines Agenten in einem Projekt mit diesem Framework ist betroffen. Besonders schmerzhaft bei `gh pr create`/`gh issue create` mit mehrzeiligem Body (Heredoc-Pattern) und bei Kommandos, die über das Verdict-/Approval-System selbst sprechen (Bug-Reports, Doku, Commit-Messages) — ironischerweise am ehesten bei der Arbeit AM Framework selbst.

## Existing Specs
Keine dedizierte Spec zu `bash_gate.py`'s Approval-Marker- oder Redirect-Erkennung in `docs/specs/` gefunden.

## Risks & Considerations
- **Sicherheitsbalance:** `APPROVAL_MARKER_PATTERNS` und `_has_real_redirect()` sind bewusst konservativ (deny-by-default) gebaut, um zu verhindern, dass ein Agent Freigabe-Marker selbst manipuliert (specification gaming). Der Fix darf diese Schutzfunktion nicht aufweichen — er soll nur die False-Positive-Rate senken, nicht die Erkennung echter Manipulationsversuche (z.B. `echo VERIFIED > .claude/workflows/x.json` muss weiterhin blockiert werden).
- **#31-Fix:** `target != "/dev/null"` muss zusätzlich gegen ein fd-Duplizierungs-Muster wie `^&\d+$` geprüft werden (matcht `&1`, `&2`, ...). Das gilt für BEIDE Stellen, die `_has_real_redirect()`/`_raw_redirect()` nutzen (auch der `sh -c`/`eval`-Fallback `_raw_redirect()` hat denselben Bug, siehe Issue #31 vollständig lesen für Details zu allen betroffenen Stellen).
- **#30-Fix (Freitext-Marker):** Zwei mögliche Ansätze aus dem Issue: (a) `_references_approval_marker()` nur auf Kommando-Teile anwenden, die tatsächlich einen Dateipfad referenzieren, kombiniert mit `_references_protected()` auf denselben Pfad; (b) Marker-Patterns nur greifen lassen, wenn sie zusammen mit einem tatsächlichen Ziel-Pfad (`workflow.py`, `*.json` State-Datei) im selben Kommando auftauchen. Muss mit bestehenden Tests (falls vorhanden) und der Git-Ausnahme-Logik (Zeile ~286-287) konsistent bleiben — evtl. lässt sich die gleiche Ausnahme-Idee (nicht `git `, sondern generischer: kein direkter State-Datei-Zugriff) verallgemeinern.
- Kein GitHub Actions/CI in diesem Repo — Verifikation ausschließlich über lokale Tests + Adversary-Dialog.
- Gefahr von Over-Engineering: Issue #30 schlägt vor, Marker-Matching an `_references_protected()` auf denselben Pfad zu koppeln — das ist der sauberste Ansatz, sollte aber nicht zu kompliziertem Parsing führen, das seinerseits neue False-Positives/Negatives erzeugt. Pragmatismus vor Vollständigkeit.

## KRITISCHER FUND (Plan/Sonnet-Review, durch Code-Lektüre verifiziert)

Der naive Fix 30 (`_references_approval_marker(command) and _references_protected(command) and _has_write_indicator(command)`) öffnet eine echte Sicherheitslücke, wenn er ungeprüft übernommen wird:

Die tatsächlichen Freigabe-Marker-Dateien liegen laut `post_implementation_gate.py`/`phase_listener.py`/`workflow.py` direkt unter `.claude/` — **nicht** unter `.claude/workflows/`:
- `.claude/pending_validation_<workflow>.json` (`post_implementation_gate.py:61`, `workflow.py:1049`)
- `.claude/user_approved_validation_<workflow>` (leerer Marker, `post_implementation_gate.py:65`, `phase_listener.py:207`, `workflow.py:1064`)

**Keines** der 5 Einträge in `PROTECTED_FILE_PATTERNS` (Zeile 46-52) matcht diese Pfade:
```python
PROTECTED_FILE_PATTERNS = [
    r"\.claude/workflows/[^\s]*\.json",
    r"workflow_state\.json",
    r"user_override_token\.json",
    r"\.claude/hooks/[^\s]*\.py",
    r"\.claude/settings\.json",
]
```

Verifiziert per Code-Lektüre (Ausführung des Test-Aufrufs selbst durch den noch nicht gefixten Bug blockiert — ironische Selbstreferenz): `touch .claude/user_approved_validation_myworkflow` matcht `_references_approval_marker()` (`user_approved_`-Pattern) UND `_has_write_indicator()` (`touch\s`-Pattern), aber KEINEN der `PROTECTED_FILE_PATTERNS`. Mit dem naiven Fix 30 würde dieser klassische Fake-Approval-Angriff (der Schritt 3a laut Code-Kommentar Zeile 54-59 explizit verhindern soll) nicht mehr blockiert — eine echte Regression.

**Korrigierter Fix-Plan:** `PROTECTED_FILE_PATTERNS` MUSS vor der Kopplung um die beiden fehlenden Marker-Pfad-Muster erweitert werden (z.B. `\.claude/pending_validation_[^\s]*\.json`, `\.claude/user_approved_validation_[^\s]*`). Erst danach ist die Kopplung an `_references_protected()` sicherheitsneutral. Reihenfolge im Fix: (1) Redirect-Fix (#31, isoliert), (2) `PROTECTED_FILE_PATTERNS` erweitern, (3) Marker-Kopplung (#30) mit Regressionstest für `touch .claude/user_approved_validation_x` (muss weiterhin blockiert bleiben).
