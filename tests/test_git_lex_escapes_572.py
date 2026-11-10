"""hook_utils._git_lex zerlegt Befehle bash-gerecht (Issue #572, Epic #429).

Spec: docs/specs/fix-572-git-lex-escapes.md (AC-1 bis AC-9).

Zwei Abweichungen von bash werden hier festgehalten:

* Fortsetzungen: `\\`+Umbruch wurde blind entfernt, auch hinter einem
  maskierten Backslash (`\\\\`+Umbruch) und in `'…'`/`$'…'`. bash liest dort
  einen wörtlichen Backslash bzw. Quote-Inhalt; ein `git commit` in der
  Folgezeile verschwand für das Commit-Gate.
* Gequotete/maskierte Operatoren (`';'`, `\\;`, `'&&'`, `'>'`) wurden zu
  Trennern bzw. Umleitungen und zerrissen Schreib-Erkennungen.

Fortsetzungs-Fälle werden zusätzlich gegen echtes bash belegt (Temp-Git-Repo
bzw. `printf` als Wort-Orakel). Kein Mock von Shell oder git.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import bash_gate  # noqa: E402
import hook_utils  # noqa: E402

BS = "\\"
LF = "\n"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="bash und git werden als Orakel gebraucht",
)


# --- Hilfen -------------------------------------------------------------------

def _git_env(home: Path) -> dict:
    env = dict(os.environ)
    env.update({
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    })
    return env


def _temp_repo(tmp_path: Path) -> "tuple[Path, dict]":
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    env = _git_env(tmp_path)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
    return repo, env


def _commit_count(repo: Path, env: dict) -> int:
    r = subprocess.run(["git", "rev-list", "--all", "--count"], cwd=repo,
                       capture_output=True, text=True, env=env)
    return int(r.stdout.strip() or 0) if r.returncode == 0 else 0


def _bash_runs_commit(cmd: str, tmp_path: Path) -> bool:
    """Führt `cmd` mit echtem bash im Temp-Repo aus: entsteht ein Commit?"""
    repo, env = _temp_repo(tmp_path)
    before = _commit_count(repo, env)
    subprocess.run(["bash", "-c", cmd], cwd=repo, env=env,
                   capture_output=True, text=True, timeout=30)
    return _commit_count(repo, env) > before


def _bash_words(args: str) -> "list[str]":
    """Wörter, die bash aus `args` macht (printf als Orakel, NUL-getrennt)."""
    r = subprocess.run(["bash", "-c", "printf '%s\\0' " + args],
                       capture_output=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.decode().split("\0")[:-1]


def _placeholders() -> "set[str]":
    """Platzhalterzeichen der Vorstufe, ermittelt über `_lex_prepare` selbst.

    Alle Sonderzeichen (`_GIT_PUNCTUATION` plus `{ } !`) stehen in `'…'`; was
    nach der Aufbereitung neu im Text auftaucht, sind die Platzhalter.
    `_lex_prepare` liefert den aufbereiteten Text (oder ein Tupel mit ihm vorn).
    """
    specials = hook_utils._GIT_PUNCTUATION + "{}!"
    source = "echo '" + specials + "'"
    prepared = hook_utils._lex_prepare(source)
    if not isinstance(prepared, str):
        prepared = prepared[0]
    return {ch for ch in prepared if ch not in source}


# --- AC-1 maskierter Backslash vor Umbruch ------------------------------------

def test_escaped_backslash_before_newline_exposes_commit(tmp_path):
    cases = [
        # Folgezeile ist ein eigener Befehl: `a\\`+LF = Wort `a\`, dann Trenner
        f"git status a{BS}{BS}{LF}git commit --allow-empty -m x",
        # Issue-Repro: in "…" ist `\\` ein Paar, der Umbruch bloßer Inhalt
        f'git status "a{BS}{BS}{LF}" && git commit --allow-empty -m pwn'
        f' && git status "b{BS}{BS}{LF}"',
    ]
    wrong = []
    for i, cmd in enumerate(cases):
        assert _bash_runs_commit(cmd, tmp_path / f"c{i}"), (
            f"Orakel: bash führt den Commit nicht aus: {cmd!r}")
        if not hook_utils.is_git_subcommand(cmd, "commit"):
            wrong.append(f"commit unsichtbar: {cmd!r} -> {hook_utils._git_lex(cmd)!r}")
    assert not wrong, "\n".join(wrong)

    first = f"git status a{BS}{BS}{LF}git commit -m x"
    assert hook_utils._git_segments(first) == [
        ["git", "status", "a\\"], ["git", "commit", "-m", "x"]]


# --- AC-2 echte Fortsetzungen bleiben -----------------------------------------

def test_real_line_continuations_still_joined(tmp_path):
    assert hook_utils._git_lex(f"git {BS}{LF}commit -m x") == ["git", "commit", "-m", "x"]
    assert hook_utils._git_lex(f"gi{BS}{LF}t commit") == ["git", "commit"]
    assert hook_utils._git_lex(f"git {BS}\r{LF}commit") == ["git", "commit"]
    # `a\\\`+LF+`b`: Paar + echte Fortsetzung -> `a\b`
    for args in (f'"a{BS}{LF}b"', f"a{BS}{BS}{BS}{LF}b"):
        assert hook_utils._git_lex("echo " + args)[1:] == _bash_words(args), args
    assert hook_utils._git_lex(f'echo "a{BS}{LF}b"') == ["echo", "ab"]

    for i, cmd in enumerate([f"git {BS}{LF}commit --allow-empty -m x",
                             f"gi{BS}{LF}t commit --allow-empty -m x"]):
        assert _bash_runs_commit(cmd, tmp_path / f"c{i}"), cmd
        assert hook_utils.is_git_subcommand(cmd, "commit"), cmd


# --- AC-3 keine Fortsetzung in '…' und $'…' -----------------------------------

def test_no_continuation_inside_single_and_ansi_c_quotes():
    single = f"'a{BS}{LF}b'"
    assert hook_utils._git_lex("echo " + single) == ["echo", f"a{BS}{LF}b"]
    assert _bash_words(single) == [f"a{BS}{LF}b"]
    ansi = hook_utils._git_lex(f"echo $'a{BS}{LF}b'")
    assert ansi is not None and len(ansi) == 2, ansi
    assert f"a{BS}{LF}b" in ansi[1], ansi


# --- AC-4 gequotete Operatoren trennen nicht ----------------------------------

QUOTED_OPS = {
    "';'": ";", "'&&'": "&&", f"{BS};": ";", "'|'": "|",
    "'>'": ">", "'{'": "{", '"!"': "!",
}


def test_quoted_operators_are_not_separators_or_redirects(tmp_path):
    wrong = []
    for quoted, plain in QUOTED_OPS.items():
        segs = hook_utils._git_segments(f"cp {quoted} x")
        if segs != [["cp", plain, "x"]]:
            wrong.append(f"cp {quoted} x -> {segs!r}")
    assert hook_utils._git_segments("cp ';' x") == [["cp", ";", "x"]]

    # Schreib-Erkennung im Worktree: Ziel im Haupt-Ordner bleibt sichtbar
    main = tmp_path / "main"
    cwd = main / ".claude" / "worktrees" / "wt"
    cwd.mkdir(parents=True)
    (main / "docs").mkdir()
    target = main / "docs" / "x.md"
    control = f"cp a {target}"
    assert bash_gate._writes_main_repo(hook_utils._git_segments(control), cwd) == str(target.resolve())
    for quoted in ("';'", f"{BS};"):
        cmd = f"cp {quoted} {target}"
        hit = bash_gate._writes_main_repo(hook_utils._git_segments(cmd) or [], cwd)
        if hit != str(target.resolve()):
            wrong.append(f"_writes_main_repo übersieht Ziel: {cmd!r} -> {hit!r}")

    protected = ".claude/settings.json"
    for cmd in (f"echo '>' {protected}", f"echo ';>' {protected}", f"echo {BS}> {protected}"):
        if bash_gate._redirects_to_protected(cmd):
            wrong.append(f"gequotetes '>' als Umleitung gewertet: {cmd!r}")
    assert bash_gate._redirects_to_protected(f"echo x > {protected}")
    assert bash_gate._redirects_to_protected(f"git status;> {protected}")
    assert not wrong, "\n".join(wrong)


# --- AC-5 echte Trenner und Umleitungen unverändert ---------------------------

def test_real_separators_and_redirects_unchanged():
    quoted = getattr(hook_utils, "_QuotedWord", ())
    assert hook_utils._git_segments("cd /tmp&&git commit -m x") == [
        ["cd", "/tmp"], ["git", "commit", "-m", "x"]]
    assert hook_utils._git_lex("git status;>x") == ["git", "status", ";>", "x"]
    assert hook_utils._git_segments("git status;>x") == [["git", "status"], ["x"]]
    assert hook_utils._git_lex("git status 2>&1") == ["git", "status", "2", ">&", "1"]
    heredoc = f"cat <<EOF > out.txt{LF}hello; world{LF}EOF{LF}git status"
    assert hook_utils._git_lex(heredoc) == [
        "cat", "<<", "EOF", ">", "out.txt", LF, "hello", ";", "world", LF,
        "EOF", LF, "git", "status"]
    assert hook_utils._git_lex(f'git commit -m "a{LF}b"') == ["git", "commit", "-m", f"a{LF}b"]
    for tok in hook_utils._git_lex(f"a && b | c ; d > e{LF}f"):
        assert not isinstance(tok, quoted), tok
    assert hook_utils._is_git_separator("&&") and hook_utils._is_git_redirect(">")


# --- AC-6 Positions-Suche ------------------------------------------------------

def test_position_search_still_finds_commit():
    for cmd in ("eval git status ';' git commit -m x",
                f"find . -exec git status {BS}; -exec git commit -m x {BS};"):
        assert hook_utils.is_git_subcommand(cmd, "commit"), cmd


# --- AC-7 nicht zerlegbar -> None, Fall 3 --------------------------------------

def test_unparseable_input_returns_none_and_falls_back():
    assert hook_utils._git_lex("echo 'offen ; git commit -m x") is None
    assert hook_utils.is_git_subcommand("echo 'offen ; git commit -m x", "commit")

    placeholders = _placeholders()
    assert len(placeholders) == len(hook_utils._GIT_PUNCTUATION) + 3, placeholders
    for ph in sorted(placeholders):
        cmd = f"echo {ph}; git commit -m x"
        assert hook_utils._git_lex(cmd) is None, repr(ph)
        assert hook_utils.is_git_subcommand(cmd, "commit"), repr(ph)
        assert not hook_utils.is_git_subcommand(f"echo {ph}", "commit"), repr(ph)


# --- AC-8 $' in "…" öffnet kein Quote -----------------------------------------

def test_ansi_c_quote_opener_inside_double_quotes_is_literal():
    cmd = "echo \"$'x\" ; git commit -m y"
    assert hook_utils._git_segments(cmd) == [["echo", "$'x"], ["git", "commit", "-m", "y"]]
    assert hook_utils.is_git_subcommand(cmd, "commit")
