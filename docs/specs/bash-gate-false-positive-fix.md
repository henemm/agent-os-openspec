---
entity_id: bash_gate_false_positive_fix
type: bugfix
created: 2026-07-02
updated: 2026-07-02
status: draft
version: "1.0"
tags: [bash-gate, false-positive, security, hooks, state-integrity]
test_targets:
  - core/hooks/bash_gate.py
workflow: fix-issue-30-31-bash-gate-false-positives
---

# Bash Gate False-Positive Fix (Issues #30, #31)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue #30:** https://github.com/henemm/agent-os-openspec/issues/30 — Freitext-Erwähnung eines Approval-Markers (z.B. `adversary_verdict` in einem PR-Body) löst fälschlich einen State-Integrity-Block aus, obwohl keine Datei manipuliert wird.
- **Issue #31:** https://github.com/henemm/agent-os-openspec/issues/31 — `2>&1` (Stderr-zu-Stdout FD-Duplizierung) wird fälschlich als echter Datei-Redirect erkannt.

## Purpose

`core/hooks/bash_gate.py` blockiert aktuell harmlose, nicht-state-verändernde Bash-Kommandos fälschlich als "Freigabe-/Erfolgs-Marker-Manipulation". Live reproduziert in dieser Session: `gh pr create --body "... adversary_verdict ..." 2>&1` wurde geblockt, obwohl weder eine State-Datei geschrieben noch ein echter Redirect vorlag. Dieser Fix behebt beide Ursachen (Freitext-Marker-Matching ohne Ziel-Bezug, FD-Duplizierung als Fake-Redirect) UND schließt dabei eine zusätzlich entdeckte Sicherheitslücke in `PROTECTED_FILE_PATTERNS`, die sonst durch den #30-Fix erst entstehen würde.

## Dependencies

| Komponente | Typ | Abhängigkeit |
|-----------|-----|-------------|
| `bash_gate.py` | bestehender Hook | PreToolUse Bash — enthält alle drei zu ändernden Funktionen/Konstanten |
| `post_implementation_gate.py` | bestehender Hook | Erzeugt die realen Marker-Dateien `.claude/pending_validation_<wf>.json` / `.claude/user_approved_validation_<wf>` (Zeile 61, 65) — definiert die Pfade, die `PROTECTED_FILE_PATTERNS` abdecken muss |
| `phase_listener.py` | bestehender Hook | Legitimer Erzeuger von `.claude/user_approved_validation_<wf>` (Zeile 207) — einziger erlaubter Schreibweg |
| `workflow.py` | bestehender Hook | Legitimer Schreibweg für dieselben Marker-Pfade (Zeile 1049, 1064) |
| `tests/test_gate_coverage.py` | bestehende Tests | Stilvorlage für Direktimport-Pattern (`sys.path.insert` auf `core/hooks`) |

## Source

