"""TDD RED — Issue #131: Hash-Bindung statt Alters-Frist im Adversary-Dialog.

`adversary_dialog.py` band die Gültigkeit eines Dialog-Protokolls bisher an
die Datei-`mtime` (`MAX_AGE_MINUTES = 60`) — ein grober Stellvertreter für
die eigentliche Frage "wurde der geprüfte Code seither verändert?", der in
beide Richtungen irrt (siehe Issue: blockiert gültige alte Nachweise UND
winkt frisch-aber-ungeprüften Code durch). Diese Tests decken den Ersatz ab:
das Protokoll trägt SHA-256-Prüfsummen der per `Code reference:` zitierten
Dateien (`stamp`), das Gate vergleicht sie beim Validieren mit dem
Ist-Stand — unabhängig vom Alter.

Kein Mock-Theater: echte Dateien in tmp_path, echter `hashlib.sha256`, echtes
`git worktree add` für die Root-Auflösung (Stilvorlage:
test_edit_gate_outside_repo_80.py). Direkter Python-Import + Funktionsaufruf
für die Bibliotheksfunktionen (Stilvorlage: test_verdict_pipeline_77.py,
test_adversary_dialog_verdict.py — adversary_dialog.py ist ein
Content-Parsing-Modul, kein stdin-lesender Hook), ein Subprozess-Smoketest
für die neue CLI-Anbindung.
"""

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

from adversary_dialog import (  # noqa: E402
    MIN_ROUNDS,
    stamp_dialog_artifact,
    validate_dialog_artifact_ex,
)

ROUNDS = "".join(
    f"### Runde {i}\n**Adversary:** Angriff {i}\n**Implementierer:** Beweis {i}\n\n"
    for i in range(1, MIN_ROUNDS + 1)
)


def _confirmation(ac: str, ref_path, line: int) -> str:
    return (
        "Confirmation:\n"
        f"  AC: {ac}\n"
        f"  Code reference: {ref_path}:{line}\n"
        "  Status: CONFIRMED\n\n"
    )


def _artifact(tmp_path: Path, body: str, name: str = "adversary-dialog.md") -> Path:
    p = tmp_path / name
    p.write_text("# Adversary Dialog — fix-131\nSpec: docs/specs/x.md\n\n" + body)
    return p


def _git(args: list, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                    capture_output=True, text=True)


# --------------------------------------------------------------------------
# AC-6: stamp erzeugt den Hash-Block aus 'Code reference:'-Zeilen
# --------------------------------------------------------------------------

def test_stamp_writes_hash_block_from_code_references(tmp_path):
    target = tmp_path / "src" / "foo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n")

    art = _artifact(tmp_path, _confirmation("AC-1", target, 1) + ROUNDS
                     + "## Verdict\n**VERIFIED**\n")

    ok, msg = stamp_dialog_artifact(str(art))
    assert ok is True, msg

    content = art.read_text()
    assert "## Geprüfte Dateien" in content
    expected_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    assert f"sha256:{expected_hash}" in content
    assert str(target) in content


def test_stamp_dedupes_files_cited_multiple_times(tmp_path):
    target = tmp_path / "src" / "foo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n")

    body = (_confirmation("AC-1", target, 1) + _confirmation("AC-2", target, 5)
            + ROUNDS + "## Verdict\n**VERIFIED**\n")
    art = _artifact(tmp_path, body)

    ok, msg = stamp_dialog_artifact(str(art))
    assert ok is True, msg
    assert art.read_text().count("sha256:") == 1


def test_stamp_without_any_code_reference_fails_clearly(tmp_path):
    art = _artifact(tmp_path, "## Checkliste\n- [x] Punkt — Beweis: x\n\n"
                     + ROUNDS + "## Verdict\n**VERIFIED**\n")

    ok, msg = stamp_dialog_artifact(str(art))
    assert ok is False
    assert "Code reference" in msg
    assert "## Geprüfte Dateien" not in art.read_text()


# --------------------------------------------------------------------------
# AC-1/AC-4: gültiger Hash-Block bleibt gültig, unabhängig vom Datei-Alter
# --------------------------------------------------------------------------

