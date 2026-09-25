"""Footer-Gate: deterministische Pruefung der ❗Du-Fusszeile (Issue #234).

Fundfall (2026-09-25, Workflow `feat-12-destatis-preise`): Der Fliesstext einer
Antwort nannte korrekt `/50-implement #12`, die ❗Du-Fusszeile aber
`/40-tdd-red #12` — den bereits erledigten Befehl. Die Fusszeile ist die einzige
Zeile, die der PO als „das tippe ich jetzt" liest. Vier Vorgaenger-Fixes
(#174/#209/#213/#221) haben ausschliesslich Prompt-Text verschaerft; die
Fehlerklasse kam jedes Mal zurueck.

`workflow.next_step()` kennt den korrekten Schritt bereits deterministisch aus
dem State. Ein neuer Stop-Hook `core/hooks/footer_gate.py` gleicht die Fusszeile
mechanisch dagegen ab und erzwingt bei Abweichung per Exit 2 eine Korrektur.

Tragende Anforderung ist NICHT die Erkennungsrate, sondern Fail-open: der Hook
laeuft im Plugin-Modus bei jedem Turn-Ende in jedem Konsumenten-Projekt. Ein
falsch-positiver Exit 2 oder ein Absturz wuerde dort jedes Turn-Ende stoeren.
Deshalb hat jeder Ausweichfall eine eigene AC.

Belegte Doku-Grundlagen (https://code.claude.com/docs/en/hooks, geprueft
2026-09-25):
- `Stop` → Can block? **Yes**; Exit 2 „Prevents Claude from stopping, continues
  the conversation".
- `last_assistant_message` liegt der Stop-Payload strukturiert bei.
- `prompt_id` (UUID des laufenden User-Prompts) ist ein gemeinsames Eingabefeld
  und damit die Turn-Kennung fuer den Schleifenschutz.
- `stop_hook_active` kommt in der Doku NICHT vor. Der Schleifenschutz darf sich
  deshalb nicht darauf stuetzen — `test_second_run_same_turn_exits_zero` und
  `test_loop_guard_works_without_prompt_id` pruefen ihn ohne dieses Feld.

ACs laut docs/specs/fix-234-footer-gate.md (AC-1 bis AC-10). Zusaetzlich zwei
Tests ohne eigene AC, die eine Luecke in der Beweisfuehrung schliessen (vom
PO-Briefing angemerkt: kaputte Eingabedaten selbst waren nicht abgedeckt):
`test_malformed_stdin_payload_exits_zero` und
`test_loop_guard_works_without_prompt_id`.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import workflow  # noqa: E402

FOOTER_GATE = HOOKS_DIR / "footer_gate.py"

WF_NAME = "fix-234-footer-command"
PROMPT_ID = "11111111-2222-3333-4444-555555555555"


# --- Helpers ---------------------------------------------------------------

def _project(tmp_path: Path, *, phase: str = "phase6_implement",
             corrupt: bool = False, active: bool = True, **fields) -> Path:
    """Main-Repo (.git als Verzeichnis -> kein Worktree) mit einem Workflow."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf_file = wf_dir / f"{WF_NAME}.json"
    if corrupt:
        wf_file.write_text('{"name": "fix-234-footer-command", "current_phase"')
    else:
        data = {"name": WF_NAME, "workflow_type": "feature", "current_phase": phase}
        data.update(fields)
        wf_file.write_text(json.dumps(data))
    if active:
        (tmp_path / ".claude" / "active_workflow").write_text(WF_NAME)
    return tmp_path


def _message(marker_line: str) -> str:
    """Nachbildung einer echten Abschlussnachricht inkl. nachfolgender ⚙-Zeile.

    Die Marker-Zeile ist absichtlich NICHT die letzte Zeile — in echten
    Nachrichten folgt darunter immer die ⚙-Zeile. Der Hook muss die letzte
    *passende* Zeile finden, nicht die letzte Zeile.
    """
    return (
        "Phase 5 (TDD RED) abgeschlossen.\n\n"
        "**Gesichert auf der Platte:** Testdatei und RED-Beleg liegen im Repo.\n\n"
        f"{marker_line}\n"
        "⚙ /40-tdd-red · agent-os-openspec 3.30.4"
    )


