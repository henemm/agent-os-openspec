"""RED-Tests fuer Issue #311 (Befunde F001, F006, F007, F008 aus #277).

Ein Test pro Acceptance Criterion der Spec
docs/specs/fix-311-freigabe-folgezeilen.md:

- F001: Einschraenkungen in Folgezeilen heben die Freigabe heute nicht auf
  (AC-1..3, AC-7, AC-8).
- F007: Bedingungs-/Zeitwoerter fehlen in NEGATION_WORDS (AC-4).
- F006: Spec #170 (Known Limitations, Tabelle, Schritt 6) (AC-11).
- F008: Kommentar in bash_gate.py nennt feste Phrasen (AC-13).

Die Tests steuern `core/hooks` des Worktrees per subprocess an (Wegwerf-
Projekt, .git als DIR), nicht die installierte Plugin-Fassung.

Regressionsschutz (beschreiben bestehendes Verhalten, duerfen vor der
Implementierung gruen sein): AC-5, AC-6, AC-9, AC-10, AC-12.
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
BASH_GATE = HOOKS_DIR / "bash_gate.py"

WF = "wf-311"

F007_WORDS = ["falls", "sobald", "bevor", "solange", "sofern", "unless", "until", "once"]

F007_MESSAGES = [
    "go, falls Henning zustimmt",
    "go, sobald CI gruen",
    "go, bevor wir mergen",
    "go, solange Tests laufen",
    "go, sofern möglich",
    "go, unless broken",
    "go, until Friday",
    "go, once CI is green",
]


# --------------------------------------------------------------------------
# Helfer (Stil aus test_phase_listener_restrictions_277.py)
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


def _state(project: Path) -> dict:
    return json.loads((project / ".claude" / "workflows" / f"{WF}.json").read_text())


def _marker(project: Path) -> Path:
    return project / ".claude" / f"user_approved_validation_{WF}"


def _token_file(project: Path) -> Path:
    # Pfad wie override_token._get_token_file(): <root>/.claude/user_override_token.json
    return project / ".claude" / "user_override_token.json"


def _has_token(project: Path) -> bool:
    path = _token_file(project)
    if not path.exists():
        return False
    data = json.loads(path.read_text())
    return WF in data.get("tokens", {})


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


def _assert_no_green(tmp_path: Path, message: str) -> None:
    project = _make_project(tmp_path, "phase6_implement", lock_age_s=60)
    res = _run_listener(project, message)
    assert res.returncode == 0
    assert _state(project).get("green_approved") is False, (
        f"{message!r} setzte green_approved (stderr={res.stderr!r})"
    )
    assert not _marker(project).exists(), f"{message!r} legte einen Freigabe-Marker an"


def _assert_no_spec(tmp_path: Path, message: str) -> None:
    project = _make_project(tmp_path, "phase3_spec")
    res = _run_listener(project, message)
    assert res.returncode == 0
    state = _state(project)
    assert state.get("spec_approved") is False, (
        f"{message!r} setzte spec_approved (stderr={res.stderr!r})"
    )
    assert state.get("current_phase") == "phase3_spec"


# --------------------------------------------------------------------------
# AC-1..4: Einschraenkungen in Folgezeilen und F007-Woerter
# --------------------------------------------------------------------------

@pytest.mark.parametrize("message", ["go\nerst die Doku", "go\nnein, später"])
def test_folgezeile_einschraenkung_setzt_keine_green_freigabe(tmp_path, message):
    """AC-1: Einschraenkung in Folgezeile -> kein green_approved, kein Marker."""
    _assert_no_green(tmp_path, message)


@pytest.mark.parametrize("message", ["Approved\nspäter", "approved\nerst noch die Doku"])
def test_folgezeile_einschraenkung_setzt_keine_spec_freigabe(tmp_path, message):
    """AC-2: Einschraenkung in Folgezeile -> kein spec_approved, Phase bleibt."""
    _assert_no_spec(tmp_path, message)


@pytest.mark.parametrize("message,phase", [
    ("go\nwarum ist das so?", "phase6_implement"),
    ("approved\nist das so richtig?", "phase3_spec"),
])
def test_frage_in_folgezeile_verwirft_freigabe(tmp_path, message, phase):
    """AC-3: Fragezeichen in Folgezeile -> keine Freigabe."""
    if phase == "phase6_implement":
        _assert_no_green(tmp_path, message)
    else:
        _assert_no_spec(tmp_path, message)


@pytest.mark.parametrize("message",
                         F007_MESSAGES + [m.replace(", ", "\n", 1) for m in F007_MESSAGES])
def test_bedingungswoerter_f007_heben_freigabe_auf(tmp_path, message):
    """AC-4: Bedingungs-/Zeitwoerter heben die Freigabe auf (Zeile 1 und
    Folgezeile)."""
    _assert_no_green(tmp_path, message)


# --------------------------------------------------------------------------
# AC-5, AC-6, AC-9: Regressionsschutz (zu streng vermeiden)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "go, bevorzugt Variante A",
    "go\noncology",
    "go\nerste Version",
])
def test_listenwort_als_wortteil_in_folgezeile_hebt_nicht_auf(tmp_path, message):
    """AC-5 (Regressionsschutz): Wortgrenzen-Regel gilt auch fuer Folgezeilen."""
    project = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, message)
    assert res.returncode == 0
    assert _state(project).get("green_approved") is True, (
        f"{message!r} wurde zu Unrecht verworfen (stderr={res.stderr!r})"
    )


@pytest.mark.parametrize("message", ["approved\n(oder später?)", "approved\n(oder später?"])
def test_klammer_in_folgezeile_bleibt_ausnahme(tmp_path, message):
    """AC-6 (Regressionsschutz, #46): Klammer-Einschub in Folgezeile zaehlt nicht."""
    project = _make_project(tmp_path, "phase3_spec")
    res = _run_listener(project, message)
    assert res.returncode == 0
    assert _state(project).get("spec_approved") is True, (
        f"{message!r} wurde zu Unrecht verworfen (stderr={res.stderr!r})"
    )


def test_leerzeile_und_zusatztext_bleibt_freigabe(tmp_path):
    """AC-9 (Regressionsschutz): Leerzeile + Zusatztext ohne Einschraenkung."""
    project = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, "go\n\nBitte Doku schreiben")
    assert res.returncode == 0
    assert _state(project).get("green_approved") is True, (
        f"'go⏎⏎Bitte Doku schreiben' wurde verworfen (stderr={res.stderr!r})"
    )


