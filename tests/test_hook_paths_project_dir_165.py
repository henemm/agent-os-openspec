"""Tests fuer #165 — Hook-Pfade an ${CLAUDE_PROJECT_DIR} verankern.

Gemeldet aus Meditationstimer: jede Nutzer-Nachricht brach ab mit

    can't open file '.../Meditationstimer iOS/Media/.claude/hooks/phase_listener.py'

Die Hook-Datei existierte — unter dem Projekt-Root. Der Eintrag in
settings.json war cwd-relativ (`python3 .claude/hooks/phase_listener.py`), und
Hook-Kommandos laufen im AKTUELLEN Arbeitsverzeichnis der Sitzung, nicht im
Projekt-Root (https://code.claude.com/docs/en/hooks). Stand die Sitzung in
einem Unterordner, zeigte der Pfad ins Leere.

Ein Test je "Expected Behavior"-Zeile aus docs/specs/hook-paths-project-dir.md.
"""

import json
import shlex
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import setup as setup_mod  # noqa: E402
from migrate_to_plugin import _anchor_command, _patch_settings, migrate  # noqa: E402

PLACEHOLDER = "${CLAUDE_PROJECT_DIR}"


# --- Helpers ---------------------------------------------------------------

def _make_project(tmp_path: Path, name: str = "My Project") -> Path:
    """Fake-Projekt — Name mit Leerzeichen, wie 'Meditationstimer iOS'."""
    proj = tmp_path / name
    (proj / ".claude" / "hooks").mkdir(parents=True)
    return proj


def _install_hook_files(proj: Path, *names: str) -> None:
    for n in names:
        (proj / ".claude" / "hooks" / n).write_text("# hook\n")


def _hook_commands(settings: dict) -> list[str]:
    out = []
    for entries in settings.get("hooks", {}).values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                out.append(hook["command"])
    return out


def _settings_with(*commands: str, event: str = "PreToolUse") -> dict:
    return {
        "hooks": {
            event: [{"matcher": "Bash", "hooks": [{"command": c} for c in commands]}]
        }
    }


# --- setup.py: Erzeugung ---------------------------------------------------

def test_generated_commands_use_project_dir_placeholder(tmp_path):
    """Kein erzeugtes Hook-Kommando ist cwd-relativ."""
    proj = _make_project(tmp_path)
    _install_hook_files(proj, "edit_gate.py", "bash_gate.py", "post_bash.py",
                        "phase_listener.py")

    setup_mod.generate_settings_json(proj, modules=[])

    settings = json.loads((proj / ".claude" / "settings.json").read_text())
    commands = _hook_commands(settings)
    assert commands, "Es wurde kein Hook-Kommando erzeugt"
    for cmd in commands:
        assert PLACEHOLDER in cmd, f"Kommando ohne Verankerung: {cmd}"
        assert "python3 .claude/hooks/" not in cmd, f"cwd-relativ: {cmd}"


def test_generated_commands_bake_in_no_absolute_project_path(tmp_path):
    """Der Projektpfad wird nicht eingebacken — sonst bricht Verschieben."""
    proj = _make_project(tmp_path)
    _install_hook_files(proj, "edit_gate.py")

    setup_mod.generate_settings_json(proj, modules=[])

    settings = json.loads((proj / ".claude" / "settings.json").read_text())
    for cmd in _hook_commands(settings):
        assert str(proj) not in cmd, f"Absoluter Projektpfad eingebacken: {cmd}"


def test_generated_commands_quote_the_placeholder(tmp_path):
    """Ordner mit Leerzeichen: der Platzhalter steht in Anfuehrungszeichen."""
    proj = _make_project(tmp_path, name="Meditationstimer iOS")
    _install_hook_files(proj, "phase_listener.py")

    setup_mod.generate_settings_json(proj, modules=[])

    settings = json.loads((proj / ".claude" / "settings.json").read_text())
    for cmd in _hook_commands(settings):
        assert f'"{PLACEHOLDER}/' in cmd, f"Platzhalter nicht gequotet: {cmd}"


# --- migrate_to_plugin.py: Reparatur --------------------------------------