- **File:** `core/hooks/bash_gate.py`
- **Identifier:** `PROTECTED_FILE_PATTERNS`, `APPROVAL_MARKER_PATTERNS`, `_references_protected()`, `_references_approval_marker()`, `_raw_redirect()`, `_has_real_redirect()`, `main()` Schritt 3a

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/bash_gate.py` | MODIFY | 3 Teilfixes: FD-Dup-Ausschluss in `_raw_redirect()`/`_has_real_redirect()`, `PROTECTED_FILE_PATTERNS`-Erweiterung, Kopplung von Schritt 3a an `_references_protected()` |
| `tests/test_bash_gate_false_positives.py` | CREATE | Regressionstests für beide Bugs + alle 5 Sicherheits-Gegenproben |

### Estimated Changes

- Files: 2
- LoC: +65/-8 (ca.)

## Root Cause

### Bug 1 (#31) — FD-Duplizierung als Datei-Redirect erkannt

`_has_real_redirect()` (Zeile 154-178) prüft per `shlex`, ob ein `>`/`>>`-Operator-Token ein Ziel `!= "/dev/null"` hat. `2>&1` (Stderr-zu-Stdout-Duplizierung, kein Datei-Write) wird tokenisiert zu `2>&1` mit Operator-Match `target = "&1"`. Da `"&1" != "/dev/null"`, wird es fälschlich als echter Redirect gewertet. Derselbe Bug existiert in `_raw_redirect()` (Zeile 146-151), dem Fallback-Pfad für verschachtelte Shells (`sh -c`, `eval`).

### Bug 2 (#30) — Freitext-Marker-Matching ohne Ziel-Bezug

`_references_approval_marker()` (Zeile 142-143) ist ein reiner `re.search()` über den **gesamten rohen** `command`-String. Schritt 3a in `main()` (Zeile 280-299) blockt, sobald `_references_approval_marker(command) and _has_write_indicator(command)` beide wahr sind — unabhängig davon, ob der Write-Indicator tatsächlich auf eine Datei zielt, die den Marker-Text enthält. Ein PR-Body, der das Wort `adversary_verdict` als Freitext erwähnt, plus ein beliebiger Write-Indicator irgendwo im selben Kommando (auch durch Bug 1 fälschlich erkannt) reicht für einen Block, obwohl keine State-Datei berührt wird.

### Sicherheits-Fund — `PROTECTED_FILE_PATTERNS` deckt die realen Marker-Pfade nicht ab

Der naheliegende Fix für Bug 2 — Schritt 3a zusätzlich an `_references_protected(command)` koppeln — öffnet eine Regression: Die realen Freigabe-Marker-Dateien liegen laut `post_implementation_gate.py:61,65`, `phase_listener.py:207` und `workflow.py:1049,1064` unter `.claude/pending_validation_<workflow>.json` und `.claude/user_approved_validation_<workflow>` — **keines** der 5 bestehenden `PROTECTED_FILE_PATTERNS`-Einträge (Zeile 46-52) matcht diese Pfade. Ohne Erweiterung würde `touch .claude/user_approved_validation_myworkflow` (klassischer Fake-Approval-Angriff) nach der Kopplung an `_references_protected()` **nicht mehr geblockt** — eine echte Sicherheitsregression gegenüber dem Status quo, in dem Schritt 3a diesen Angriff bereits (ohne Protected-Check) korrekt blockt. Deshalb MUSS `PROTECTED_FILE_PATTERNS` vor der Kopplung erweitert werden.

## Implementation Details

Reihenfolge zwingend: Teil 1 (isoliert) → Teil 2 (Voraussetzung) → Teil 3 (nutzt Teil 2).

### Teil 1 — Fix #31: FD-Duplizierung ausschließen

**`_raw_redirect()` (Zeile 146-151), vorher:**

```python
def _raw_redirect(command: str) -> bool:
    """Roher Redirect-Scan ueber den gesamten String (konservativ)."""
    for m in re.finditer(r"(?<!\d)>{1,2}\s*(\S+)", command):
        if m.group(1) != "/dev/null":
            return True
    return False
```

**Nachher:**

```python
def _raw_redirect(command: str) -> bool:
    """Roher Redirect-Scan ueber den gesamten String (konservativ)."""
    for m in re.finditer(r"(?<!\d)>{1,2}\s*(\S+)", command):
        target = m.group(1)
        if target == "/dev/null":
            continue
        if re.match(r"^&\d+$", target):
            continue  # FD-Duplizierung (2>&1, >&2, ...) ist kein Datei-Write
        return True
    return False
```

**`_has_real_redirect()` (Zeile 171-178), vorher:**

```python
    for i, tok in enumerate(tokens):
        m = re.match(r"^\d*>{1,2}(.*)$", tok)  # echter Operator-Token: >  >>  2>  >file
        if not m:
            continue
        target = m.group(1) or (tokens[i + 1] if i + 1 < len(tokens) else "")
        if target and target != "/dev/null":
            return True
    return False
```

**Nachher:**

```python
    for i, tok in enumerate(tokens):
        m = re.match(r"^\d*>{1,2}(.*)$", tok)  # echter Operator-Token: >  >>  2>  >file
        if not m:
            continue
        target = m.group(1) or (tokens[i + 1] if i + 1 < len(tokens) else "")
        if not target or target == "/dev/null":
            continue
        if re.match(r"^&\d+$", target):
            continue  # FD-Duplizierung (2>&1, >&2, ...) ist kein Datei-Write
        return True
    return False
