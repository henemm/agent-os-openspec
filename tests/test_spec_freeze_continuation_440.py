"""TDD RED — Bugfix #440: Fortsetzungszeilen unter `- Test:` sind eingefroren.

Belegt AC-1 … AC-8 aus `docs/specs/fix-440-test-zeilen.md` (AC-9 liegt in
`tests/test_spec_freeze_partial_hash_439.py`).

Seit #439 sind im AC-Abschnitt die eingerueckten `- Test:`-Zeilen beweglich —
bisher samt tiefer eingerueckter Folgezeilen, ausser diese enthalten ein
AC-Label oder given/when/then (`_SPEC_AC_TEXT_RE`). Diese Woerterliste ist
umgehbar. Kuenftig ist nur die `- Test:`-Zeile selbst beweglich; jede
Folgezeile bleibt im Teil-Hash. Dazu: `edit_gate.py` darf bei Muell-Payload
nicht mit Traceback (Exit 1) abstuerzen.

Hash-Tests rufen `hook_utils.frozen_spec_sha256` direkt; Gate-Tests laufen als
Subprozess gegen das echte `core/hooks/edit_gate.py` in einer Sandbox (tmp_path,
Muster aus test_spec_freeze_partial_hash_439.py).

RED-Erwartung vor der Implementierung:
  * AC-1 … AC-4: Teil-Hash bleibt gleich bzw. Gate Exit 0 statt Exit 2
  * AC-7: Traceback / Exit 1 bei `file_path` als Zahl bzw. `tool_input` als String
  * AC-8: Edit an der Fortsetzung → Exit 0 statt Exit 2
Schon gruen (Regressionsschutz): AC-5, AC-6.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
EDIT_GATE = HOOKS_DIR / "edit_gate.py"

sys.path.insert(0, str(HOOKS_DIR))
import hook_utils  # noqa: E402

WF = "wf-440"
SPEC_REL = "docs/specs/demo-440.md"
BRIEFING_REL = f"docs/briefings/{WF}.md"
RUECKSPRUNG = "phase3_spec"

TEST_LINE = "  - Test: `tests/test_demo.py::test_zwei`"
CONT = "    Fortsetzung der Testzeile"

SPEC_HEAD = """---
entity_id: demo-440
status: draft
---

# Demo-Spec

## Approval

- [ ] Approved

## Purpose

Der Zweck ist klar umrissen.

## Scope

- **Affected Files:** `core/x.py`

## Definition of Done

- [ ] Jede AC ist belegt

## Acceptance Criteria

- **AC-1:** Given ein Nutzer / When er klickt / Then passiert etwas Sichtbares
  - Test: `tests/test_demo.py::test_alt`
- **AC-2:** Mit Unterpunkten
  - Given ein angemeldeter Nutzer
  - When er auf Senden klickt
  - Then erscheint eine Bestaetigung
"""

SPEC_TAIL = """
## Test Plan

