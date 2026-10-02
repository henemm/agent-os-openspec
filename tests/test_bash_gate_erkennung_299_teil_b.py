"""bash_gate: Erkennungsluecken schliessen — Teil B von #299 (#281, #297, #318).

Wie Teil A (tests/test_bash_gate_erkennung_299.py): echter Gate-Subprozess dieses
Arbeitsbaums, beide Fehlerrichtungen.

Produktentscheidung #297 (merge/cherry-pick/revert/am/pull): zaehlen NICHT als
Commit-Weg. Sie spielen vorhandene, bereits gepruefte Staende ein; die
Adversary-Pflicht gilt dem selbst geschriebenen Code. Das haelt den normalen
Weg (origin/main in den Zweig holen) frei. Known Limitation, siehe CHANGELOG.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bash_gate_erkennung_299 import (  # noqa: E402
    _assert_allowed, _assert_blocked_as_commit, _expect, _sandbox, _write_workflow,
)

MARKER_CMD = "touch .claude/user_approved_validation_x"


def _repo_sandbox(tmp_path: Path, **aliases: str) -> Path:
    """Sandbox mit ECHTEM git-Repo, damit die Alias-Abfrage etwas findet."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, value in aliases.items():
        subprocess.run(["git", "-C", str(tmp_path), "config", f"alias.{name}", value], check=True)
    _write_workflow(tmp_path)
    return tmp_path


# --- #281 Aliase ------------------------------------------------------------

def test_281_inline_alias_ist_ein_commit(tmp_path):
    _assert_blocked_as_commit([
        "git -c alias.ci=commit ci -m x",
        "git -c alias.ci='commit -v' ci -m x",
        "git -c alias.ci='!git commit -m y' ci",
        "cd /tmp && git -c alias.ci=commit ci -m x",
    ], tmp_path, "#281 inline")


def test_281_repo_alias_ist_ein_commit(tmp_path):
    root = _repo_sandbox(tmp_path, ci="commit", cv="commit -v", c2="ci", sh="!git commit -m y")
    wrong = _expect(["git ci -m x", "git cv -m x", "git c2 -m x", "git sh"], root, 2, "Adversary verdict")
    assert not wrong, "\n".join(wrong)


def test_281_harmlose_aliase_bleiben_erlaubt(tmp_path):
    root = _repo_sandbox(tmp_path, st="status", lg="log --oneline", ci="commit")
    _assert_allowed(["git st", "git lg -3", "git status"], root, "#281")


def test_281_ohne_repo_kein_absturz(tmp_path):
    root = _sandbox(tmp_path)  # fake .git, kein echtes Repo
    _assert_allowed(["git ci -m x", "git st"], root, "#281 fail-open")


# --- #297 --------------------------------------------------------------------

def test_297_merge_und_verwandte_sind_kein_commit(tmp_path):
    _assert_allowed([
        "git merge origin/main", "git cherry-pick abc123", "git revert HEAD",
        "git pull --ff-only", "git am x.patch",
    ], _sandbox(tmp_path), "#297 merge")


def test_297_gefaehrliche_konfiguration_ist_kein_reines_git(tmp_path):
    wrong = _expect([
        f"git -c core.pager='{MARKER_CMD}' log",
        f"git -c core.editor='{MARKER_CMD}' log",
        f"git -c diff.external='{MARKER_CMD}' diff",
        f"git rebase --exec '{MARKER_CMD}' HEAD~1",
        f"git rebase -x '{MARKER_CMD}' HEAD~1",
        f"git difftool -x '{MARKER_CMD}'",
        f"git bisect run {MARKER_CMD}",
        f"git submodule foreach '{MARKER_CMD}'",
        f"git -c alias.x='!{MARKER_CMD}' x",
    ], _sandbox(tmp_path), 2, "Freigabe")
    assert not wrong, "\n".join(wrong)


def test_297_harmloses_git_bleibt_reines_git(tmp_path):
    _assert_allowed([
        "git -c color.ui=always log -3", "git -c core.autocrlf=false status",
        "git rebase --autostash origin/main", "git bisect start", "git submodule update",
    ], _sandbox(tmp_path), "#297 harmlos")


# --- #318 Erkennung ------------------------------------------------------------

def test_318_shell_und_umleitungs_schreibweisen(tmp_path):
    _assert_blocked_as_commit([
        'bash -eo pipefail -c "git commit -m x"',
        'bash -euo pipefail -c "git commit -m x"',
        'bash -o pipefail -c "git commit -m x"',
        "git >| out commit -m x",
        'bash 2>&1 -lc "git commit -m x"',
        'bash >/dev/null -c "git commit -m x"',
        'bash -c -l "git commit -m x"',
    ], tmp_path, "#318")


def test_318_keine_skriptdatei_als_kommando(tmp_path):
    _assert_allowed(['bash script.sh -c "git commit -m x"', "bash -eo pipefail script.sh"],
                    _sandbox(tmp_path), "#318 Skriptdatei")
