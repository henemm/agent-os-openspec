"""RED-Tests fuer Issue #237/#239: secret_egress_guard.py blockt /dev/null,
Standard-Kanaele, FD-Duplizierung mit angehaengtem Trennzeichen und das
Sitzungs-Scratchpad faelschlich.

Bewusst eine NEUE Datei (nicht tests/test_secret_egress_redirect_guard_97.py):
diese Datei ist fuer Read/Bash gesperrt (Issue #241, veraltete config.yaml im
Haupt-Ordner + find_project_root()-Aufloesung dorthin in einer Worktree-
Sitzung) und bleibt deshalb unveraendert. Siehe docs/specs/
fix-237-egress-guard-scratchpad.md fuer die vollstaendigen Acceptance
Criteria (AC-1 bis AC-15).

Testaufbau (Stilvorlage tests/test_bash_gate_false_positives.py):
- Subprozess-Aufruf des echten Hooks mit CLAUDE_PROJECT_DIR=tmp_path
- CLAUDE_TOOL_INPUT/CLAUDE_TOOL_NAME werden NICHT gesetzt, damit der Hook
  das Payload-JSON von stdin liest (einzige Quelle fuer scratchpad_dir)
- Kein cwd-Override bei relativen Redirect-Zielen (AC-7): die Subprozess-CWD
  entspricht damit der echten Test-Runner-CWD, waehrend CLAUDE_PROJECT_DIR
  auf ein unabhaengiges tmp_path-Verzeichnis zeigt -- exakt das Delta, das
  einen relativen Ziel-String heute faelschlich als "ausserhalb der Zone"
  erscheinen laesst.
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import secret_egress_guard as egress  # noqa: E402  (Pfad muss vor dem Import gesetzt sein)


def _run_egress_guard(project_dir: Path, command: str,
                       scratchpad_dir: "str | None" = None) -> subprocess.CompletedProcess:
    """Ruft secret_egress_guard.py als echten Subprozess auf.

    Payload geht ausschliesslich per stdin-JSON rein (kein CLAUDE_TOOL_INPUT/
    CLAUDE_TOOL_NAME-Env-Zweig) -- das ist der einzige Weg, `scratchpad_dir`
    zu uebergeben (D3 der Spec).
    """
    payload: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if scratchpad_dir is not None:
        payload["scratchpad_dir"] = scratchpad_dir
    env = dict(os.environ)
    env.pop("CLAUDE_TOOL_INPUT", None)
    env.pop("CLAUDE_TOOL_NAME", None)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "secret_egress_guard.py")],
        input=json.dumps(payload), capture_output=True, text=True, env=env,
    )


# --- AC-1 bis AC-5: /dev/null, /dev/stdout, /dev/stderr mit/ohne Trennzeichen ---

class TestDeviceTargetsAllowed:
    def test_ac1_devnull_with_semicolon_allowed(self, tmp_path):
        """AC-1.
        GIVEN: das Bash-Kommando 'ls -d ~/x 2>/dev/null; echo done'
        WHEN: secret_egress_guard.py es prueft
        THEN: Exit 0 -- /dev/null mit angehaengtem ';' ist kein echtes Ziel.
        """
        result = _run_egress_guard(tmp_path, "ls -d ~/x 2>/dev/null; echo done")
        assert result.returncode == 0, result.stderr

    def test_ac2_devnull_with_ampersand_allowed(self, tmp_path):
        """AC-2.
        GIVEN: das Bash-Kommando 'cmd 2>/dev/null&'
        WHEN: geprueft
        THEN: Exit 0 -- /dev/null mit angehaengtem '&'.
        """
        result = _run_egress_guard(tmp_path, "cmd 2>/dev/null&")
        assert result.returncode == 0, result.stderr

    def test_ac3_devnull_with_closing_paren_allowed(self, tmp_path):
        """AC-3.
        GIVEN: das Bash-Kommando '(cmd 2>/dev/null)'
        WHEN: geprueft
        THEN: Exit 0 -- /dev/null mit angehaengtem ')'.
        """
        result = _run_egress_guard(tmp_path, "(cmd 2>/dev/null)")
        assert result.returncode == 0, result.stderr

    def test_ac4_devstdout_allowed(self, tmp_path):
        """AC-4.
        GIVEN: das Bash-Kommando 'cmd >/dev/stdout'
        WHEN: geprueft
        THEN: Exit 0 -- /dev/stdout ist ein erlaubtes Geraet (D2).
        """
        result = _run_egress_guard(tmp_path, "cmd >/dev/stdout")
        assert result.returncode == 0, result.stderr

    def test_ac5_devstderr_allowed(self, tmp_path):
        """AC-5.
        GIVEN: das Bash-Kommando 'cmd 2>/dev/stderr'
        WHEN: geprueft
        THEN: Exit 0 -- /dev/stderr ist ein erlaubtes Geraet (D2).
        """
        result = _run_egress_guard(tmp_path, "cmd 2>/dev/stderr")
        assert result.returncode == 0, result.stderr


# --- AC-6: echtes Ziel ausserhalb der Zone, Meldung muss bereinigt sein ---

class TestRealTargetOutsideZoneMessageIsClean:
    def test_ac6_real_target_outside_zone_still_blocked_with_clean_name(self, tmp_path):
        """AC-6.
        GIVEN: 'echo x > ~/bericht.txt; echo fertig' -- ein echtes Ziel
        ausserhalb der Zone (absoluter Pfad im Home-Verzeichnis, nicht im
        Projekt), mit angehaengtem Trennzeichen
        WHEN: geprueft
        THEN: Exit 2 bleibt (Zone unveraendert), aber die Meldung nennt das
        BEREINIGTE Ziel ('bericht.txt', nicht 'bericht.txt;').
        """
        target = str(Path.home() / "bericht.txt")
        command = f"echo x > {target}; echo fertig"
        result = _run_egress_guard(tmp_path, command)
        assert result.returncode == 2, result.stdout + result.stderr
        assert "bericht.txt;" not in result.stderr, (
            "Meldung enthaelt noch das unbereinigte Ziel mit angehaengtem ';': "
            + result.stderr
        )
        assert "bericht.txt" in result.stderr


# --- AC-7: FD-Duplizierung mit angehaengtem Trennzeichen ---

class TestFdDuplicationWithTrailingSeparatorAllowed:
    def test_ac7_stderr_to_stdout_with_semicolon_allowed(self, tmp_path):
        """AC-7.
        GIVEN: das Bash-Kommando 'cmd 2>&1; echo x' (FD-Duplizierung mit
        angehaengtem Trennzeichen)
        WHEN: geprueft
        THEN: Exit 0 -- die Ausnahme fuer 2>&1/>&2 bleibt auch mit
        angehaengtem Trennzeichen wirksam. Ohne cwd-Override loest der
        unbereinigte Ziel-String '&1;' heute relativ zur Subprozess-CWD auf
        (die von CLAUDE_PROJECT_DIR=tmp_path abweicht) und erscheint dadurch
        faelschlich als Ziel ausserhalb der Zone.
        """
        result = _run_egress_guard(tmp_path, "cmd 2>&1; echo x")
        assert result.returncode == 0, result.stderr


# --- AC-8, AC-9, AC-10: Scratchpad-Ausnahme ---

class TestScratchpadException:
    def test_ac8_write_into_own_scratchpad_subfolder_allowed(self, tmp_path):
        """AC-8.
        GIVEN: eine PreToolUse-Payload mit gesetztem scratchpad_dir UND ein
        Bash-Kommando, das per '>' in eine Datei INNERHALB dieses Pfads
        schreibt (in einem Unterordner)
        WHEN: geprueft
        THEN: Exit 0 -- heute rot, weil _read_payload()/main() das Feld
        scratchpad_dir noch nicht auslesen/durchreichen (D3 fehlt).
        """
        project = tmp_path / "project"
        project.mkdir()
        scratchpad = tmp_path / "scratchpad"
        scratchpad.mkdir()
        target = str(scratchpad / "sub" / "out.txt")
        command = f"echo hi > {target}"
        result = _run_egress_guard(project, command, scratchpad_dir=str(scratchpad))
        assert result.returncode == 0, result.stderr

    def test_ac9_write_into_foreign_scratchpad_still_blocked(self, tmp_path):
        """AC-9 -- REGRESSIONSSCHUTZ: dieser Test ist schon heute gruen (die
        Scratchpad-Ausnahme existiert noch nicht, also wird ohnehin jedes
        Ziel ausserhalb der Projekt-Zone blockiert) und MUSS es nach der
        Implementierung bleiben.
        GIVEN: eine Payload mit gesetztem scratchpad_dir UND ein Bash-
        Kommando, das in ein ANDERES (fremdes) Scratchpad-Verzeichnis
        schreibt (kein Praefix von scratchpad_dir)
        WHEN: geprueft
        THEN: Exit 2.
        """
        project = tmp_path / "project"
        project.mkdir()
        own_scratchpad = tmp_path / "scratchpad"
        own_scratchpad.mkdir()
        foreign_scratchpad = tmp_path / "other-session-scratchpad"
        foreign_scratchpad.mkdir()
        target = str(foreign_scratchpad / "leak.txt")
        command = f"echo hi > {target}"
        result = _run_egress_guard(project, command, scratchpad_dir=str(own_scratchpad))
        assert result.returncode == 2, result.stdout + result.stderr

    def test_ac10_no_scratchpad_dir_field_tmp_write_still_blocked(self, tmp_path):
        """AC-10 -- REGRESSIONSSCHUTZ: bereits heute gruen (kein
        scratchpad_dir im Payload -> kein Muster-Fallback, unveraendertes
        Verhalten) und MUSS es bleiben.
        GIVEN: eine Payload OHNE scratchpad_dir-Feld UND ein Bash-Kommando,
        das in ein /tmp-Verzeichnis schreibt, das keinem konfigurierten
        Muster entspricht
        WHEN: geprueft
        THEN: Exit 2.
        """
        project = tmp_path / "project"
        project.mkdir()
        command = "echo hi > /tmp/some-unrelated-dir-237/file.txt"
        result = _run_egress_guard(project, command, scratchpad_dir=None)
        assert result.returncode == 2, result.stdout + result.stderr


# --- AC-13: Wert-Pruefung hat Vorrang vor dem Ziel-Check (unveraendert) ---

class TestLeakCheckTakesPrecedenceOverRedirectCheck:
    def test_ac13_literal_secret_value_blocks_before_redirect_check(self, tmp_path):
        """AC-13 -- REGRESSIONSSCHUTZ: find_leaks() ist von dieser Aenderung
        nicht betroffen und laeuft weiterhin zuerst/exklusiv -- bereits heute
        gruen, muss es bleiben.
        GIVEN: ein Bash-Kommando, das gleichzeitig einen ausgeschriebenen
        Secret-Wert aus der .env UND ein Ziel ausserhalb der Zone enthaelt
        WHEN: secret_egress_guard.py es prueft
        THEN: Exit 2 mit der Literal-Wert-Meldung (nicht mit der
        Redirect-Meldung).
        """
        project = tmp_path / "project"
        project.mkdir()
        (project / ".env").write_text("SECRET_KEY=abcdefghij1234\n")
        target = str(Path.home() / "leak-target.txt")
        command = f"echo abcdefghij1234 > {target}"
        result = _run_egress_guard(project, command)
        assert result.returncode == 2, result.stdout + result.stderr
        assert "SECRET_KEY" in result.stderr
        assert "aus .env" in result.stderr
        assert "schreibt per Umleitung" not in result.stderr


# --- AC-15: Meldungstext nennt das Scratchpad nur, wenn eins existiert ---

class TestMessageMentionsScratchpadOnlyWhenPresent:
    def test_ac15_message_omits_scratchpad_when_field_missing(self, tmp_path):
        """AC-15.
        GIVEN: ein blockiertes Ziel ausserhalb der Zone UND eine Payload
        OHNE scratchpad_dir
        WHEN: secret_egress_guard.py blockiert
        THEN: die Meldung nennt das Sitzungs-Scratchpad NICHT als richtiges
        Ziel (diese Sitzung hat keins -- der Rat waere nicht befolgbar).
        Heute rot: die Meldung nennt das Scratchpad unbedingt.
        """
        target = str(Path.home() / "irgendein-blockiertes-ziel.txt")
        result = _run_egress_guard(tmp_path, f"echo x > {target}", scratchpad_dir=None)
        assert result.returncode == 2, result.stdout + result.stderr
        assert "Scratchpad" not in result.stderr, result.stderr

    def test_ac15_message_still_mentions_scratchpad_when_field_present(self, tmp_path):
        """AC-15 (zweite Haelfte) -- bereits heute gruen (die Meldung nennt
        das Scratchpad unbedingt, also auch wenn scratchpad_dir gesetzt ist)
        und muss es bleiben.
        GIVEN: ein blockiertes Ziel ausserhalb der Zone UND eine Payload MIT
        gesetztem scratchpad_dir
        WHEN: secret_egress_guard.py blockiert
        THEN: die Meldung nennt das Sitzungs-Scratchpad weiterhin.
        """
        project = tmp_path / "project"
        project.mkdir()
        scratchpad = tmp_path / "scratchpad"
        scratchpad.mkdir()
        target = str(Path.home() / "irgendein-anderes-blockiertes-ziel.txt")
        result = _run_egress_guard(project, f"echo x > {target}", scratchpad_dir=str(scratchpad))
        assert result.returncode == 2, result.stdout + result.stderr
        assert "Scratchpad" in result.stderr


# --- Unit-Test-Infrastruktur fuer D3/D4 (Signaturwechsel) ---

class TestReadPayloadUnit:
    def test_read_payload_returns_three_tuple_with_scratchpad_dir(self, monkeypatch):
        """Infrastruktur fuer AC-8/AC-9/AC-15.
        GIVEN: stdin-JSON mit gesetztem scratchpad_dir
        WHEN: _read_payload() aufgerufen wird
        THEN: liefert ein 3-Tupel (tool_name, tool_input, scratchpad_dir).
        Heute rot: die Funktion liefert nur ein 2-Tupel (ValueError beim
        Entpacken in 3 Variablen).
        """
        monkeypatch.delenv("CLAUDE_TOOL_INPUT", raising=False)
        monkeypatch.delenv("CLAUDE_TOOL_NAME", raising=False)
        payload = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi"},
            "scratchpad_dir": "/tmp/claude-501/some-session/scratchpad",
        })
        monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
        tool_name, tool_input, scratchpad_dir = egress._read_payload()
        assert tool_name == "Bash"
        assert tool_input == {"command": "echo hi"}
        assert scratchpad_dir == "/tmp/claude-501/some-session/scratchpad"

    def test_read_payload_returns_none_scratchpad_dir_when_absent(self, monkeypatch):
        """Infrastruktur fuer AC-10.
        GIVEN: stdin-JSON OHNE scratchpad_dir-Feld
        WHEN: _read_payload() aufgerufen wird
        THEN: das dritte Element des 3-Tupels ist None.
        Heute rot: 2-Tupel, kein drittes Element zum Entpacken.
        """
        monkeypatch.delenv("CLAUDE_TOOL_INPUT", raising=False)
        monkeypatch.delenv("CLAUDE_TOOL_NAME", raising=False)
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo hi"}})
        monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
        _tool_name, _tool_input, scratchpad_dir = egress._read_payload()
        assert scratchpad_dir is None


class TestIsOutsideSafeZoneScratchpadParamUnit:
    def test_target_inside_scratchpad_dir_param_is_safe(self, tmp_path):
        """Infrastruktur fuer AC-8/AC-9.
        GIVEN: ein Ziel innerhalb eines per Parameter uebergebenen
        scratchpad_dir (auch in einem Unterordner)
        WHEN: _is_outside_safe_zone() mit dem neuen optionalen
        scratchpad_dir-Parameter aufgerufen wird
        THEN: liefert False (sicher).
        Heute rot: die Funktion kennt den Parameter noch nicht (TypeError).
        """
        root = tmp_path / "project"
        root.mkdir()
        scratchpad = tmp_path / "scratchpad"
        scratchpad.mkdir()
        target = str(scratchpad / "sub" / "out.txt")
        cfg = {"extra_allowed_write_dirs": []}
        result = egress._is_outside_safe_zone(
            target, root, cfg, scratchpad_dir=str(scratchpad)
        )
        assert result is False

    def test_target_outside_scratchpad_dir_param_is_unsafe(self, tmp_path):
        """Infrastruktur fuer AC-9 -- Gegenprobe.
        GIVEN: ein Ziel AUSSERHALB des per Parameter uebergebenen
        scratchpad_dir
        WHEN: _is_outside_safe_zone() mit dem scratchpad_dir-Parameter
        aufgerufen wird
        THEN: liefert True (unsicher).
        Heute rot: die Funktion kennt den Parameter noch nicht (TypeError).
        """
        root = tmp_path / "project"
        root.mkdir()
        scratchpad = tmp_path / "scratchpad"
        scratchpad.mkdir()
        foreign = tmp_path / "foreign-scratchpad" / "leak.txt"
        cfg = {"extra_allowed_write_dirs": []}
        result = egress._is_outside_safe_zone(
            str(foreign), root, cfg, scratchpad_dir=str(scratchpad)
        )
        assert result is True
