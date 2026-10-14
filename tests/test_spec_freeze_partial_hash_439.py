"""TDD RED — Feature #439: Spec-Freeze nur fuer den freigegebenen Teil (Teil-Hash).

Belegt AC-1 … AC-29 aus `docs/specs/feat-439-spec-freeze-teilhash.md`
(AC-6 liegt in `tests/test_edit_gate_spec_freeze_230.py`, AC-23 in
`tests/test_po_briefing_gate.py`, AC-24/AC-25 in `tests/test_ci_spec_gate.py`).

Bisher (#230) ist die freigegebene Spec als Ganzes eingefroren; der einzige
Ausweg ist ein Override-Token. Kuenftig sind nur bewegliche Teile (Frontmatter,
Known Limitations, Implementation Details, Changelog, Test Plan, Approval und
die `- Test:`-Zeilen im AC-Abschnitt) ohne Token aenderbar; alles andere bleibt
eingefroren — auch mit Override-Token.

Muster: echte Hooks (`edit_gate.py`, `edit_verify.py`, `workflow.py`) als
Subprozess gegen ein hermetisches Fake-Projekt in tmp_path (Vorbild:
test_edit_gate_spec_freeze_230.py, test_adversary_evidence_gate_253.py).
Unit-Tests rufen `workflow.frozen_spec_sha256` direkt auf — per getattr, damit
die Datei auch vor der Implementierung sammelbar bleibt.

RED-Erwartung vor der Implementierung:
  * Erlaubt-Faelle (AC-1, AC-3, AC-8a, AC-14, AC-18a, AC-20, AC-22a) → Exit 2 statt 0
  * Block-Faelle → Exit 2, aber ohne Ruecksprung-Hinweis `phase3_spec`
    (bzw. ohne `präzisieren` / `set-briefing`)
  * Unit-Tests → `frozen_spec_sha256` fehlt
  * Spur (AC-27) → `spec_post_approval_edits` fehlt
Schon gruen (Regressionsschutz): AC-26, AC-28, AC-29.
"""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
EDIT_GATE = HOOKS_DIR / "edit_gate.py"
EDIT_VERIFY = HOOKS_DIR / "edit_verify.py"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
CI_SCRIPT = REPO_ROOT / "scripts" / "ci_spec_gate.py"

sys.path.insert(0, str(HOOKS_DIR))
import workflow as _wf  # noqa: E402

WF = "wf-439"
SPEC_REL = "docs/specs/demo-439.md"
BRIEFING_REL = f"docs/briefings/{WF}.md"

RUECKSPRUNG = "phase3_spec"
PRAEZISIEREN = "präzisieren"

SPEC = """---
entity_id: demo-439
status: draft
---

# Demo-Spec

## Approval

- [ ] Approved

## Purpose

Der Zweck ist klar umrissen.

## Scope

- **Affected Files:** `core/x.py`
- Umfang bleibt klein.

## Implementation Details

Details zur Umsetzung.

## Known Limitations

- Eine bekannte Grenze.
- Doppelt vorhanden.

## Definition of Done

- [ ] Jede AC ist belegt

## Acceptance Criteria

- **AC-1:** Given ein Nutzer / When er klickt / Then passiert etwas Sichtbares
  - Test: `tests/test_demo.py::test_alt`
- **AC-2:** Mit Unterpunkten
  - Given ein angemeldeter Nutzer
  - When er auf Senden klickt
  - Then erscheint eine Bestaetigung
  - Test: `tests/test_demo.py::test_zwei`
    Fortsetzung der Testzeile

## Test Plan

- `pytest tests/test_demo.py`
- Doppelt vorhanden.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Reine Ergaenzung ohne Architektur-Relevanz, nur zum Testen.

## Changelog

- 2026-10-13: Initial
"""

# Variante: ADR ist der letzte Abschnitt der Datei (kein Changelog dahinter).
SPEC_ADR_END = SPEC.split("## Changelog")[0].rstrip() + "\n"

BRIEFING = (
    "# PO-Briefing: wf-439\n\n"
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

def _frozen_fn():
    """`workflow.frozen_spec_sha256` — fehlt vor der Implementierung (RED-Grund)."""
    fn = getattr(_wf, "frozen_spec_sha256", None)
    assert fn is not None, (
        "workflow.frozen_spec_sha256 fehlt — der Teil-Hash ist noch nicht implementiert (#439)."
    )
    return fn


def _frozen_or_dummy(content: str) -> str:
    """Teil-Hash, falls schon implementiert, sonst ein Platzhalter-Hex-Wert.

    Fixtures, die nur ein NICHT-Legacy-Briefing brauchen (Feld vorhanden),
    sollen vor der Implementierung am Gate-Verhalten scheitern, nicht hier.
    """
    fn = getattr(_wf, "frozen_spec_sha256", None)
    return fn(content) if fn is not None else "f" * 64


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


_SCRUBBED = {"CLAUDE_TOOL_INPUT", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT",
             "PYTHONPATH"}


def _base_env() -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in _SCRUBBED and not k.startswith("OPENSPEC_")
           and not k.startswith("GIT_")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _env(proj: Path, home: Path, name: str = WF) -> dict:
    env = _base_env()
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = name
    env["HOME"] = str(home)
    return env


def _make_project(tmp_path: Path, spec: str = SPEC) -> "tuple[Path, Path, Path]":
    proj = tmp_path / "project"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows").mkdir(parents=True)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    spec_path = proj / SPEC_REL
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(spec)
    return proj, home, spec_path


def _briefing_entry(spec: str = SPEC, *, frozen: bool = True) -> dict:
    entry = {"file": BRIEFING_REL, "spec_sha256": _sha(spec),
             "created": "2026-10-13T10:00:00"}
    if frozen:
        entry["spec_frozen_sha256"] = _frozen_or_dummy(spec)
    return entry


def _write_workflow(proj: Path, *, phase: str = "phase5_tdd_red",
                    po_briefing: "dict | None" = None,
                    workflow_type: str = "feature", **extra) -> Path:
    data = {
        "name": WF,
        "workflow_type": workflow_type,
        "current_phase": phase,
        "context_file": "docs/context.md",
        "spec_file": SPEC_REL,
        "spec_approved": True,
        "affected_files": [],
        "red_test_done": True,
        "phase_transitions": [],
        "phase_log": [],
    }
    if po_briefing is not None:
        data["po_briefing"] = po_briefing
        bpath = proj / po_briefing["file"]
        bpath.parent.mkdir(parents=True, exist_ok=True)
        bpath.write_text(BRIEFING)
    data.update(extra)
    path = proj / ".claude" / "workflows" / f"{WF}.json"
    path.write_text(json.dumps(data, indent=2))
    return path


def _approved_project(tmp_path: Path, spec: str = SPEC, **wf_kwargs):
    """Freigegebene Spec (phase5_tdd_red) mit Teil-Hash-Briefing."""
    proj, home, spec_path = _make_project(tmp_path, spec)
    wf_kwargs.setdefault("po_briefing", _briefing_entry(spec))
    _write_workflow(proj, **wf_kwargs)
    return proj, home, spec_path


def _write_token(proj: Path, key: str) -> None:
    (proj / ".claude" / "user_override_token.json").write_text(json.dumps({
        "version": 2,
        "tokens": {key: {"created": datetime.now().isoformat(),
                         "granted_by": "user_prompt"}},
    }))


def _run_gate(proj: Path, home: Path, tool_name: str, tool_input: dict):
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, str(EDIT_GATE)], input=payload, capture_output=True,
        text=True, env=_env(proj, home), cwd=str(proj), timeout=60,
    )


