"""Regressionstest für Issue #80: edit_gate blockt Schreibvorgänge außerhalb
des Projekts — Pfad-Herkunft wurde nicht geprüft.

`edit_gate.py` entschied bisher allein anhand von Dateiendung und
Workflow-Phase, ob ein Schreibvorgang erlaubt ist, ohne je zu prüfen, ob der
Zielpfad überhaupt zum Projekt gehört. Eine Wegwerf-Datei weit außerhalb des
Repos (z.B. `/home/user/.claude/jobs/<id>/tmp/paramscan/main.go`) wurde wie
geschützter Projektcode behandelt — beobachtet als irreführende
Berechtigungsanfrage an den PO für eine Datei, die beim Aufräumen der Sitzung
ohnehin gelöscht wird.

Zwei Sicherheitsanforderungen aus dem Issue selbst:
- Symlinks werden vor dem Vergleich aufgelöst (`Path.resolve()`), damit ein
  Link von außen nach innen nicht durchrutscht.
- Die bestehenden Sonderregeln für `~/.claude/` und Orchestrator-Dateien
  behalten ihren Vorrang.

Zusätzliche, im Issue nicht explizit genannte, aber notwendige Anforderung:
ein Git-Worktree kann außerhalb von `_root` (dem Hauptrepo) liegen — das ist
das *normale* `git worktree add`-Verhalten und wird bereits von
`tests/test_loc_gate_worktree_root_96.py` so nachgebildet (Worktree als
Geschwister-Verzeichnis, nicht darunter). Eine reine `_root`-Prüfung hätte
deshalb jede Worktree-Sitzung fälschlich als "außerhalb des Projekts"
eingestuft und den gesamten Schutz für sie abgeschaltet — schlimmer als der
ursprüngliche Fehlalarm. Der Fix prüft deshalb sowohl `_root` als auch
`find_worktree_root()`.

Kein Mock-Theater: echte Git-Repos, echter `git worktree add`, echte
Symlinks, Hook als Subprozess (Stilvorlage: test_edit_gate_orchestrator_files.py,
test_loc_gate_worktree_root_96.py).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"


def _git(args: list, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _run_edit_gate(file_path: str, cwd: Path, project_dir: Path,
                    extra_env: "dict | None" = None) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"file_path": file_path}})
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "edit_gate.py")],
        input=payload, capture_output=True, text=True, env=env, cwd=str(cwd),
    )


def _make_project(tmp_path: Path) -> Path:
    proj = tmp_path / "project"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude").mkdir(parents=True)
    return proj


# --------------------------------------------------------------------------
# AC-1/AC-2: der gemessene Fall — Ziel klar außerhalb vs. klar innerhalb
# --------------------------------------------------------------------------

def test_file_far_outside_project_is_allowed(tmp_path):
    """Der Vorfall aus dem Issue: eine Wegwerf-Datei weit außerhalb des Repos
    (hier: eine Code-Datei mit geschützter Endung, KEIN aktiver Workflow —
    beides würde ohne den Fix zwingend blocken)."""
    proj = _make_project(tmp_path)
    outside = tmp_path / "elsewhere" / "tmp" / "paramscan" / "main.go"
    outside.parent.mkdir(parents=True)
    outside.write_text("package main\n")

    result = _run_edit_gate(str(outside), cwd=proj, project_dir=proj)
    assert result.returncode == 0, result.stdout + result.stderr


def test_file_inside_project_without_workflow_still_blocked(tmp_path):
    """Gegenprobe: dieselbe Konstellation, aber Ziel INNERHALB des Projekts —
    das bestehende Verhalten (Block mangels Workflow) bleibt unverändert."""
    proj = _make_project(tmp_path)
    inside = proj / "src" / "main.go"
    inside.parent.mkdir(parents=True)
    inside.write_text("package main\n")

    result = _run_edit_gate(str(inside), cwd=proj, project_dir=proj)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "No active workflow" in result.stderr


# --------------------------------------------------------------------------
# AC-3: Worktree außerhalb von _root bleibt vollständig geschützt
# --------------------------------------------------------------------------

def test_worktree_outside_root_is_not_exempted(tmp_path):
    """Ein echter Git-Worktree als Geschwister-Verzeichnis des Hauptrepos
    (Standard-git-Verhalten) darf NICHT durch die neue Pruefung freigegeben
    werden — sonst waere jede Worktree-Sitzung ungeschuetzt."""
    main = tmp_path / "main_repo"
    main.mkdir()
    _git(["init", "-b", "main"], main)
    _git(["config", "user.email", "test@example.invalid"], main)
    _git(["config", "user.name", "Test"], main)
    _git(["config", "commit.gpgsign", "false"], main)
    (main / "README.md").write_text("x\n")
    _git(["add", "-A"], main)
    _git(["commit", "-m", "init"], main)

    worktree = tmp_path / "worktrees" / "fix-80"
    _git(["worktree", "add", str(worktree), "-b", "fix-80"], main)

    target = worktree / "src" / "main.go"
    target.parent.mkdir(parents=True)
    target.write_text("package main\n")

    # CLAUDE_PROJECT_DIR zeigt bewusst weiter auf das Hauptrepo (Produktionszustand:
    # die Zustandswurzel bleibt immer das Hauptrepo) — find_worktree_root() muss
    # den Worktree ueber cwd selbst erkennen.
    result = _run_edit_gate(str(target), cwd=worktree, project_dir=main)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "No active workflow" in result.stderr


def test_relative_path_inside_worktree_is_not_exempted(tmp_path):
    """Relativer Pfad (kein Tool liefert immer absolute Pfade) innerhalb des
    Worktrees muss ebenfalls als 'innerhalb' erkannt werden."""
    main = tmp_path / "main_repo"
    main.mkdir()
    _git(["init", "-b", "main"], main)
    _git(["config", "user.email", "test@example.invalid"], main)
    _git(["config", "user.name", "Test"], main)
    _git(["config", "commit.gpgsign", "false"], main)
    (main / "README.md").write_text("x\n")
    _git(["add", "-A"], main)
    _git(["commit", "-m", "init"], main)

    worktree = tmp_path / "worktrees" / "fix-80b"
    _git(["worktree", "add", str(worktree), "-b", "fix-80b"], main)
    (worktree / "src").mkdir()
    (worktree / "src" / "main.go").write_text("package main\n")

    result = _run_edit_gate("src/main.go", cwd=worktree, project_dir=main)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "No active workflow" in result.stderr


# --------------------------------------------------------------------------
# AC-4: Symlink von außen nach innen rutscht nicht durch
# --------------------------------------------------------------------------

def test_symlink_from_outside_to_inside_target_is_not_exempted(tmp_path):
    """Ein Symlink LIEGT ausserhalb des Projekts, ZEIGT aber auf eine Datei
    INNERHALB — Path.resolve() muss dem Link folgen, sonst waere das ein
    Bypass fuer den echten Schutz."""
    proj = _make_project(tmp_path)
    real_target = proj / "src" / "secret_logic.py"
    real_target.parent.mkdir(parents=True)
    real_target.write_text("SECRET = 1\n")

    outside_link = tmp_path / "outside_link.py"
    outside_link.symlink_to(real_target)

    result = _run_edit_gate(str(outside_link), cwd=proj, project_dir=proj)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "No active workflow" in result.stderr


# --------------------------------------------------------------------------
# AC-5: bestehende Sonderregeln behalten ihren Vorrang
# --------------------------------------------------------------------------

def test_orchestrator_file_outside_project_still_blocked(tmp_path):
    """Ein Orchestrator-Dateiname (.claude/settings.json) ausserhalb des
    Projekts UND ausserhalb von ~/.claude/ muss weiterhin blocken — Schritt 1b
    laeuft vor der neuen Herkunftspruefung."""
    proj = _make_project(tmp_path)
    fake_home = tmp_path / "fakehome"
    (fake_home / ".claude").mkdir(parents=True)

    outside = tmp_path / "elsewhere" / ".claude" / "settings.json"
    outside.parent.mkdir(parents=True)
    outside.write_text("{}\n")

    result = _run_edit_gate(str(outside), cwd=proj, project_dir=proj,
                             extra_env={"HOME": str(fake_home)})
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Orchestrator" in result.stderr


def test_protected_state_file_outside_project_still_blocked(tmp_path):
    """PROTECTED_STATE_FILES (.claude/workflows/) ausserhalb des Projekts
    muss weiterhin blocken — Schritt 1 laeuft vor der neuen Pruefung."""
    proj = _make_project(tmp_path)
    outside = tmp_path / "elsewhere" / ".claude" / "workflows" / "foo.json"
    outside.parent.mkdir(parents=True)
    outside.write_text("{}\n")

    result = _run_edit_gate(str(outside), cwd=proj, project_dir=proj)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Protected state file" in result.stderr


def test_home_claude_settings_still_exempted(tmp_path):
    """Gegenprobe zur Gegenprobe: die bestehende ~/.claude/-Ausnahme (#48)
    bleibt unveraendert funktionsfaehig, unabhaengig von der neuen Pruefung."""
    proj = _make_project(tmp_path)
    fake_home = tmp_path / "fakehome"
    global_settings = fake_home / ".claude" / "settings.json"
    global_settings.parent.mkdir(parents=True)
    global_settings.write_text("{}\n")

    result = _run_edit_gate(str(global_settings), cwd=proj, project_dir=proj,
                             extra_env={"HOME": str(fake_home)})
    assert result.returncode == 0, result.stdout + result.stderr