# --------------------------------------------------------------------------
# AC-7: Override verlangt leere Folgezeilen
# --------------------------------------------------------------------------

def test_override_verlangt_leere_folgezeilen(tmp_path):
    """AC-7: override⏎irgendwas -> kein Token; override⏎⏎ und
    override⏎(danach weiter) -> Token."""
    # Gegenprobe: 'override' allein legt den Token im erwarteten Pfad an,
    # sonst waere der Negativfall aus falschem Grund gruen.
    probe = _make_project(tmp_path / "probe", "phase6_implement")
    res = _run_listener(probe, "override")
    assert res.returncode == 0
    assert _has_token(probe), (
        f"Gegenprobe: 'override' allein legte keinen Token an "
        f"({_token_file(probe)}; stderr={res.stderr!r})"
    )

    neg = _make_project(tmp_path / "neg", "phase6_implement")
    res = _run_listener(neg, "override\nirgendwas")
    assert res.returncode == 0
    assert not _has_token(neg), (
        f"'override⏎irgendwas' legte einen Override-Token an (stderr={res.stderr!r})"
    )

    for i, message in enumerate(["override\n\n", "override\n(danach weiter)"]):
        pos = _make_project(tmp_path / f"pos{i}", "phase6_implement")
        res = _run_listener(pos, message)
        assert res.returncode == 0
        assert _has_token(pos), (
            f"{message!r} legte keinen Override-Token an (stderr={res.stderr!r})"
        )


# --------------------------------------------------------------------------
# AC-8: Hinweis nennt Folgezeile als systemMessage
# --------------------------------------------------------------------------

def test_verworfen_hinweis_nennt_folgezeile_als_systemmessage(tmp_path):
    """AC-8: stdout = ein JSON-Objekt, systemMessage nennt 'go' und die
    Folgezeile; stderr bleibt als Spiegel gefuellt."""
    project = _make_project(tmp_path, "phase6_implement")
    res = _run_listener(project, "go\nerst die Doku")
    assert res.returncode == 0
    msg = _system_message(res).lower()
    assert "go" in msg, f"Hinweis nennt das Stichwort 'go' nicht: {msg!r}"
    assert "folgezeile" in msg, f"Hinweis nennt die Folgezeile nicht als Grund: {msg!r}"
    assert res.stderr.strip(), "stderr-Spiegel der Meldung fehlt"


# --------------------------------------------------------------------------
# AC-10: Notification-Turn und Stop-Lock unveraendert
# --------------------------------------------------------------------------