def _du_line(command: str) -> str:
    return f"❗ Du: `{command}` — der naechste Pflicht-Schritt"


def _run_hook(project: Path, message: "str | None" = None, *,
              prompt_id: "str | None" = PROMPT_ID,
              active_env: "str | None" = WF_NAME,
              extra_env: "dict | None" = None,
              raw_payload: "str | None" = None) -> subprocess.CompletedProcess:
    """Startet footer_gate.py als Subprozess, so wie Claude Code es tut."""
    assert FOOTER_GATE.exists(), (
        f"RED erwartet: {FOOTER_GATE.relative_to(REPO_ROOT)} existiert noch nicht"
    )
    if raw_payload is None:
        payload = {
            "session_id": "sess-234",
            "hook_event_name": "Stop",
            "cwd": str(project),
            "last_assistant_message": message,
        }
        if prompt_id is not None:
            payload["prompt_id"] = prompt_id
        raw_payload = json.dumps(payload)
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env.pop("OPENSPEC_FRAMEWORK", None)
    if active_env:
        env["OPENSPEC_ACTIVE_WORKFLOW"] = active_env
    else:
        env.pop("OPENSPEC_ACTIVE_WORKFLOW", None)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, str(FOOTER_GATE)],
        input=raw_payload, capture_output=True, text=True, env=env,
        cwd=str(project),
    )


# --- AC-1 / AC-2: der eigentliche Abgleich ---------------------------------

def test_mismatch_blocks_with_both_commands_in_stderr(tmp_path):
    """AC-1: Fusszeile nennt /40-tdd-red, State verlangt /50-implement -> Exit 2."""
    project = _project(tmp_path, phase="phase6_implement")
    result = _run_hook(project, _message(_du_line("/40-tdd-red #234")))
    assert result.returncode == 2, (
        f"Exit 2 erwartet, war {result.returncode}. stderr={result.stderr!r}"
    )
    assert "/40-tdd-red" in result.stderr
    assert "/50-implement" in result.stderr


def test_matching_footer_exits_zero(tmp_path):
    """AC-2: Fusszeile nennt bereits den korrekten Befehl -> Exit 0."""
    project = _project(tmp_path, phase="phase6_implement")
    result = _run_hook(project, _message(_du_line("/50-implement #234")))
    assert result.returncode == 0, f"stderr={result.stderr!r}"


# --- AC-3 bis AC-8: Fail-open (die risikotragende Seite) --------------------

def test_no_active_workflow_exits_zero(tmp_path):
    """AC-3: Kein aufloesbarer aktiver Workflow -> Exit 0."""
    project = _project(tmp_path, phase="phase6_implement", active=False)
    result = _run_hook(project, _message(_du_line("/40-tdd-red #234")),
                       active_env=None)
    assert result.returncode == 0, f"stderr={result.stderr!r}"


def test_phase8_complete_exits_zero(tmp_path):
    """AC-4: phase8_complete -> next_step() ist None -> Exit 0."""
    project = _project(tmp_path, phase="phase8_complete")
    result = _run_hook(project, _message(_du_line("/40-tdd-red #234")))
    assert result.returncode == 0, f"stderr={result.stderr!r}"


def test_corrupt_workflow_state_exits_zero(tmp_path):
    """AC-5: Kaputtes Workflow-JSON -> Exit 0, kein unbehandelter Absturz."""
    project = _project(tmp_path, corrupt=True)
    result = _run_hook(project, _message(_du_line("/40-tdd-red #234")))
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert "Traceback" not in result.stderr


def test_framework_disabled_exits_zero(tmp_path):
    """AC-6: framework_disabled() -> Exit 0, trotz abweichender Fusszeile."""
    project = _project(tmp_path, phase="phase6_implement")
    result = _run_hook(project, _message(_du_line("/40-tdd-red #234")),
                       extra_env={"OPENSPEC_FRAMEWORK": "off"})
    assert result.returncode == 0, f"stderr={result.stderr!r}"


