"""bash_gate 5b: Rueckstand waehrend eines laufenden Merges gegen MERGE_HEAD messen (#352).

Spec: docs/specs/fix-352-349-gates.md (AC-1 bis AC-4).

Alle Tests rufen `core/hooks/bash_gate.py` als echten Subprozess gegen ein
Wegwerf-Repo mit Bare-Origin auf (Helfer aus tests/test_bash_gate_erkennung_299.py).
Der Merge wird wirklich mit `git merge --no-commit --no-ff origin/main` gestartet.
"""

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bash_gate_erkennung_299 import (  # noqa: E402
    _configure, _gate, _git, _origin_mit_klon, _write_workflow,
)


def _count(repo: Path, rng: str) -> int:
    return int(_git(["rev-list", "--count", rng], repo).stdout.strip())


def _laufender_merge(tmp_path: Path) -> Path:
    """Klon mit Rueckstand, in dem ein Merge von origin/main laeuft (MERGE_HEAD gesetzt)."""
    clone = _origin_mit_klon(tmp_path)
    _git(["commit", "-m", "lokal"], clone)  # staged.txt committen, Index frei fuer den Merge
    _git(["fetch", "origin"], clone)
    assert _count(clone, "HEAD..origin/main") > 0, "Vorbedingung: Klon muss hinter origin/main liegen"
    _git(["merge", "--no-commit", "--no-ff", "origin/main"], clone)
    assert _git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], clone, check=False).returncode == 0, (
        "Vorbedingung: MERGE_HEAD muss gesetzt sein"
    )
    return clone


def test_abschliessender_merge_commit_wird_durchgelassen(tmp_path):
    """AC-1: Merge holt origin/main vollstaendig herein -> 5b blockt nicht."""
    clone = _laufender_merge(tmp_path)
    assert _count(clone, "MERGE_HEAD..origin/main") == 0
    assert _count(clone, "HEAD..origin/main") > 0  # sonst bestuende der Test leer

    proc = _gate("git commit -m x", clone)
    assert proc.returncode == 0 and "hinter origin/main" not in proc.stderr, (
        f"AC-1 #352: abschliessender Merge-Commit wird von 5b geblockt: "
        f"rc={proc.returncode} stderr={proc.stderr!r}"
    )


def test_unvollstaendiger_merge_blockt_ohne_autostash_rat(tmp_path):
    """AC-2: origin/main ist nach Merge-Start weitergezogen -> Block mit Merge-Rat."""
    clone = _laufender_merge(tmp_path)
    seed = tmp_path / "seed"
    _configure(seed)
    _git(["pull", "--ff-only", "origin", "main"], seed)
    (seed / "c.txt").write_text("c\n")
    _git(["add", "c.txt"], seed)
    _git(["commit", "-m", "upstream2"], seed)
    _git(["push", "origin", "HEAD:main"], seed)
    _git(["fetch", "origin"], clone)
    assert _count(clone, "MERGE_HEAD..origin/main") > 0, "Vorbedingung: Merge unvollstaendig"

    proc = _gate("git commit -m x", clone)
    assert proc.returncode == 2, (
        f"AC-2 #352: unvollstaendiger Merge muss blocken: rc={proc.returncode} stderr={proc.stderr!r}"
    )
    assert "git merge origin/main" in proc.stderr, (
        f"AC-2 #352: Meldung nennt `git merge origin/main` nicht: {proc.stderr!r}"
    )
    assert "--autostash" not in proc.stderr, (
        f"AC-2 #352: Meldung raet waehrend eines Merges zu --autostash: {proc.stderr!r}"
    )


def test_ohne_merge_bleibt_rueckstand_block_unveraendert(tmp_path):
    """AC-3: kein Merge, Rueckstand -> Block wie bisher mit --autostash-Rat."""
    clone = _origin_mit_klon(tmp_path)
    assert _git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], clone, check=False).returncode != 0

    proc = _gate("git commit -m x", clone)
    assert proc.returncode == 2 and "hinter origin/main" in proc.stderr, (
        f"AC-3: Rueckstand ohne Merge wird nicht geblockt: rc={proc.returncode} stderr={proc.stderr!r}"
    )
    assert "git rebase --autostash origin/main" in proc.stderr, (
        f"AC-3: bisherige --autostash-Meldung fehlt: {proc.stderr!r}"
    )