def _edit(proj, home, spec_path, old, new, *, replace_all=False, expect_count=1):
    text = spec_path.read_text()
    assert text.count(old) == expect_count, (
        f"Fixture-Fehler: old_string kommt {text.count(old)}x vor, erwartet "
        f"{expect_count}x: {old!r}"
    )
    tool_input = {"file_path": str(spec_path), "old_string": old, "new_string": new}
    if replace_all:
        tool_input["replace_all"] = True
    return _run_gate(proj, home, "Edit", tool_input)


def _write(proj, home, spec_path, content):
    return _run_gate(proj, home, "Write",
                     {"file_path": str(spec_path), "content": content})


def _assert_allowed(result, what: str) -> None:
    assert result.returncode == 0, (
        f"{what}: Aenderung an beweglichem Teil muss ohne Token erlaubt sein, "
        f"aber returncode={result.returncode}. stderr={result.stderr!r}"
    )


def _assert_rueckspung_block(result, what: str) -> None:
    assert result.returncode == 2, (
        f"{what}: Aenderung am Freigegebenen muss blocken, aber "
        f"returncode={result.returncode}. stderr={result.stderr!r}"
    )
    assert RUECKSPRUNG in result.stderr, (
        f"{what}: Blockmeldung muss den Ruecksprung nach {RUECKSPRUNG} nennen. "
        f"stderr={result.stderr!r}"
    )


def _run_verify(proj: Path, home: Path, payload) -> subprocess.CompletedProcess:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(EDIT_VERIFY)], input=raw, capture_output=True,
        text=True, env=_env(proj, home), cwd=str(proj), timeout=60,
    )


def _state(proj: Path) -> dict:
    return json.loads((proj / ".claude" / "workflows" / f"{WF}.json").read_text())


def _run_workflow(proj: Path, home: Path, args: list):
    return subprocess.run(
        [sys.executable, str(WORKFLOW_PY), *args], capture_output=True, text=True,
        env=_env(proj, home), cwd=str(proj), timeout=60,
    )


# --- AC-1: `- Test:`-Zeile aendern ist erlaubt -------------------------------

def test_test_zeile_aendern_erlaubt(tmp_path):
    """AC-1 — GIVEN freigegebene Spec (phase5) mit Teil-Hash-Briefing, kein Token
    WHEN eine `- Test:`-Zeile unter einer AC per Edit geaendert wird
    THEN laesst das Edit-Gate den Edit durch (Exit 0)."""
    proj, home, spec_path = _approved_project(tmp_path)
    r = _edit(proj, home, spec_path,
              "  - Test: `tests/test_demo.py::test_alt`",
              "  - Test: `tests/test_demo.py::test_neu`")
    _assert_allowed(r, "AC-1 Test-Zeile")


# --- AC-2: Briefing bleibt gueltig, phase8_complete klappt -------------------

AC2_WF = WF
AC2_ART = f"docs/artifacts/{AC2_WF}/adversary-dialog.md"
AC2_EXAMINED = "src/checked_module.py"


