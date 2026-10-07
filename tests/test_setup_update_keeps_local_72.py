"""`setup.py --update` darf lokale Anpassungen nicht still ueberschreiben (#72).

In gregor_zwanzig entfernte ein Update zwei bewusst ergaenzte Abschnitte aus
Agent-Dateien: `update_project` ersetzte jede Datei, deren Inhalt von der
Framework-Fassung abwich. Jetzt merkt sich `.claude/framework_manifest.json`,
was das Framework zuletzt geschrieben hat. Eine davon abweichende Datei ist
lokal geaendert und bleibt stehen; die neue Fassung landet als `<name>.new`
daneben, und das Update meldet es laut.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import setup as setup_py  # noqa: E402

AGENT = ".claude/agents/implementation-validator.md"
MODULE_AGENT = ".claude/agents/localizer.md"   # nur in modules/ios-swiftui
LOCAL = "\n## Authenticated Requests\nProjekt-eigener Abschnitt.\n"


def _install(project: Path, *modules: str) -> None:
    args = [sys.executable, str(REPO_ROOT / "setup.py"), str(project)]
    for module in modules:
        args += ["--module", module]
    r = subprocess.run(args, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _manifest(project: Path) -> dict:
    return json.loads((project / setup_py.MANIFEST_REL).read_text())["files"]


def _framework_moved_on(project: Path, rel: str) -> None:
    """Simuliert eine neuere Framework-Fassung: das Manifest zeigt auf einen alten Stand."""
    path = project / setup_py.MANIFEST_REL
    m = json.loads(path.read_text())
    m["files"][rel] = setup_py._sha256(b"aeltere Framework-Fassung")
    path.write_text(json.dumps(m))


def _framework_agent() -> bytes:
    return (REPO_ROOT / "core" / "agents" / "implementation-validator.md").read_bytes()


@pytest.fixture
def project(tmp_path):
    _install(tmp_path)
    return tmp_path


def test_fresh_install_writes_manifest(project):
    files = _manifest(project)
    assert AGENT in files
    assert ".claude/hooks/edit_gate.py" in files
    assert ".claude/commands/50-implement.md" in files


def test_locally_changed_agent_is_kept_and_reported(project, capsys):
    agent = project / AGENT
    agent.write_text(agent.read_text() + LOCAL)
    _framework_moved_on(project, AGENT)
    setup_py.update_project(project, [])
    out = capsys.readouterr().out
    assert LOCAL in agent.read_text()
    assert (project / (AGENT + ".new")).read_bytes() == _framework_agent()
    assert "LOKAL GEAENDERT" in out and AGENT in out


def test_untouched_agent_is_updated(project):
    """Datei entspricht der zuletzt vom Framework geschriebenen Fassung."""
    agent = project / AGENT
    old_framework = agent.read_text().replace("Adversary", "Gegenspieler", 1)
    agent.write_text(old_framework)
    m = json.loads((project / setup_py.MANIFEST_REL).read_text())
    m["files"][AGENT] = setup_py._sha256(old_framework.encode())
    (project / setup_py.MANIFEST_REL).write_text(json.dumps(m))
    setup_py.update_project(project, [])
    assert agent.read_bytes() == _framework_agent()
    assert not (project / (AGENT + ".new")).exists()


def test_install_without_manifest_backs_up_before_overwrite(project, capsys):
    (project / setup_py.MANIFEST_REL).unlink()
    agent = project / AGENT
    agent.write_text(agent.read_text() + LOCAL)
    setup_py.update_project(project, [])
    out = capsys.readouterr().out
    assert agent.read_bytes() == _framework_agent()
    backups = list((project / setup_py.BACKUP_DIR_REL).rglob("implementation-validator.md"))
    assert len(backups) == 1 and LOCAL in backups[0].read_text()
    assert "GESICHERT" in out
    assert AGENT in _manifest(project)


def test_force_overwrites_local_change(project):
    agent = project / AGENT
    agent.write_text(agent.read_text() + LOCAL)
    setup_py.update_project(project, [], force=True)
    assert agent.read_bytes() == _framework_agent()
    assert not (project / (AGENT + ".new")).exists()


def test_local_change_survives_repeated_updates(project):
    agent = project / AGENT
    agent.write_text(agent.read_text() + LOCAL)
    setup_py.update_project(project, [])
    setup_py.update_project(project, [])
    assert LOCAL in agent.read_text()


def test_merged_conflict_cleans_up_new_file(project):
    agent = project / AGENT
    agent.write_text(agent.read_text() + LOCAL)
    _framework_moved_on(project, AGENT)
    setup_py.update_project(project, [])
    agent.write_bytes(_framework_agent())  # Nutzer uebernimmt die neue Fassung
    setup_py.update_project(project, [])
    assert not (project / (AGENT + ".new")).exists()


def test_locally_changed_module_agent_is_kept(tmp_path):
    _install(tmp_path, "ios-swiftui")
    agent = tmp_path / MODULE_AGENT
    assert MODULE_AGENT in _manifest(tmp_path)
    agent.write_text(agent.read_text() + LOCAL)
    _framework_moved_on(tmp_path, MODULE_AGENT)
    setup_py.update_project(tmp_path, ["ios-swiftui"])
    assert LOCAL in agent.read_text()
    assert (tmp_path / (MODULE_AGENT + ".new")).exists()


def test_locally_changed_command_is_kept(project):
    cmd = project / ".claude/commands/50-implement.md"
    cmd.write_text(cmd.read_text() + LOCAL)
    _framework_moved_on(project, ".claude/commands/50-implement.md")
    setup_py.update_project(project, [])
    assert LOCAL in cmd.read_text()
    assert (project / ".claude/commands/50-implement.md.new").exists()


def test_no_repeat_warning_after_merge(project, capsys):
    """Adversary #72: nach dem Zusammenfuehren kein `.new` und keine Warnung mehr."""
    agent = project / AGENT
    agent.write_text(agent.read_text() + LOCAL)
    _framework_moved_on(project, AGENT)
    setup_py.update_project(project, [])
    (project / (AGENT + ".new")).unlink()   # Nutzer hat zusammengefuehrt
    capsys.readouterr()
    setup_py.update_project(project, [])
    out = capsys.readouterr().out
    assert LOCAL in agent.read_text()
    assert not (project / (AGENT + ".new")).exists()
    assert "LOKAL GEAENDERT" not in out


def test_local_change_without_framework_change_is_silent(project, capsys):
    agent = project / AGENT
    agent.write_text(agent.read_text() + LOCAL)
    setup_py.update_project(project, [])
    out = capsys.readouterr().out
    assert LOCAL in agent.read_text()
    assert not (project / (AGENT + ".new")).exists()
    assert "LOKAL GEAENDERT" not in out