def test_no_du_line_exits_zero(tmp_path):
    """AC-7: Keine ❗Du-/‼️Du-Zeile in der Nachricht -> Exit 0."""
    project = _project(tmp_path, phase="phase6_implement")
    message = _message(
        "ℹ️ Nichts zu tun: Ich warte auf einen Hintergrund-Agenten — "
        "danach: /40-tdd-red #234"
    )
    result = _run_hook(project, message)
    assert result.returncode == 0, f"stderr={result.stderr!r}"


def test_non_slash_next_step_exits_zero(tmp_path):
    """AC-8: next_step() liefert einen Freitext-Schritt (Freigabe) -> Exit 0."""
    project = _project(tmp_path, phase="phase3_spec",
                       spec_file="docs/specs/fix-234-footer-gate.md")
    result = _run_hook(project, _message(_du_line("/40-tdd-red #234")))
    assert result.returncode == 0, f"stderr={result.stderr!r}"


# --- AC-9: Schleifenschutz --------------------------------------------------

def test_second_run_same_turn_exits_zero(tmp_path):
    """AC-9: Zweiter Lauf fuer denselben Turn korrigiert nicht erneut.

    Exit 2 setzt den Turn laut Doku fort — ohne diesen Schutz entstuende eine
    Endlosschleife. Geprueft ohne `stop_hook_active`: der eigene Zaehler traegt
    die Garantie allein.
    """
    project = _project(tmp_path, phase="phase6_implement")
    message = _message(_du_line("/40-tdd-red #234"))
    first = _run_hook(project, message)
    assert first.returncode == 2, (
        f"Erster Lauf muss blocken, war {first.returncode}. stderr={first.stderr!r}"
    )
    second = _run_hook(project, message)
    assert second.returncode == 0, (
        f"Zweiter Lauf desselben Turns muss durchlassen, war {second.returncode}"
    )


# --- AC-10: die neue Huelle in workflow.py ----------------------------------

def test_expected_footer_command_matches_next_step_plus_issue():
    """AC-10: expected_footer_command() liefert next_step() + Issue-Nummer."""
    assert hasattr(workflow, "expected_footer_command"), (
        "RED erwartet: workflow.expected_footer_command() existiert noch nicht"
    )
    data = {"name": WF_NAME, "current_phase": "phase6_implement"}
    assert workflow.expected_footer_command(data) == "/50-implement #234"


# --- Zusatzabdeckung ohne eigene AC (Luecke aus dem PO-Briefing) ------------

def test_malformed_stdin_payload_exits_zero(tmp_path):
    """Kaputte Stop-Payload selbst (kein gueltiges JSON) -> Exit 0.

    Die ACs decken Fehler beim Lesen des Workflow-States ab, nicht Fehler beim
    Lesen der Payload. Genau dort liegt aber der Blast Radius: ein Absturz vor
    dem State-Zugriff wuerde bei jedem Turn-Ende auftreten.
    """
    project = _project(tmp_path, phase="phase6_implement")
    result = _run_hook(project, raw_payload="{ kein gueltiges JSON")
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert "Traceback" not in result.stderr


def test_loop_guard_works_without_prompt_id(tmp_path):
    """Schleifenschutz auch ohne `prompt_id` (Claude Code < v2.1.196).

    `prompt_id` ist laut Doku erst ab v2.1.196 vorhanden. Faellt es weg, darf
    der Schutz nicht ausfallen — sonst blockt das Gate denselben Turn endlos.
    """
    project = _project(tmp_path, phase="phase6_implement")
    message = _message(_du_line("/40-tdd-red #234"))
    first = _run_hook(project, message, prompt_id=None)
    assert first.returncode == 2, (
        f"Erster Lauf muss blocken, war {first.returncode}. stderr={first.stderr!r}"
    )
    second = _run_hook(project, message, prompt_id=None)
    assert second.returncode == 0, (
        f"Zweiter Lauf desselben Turns muss durchlassen, war {second.returncode}"
    )


