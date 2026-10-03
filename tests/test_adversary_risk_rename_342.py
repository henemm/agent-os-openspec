"""#342 Nachtrag: Renames duerfen Hochrisiko-Pfade nicht verschleiern.

`git diff --name-only` meldet bei einem Rename nur den neuen Pfad; der
verschwundene Hochrisiko-Pfad (z. B. core/hooks/x.py) bliebe unsichtbar.
Die Helfer stammen aus dem eingefrorenen tests/test_adversary_risk_342.py.
"""
from test_adversary_risk_342 import (
    _assert_high, _assert_low, _git, _make_repo, _py_json, _report, _write,
)


def _move(repo, old, new, commit):
    _write(repo, old, "# " + old + "\n" + "ZEILE = 1\n" * 20)
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "add"], repo)
    _git(["branch", "-f", "base"], repo)
    (repo / new).parent.mkdir(parents=True, exist_ok=True)
    _git(["mv", old, new], repo)
    if commit:
        _git(["commit", "-q", "-m", "rename"], repo)


def test_committed_rename_out_of_high_risk_path_is_high(tmp_path):
    repo = _make_repo(tmp_path)
    _move(repo, "core/hooks/x.py", "docs/x.md", commit=True)
    _assert_high(_report(repo), "committeter Rename core/hooks/x.py -> docs/x.md")


def test_staged_rename_out_of_high_risk_path_is_high(tmp_path):
    repo = _make_repo(tmp_path)
    _move(repo, "core/hooks/x.py", "docs/x.md", commit=False)
    _assert_high(_report(repo), "gestagter Rename")


def test_rename_between_low_risk_paths_stays_low(tmp_path):
    repo = _make_repo(tmp_path)
    _move(repo, "docs/a.md", "docs/b.md", commit=True)
    _assert_low(_report(repo), "Rename docs/a.md -> docs/b.md")


def test_observable_files_contains_both_rename_paths(tmp_path):
    repo = _make_repo(tmp_path)
    _move(repo, "core/hooks/x.py", "docs/x.md", commit=True)
    base = _git(["rev-parse", "base"], repo)
    res = _py_json(repo, "import hook_utils\nfrom pathlib import Path\n"
                         f"f, e = hook_utils._observable_files(Path.cwd(), {base!r})\n"
                         "print(json.dumps([f, e]))")
    files, err = res
    assert err == "" and "core/hooks/x.py" in files and "docs/x.md" in files, res
