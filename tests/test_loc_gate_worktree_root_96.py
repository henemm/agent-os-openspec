"""Regressionstest fuer Issue #96 (LoC-Gate misst in Worktree-Sitzungen das
Hauptrepo — Limit greift dort nie, fail-open).

`edit_gate._check_loc_delta()` misst das LoC-Delta mit
`git diff HEAD --numstat` und `cwd=_root`, wobei `_root = find_project_root()`
den Git-Worktree bewusst auf den HAUPTREPO-Root aufloest. Fuer die Ablage von
Zustandsdateien (`.claude/workflows/*.json`) ist das richtig und gewollt, fuer
eine Messung am Arbeitsbaum ist es falsch: laeuft die Sitzung in einem
Worktree, misst das Gate einen anderen, in der Regel sauberen Baum. Das Delta
ist dann konstant `+0` und das Limit greift nie (gemessen henemm/gregor_zwanzig,
Worktree `intake-1555`: 764 hinzugefuegte Testzeilen bei Grenze 500, gemeldet
wurde `+0`, kein einziger Schreibvorgang blockiert).

Dieselbe Wurzelaufloesung erzeugt die Gegenrichtung — Fehlalarme, wenn das Gate
aus dem Worktree fremdes Delta des Hauptrepos der eigenen Arbeit zuschreibt.
Beide Erscheinungsformen verschwinden mit derselben Korrektur.

Kein Mock-Theater: echte Git-Repos, echter `git worktree add`, echtes
`git diff`. Der Worktree-Kontext wird ueber `monkeypatch.chdir()` gesetzt,
damit `hook_utils._find_worktree_root()` real aufloest statt injiziert zu
werden.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import edit_gate  # noqa: E402

# Grenzen bewusst so gewaehlt, dass die beiden Baeume unterscheidbar sind:
# der "grosse" Baum ueberschreitet, der "kleine" bleibt klar darunter.
PROD_LIMIT = 250
TEST_LIMIT = 500
LARGE_ADDED = 600
SMALL_ADDED = 10

SCOPE_CFG = {
    "max_loc_delta": PROD_LIMIT,
    "loc_exclude_patterns": [],
    "max_test_loc_delta": TEST_LIMIT,
    "test_path_patterns": [r"(^|/)tests?/"],
}


def _git(args: list, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _append_lines(path: Path, count: int) -> None:
    """Haengt `count` Zeilen Produktivcode an eine bestehende Datei an."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for i in range(count):
            f.write(f"CONSTANT_{i} = {i}\n")


@pytest.fixture
def repo_and_worktree(tmp_path):
    """Echtes Hauptrepo mit einem daran gelinkten, echten Git-Worktree."""
    main = tmp_path / "main_repo"
    main.mkdir()
    _git(["init", "-b", "main"], main)
    _git(["config", "user.email", "test@example.invalid"], main)
    _git(["config", "user.name", "Test"], main)
    _git(["config", "commit.gpgsign", "false"], main)

    (main / "src").mkdir()
    (main / "src" / "app.py").write_text("BASE = 0\n")
    (main / "tests").mkdir()
    (main / "tests" / "test_app.py").write_text("BASE = 0\n")
    _git(["add", "-A"], main)
    _git(["commit", "-m", "init"], main)

    worktree = tmp_path / "worktrees" / "fix-96"
    _git(["worktree", "add", str(worktree), "-b", "fix-96"], main)
    return main, worktree


def _run_check(root: Path, workflow_extra: "dict | None" = None) -> "str | None":
    """Ruft `_check_loc_delta` mit `_root` = Hauptrepo auf (Produktionszustand:
    die Zustandswurzel bleibt immer das Hauptrepo)."""
    orig_root = edit_gate._root
    edit_gate._root = root
    try:
        workflow = {"name": "test-wf", "current_phase": "phase6_implement"}
        workflow.update(workflow_extra or {})
        return edit_gate._check_loc_delta({"scope_guard": dict(SCOPE_CFG)}, workflow)
    finally:
        edit_gate._root = orig_root


