"""`config.yaml` fuehrte die geharteten Secrets-Muster aus #75 nie nach (Issue #145).

## Befund

`secrets_guard.py` blockierte den Lesezugriff auf
`tests/test_phase_listener_keyword_guard.py` vollstaendig — eine normale
pytest-Datei ohne jedes Geheimnis. Die Meldung nannte "Credentials/Keys",
"immer geschuetzt", kein Override moeglich.

Der Verdacht im Issue ("keyword" matcht "key") war eine Ebene zu flach:
`core/hooks/hook_utils.py::SECRETS_SENSITIVE_PATTERNS` traegt seit #75 die
geharteten, verankerten Formen (`private[_.]key`, `[_.]secret\\.`) — diese
matchen "keyword" nicht.

Der wahre Fehler liegt in `config.yaml`. `secrets_guard.py::_get_config()`
liest `secrets_guard.sensitive_patterns`/`always_blocked` aus der geladenen
Projekt-Config und nutzt den Code-Default nur als Fallback, wenn die Config
das Feld NICHT setzt:

    cfg.get("sensitive_patterns", _DEFAULT_SENSITIVE)

`config.yaml` SETZT das Feld — mit den ALTEN, unverankerten Mustern `_key`
und `_secret`, die #75 im Code laengst ersetzt hat. Die Config gewinnt gegen
den Code-Default und macht die #75-Haertung dadurch wirkungslos: `_key`
matcht als Substring in `..._keyword_guard.py`.

Das ist derselbe Drift, den ein Kommentar in `hook_utils.py` bereits einmal
dokumentiert (zwischen `bash_gate.py` und `secrets_guard.py`, ebenfalls #75)
— nur diesmal zwischen Code-Default und ausgelieferter Vorlage. `config.yaml`
ist nicht nur die Config dieses Repos selbst, sondern auch die Vorlage, die
`setup.py::generate_config_yaml()` in JEDES Konsumenten-Projekt kopiert
(Copy- und Plugin-Modus). Jedes neu installierte Projekt erbt die
ungehaerteten Muster.

## Fix

`config.yaml` auf dieselben Muster wie `hook_utils.SECRETS_SENSITIVE_PATTERNS`
gebracht. Damit die beiden Quellen nicht wieder auseinanderlaufen koennen,
prueft ein Test hier direkt, dass `config.yaml`s YAML-Werte mit den
Code-Defaults uebereinstimmen.
"""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
CONFIG_YAML = REPO_ROOT / "config.yaml"

sys.path.insert(0, str(HOOKS_DIR))
from hook_utils import SECRETS_SENSITIVE_PATTERNS, SECRETS_ALWAYS_BLOCKED  # noqa: E402


def _config_secrets_section() -> dict:
    return yaml.safe_load(CONFIG_YAML.read_text())["secrets_guard"]


class TestConfigYamlMatchesCodeDefaults:
    """Der eigentliche Befund: die Vorlage muss die geharteten Muster tragen."""

    def test_sensitive_patterns_match_hook_utils_default(self):
        assert _config_secrets_section()["sensitive_patterns"] == SECRETS_SENSITIVE_PATTERNS

    def test_always_blocked_matches_hook_utils_default(self):
        assert _config_secrets_section()["always_blocked"] == SECRETS_ALWAYS_BLOCKED

    def test_no_unanchored_key_or_secret_substrings(self):
        """Die konkrete Regression: `_key`/`_secret` ohne Anker duerfen in
        keiner der beiden Listen mehr vorkommen — das war die Ursache."""
        section = _config_secrets_section()
        for key in ("sensitive_patterns", "always_blocked"):
            for pattern in section[key]:
                assert pattern not in ("_key", "_secret"), (
                    f"config.yaml::{key} enthaelt noch das ungeankerte Altmuster {pattern!r}"
                )


class TestRealFilesNoLongerBlocked:
    """Der reale Vorfall: `secrets_guard.py` gegen die echte `config.yaml` dieses
    Repos, hermetisch per Subprozess (Stilvorlage: test_bash_gate_freetext_fixes_64_75.py).
    """

    def _run_read(self, tmp_path: Path, rel_path: str) -> subprocess.CompletedProcess:
        import json
        import os
        payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": rel_path}})
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
        env.pop("OPENSPEC_ENV", None)
        env.pop("CLAUDE_TOOL_INPUT", None)
        # config.yaml des echten Repos in die hermetische Projekt-Root kopieren —
        # der Fehler lebt in der Config, nicht im Code, und muss deshalb mitgetestet
        # werden, sonst prueft der Test nur den (bereits korrekten) Code-Default.
        (tmp_path / "config.yaml").write_text(CONFIG_YAML.read_text())
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / "secrets_guard.py")],
            input=payload, capture_output=True, text=True, env=env, cwd=str(tmp_path),
        )

    def test_keyword_guard_test_file_readable(self, tmp_path):
        """Der genaue Vorfall aus #145."""
        res = self._run_read(tmp_path, "tests/test_phase_listener_keyword_guard.py")
        assert res.returncode == 0, res.stdout + res.stderr

    def test_secret_egress_guard_test_file_readable(self, tmp_path):
        """Derselbe Fehlertyp, schon einmal in #75 dokumentiert
        (tests/test_secret_egress_guard.py, '_secret' als Substring)."""
        res = self._run_read(tmp_path, "tests/test_secret_egress_guard.py")
        assert res.returncode == 0, res.stdout + res.stderr

    def test_real_dotenv_file_still_blocked(self, tmp_path):
        """Gegenprobe: eine echte .env-Datei muss weiterhin blockiert bleiben —
        der Fix darf den Schutz nicht abschwaechen."""
        res = self._run_read(tmp_path, ".env")
        assert res.returncode == 2, res.stdout + res.stderr

    def test_real_private_key_still_always_blocked(self, tmp_path):
        res = self._run_read(tmp_path, "config/private.key")
        assert res.returncode == 2, res.stdout + res.stderr
        assert "immer geschützt" in (res.stdout + res.stderr)