def _git(args: list, cwd: Path) -> None:
    res = subprocess.run(
        ["git", "-c", "user.email=t@t.invalid", "-c", "user.name=Test",
         "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
        cwd=str(cwd), capture_output=True, text=True, env=_base_env(),
    )
    assert res.returncode == 0, f"git {args} failed: {res.stderr}"


def _dialog_text() -> str:
    return (
        f"# Adversary Dialog — {AC2_WF}\nSpec: {SPEC_REL}\n\n"
        "## Checkliste\n"
        "- [x] AC-1: Test-Zeile beweglich — Beweis: Testlauf\n"
        f"  Code reference: {AC2_EXAMINED}:1\n"
        "- [x] AC-2: Unterpunkte eingefroren — Beweis: Testlauf\n"
        f"  Code reference: {AC2_EXAMINED}:1\n\n"
        "## Dialog\n\n"
        "### Runde 1\n**Adversary:** Angriff 1\n**Implementierer:** Beweis 1\n\n"
        "### Runde 2\n**Adversary:** Angriff 2\n**Implementierer:** Beweis 2\n\n"
        "VERDICT: VERIFIED\n"
    )


def test_briefing_bleibt_gueltig_und_phase8_klappt(tmp_path):
    """AC-2 — GIVEN freigegebene Spec, Briefing per echtem `set-briefing` gestempelt,
    gueltiger VERIFIED-Adversary-Nachweis
    WHEN danach die `- Test:`-Zeile geaendert wird und `phase phase8_complete` laeuft
    THEN gilt das Briefing als aktuell und der Uebergang klappt (Exit 0)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    _git(["init", "-q"], proj)
    (proj / ".claude" / "workflows").mkdir(parents=True)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    spec_path = proj / SPEC_REL
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(SPEC)
    (proj / BRIEFING_REL).parent.mkdir(parents=True)
    (proj / BRIEFING_REL).write_text(BRIEFING)

    # Briefing ueber die echte CLI stempeln (Phase 3, vor der Freigabe).
    _write_workflow(proj, phase="phase3_spec", spec_approved=False)
    r = _run_workflow(proj, home, ["set-briefing", BRIEFING_REL])
    assert r.returncode == 0, f"Fixture: set-briefing scheitert: {r.stderr!r}"

    # Freigabe + Adversary-Nachweis wie in test_adversary_evidence_gate_253.
    data = _state(proj)
    data.update({
        "current_phase": "phase6b_adversary", "spec_approved": True,
        "test_artifacts": [{
            "type": "test_output", "path": f"docs/artifacts/{AC2_WF}/test-red-output.txt",
            "description": "red", "phase": "phase5_tdd_red",
            "created": "2026-10-13T09:00:00",
        }],
    })
    (proj / ".claude" / "workflows" / f"{WF}.json").write_text(json.dumps(data, indent=2))
    examined = proj / AC2_EXAMINED
    examined.parent.mkdir(parents=True)
    examined.write_text("VALUE = 1\n")
    art = proj / AC2_ART
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(_dialog_text())
    env = _env(proj, home)
    s = subprocess.run([sys.executable, str(HOOKS_DIR / "adversary_dialog.py"), "stamp",
                        str(art)], capture_output=True, text=True, cwd=str(proj), env=env)
    assert s.returncode == 0, f"Fixture: stamp scheitert: {s.stdout}{s.stderr}"
    a = _run_workflow(proj, home, ["add-artifact", "adversary_dialog", AC2_ART,
                                   "dialog", "phase6b_adversary"])
    assert a.returncode == 0, f"Fixture: add-artifact scheitert: {a.stderr!r}"
    green = proj / "docs" / "artifacts" / AC2_WF / "test-green-output.txt"
    green.write_text(
        "============================= test session starts ==============================\n"
        "collected 5 items\n\ntests/test_gate.py .....\n\n"
        "============================== 5 passed in 0.12s ===============================\n"
    )
    q = subprocess.run([sys.executable, str(HOOKS_DIR / "qa_gate.py"), str(green),
                        "--checklist", str(art)], capture_output=True, text=True,
                       cwd=str(proj), env=env)
    assert q.returncode == 0, f"Fixture: qa_gate scheitert: {q.stdout}{q.stderr}"
    p7 = _run_workflow(proj, home, ["phase", "phase7_validate"])
    assert p7.returncode == 0, f"Fixture: phase7 scheitert: {p7.stderr!r}"

    # Nachtraegliche Aenderung an einer `- Test:`-Zeile (beweglicher Teil).
    spec_path.write_text(SPEC.replace("test_demo.py::test_alt", "test_demo.py::test_neu"))

    p8 = _run_workflow(proj, home, ["phase", "phase8_complete"])
    assert "Dialog-Nachweis" not in p8.stderr, (
        f"Fixture-Fehler: Adversary-Nachweis ungueltig: {p8.stderr!r}"
    )
    assert p8.returncode == 0, (
        "Nach einer Aenderung nur an einer `- Test:`-Zeile muss das Briefing "
        f"aktuell bleiben und phase8_complete klappen. stderr={p8.stderr!r}"
    )
    assert _state(proj)["current_phase"] == "phase8_complete"


# --- AC-3: bewegliche Abschnitte ohne Token erlaubt --------------------------

@pytest.mark.parametrize("old,new", [
    ("- Eine bekannte Grenze.", "- Eine geaenderte Grenze."),
    ("- `pytest tests/test_demo.py`", "- `pytest tests/test_demo.py -v`"),
    ("- 2026-10-13: Initial", "- 2026-10-13: Initial\n- 2026-10-14: Testname korrigiert"),
    ("Details zur Umsetzung.", "Details zur Umsetzung, ergaenzt."),
    ("- [ ] Approved", "- [x] Approved"),
    ("status: draft", "status: approved"),
], ids=["known-limitations", "test-plan", "changelog", "implementation-details",
        "approval", "frontmatter"])
def test_bewegliche_abschnitte_erlaubt(tmp_path, old, new):
    """AC-3 — GIVEN freigegebene Spec mit Teil-Hash-Briefing, kein Token
    WHEN Known Limitations, Test Plan, Changelog, Implementation Details,
    Approval bzw. Frontmatter geaendert werden
    THEN sind diese Edits erlaubt (Exit 0)."""
    proj, home, spec_path = _approved_project(tmp_path)
    r = _edit(proj, home, spec_path, old, new)
    _assert_allowed(r, f"AC-3 {old!r}")


# --- AC-4: eingefrorene Abschnitte blocken -----------------------------------

FROZEN_EDITS = [
    ("Der Zweck ist klar umrissen.", "Der Zweck ist ganz anders."),
    ("- Umfang bleibt klein.", "- Umfang waechst."),
    ("- [ ] Jede AC ist belegt", "- [ ] Einige AC sind belegt"),
    ("Then passiert etwas Sichtbares", "Then passiert nichts"),
    ("Reine Ergaenzung ohne Architektur-Relevanz", "Neue Architektur"),
    ("# Demo-Spec\n", "# Andere Spec\n"),
]
FROZEN_IDS = ["purpose", "scope", "dod", "ac-text", "adr", "titel"]


@pytest.mark.parametrize("old,new", FROZEN_EDITS, ids=FROZEN_IDS)
def test_eingefrorene_abschnitte_blocken(tmp_path, old, new):
    """AC-4 — GIVEN freigegebene Spec, kein Token
    WHEN Purpose, Scope, Definition of Done, AC-Text, ADR oder Titel geaendert wird
    THEN blockt das Gate mit Exit 2 und dem Ruecksprung-Hinweis auf phase3_spec."""
    proj, home, spec_path = _approved_project(tmp_path)
    r = _edit(proj, home, spec_path, old, new)
    _assert_rueckspung_block(r, f"AC-4 {old!r}")


# --- AC-5: Override oeffnet den Spec-Freeze nicht ----------------------------

@pytest.mark.parametrize("token_key", [WF, "__infra__", "fremder-workflow"],
                         ids=["workflow-token", "infra-token", "globales-token"])
def test_override_oeffnet_spec_freeze_nicht(tmp_path, token_key):
    """AC-5 — GIVEN eine Aenderung am Purpose und ein gueltiger Override-Token
    (Workflow-, __infra__- oder fremder = globaler Token)
    WHEN das Gate laeuft
    THEN blockt es weiterhin mit Ruecksprung-Hinweis."""
    proj, home, spec_path = _approved_project(tmp_path)
    _write_token(proj, token_key)
    r = _edit(proj, home, spec_path, "Der Zweck ist klar umrissen.",
              "Der Zweck ist ganz anders.")
    _assert_rueckspung_block(r, f"AC-5 Token {token_key}")


# --- AC-7: eingerueckte Given/When/Then-Zeilen eingefroren -------------------

def test_eingerueckte_given_when_then_eingefroren(tmp_path):
    """AC-7 — GIVEN ein AC mit eingerueckten Given/When/Then-Sub-Bullets
    WHEN einer dieser Sub-Bullets geaendert wird
    THEN blockt das Gate (nur `- Test:`-Zeilen sind beweglich)."""
    proj, home, spec_path = _approved_project(tmp_path)
    r = _edit(proj, home, spec_path, "  - When er auf Senden klickt",
              "  - When er auf Abbrechen klickt")
    _assert_rueckspung_block(r, "AC-7 When-Zeile")


# --- AC-8: Fortsetzung beweglich, neuer Bullet nicht -------------------------

def test_test_zeile_fortsetzung_beweglich_neuer_bullet_nicht(tmp_path):
    """AC-8 — GIVEN eine `- Test:`-Zeile mit Fortsetzungszeile
    WHEN Zeile und Fortsetzung geaendert werden THEN erlaubt;
    WHEN dagegen ein neuer Bullet ohne `- Test:` eingefuegt wird THEN Block."""
    proj, home, spec_path = _approved_project(tmp_path)
    r = _edit(proj, home, spec_path,
              "  - Test: `tests/test_demo.py::test_zwei`\n    Fortsetzung der Testzeile",
              "  - Test: `tests/test_demo.py::test_zwei_neu`\n    Andere Fortsetzung")
    _assert_allowed(r, "AC-8 Test-Zeile + Fortsetzung")

    r2 = _edit(proj, home, spec_path,
               "  - Test: `tests/test_demo.py::test_alt`\n",
               "  - Test: `tests/test_demo.py::test_alt`\n  - Neue Bedingung\n")
    _assert_rueckspung_block(r2, "AC-8 neuer Bullet")


# --- AC-9: Verschieben in beweglichen Abschnitt ------------------------------

def test_verschieben_in_beweglichen_abschnitt_blockt(tmp_path):
    """AC-9 — GIVEN freigegebene Spec
    WHEN eine Scope-Zeile per Write in Known Limitations verschoben wird
    THEN aendert sich der Teil-Hash und das Gate blockt."""
    proj, home, spec_path = _approved_project(tmp_path)
    moved = SPEC.replace("- Umfang bleibt klein.\n", "").replace(
        "- Eine bekannte Grenze.\n", "- Eine bekannte Grenze.\n- Umfang bleibt klein.\n")
    assert moved != SPEC and moved.count("Umfang bleibt klein") == 1
    r = _write(proj, home, spec_path, moved)
    _assert_rueckspung_block(r, "AC-9 Verschieben")


# --- AC-10: Zerteilen durch bewegliche Ueberschrift --------------------------

def test_zerteilen_durch_bewegliche_ueberschrift_blockt(tmp_path):
    """AC-10 — GIVEN freigegebene Spec
    WHEN `## Changelog` mitten in den Scope eingefuegt wird
    THEN blockt das Gate."""
    proj, home, spec_path = _approved_project(tmp_path)
    r = _edit(proj, home, spec_path, "- Umfang bleibt klein.",
              "## Changelog\n\n- Umfang bleibt klein.")
    _assert_rueckspung_block(r, "AC-10 Zerteilen")


# --- AC-11: Ueberschriften-Einrueckung und Tab (Unit) ------------------------

def test_ueberschrift_einrueckung_und_tab():
    """AC-11 — GIVEN Ueberschriften mit 0–3 Leerzeichen Einrueckung oder Tab nach ##
    WHEN die Spec zerlegt wird
    THEN sind sie H2 (beweglich bzw. eingefroren korrekt); 4 Leerzeichen sind keine."""
    frozen = _frozen_fn()
    for heading in ("   ## Known Limitations", "##\tKnown Limitations",
                    " ## Known Limitations"):
        base = f"# T\n\n## Scope\n\nA\n\n{heading}\n\nB\n"
        assert frozen(base) == frozen(base.replace("\nB\n", "\nB geaendert\n")), (
            f"{heading!r} muss als bewegliche H2 erkannt werden"
        )
    # Eingeruecktes '   ## Scope' beendet den beweglichen Abschnitt davor.
    base = "# T\n\n## Known Limitations\n\nB\n\n   ## Scope\n\nC\n"
    assert frozen(base) != frozen(base.replace("\nC\n", "\nC geaendert\n")), (
        "'   ## Scope' muss als eingefrorene H2 erkannt werden"
    )
    # Vier Leerzeichen: keine Ueberschrift → B gehoert zum eingefrorenen Scope.
    base = "# T\n\n## Scope\n\nA\n\n    ## Known Limitations\n\nB\n"
    assert frozen(base) != frozen(base.replace("\nB\n", "\nB geaendert\n")), (
        "'    ## Known Limitations' (4 Leerzeichen) darf keine Ueberschrift sein"
    )


# --- AC-12: '##' in Code-Fence ist keine Ueberschrift (Unit) ------------------

@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_code_fence_ueberschrift_ist_keine_ueberschrift(fence):
    """AC-12 — GIVEN ein `##` innerhalb eines Code-Blocks mit ``` bzw. ~~~
    WHEN die Spec zerlegt wird
    THEN ist es keine Ueberschrift."""
    frozen = _frozen_fn()
    # Fence im beweglichen Abschnitt: '## Scope' darin macht x NICHT eingefroren.
    base = f"# T\n\n## Purpose\n\nP\n\n## Known Limitations\n\n{fence}\n## Scope\nx\n{fence}\n"
    assert frozen(base) == frozen(base.replace("\nx\n", "\ny\n"))
    # Fence im eingefrorenen Abschnitt: '## Changelog' darin macht z NICHT beweglich.
    base = f"# T\n\n## Scope\n\n{fence}\n## Changelog\n{fence}\nz\n"
    assert frozen(base) != frozen(base.replace("\nz\n", "\nw\n"))


# --- AC-13: offene Fence blockt -----------------------------------------------

def test_offene_fence_blockt(tmp_path):
    """AC-13 — GIVEN freigegebene Spec
    WHEN eine nicht geschlossene Code-Fence in Known Limitations eingefuegt
    bzw. eine bestehende offene Fence entfernt wird
    THEN gilt der Rest als Fence-Inhalt, der Teil-Hash aendert sich, das Gate blockt."""
    frozen = _frozen_fn()
    opened = SPEC.replace("- Eine bekannte Grenze.", "- Eine bekannte Grenze.\n```")
    assert frozen(SPEC) != frozen(opened)

    proj, home, spec_path = _approved_project(tmp_path)
    r = _edit(proj, home, spec_path, "- Eine bekannte Grenze.",
              "- Eine bekannte Grenze.\n```")
    _assert_rueckspung_block(r, "AC-13 Fence einfuegen")

    proj2, home2, spec2 = _approved_project(tmp_path / "b", spec=opened)
    r2 = _edit(proj2, home2, spec2, "- Eine bekannte Grenze.\n```",
               "- Eine bekannte Grenze.")
    _assert_rueckspung_block(r2, "AC-13 Fence entfernen")


# --- AC-14: Changelog am Dateiende anhaengen ---------------------------------

def test_changelog_am_dateiende_anhaengen_erlaubt(tmp_path):
    """AC-14 — GIVEN ein eingefrorener ADR-Abschnitt am Dateiende
    WHEN dahinter ein neuer `## Changelog`-Abschnitt angehaengt wird
    THEN ist das erlaubt (Trailing-Whitespace zaehlt nicht)."""
    appended = SPEC_ADR_END + "\n## Changelog\n\n- 2026-10-14: Nachtrag\n"
    proj, home, spec_path = _approved_project(tmp_path, spec=SPEC_ADR_END)
    r = _write(proj, home, spec_path, appended)
    _assert_allowed(r, "AC-14 Changelog anhaengen")

    frozen = _frozen_fn()
    assert frozen(SPEC_ADR_END) == frozen(appended)
    assert frozen(SPEC_ADR_END) == frozen(SPEC_ADR_END + "\n\n   \n")


# --- AC-15: CRLF aendert den Teil-Hash nicht (Unit) ---------------------------

def test_crlf_aendert_teilhash_nicht():
    """AC-15 — GIVEN dieselbe Spec mit \\r\\n- bzw. \\n-Zeilenenden
    WHEN der Teil-Hash berechnet wird
    THEN ist er identisch."""
    frozen = _frozen_fn()
    assert frozen(SPEC) == frozen(SPEC.replace("\n", "\r\n"))


# --- AC-16: Normalisierung der Ueberschriften (Unit) --------------------------

@pytest.mark.parametrize("heading", [
    "## Known Limitations (Stand Oktober)",
    "## KNOWN   limitations",
    "## Implementierungsdetails",
    "## Implementation Details",
    "## Bekannte Einschränkungen",
    "## Testplan",
    "## Test Plan",
    "## Changelog",
    "## Freigabe",
    "## Approval",
])
def test_ueberschrift_normalisierung_und_unbekannt_eingefroren(heading):
    """AC-16 — GIVEN Ueberschriften mit Klammerzusatz, Gross-/Kleinschreibung,
    Mehrfach-Leerzeichen oder deutschem Titel
    WHEN sie gegen die Alias-Tabelle normalisiert werden
    THEN sind sie beweglich; unbekannte Ueberschriften bleiben eingefroren."""
    frozen = _frozen_fn()
    base = f"# T\n\n## Purpose\n\nP\n\n{heading}\n\nB\n"
    assert frozen(base) == frozen(base.replace("\nB\n", "\nB geaendert\n")), (
        f"{heading!r} muss beweglich sein"
    )
    for unknown in ("## Notizen", "## Known Limitation", "## Hinweise (beweglich?)"):
        base = f"# T\n\n## Purpose\n\nP\n\n{unknown}\n\nB\n"
        assert frozen(base) != frozen(base.replace("\nB\n", "\nB geaendert\n")), (
            f"Unbekannte Ueberschrift {unknown!r} muss eingefroren bleiben"
        )


# --- AC-17: Simulation fail-closed --------------------------------------------

def test_simulation_fail_closed(tmp_path):
    """AC-17 — GIVEN ein Edit mit fehlendem old_string, ein mehrdeutiger Edit ohne
    replace_all oder eine nicht lesbare Datei (alles in beweglichen Teilen)
    WHEN das Gate die neue Fassung simulieren will
    THEN blockt es mit 'Edit präzisieren oder Write verwenden'."""
    proj, home, spec_path = _approved_project(tmp_path)

    missing = _edit(proj, home, spec_path, "- Gibt es nicht in der Datei.",
                    "- Neu.", expect_count=0)
    assert missing.returncode == 2, f"fehlender old_string: {missing.stderr!r}"
    assert PRAEZISIEREN in missing.stderr, missing.stderr

    ambiguous = _edit(proj, home, spec_path, "- Doppelt vorhanden.",
                      "- Einmal geaendert.", expect_count=2)
    assert ambiguous.returncode == 2, f"mehrdeutig: {ambiguous.stderr!r}"
    assert PRAEZISIEREN in ambiguous.stderr, ambiguous.stderr

    # Gegenprobe: mit replace_all ist derselbe Edit eindeutig und beweglich.
    both = _edit(proj, home, spec_path, "- Doppelt vorhanden.",
                 "- Beide geaendert.", replace_all=True, expect_count=2)
    _assert_allowed(both, "AC-17 replace_all")

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root liest auch chmod-000-Dateien")
    spec_path.chmod(0)
    try:
        unreadable = _run_gate(proj, home, "Edit", {
            "file_path": str(spec_path), "old_string": "- Eine bekannte Grenze.",
            "new_string": "- Andere Grenze."})
    finally:
        spec_path.chmod(0o644)
    assert unreadable.returncode == 2, f"unlesbar: {unreadable.stderr!r}"
    assert PRAEZISIEREN in unreadable.stderr, unreadable.stderr


# --- AC-18: MultiEdit sequentiell, Write mit vollem Inhalt --------------------

def test_multiedit_und_write_simulation(tmp_path):
    """AC-18 — GIVEN MultiEdit mit mehreren Edits bzw. Write mit vollem Inhalt
    WHEN die neue Fassung simuliert wird
    THEN wird sequentiell bzw. mit dem vollen Inhalt verglichen; beweglich → erlaubt,
    eingefroren → Block."""
    proj, home, spec_path = _approved_project(tmp_path)

    # Zweiter old_string existiert NUR nach dem ersten Edit → beweist Sequenz.
    seq = _run_gate(proj, home, "MultiEdit", {"file_path": str(spec_path), "edits": [
        {"old_string": "- Eine bekannte Grenze.", "new_string": "- Zwischenstand."},
        {"old_string": "- Zwischenstand.", "new_string": "- Endstand."},
    ]})
    _assert_allowed(seq, "AC-18 MultiEdit sequentiell beweglich")

    mixed = _run_gate(proj, home, "MultiEdit", {"file_path": str(spec_path), "edits": [
        {"old_string": "- Eine bekannte Grenze.", "new_string": "- Andere Grenze."},
        {"old_string": "Der Zweck ist klar umrissen.", "new_string": "Neuer Zweck."},
    ]})
    _assert_rueckspung_block(mixed, "AC-18 MultiEdit mit eingefrorenem Teil")

    w_ok = _write(proj, home, spec_path,
                  SPEC.replace("- 2026-10-13: Initial", "- 2026-10-13: Initial\n- Nachtrag"))
    _assert_allowed(w_ok, "AC-18 Write beweglich")

    w_bad = _write(proj, home, spec_path,
                   SPEC.replace("Der Zweck ist klar umrissen.", "Neuer Zweck."))
    _assert_rueckspung_block(w_bad, "AC-18 Write eingefroren")


# --- AC-19: Legacy-Briefing behaelt Gesamt-Freeze -----------------------------

def test_legacy_briefing_behaelt_gesamt_freeze(tmp_path):
    """AC-19 — GIVEN Workflow mit Legacy-Briefing (nur spec_sha256)
    WHEN eine Aenderung an einem beweglichen Teil versucht wird
    THEN gilt der Gesamt-Freeze (Block) mit Hinweis auf `workflow.py set-briefing`."""
    proj, home, spec_path = _approved_project(
        tmp_path, po_briefing=_briefing_entry(SPEC, frozen=False))
    r = _edit(proj, home, spec_path, "- Eine bekannte Grenze.", "- Andere Grenze.")
    assert r.returncode == 2, f"Legacy muss blocken: {r.stderr!r}"
    assert "set-briefing" in r.stderr, (
        f"Legacy-Block muss auf `workflow.py set-briefing` (Migration) verweisen. "
        f"stderr={r.stderr!r}"
    )


# --- AC-20: set-briefing migriert Legacy, wenn Hash passt --------------------

def test_set_briefing_migriert_legacy_wenn_hash_passt(tmp_path):
    """AC-20 — GIVEN Legacy-Briefing, dessen Gesamt-Hash zum aktuellen Inhalt passt
    WHEN `set-briefing` nach der Freigabe (phase5) laeuft
    THEN stehen spec_sha256 + spec_frozen_sha256 in State und Briefing-Frontmatter,
    und danach sind bewegliche Aenderungen erlaubt."""
    proj, home, spec_path = _approved_project(
        tmp_path, po_briefing=_briefing_entry(SPEC, frozen=False))
    r = _run_workflow(proj, home, ["set-briefing", BRIEFING_REL])
    assert r.returncode == 0, f"set-briefing muss migrieren: {r.stdout!r} {r.stderr!r}"

    entry = _state(proj).get("po_briefing", {})
    assert entry.get("spec_sha256") == _sha(SPEC), entry
    assert entry.get("spec_frozen_sha256"), f"Teil-Hash fehlt im State: {entry}"
    assert entry["spec_frozen_sha256"] == _frozen_fn()(SPEC)
    front = _wf.parse_briefing_frontmatter((proj / BRIEFING_REL).read_text())
    assert front.get("spec_sha256") == _sha(SPEC), front
    assert front.get("spec_frozen_sha256") == entry["spec_frozen_sha256"], front

    e = _edit(proj, home, spec_path, "- Eine bekannte Grenze.", "- Andere Grenze.")
    _assert_allowed(e, "AC-20 nach Migration")


# --- AC-21: set-briefing lehnt ab, wenn Hash nicht passt ---------------------

def test_set_briefing_lehnt_ab_wenn_hash_nicht_passt(tmp_path):
    """AC-21 — GIVEN Legacy-Briefing, dessen Gesamt-Hash nicht mehr zum Inhalt passt
    WHEN `set-briefing` nach der Freigabe laeuft
    THEN lehnt es mit Ruecksprung-Hinweis ab und aendert den Stempel nicht."""
    stale = _briefing_entry(SPEC, frozen=False)
    proj, home, spec_path = _approved_project(tmp_path, po_briefing=stale)
    spec_path.write_text(SPEC.replace("Der Zweck ist klar umrissen.", "Still geaendert."))
    briefing_before = (proj / BRIEFING_REL).read_text()

    r = _run_workflow(proj, home, ["set-briefing", BRIEFING_REL])
    assert r.returncode != 0, (
        f"set-briefing darf nach Freigabe bei abweichendem Hash nicht neu stempeln. "
        f"stdout={r.stdout!r} stderr={r.stderr!r}"
    )
    assert RUECKSPRUNG in r.stderr, f"Ruecksprung-Hinweis fehlt: {r.stderr!r}"
    assert _state(proj)["po_briefing"] == stale
    assert (proj / BRIEFING_REL).read_text() == briefing_before


# --- AC-22: Workflow ohne Briefing nutzt Teil-Hash-Vergleich -----------------

@pytest.mark.parametrize("wf_type", ["feature-fast", "feature"])
def test_workflow_ohne_briefing_nutzt_teilhash_vergleich(tmp_path, wf_type):
    """AC-22 — GIVEN freigegebener Workflow ganz ohne Briefing (Fast Track / Gate aus)
    WHEN die Spec geaendert wird
    THEN entscheidet der Teil-Hash-Vergleich: beweglich erlaubt, eingefroren Block."""
    proj, home, spec_path = _make_project(tmp_path)
    _write_workflow(proj, workflow_type=wf_type)
    ok = _edit(proj, home, spec_path, "- Eine bekannte Grenze.", "- Andere Grenze.")
    _assert_allowed(ok, f"AC-22 {wf_type} beweglich")
    bad = _edit(proj, home, spec_path, "Der Zweck ist klar umrissen.", "Neuer Zweck.")
    _assert_rueckspung_block(bad, f"AC-22 {wf_type} eingefroren")


# --- Adversary-Funde (Runde 1) -------------------------------------------------

@pytest.mark.parametrize("tool", ["Edit", "MultiEdit", "Write"])
def test_f001_lone_surrogate_blockt_statt_absturz(tmp_path, tool):
    """F001 — GIVEN eingefrorener Purpose WHEN new_string/content ein einzelnes
    Surrogat (\\ud800) enthaelt THEN blockt das Gate (Exit 2), statt mit Exit 1
    abzustuerzen (Exit 1 = Edit geht durch, fail-open)."""
    proj, home, spec_path = _approved_project(tmp_path)
    old, new = "Der Zweck ist klar umrissen.", "A\ud800B"
    if tool == "Edit":
        payload = {"file_path": str(spec_path), "old_string": old, "new_string": new}
    elif tool == "MultiEdit":
        payload = {"file_path": str(spec_path),
                   "edits": [{"old_string": old, "new_string": new}]}
    else:
        payload = {"file_path": str(spec_path), "content": SPEC.replace(old, new)}
    r = _run_gate(proj, home, tool, payload)
    assert r.returncode == 2, f"{tool}: rc={r.returncode} stderr={r.stderr!r}"
    _frozen_fn()("A\ud800B")  # darf nicht werfen


SPEC_F002 = SPEC.replace("- Doppelt vorhanden.\n\n## Definition of Done",
                         "- Letzte Grenze X\n## Definition of Done")


def test_f002_leerer_new_string_mit_zeilenende_blockt(tmp_path):
    """F002 — GIVEN letzte Zeile eines beweglichen Abschnitts direkt vor einer
    eingefrorenen H2 WHEN ein Edit mit leerem new_string das Zeilenende loescht
    (Claude Code entfernt dabei ggf. das folgende \\n) THEN blockt das Gate,
    weil die Variante ohne \\n die Ueberschrift zerstoert."""
    assert "- Letzte Grenze X\n## Definition of Done" in SPEC_F002
    proj, home, spec_path = _approved_project(tmp_path, spec=SPEC_F002)
    r = _edit(proj, home, spec_path, "Letzte Grenze X", "")
    _assert_rueckspung_block(r, "F002 leerer new_string")


def test_f003_fortsetzung_mit_ac_text_eingefroren(tmp_path):
    """F003 — GIVEN `- Test:`-Zeile mit Fortsetzung WHEN eine Fortsetzung mit
    AC-Label oder Given/When/Then hinzukommt THEN Block; eine normale
    Fortsetzung (Testpfad-Umbruch) bleibt erlaubt."""
    proj, home, spec_path = _approved_project(tmp_path)
    cont = "    Fortsetzung der Testzeile"
    for hidden in ("    **AC-31:** Given x When y Then z", "    then passiert nichts"):
        r = _edit(proj, home, spec_path, cont, cont + "\n" + hidden)
        _assert_rueckspung_block(r, f"F003 {hidden!r}")
    ok = _edit(proj, home, spec_path, cont,
               cont + "\n    `tests/test_demo.py::test_zwei_umbruch`")
    _assert_allowed(ok, "F003 normale Fortsetzung")


# --- AC-26: Legacy-Hashfunktionen byte-identisch ------------------------------

LEGACY_BRIEFING = "docs/briefings/fix-230-briefing-hash.md"
LEGACY_SPEC = "docs/specs/fix-230-spec-freeze-after-approval.md"


def test_legacy_hashfunktionen_byte_identisch():
    """AC-26 — GIVEN das committete Briefing fix-230 mit Gesamt-Hash-Stempel
    WHEN `workflow.spec_sha256` bzw. der Byte-Hash im CI-Gate auf die Spec laeuft
    THEN ergeben beide exakt den gestempelten Wert (schon heute gruen)."""
    front = _wf.parse_briefing_frontmatter((REPO_ROOT / LEGACY_BRIEFING).read_text())
    assert front.get("spec_file") == LEGACY_SPEC, front
    stamp = front["spec_sha256"]
    spec_path = REPO_ROOT / LEGACY_SPEC
    assert _wf.spec_sha256(spec_path.read_text()) == stamp
    assert hashlib.sha256(spec_path.read_bytes()).hexdigest() == stamp
    assert "spec_frozen_sha256" not in front, "Fixture muss ein Legacy-Briefing sein"

    spec = importlib.util.spec_from_file_location("ci_spec_gate_439", CI_SCRIPT)
    ci = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ci)
    problems: list = []
    ci._check_briefing(REPO_ROOT, LEGACY_SPEC, problems)
    assert not [p for p in problems if "veraltet" in p.lower()], problems


