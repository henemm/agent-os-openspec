"""Das LoC-Gate misst im Worktree, liest seine Config aber aus dem Hauptrepo
(Issue #153) — die Meldung muss das sagen.

`edit_gate._check_loc_delta` misst mit `_measurement_root()` im Worktree
(Issue #96), laedt `scope_guard` aber ueber `config_loader.find_project_root()`,
das einen Worktree bewusst auf das Hauptrepo aufloest. Traegt man neue
`loc_exclude_patterns` im Worktree ein, greifen sie erst nach dem Merge.

Gemeldet aus einer Worktree-Sitzung: Das Gate blockte mit `Produktiv 1015/250`,
obwohl 890 der Zeilen abgeholte Messdaten waren und die passenden Patterns in
der `openspec.yaml` des Worktrees bereits standen. Die Meldung nannte die
Quelle nicht — der Fehler sah aus wie ein Tippfehler in der eigenen Config.

## Warum die Config NICHT worktree-first gelesen wird

`edit_gate` erlaubt in phase6 das Editieren von `openspec.yaml`. Laese das Gate
seine Grenzen aus dem Worktree, koennte eine Sitzung `max_loc_delta` im eigenen
Branch hochsetzen und weiterarbeiten — ohne Merge, ohne Review. Das ist genau
das Muster, das die Sperrmeldung des Gates selbst verbietet: den Pruefpunkt
manipulieren statt die Bedingung zu erfuellen. Die Config bleibt deshalb am
Hauptrepo; behoben wird die *Diagnose*, nicht die Fundstelle.

Getestet wird als Subprozess mit `cwd=worktree`: `config_loader.load_config()`
und `find_project_root()` sind `lru_cache`-behaftet, ein In-Process-Test wuerde
die Wurzel lesen, die ein frueher gelaufener Test zwischengespeichert hat.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
EDIT_GATE = HOOKS_DIR / "edit_gate.py"

WF_NAME = "fix-153"
PROD_LIMIT = 50
LARGE_ADDED = 400


def _git(args: list, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _config_yaml(exclude: "list[str]") -> str:
    lines = [
        "scope_guard:",
        f"  max_loc_delta: {PROD_LIMIT}",
        "  loc_exclude_patterns:",
    ]
    lines += [f"    - '{p}'" for p in exclude] or ["    []"]
    return "\n".join(lines) + "\n"


@pytest.fixture
def repo_and_worktree(tmp_path):
    main = tmp_path / "main_repo"
    main.mkdir()
    _git(["init", "-b", "main"], main)
    _git(["config", "user.email", "test@example.invalid"], main)
    _git(["config", "user.name", "Test"], main)
    _git(["config", "commit.gpgsign", "false"], main)

    (main / "src").mkdir()
    (main / "src" / "app.py").write_text("BASE = 0\n")
    (main / "Measurement").mkdir()
    (main / "Measurement" / "results.json").write_text("{}\n")
    # Hauptrepo-Config: OHNE die Messdaten-Ausnahme.
    (main / "openspec.yaml").write_text(_config_yaml([]))
    _git(["add", "-A"], main)
    _git(["commit", "-m", "init"], main)

    worktree = tmp_path / "worktrees" / WF_NAME
    _git(["worktree", "add", str(worktree), "-b", WF_NAME], main)

    wf_dir = main / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{WF_NAME}.json").write_text(json.dumps({
        "name": WF_NAME,
        "current_phase": "phase6_implement",
        "workflow_type": "feature-fast",
        "spec_file": "docs/spec.md",
        "user_approved": True,
    }))
    (worktree / ".claude").mkdir(parents=True, exist_ok=True)
    (worktree / ".claude" / "active_workflow").write_text(WF_NAME)
    return main, worktree


def _bloat(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for i in range(count):
            f.write(f"CONSTANT_{i} = {i}\n")


def _run_gate(cwd: Path, target: Path):
    """edit_gate.py als Hook, Ziel ist ein Schreibvorgang im Worktree."""
    env = dict(os.environ)
    for var in ("CLAUDE_PROJECT_DIR", "CLAUDE_TOOL_INPUT",
                "OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK"):
        env.pop(var, None)
    payload = json.dumps({
        "tool_input": {"file_path": str(target), "content": "X = 1\n"}
    })
    proc = subprocess.run(
        [sys.executable, str(EDIT_GATE)],
        cwd=str(cwd), input=payload, capture_output=True, text=True,
        timeout=60, env=env,
    )
    return proc.returncode, proc.stderr


class TestBlockMessageNamesConfigSource:
    def test_message_names_the_config_file_actually_used(self, repo_and_worktree):
        """Kern-Regression: blockt das Gate, muss die Meldung sagen, AUS WELCHER
        Datei die Grenzen stammen. Ohne das sieht ein wirkungsloser Eintrag im
        Worktree wie ein eigener Tippfehler aus."""
        main, worktree = repo_and_worktree
        _bloat(worktree / "Measurement" / "results.json", LARGE_ADDED)

        rc, stderr = _run_gate(worktree, worktree / "src" / "app.py")

        assert rc == 2, f"{LARGE_ADDED} Zeilen bei Grenze {PROD_LIMIT} muessen blocken: {stderr!r}"
        assert str(main / "openspec.yaml") in stderr, (
            "Die Meldung muss die tatsaechlich benutzte Config-Datei nennen — "
            f"war: {stderr!r}"
        )

    def test_message_warns_when_worktree_config_differs(self, repo_and_worktree):
        """Der Fundfall: im Worktree stehen die Patterns bereits, wirksam ist
        aber die Fassung des Hauptrepos. Das muss ausdruecklich dastehen."""
        main, worktree = repo_and_worktree
        (worktree / "openspec.yaml").write_text(_config_yaml([r"^Measurement/"]))
        _bloat(worktree / "Measurement" / "results.json", LARGE_ADDED)

        rc, stderr = _run_gate(worktree, worktree / "src" / "app.py")

        assert rc == 2
        assert str(worktree / "openspec.yaml") in stderr, (
            f"Die abweichende Worktree-Config muss genannt werden: {stderr!r}"
        )
        assert "abweich" in stderr.lower() or "wirksam" in stderr.lower(), (
            f"Die Meldung muss den Unterschied benennen, nicht nur Pfade: {stderr!r}"
        )

    def test_identical_worktree_config_produces_no_warning(self, repo_and_worktree):
        """Gegenprobe: ist die Worktree-Config byte-gleich, darf KEIN Hinweis
        erscheinen — sonst wird die Meldung zu Hintergrundrauschen."""
        main, worktree = repo_and_worktree
        _bloat(worktree / "Measurement" / "results.json", LARGE_ADDED)

        rc, stderr = _run_gate(worktree, worktree / "src" / "app.py")

        assert rc == 2
        assert "abweich" not in stderr.lower(), (
            f"Unveraenderte Config darf keinen Abweichungs-Hinweis ausloesen: {stderr!r}"
        )

    def test_main_repo_session_names_its_own_config(self, repo_and_worktree):
        """Sitzung im Hauptrepo: eine Quelle, kein Abweichungs-Hinweis."""
        main, _worktree = repo_and_worktree
        (main / ".claude" / "active_workflow").write_text(WF_NAME)
        _bloat(main / "Measurement" / "results.json", LARGE_ADDED)

        rc, stderr = _run_gate(main, main / "src" / "app.py")

        assert rc == 2
        assert str(main / "openspec.yaml") in stderr
        assert "abweich" not in stderr.lower(), (
            f"Ohne Worktree gibt es nichts abzuweichen: {stderr!r}"
        )

    def test_no_crash_when_worktree_has_no_config_file(self, repo_and_worktree):
        """`CONFIG_NAMES` kennt mehrere Orte; fehlt die Datei im Worktree, darf
        die Meldung nicht in einen Fehler laufen."""
        main, worktree = repo_and_worktree
        (worktree / "openspec.yaml").unlink()
        _bloat(worktree / "Measurement" / "results.json", LARGE_ADDED)

        rc, stderr = _run_gate(worktree, worktree / "src" / "app.py")

        assert rc == 2, f"Gate muss weiterhin sauber blocken: {stderr!r}"
        assert "Traceback" not in stderr, f"Kein Absturz erlaubt: {stderr!r}"


class TestConfigAuthorityStaysAtMainRepo:
    def test_worktree_config_cannot_raise_the_limit(self, repo_and_worktree):
        """Die bewusste Nicht-Aenderung: eine im Worktree hochgesetzte Grenze
        darf NICHT greifen. Sonst koennte eine Sitzung ihr eigenes Gate
        oeffnen, ohne Merge und ohne Review."""
        main, worktree = repo_and_worktree
        (worktree / "openspec.yaml").write_text(
            "scope_guard:\n  max_loc_delta: 99999\n  loc_exclude_patterns: []\n"
        )
        _bloat(worktree / "src" / "app.py", LARGE_ADDED)

        rc, stderr = _run_gate(worktree, worktree / "src" / "app.py")

        assert rc == 2, (
            "Eine im eigenen Worktree hochgesetzte Grenze darf das Gate nicht "
            f"oeffnen — rc={rc}, stderr={stderr!r}"
        )
        assert f"/{PROD_LIMIT}" in stderr, (
            f"Wirksam bleibt die Grenze des Hauptrepos ({PROD_LIMIT}): {stderr!r}"
        )
