"""Issue #289: Aufsetzen auf main entwertet den Adversary-Nachweis nicht mehr.

Der Stempel haelt zusaetzlich die Basis (merge-base origin/main) und einen
Fingerabdruck der eigenen Aenderung fest. Eine Hash-Abweichung gilt nur dann als
unschaedlich, wenn main die Datei zwischen alter und neuer Basis geaendert hat
und die eigene Aenderung (samt 3 Kontextzeilen) gleich geblieben ist.
Alles andere blockt wie bisher.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

import adversary_dialog  # noqa: E402
from adversary_dialog import MIN_ROUNDS, stamp_dialog_artifact, validate_dialog_artifact_ex  # noqa: E402

ROUNDS = "".join(
    f"### Runde {i}\n**Adversary:** Angriff {i}\n**Implementierer:** Beweis {i}\n\n"
    for i in range(1, MIN_ROUNDS + 1)
)
LINES = [f"line_{i} = {i}" for i in range(1, 41)]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(repo), check=True,
                          capture_output=True, text=True).stdout.strip()


def _write(repo: Path, lines: list) -> None:
    (repo / "gate.py").write_text("\n".join(lines) + "\n")


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "T")
    _git(r, "config", "commit.gpgsign", "false")
    _write(r, LINES)
    base = _commit(r, "base")
    _git(r, "update-ref", "refs/remotes/origin/main", base)
    _git(r, "checkout", "-q", "-b", "feature")
    own = list(LINES)
    own[29] = "line_30 = 'eigene Aenderung'"
    _write(r, own)
    _commit(r, "own change")
    monkeypatch.setattr(adversary_dialog, "_hash_root", lambda: r)
    monkeypatch.chdir(r)
    return r


def _stamped_artifact(repo: Path) -> Path:
    art = repo / "dialog.md"
    art.write_text(
        "# Adversary Dialog\nSpec: docs/specs/x.md\n\n"
        "Confirmation:\n  AC: AC-1\n  Code reference: gate.py:30\n  Status: CONFIRMED\n\n"
        + ROUNDS + "## Verdict\n**VERIFIED**\n")
    ok, msg = stamp_dialog_artifact(str(art))
    assert ok, msg
    assert "## Prüfbasis" in art.read_text()
    return art


def _advance_main(repo: Path, change) -> None:
    """main bekommt einen Commit, der Zweig setzt per Rebase darauf auf."""
    _git(repo, "checkout", "-q", "main")
    lines = list(LINES)
    change(lines)
    _write(repo, lines)
    new_main = _commit(repo, "upstream")
    _git(repo, "update-ref", "refs/remotes/origin/main", new_main)
    _git(repo, "checkout", "-q", "feature")
    _git(repo, "rebase", "-q", "main")


def _valid(art: Path):
    ok, msg = validate_dialog_artifact_ex(str(art))[:2]
    return ok, msg


def test_upstream_change_far_away_keeps_evidence(repo):
    art = _stamped_artifact(repo)
    _advance_main(repo, lambda ls: ls.__setitem__(2, "line_3 = 'upstream'"))
    ok, msg = _valid(art)
    assert ok, msg


def test_upstream_insertion_shifting_lines_keeps_evidence(repo):
    art = _stamped_artifact(repo)
    _advance_main(repo, lambda ls: ls.insert(0, "# neuer Kopf\n# zweite Zeile"))
    ok, msg = _valid(art)
    assert ok, msg


def test_own_rework_after_stamp_still_blocks(repo):
    """Gegenprobe: Basis unveraendert, Datei geaendert -> Nacharbeit, blockt."""
    art = _stamped_artifact(repo)
    text = (repo / "gate.py").read_text().replace("line_10 = 10", "line_10 = 'heimlich'")
    (repo / "gate.py").write_text(text)
    ok, msg = _valid(art)
    assert not ok and "gate.py" in msg


def test_rework_on_top_of_rebase_still_blocks(repo):
    """Gegenprobe: aufgesetzt UND eigene Aenderung nachtraeglich veraendert."""
    art = _stamped_artifact(repo)
    _advance_main(repo, lambda ls: ls.__setitem__(2, "line_3 = 'upstream'"))
    text = (repo / "gate.py").read_text().replace("eigene Aenderung", "andere Aenderung")
    (repo / "gate.py").write_text(text)
    ok, msg = _valid(art)
    assert not ok


def test_extra_change_elsewhere_after_rebase_blocks(repo):
    """Gegenprobe: zusaetzliche eigene Zeile fern der gestempelten Aenderung."""
    art = _stamped_artifact(repo)
    _advance_main(repo, lambda ls: ls.__setitem__(2, "line_3 = 'upstream'"))
    text = (repo / "gate.py").read_text().replace("line_15 = 15", "line_15 = 'neu'")
    (repo / "gate.py").write_text(text)
    ok, _ = _valid(art)
    assert not ok


def test_upstream_change_next_to_own_change_requires_new_dialog(repo):
    """Konservativ: main aendert eine Kontextzeile -> neuer Dialog noetig."""
    art = _stamped_artifact(repo)
    _advance_main(repo, lambda ls: ls.__setitem__(31, "line_32 = 'upstream nah'"))
    ok, _ = _valid(art)
    assert not ok


def test_rebase_without_upstream_change_to_file_does_not_mask_rework(repo):
    """main aendert eine ANDERE Datei; Abweichung in gate.py ist eigene Nacharbeit."""
    art = _stamped_artifact(repo)
    _git(repo, "checkout", "-q", "main")
    (repo / "other.txt").write_text("x\n")
    new_main = _commit(repo, "other")
    _git(repo, "update-ref", "refs/remotes/origin/main", new_main)
    _git(repo, "checkout", "-q", "feature")
    _git(repo, "rebase", "-q", "main")
    text = (repo / "gate.py").read_text().replace("line_10 = 10", "line_10 = 'heimlich'")
    (repo / "gate.py").write_text(text)
    ok, _ = _valid(art)
    assert not ok


def test_tampered_review_base_block_is_ignored_if_before_hash_block(repo):
    """Nur ein Pruefbasis-Block HINTER dem letzten Hash-Block zaehlt."""
    art = _stamped_artifact(repo)
    content = art.read_text()
    head, _, rest = content.partition("## Geprüfte Dateien")
    hashes, _, base_block = rest.partition("## Prüfbasis")
    art.write_text(head + "## Prüfbasis" + base_block + "\n## Geprüfte Dateien" + hashes)
    _advance_main(repo, lambda ls: ls.__setitem__(2, "line_3 = 'upstream'"))
    ok, _ = _valid(art)
    assert not ok


def test_stamp_without_origin_main_has_no_review_base(repo):
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    art = repo / "dialog.md"
    art.write_text("Confirmation:\n  AC: AC-1\n  Code reference: gate.py:30\n"
                   "  Status: CONFIRMED\n\n" + ROUNDS + "## Verdict\n**VERIFIED**\n")
    ok, msg = stamp_dialog_artifact(str(art))
    assert ok, msg
    assert "## Prüfbasis" not in art.read_text()
