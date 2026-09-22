"""Die Versionsangabe im README darf nicht driften (Issue #195).

Befund am 2026-09-21: `README.md` Zeile 5 nannte `3.9.0`, waehrend
`.claude-plugin/plugin.json` und `CHANGELOG.md` bei `3.27.2` standen. Achtzehn
Minor-Versionen Abstand, ueber Monate unbemerkt.

Ursache ist keine Nachlaessigkeit, sondern eine Luecke im Waechter:
`scripts/release_check.py` gleicht `plugin.json` gegen `CHANGELOG.md` ab und
laesst das README aus. Was nichts prueft, driftet — und das README ist
ausgerechnet die Datei, die ein Fremder zuerst liest.

Geprueft wird beides: die reine Extraktion (damit die Regex nicht an einer
harmlosen Umformulierung der Zeile zerbricht) und der Waechter als Ganzes
(damit die Pruefung in `main()` auch wirklich laeuft, statt nur zu
existieren).
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import release_check  # noqa: E402


class TestReadmeVersionExtraction:
    def test_reads_version_from_marker_line(self):
        text = (
            "# Agent OS + OpenSpec Framework\n"
            "\n"
            "Beschreibung.\n"
            "\n"
            "**Version**: 3.27.2 · [Changelog](CHANGELOG.md)\n"
        )
        assert release_check.readme_version(text) == "3.27.2"

    def test_returns_none_without_marker(self):
        assert release_check.readme_version("# Titel\n\nkeine Versionszeile\n") is None

    def test_ignores_other_version_mentions(self):
        """Nur die Marker-Zeile zaehlt — sonst gewinnt die erstbeste Zahl aus
        einem Beispielblock und der Waechter meldet Unsinn."""
        text = (
            "# Titel\n"
            "\n"
            "Beispiel: `pip install foo==1.2.3`\n"
            "\n"
            "**Version**: 3.27.2 · [Changelog](CHANGELOG.md)\n"
        )
        assert release_check.readme_version(text) == "3.27.2"


class TestReadmeVersionCheck:
    def test_matching_version_passes(self):
        ok, _ = release_check.check_readme_version("3.27.2", "**Version**: 3.27.2\n")
        assert ok

    def test_mismatch_fails_and_names_both_numbers(self):
        ok, detail = release_check.check_readme_version("3.27.2", "**Version**: 3.9.0\n")
        assert not ok
        assert "3.9.0" in detail, "die gefundene Zahl muss in der Meldung stehen"
        assert "3.27.2" in detail, "die erwartete Zahl muss in der Meldung stehen"

    def test_missing_version_line_fails(self):
        ok, detail = release_check.check_readme_version("3.27.2", "# ohne Versionszeile\n")
        assert not ok
        assert detail.strip(), "ein Fehlschlag ohne Begruendung ist wertlos"


class TestRepositoryState:
    def test_readme_matches_plugin_manifest(self):
        """Der eigentliche Befund aus #195."""
        manifest = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
        found = release_check.readme_version((REPO_ROOT / "README.md").read_text())
        assert found == manifest["version"], (
            f"README nennt {found!r}, ausgeliefert wird {manifest['version']!r}"
        )

    def test_release_check_actually_runs_the_readme_check(self):
        """Eine Pruefung, die `main()` nicht aufruft, schuetzt nichts.

        Der Lauf scheitert hier an Branch/Arbeitsbaum — das ist egal. Geprueft
        wird nur, dass die README-Zeile in der Pruefliste steht.

        Gebunden an die *Zeilenform* der Pruefliste ("  OK    README  ..."),
        nicht an das blosse Vorkommen des Wortes: `README.md` taucht als
        geaenderte Datei ohnehin in der Arbeitsbaum-Zeile auf. Ein
        `"README" in stdout` war darum immer wahr — auch mit ausgebauter
        Pruefung. Belegt durch Gegenprobe: erst diese Fassung wird rot, wenn
        die Zeile aus `checks` entfernt wird.
        """
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "release_check.py"), "--no-tests"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        row = re.compile(r"^\s*(OK|FAIL)\s+README\s", re.MULTILINE)
        assert row.search(result.stdout), (
            "release_check fuehrt keine README-Pruefung aus:\n" + result.stdout
        )