def test_rev_parse_fehler_faellt_auf_head_zurueck(tmp_path, monkeypatch):
    """AC-4: liefert `rev-parse MERGE_HEAD` nichts Brauchbares, gilt Basis HEAD."""
    clone = _laufender_merge(tmp_path)
    real_git = shutil.which("git")
    assert real_git, "git nicht gefunden"

    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    shim = shim_dir / "git"
    shim.write_text(
        "#!/bin/bash\n"
        'is_rev_parse=0; has_merge_head=0\n'
        'for a in "$@"; do\n'
        '  [ "$a" = "rev-parse" ] && is_rev_parse=1\n'
        '  [ "$a" = "MERGE_HEAD" ] && has_merge_head=1\n'
        "done\n"
        'if [ "$is_rev_parse" = 1 ] && [ "$has_merge_head" = 1 ]; then exit 0; fi\n'
        f'exec "{real_git}" "$@"\n'
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    assert shutil.which("git") == str(shim), "Vorbedingung: Shim muss vorn im PATH stehen"

    proc = _gate("git commit -m x", clone)
    assert "Traceback" not in proc.stderr, f"AC-4: Gate stuerzt ab: {proc.stderr!r}"
    assert proc.returncode == 2 and "hinter origin/main" in proc.stderr, (
        f"AC-4: ohne verwertbares MERGE_HEAD muss Basis HEAD gelten: "
        f"rc={proc.returncode} stderr={proc.stderr!r}"
    )


def test_rev_parse_timeout_faellt_auf_head_zurueck(tmp_path, monkeypatch):
    """AC-4: `rev-parse MERGE_HEAD` laeuft in den Timeout (except-Zweig) -> Basis HEAD.

    Ein git-Stellvertreter vorn im PATH reicht alles ans echte git durch, nur
    `rev-parse ... MERGE_HEAD` schlaeft laenger als der 5s-Timeout des Gates.
    Ohne den inneren except-Zweig wuerde TimeoutExpired vom aeusseren
    `except ... pass` geschluckt -> Exit 0 statt Block; der Test waere rot.
    """
    clone = _laufender_merge(tmp_path)
    real_git = shutil.which("git")
    assert real_git, "git nicht gefunden"

    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    shim = shim_dir / "git"
    shim.write_text(
        "#!/bin/bash\n"
        'is_rev_parse=0; has_merge_head=0\n'
        'for a in "$@"; do\n'
        '  [ "$a" = "rev-parse" ] && is_rev_parse=1\n'
        '  [ "$a" = "MERGE_HEAD" ] && has_merge_head=1\n'
        "done\n"
        # exec: der vom Timeout getoetete Prozess ist sleep selbst, keine Enkel halten die Pipe
        'if [ "$is_rev_parse" = 1 ] && [ "$has_merge_head" = 1 ]; then exec sleep 7; fi\n'
        f'exec "{real_git}" "$@"\n'
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    assert shutil.which("git") == str(shim), "Vorbedingung: Shim muss vorn im PATH stehen"
    assert _count(clone, "HEAD..origin/main") > 0  # Basis HEAD muss blocken, sonst Test leer

    proc = _gate("git commit -m x", clone)
    assert "Traceback" not in proc.stderr, f"AC-4: Gate stuerzt ab: {proc.stderr!r}"
    assert proc.returncode == 2 and "hinter origin/main" in proc.stderr, (
        f"AC-4: nach Timeout von rev-parse MERGE_HEAD muss Basis HEAD gelten: "
        f"rc={proc.returncode} stderr={proc.stderr!r}"
    )
    assert "git rebase --autostash origin/main" in proc.stderr, (
        f"AC-4: Basis HEAD liefert die --autostash-Meldung: {proc.stderr!r}"
    )


def test_abschliessender_merge_im_worktree_wird_durchgelassen(tmp_path):
    """AC-1 im `git worktree add`-Worktree: MERGE_HEAD liegt worktree-lokal."""
    clone = _origin_mit_klon(tmp_path)
    _git(["commit", "-m", "lokal"], clone)
    wt = tmp_path / "wt"
    _git(["worktree", "add", "-b", "wt-zweig", str(wt), "HEAD"], clone)
    _write_workflow(wt, workflow_type="feature-fast")
    _git(["fetch", "origin"], wt)
    assert _count(wt, "HEAD..origin/main") > 0, "Vorbedingung: Worktree muss hinter origin/main liegen"
    _git(["merge", "--no-commit", "--no-ff", "origin/main"], wt)
    assert _git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], wt, check=False).returncode == 0
    assert _git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], clone, check=False).returncode != 0, (
        "Vorbedingung: MERGE_HEAD muss worktree-lokal sein, nicht im Hauptklon"
    )
    assert _count(wt, "MERGE_HEAD..origin/main") == 0

    proc = _gate("git commit -m x", wt)
    assert proc.returncode == 0 and "hinter origin/main" not in proc.stderr, (
        f"AC-1 #352 (Worktree): abschliessender Merge-Commit wird von 5b geblockt: "
        f"rc={proc.returncode} stderr={proc.stderr!r}"
    )