```

Beide Stellen nutzen dasselbe Ausschlussmuster `^&\d+$` (matcht `&1`, `&2`, `&10`, ...). Ein echtes Datei-Ziel wie `output.log` oder `.claude/workflows/x.json` matcht dieses Muster nicht und wird weiterhin korrekt als Redirect erkannt.

### Teil 2 — `PROTECTED_FILE_PATTERNS` erweitern

**Zeile 46-52, vorher:**

```python
PROTECTED_FILE_PATTERNS = [
    r"\.claude/workflows/[^\s]*\.json",
    r"workflow_state\.json",
    r"user_override_token\.json",
    r"\.claude/hooks/[^\s]*\.py",
    r"\.claude/settings\.json",
]
```

**Nachher:**

```python
PROTECTED_FILE_PATTERNS = [
    r"\.claude/workflows/[^\s]*\.json",
    r"workflow_state\.json",
    r"user_override_token\.json",
    r"\.claude/hooks/[^\s]*\.py",
    r"\.claude/settings\.json",
    r"\.claude/pending_validation_[^\s]*\.json",
    r"\.claude/user_approved_validation_[^\s]*",
]
```

Diese beiden neuen Patterns decken exakt die Pfade ab, die `post_implementation_gate.py`, `phase_listener.py` und `workflow.py` tatsächlich als Freigabe-Marker verwenden.

### Teil 3 — Fix #30: Marker-Match an Protected-Path-Referenz koppeln

**`main()` Schritt 3a (Zeile 280-299), vorher (Kernbedingung):**

```python
    is_git_command = command.lstrip().startswith("git ")
    if not is_git_command and _references_approval_marker(command) and _has_write_indicator(command):
        block(
            "BLOCKED: Freigabe-/Erfolgs-Marker duerfen NICHT per Bash erzeugt, "
            ...
        )
```

**Nachher (Kernbedingung):**

```python
    is_git_command = command.lstrip().startswith("git ")
    if (
        not is_git_command
        and _references_approval_marker(command)
        and _has_write_indicator(command)
        and _references_protected(command)
    ):
        block(
            "BLOCKED: Freigabe-/Erfolgs-Marker duerfen NICHT per Bash erzeugt, "
            ...
        )