# --- Gegenpruefung: zwei Fail-open-Defekte der ersten Fassung (BROKEN) ------
#
# F001 (Falsch-Positiv, CRITICAL): Der erste Slash-Treffer der ZEILE gewann —
# stand ein Dateipfad oder eine URL vor dem Befehl, gewann der Pfad
# (`/specs` statt `/50-implement`). Eine Fusszeile mit dem KORREKTEN Befehl
# wurde dadurch blockiert.
#
# F002 (Schleifenschutz wirkungslos ohne `prompt_id`): Die Ersatzkennung ist
# ein Hash der Antwort. Korrigiert Claude die Fusszeile, aendert sich der Text
# und damit die Kennung — der naechste Lauf blockt erneut, unbegrenzt. Die
# bestehenden Schleifenschutz-Tests schicken zweimal DENSELBEN Text und
# konnten das nicht sehen.

def _state_file(project: Path) -> Path:
    return project / ".claude" / "footer_gate_state.json"


def test_path_before_command_does_not_block(tmp_path):
    """F001: Dateipfad vor dem korrekten Befehl -> Exit 0 (AC-2 bleibt gewahrt)."""
    project = _project(tmp_path, phase="phase6_implement")
    message = _message(
        "❗ Du: siehe docs/specs/fix-234-footer-gate.md, dann `/50-implement #234`"
    )
    result = _run_hook(project, message)
    assert result.returncode == 0, (
        f"Fusszeile nennt den korrekten Befehl, Exit 0 erwartet, war "
        f"{result.returncode}. stderr={result.stderr!r}"
    )


def test_url_in_du_line_does_not_block(tmp_path):
    """F001: URL vor dem korrekten Befehl -> Exit 0 (`//` darf nicht treffen)."""
    project = _project(tmp_path, phase="phase6_implement")
    message = _message(
        "❗ Du: siehe https://example.com/foo — dann `/50-implement #234`"
    )
    result = _run_hook(project, message)
    assert result.returncode == 0, (
        f"Exit 0 erwartet, war {result.returncode}. stderr={result.stderr!r}"
    )


def test_mismatch_with_path_before_command_still_blocks(tmp_path):
    """Gegenprobe zu F001: der Fix darf die Erkennung nicht abschalten."""
    project = _project(tmp_path, phase="phase6_implement")
    message = _message(
        "❗ Du: siehe docs/specs/x.md, dann `/40-tdd-red #234`"
    )
    result = _run_hook(project, message)
    assert result.returncode == 2, (
        f"Exit 2 erwartet, war {result.returncode}. stderr={result.stderr!r}"
    )
    assert "/40-tdd-red" in result.stderr
    assert "/50-implement" in result.stderr


def test_loop_guard_bounds_blocks_without_prompt_id(tmp_path):
    """F002: ohne `prompt_id` hoechstens eine Blockade je Zeitfenster.

    Zwei Laeufe mit UNTERSCHIEDLICHEM Text — genau der Fall, den die
    Hash-Ersatzkennung nicht erkennt, weil Claudes Korrekturversuch den Text
    veraendert.
    """
    project = _project(tmp_path, phase="phase6_implement")
    first = _run_hook(project, _message(_du_line("/40-tdd-red #234")),
                      prompt_id=None)
    assert first.returncode == 2, (
        f"Erster Lauf muss blocken, war {first.returncode}. stderr={first.stderr!r}"
    )
    second = _run_hook(
        project,
        _message(_du_line("/40-tdd-red #234")) + "\n\nNachtrag: anderer Text.",
        prompt_id=None,
    )
    assert second.returncode == 0, (
        f"Zweiter Lauf im Zeitfenster muss durchlassen, war {second.returncode}. "
        f"stderr={second.stderr!r}"
    )


def test_loop_guard_window_expires(tmp_path):
    """F002: die Grenze ist ein Fenster, kein dauerhaftes Abschalten."""
    import footer_gate  # noqa: E402 — nur fuer die Fenstergroesse

    project = _project(tmp_path, phase="phase6_implement")
    first = _run_hook(project, _message(_du_line("/40-tdd-red #234")),
                      prompt_id=None)
    assert first.returncode == 2, f"stderr={first.stderr!r}"

    state = json.loads(_state_file(project).read_text())
    expired = datetime.now() - timedelta(
        seconds=footer_gate._LOOP_WINDOW_SECONDS + 10
    )
    state["last_block_at"] = expired.isoformat()
    _state_file(project).write_text(json.dumps(state))

    second = _run_hook(
        project,
        _message(_du_line("/40-tdd-red #234")) + "\n\nNachtrag: anderer Text.",
        prompt_id=None,
    )
    assert second.returncode == 2, (
        f"Nach Ablauf des Fensters muss wieder geblockt werden, war "
        f"{second.returncode}. stderr={second.stderr!r}"
    )


