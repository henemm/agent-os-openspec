"""Regressionstests: `.environment` / `.environmentObject` (SwiftUI) sind keine .env-Dateien.

Ursache: `SECRETS_SENSITIVE_PATTERNS` enthielt das unverankerte Muster `\\.env`.
Es matcht jedes Token, das `.env` als Praefix hat, also auch die SwiftUI-
Modifier `.environment(...)` und `.environmentObject(...)`, die in praktisch
jeder SwiftUI-Datei vorkommen. Ein `grep` oder `sed` auf einen dieser
Modifier in einer Swift-Datei wurde deshalb als Zugriff auf eine .env-Datei
geblockt (beobachtet beim Anlegen einer SwiftUI-App mit Hook-Schutz).

Fix: `\\.env(rc)?\\b`, Wortgrenze nach `env`. `.env`, `.env.local`,
`.env.production`, `.envrc` und `config/.env` bleiben geschuetzt; `.environment`
hat zwischen `v` und `i` keine Wortgrenze und faellt heraus.

Stilvorlage: tests/test_bash_gate_false_positives.py (hermetisch, beide Guards).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"


def _run(hook: str, tmp_path: Path, payload: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
    env.pop("OPENSPEC_ENV", None)  # kein Staging-Bypass
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / hook)],
        input=json.dumps(payload), capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _read(path: str) -> dict:
    return {"tool_name": "Read", "tool_input": {"file_path": path}}


def _run_both(tmp_path: Path, command: str):
    return _run("secrets_guard.py", tmp_path, _bash(command)), _run("bash_gate.py", tmp_path, _bash(command))


class TestSwiftUIEnvironmentModifiersAllowed:
    def test_grep_environment_object_in_swift_file_allowed(self, tmp_path):
        """Realfall: grep nach dem SwiftUI-Modifier in einer Swift-Datei."""
        cmd = r'grep -n "\.environmentObject(" Sources/App/LooseEndsApp.swift'
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 0, sg.stderr
        assert bg.returncode == 0, bg.stderr

    def test_sed_print_environment_modifier_allowed(self, tmp_path):
        """sed -n ... p ist ein Ausgabe-Kommando, aber kein Token ist ein .env-Pfad."""
        cmd = r"sed -n 's/\.environment(\\.modelContext)/.modelContext/p' Sources/ContentView.swift"
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 0, sg.stderr
        assert bg.returncode == 0, bg.stderr

    def test_cat_swift_file_with_environment_in_name_allowed(self, tmp_path):
        cmd = "cat Sources/Extensions/View.environment+Loose.swift"
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 0, sg.stderr
        assert bg.returncode == 0, bg.stderr

    def test_read_tool_swift_file_with_environment_in_name_allowed(self, tmp_path):
        res = _run("secrets_guard.py", tmp_path, _read(str(tmp_path / "Sources" / "View.environment.swift")))
        assert res.returncode == 0, res.stderr


class TestDotEnvFilesStillBlocked:
    @pytest.mark.parametrize("path", [".env", ".env.local", ".env.production", ".envrc", "config/.env"])
    def test_cat_dotenv_variants_blocked(self, tmp_path, path):
        sg, bg = _run_both(tmp_path, f"cat {path}")
        assert sg.returncode == 2, sg.stdout + sg.stderr
        assert bg.returncode == 2, bg.stdout + bg.stderr

    def test_read_tool_dotenv_blocked(self, tmp_path):
        res = _run("secrets_guard.py", tmp_path, _read(str(tmp_path / ".env")))
        assert res.returncode == 2, res.stdout + res.stderr
