"""Tests fuer #135 — Laufzeit-Marker gehoeren nicht in den Arbeitsbaum.

Zwei Marker-Familien fehlten im `# Runtime state (never commit)`-Block der
.gitignore: `.claude/pending_validation_*.json` und
`.claude/user_approved_validation_*`. Folge: im Framework-Repo lagen 18 solche
Dateien dauerhaft unversioniert herum, `scripts/release_check.py` scheiterte
darum bei jedem Lauf — und weil dessen Meldung auf fuenf Eintraege kuerzt,
verschwand das echte Signal ("du hast unversionierte Quelldateien") zwischen
Laufzeit-Zustand, der nichts bedeutet.

Dazu erreichte `workflow.py cleanup-stale-locks` nur Marker MIT gleichnamigem
pending-Lock; 6 von 9 Freigabe-Markern waren durch keinen Befehl entfernbar.

Die .gitignore wird gegen ein echtes git-Repo geprueft, nicht per
String-Suche: dass ein Muster in der Datei steht, belegt nicht, dass git es
auch greift (Muster aus test_release_check_93.py).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(HOOKS_DIR))

import release_check  # noqa: E402

MARKER_FILES = [
    ".claude/pending_validation_feat-1-thing.json",
    ".claude/pending_validation_fix-2-other.json",
    ".claude/user_approved_validation_feat-1-thing",
    ".claude/user_approved_validation_feat-99-orphan",
]


def _git(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), check=True,
                          capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Echtes Repo mit der .gitignore DIESES Repos — sie ist der Prueflung."""
    work = tmp_path / "work"
    work.mkdir()
    _git(["init", "-b", "main"], work)
    _git(["config", "user.email", "test@example.invalid"], work)
    _git(["config", "user.name", "Test"], work)
    _git(["config", "commit.gpgsign", "false"], work)
    (work / ".gitignore").write_text((REPO_ROOT / ".gitignore").read_text())
    (work / "README.md").write_text("# x\n")
    _git(["add", "-A"], work)
    _git(["commit", "-m", "init"], work)
    monkeypatch.setattr(release_check, "REPO_ROOT", work)
    return work


def _touch_markers(repo: Path) -> None:
    (repo / ".claude").mkdir(exist_ok=True)
    for rel in MARKER_FILES:
        p = repo / rel
        p.write_text('{"workflow": "x"}' if p.suffix == ".json" else "")


# --- AC-1 / AC-2: git sieht die Marker nicht mehr -------------------------

def test_git_does_not_report_the_markers(repo):
    _touch_markers(repo)
    out = _git(["status", "--porcelain", "--untracked-files=all"], repo).stdout
    assert out.strip() == "", f"git meldet noch Laufzeit-Marker:\n{out}"


def test_release_check_calls_the_tree_clean(repo):
    _touch_markers(repo)
    ok, message = release_check.check_clean_tree()
    assert ok, message
    assert "sauber" in message


def test_the_other_runtime_state_stays_ignored(repo):
    """Kontrolle: der bestehende Block darf beim Ergaenzen nicht kaputtgehen."""
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "active_workflow").write_text("x")
    (repo / ".claude" / "stop_lock.json").write_text("{}")
    (repo / ".claude" / "workflows").mkdir()
    (repo / ".claude" / "workflows" / "w.json").write_text("{}")
    assert _git(["status", "--porcelain", "--untracked-files=all"], repo).stdout.strip() == ""


# --- AC-3: das echte Signal bleibt sichtbar ------------------------------

def test_a_real_untracked_source_file_is_still_reported(repo):
    """Der Kern des Issues. Der Wächter darf durch die Marker nicht blind
    werden — eine unversionierte Quelldatei muss er weiter nennen, und zwar
    namentlich."""
    _touch_markers(repo)
    (repo / "core").mkdir(exist_ok=True)
    (repo / "core" / "forgotten.py").write_text("x = 1\n")
    ok, message = release_check.check_clean_tree()
    assert not ok
    assert "core/forgotten.py" in message


def test_a_modified_tracked_file_is_still_reported(repo):
    _touch_markers(repo)
    (repo / "README.md").write_text("# geaendert\n")
    ok, message = release_check.check_clean_tree()
    assert not ok
    assert "README.md" in message


# --- AC-4 / AC-5: der Aufraeum-Befehl erreicht beide Familien ------------

def _run_cleanup(project: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "workflow.py"), "cleanup-stale-locks"],
        capture_output=True, text=True, cwd=str(project),
        env={"PATH": "/usr/bin:/bin", "HOME": str(project),
             "CLAUDE_PROJECT_DIR": str(project)},
    )


@pytest.fixture
def project(tmp_path):
    """Projekt mit .git-Verzeichnis, damit find_project_root() hier landet."""
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows").mkdir(parents=True)
    return proj


def test_cleanup_removes_an_orphaned_approval_marker(project):
    """6 der 9 Marker im Framework-Repo waren genau das: eine Freigabe ohne
    gleichnamigen pending-Lock, durch keinen Befehl erreichbar."""
    orphan = project / ".claude" / "user_approved_validation_feat-63-adr-spec-gate"
    orphan.write_text("")
    res = _run_cleanup(project)
    assert res.returncode == 0, res.stdout + res.stderr
    assert not orphan.exists(), res.stdout + res.stderr


def test_cleanup_removes_a_matched_pair(project):
    lock = project / ".claude" / "pending_validation_fix-1.json"
    approval = project / ".claude" / "user_approved_validation_fix-1"
    lock.write_text("{}")
    approval.write_text("")
    _run_cleanup(project)
    assert not lock.exists()
    assert not approval.exists()


def test_cleanup_leaves_an_active_phase6_workflow_alone(project):
    """Bestehendes SKIPPED-Verhalten: eine laufende Implementierung darf ihre
    Marker nicht unter sich verlieren."""
    (project / ".claude" / "workflows" / "live.json").write_text(
        json.dumps({"name": "live", "current_phase": "phase6_implement"})
    )
    lock = project / ".claude" / "pending_validation_live.json"
    approval = project / ".claude" / "user_approved_validation_live"
    lock.write_text("{}")
    approval.write_text("")
    res = _run_cleanup(project)
    assert lock.exists(), res.stdout + res.stderr
    assert approval.exists(), res.stdout + res.stderr
    assert "SKIPPED" in res.stdout


def test_cleanup_skips_an_orphaned_approval_of_an_active_workflow(project):
    """Auch ohne pending-Lock: laeuft ein Workflow des Namens gerade in
    phase6, ist seine Freigabe kein Muell."""
    (project / ".claude" / "workflows" / "live.json").write_text(
        json.dumps({"name": "live", "current_phase": "phase6_implement"})
    )
    approval = project / ".claude" / "user_approved_validation_live"
    approval.write_text("")
    _run_cleanup(project)
    assert approval.exists()


def test_cleanup_says_so_when_there_is_nothing_to_do(project):
    res = _run_cleanup(project)
    assert res.returncode == 0
    assert "Keine verwaisten" in res.stdout
