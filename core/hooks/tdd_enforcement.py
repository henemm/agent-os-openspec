#!/usr/bin/env python3
"""
TDD Enforcement Hook — PreToolUse Edit|Write|MultiEdit

Validiert RED-Phase-Artefakte tiefgehend bevor Code-Edits in phase6+
erlaubt werden. Ergänzt edit_gate.py's einfache Boolean-Prüfung durch:

- Existenz der Artefakt-Datei auf Disk
- Mindestgröße (kein Platzhalter/leere Datei)
- Frische (<24h alt)
- Fehlerkeywords im Inhalt (echte Fehlermeldungen, nicht nur "failed")
- Keine Platzhalter-Patterns im RAHMEN der Testausgabe. Vom Runner zitierter
  Fremdinhalt (Assertion-Dumps, Quellzeilen, aufgefangenes stdout) ist davon
  ausgenommen, sonst blockt ein RED-Test ueber Framework-Dokumente das Gate mit
  dessen eigener Platzhalter-Warnung (Issue #262).

Fail-safe: Bei Import-Fehlern oder Parse-Fehlern → exit(0), nie blockieren.
"""

import os
import re
import sys
import time
from pathlib import Path


def _setup():
    hooks_dir = str(Path(__file__).parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


_setup()

import hook_utils  # noqa: E402
from hook_utils import get_tool_input, find_project_root, block, allow, get_active_workflow_name, framework_disabled  # noqa: E402
from hook_utils import is_hook_always_allowed  # noqa: E402

# Phasen in denen TDD-Enforcement gilt
TEST_REQUIRED_PHASES = {"phase6_implement", "phase6b_adversary"}

# Mindestgröße eines gültigen Artefakts in Bytes
_MIN_SIZE = 80

# Maximales Alter in Sekunden (24h)
_MAX_AGE_S = 86_400

# Keywords die echte Test-Fehler belegen
_FAILURE_RE = re.compile(
    r"\b(FAILED|ERROR|error|failed|FAIL|assert|AssertionError"
    r"|ImportError|ModuleNotFoundError|SyntaxError|TypeError"
    r"|AttributeError|NameError|NotImplementedError"
    r"|raise|Traceback|Exception|stderr)\b"
    # #275: xcbeautify-/Runner-Marker, Swift Testing, Zaehler und Exit-Code.
    # Zahlen beginnen mit 1-9: '0 failures' und 'EXIT=0' sind keine Evidenz.
    r"|[❌✖✘]"
    r"|\bTEST FAILED\b"
    r"|\bTest run with .* failed\b"
    r"|\b[1-9]\d*\s+failures?\b"
    r"|\bEXIT=[1-9]\d*\b",
    re.MULTILINE,
)

# Platzhalter-Patterns die auf gefälschte Artefakte hinweisen. Die drei
# bloßen Wörter stehen mit \b-Wortgrenzen (wie _FAILURE_RE unten), damit ein
# Testname wie "test_gate_ignores_known_placeholder_values" nicht schon durch
# den Teilstring "placeholder" matcht (Issue #89). Die Klammer-/Phrasen-
# Alternativen brauchen keine Wortgrenzen: sie enthalten Leerzeichen bzw.
# spitze Klammern, die in einem snake_case-/camelCase-Bezeichner nicht
# vorkommen können.
_PLACEHOLDER_RE = re.compile(
    r"\b(TODO|PLACEHOLDER|FIXME)\b|(<test_output>|<your output>"
    r"|insert output|copy output|example output)",
    re.IGNORECASE,
)

# TAP-Summary-Zeilen von `node --test` (enden IMMER mit '# todo 0' etc.) —
# werden VOR der Platzhalter-Pruefung entfernt, damit das TODO-Pattern nicht
# jedes echte node-Test-Artefakt als "gefaelscht" blockt (Issue #73).
# Die Fehler-Evidenz-Pruefung (_FAILURE_RE) laeuft weiter auf dem
# Original-Inhalt, denn '# fail 3' ist echte Evidenz.
# Der spec-Reporter schreibt dieselben Zeilen mit 'ℹ' statt '#' (Issue #349).
_TAP_SUMMARY_RE = re.compile(
    r"(?m)^[#ℹ]\s*(tests|suites|pass|fail|cancelled|skipped|todo|duration_ms)\b.*$"
)

# --- Zitierter Fremdinhalt (Issue #262) ------------------------------------
# Eine Testausgabe besteht aus zwei Sorten Zeilen: dem RAHMEN, den der Runner
# selbst erzeugt, und ZITAT, das der Runner aus dem Pruefgegenstand uebernimmt
# (Dateiinhalt einer gescheiterten Assertion, Quellzeile, aufgefangenes
# stdout/stderr). Die Platzhalter-Suche darf nur den Rahmen sehen: Prueft ein
# RED-Test den Inhalt eines Framework-Dokuments, steht in dessen Zitat
# unvermeidlich das Wort "Placeholder" — skills/40-tdd-red/SKILL.md warnt genau
# davor. Das Gate blockte dadurch an seiner eigenen Warnung.
# Gleiches Vorgehen wie _TAP_SUMMARY_RE oben (Issue #73), nur allgemeiner.
#
# pytest markiert Zitat eindeutig pro Zeile:
#   'E   ...'  Assertion-Detail / longrepr — JEDE Zeile davon traegt das 'E'.
#   '>   ...'  die ausgefuehrte Quellzeile.
# Das Zeichen muss von Whitespace oder Zeilenende gefolgt sein, damit echte
# Woerter am Zeilenanfang ('Error: ...', 'ERROR') nicht als Zitat gelten.
_QUOTED_LINE_RE = re.compile(r"^\s*[E>](?:\s.*)?$")

# Kopf eines aufgefangenen Ausgabeblocks:
# '----------------------------- Captured stdout call -----------------------------'
# Auch 'Captured log call', 'Captured stderr setup', 'Captured stdout teardown'.
_CAPTURED_HEADER_RE = re.compile(
    r"^-{5,}\s*Captured \w+(?:\s+\w+)?\s*-{5,}\s*$"
)

# Beliebiger Runner-Abschnittskopf — beendet einen aufgefangenen Block.
# Mindestens zehn Fuellzeichen plus Titel, damit eine '---'-Zeile aus zitiertem
# Markdown (YAML-Frontmatter!) den Block NICHT vorzeitig beendet.
_SECTION_HEADER_RE = re.compile(r"^([=\-_])\1{9,}\s+\S")


def _iter_frame_lines(content: str):
    """Liefert (Zeilennummer, Zeile) fuer alle Zeilen, die der Runner SELBST
    erzeugt hat — Zitat-Bereiche werden uebersprungen (Issue #262).

    Die Zeilennummern beziehen sich auf das Original, damit eine Fundstelle in
    der Blockier-Meldung benannt werden kann.
    """
    in_captured = False
    for lineno, line in enumerate(content.splitlines(), start=1):
        if _CAPTURED_HEADER_RE.match(line):
            in_captured = True
            continue
        if in_captured:
            if _SECTION_HEADER_RE.match(line):
                in_captured = False
            else:
                continue
        if _QUOTED_LINE_RE.match(line):
            continue
        if _TAP_SUMMARY_RE.match(line):
            continue
        yield lineno, line


def _find_placeholder(content: str) -> "tuple[int, str] | None":
    """Sucht Platzhalter-Marker ausschliesslich im Runner-Rahmen.

    Gibt (Zeilennummer, Zeileninhalt) der ersten Fundstelle zurueck, sonst None.
    """
    for lineno, line in _iter_frame_lines(content):
        if _PLACEHOLDER_RE.search(line):
            return lineno, line.strip()
    return None


def _resolve_artifact_path(path_str: str, project_root: Path) -> Path:
    """Löst einen Artefakt-Pfad auf (Issue #1478 Teil 1).

    `project_root` (via `find_project_root()`) löst Git-Worktrees bewusst auf
    den Hauptrepo-Root auf -- richtig für geteilten Workflow-State unter
    `.claude/workflows/`. `docs/artifacts/` ist aber gitignored und wird
    zwischen Worktree und Hauptrepo NICHT geteilt: ein frisch geschriebenes
    RED-Test-Artefakt liegt physisch nur im Worktree. Ein relativer Pfad wird
    deshalb zuerst gegen den WORKTREE aufgelöst (falls die Session in einem
    läuft und die Datei dort existiert), sonst gegen `project_root`
    (Hauptrepo, unverändertes Rückwärtskompat-Verhalten).
    """
    if Path(path_str).is_absolute():
        return Path(path_str)
    worktree_root = hook_utils._find_worktree_root()
    if worktree_root is not None:
        worktree_candidate = worktree_root / path_str
        if worktree_candidate.exists():
            return worktree_candidate
    return project_root / path_str


def _validate_artifact(art: dict, project_root: Path) -> "str | None":
    """Prüft ein einzelnes Artefakt. Gibt Fehlermeldung zurück oder None."""
    art_type = art.get("type", "")
    path_str = art.get("path", "")
    description = art.get("description", "").strip()

    if len(description) < 10:
        return f"Beschreibung zu kurz ({len(description)} Zeichen): '{description}'"

    if not path_str:
        return None  # Kein Dateipfad → kann nicht weiter prüfen

    artifact_path = _resolve_artifact_path(path_str, project_root)

    if not artifact_path.exists():
        return f"Artefakt-Datei nicht gefunden: {path_str}"

    size = artifact_path.stat().st_size
    if size < _MIN_SIZE:
        return f"Artefakt-Datei zu klein ({size} Bytes < {_MIN_SIZE}): {path_str}"

    age_s = time.time() - artifact_path.stat().st_mtime
    if age_s > _MAX_AGE_S:
        return (
            f"Artefakt-Datei zu alt ({age_s / 3600:.1f}h > 24h): {path_str}\n"
            f"  → Neue RED-Tests ausführen und frische Artefakte registrieren."
        )

    # Inhalt nur für test_output prüfen (nicht für Screenshots)
    if art_type == "test_output":
        try:
            content = artifact_path.read_text(errors="replace")
        except OSError:
            return f"Artefakt-Datei nicht lesbar: {path_str}"

        hit = _find_placeholder(content)
        if hit is not None:
            lineno, text = hit
            snippet = text if len(text) <= 120 else text[:117] + "..."
            return (
                f"Artefakt enthält Platzhalter-Text: {path_str}\n"
                f"  → Zeile {lineno}: {snippet}\n"
                f"  → Echte Testausgabe eintragen, kein Copy-Paste-Beispiel.\n"
                f"  → Zitierte Bereiche (E-/>-Zeilen, Captured-Abschnitte) sind "
                f"ausgenommen — dieser Treffer steht im Artefakt selbst."
            )

        if not _FAILURE_RE.search(hook_utils.strip_ansi(content)):
            return (
                f"RED-Artefakt zeigt keine Fehler-Evidenz: {path_str}\n"
                f"  → Datei muss echte Fehlermeldungen enthalten (FAILED, ERROR, etc.).\n"
                f"  → Artefakt scheint zu zeigen, dass Tests bestanden — das ist kein RED."
            )

    return None


def main() -> None:
    # Ohne Workflow gibt es kein RED-Artefakt, das erzwungen werden koennte (#132).
    if framework_disabled():
        allow()

    try:
        tool_input = get_tool_input()
    except Exception:
        allow()

    file_path = tool_input.get("file_path", "")

    # Immer-Erlaubt-Pfade (Docs, Specs, .claude/) — gemeinsamer Helfer mit
    # post_implementation_gate, relativ zur Worktree-/Projektwurzel (#409).
    # Eigene Liste, NICHT identisch mit edit_gate.py.
    if is_hook_always_allowed(file_path):
        allow()

    # Workflow laden
    try:
        import workflow as _wf
        result = _wf.read_active_workflow_fast()
    except hook_utils.UnsafeStateError as exc:
        # #416: kein vertrauenswuerdiger State = keine Freigabe fuer Code-Edits
        block(f"BLOCKED [tdd_enforcement]: {exc}")
    except Exception:
        allow()

    if result is None:
        allow()

    wf_name, workflow = result
    current_phase = workflow.get("current_phase", "")

    if current_phase not in TEST_REQUIRED_PHASES:
        allow()

    project_root = find_project_root()

    red_artifacts = [
        a for a in workflow.get("test_artifacts", [])
        if a.get("phase") == "phase5_tdd_red"
    ]

    if not red_artifacts:
        # Kein Artefakt → erst hier blockieren wenn auch edit_gate's boolean-Flag fehlt
        # (edit_gate.py blockiert schon, aber zur Sicherheit auch hier)
        red_done = workflow.get("red_test_done", False) or workflow.get("ui_test_red_done", False)
        if not red_done:
            block(
                f"BLOCKED [tdd_enforcement]: Keine RED-Test-Artefakte für '{wf_name}'.\n"
                f"  Phase: {current_phase}\n"
                f"→ Zuerst /40-tdd-red ausführen und Artefakte registrieren:\n"
                f"  python3 .claude/hooks/workflow.py add-artifact test_output "
                f"'pfad/zum/output.txt' 'Tests fehlgeschlagen: ...' phase5_tdd_red"
            )
        allow()

    # Qualität der Artefakte prüfen
    errors = []
    for art in red_artifacts:
        err = _validate_artifact(art, project_root)
        if err:
            errors.append(f"  [{art.get('path', '?')}] {err}")

    if errors:
        block(
            f"BLOCKED [tdd_enforcement]: RED-Artefakte ungültig für '{wf_name}':\n"
            + "\n".join(errors)
            + "\n→ Echte fehlschlagende Tests ausführen und neue Artefakte registrieren."
            + "\n→ Falsch registriertes Artefakt entfernen: "
            "python3 .claude/hooks/workflow.py remove-artifact '<pfad>' phase5_tdd_red"
        )

    allow()


if __name__ == "__main__":
    main()