def test_project_own_hook_command_is_anchored():
    """Projekteigener Hook (kein Plugin-Hook) wird verankert statt entfernt."""
    settings = _settings_with("python3 .claude/hooks/session_start.py",
                              event="SessionStart")

    changes = _patch_settings(settings, dry_run=False)

    assert len(changes) == 1
    assert _hook_commands(settings) == [
        f'python3 "{PLACEHOLDER}/.claude/hooks/session_start.py"'
    ]


def test_extra_arguments_survive_the_rewrite():
    """`qa_gate.py --hook-mode` behaelt sein Argument."""
    anchored = _anchor_command("python3 .claude/hooks/qa_gate.py --hook-mode")
    assert anchored == f'python3 "{PLACEHOLDER}/.claude/hooks/qa_gate.py" --hook-mode'


def test_env_prefix_survives_the_rewrite():
    """Vorangestellte Env-Zuweisungen bleiben erhalten."""
    anchored = _anchor_command(
        "WORKFLOW_CALLER=phase_listener python3 .claude/hooks/workflow.py status"
    )
    assert anchored == (
        f'WORKFLOW_CALLER=phase_listener python3 '
        f'"{PLACEHOLDER}/.claude/hooks/workflow.py" status'
    )


def test_absolute_path_is_anchored_too():
    """Eingebackener absoluter Pfad (auch mit Leerzeichen) wird verankert."""
    anchored = _anchor_command(
        'python3 "/Users/hem/Developer/My Project/.claude/hooks/session_start.py"'
    )
    assert anchored == f'python3 "{PLACEHOLDER}/.claude/hooks/session_start.py"'


def test_unquoted_absolute_path_with_space_is_anchored():
    """Der historische Normalfall: absoluter Pfad MIT Leerzeichen, OHNE Quotes.

    Genau so hat die alte `setup.py` geschrieben (`f"python3 {h}"`, h absolut,
    ungequotet). Ein halb ersetzter Pfad ist schlimmer als gar keiner: Das
    Kommando laeuft dann auf den Ordner vor dem Leerzeichen und der richtige
    Pfad landet als Argument — und das Werkzeug meldet trotzdem Erfolg.
    """
    anchored = _anchor_command(
        "python3 /Users/hem/Developer/Meditationstimer iOS/.claude/hooks/foo.py"
    )

    assert anchored == f'python3 "{PLACEHOLDER}/.claude/hooks/foo.py"'
    assert shlex.split(anchored) == [
        "python3", f"{PLACEHOLDER}/.claude/hooks/foo.py"
    ]


def test_unquoted_absolute_path_with_space_keeps_arguments():
    """Derselbe Fall mit Zusatzargument — genau zwei Tokens plus Argument."""
    anchored = _anchor_command(
        "python3 /Users/hem/My Projekt/.claude/hooks/qa_gate.py --hook-mode"
    )

    assert shlex.split(anchored) == [
        "python3", f"{PLACEHOLDER}/.claude/hooks/qa_gate.py", "--hook-mode"
    ]


def test_command_is_never_left_with_a_path_fragment():
    """Kein Rest des alten Pfads bleibt als eigenes Token stehen."""
    for raw in (
        "python3 /Users/hem/Developer/Meditationstimer iOS/.claude/hooks/foo.py",
        'python3 "/Users/hem/Developer/Meditationstimer iOS/.claude/hooks/foo.py"',
        "python3 ./relativ mit luecke/.claude/hooks/foo.py",
        "python3 .claude/hooks/foo.py",
    ):
        tokens = shlex.split(_anchor_command(raw))
        assert tokens == ["python3", f"{PLACEHOLDER}/.claude/hooks/foo.py"], raw


def test_absolute_interpreter_survives():
    """Ist der Interpreter selbst absolut geschrieben, bleibt er stehen.

    Adversary-Befund F004: Die links-verankerte Suche begann beim ERSTEN Token
    mit Pfad-Sigel — das war dann `/usr/bin/python3`, und der Interpreter wurde
    mitverschluckt. Das Kommando haengt danach am Ausfuehrbar-Bit der Hook-Datei
    statt an Python. Dafuer braucht es nicht einmal ein Leerzeichen im Pfad.
    """
    anchored = _anchor_command("/usr/bin/python3 /Users/hem/Projekt/.claude/hooks/x.py")

    assert shlex.split(anchored) == [
        "/usr/bin/python3", f"{PLACEHOLDER}/.claude/hooks/x.py"
    ]


