"""`framework_version.json` darf im Plugin-Modus keine Zahl behaupten, die sie
nicht kennen kann.

Befund aus gregor_zwanzig (2026-09-20): die Datei stand auf `3.4.13`, waehrend
das Plugin 3.25.1 auslieferte. Kein Uebertragungsfehler, sondern Bauart:

- `setup.py::install_plugin_mode` schreibt `framework_version: FRAMEWORK_VERSION`
  zusammen mit `plugin_mode: True`. Das ist die Version des setup.py, das zufaellig
  gerade lief.
- Danach laufen Updates ueber `claude plugin update`. Das ruehrt diese Datei nie an.
- `migrate_to_plugin.py::migrate` setzt beim Umstellen `plugin_mode: True`, laesst
  die alte Copy-Mode-Zahl aber stehen.

Die Zahl ist also ab der ersten Plugin-Aktualisierung falsch — in JEDEM
Plugin-Modus-Projekt, nicht nur in gregor_zwanzig. Wer sie liest (die README
empfiehlt genau das), bekommt eine Auskunft, die wie eine Messung aussieht und
keine ist. Gleiche Fehlerklasse wie #155.

Im Copy-Modus bleibt die Zahl richtig und wird weiter geschrieben: dort IST die
Datei die Auskunftsquelle, weil `setup.py` die Dateien selbst kopiert hat.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import setup as setup_py  # noqa: E402
import migrate_to_plugin  # noqa: E402

STALE = "3.4.13"


def _version_file(project: Path) -> dict:
    return json.loads((project / ".claude" / "framework_version.json").read_text())


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".claude").mkdir()
    return tmp_path


class TestPluginModeInstall:
    def test_install_plugin_mode_pins_no_version_number(self, project, capsys):
        """Der Plugin-Modus-Installer darf keine Zahl stempeln, die schon beim
        naechsten `claude plugin update` falsch ist."""
        setup_py.install_plugin_mode(project, [])
        capsys.readouterr()

        data = _version_file(project)

        assert data.get("plugin_mode") is True
        assert data.get("framework_version") is None, (
            "Im Plugin-Modus kennt diese Datei die geladene Version nicht — sie "
            f"darf keine behaupten, stand aber auf {data.get('framework_version')!r}"
        )

    def test_install_plugin_mode_names_the_real_authority(self, project, capsys):
        """Eine geleerte Zahl allein hilft niemandem: die Datei muss sagen,
        wo die Version WIRKLICH steht."""
        setup_py.install_plugin_mode(project, [])
        capsys.readouterr()

        data = _version_file(project)

        assert data.get("version_source") == "plugin", (
            f"Quelle der Wahrheit muss benannt sein, war {data!r}"
        )
        assert any("plugin" in str(v).lower() for k, v in data.items() if k == "note"), (
            f"Ein Hinweis, wie man die geladene Version abliest, fehlt: {data!r}"
        )


class TestCopyModeUnchanged:
    def test_copy_mode_still_pins_the_version(self, project, capsys):
        """Gegenprobe und Rueckwaertskompatibilitaet: im Copy-Modus hat
        `setup.py` die Dateien selbst kopiert — dort IST die Datei die
        Auskunftsquelle und behaelt ihre Zahl."""
        import argparse

        # Der Copy-Modus-Pfad in main() ist nicht einzeln aufrufbar; geprueft
        # wird die Stelle, die ihn traegt: update_project() stempelt weiterhin.
        setup_py.update_project(project, [], force=True)
        capsys.readouterr()

        data = _version_file(project)

        assert data.get("framework_version") == setup_py.FRAMEWORK_VERSION, (
            "Der Copy-Modus muss weiter die installierte Version festhalten, "
            f"war {data!r}"
        )
        assert argparse  # Import nur zur Dokumentation des Aufrufwegs


class TestMigration:
    @staticmethod
    def _seed(project: Path, **extra) -> None:
        (project / ".claude" / "settings.json").write_text(json.dumps({"hooks": {}}))
        data = {
            "framework_version": STALE,
            "last_updated": "2026-06-30T13:15:00.000000",
            "installed_modules": [],
        }
        data.update(extra)
        (project / ".claude" / "framework_version.json").write_text(json.dumps(data))

    def test_migrate_clears_the_stale_copy_mode_version(self, project, capsys):
        """Der Fundfall: beim Umstellen auf Plugin-Modus bleibt die alte
        Copy-Mode-Zahl stehen und wird ab sofort zur Falschauskunft."""
        self._seed(project)

        migrate_to_plugin.migrate(project, dry_run=False)
        capsys.readouterr()

        data = _version_file(project)

        assert data.get("plugin_mode") is True
        assert data.get("framework_version") is None, (
            f"Die Copy-Mode-Zahl {STALE!r} darf nicht ueberleben, war {data!r}"
        )
        assert data.get("version_source") == "plugin"

    def test_migrate_dry_run_changes_nothing(self, project, capsys):
        """Trockenlauf bleibt Trockenlauf."""
        self._seed(project)

        migrate_to_plugin.migrate(project, dry_run=True)
        capsys.readouterr()

        data = _version_file(project)

        assert data.get("framework_version") == STALE
        assert "plugin_mode" not in data

    def test_migrate_is_idempotent(self, project, capsys):
        """Zweiter Lauf auf einem bereits umgestellten Projekt darf nichts
        kaputtmachen — und keine Zahl zurueckschreiben."""
        self._seed(project)
        migrate_to_plugin.migrate(project, dry_run=False)
        capsys.readouterr()

        migrate_to_plugin.migrate(project, dry_run=False)
        capsys.readouterr()

        data = _version_file(project)
        assert data.get("plugin_mode") is True
        assert data.get("framework_version") is None

    def test_migrate_of_already_marked_project_still_clears_number(self, project, capsys):
        """Der Zustand, in dem gregor_zwanzig stand: `plugin_mode` war bereits
        gesetzt, die Zahl aber alt. Ein erneuter Lauf muss ihn bereinigen,
        sonst braucht jedes betroffene Projekt Handarbeit."""
        self._seed(project, plugin_mode=True)

        migrate_to_plugin.migrate(project, dry_run=False)
        capsys.readouterr()

        data = _version_file(project)
        assert data.get("framework_version") is None, (
            f"Bestehender plugin_mode darf die alte Zahl nicht konservieren: {data!r}"
        )
