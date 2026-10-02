"""bash_gate: Restluecken der State-Integrity-Pruefung — Teil C von #299 (#316, #319).

Spec: docs/specs/fix-299-bash-gate-erkennung-teil-c.md (AC-1 bis AC-6).

Wie Teil A/B: echter Gate-Subprozess dieses Arbeitsbaums gegen eine
Wegwerf-Sandbox mit aktivem Workflow in phase6, beide Fehlerrichtungen,
Abweichungen werden gesammelt statt beim ersten Fehler abzubrechen.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bash_gate_erkennung_299 import (  # noqa: E402
    HOOKS_DIR, WF, WF_PATH, _assert_allowed, _expect, _sandbox,
)

sys.path.insert(0, str(HOOKS_DIR))
import hook_utils  # noqa: E402

STATE_MSG = "Direct state file manipulation"
WF_FILE = f"{WF}.json"
MARKER = ".claude/user_approved_validation_x"


def _assert_blocked_as_state(cases, tmp_path: Path, issue: str):
    wrong = _expect(cases, _sandbox(tmp_path), 2, STATE_MSG)
    assert not wrong, (
        f"{issue}: Schreibzugriff auf den Workflow-State rutscht durch "
        f"({len(wrong)}/{len(cases)}):\n" + "\n".join(wrong)
    )


# --- AC-1 cd-Kontext ----------------------------------------------------------

def test_cd_in_state_ordner_dann_schreiben_blockt(tmp_path):
    _assert_blocked_as_state([
        f"cd .claude/workflows && echo x > {WF_FILE}",
        f"pushd .claude/workflows && sed -i s/a/b/ {WF_FILE}",
        f"cd .claude/workflows && python3 -c \"open('{WF_FILE}','w')\"",
    ], tmp_path, "AC-1 cd-Kontext")


# --- AC-2 Umleitung hinter erlaubtem Befehl -----------------------------------

def test_umleitung_hinter_erlaubtem_befehl_auf_state_blockt(tmp_path):
    _assert_blocked_as_state([
        f"git status > {WF_PATH}",
        f"git status >> {WF_PATH}",
        f"python3 .claude/hooks/workflow.py status > {WF_PATH}",
        f"git status > {MARKER}",
    ], tmp_path, "AC-2 Umleitung")


# --- AC-3 Apostroph im Kommentar ----------------------------------------------

def test_apostroph_im_kommentar_hebt_schutz_nicht_auf(tmp_path):
    _assert_blocked_as_state([
        f"git status && sed -i s/a/b/ {WF_PATH} # don't",
        f"git status && sed -i s/a/b/ {WF_PATH} # dont",
    ], tmp_path, "AC-3 Kommentar")


# --- AC-4 Kontrollfaelle --------------------------------------------------------

def test_harmlose_kontrollfaelle_bleiben_frei(tmp_path):
    _assert_allowed([
        "cd .claude/workflows",
        "cd .claude/workflows && ls",
        f"cd .claude/workflows && cat {WF_FILE}",
        "git log > out.txt",
        "git status 2>&1",
        "git status | tee out.txt",
    ], _sandbox(tmp_path), "AC-4 Kontrolle")


# --- AC-5 '#' ohne Kommentar ------------------------------------------------------

def test_hash_ohne_kommentar_bleibt_unveraendert(tmp_path):
    wrong = _expect([
        "git log --grep='#1431'",
        "echo \"it's\" > out.txt",
        "git status # don't panic",
    ], _sandbox(tmp_path), 0)

    strip = getattr(hook_utils, "_strip_shell_comments", None)
    if strip is None:
        wrong.append("  hook_utils._strip_shell_comments fehlt")
    else:
        for cmd in ["a#b", "echo $#", "echo ${#x}", "git log --grep=#1431", 'git commit -m "x # y"']:
            out = strip(cmd)
            if out != cmd:
                wrong.append(f"  {cmd!r}: veraendert zu {out!r}")
        out = strip("git status # don't")
        if "don" in out:
            wrong.append(f"  'git status # don't': Kommentar nicht entfernt ({out!r})")

    assert not wrong, "AC-5:\n" + "\n".join(wrong)


# --- AC-6 unausgewogene Quotes ----------------------------------------------------

def test_unausgewogene_quotes_bleiben_unveraendert():
    cmd = "echo 'abc # x"
    assert hook_utils._strip_shell_comments(cmd) == cmd
