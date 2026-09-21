"""Regressionstests fuer Issue #170 (beilaeufiges Freigabe-Wort in einer
Diskussionsnachricht wird als echte Freigabe gewertet).

Beobachtet am 2026-09-21: Die Nachricht
"1. die mischung aus go, approved und der eingabe von slash-commands ist
unglücklich." setzte `green_approved = True` und legte den Marker
`user_approved_validation_<workflow>` an — der PO wollte nichts freigeben.

Ursache: `_matches(..., leading_only=True)` prueft die *Position* ("Wort steht
irgendwo in Zeile 1 / den ersten 120 Zeichen"), nicht den *Satzbau* ("die
Nachricht IST eine Freigabe").

Spec: docs/specs/fix-170-go-freigabe-phrase.md (AC-1 bis AC-7).
Die Tests sind an die Beispiel-Tabelle der Spec gebunden: jede Zeile dort ist
hier ein parametrisierter Fall.
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

import phase_listener as pl  # noqa: E402


# Wortlaut aus Issue #170 — der Realfall, der die Freigabe ausgeloest hat.
ISSUE_MESSAGE = (
    "1. die mischung aus go, approved und der eingabe von slash-commands "
    "ist unglücklich."
)

# Projekt-Konfiguration wie im Fundprojekt (vgl.
# tests/test_phase_listener_dropped_approval_90.py): "go" ist dort FREIGABE-Phrase
# und gleichzeitig — ueber die Framework-Defaults — GREEN-Phrase.
GREGOR_CONFIG = """
workflow:
  approval_phrases:
    - "go"
    - "approved"
    - "validated"
