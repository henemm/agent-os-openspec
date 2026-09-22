"""`setup.py --update` darf den Plugin-Modus nicht stillschweigend aufheben
(Issue #159).

`update_project` schrieb `framework_version.json` beim Update komplett neu:

    version_info = {
        "framework_version": FRAMEWORK_VERSION,
        "last_updated": ...,
        "installed_modules": modules,
    }

Drei Felder gehen dabei verloren — `plugin_mode`, `version_source`, `note` —
und `framework_version` bekommt wieder eine Zahl gestempelt, die im
Plugin-Modus nicht stimmen kann. Genau diese Falschauskunft war der Grund fuer
3.26.0 (PR #158); ein einziges `--update` machte den Fix rueckgaengig.

Folgeschaden: `migrate_to_plugin.py` und alles andere, was `plugin_mode`
auswertet, haelt das Projekt danach fuer ein Copy-Modus-Projekt. Ohne jede
Meldung.

Im Copy-Modus bleibt das bisherige Verhalten richtig und wird hier ebenfalls
festgehalten — sonst repariert der Fix den einen Fall und zerbricht den
anderen.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import setup as setup_py  # noqa: E402


def _version_file(project: Path) -> dict:
    return json.loads((project / ".claude" / "framework_version.json").read_text())


@pytest.fixture
def plugin_project(tmp_path, capsys):
    setup_py.install_plugin_mode(tmp_path, [])
    capsys.readouterr()
    return tmp_path


@pytest.fixture
def copy_project(tmp_path, capsys):
    setup_py.create_directory_structure(tmp_path)
    version_file = tmp_path / ".claude" / "framework_version.json"
    version_file.write_text(json.dumps({
        "framework_version": "3.3.0",
        "installed": "2026-06-21T00:00:00",
        "installed_modules": [],
    }))
    capsys.readouterr()
    return tmp_path


class TestPluginModeSurvivesUpdate:
    def test_plugin_mode_flag_is_preserved(self, plugin_project, capsys):
        setup_py.update_project(plugin_project, [])
        capsys.readouterr()

        assert _version_file(plugin_project).get("plugin_mode") is True

    def test_no_version_number_is_stamped(self, plugin_project, capsys):
        setup_py.update_project(plugin_project, [])
        capsys.readouterr()

        data = _version_file(plugin_project)
        assert data.get("framework_version") is None, (
            "Im Plugin-Modus kennt die Datei die geladene Version nicht — sie "
            f"darf keine behaupten, stand aber auf {data.get('framework_version')!r}"
        )

    def test_version_source_and_note_are_preserved(self, plugin_project, capsys):
        setup_py.update_project(plugin_project, [])
        capsys.readouterr()

        data = _version_file(plugin_project)
        assert data.get("version_source") == setup_py.PLUGIN_MODE_VERSION_SOURCE
        assert data.get("note") == setup_py.PLUGIN_MODE_VERSION_NOTE

    def test_repeated_updates_stay_stable(self, plugin_project, capsys):
        """Der Befund trat bei *jedem* Update auf — einmal pruefen genuegt nicht."""
        setup_py.update_project(plugin_project, [])
        setup_py.update_project(plugin_project, [])
        capsys.readouterr()

        data = _version_file(plugin_project)
        assert data.get("plugin_mode") is True
        assert data.get("framework_version") is None


class TestCopyModeUnchanged:
    def test_copy_mode_still_stamps_the_version(self, copy_project, capsys):
        setup_py.update_project(copy_project, [])
        capsys.readouterr()

        data = _version_file(copy_project)
        assert data.get("framework_version") == setup_py.FRAMEWORK_VERSION, (
            "Im Copy-Modus IST die Datei die Auskunftsquelle — dort gehoert die "
            "Zahl hin"
        )
        assert not data.get("plugin_mode")

    def test_copy_mode_records_last_updated(self, copy_project, capsys):
        setup_py.update_project(copy_project, [])
        capsys.readouterr()

        assert _version_file(copy_project).get("last_updated")


class TestRobustness:
    def test_update_without_existing_version_file(self, tmp_path, capsys):
        """Ein Projekt ohne `framework_version.json` darf das Update nicht
        zum Absturz bringen."""
        setup_py.create_directory_structure(tmp_path)
        setup_py.update_project(tmp_path, [])
        capsys.readouterr()

        assert _version_file(tmp_path).get("framework_version") == setup_py.FRAMEWORK_VERSION

    def test_update_with_corrupt_version_file(self, tmp_path, capsys):
        setup_py.create_directory_structure(tmp_path)
        (tmp_path / ".claude" / "framework_version.json").write_text("{kaputt")

        setup_py.update_project(tmp_path, [])
        capsys.readouterr()

        assert _version_file(tmp_path).get("framework_version") == setup_py.FRAMEWORK_VERSION