def test_valid_hash_block_passes_regardless_of_artifact_age(tmp_path):
    target = tmp_path / "src" / "foo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n")

    art = _artifact(tmp_path, _confirmation("AC-1", target, 1) + ROUNDS
                     + "## Verdict\n**VERIFIED**\n")
    ok, msg = stamp_dialog_artifact(str(art))
    assert ok is True, msg

    # Weit ausserhalb der frueheren 60-Minuten-Grenze — die Alters-Regel
    # existiert nach diesem Fix nicht mehr, auch nicht als Zusatzpruefung.
    ancient = time.time() - 24 * 3600
    os.utime(art, (ancient, ancient))

    valid, msg, kind = validate_dialog_artifact_ex(str(art))
    assert valid is True, msg
    assert kind is None


# --------------------------------------------------------------------------
# AC-2: eine seither geaenderte/geloeschte referenzierte Datei wird erkannt
# --------------------------------------------------------------------------

def test_modified_referenced_file_is_rejected_as_format_error(tmp_path):
    target = tmp_path / "src" / "foo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n")

    art = _artifact(tmp_path, _confirmation("AC-1", target, 1) + ROUNDS
                     + "## Verdict\n**VERIFIED**\n")
    ok, msg = stamp_dialog_artifact(str(art))
    assert ok is True, msg

    target.write_text("VALUE = 2\n")  # Prüfling geändert NACH dem Stempeln

    valid, msg, kind = validate_dialog_artifact_ex(str(art))
    assert valid is False
    assert kind == "format", (
        "Ein Hash-Mismatch ist kein inhaltliches Adversary-Urteil — qa_gate "
        "darf dafuer keinen bestehenden adversary_verdict ueberschreiben."
    )
    assert "Prüfling seit dem Dialog geändert" in msg
    assert str(target) in msg


def test_deleted_referenced_file_is_rejected(tmp_path):
    target = tmp_path / "src" / "foo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n")

    art = _artifact(tmp_path, _confirmation("AC-1", target, 1) + ROUNDS
                     + "## Verdict\n**VERIFIED**\n")
    ok, msg = stamp_dialog_artifact(str(art))
    assert ok is True, msg

    target.unlink()

    valid, msg, kind = validate_dialog_artifact_ex(str(art))
    assert valid is False
    assert kind == "format"


# --------------------------------------------------------------------------
# AC-3: fehlender Hash-Block blockt — ersetzt die alte Alters-Pruefung
# --------------------------------------------------------------------------

def test_missing_hash_block_is_rejected_as_format_error(tmp_path):
    art = _artifact(tmp_path, _confirmation("AC-1", "irgendwas.py", 1) + ROUNDS
                     + "## Verdict\n**VERIFIED**\n")
    # bewusst NICHT gestempelt

    valid, msg, kind = validate_dialog_artifact_ex(str(art))
    assert valid is False
    assert kind == "format"
    assert "Re-run dialog" in msg


def test_broken_verdict_without_hash_block_still_fails_as_content(tmp_path):
    """Regressionsschutz fuer die Reihenfolge-Entscheidung: der Hash-Check
    laeuft NACH der Verdict-Klassifikation. Ein BROKEN-Verdict muss weiterhin
    mit kind='content' scheitern (dem eigentlichen Grund), nicht faelschlich
    mit 'format' wegen eines fehlenden/nicht erreichten Hash-Checks."""
    art = _artifact(tmp_path, _confirmation("AC-1", "irgendwas.py", 1) + ROUNDS
                     + "## Verdict\n**BROKEN**\n")
    # kein stamp() — BROKEN darf trotzdem korrekt als 'content' erkannt werden

    valid, msg, kind = validate_dialog_artifact_ex(str(art))
    assert valid is False
    assert kind == "content"


# --------------------------------------------------------------------------
# AC-5: bei mehreren Hash-Bloecken (Fix-Loop) zaehlt nur der LETZTE
# --------------------------------------------------------------------------

def test_only_last_hash_block_counts_across_fix_loop(tmp_path):
    target = tmp_path / "src" / "foo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n")
    real_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    stale_hash = "0" * 64

    body = (
        _confirmation("AC-1", target, 1) + ROUNDS + "## Verdict\n**BROKEN**\n"
        + f"\n## Geprüfte Dateien\n\n- sha256:{stale_hash}  {target}\n"
        + "\n" + ROUNDS + "## Verdict\n**VERIFIED**\n"
        + f"\n## Geprüfte Dateien\n\n- sha256:{real_hash}  {target}\n"
    )
    art = _artifact(tmp_path, body)

    valid, msg, kind = validate_dialog_artifact_ex(str(art))
    assert valid is True, msg


