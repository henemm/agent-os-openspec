"""Regressionstest für Issue #1478 Teil 1 (RED-Artefakt-Suche trifft Hauptrepo
statt Worktree).

`tdd_enforcement._validate_artifact()` löste einen relativen Artefakt-Pfad
bislang ausschließlich gegen `find_project_root()` auf -- die resolviert
Git-Worktrees bewusst auf den Hauptrepo-Root (richtig für geteilten
Workflow-State unter `.claude/workflows/`). `docs/artifacts/` ist aber
gitignored und wird zwischen Worktree und Hauptrepo NICHT geteilt: ein
frisch geschriebenes RED-Test-Artefakt liegt physisch nur im Worktree, das
Gate suchte es aber im Hauptrepo und meldete fälschlich "Artefakt-Datei
nicht gefunden" (gemessen henemm/gregor_zwanzig#1478, Workflow
fix-1196-s1-testnetz-entrauschen und mehrfach danach).

Kein Mock-Theater: echte Dateien auf echtem `tmp_path`, nur die
Kontext-Auflösungsfunktion `hook_utils._find_worktree_root` wird injiziert
(identisches Muster wie tests/test_workflow_resolution_consolidation.py).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import hook_utils  # noqa: E402
import tdd_enforcement  # noqa: E402


def _make_artifact_entry(path_str: str) -> dict:
    return {
        "type": "test_output",
        "path": path_str,
        "description": "16 Tests FAILED wie erwartet -- Formel noch nicht korrigiert",
    }


def _write_fresh_artifact(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class TestArtifactResolvesAgainstWorktreeFirst:
    def test_relative_artifact_found_in_worktree_not_only_main_repo(self, tmp_path, monkeypatch):
        """Kern-Regression: Artefakt existiert NUR im Worktree, `project_root`
        (Hauptrepo) kennt die Datei nicht -- Validierung muss trotzdem
        durchgehen, nicht mit 'nicht gefunden' scheitern."""
        main_repo = tmp_path / "main_repo"
        worktree = tmp_path / "worktrees" / "fix-1478-teil1"
        main_repo.mkdir(parents=True)
        worktree.mkdir(parents=True)

        rel_path = "docs/artifacts/fix-1478-teil1/test-red-output.txt"
        content = "FAILED tests/test_x.py::test_y - AssertionError\n" + ("x" * 200)
        _write_fresh_artifact(worktree / rel_path, content)
        # Bewusst NICHT im Hauptrepo anlegen -- genau der Bug-Zustand.

        monkeypatch.setattr(hook_utils, "_find_worktree_root", lambda: worktree)

        art = _make_artifact_entry(rel_path)
        err = tdd_enforcement._validate_artifact(art, main_repo)

        assert err is None, (
            f"Artefakt liegt im Worktree, muss gefunden werden -- Fehler war: {err!r}"
        )

    def test_relative_artifact_falls_back_to_main_repo_when_absent_in_worktree(self, tmp_path, monkeypatch):
        """Rückwärtskompatibilität: liegt die Datei NICHT im Worktree, aber
        regulär im Hauptrepo (z.B. bewusst dort registriert), bleibt der
        bisherige Pfad ein gültiger Treffer."""
        main_repo = tmp_path / "main_repo"
        worktree = tmp_path / "worktrees" / "fix-1478-teil1"
        main_repo.mkdir(parents=True)
        worktree.mkdir(parents=True)

        rel_path = "docs/artifacts/fix-1478-teil1/test-red-output.txt"
        content = "FAILED tests/test_x.py::test_y - AssertionError\n" + ("x" * 200)
        _write_fresh_artifact(main_repo / rel_path, content)
        # Worktree-Pfad existiert bewusst nicht.

        monkeypatch.setattr(hook_utils, "_find_worktree_root", lambda: worktree)

        art = _make_artifact_entry(rel_path)
        err = tdd_enforcement._validate_artifact(art, main_repo)

        assert err is None, f"Hauptrepo-Fallback muss weiterhin greifen -- Fehler war: {err!r}"

    def test_missing_everywhere_still_reports_not_found(self, tmp_path, monkeypatch):
        """Regressionswächter: existiert die Datei NIRGENDS, muss die Meldung
        weiterhin erscheinen -- der Fix darf keine echten Lücken verschlucken."""
        main_repo = tmp_path / "main_repo"
        worktree = tmp_path / "worktrees" / "fix-1478-teil1"
        main_repo.mkdir(parents=True)
        worktree.mkdir(parents=True)

        monkeypatch.setattr(hook_utils, "_find_worktree_root", lambda: worktree)

        art = _make_artifact_entry("docs/artifacts/fix-1478-teil1/nie-geschrieben.txt")
        err = tdd_enforcement._validate_artifact(art, main_repo)

        assert err is not None and "nicht gefunden" in err

    def test_no_worktree_context_uses_main_repo_unchanged(self, tmp_path, monkeypatch):
        """Ausserhalb eines Worktrees (Hauptrepo-Session, `_find_worktree_root`
        liefert None) bleibt das Verhalten bit-identisch zum Bestand."""
        main_repo = tmp_path / "main_repo"
        main_repo.mkdir(parents=True)

        rel_path = "docs/artifacts/fix-1478-teil1/test-red-output.txt"
        content = "FAILED tests/test_x.py::test_y - AssertionError\n" + ("x" * 200)
        _write_fresh_artifact(main_repo / rel_path, content)

        monkeypatch.setattr(hook_utils, "_find_worktree_root", lambda: None)

        art = _make_artifact_entry(rel_path)
        err = tdd_enforcement._validate_artifact(art, main_repo)

        assert err is None