```

Der Block-Text bleibt unverändert. Nur die Bedingung wird um `_references_protected(command)` erweitert (nutzt die in Teil 2 erweiterten Patterns). Schritt 3b (Zeile 301-306, `_references_protected(command) and _has_write_indicator(command)` ohne Marker-Anforderung) bleibt komplett unverändert — er ist die primäre Verteidigungslinie gegen direkte State-Datei-Manipulation unabhängig vom Marker-Wortlaut (z.B. `echo VERIFIED > .claude/workflows/x.json`, wo kein Marker-Pattern-Text vorkommt) und deckt bereits vor diesem Fix die meisten der geforderten Sicherheits-Gegenproben ab.

## Expected Behavior

- Ein Kommando, das einen Marker-Begriff nur als Freitext enthält (PR-Body, Commit-Message, Doku-Zeile) UND keinen Protected-Pfad referenziert → **nicht** geblockt, auch wenn ein (echter oder vormals fälschlich erkannter) Write-Indicator vorkommt.
- `2>&1` / `>&2` (FD-Duplizierung) allein löst in `_has_real_redirect()`/`_raw_redirect()` **keinen** Redirect-Treffer mehr aus — unabhängig davon, ob im selben Kommando ein echtes Datei-Ziel an anderer Stelle vorkommt (das wird weiterhin erkannt).
- Jeder Bash-Versuch, `.claude/pending_validation_<wf>.json` oder `.claude/user_approved_validation_<wf>` zu erzeugen/ändern/löschen, bleibt über Schritt 3a **und** neu auch über Schritt 3b geblockt (doppelte Absicherung durch die Teil-2-Erweiterung).
- Alle bereits vor diesem Fix über Schritt 3b abgedeckten State-Manipulationen (`.claude/workflows/*.json`, `workflow_state.json`, `user_override_token.json`, `.claude/hooks/*.py`, `.claude/settings.json`) bleiben unverändert geblockt — Schritt 3b wird von diesem Fix nicht angefasst.
- Die bestehende Git-Ausnahme (`is_git_command`, Zeile 286-287) bleibt unverändert: Commit-Messages dürfen Marker-Namen weiterhin frei erwähnen.

## Error Handling

Keine der drei Änderungen führt neue Fehlerpfade ein:

- `_raw_redirect()`/`_has_real_redirect()`: Das zusätzliche `re.match(r"^&\d+$", target)` ist eine reine String-Prüfung, kann nicht werfen. Der bestehende `try/except ValueError → _raw_redirect()`-Fallback bei `shlex.split()`-Parse-Fehlern bleibt unverändert.
- `PROTECTED_FILE_PATTERNS`: Zwei zusätzliche Einträge in einer bestehenden Liste, die ausschließlich per `re.search()` konsumiert wird (`_references_protected()`) — kein neues Fehlverhalten möglich.
- `main()` Schritt 3a: Zusätzliches `and`-Glied in einer bestehenden Bedingung, keine neue Exception-Quelle. Fail-Modus bleibt konservativ (deny-by-default) — im Zweifel (Regex greift nicht eindeutig) wird weiterhin über Schritt 3b abgesichert.

## Fix-Loop Iteration 1 — Adversary-Fund und Korrektur

**Adversary-Verdikt Runde 1: BROKEN.** Der Adversary-Agent bewies per A/B-Test (git stash gegen den Vorher-Stand), dass `cd .claude && touch user_approved_validation_faketest` **vor** diesem Fix blockiert wurde (die alte, ungekoppelte `_references_approval_marker()`-Prüfung matchte den Marker-Namen unabhängig vom Pfad-Kontext), aber **nach** der Teil-3-Kopplung an `_references_protected(command)` durchrutscht — weil `_references_protected()` den vollständigen String `.claude/user_approved_validation_` zusammenhängend im Kommando erwartet, der bei vorangestelltem `cd .claude` nie zusammenhängend auftaucht. Eine echte, durch diesen Fix eingeführte Sicherheitsregression, keine Vorbedingung.

**Korrektur — zweistufige Marker-Klassifizierung statt einheitlicher Kopplung:**

Die vier Einträge in `APPROVAL_MARKER_PATTERNS` haben unterschiedliches Freitext-Risiko und werden künftig unterschiedlich behandelt:

- **Tier 1 — Feldnamen (`adversary_verdict`, `_verified\b`):** Hohes Freitext-Risiko (genau diese beiden lösten den live reproduzierten #30-Fall aus — Feldnamen tauchen plausibel in Bug-Reports/PR-Texten/Doku auf). Bleiben an `_references_protected(command)` gekoppelt (Teil 3 wie bisher).
- **Tier 2 — Marker-Dateinamen-Präfixe (`user_approved_`, `pending_validation_`):** Diese Strings SIND die Marker-Dateinamen selbst, kommen in normaler Prosa praktisch nie vor. Sie behalten die ursprüngliche, pfad-unabhängige Block-Logik (Marker-Erwähnung + Write-Indicator blockt, wie vor diesem Fix) — das ist genau die Eigenschaft, die den `cd`-Bypass verhindert, weil keine zusammenhängende Pfad-Referenz verlangt wird.

```python
# Tier 1: Feldnamen mit hohem Freitext-Risiko (Issue #30) — nur blocken, wenn
# zusaetzlich ein echter Protected-Pfad im selben Kommando referenziert wird.
APPROVAL_MARKER_PATTERNS_REQUIRE_PATH = [
    r"adversary_verdict",
    r"_verified\b",
]

# Tier 2: Marker-*Dateinamen*-Praefixe — erscheinen praktisch nie als Freitext,
# bleiben unabhaengig vom Pfad-Kontext blockierend (verhindert cd-Obfuskation).
APPROVAL_MARKER_PATTERNS_FILENAME = [
    r"user_approved_",
    r"pending_validation_",
]
```

Schritt 3a in `main()`:
```python
is_git_command = command.lstrip().startswith("git ")
if not is_git_command and _has_write_indicator(command):
    if any(re.search(p, command) for p in APPROVAL_MARKER_PATTERNS_FILENAME):
        block(...)
    elif (any(re.search(p, command) for p in APPROVAL_MARKER_PATTERNS_REQUIRE_PATH)
          and _references_protected(command)):
        block(...)
```

**Trade-off, bewusst akzeptiert:** Freitext-Erwähnungen von `user_approved_`/`pending_validation_` in einem Nicht-Git-Kommando mit Write-Indicator (z.B. `gh issue create --body "...pending_validation_..." 2>&1`) können weiterhin blockiert werden — das ist kein Rückfall in den ursprünglich gemeldeten #30-Fall (der drehte sich um `adversary_verdict`), sondern eine bewusste Priorisierung von Sicherheit (kein `cd`-Bypass auf echte Marker-Dateien) über vollständige Freitext-Toleranz für diese zwei spezifischeren Muster. `--body-file` statt `--body` umgeht das ohnehin vollständig (Marker-Text landet dann nie im Bash-Kommando-String).

**Neue/geänderte Acceptance Criteria:**
- **AC-8 (präzisiert):** Given `touch .claude/user_approved_validation_myworkflow` ODER `cd .claude && touch user_approved_validation_myworkflow` als Fake-Approval-Angriff / When `main()` geprüft wird / Then bleiben BEIDE Varianten geblockt mit Exit 2, weil Tier-2-Marker pfad-unabhängig blocken.
- **AC-12 (neu):** Given `cd .claude && echo x > pending_validation_faketest.json` als pfad-verschleierter Angriff / When `main()` geprüft wird / Then bleibt er geblockt mit Exit 2 (Tier-2-Marker, unabhängig vom `cd`-Kontext).

## Known Limitations

- **Bewusst nicht in diesem Fix behandelt:** Schritt 3b (`_references_protected(command) and _has_write_indicator(command)`, Zeile 301-306) hat dieselbe strukturelle Schwäche wie der ursprüngliche Bug 2 — unverankerte Pfad-Matches (`re.search()` ohne Wortgrenzen/Anker) kombiniert mit dem sehr groben Write-Indicator `python3\s+-c` (matcht auch reine Lese-Aufrufe wie `python3 -c "..."` die nur von Stdin lesen). Live reproduziert: `cat <fremdes-repo>/.claude/settings.json | python3 -c "..."` wurde fälschlich geblockt, obwohl reiner Lesezugriff. Gleiche Wurzelursache, aber separater Scope — **Empfehlung: eigenes Issue eröffnen**, um Scope-Disziplin zu wahren und dieses Fix nicht durch zusätzliches Parsing-Risiko aufzublähen.
- Die Kopplung in Teil 3 setzt voraus, dass `PROTECTED_FILE_PATTERNS` (Teil 2) vollständig ist. Sollte künftig ein weiterer Marker-Dateipfad eingeführt werden (z.B. durch einen neuen Hook), muss `PROTECTED_FILE_PATTERNS` synchron erweitert werden — sonst entsteht dieselbe Sicherheitslücke erneut. Kein automatischer Konsistenz-Check zwischen `APPROVAL_MARKER_PATTERNS` und `PROTECTED_FILE_PATTERNS` vorhanden (Over-Engineering-Risiko laut Kontext-Dokument bewusst vermieden).
- Der Heredoc-Fall `cat <<EOF\n...\nEOF 2>&1 > output.log` schreibt tatsächlich in `output.log` — das ist korrekt kein False-Positive-Ziel dieses Fixes, weil `output.log` kein Protected-Pfad ist und daher schon vor diesem Fix nicht blockiert wurde (weder über 3a noch 3b). Dieser Fix ändert an diesem Verhalten nichts; die Aufgabenstellung fragt danach nur zur Klarstellung.

## Acceptance Criteria

- **AC-1:** Given ein `gh pr create`-Befehl dessen Body-Text "adversary_verdict" als Freitext erwähnt und mit `2>&1` endet / When bash_gate `main()` das Kommando prüft / Then wird es nicht geblockt (Exit 0).
- **AC-2:** Given das Kommando `cat logs.txt 2>&1 | less` / When `_has_real_redirect()` aufgerufen wird / Then liefert die Funktion False, weil `2>&1` reine FD-Duplizierung ist.
- **AC-3:** Given das Kommando `cat <<EOF ... EOF 2>&1 > output.log` mit echtem Datei-Ziel `output.log` / When `_has_real_redirect()` geprüft wird / Then liefert es weiterhin True für das echte Ziel.
- **AC-4:** Given der Fallback-Pfad `sh -c "cmd 2>&1"` ohne echtes Redirect-Ziel / When `_raw_redirect()` aufgerufen wird / Then liefert es False statt fälschlich True.
- **AC-5:** Given das Kommando `echo VERIFIED > .claude/workflows/x.json` / When bash_gate `main()` geprüft wird / Then bleibt der Angriff geblockt mit Exit 2.
- **AC-6:** Given das Kommando `sed -i 's/BROKEN/VERIFIED/' .claude/workflows/x.json` / When `main()` geprüft wird / Then bleibt es geblockt mit Exit 2.
- **AC-7:** Given ein `python3 -c "..."`-Aufruf der nach `.claude/workflows/x.json` umleitet / When `main()` geprüft wird / Then bleibt es geblockt mit Exit 2.
- **AC-8:** Given `touch .claude/user_approved_validation_myworkflow` als Fake-Approval-Angriff / When `main()` nach Teil 2 und Teil 3 geprüft wird / Then bleibt es geblockt mit Exit 2, weil `PROTECTED_FILE_PATTERNS` jetzt greift.
- **AC-9:** Given `sh -c "echo VERIFIED > .claude/workflows/x.json"` als verschachtelter Shell-Angriff / When `main()` geprüft wird / Then bleibt es über den `_raw_redirect()`-Fallback geblockt mit Exit 2.
- **AC-10:** Given `git commit -m "Fix: user_approved_ workflow"` / When `main()` geprüft wird / Then bleibt es erlaubt mit Exit 0, weil die Git-Ausnahme unverändert greift.
- **AC-11:** Given die Pfade `.claude/pending_validation_myworkflow.json` und `.claude/user_approved_validation_myworkflow` / When `_references_protected()` geprüft wird / Then liefert die Funktion für beide Pfade True.

## Test Plan

Direktimport-Pattern wie in `tests/test_gate_coverage.py`. Ziel-Datei: `tests/test_bash_gate_false_positives.py`.

```python
"""Regressionstests für den Bash-Gate False-Positive-Fix (Issues #30, #31).

Deckt drei Teilfixes ab:
1. FD-Duplizierung (2>&1) wird nicht mehr als Datei-Redirect erkannt (#31)
2. PROTECTED_FILE_PATTERNS deckt die realen Marker-Dateipfade ab (Sicherheits-Fund)
3. Freitext-Marker-Erwähnung löst nur noch mit echter Protected-Path-Referenz
   einen Block aus (#30)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import bash_gate  # noqa: E402  (Pfad muss vor dem Import gesetzt sein)


# --- Teil 1 (Issue #31): FD-Duplizierung nicht als Redirect werten ---

class TestFdDuplicationNotRedirect:
    def test_stderr_to_stdout_not_real_redirect(self):
        assert bash_gate._has_real_redirect("cat logs.txt 2>&1 | less") is False

    def test_stdout_to_stderr_not_real_redirect(self):
        assert bash_gate._has_real_redirect("some_cmd >&2") is False

    def test_real_file_redirect_after_fd_dup_still_detected(self):
        cmd = "cat <<EOF\nSome text\nEOF 2>&1 > output.log"
        assert bash_gate._has_real_redirect(cmd) is True

    def test_gh_pr_create_with_marker_text_and_fd_dup_not_real_redirect(self):
        cmd = 'gh pr create --title "Fix" --body "... adversary_verdict ..." 2>&1'
        assert bash_gate._has_real_redirect(cmd) is False

    def test_raw_redirect_fallback_ignores_fd_duplication(self):
        # _raw_redirect() ist der Fallback-Pfad fuer sh -c / eval
        assert bash_gate._raw_redirect('sh -c "cmd 2>&1"') is False

    def test_raw_redirect_fallback_still_detects_real_file_target(self):
        cmd = 'sh -c "echo VERIFIED > .claude/workflows/x.json"'
        assert bash_gate._raw_redirect(cmd) is True


# --- Teil 2: PROTECTED_FILE_PATTERNS deckt reale Marker-Pfade ab ---

class TestProtectedFilePatternsCoverMarkerPaths:
    def test_pending_validation_json_is_protected(self):
        cmd = "cat .claude/pending_validation_myworkflow.json"
        assert bash_gate._references_protected(cmd) is True

    def test_user_approved_validation_marker_is_protected(self):
        cmd = "touch .claude/user_approved_validation_myworkflow"
        assert bash_gate._references_protected(cmd) is True


# --- Teil 3 (Issue #30) + Sicherheits-Gegenproben: Live-Aufruf von main() ---

def _run_bash_gate(tmp_path: Path, command: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"command": command}})
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bash_gate.py")],
        input=payload, capture_output=True, text=True, env=env,
    )


class TestFreetextMarkerRequiresProtectedPath:
    def test_gh_pr_create_freetext_marker_allowed(self, tmp_path):
        """Reproduzierter Live-Fall dieser Session: PR-Body erwaehnt
        'adversary_verdict' als Freitext, kein Protected-Path betroffen ->
        darf nicht blocken (AC-1)."""
        cmd = (
            'gh pr create --title "Fix bash_gate" '
            '--body "Fixes adversary_verdict handling" 2>&1'
        )
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 0, result.stderr

    def test_git_commit_freetext_marker_allowed(self, tmp_path):
        """AC-10: Git-Ausnahme bleibt unveraendert."""
        subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, capture_output=True)
        cmd = 'git commit -m "Fix: user_approved_ workflow"'
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 0, result.stderr


class TestRealMarkerManipulationStillBlocked:
    """Sicherheits-Gegenproben: alle 5 im Context-Dokument geforderten
    Angriffsmuster muessen nach dem Fix weiterhin geblockt werden."""

    def test_echo_verified_into_workflow_json_blocked(self, tmp_path):
        """AC-5."""
        cmd = "echo VERIFIED > .claude/workflows/x.json"
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

    def test_sed_broken_to_verified_blocked(self, tmp_path):
        """AC-6."""
        cmd = "sed -i 's/BROKEN/VERIFIED/' .claude/workflows/x.json"
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

    def test_python_c_redirect_into_workflow_json_blocked(self, tmp_path):
        """AC-7."""
        cmd = 'python3 -c "import json; print(1)" > .claude/workflows/x.json'
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

    def test_touch_fake_user_approved_marker_blocked(self, tmp_path):
        """AC-8: Regressionstest fuer den kritischen Sicherheits-Fund. Ohne
        Teil 2 (PROTECTED_FILE_PATTERNS-Erweiterung) wuerde dieser Angriff
        nach Teil 3 durchrutschen, weil user_approved_validation_* vorher in
        keinem Pattern enthalten war."""
        cmd = "touch .claude/user_approved_validation_myworkflow"
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

    def test_nested_shell_redirect_verified_blocked(self, tmp_path):
        """AC-9: _raw_redirect()-Fallback fuer verschachtelte Shells."""
        cmd = 'sh -c "echo VERIFIED > .claude/workflows/x.json"'
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr
```

## Changelog

- 2026-07-02: Initial spec erstellt (kombinierter Fix für Issues #30 und #31, inkl. Sicherheits-Fund zu `PROTECTED_FILE_PATTERNS`)