def test_stale_last_hash_block_fails_even_if_earlier_block_matches(tmp_path):
    """Spiegelfall: der ERSTE Block ist korrekt, der LETZTE nicht — es zaehlt
    weiterhin nur der letzte, das Ergebnis muss also scheitern."""
    target = tmp_path / "src" / "foo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n")
    real_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    stale_hash = "0" * 64

    body = (
        _confirmation("AC-1", target, 1) + ROUNDS + "## Verdict\n**BROKEN**\n"
        + f"\n## Geprüfte Dateien\n\n- sha256:{real_hash}  {target}\n"
        + "\n" + ROUNDS + "## Verdict\n**VERIFIED**\n"
        + f"\n## Geprüfte Dateien\n\n- sha256:{stale_hash}  {target}\n"
    )
    art = _artifact(tmp_path, body)

    valid, msg, kind = validate_dialog_artifact_ex(str(art))
    assert valid is False
    assert kind == "format"


# --------------------------------------------------------------------------
# AC-7: relative Pfade loesen gegen den WORKTREE-Root auf, nicht den
# geteilten Haupt-Repo-Root (Praezedenz #80/#96)
# --------------------------------------------------------------------------

def _make_worktree(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "main_repo"
    main.mkdir()
    _git(["init", "-b", "main"], main)
    _git(["config", "user.email", "test@example.invalid"], main)
    _git(["config", "user.name", "Test"], main)
    _git(["config", "commit.gpgsign", "false"], main)
    (main / "README.md").write_text("x\n")
    _git(["add", "-A"], main)
    _git(["commit", "-m", "init"], main)

    worktree = tmp_path / "worktrees" / "fix-131"
    _git(["worktree", "add", str(worktree), "-b", "fix-131"], main)
    return main, worktree


def test_worktree_relative_path_resolves_against_worktree_root(tmp_path, monkeypatch):
    main, worktree = _make_worktree(tmp_path)

    (main / "src").mkdir()
    (main / "src" / "foo.py").write_text("MAIN_VERSION = 1\n")
    (worktree / "src").mkdir()
    (worktree / "src" / "foo.py").write_text("WORKTREE_VERSION = 1\n")

    art = _artifact(worktree, _confirmation("AC-1", "src/foo.py", 1) + ROUNDS
                     + "## Verdict\n**VERIFIED**\n")

    monkeypatch.chdir(worktree)
    ok, msg = stamp_dialog_artifact(str(art))
    assert ok is True, msg

    expected = hashlib.sha256((worktree / "src" / "foo.py").read_bytes()).hexdigest()
    assert f"sha256:{expected}" in art.read_text(), (
        "Der Hash muss vom WORKTREE-Stand stammen, nicht vom Haupt-Repo."
    )

    # Der Haupt-Repo-Zwilling aendert sich — darf die Worktree-Validierung
    # NICHT beeinflussen (sonst wuerde faelschlich gegen den falschen Root
    # geprueft, exakt der in #96 behobene Fehlerfall).
    (main / "src" / "foo.py").write_text("MAIN_VERSION = 2\n")

    valid, msg, kind = validate_dialog_artifact_ex(str(art))
    assert valid is True, msg


def test_worktree_change_in_worktree_copy_is_detected(tmp_path, monkeypatch):
    main, worktree = _make_worktree(tmp_path)
    (worktree / "src").mkdir()
    (worktree / "src" / "foo.py").write_text("WORKTREE_VERSION = 1\n")

    art = _artifact(worktree, _confirmation("AC-1", "src/foo.py", 1) + ROUNDS
                     + "## Verdict\n**VERIFIED**\n")

    monkeypatch.chdir(worktree)
    ok, msg = stamp_dialog_artifact(str(art))
    assert ok is True, msg

    (worktree / "src" / "foo.py").write_text("WORKTREE_VERSION = 2\n")

    valid, msg, kind = validate_dialog_artifact_ex(str(art))
    assert valid is False
    assert kind == "format"
    assert "src/foo.py" in msg


# --------------------------------------------------------------------------
# CLI-Anbindung: 'stamp'-Subcommand (Smoketest fuer argv-Verdrahtung)
# --------------------------------------------------------------------------

def test_stamp_cli_subcommand_smoke(tmp_path):
    target = tmp_path / "src" / "foo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n")
    art = _artifact(tmp_path, _confirmation("AC-1", target, 1) + ROUNDS
                     + "## Verdict\n**VERIFIED**\n")

    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "adversary_dialog.py"), "stamp", str(art)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "## Geprüfte Dateien" in art.read_text()