# --- AC-27: Spur nach Edit an beweglichem Teil --------------------------------

def test_spur_nach_edit_an_beweglichem_teil(tmp_path):
    """AC-27 — GIVEN ein erlaubter Edit an Known Limitations einer freigegebenen Spec
    (Datei auf Disk bereits geaendert)
    WHEN edit_verify.py danach laeuft (Edit, dann Write)
    THEN steht je ein Eintrag {ts, tool, sections} in spec_post_approval_edits."""
    proj, home, spec_path = _approved_project(tmp_path)
    new = "- Eine nachgetragene Grenze."
    spec_path.write_text(SPEC.replace("- Eine bekannte Grenze.", new))
    r = _run_verify(proj, home, {"tool_name": "Edit", "tool_input": {
        "file_path": str(spec_path), "old_string": "- Eine bekannte Grenze.",
        "new_string": new}})
    assert r.returncode == 0, r.stderr

    edits = _state(proj).get("spec_post_approval_edits")
    assert isinstance(edits, list) and len(edits) == 1, (
        f"Spur fehlt: spec_post_approval_edits={edits!r}"
    )
    entry = edits[0]
    assert entry.get("ts") and entry.get("tool") == "Edit", entry
    sections = entry.get("sections")
    assert isinstance(sections, list) and sections, entry
    assert any("known limitations" in str(s).lower() for s in sections), entry

    content = spec_path.read_text().replace("- 2026-10-13: Initial",
                                            "- 2026-10-13: Initial\n- Nachtrag")
    spec_path.write_text(content)
    w = _run_verify(proj, home, {"tool_name": "Write", "tool_input": {
        "file_path": str(spec_path), "content": content}})
    assert w.returncode == 0, w.stderr
    edits = _state(proj).get("spec_post_approval_edits")
    assert len(edits) == 2, edits
    assert edits[1].get("tool") == "Write" and edits[1].get("sections") == ["*"], edits[1]