def test_absolute_interpreter_with_env_prefix_and_argument():
    """Env-Praefix, absoluter Interpreter und Argument bleiben vollstaendig."""
    anchored = _anchor_command(
        "WF=1 /usr/bin/python3 /Users/hem/Projekt/.claude/hooks/x.py --flag"
    )

    assert shlex.split(anchored) == [
        "WF=1", "/usr/bin/python3", f"{PLACEHOLDER}/.claude/hooks/x.py", "--flag"
    ]


def test_absolute_argument_before_the_hook_path_survives():
    """Ein absolutes Argument VOR dem Hook-Pfad wird nicht einverleibt."""
    anchored = _anchor_command(
        "python3 /usr/bin/wrapper /pfad mit luecke/.claude/hooks/x.py"
    )

    assert shlex.split(anchored) == [
        "python3", "/usr/bin/wrapper", f"{PLACEHOLDER}/.claude/hooks/x.py"
    ]


@pytest.mark.parametrize("raw", [
    "python3 /Users/hem/env foo/.claude/hooks/x.py",
    "python3 /Users/hem/node modules/.claude/hooks/x.py",
    "python3 /Users/hem/python3 experimente/.claude/hooks/x.py",
])
def test_directory_named_like_an_interpreter_is_part_of_the_path(raw):
    """Ein Ordner, der heisst wie ein Interpreter, ist trotzdem ein Ordner.

    Adversary-Befund F006: Die Interpreter-Erkennung lief auf JEDES Token der
    Linkserweiterung. Ein Pfad wie `/Users/hem/env foo/…` brach deshalb
    auseinander — `/Users/hem/env` blieb als eigenes Token stehen, und Python
    versuchte diesen Ordner als Skript auszufuehren. Der Interpreter ist immer
    der Kopf des Aufrufs, nie ein Stueck mitten im Pfad.
    """
    anchored = _anchor_command(raw)

    assert shlex.split(anchored) == [
        "python3", f"{PLACEHOLDER}/.claude/hooks/x.py"
    ]


def test_bare_path_with_space_and_no_interpreter():
    """Kommando ohne Interpreter: der ganze Pfad ist das Kommando."""
    anchored = _anchor_command("/Users/hem/My Projekt/.claude/hooks/x.py")

    assert shlex.split(anchored) == [f"{PLACEHOLDER}/.claude/hooks/x.py"]


def test_absolute_interpreter_with_relative_spaced_path():
    """Absoluter Interpreter, Pfad mit Leerzeichen ohne Sigel: kein Rest."""
    anchored = _anchor_command("/usr/bin/python3 My Projekt/.claude/hooks/x.py")

    assert shlex.split(anchored) == [
        "/usr/bin/python3", f"{PLACEHOLDER}/.claude/hooks/x.py"
    ]


def test_tab_separated_prefix_survives():
    """Tabulator statt Leerzeichen vor dem Aufruf-Kopf.

    Adversary-Befund F008: `_head_start` trennte nur an Leerzeichen, der Rest
    des Codes auch an Tabulatoren. Die beiden Zaehlungen liefen auseinander,
    der Kopf wurde nie erkannt, und die Linkssuche loeschte Env-Praefix und
    Interpreter gleich mit.
    """
    anchored = _anchor_command("WF=1\tpython3 foo/.claude/hooks/x.py")

    assert shlex.split(anchored) == [
        "WF=1", "python3", f"{PLACEHOLDER}/.claude/hooks/x.py"
    ]


def test_left_scan_stops_at_a_shell_separator():
    """Die Linkssuche laeuft nicht ueber einen Shell-Operator hinweg.

    Adversary-Befund F009: Ohne Grenze verschluckte die Suche alles bis zum
    naechsten Pfad-Sigel — bei `echo hi; python3 bar/…` auch `hi; python3`.
    """
    anchored = _anchor_command("echo hi; python3 bar/.claude/hooks/a.py")

    assert anchored == (
        f'echo hi; python3 "{PLACEHOLDER}/.claude/hooks/a.py"'
    )