# --- Zweite Gegenpruefung: F003 / F004 -------------------------------------
#
# F003 (Falsch-Positiv): Die Zeile darf MEHRERE Slash-Befehle enthalten — der
# erste ist nicht zwangslaeufig der gemeinte ("nicht mehr `/40-tdd-red`,
# sondern `/50-implement`"). Regel laut PO-Entscheidung: blockiert wird nur,
# wenn der erwartete Befehl unter KEINEM Treffer der Zeile ist. Bewusst in
# Kauf genommen: eine Zeile, die den erwarteten Befehl irgendwo enthaelt, aber
# auf einen anderen zeigt, wird durchgelassen — Fail-open ist die tragende
# Anforderung.
#
# F004: Ein Zeitstempel in der ZUKUNFT (kaputte Zustandsdatei, Uhr-Drift)
# machte das Schleifenschutz-Fenster dauerhaft wahr und schaltete das Gate
# still ab.

def test_correct_command_after_other_command_does_not_block(tmp_path):
    """F003: erwarteter Befehl steht hinter einem anderen -> Exit 0."""
    project = _project(tmp_path, phase="phase6_implement")
    message = _message(
        "❗ Du: nicht mehr `/40-tdd-red`, sondern `/50-implement #234`"
    )
    result = _run_hook(project, message)
    assert result.returncode == 0, (
        f"Exit 0 erwartet, war {result.returncode}. stderr={result.stderr!r}"
    )


def test_markdown_link_to_other_command_does_not_block(tmp_path):
    """F003: Markdown-Link auf einen anderen Befehl davor -> Exit 0."""
    project = _project(tmp_path, phase="phase6_implement")
    message = _message(
        "❗ Du: [nicht mehr aktuell](/40-tdd-red) — jetzt: `/50-implement #234`"
    )
    result = _run_hook(project, message)
    assert result.returncode == 0, (
        f"Exit 0 erwartet, war {result.returncode}. stderr={result.stderr!r}"
    )


def test_absolute_path_before_command_does_not_block(tmp_path):
    """F003: absoluter Pfad davor -> Exit 0 (bisherige Known Limitation)."""
    project = _project(tmp_path, phase="phase6_implement")
    message = _message("❗ Du: /root/pfad.txt lesen, dann `/50-implement #234`")
    result = _run_hook(project, message)
    assert result.returncode == 0, (
        f"Exit 0 erwartet, war {result.returncode}. stderr={result.stderr!r}"
    )


def test_future_block_timestamp_does_not_disable_gate(tmp_path):
    """F004: Zeitstempel in der Zukunft darf das Gate nicht stilllegen."""
    project = _project(tmp_path, phase="phase6_implement")
    _state_file(project).parent.mkdir(parents=True, exist_ok=True)
    _state_file(project).write_text(json.dumps({
        "last_turn_id": "sha256:fremde-kennung",
        "last_block_at": (datetime.now() + timedelta(days=3650)).isoformat(),
    }))
    result = _run_hook(project, _message(_du_line("/40-tdd-red #234")),
                       prompt_id=None)
    assert result.returncode == 2, (
        f"Gate muss trotz Zukunfts-Zeitstempel wirksam bleiben, war "
        f"{result.returncode}. stderr={result.stderr!r}"
    )


def test_only_wrong_command_still_blocks(tmp_path):
    """Gegenprobe zu F003: die Erkennung darf nicht verlorengehen."""
    project = _project(tmp_path, phase="phase6_implement")
    message = _message("❗ Du: `/40-tdd-red #234` — der naechste Schritt")
    result = _run_hook(project, message)
    assert result.returncode == 2, (
        f"Exit 2 erwartet, war {result.returncode}. stderr={result.stderr!r}"
    )
    assert "/40-tdd-red" in result.stderr
    assert "/50-implement" in result.stderr