def test_notification_turn_und_stop_lock_unveraendert(tmp_path):
    """AC-10 (Regressionsschutz)."""
    notif = _make_project(tmp_path / "notif", "phase6_implement", lock_age_s=60)
    res = _run_listener(
        notif, "go\n\n<task-notification>Agent hat berichtet</task-notification>")
    assert res.returncode == 0
    assert _state(notif).get("green_approved") is False
    assert not _marker(notif).exists()

    stop = _make_project(tmp_path / "stop", "phase6_implement")
    res = _run_listener(stop, "stopp")
    assert res.returncode == 0
    lock = json.loads((stop / ".claude" / "stop_lock.json").read_text())
    assert lock == {"enabled": True}


# --------------------------------------------------------------------------
# AC-11: Spec #170 konsistent
# --------------------------------------------------------------------------

def _table_row(text: str, needle: str) -> "str | None":
    return next((ln for ln in text.splitlines()
                 if ln.lstrip().startswith("|") and needle in ln), None)


def test_spec_170_konsistenz_folgezeilen_tabelle_schritt6():
    """AC-11: Known Limitations ohne 'Nur die erste Zeile zaehlt (unveraendert)',
    Tabelle mit beiden Folgezeilen-Faellen, Schritt 6 mit den F007-Woertern."""
    text = SPEC_170.read_text()

    assert not re.search(r"Nur die erste Zeile zählt\**\s*\(unverändert\)", text), (
        "Known Limitations sagt noch 'Nur die erste Zeile zählt (unverändert)'"
    )

    row_neg = _table_row(text, "erst die Doku")
    assert row_neg is not None, "Beispieltabelle hat keine Zeile 'go⏎erst die Doku'"
    assert "go⏎erst die Doku" in row_neg, f"Schreibweise 'go⏎erst die Doku' fehlt: {row_neg!r}"
    assert "keine" in row_neg.lower(), f"'go⏎erst die Doku' nicht als keine Freigabe: {row_neg!r}"

    row_pos = _table_row(text, "Bitte Doku schreiben")
    assert row_pos is not None, "Beispieltabelle hat keine Zeile 'go⏎⏎Bitte Doku schreiben'"
    assert "go⏎⏎Bitte Doku schreiben" in row_pos, (
        f"Schreibweise 'go⏎⏎Bitte Doku schreiben' fehlt: {row_pos!r}"
    )
    cells = [c.strip().lower() for c in row_pos.strip().strip("|").split("|")]
    assert len(cells) >= 2 and cells[1].startswith("freigabe"), (
        f"'go⏎⏎Bitte Doku schreiben' nicht als Freigabe: {row_pos!r}"
    )

    step6 = next((ln for ln in text.splitlines() if ln.startswith("6. ")), None)
    assert step6 is not None, "Schritt 6 nicht gefunden"
    missing = [w for w in F007_WORDS if not re.search(rf"\b{w}\b", step6)]
    assert not missing, f"Schritt 6 nennt nicht: {missing} — {step6!r}"


# --------------------------------------------------------------------------
# AC-12: bestehende Freigabe-Tests bleiben gruen
# --------------------------------------------------------------------------

def test_bestehende_freigabe_tests_bleiben_gruen():
    """AC-12: die vier bestehenden Testdateien laufen gruen (ohne diese Datei)."""
    files = [
        "tests/test_phase_listener_go_discussion_170.py",
        "tests/test_phase_listener_restrictions_277.py",
        "tests/test_phase_listener_keyword_guard.py",
        "tests/test_phase_listener_dropped_approval_90.py",
    ]
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *files],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert res.returncode == 0, (
        f"Bestehende Freigabe-Tests sind rot:\n{res.stdout[-4000:]}\n{res.stderr[-2000:]}"
    )


# --------------------------------------------------------------------------
# AC-13: bash_gate.py-Kommentar ohne feste Phrasen
# --------------------------------------------------------------------------

def test_bash_gate_kommentar_nennt_keine_festen_phrasen():
    """AC-13 (F008): Kommentarblock um 'legitime Erzeuger' verweist auf die
    konfigurierten Freigabe-Phrasen statt fest "go"/"freigabe"/"approved"."""
    lines = BASH_GATE.read_text().splitlines()
    idx = next((i for i, ln in enumerate(lines) if "legitime Erzeuger" in ln), None)
    assert idx is not None, "Kommentar 'legitime Erzeuger' in bash_gate.py nicht gefunden"
    start = idx
    while start > 0 and lines[start - 1].lstrip().startswith("#"):
        start -= 1
    end = idx
    while end + 1 < len(lines) and lines[end + 1].lstrip().startswith("#"):
        end += 1
    block = "\n".join(lines[start:end + 1])
    assert '"go"/"freigabe"/"approved"' not in block, (
        f'Kommentar nennt noch fest "go"/"freigabe"/"approved":\n{block}'
    )
    assert "konfigur" in block.lower(), (
        f"Kommentar verweist nicht auf die konfigurierten Freigabe-Phrasen:\n{block}"
    )