def test_unbalanced_quotes_leave_the_command_untouched():
    """Unpaarige Anfuehrungszeichen: nicht anfassen, statt kaputt zu machen.

    Adversary-Befund F007: Das fuehrende Quote blieb stehen, die Ersetzung
    brachte ihr eigenes mit — das Ergebnis war nicht mehr zerlegbar. Was nicht
    verlaesslich gelesen werden kann, wird nicht umgeschrieben.
    """
    raw = 'python3 "/Users/hem/My Projekt/.claude/hooks/x.py'

    assert _anchor_command(raw) == raw


def test_shell_separator_after_the_path_survives():
    """Ein Trennzeichen direkt hinter dem Pfad bleibt stehen.

    Die v2-Wrapper-Form endet mit `…/foo.py; fi`. Wird das Semikolon als Teil
    des Pfads verschluckt, entsteht `then python3 "…" fi` — syntaktisch kaputt.
    """
    raw = ("if [ -f /Users/hem/P/.claude/hooks/foo.py ]; "
           "then python3 /Users/hem/P/.claude/hooks/foo.py; fi")

    anchored = _anchor_command(raw)

    assert anchored == (
        f'if [ -f "{PLACEHOLDER}/.claude/hooks/foo.py" ]; '
        f'then python3 "{PLACEHOLDER}/.claude/hooks/foo.py"; fi'
    )


def test_preexisting_empty_entry_is_left_alone():
    """Ein Eintrag, der schon vorher leer war, wird nicht mitentfernt.

    Adversary-Befund F005: Das Aufraeumen griff breiter als noetig und nur im
    Apply-Lauf — der Trockenlauf sagte es nicht voraus.
    """
    settings = {"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": []},
        {"matcher": "Nix"},
        {"matcher": "Edit|Write", "hooks": [
            {"command": "python3 .claude/hooks/session_start.py"}
        ]},
    ]}}

    _patch_settings(settings, dry_run=False)

    assert [e.get("matcher") for e in settings["hooks"]["PreToolUse"]] == [
        "Bash", "Nix", "Edit|Write"
    ]


def test_dry_run_and_apply_report_the_same_changes():
    """Vorschau und Anwendung melden dasselbe — sonst ist die Vorschau wertlos."""
    def _fresh():
        return {"hooks": {"PreToolUse": [
            {"matcher": "Edit|Write", "hooks": [
                {"command": "python3 .claude/hooks/edit_gate.py"}
            ]},
            {"matcher": "Bash", "hooks": [
                {"command": "python3 .claude/hooks/session_start.py"}
            ]},
        ]}}

    preview = _patch_settings(_fresh(), dry_run=True)
    applied = _patch_settings(_fresh(), dry_run=False)

    assert preview == applied


def test_emptied_hook_entry_is_pruned():
    """Wird der letzte Hook eines Eintrags entfernt, bleibt kein leerer Rumpf."""
    settings = _settings_with("python3 .claude/hooks/edit_gate.py")

    _patch_settings(settings, dry_run=False)

    assert settings["hooks"]["PreToolUse"] == []


