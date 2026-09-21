"""Ein Modul-Hook darf beim Import nichts tun (Issue #154, Teil 1 von #70).

`modules/ios-swiftui/hooks/test_lock_guard.py` ist ein Hook-Script, kein Test.
Es heisst nur `test_*` und ruft seinen Modul-Guard auf Modulebene auf:

    if "ios-swiftui" not in os.environ.get("OPENSPEC_ENABLED_MODULES", "").split(","):
        sys.exit(0)

Der pytest-Collector faengt `SystemExit` beim Import nicht ab. Ein nacktes
`python3 -m pytest` (der naheliegende Aufruf) bricht deshalb mit INTERNALERROR
ab, bevor ein einziger Test laeuft.

Warum das zaehlt: Ein abbrechender Sammellauf verdeckt echte Fehlschlaege. Wer
die Suite ohne Zusatzpfad aufruft, bekommt kein Ergebnis, sondern einen
Abbruch — und im Zweifel den Eindruck, es sei nur "irgendein Setup-Problem".

Die Heilung ist die Ursache, nicht die Kulisse: der Guard gehoert in `main()`,
nicht auf Modulebene. Diese Tests halten beides fest — der Import ist
nebenwirkungsfrei, UND der Guard wirkt weiterhin, wenn das Script als Hook
laeuft.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "modules" / "ios-swiftui" / "hooks" / "test_lock_guard.py"


def _run_hook(env_extra: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "OPENSPEC_ENABLED_MODULES"}
    env.update(env_extra)
    return subprocess.run([sys.executable, str(HOOK)], env=env,
                          capture_output=True, text=True)


class TestImportIsSideEffectFree:
    def test_import_does_not_raise_systemexit(self):
        spec = importlib.util.spec_from_file_location("ios_test_lock_guard", HOOK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # darf nicht abbrechen
        assert hasattr(module, "main"), "main() muss nach dem Import erreichbar sein"

    def test_naked_pytest_collection_succeeds(self):
        """Der eigentliche Befund: `pytest` ohne Zusatzpfad muss durchlaufen."""
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q",
             "-p", "no:cacheprovider"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        combined = result.stdout + result.stderr
        assert "INTERNALERROR" not in combined, (
            "Sammellauf bricht ab:\n" + combined[-2000:]
        )
        assert result.returncode == 0, (
            f"Sammellauf endet mit {result.returncode}:\n" + combined[-2000:]
        )


class TestModuleGuardStillWorks:
    def test_exits_zero_when_module_inactive(self):
        """Ohne aktives ios-swiftui-Modul laesst der Hook alles durch."""
        result = _run_hook({"CLAUDE_TOOL": "Bash"})
        assert result.returncode == 0

    def test_exits_zero_for_non_bash_tool_when_module_active(self):
        result = _run_hook({
            "OPENSPEC_ENABLED_MODULES": "ios-swiftui",
            "CLAUDE_TOOL": "Read",
        })
        assert result.returncode == 0

    def test_exits_zero_for_unrelated_bash_command_when_module_active(self):
        result = _run_hook({
            "OPENSPEC_ENABLED_MODULES": "ios-swiftui",
            "CLAUDE_TOOL": "Bash",
            "CLAUDE_TOOL_INPUT": '{"command": "ls -la"}',
        })
        assert result.returncode == 0