"""


# --------------------------------------------------------------------------
# Helfer (E2E gegen den echten Hook, Muster aus test_..._dropped_approval_90.py)
# --------------------------------------------------------------------------

def _make_project(tmp_path: Path, phase: str, *, spec_approved: bool = False,
                  green_approved: bool = False,
                  config_yaml: "str | None" = None) -> "tuple[Path, str]":
    """Main-Repo (.git als DIR → kein Worktree) mit aktivem Workflow.

    Bewusst OHNE `spec_file`: dann greifen weder ADR- noch PO-Briefing-Gate
    (beide sind ohne Spec-Datei tolerant), und die Freigabe-Pfade lassen sich
    isoliert pruefen.
    """
    (tmp_path / ".git").mkdir()
    wf_name = "wf-170"
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{wf_name}.json").write_text(json.dumps({
        "name": wf_name,
        "workflow_type": "feature",
        "current_phase": phase,
        "spec_approved": spec_approved,
        "green_approved": green_approved,
    }))
    if config_yaml is not None:
        (tmp_path / "openspec.yaml").write_text(config_yaml)
    return tmp_path, wf_name


def _run_listener(project: Path, wf_name: str, prompt: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"prompt": prompt})
    full_env = dict(os.environ)
    full_env.update({
        "CLAUDE_PROJECT_DIR": str(project),
        "OPENSPEC_ACTIVE_WORKFLOW": wf_name,
    })
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "phase_listener.py")],
        input=payload, capture_output=True, text=True, env=full_env, cwd=str(project),
    )


def _wf_state(project: Path, wf_name: str) -> dict:
    return json.loads((project / ".claude" / "workflows" / f"{wf_name}.json").read_text())


def _marker_path(project: Path, wf_name: str) -> Path:
    return project / ".claude" / f"user_approved_validation_{wf_name}"


def _tokens(project: Path) -> dict:
    """Override-Tokens aus `.claude/user_override_token.json` (v2-Format)."""
    token_file = project / ".claude" / "user_override_token.json"
    if not token_file.exists():
        return {}
    data = json.loads(token_file.read_text())
    if data.get("version") == 2:
        return data.get("tokens", {})
    return {data.get("workflow"): data} if data.get("workflow") else {}


# --------------------------------------------------------------------------
# AC-2 / AC-3 / AC-4: Unit-Tabelle fuer _matches(..., leading_only=True)
# --------------------------------------------------------------------------

# (Nachricht, Name der Phrasenliste, erwartetes Ergebnis, Spec-Begruendung)
APPROVAL_TABLE = [
    # --- AC-2: echte Freigaben (Spec-Tabelle, Spalte "Freigabe") ---
    ("go", "GREEN_PHRASES", True, "Phrase allein"),
    ("Go.", "GREEN_PHRASES", True, "Phrase + Satzzeichen"),
    ("go, passt", "GREEN_PHRASES", True, "Phrase fuehrt, Kopfsatz leer"),
    ("go!", "GREEN_PHRASES", True, "Phrase + Ausrufezeichen"),
    ("ja, go", "GREEN_PHRASES", True, "ein Fuellwort als Vorspann"),
    ("go bitte umsetzen", "GREEN_PHRASES", True, "2 Zusatzwoerter erlaubt"),
    ("green ok", "GREEN_PHRASES", True, "mehrwortige Phrase"),
    ("ok, passt", "APPROVAL_PHRASES", True, "ein Fuellwort als Vorspann"),
    ("Danke, passt so", "APPROVAL_PHRASES", True, "Fuellwort + 1 Zusatzwort"),
    ("Passt für mich", "APPROVAL_PHRASES", True, "2 Zusatzwoerter erlaubt"),
    ("approved", "APPROVAL_PHRASES", True, "Phrase allein"),
    (
        "approved (oder kann ich nicht einfach selbst weitermachen?)",
        "APPROVAL_PHRASES", True,
        "Klammer-Nachsatz wird ignoriert (Realfall aus #46)",
    ),
    # --- AC-1/AC-3: keine Freigaben ---
    (ISSUE_MESSAGE, "GREEN_PHRASES", False, "Issue #170: Zeile beginnt mit Ziffer"),
    (ISSUE_MESSAGE, "APPROVAL_PHRASES", False, "Issue #170: Phrase fuehrt nicht"),
    ("Passt das so?", "APPROVAL_PHRASES", False, "Fragezeichen"),
    ("Approved? Wirklich?", "APPROVAL_PHRASES", False, "Fragezeichen"),
    ("Passt nicht.", "APPROVAL_PHRASES", False, "Negation"),
    ("Go, aber nur für Teil 1", "GREEN_PHRASES", False, "Einschraenkung 'aber'"),
    ("Go check the spec first", "GREEN_PHRASES", False, "Kopfsatz 4 Woerter"),
]


@pytest.mark.parametrize(
    "message,phrase_set,expected,reason",
    APPROVAL_TABLE,
    ids=[f"{m[:38]}|{s[0]}|{'ja' if e else 'nein'}" for m, s, e, _ in APPROVAL_TABLE],
)
def test_ac2_ac3_matches_leading_only_table(message, phrase_set, expected, reason):
    """AC-2 (echte Freigabe wirkt) / AC-3 (Frage, Negation, Einschraenkung nicht).

    GIVEN eine Nachricht aus der Beispiel-Tabelle der Spec
    WHEN `_matches(..., leading_only=True)` sie gegen die Standard-Phrasenliste prueft
    THEN entscheidet der Satzbau, nicht die blosse Position des Stichworts.
    """
    phrases = getattr(pl, phrase_set)
    assert pl._matches(message, phrases, leading_only=True) is expected, (
        f"{message!r} gegen {phrase_set}: erwartet {expected} ({reason})"
    )


OVERRIDE_TABLE = [
    ("override", True, "Phrase allein"),
    ("Override?", False, "Fragezeichen"),
    ("override, bitte erklären", False, "override erlaubt 0 Zusatzwoerter"),
    ("Override: wie funktioniert das?", False, "Fragezeichen + Zusatzwoerter"),
]


@pytest.mark.parametrize(
    "message,expected,reason",
    OVERRIDE_TABLE,
    ids=[f"{m[:30]}|{'ja' if e else 'nein'}" for m, e, _ in OVERRIDE_TABLE],
)
def test_ac4_matches_override_is_stricter(message, expected, reason):
    """AC-4: Override braucht die Phrase allein (0 Zusatzwoerter).

    GIVEN eine Nachricht mit dem Override-Stichwort
    WHEN `_matches(..., leading_only=True)` sie gegen `OVERRIDE_PHRASES` prueft
    THEN gilt nur die Phrase allein als Override — ein Token entsperrt eine
    Stunde lang alle Gates.
    """
    assert pl._matches(message, pl.OVERRIDE_PHRASES, leading_only=True) is expected, (
        f"{message!r} gegen OVERRIDE_PHRASES: erwartet {expected} ({reason})"
    )


# --------------------------------------------------------------------------
# AC-1: Die Nachricht aus dem Issue setzt nichts
# --------------------------------------------------------------------------

def test_ac1_issue_message_does_not_set_green_approval(tmp_path):
    """AC-1: Der Realfall aus Issue #170 darf GREEN nicht freigeben.

    GIVEN ein aktiver Workflow in phase6_implement
    WHEN der User die Diskussionsnachricht mit "go" und "approved" mitten im
         Satz sendet
    THEN bleibt `green_approved` false und der Marker
         `user_approved_validation_<workflow>` wird nicht angelegt.
    """
    project, wf = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, wf, ISSUE_MESSAGE)

    assert res.returncode == 0
    state = _wf_state(project, wf)
    assert state.get("green_approved") is not True, (
        f"Diskussionsnachricht darf GREEN nicht freigeben — State: {state!r}"
    )
    assert not _marker_path(project, wf).exists(), (
        "Das Post-Implementation-Gate darf durch eine Diskussionsnachricht "
        "nicht entsperrt werden"
    )


def test_ac2_e2e_plain_go_still_approves_green(tmp_path):
    """AC-2 (E2E, Regressionswaechter): die echte Freigabe wirkt weiterhin.

    GIVEN ein Workflow in phase6_implement
    WHEN der User `go` sendet
    THEN ist `green_approved` true und der Marker existiert.
    """
    project, wf = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, wf, "go")

    assert res.returncode == 0
    assert _wf_state(project, wf).get("green_approved") is True, (
        f"Echte Freigabe muss wirken — stderr: {res.stderr!r}"
    )
    assert _marker_path(project, wf).exists()


# --------------------------------------------------------------------------
# AC-5: Kein stilles Verwerfen (#90) — und keine laute Falschmeldung
# --------------------------------------------------------------------------

def test_ac5_discarded_keyword_is_reported(tmp_path):
    """AC-5 (a): Ein erkanntes, aber verworfenes Stichwort wird gemeldet.

    GIVEN ein Workflow in phase6_implement (GREEN waere hier relevant)
    WHEN die Diskussionsnachricht aus Issue #170 ankommt
    THEN nennt stderr das Stichwort und sagt, dass es nicht als Freigabe
         gewertet wurde.
    """
    project, wf = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, wf, ISSUE_MESSAGE)

    err = res.stderr
    assert "erkannt, aber nicht als Freigabe gewertet" in err, (
        f"Verworfene Stichworte duerfen nicht still verpuffen (#90) — stderr: {err!r}"
    )
    assert "'go'" in err, f"Das erkannte Stichwort muss genannt sein — stderr: {err!r}"
    assert "'approved'" not in err, (
        "Die Freigabe-Phrase ist in phase6 gar nicht relevant — nur das GREEN-"
        f"Stichwort gehoert in den Hinweis. stderr: {err!r}"
    )


def test_ac5_no_notice_when_message_took_effect_via_other_gate(tmp_path):
    """AC-5 (b): Kein Hinweis, wenn dieselbe Nachricht regulaer gewirkt hat.

    GIVEN eine Projekt-Config, in der "go" Freigabe- UND GREEN-Phrase ist
    WHEN der User in phase6_implement `go` sendet
    THEN wirkt GREEN regulaer und es erscheint KEIN Verworfen-Hinweis
         (sonst erzeugt der Fix fuer eine stille Verwerfung eine laute
         Falschmeldung).
    """
    project, wf = _make_project(tmp_path, "phase6_implement", config_yaml=GREGOR_CONFIG)
    res = _run_listener(project, wf, "go")

    assert res.returncode == 0
    assert _wf_state(project, wf).get("green_approved") is True, (
        f"GREEN muss regulaer greifen — stderr: {res.stderr!r}"
    )
    assert "nicht als Freigabe gewertet" not in res.stderr, (
        f"Keine Falschmeldung bei wirkender Freigabe — stderr: {res.stderr!r}"
    )


# --------------------------------------------------------------------------
# AC-6: Wirkende Freigaben nennen ihren Ausloeser
# --------------------------------------------------------------------------

def test_ac6_green_approval_names_trigger_message(tmp_path):
    """AC-6: Die GREEN-Meldung nennt den ausloesenden Nachrichtentext.

    GIVEN ein Workflow in phase6_implement
    WHEN der User `go, passt` sendet
    THEN steht der ausloesende Text in der stderr-Meldung
         (`GREEN approved (durch: '...')`).
    """
    project, wf = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, wf, "go, passt")

    assert _wf_state(project, wf).get("green_approved") is True, (
        f"Freigabe muss wirken — stderr: {res.stderr!r}"
    )
    assert "durch:" in res.stderr, (
        f"Die Meldung muss den Ausloeser nennen — stderr: {res.stderr!r}"
    )
    assert "go, passt" in res.stderr, (
        f"Der Nachrichtentext gehoert in die Meldung — stderr: {res.stderr!r}"
    )


def test_ac6_spec_approval_names_trigger_message(tmp_path):
    """AC-6: Auch die Spec-Freigabe nennt ihren Ausloeser.

    GIVEN ein Workflow in phase3_spec (ohne `spec_file`, damit weder ADR- noch
          PO-Briefing-Gate greifen)
    WHEN der User `approved` sendet
    THEN ist die Spec freigegeben und die stderr-Meldung nennt den Ausloeser.
    """
    project, wf = _make_project(tmp_path, "phase3_spec")
    res = _run_listener(project, wf, "approved")

    state = _wf_state(project, wf)
    assert state.get("spec_approved") is True, (
        f"Freigabe muss wirken — stderr: {res.stderr!r}"
    )
    assert "durch:" in res.stderr, (
        f"Die Meldung muss den Ausloeser nennen — stderr: {res.stderr!r}"
    )
    assert "approved" in res.stderr


def test_ac6_override_token_names_trigger_message(tmp_path):
    """AC-6: Der Override-Token meldet den ausloesenden Text mit.

    GIVEN eine Session mit aktivem Workflow
    WHEN der User `override` sendet
    THEN meldet stderr die Token-Erzeugung samt Ausloeser.
    """
    project, wf = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, wf, "override")

    assert "Override token created" in res.stderr, (
        f"Token-Meldung fehlt — stderr: {res.stderr!r}"
    )
    assert "durch:" in res.stderr, (
        f"Die Meldung muss den Ausloeser nennen — stderr: {res.stderr!r}"
    )


# --------------------------------------------------------------------------
# AC-4 (E2E): Override-Token entsteht nur bei der Phrase allein
# --------------------------------------------------------------------------

def test_ac4_e2e_plain_override_creates_token(tmp_path):
    """AC-4 (Regressionswaechter): `override` allein erzeugt den Token.

    GIVEN eine Session mit aktivem Workflow
    WHEN der User `override` sendet
    THEN existiert ein Token fuer diesen Workflow.
    """
    project, wf = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, wf, "override")

    assert res.returncode == 0
    assert wf in _tokens(project), (
        f"Echtes Override muss wirken — stderr: {res.stderr!r}"
    )


@pytest.mark.parametrize("message", [
    "Override?",
    "override, bitte erklären",
    "Override: wie funktioniert das?",
])
def test_ac4_e2e_question_about_override_creates_no_token(tmp_path, message):
    """AC-4: Eine Frage nach dem Override erzeugt keinen Token.

    GIVEN eine Session mit aktivem Workflow
    WHEN der User nach dem Override fragt statt ihn zu erteilen
    THEN entsteht kein Eintrag in `.claude/user_override_token.json`.
    """
    project, wf = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, wf, message)

    assert res.returncode == 0
    assert _tokens(project) == {}, (
        f"{message!r} darf keinen Override-Token erzeugen — "
        f"Tokens: {_tokens(project)!r}, stderr: {res.stderr!r}"
    )


# --------------------------------------------------------------------------
# AC-7: Unveraendertes Verhalten von Stop-Lock und Notification-Turns
# --------------------------------------------------------------------------

def test_ac7_stop_phrase_mid_sentence_still_matches():
    """AC-7: Der Not-Aus bleibt bewusst grosszuegig.

    GIVEN ein Stop-Wort mitten im Satz
    WHEN `_matches` ohne `leading_only` prueft (so ruft der Hook die
         Stop-/Continue-Listen auf)
    THEN greift es weiterhin — die Verschaerfung gilt nur fuer
         approval/GREEN/override.
    """
    assert pl._matches("bitte jetzt stopp sagen", pl.STOP_PHRASES) is True
    assert pl._matches("lass uns jetzt weitermachen", pl.CONTINUE_PHRASES) is True


def test_ac7_notification_turn_still_ignored(tmp_path):
    """AC-7: Notification-Turns werden weiterhin komplett uebersprungen (#46).

    GIVEN ein Workflow in phase6_implement
    WHEN ein harness-injizierter Turn ankommt, dessen erste Zeile `go` lautet
    THEN aendert sich nichts am Workflow-Zustand.
    """
    project, wf = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(
        project, wf,
        "go\n\n<task-notification>Agent hat berichtet</task-notification>",
    )

    assert res.returncode == 0
    assert _wf_state(project, wf).get("green_approved") is not True, (
        "Notification-Turns duerfen keine Freigabe setzen"
    )
    assert not _marker_path(project, wf).exists()
