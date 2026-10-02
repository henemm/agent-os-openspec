"""RED-Tests fuer Issue #277 (Sammel-Vorgang, fasst #268, #175, #310).

Drei Ursachen, ein Test pro Acceptance Criterion der Spec
docs/specs/fix-277-freigabe-woerter.md:

- #268: Die Sperrmeldung des Post-Implementation-Gates nennt Woerter
  ('freigabe', 'approved'), die in phase6 nicht wirken (AC-1..3).
- #175: Deutsche Einschraenkungen ("go, erst noch die Doku") heben die
  Freigabe nicht auf (AC-4, AC-5; Gegenprobe AC-6..8).
- #310: Rueckmeldungen des phase_listener gehen auf stderr und erreichen
  niemanden; sie muessen als ein JSON-Objekt mit `systemMessage` auf stdout
  (AC-9..13).
- F004: Prosa von Schritt 4 in Spec #170 widerspricht dem Code (AC-14).

Die Tests steuern `core/hooks` des Worktrees per subprocess an (Wegwerf-
Projekt, .git als DIR), nicht die installierte Plugin-Fassung.

Regressionsschutz (beschreiben bestehendes Verhalten, duerfen vor der
Implementierung gruen sein): AC-6, AC-7, AC-8, AC-13.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
SPEC_170 = REPO_ROOT / "docs" / "specs" / "fix-170-go-freigabe-phrase.md"

WF = "wf-277"

# Projekt mit abweichender GREEN-Liste (AC-2, AC-12)
LOS_CONFIG = """
workflow:
  green_phrases:
    - "los"
    - "go"
"""

# Projekt mit "passt" als Freigabe-Phrase (AC-6)
PASST_CONFIG = """
workflow:
  approval_phrases:
    - "approved"
    - "passt"