- `pytest tests/test_demo.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reine Ergaenzung ohne Architektur-Relevanz, nur zum Testen.

## Changelog

- 2026-10-14: Initial
"""

# Spec MIT Fortsetzungszeile unter `- Test:`
SPEC = SPEC_HEAD + TEST_LINE + "\n" + CONT + "\n" + SPEC_TAIL
# Spec OHNE Fortsetzungszeile (AC-6: Hash muss byte-identisch zum Vorstand sein)
SPEC_NO_CONT = SPEC_HEAD + TEST_LINE + "\n" + SPEC_TAIL

# Teil-Hash von SPEC_NO_CONT, erzeugt mit dem unveraenderten Stand vor #440
# (Commit fb57d33, `hook_utils.frozen_spec_sha256`).
SPEC_NO_CONT_FROZEN_SHA = "ec8459097efb4971f7245504a263de713dc8f30950fb6181117fd853ad7f752c"

BRIEFING = (
    "# PO-Briefing: wf-440\n\n"
    "## Was gebaut wird\n\n"
    "Nutzer koennen kuenftig mit einem Klick etwas ausloesen, das heute fehlt.\n\n"
    "## Definition of Done\n\n"
    "Fertig ist es, wenn der Klick sichtbar etwas ausloest und das automatisch geprueft wird.\n\n"
    "## Wie geprüft wird\n\n"
    "Ein automatischer Test klickt stellvertretend und prueft das sichtbare Ergebnis.\n\n"
    "## Kritische Anmerkungen\n\n"
    "- Die Spec laesst offen, was bei zweimaligem Klicken passiert.\n"
)


# --- Helfer -----------------------------------------------------------------

def _frozen(content: str) -> str:
    return hook_utils.frozen_spec_sha256(content)


def _with_extra_cont(extra: str) -> str:
    """SPEC mit einer zusaetzlichen Fortsetzungszeile unter der Test-Zeile."""
    out = SPEC.replace(CONT + "\n", CONT + "\n" + extra + "\n", 1)
    assert out != SPEC
    return out


_SCRUBBED = {"CLAUDE_TOOL_INPUT", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT",
             "PYTHONPATH"}


def _env(proj: Path, home: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in _SCRUBBED and not k.startswith("OPENSPEC_")
           and not k.startswith("GIT_")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = WF
    env["HOME"] = str(home)
    return env


def _approved_project(tmp_path: Path, spec: str = SPEC):
    """Freigegebene Spec (phase5_tdd_red) mit Teil-Hash-Briefing in tmp_path."""
    proj = tmp_path / "project"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows").mkdir(parents=True)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    spec_path = proj / SPEC_REL
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(spec)
    bpath = proj / BRIEFING_REL
    bpath.parent.mkdir(parents=True, exist_ok=True)
    bpath.write_text(BRIEFING)
    data = {
        "name": WF, "workflow_type": "bugfix", "current_phase": "phase5_tdd_red",
        "context_file": "docs/context.md", "spec_file": SPEC_REL,
        "spec_approved": True, "affected_files": [], "red_test_done": True,
        "phase_transitions": [], "phase_log": [],
        "po_briefing": {
            "file": BRIEFING_REL,
            "spec_sha256": hashlib.sha256(spec.encode("utf-8")).hexdigest(),
            "spec_frozen_sha256": _frozen(spec),
            "created": "2026-10-14T10:00:00",
        },
    }
    (proj / ".claude" / "workflows" / f"{WF}.json").write_text(json.dumps(data, indent=2))
    return proj, home, spec_path


def _run_gate_raw(proj: Path, home: Path, raw: str):
    return subprocess.run(
        [sys.executable, str(EDIT_GATE)], input=raw, capture_output=True,
        text=True, env=_env(proj, home), cwd=str(proj), timeout=60,
    )


def _edit(proj, home, spec_path, old, new):
    text = spec_path.read_text()
    assert text.count(old) == 1, f"Fixture-Fehler: {old!r} kommt {text.count(old)}x vor"
    payload = {"tool_name": "Edit",
               "tool_input": {"file_path": str(spec_path),
                              "old_string": old, "new_string": new}}
    return _run_gate_raw(proj, home, json.dumps(payload))


def _assert_block(result, what: str) -> None:
    assert result.returncode == 2, (
        f"{what}: Aenderung an einer Fortsetzungszeile muss blocken, aber "
        f"returncode={result.returncode}. stderr={result.stderr!r}"
    )
    assert RUECKSPRUNG in result.stderr, (
        f"{what}: Blockmeldung muss den Ruecksprung nach {RUECKSPRUNG} nennen. "
        f"stderr={result.stderr!r}"
    )


def _assert_allowed(result, what: str) -> None:
    assert result.returncode == 0, (
        f"{what}: Aenderung nur der `- Test:`-Zeile muss erlaubt sein, aber "
        f"returncode={result.returncode}. stderr={result.stderr!r}"
    )


# --- AC-1: Fliesstext-Fortsetzung -------------------------------------------

def test_fliesstext_fortsetzung_aendert_hash_und_blockt(tmp_path):
    """AC-1 — GIVEN freigegebene Spec mit `- Test:`-Zeile und Fortsetzung
    WHEN die Fortsetzung durch Fliesstext mit neuer Anforderung ergaenzt oder
    geaendert wird THEN aendert sich der Teil-Hash und das Gate endet mit Exit 2."""
    base = _frozen(SPEC)
    added = _with_extra_cont("    Das System muss zusaetzlich Y tun.")
    changed = SPEC.replace(CONT, "    Das System muss zusaetzlich Y tun.")
    assert _frozen(added) != base, "AC-1: ergaenzter Fliesstext laesst Teil-Hash gleich"
    assert _frozen(changed) != base, "AC-1: geaenderte Fortsetzung laesst Teil-Hash gleich"

    proj, home, spec_path = _approved_project(tmp_path)
    r = _edit(proj, home, spec_path, CONT,
              CONT + "\n    Das System muss zusaetzlich Y tun.")
    _assert_block(r, "AC-1 Fliesstext ergaenzt")
    r2 = _edit(proj, home, spec_path, CONT, "    Das System muss zusaetzlich Y tun.")
    _assert_block(r2, "AC-1 Fortsetzung geaendert")


# --- AC-2: "A C-31" -----------------------------------------------------------

def test_label_mit_leerzeichen_aendert_hash():
    """AC-2 — WHEN eine Fortsetzung mit „A C-31“ hinzukommt THEN neuer Teil-Hash."""
    extra = "    **A C-31:** Das System loescht alle Daten"
    assert _frozen(_with_extra_cont(extra)) != _frozen(SPEC), (
        "AC-2: Fortsetzung mit 'A C-31' laesst den Teil-Hash gleich")


# --- AC-3: kyrillisches А -----------------------------------------------------

def test_kyrillisches_a_aendert_hash():
    """AC-3 — WHEN eine Fortsetzung mit kyrillischem „А“ (U+0410) im Label
    hinzukommt THEN neuer Teil-Hash."""
    extra = "    **АC-31:** Das System loescht alle Daten"
    assert "А" in extra
    assert _frozen(_with_extra_cont(extra)) != _frozen(SPEC), (
        "AC-3: Fortsetzung mit kyrillischem A laesst den Teil-Hash gleich")


# --- AC-4: Soft-Hyphen / Zero-Width-Space ------------------------------------

@pytest.mark.parametrize("extra", [
    "    **A­C-31:** Das System loescht alle Daten",   # Soft-Hyphen im Label
    "    the­n loescht das System alle Daten",          # Soft-Hyphen in then
    "    **A​C-31:** Das System loescht alle Daten",   # ZWSP im Label
    "    whe​n der Nutzer klickt, loescht das System",  # ZWSP in when
])
def test_soft_hyphen_und_zero_width_space_aendern_hash(extra):
    """AC-4 — WHEN eine Fortsetzung mit Soft-Hyphen (U+00AD) oder ZWSP (U+200B)
    mitten im Schluesselwort hinzukommt THEN neuer Teil-Hash."""
    assert _frozen(_with_extra_cont(extra)) != _frozen(SPEC), (
        f"AC-4: Fortsetzung {extra!r} laesst den Teil-Hash gleich")


# --- AC-5: nur die Test-Zeile aendern ----------------------------------------

def test_aenderung_nur_der_test_zeile_laesst_hash_gleich():
    """AC-5 — GIVEN `- Test:`-Zeile mit tiefer eingerueckten Folgezeilen
    WHEN nur die `- Test:`-Zeile geaendert wird THEN bleibt der Teil-Hash gleich."""
    spec = _with_extra_cont("    zweite Folgezeile")
    changed = spec.replace(TEST_LINE, "  - Test: `tests/test_demo.py::test_zwei_neu`")
    assert changed != spec
    assert _frozen(changed) == _frozen(spec)


# --- AC-6: Hash ohne Fortsetzung byte-identisch -------------------------------

def test_spec_ohne_fortsetzung_hash_identisch_zum_vorstand():
    """AC-6 — GIVEN Fixture-Spec ohne Fortsetzungszeilen unter `- Test:`
    WHEN `frozen_spec_sha256` sie hasht THEN entspricht das Ergebnis dem
    festen Literal aus dem Stand vor #440."""
    assert _frozen(SPEC_NO_CONT) == SPEC_NO_CONT_FROZEN_SHA


# --- AC-7: Muell-Payload ------------------------------------------------------

@pytest.mark.parametrize("label,raw", [
    ("file_path Zahl", {"tool_name": "Edit", "tool_input": {"file_path": 42}}),
    ("file_path Liste", {"tool_name": "Edit",
                         "tool_input": {"file_path": ["docs/specs/demo-440.md"]}}),
    ("file_path null", {"tool_name": "Edit", "tool_input": {"file_path": None}}),
    ("tool_input String", {"tool_name": "Edit", "tool_input": "kein-objekt"}),
])
def test_muell_payload_endet_mit_exit_0_ohne_traceback(tmp_path, label, raw):
    """AC-7 — GIVEN Payload mit `file_path` als Zahl/Liste/null bzw.
    `tool_input` als String WHEN edit_gate.py als Subprozess laeuft
    THEN Exit 0 und kein Traceback auf stderr."""
    proj, home, _ = _approved_project(tmp_path)
    r = _run_gate_raw(proj, home, json.dumps(raw))
    assert "Traceback" not in r.stderr, f"AC-7 {label}: Traceback. stderr={r.stderr!r}"
    assert r.returncode == 0, f"AC-7 {label}: rc={r.returncode} stderr={r.stderr!r}"


# --- AC-8: Ende-zu-Ende -------------------------------------------------------

def test_edit_gate_ende_zu_ende_fortsetzung_blockt(tmp_path):
    """AC-8 — GIVEN freigegebener Workflow mit Spec und Fortsetzung unter
    `- Test:` WHEN das echte edit_gate.py einen Edit an der Fortsetzung sieht
    THEN Exit 2 mit Ruecksprung-Meldung; derselbe Edit nur an der Test-Zeile
    THEN Exit 0."""
    proj, home, spec_path = _approved_project(tmp_path)
    r = _edit(proj, home, spec_path, CONT, "    Andere Fortsetzung")
    _assert_block(r, "AC-8 Fortsetzung geaendert")

    ok = _edit(proj, home, spec_path, TEST_LINE,
               "  - Test: `tests/test_demo.py::test_zwei_neu`")
    _assert_allowed(ok, "AC-8 nur Test-Zeile")