# --- AC-28: keine Spur bei geblocktem Edit oder fremder Datei -----------------

def test_keine_spur_bei_geblocktem_edit_oder_fremder_datei(tmp_path):
    """AC-28 — GIVEN ein geblockter Edit (Datei unveraendert), eine fremde Datei
    bzw. eine Spec vor der Freigabe
    WHEN edit_verify.py laeuft
    THEN entsteht kein Spur-Eintrag (schon heute gruen)."""
    proj, home, spec_path = _approved_project(tmp_path)
    blocked = _run_verify(proj, home, {"tool_name": "Edit", "tool_input": {
        "file_path": str(spec_path), "old_string": "Der Zweck ist klar umrissen.",
        "new_string": "Neuer Zweck, der nie auf Disk landete."}})
    assert blocked.returncode == 0
    other = proj / "docs" / "other.md"
    other.write_text("# Andere Datei\n\nNeuer Text.\n")
    o = _run_verify(proj, home, {"tool_name": "Edit", "tool_input": {
        "file_path": str(other), "old_string": "Alt.", "new_string": "Neuer Text."}})
    assert o.returncode == 0
    assert not _state(proj).get("spec_post_approval_edits"), _state(proj)

    proj2, home2, spec2 = _make_project(tmp_path / "draft")
    _write_workflow(proj2, phase="phase3_spec", spec_approved=False)
    spec2.write_text(SPEC.replace("- Eine bekannte Grenze.", "- Entwurf."))
    d = _run_verify(proj2, home2, {"tool_name": "Edit", "tool_input": {
        "file_path": str(spec2), "old_string": "- Eine bekannte Grenze.",
        "new_string": "- Entwurf."}})
    assert d.returncode == 0
    assert not _state(proj2).get("spec_post_approval_edits"), _state(proj2)