"""


# --------------------------------------------------------------------------
# Helfer
# --------------------------------------------------------------------------

def _make_project(tmp_path: Path, phase: str, *, config_yaml: "str | None" = None,
                  lock_age_s: "float | None" = None,
                  marker_content: "str | None" = None) -> Path:
    """Main-Repo (.git als DIR) mit aktivem Workflow, bewusst ohne spec_file."""
    (tmp_path / ".git").mkdir(parents=True)
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{WF}.json").write_text(json.dumps({
        "name": WF,
        "workflow_type": "feature",
        "current_phase": phase,
        "spec_approved": False,
        "green_approved": False,
    }))
    if config_yaml is not None:
        (tmp_path / "openspec.yaml").write_text(config_yaml)
    if lock_age_s is not None:
        (tmp_path / ".claude" / f"pending_validation_{WF}.json").write_text(json.dumps({
            "workflow": WF,
            "workflow_created": None,
            "created": time.time() - lock_age_s,
        }))
    if marker_content is not None:
        (tmp_path / ".claude" / f"user_approved_validation_{WF}").write_text(marker_content)
    return tmp_path


def _env(project: Path, active: "str | None" = WF) -> dict:
    env = dict(os.environ)
    env.pop("CLAUDE_TOOL_INPUT", None)
    env.pop("OPENSPEC_FRAMEWORK", None)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    if active:
        env["OPENSPEC_ACTIVE_WORKFLOW"] = active
    else:
        env.pop("OPENSPEC_ACTIVE_WORKFLOW", None)
    return env


def _run_listener(project: Path, prompt: str,
                  active: "str | None" = WF) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "phase_listener.py")],
        input=json.dumps({"prompt": prompt}), capture_output=True, text=True,
        env=_env(project, active), cwd=str(project),
    )


def _run_gate(project: Path) -> subprocess.CompletedProcess:
    """post_implementation_gate.py mit einem Code-Edit (kein Docs-Pfad)."""
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(project / "src" / "app.py")}}
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "post_implementation_gate.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env=_env(project), cwd=str(project),
    )


def _state(project: Path) -> dict:
    return json.loads((project / ".claude" / "workflows" / f"{WF}.json").read_text())


def _marker(project: Path) -> Path:
    return project / ".claude" / f"user_approved_validation_{WF}"


def _json_stdout(res: subprocess.CompletedProcess) -> dict:
    """stdout muss genau ein parsbares JSON-Objekt sein."""
    try:
        obj = json.loads(res.stdout)
    except json.JSONDecodeError:
        pytest.fail(
            "stdout ist kein einzelnes JSON-Objekt (Rueckmeldung erreicht den "
            f"Nutzer nicht). stdout={res.stdout!r} stderr={res.stderr!r}"
        )
    assert isinstance(obj, dict), f"stdout ist kein JSON-Objekt: {obj!r}"
    return obj


def _system_message(res: subprocess.CompletedProcess) -> str:
    obj = _json_stdout(res)
    assert isinstance(obj.get("systemMessage"), str) and obj["systemMessage"].strip(), (
        f"systemMessage fehlt oder leer: {obj!r}"
    )
    return obj["systemMessage"]


def _quoted_phrases(text: str) -> list:
    """Alle in einfache Anfuehrungszeichen gesetzten Phrasen einer Meldung."""
    return re.findall(r"'([^']+)'", text)


def _gate_messages(tmp_path: Path, config_yaml: "str | None") -> "list[str]":
    """Beide Sperrmeldungen des Gates: Batch-Fenster abgelaufen und
    Marker-aus-frueherem-Lauf. Jeweils eigenes Wegwerf-Projekt."""
    msgs = []
    expired = _make_project(tmp_path / "expired", "phase6_implement",
                            config_yaml=config_yaml, lock_age_s=60 * 60)
    res = _run_gate(expired)
    assert res.returncode == 2, f"Gate sperrte nicht (Fenster): {res.returncode} {res.stderr!r}"
    msgs.append(res.stderr)

    stale = _make_project(tmp_path / "stale", "phase6_implement",
                          config_yaml=config_yaml, lock_age_s=60,
                          marker_content="0.0")
    res = _run_gate(stale)
    assert res.returncode == 2, f"Gate sperrte nicht (Marker): {res.returncode} {res.stderr!r}"
    msgs.append(res.stderr)
    return msgs


# --------------------------------------------------------------------------
# AC-1..3: Sperrmeldung aus der Konfiguration (#268)
# --------------------------------------------------------------------------

def test_sperrmeldung_nennt_nur_green_phrasen(tmp_path):
    """AC-1: Standard-Config -> Meldung nennt 'go', nicht freigabe/approved."""
    for msg in _gate_messages(tmp_path, None):
        assert "'go'" in msg, f"Sperrmeldung nennt 'go' nicht: {msg!r}"
        assert "freigabe'" not in msg.lower() and "'freigabe" not in msg.lower(), (
            f"Sperrmeldung nennt unwirksames Wort 'freigabe': {msg!r}"
        )
        assert "approved" not in msg.lower(), (
            f"Sperrmeldung nennt unwirksames Wort 'approved': {msg!r}"
        )


def test_sperrmeldung_folgt_projekt_config(tmp_path):
    """AC-2: abweichende green_phrases stehen genau so in der Sperrmeldung."""
    for msg in _gate_messages(tmp_path, LOS_CONFIG):
        assert sorted(_quoted_phrases(msg)) == ["go", "los"], (
            f"Sperrmeldung nennt nicht genau die konfigurierten Phrasen "
            f"['los','go']: {msg!r}"
        )


@pytest.mark.parametrize("config_yaml", [None, LOS_CONFIG], ids=["standard", "projekt"])
def test_jede_genannte_phrase_wirkt_in_phase6(tmp_path, config_yaml):
    """AC-3: jede in einer Sperrmeldung genannte Phrase setzt green_approved."""
    phrases = set()
    for msg in _gate_messages(tmp_path / "gate", config_yaml):
        phrases.update(_quoted_phrases(msg))
    assert phrases, "Keine Phrase in den Sperrmeldungen gefunden"
    for i, phrase in enumerate(sorted(phrases)):
        project = _make_project(tmp_path / f"listener{i}", "phase6_implement",
                                config_yaml=config_yaml)
        res = _run_listener(project, phrase)
        assert res.returncode == 0
        assert _state(project).get("green_approved") is True, (
            f"Sperrmeldung nennt '{phrase}', aber es setzt keine GREEN-Freigabe "
            f"(stderr={res.stderr!r})"
        )


# --------------------------------------------------------------------------
# AC-4..8: Einschraenkungswoerter (#175)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "Go war falsch",
    "go, erst noch die Doku",
    "go, wenn Tests grün",
    "go, nein",
    "go, niemals",
])
def test_einschraenkungssaetze_setzen_keine_green_freigabe(tmp_path, message):
    """AC-4: Einschraenkung -> kein green_approved, kein Freigabe-Marker."""
    project = _make_project(tmp_path, "phase6_implement", lock_age_s=60)
    res = _run_listener(project, message)
    assert res.returncode == 0
    assert _state(project).get("green_approved") is False, (
        f"'{message}' setzte green_approved (stderr={res.stderr!r})"
    )
    assert not _marker(project).exists(), f"'{message}' legte einen Freigabe-Marker an"


@pytest.mark.parametrize("message", [
    "Freigabe fehlt noch",
    "approved, erst noch die Doku",
    "approved, wenn Tests grün",
    "approved, nein",
])
def test_einschraenkungssaetze_setzen_keine_spec_freigabe(tmp_path, message):
    """AC-5: Einschraenkung -> kein spec_approved, Phase bleibt phase3_spec."""
    project = _make_project(tmp_path, "phase3_spec")
    res = _run_listener(project, message)
    assert res.returncode == 0
    state = _state(project)
    assert state.get("spec_approved") is False, (
        f"'{message}' setzte spec_approved (stderr={res.stderr!r})"
    )
    assert state.get("current_phase") == "phase3_spec"


@pytest.mark.parametrize("message,phase,config_yaml,field", [
    ("go", "phase6_implement", None, "green_approved"),
    ("go, passt", "phase6_implement", None, "green_approved"),
    ("go bitte umsetzen", "phase6_implement", None, "green_approved"),
    ("approved (oder kann ich nicht einfach selbst weitermachen?)",
     "phase3_spec", None, "spec_approved"),
    ("Passt für mich", "phase3_spec", PASST_CONFIG, "spec_approved"),
])
def test_echte_freigaben_wirken_weiter(tmp_path, message, phase, config_yaml, field):
    """AC-6 (Regressionsschutz, darf vor der Implementierung gruen sein)."""
    project = _make_project(tmp_path, phase, config_yaml=config_yaml)
    res = _run_listener(project, message)
    assert res.returncode == 0
    assert _state(project).get(field) is True, (
        f"Echte Freigabe '{message}' wirkt nicht mehr (stderr={res.stderr!r})"
    )


@pytest.mark.parametrize("message", ["go, erste Version", "go, nochmal bitte"])
def test_listenwort_als_wortteil_hebt_nicht_auf(tmp_path, message):
    """AC-7 (Regressionsschutz): Wortgrenzen-Regel, 'erste'/'nochmal' sind
    keine Listenwoerter."""
    project = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, message)
    assert res.returncode == 0
    assert _state(project).get("green_approved") is True, (
        f"'{message}' wurde zu Unrecht verworfen (stderr={res.stderr!r})"
    )


def test_negation_in_klammern_bleibt_wirkungslos(tmp_path):
    """AC-8 (Regressionsschutz, F002): Klammern sind Nebenbemerkung."""
    project = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, "go (aber nicht jetzt)")
    assert res.returncode == 0
    assert _state(project).get("green_approved") is True


# --------------------------------------------------------------------------
# AC-9..13: Rueckmeldung sichtbar (#310)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("message,keyword", [
    ("go, nein", "go"),
    ("approved", "approved"),
])
def test_meldung_als_systemmessage_ein_json_objekt(tmp_path, message, keyword):
    """AC-9: stdout = ein JSON-Objekt, systemMessage nennt das Stichwort,
    stderr bleibt als Spiegel gefuellt."""
    project = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, message)
    assert res.returncode == 0
    assert keyword in _system_message(res).lower()
    assert res.stderr.strip(), "stderr-Spiegel der Meldung fehlt"


def test_status_note_und_meldung_ein_objekt(tmp_path):
    """AC-10: mit Meldung -> ein JSON-Objekt, Statusvermerk in
    additionalContext; ohne Meldung -> reiner Statusvermerk wie bisher."""
    # ohne Meldung: reiner Text (bleibt wie 3.25.0)
    quiet = _make_project(tmp_path / "quiet", "phase6_implement")
    res = _run_listener(quiet, "Bitte mach weiter mit dem Test")
    assert res.returncode == 0
    assert res.stdout.strip(), "Statusvermerk fehlt ohne Meldung"
    with pytest.raises(json.JSONDecodeError):
        json.loads(res.stdout)
    plain_note = res.stdout.strip()

    # mit Meldung: ein Objekt, Vermerk in additionalContext
    noisy = _make_project(tmp_path / "noisy", "phase6_implement")
    res = _run_listener(noisy, "go, nein")
    assert res.returncode == 0
    obj = _json_stdout(res)
    assert obj.get("systemMessage", "").strip()
    hso = obj.get("hookSpecificOutput", {})
    assert hso.get("hookEventName") == "UserPromptSubmit", obj
    assert plain_note in hso.get("additionalContext", ""), (
        f"Statusvermerk {plain_note!r} fehlt in additionalContext: {obj!r}"
    )


def test_fruehe_austrittspunkte_nutzen_denselben_kanal(tmp_path):
    """AC-11: Stop-Lock-Exit und Lauf ohne aufloesbaren Workflow."""
    # Stop-Lock-Satz mit verworfenem Override-Stichwort -> Meldung + frueher Exit
    p1 = _make_project(tmp_path / "stop", "phase6_implement")
    res = _run_listener(p1, "override, bitte stopp")
    assert res.returncode == 0
    assert "override" in _system_message(res).lower()

    # Lauf ohne aufloesbaren Workflow, freigabe-aehnliche Eingabe
    p2 = _make_project(tmp_path / "nowf", "phase6_implement")
    res = _run_listener(p2, "go", active="gibt-es-nicht")
    assert res.returncode == 0
    assert "workflow" in _system_message(res).lower()


@pytest.mark.parametrize("config_yaml,expected", [(None, "go"), (LOS_CONFIG, "los")])
def test_verworfen_hinweis_nennt_konfigurierte_phrase(tmp_path, config_yaml, expected):
    """AC-12: Beispielphrase im Verworfen-Hinweis = erste konfigurierte
    GREEN-Phrase, nie 'approved'."""
    project = _make_project(tmp_path, "phase6_implement", config_yaml=config_yaml)
    res = _run_listener(project, "go, nein")
    assert res.returncode == 0
    msg = _system_message(res)
    assert f'"{expected}"' in msg or f"'{expected}'" in msg, (
        f"Konfigurierte Phrase '{expected}' fehlt im Hinweis: {msg!r}"
    )
    assert "approved" not in msg.lower(), f"Hinweis nennt 'approved': {msg!r}"


def test_notification_turn_unveraendert(tmp_path):
    """AC-13 (Regressionsschutz): Notification-Turn ueberspringt die
    Keyword-Erkennung, Statusvermerk bleibt reiner Text; Stop-Lock wirkt."""
    project = _make_project(tmp_path / "notif", "phase6_implement")
    res = _run_listener(project, "<task-notification>go</task-notification>")
    assert res.returncode == 0
    assert _state(project).get("green_approved") is False
    assert res.stdout.strip(), "Statusvermerk fehlt im Notification-Turn"
    with pytest.raises(json.JSONDecodeError):
        json.loads(res.stdout)

    stop = _make_project(tmp_path / "stop", "phase6_implement")
    res = _run_listener(stop, "stopp")
    assert res.returncode == 0
    lock = json.loads((stop / ".claude" / "stop_lock.json").read_text())
    assert lock == {"enabled": True}


# --------------------------------------------------------------------------
# AC-14: Spec #170, Schritt 4 passt zu Tabelle/AC-4 (F004)
# --------------------------------------------------------------------------

def test_spec_170_schritt4_passt_zur_tabelle():
    """Schritt 4 darf Override nicht als '0 Zusatzwoerter im Kopfsatz'
    beschreiben (das liesse 'override, danke' zu, Tabelle/Code verlangen die
    Phrase allein bis Zeilenende). Pflicht: Schritt 4 sagt fuer Override
    ausdruecklich 'allein' und nennt das Zeilenende."""
    text = SPEC_170.read_text()
    step4 = next((ln for ln in text.splitlines() if ln.startswith("4. **Kopfsatz")), None)
    assert step4 is not None, "Schritt 4 (Kopfsatz) nicht gefunden"
    assert "2 Zusatzwörter" in step4, f"Schritt 4 nennt die 2-Wort-Regel nicht: {step4!r}"
    assert not re.search(r"override\s*\**\s*0", step4, re.IGNORECASE), (
        f"Schritt 4 beschreibt Override noch als '0 Zusatzwoerter im Kopfsatz': {step4!r}"
    )
    override_part = step4.lower().split("override", 1)[-1] if "override" in step4.lower() else ""
    assert "allein" in override_part and "zeilenende" in override_part, (
        f"Schritt 4 sagt fuer Override nicht 'Phrase allein bis Zeilenende': {step4!r}"
    )


# --------------------------------------------------------------------------
# Adversary-Nachtrag: bash_gate-Marker-Sperre, leere green-Config
# --------------------------------------------------------------------------

def test_bash_gate_marker_sperre_nennt_keine_unwirksamen_woerter(tmp_path):
    """Die bash_gate-Sperrmeldung fuer Freigabe-Marker nennt weder 'approved'
    noch 'freigabe' als einzutippendes Wort (in phase6 unwirksam, #268)."""
    project = _make_project(tmp_path, "phase6_implement")
    cmd = f"touch .claude/user_approved_validation_{WF}"
    res = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bash_gate.py")],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True, text=True, env=_env(project), cwd=str(project),
    )
    assert res.returncode == 2, f"Marker-Sperre griff nicht: {res.returncode} {res.stderr!r}"
    assert "Freigabe-/Erfolgs-Marker" in res.stderr, res.stderr
    assert "'approved'" not in res.stderr and "'freigabe'" not in res.stderr, res.stderr


def test_leere_green_config_faellt_auf_standard_zurueck(tmp_path):
    """Leere green_phrases -> Sperrmeldung nennt trotzdem 'go' (nie 'tippt .')."""
    for msg in _gate_messages(tmp_path, "workflow:\n  green_phrases: []\n"):
        assert "'go'" in msg, f"Sperrmeldung ohne 'go' bei leerer Config: {msg!r}"