class TestLocDeltaMeasuresWorkingTree:
    def test_worktree_session_measures_worktree_not_main_repo(
        self, repo_and_worktree, monkeypatch
    ):
        """Kern-Regression (fail-open): der Worktree ueberschreitet die Grenze,
        das Hauptrepo bleibt klar darunter. Gemessen werden muss der Worktree —
        vor dem Fix meldete das Gate das Hauptrepo-Delta und liess durch."""
        main, worktree = repo_and_worktree
        _append_lines(worktree / "src" / "app.py", LARGE_ADDED)
        _append_lines(main / "src" / "app.py", SMALL_ADDED)

        monkeypatch.chdir(worktree)
        result = _run_check(main)

        assert result is not None, (
            f"{LARGE_ADDED} Produktivzeilen im Worktree bei Grenze {PROD_LIMIT} "
            "muessen blockieren — das Gate hat das Hauptrepo gemessen (fail-open)"
        )
        assert f"Produktiv {LARGE_ADDED}/{PROD_LIMIT}" in result, (
            f"Gemeldet werden muss das Worktree-Delta {LARGE_ADDED}, "
            f"nicht das des Hauptrepos ({SMALL_ADDED}) — Meldung war: {result!r}"
        )

    def test_worktree_session_does_not_inherit_main_repo_delta(
        self, repo_and_worktree, monkeypatch
    ):
        """Gegenrichtung (Fehlalarm): das Hauptrepo ist weit ueber der Grenze,
        der eigene Worktree sauber. Fremdes Delta darf der eigenen Arbeit nicht
        zugeschrieben werden."""
        main, worktree = repo_and_worktree
        _append_lines(main / "src" / "app.py", LARGE_ADDED)

        monkeypatch.chdir(worktree)
        result = _run_check(main)

        assert result is None, (
            "Der Worktree ist unveraendert — das Delta eines fremden Baums darf "
            f"nicht blockieren. Meldung war: {result!r}"
        )

    def test_test_code_counted_against_test_limit_in_worktree(
        self, repo_and_worktree, monkeypatch
    ):
        """Der Produktiv/Test-Split (#94) muss auch im Worktree greifen: 600
        Testzeilen liegen unter der Testgrenze 500? Nein — sie ueberschreiten
        sie, aber gegen den TEST-Zaehler, nicht den Produktiv-Zaehler."""
        main, worktree = repo_and_worktree
        _append_lines(worktree / "tests" / "test_app.py", LARGE_ADDED)

        monkeypatch.chdir(worktree)
        result = _run_check(main)

        assert result is not None
        assert f"Tests {LARGE_ADDED}/{TEST_LIMIT}" in result, (
            f"Testzeilen muessen gegen die Testgrenze zaehlen — Meldung: {result!r}"
        )
        assert "Produktiv 0/" in result, (
            f"Produktiv-Zaehler muss 0 bleiben — Meldung: {result!r}"
        )

    def test_main_repo_session_unchanged(self, repo_and_worktree, monkeypatch):
        """Rueckwaertskompatibilitaet: laeuft die Sitzung im Hauptrepo (kein
        Worktree), bleibt das Verhalten bit-identisch zum Bestand."""
        main, worktree = repo_and_worktree
        _append_lines(main / "src" / "app.py", LARGE_ADDED)
        _append_lines(worktree / "src" / "app.py", SMALL_ADDED)

        monkeypatch.chdir(main)
        result = _run_check(main)

        assert result is not None
        assert f"Produktiv {LARGE_ADDED}/{PROD_LIMIT}" in result, (
            f"Hauptrepo-Sitzung muss den Hauptrepo-Baum messen — Meldung: {result!r}"
        )

    def test_override_still_applies_in_worktree(self, repo_and_worktree, monkeypatch):
        """Die regulaere Ausnahme (`set-field loc_limit_override`) muss auch
        greifen, wenn im Worktree korrekt gemessen wird — sonst tauscht der Fix
        eine Blindstelle gegen eine Sackgasse."""
        main, worktree = repo_and_worktree
        _append_lines(worktree / "src" / "app.py", LARGE_ADDED)

        monkeypatch.chdir(worktree)
        result = _run_check(main, {"loc_limit_override": LARGE_ADDED + 100})

        assert result is None, f"Override muss durchlassen — Meldung: {result!r}"


class TestStateStaysInMainRepo:
    def test_delta_is_written_to_main_repo_state_not_worktree(
        self, repo_and_worktree, monkeypatch
    ):
        """Die zweite Haelfte der Trennung: gemessen wird im Worktree, der
        gemessene Wert wird aber weiterhin in den GETEILTEN Workflow-State im
        Hauptrepo geschrieben (dort liegen alle Workflow-JSONs)."""
        main, worktree = repo_and_worktree
        _append_lines(worktree / "src" / "app.py", SMALL_ADDED)

        wf_name = "fix-96"
        wf_dir = main / ".claude" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / f"{wf_name}.json").write_text(json.dumps({"name": wf_name}))
        # Worktree-lokale Workflow-Identitaet (resolve_active_workflow ignoriert
        # in Worktrees bewusst die eingefrorene Env-Var, Issue #58).
        (worktree / ".claude").mkdir(parents=True, exist_ok=True)
        (worktree / ".claude" / "active_workflow").write_text(wf_name)

        monkeypatch.chdir(worktree)
        result = _run_check(main)

        assert result is None, f"{SMALL_ADDED} Zeilen duerfen nicht blocken: {result!r}"

        state = json.loads((wf_dir / f"{wf_name}.json").read_text())
        assert state.get("loc_delta_current") == f"+{SMALL_ADDED}", (
            f"Gemessenes Worktree-Delta muss im Hauptrepo-State landen: {state!r}"
        )
        assert not (worktree / ".claude" / "workflows").exists(), (
            "Der Fix darf keine zweite, worktree-lokale Workflow-Ablage anlegen"
        )
