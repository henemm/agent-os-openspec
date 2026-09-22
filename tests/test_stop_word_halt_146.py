"""'halt' als STOP_PHRASE matcht deutsches Fuellwort in jeder Nachricht (Issue #146).

## Befund

`STOP_PHRASES` in `core/hooks/phase_listener.py` enthielt `"halt"` ohne
`leading_only`-Einschraenkung (Stop-Lock-Phrasen matchen bewusst ueberall im
Text, siehe `_matches()`-Docstring: "Not-Aus darf grosszuegig greifen"). Im
Deutschen ist "halt" ein extrem haeufiges Fuellwort ("das ist halt so", "ich
wollte halt fragen") — jede solche Nachricht loeste ungewollt einen echten
Stop-Lock aus.

Derselbe Drift wie #145: `config.yaml` (`stop_lock.stop_keywords`) fuehrt eine
EIGENE Kopie der Liste, die `phase_listener._load_phrases()` gegenueber dem
Python-Default bevorzugt (`config.get(...).get("stop_keywords", STOP_PHRASES)`).
Ein Fix nur am Code-Default haette den echten Bug nicht behoben, da
`config.yaml` selbst `"halt"` explizit auflistet und damit gewinnt — und
`config.yaml` ist ausserdem die Vorlage, die `setup.py::generate_config_yaml()`
in jedes Konsumenten-Projekt kopiert.

## Fix

`"halt"` aus beiden Listen entfernt — `core/hooks/phase_listener.py::STOP_PHRASES`
und `config.yaml::stop_lock.stop_keywords`. `stop`/`stopp`/`anhalten` bleiben
und decken den echten Anwendungsfall eindeutig ab (Tech-Lead-Entscheidung,
Issue-Kommentar #146).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
CONFIG_YAML = REPO_ROOT / "config.yaml"

sys.path.insert(0, str(HOOKS_DIR))
import phase_listener as pl  # noqa: E402


def _config_stop_lock_section() -> dict:
    return yaml.safe_load(CONFIG_YAML.read_text())["stop_lock"]


class TestNoFillerWordInDefaults:
    """Der eigentliche Befund: weder Code-Default noch Config-Vorlage duerfen
    'halt' mehr als Stop-Phrase fuehren."""

    def test_halt_not_in_code_default(self):
        assert "halt" not in pl.STOP_PHRASES

    def test_halt_not_in_config_yaml(self):
        assert "halt" not in _config_stop_lock_section()["stop_keywords"]

    def test_real_stop_words_still_present(self):
        """Gegenprobe: der Fix darf die echten Stop-Woerter nicht mit entfernen."""
        for word in ("stop", "stopp", "anhalten"):
            assert word in pl.STOP_PHRASES
            assert word in _config_stop_lock_section()["stop_keywords"]

    def test_config_yaml_matches_code_default(self):
        """Einzige Quelle der Wahrheit: Config-Vorlage und Code-Default duerfen
        nicht wieder auseinanderlaufen (derselbe Drift wie #145)."""
        assert _config_stop_lock_section()["stop_keywords"] == pl.STOP_PHRASES


class TestIntegrationRealConfigNoLongerTriggersOnFillerWord:
    """Hermetischer Subprozess-Test gegen die ECHTE config.yaml dieses Repos —
    Stilvorlage: test_config_yaml_secrets_pattern_drift_145.py. Ein Test nur
    gegen den Code-Default haette den Config-Anteil des Drifts nicht gefunden."""

    def _run_listener(self, tmp_path: Path, prompt: str) -> subprocess.CompletedProcess:
        (tmp_path / ".git").mkdir()
        (tmp_path / "config.yaml").write_text(CONFIG_YAML.read_text())
        payload = json.dumps({"prompt": prompt})
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / "phase_listener.py")],
            input=payload, capture_output=True, text=True, env=env, cwd=str(tmp_path),
        )

    def test_filler_word_does_not_enable_stop_lock(self, tmp_path):
        """Der genaue Vorfall aus #146: 'halt' als Fuellwort in einer normalen
        Nachricht."""
        res = self._run_listener(tmp_path, "das ist halt so, kein Problem damit")
        assert res.returncode == 0, res.stdout + res.stderr
        lock_file = tmp_path / ".claude" / "stop_lock.json"
        assert not lock_file.exists(), "Fuellwort 'halt' hat faelschlich Stop-Lock gesetzt"

    def test_real_stop_word_still_enables_stop_lock(self, tmp_path):
        """Gegenprobe: ein echtes Stop-Wort muss weiterhin greifen."""
        res = self._run_listener(tmp_path, "Mach bitte erst den Bericht fertig, dann stopp.")
        assert res.returncode == 0, res.stdout + res.stderr
        lock_file = tmp_path / ".claude" / "stop_lock.json"
        assert lock_file.exists()
        assert json.loads(lock_file.read_text()).get("enabled") is True