def test_entry_with_remaining_hooks_is_kept():
    """Ein Eintrag mit verbleibendem Hook behaelt Matcher und Inhalt."""
    settings = _settings_with("python3 .claude/hooks/edit_gate.py",
                              "python3 .claude/hooks/session_start.py")

    _patch_settings(settings, dry_run=False)

    entry = settings["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Bash"
    assert len(entry["hooks"]) == 1


def test_rewrite_is_idempotent():
    """Zweiter Lauf aendert nichts mehr."""
    once = _anchor_command("python3 .claude/hooks/session_start.py")
    assert _anchor_command(once) == once

    settings = _settings_with(once, event="SessionStart")
    assert _patch_settings(settings, dry_run=False) == []


def test_plugin_hooks_are_still_removed_not_anchored():
    """Bestehendes Verhalten: Plugin-Hooks verschwinden, sie werden nicht verankert."""
    settings = _settings_with("python3 .claude/hooks/edit_gate.py",
                              "python3 .claude/hooks/session_start.py")

    _patch_settings(settings, dry_run=False)

    assert _hook_commands(settings) == [
        f'python3 "{PLACEHOLDER}/.claude/hooks/session_start.py"'
    ]


def test_dry_run_changes_nothing():
    """Trockenlauf meldet, aber schreibt nicht."""
    settings = _settings_with("python3 .claude/hooks/session_start.py",
                              event="SessionStart")

    changes = _patch_settings(settings, dry_run=True)

    assert len(changes) == 1
    assert _hook_commands(settings) == ["python3 .claude/hooks/session_start.py"]


# --- settings.local.json ---------------------------------------------------

def test_local_settings_hooks_are_migrated(tmp_path, capsys):
    """settings.local.json wird mitgenommen, permissions bleibt unangetastet."""
    proj = _make_project(tmp_path)
    (proj / ".claude" / "settings.json").write_text(json.dumps(
        _settings_with("python3 .claude/hooks/session_start.py", event="SessionStart")
    ))
    local = proj / ".claude" / "settings.local.json"
    local.write_text(json.dumps({
        "permissions": {"allow": ["Bash(python3 .claude/hooks/workflow.py status)"]},
        "hooks": {"SessionStart": [{"hooks": [
            {"command": "python3 .claude/hooks/project_banner.py"}
        ]}]},
    }))

    migrate(proj, dry_run=False)

    result = json.loads(local.read_text())
    assert _hook_commands(result) == [
        f'python3 "{PLACEHOLDER}/.claude/hooks/project_banner.py"'
    ]
    # permissions ist kein Hook-Kommando und wird nicht umgeschrieben
    assert result["permissions"]["allow"] == [
        "Bash(python3 .claude/hooks/workflow.py status)"
    ]


def test_local_settings_without_hooks_is_untouched(tmp_path):
    """Keine Hooks in settings.local.json → Datei bleibt byte-gleich."""
    proj = _make_project(tmp_path)
    (proj / ".claude" / "settings.json").write_text(json.dumps(
        _settings_with("python3 .claude/hooks/session_start.py", event="SessionStart")
    ))
    local = proj / ".claude" / "settings.local.json"
    original = json.dumps({"permissions": {"allow": ["Bash"]}}, indent=2)
    local.write_text(original)

    migrate(proj, dry_run=False)

    assert local.read_text() == original


def test_broken_local_settings_does_not_abort_migration(tmp_path, capsys):
    """Unlesbares JSON: Warnung, settings.json wird trotzdem migriert."""
    proj = _make_project(tmp_path)
    settings_path = proj / ".claude" / "settings.json"
    settings_path.write_text(json.dumps(
        _settings_with("python3 .claude/hooks/session_start.py", event="SessionStart")
    ))
    (proj / ".claude" / "settings.local.json").write_text("{ kaputt")

    migrate(proj, dry_run=False)

    assert "WARNUNG" in capsys.readouterr().out
    result = json.loads(settings_path.read_text())
    assert _hook_commands(result) == [
        f'python3 "{PLACEHOLDER}/.claude/hooks/session_start.py"'
    ]


# --- Der gemeldete Fall ----------------------------------------------------

def test_reported_meditationstimer_case_is_repaired(tmp_path):
    """Der gemeldete Fall: 4 Plugin-Hooks weg, session_start.py verankert."""
    proj = _make_project(tmp_path, name="Meditationstimer")
    _install_hook_files(proj, "edit_gate.py", "bash_gate.py", "post_bash.py",
                        "phase_listener.py", "session_start.py")
    settings_path = proj / ".claude" / "settings.json"
    settings_path.write_text(json.dumps({"hooks": {
        "PreToolUse": [
            {"matcher": "Edit|Write", "hooks": [{"command": "python3 .claude/hooks/edit_gate.py"}]},
            {"matcher": "Bash", "hooks": [{"command": "python3 .claude/hooks/bash_gate.py"}]},
        ],
        "PostToolUse": [{"matcher": "Bash", "hooks": [{"command": "python3 .claude/hooks/post_bash.py"}]}],
        "UserPromptSubmit": [{"hooks": [{"command": "python3 .claude/hooks/phase_listener.py"}]}],
        "SessionStart": [{"hooks": [{"command": "python3 .claude/hooks/session_start.py"}]}],
    }}))

    migrate(proj, dry_run=False)

    remaining = _hook_commands(json.loads(settings_path.read_text()))
    assert remaining == [f'python3 "{PLACEHOLDER}/.claude/hooks/session_start.py"']
    # Kein einziges verbleibendes Kommando ist noch cwd-relativ
    assert not [c for c in remaining if "python3 .claude/hooks/" in c]