# --- AC-29: edit_verify blockt nie ---------------------------------------------

def test_edit_verify_blockt_nie(tmp_path):
    """AC-29 — GIVEN defekter State, unlesbare Datei oder kaputte Eingaben
    WHEN edit_verify.py laeuft
    THEN endet es immer mit Exit 0 (schon heute gruen)."""
    proj, home, spec_path = _approved_project(tmp_path)
    edit_payload = {"tool_name": "Edit", "tool_input": {
        "file_path": str(spec_path), "old_string": "x", "new_string": "Eine"}}

    # Defekter State
    (proj / ".claude" / "workflows" / f"{WF}.json").write_text("{kaputt")
    assert _run_verify(proj, home, edit_payload).returncode == 0

    # Kaputte Eingaben
    for raw in ("kein json", "[]", json.dumps({"tool_input": []}),
                json.dumps({"tool_name": "MultiEdit",
                            "tool_input": {"file_path": str(spec_path), "edits": "x"}}),
                json.dumps({"tool_name": "Edit", "tool_input": {"file_path": 5}})):
        assert _run_verify(proj, home, raw).returncode == 0, raw

    # Unlesbare Datei bei intaktem State
    _write_workflow(proj, po_briefing=_briefing_entry(SPEC))
    if not (hasattr(os, "geteuid") and os.geteuid() == 0):
        spec_path.chmod(0)
        try:
            assert _run_verify(proj, home, edit_payload).returncode == 0
        finally:
            spec_path.chmod(0o644)

    # State-Datei als Verweis (#416): still bleiben, nicht blocken
    real = tmp_path / "elsewhere.json"
    real.write_text(json.dumps(_state(proj)))
    wf_file = proj / ".claude" / "workflows" / f"{WF}.json"
    wf_file.unlink()
    wf_file.symlink_to(real)
    assert _run_verify(proj, home, edit_payload).returncode == 0
