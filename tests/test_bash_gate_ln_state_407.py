"""bash_gate: Verweise (ln/link) und Ordner-Operationen auf Zustandsdateien — #407.

Spec: docs/specs/fix-407-ln-state-integrity.md (AC-1 bis AC-9).

Muster wie #299 Teil A-C: `core/hooks/bash_gate.py` DIESES Arbeitsbaums laeuft
als echter Subprozess gegen eine Wegwerf-Sandbox in tmp_path mit aktivem
Workflow in phase6. Beide Fehlerrichtungen; Abweichungen werden je Test
gesammelt statt beim ersten Fehler abzubrechen.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASH_GATE = REPO_ROOT / "core" / "hooks" / "bash_gate.py"

WF = "sandboxwf"
WF_PATH = f".claude/workflows/{WF}.json"
STATE_MSG = "Direct state file manipulation"


# --------------------------------------------------------------------- #
# Sandbox + Gate-Aufruf (kopiert aus tests/test_bash_gate_erkennung_299.py)
# --------------------------------------------------------------------- #

def _sandbox(tmp_path: Path) -> Path:
    """Projekt-Sandbox mit aktivem Workflow in phase6_implement."""
    (tmp_path / ".git").mkdir()  # kein Worktree -> Haupt-Repo-Aufloesung
    claude = tmp_path / ".claude"
    (claude / "workflows").mkdir(parents=True, exist_ok=True)
    (claude / "active_workflow").write_text(WF + "\n")
    (claude / "workflows" / f"{WF}.json").write_text(json.dumps({
        "name": WF,
        "current_phase": "phase6_implement",
        "workflow_type": "feature",
    }))
    return tmp_path


def _sandbox_ohne_workflow(tmp_path: Path) -> Path:
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    return tmp_path


def _gate(command: str, project_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for var in ("OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK"):
        env.pop(var, None)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env["CLAUDE_TOOL_INPUT"] = json.dumps({"command": command})
    return subprocess.run(
        [sys.executable, str(BASH_GATE)],
        cwd=str(project_dir), env=env, capture_output=True, text=True, timeout=60,
    )


def _expect(cases, project_dir: Path, rc: int, needle: "str | None" = None):
    """Alle Faelle pruefen, Abweichungen SAMMELN (nicht beim ersten abbrechen)."""
    wrong = []
    for cmd in cases:
        proc = _gate(cmd, project_dir)
        if proc.returncode != rc or (needle and needle not in proc.stderr):
            wrong.append(f"  {cmd!r}: rc={proc.returncode} (soll {rc}), "
                         f"stderr={proc.stderr.strip()[:160]!r}")
    return wrong


def _assert_blocked_as_state(cases, project_dir: Path, ac: str):
    wrong = _expect(cases, project_dir, 2, STATE_MSG)
    assert not wrong, (
        f"{ac}: Verweis/Ordner-Operation auf Zustand rutscht durch "
        f"({len(wrong)}/{len(cases)}):\n" + "\n".join(wrong)
    )


def _assert_allowed(cases, project_dir: Path, ac: str):
    wrong = _expect(cases, project_dir, 0)
    assert not wrong, (
        f"{ac}: harmloser Befehl wird ueber-blockiert "
        f"({len(wrong)}/{len(cases)}):\n" + "\n".join(wrong)
    )


# --------------------------------------------------------------------- #
# Blockende Faelle (AC-1 bis AC-6)
# --------------------------------------------------------------------- #

LN_QUELLE = [
    f"ln {WF_PATH} docs/x/notes.txt",
    f"ln -f {WF_PATH} docs/x/notes.txt",
    f"ln -s {WF_PATH} docs/x/notes.txt",
    f"link {WF_PATH} docs/x/notes.txt",
]
LN_ZIEL = [f"ln docs/x/notes.txt {WF_PATH}"]
LN_TOKEN_SETTINGS_HOOK = [
    "ln .claude/user_override_token.json docs/x/token.txt",
    "ln .claude/settings.json docs/x/settings.txt",
    "ln -s ../core/hooks/x.py .claude/hooks/x.py",
]
ORDNER_OPERATIONEN = [
    "mv .claude/workflows docs/w",
    "cp -r .claude/workflows docs/w",
    "cp -r docs/w .claude/workflows",
    "rsync -a docs/w/ .claude/workflows/",
    f"install docs/x {WF_PATH}",
]


def _ordner_verweise(sandbox: Path):
    abs_claude = f"{sandbox}/.claude"
    return [
        "ln -s .claude/workflows docs/w",
        "ln -s .claude docs/c",
        "ln -s ./.claude/workflows docs/w",
        "ln -s ./.claude docs/c",
        "ln -s .claude/workflows/ docs/w",
        "ln -s .claude/ docs/c",
        f"ln -s {abs_claude}/workflows docs/w",
        f"ln -s {abs_claude} docs/c",
        f"ln -s {abs_claude}/workflows/ docs/w",
    ]


def test_ln_mit_state_datei_als_quelle_blockt(tmp_path):
    """AC-1."""
    _assert_blocked_as_state(LN_QUELLE, _sandbox(tmp_path), "AC-1 State als Quelle")


def test_ln_mit_state_datei_als_ziel_blockt(tmp_path):
    """AC-2."""
    _assert_blocked_as_state(LN_ZIEL, _sandbox(tmp_path), "AC-2 State als Ziel")


def test_ln_mit_token_settings_und_hook_datei_blockt(tmp_path):
    """AC-3."""
    _assert_blocked_as_state(LN_TOKEN_SETTINGS_HOOK, _sandbox(tmp_path),
                             "AC-3 Token/Settings/Hook")


def test_ordner_verweis_auf_zustandsordner_blockt(tmp_path):
    """AC-4: auch mit ./, absolutem Pfad und abschliessendem Slash."""
    sandbox = _sandbox(tmp_path)
    _assert_blocked_as_state(_ordner_verweise(sandbox), sandbox, "AC-4 Ordner-Verweis")


def test_ordner_operationen_mv_cp_rsync_install_blocken(tmp_path):
    """AC-5."""
    _assert_blocked_as_state(ORDNER_OPERATIONEN, _sandbox(tmp_path),
                             "AC-5 Ordner-Operationen")


def test_roh_scan_fallback_erkennt_ordner_muster(tmp_path):
    """AC-6: sh -c / eval / nicht zerlegbarer Text (shlex-Fehler)."""
    _assert_blocked_as_state([
        'sh -c "ln -s .claude/workflows docs/w"',
        f'eval "ln {WF_PATH} docs/x"',
        'ln -s .claude/workflows docs/w; echo "offen',
    ], _sandbox(tmp_path), "AC-6 Roh-Scan-Fallback")


# --------------------------------------------------------------------- #
# Kontrollfaelle (AC-7 bis AC-9)
# --------------------------------------------------------------------- #

def test_harmlose_kontrollfaelle_bleiben_frei(tmp_path):
    """AC-7."""
    _assert_allowed([
        f"ls -ln {WF_PATH}",
        f"cat {WF_PATH}",
        "ln -s docs/a docs/b",
        "ln -s ../../node_modules .claude/worktrees/x/node_modules",
        "pip install x",
        "npm install",
    ], _sandbox(tmp_path), "AC-7 Kontrolle")


def test_freitext_mit_ln_und_zustandspfad_bleibt_frei(tmp_path):
    """AC-8: Inhalte von -m/--body zaehlen nicht (Freitext-Ausnahme).

    `git tag -m` statt `git commit -m`: ein Commit blockt in der Sandbox
    unabhaengig von 3b am Commit-Gate (kein Adversary-Verdict); dieselbe
    Freitext-Ausnahme (SECRETS_FREETEXT_FLAGS) gilt fuer beide.
    """
    _assert_allowed([
        f'git tag -a v1 -m "ln {WF_PATH} docs/x"',
        f'gh issue comment 1 --body "ln {WF_PATH} docs/x"',
        'gh pr create --title t --body "ln -s .claude/workflows docs/w"',
    ], _sandbox(tmp_path), "AC-8 Freitext")


def test_ohne_aktiven_workflow_unveraendert(tmp_path):
    """AC-9: dieselben Befehle ohne aktiven Workflow bleiben Exit 0."""
    sandbox = _sandbox_ohne_workflow(tmp_path)
    _assert_allowed(
        LN_QUELLE + LN_ZIEL + LN_TOKEN_SETTINGS_HOOK
        + _ordner_verweise(sandbox) + ORDNER_OPERATIONEN,
        sandbox, "AC-9 ohne Workflow",
    )
