"""Klartext-Gate: Stop-Hook prüft die Antwort an den Nutzer auf Git-Wörter (#582).

Der Hook läuft wie in Claude Code als eigener Prozess mit der Stop-Payload auf
stdin. Blockade = Exit 2 mit Begründung auf stderr; jeder andere Fall Exit 0.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "core" / "hooks" / "klartext_gate.py"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"


def _transcript(tmp_path: Path, frage, antwort: str) -> Path:
    pfad = tmp_path / "t.jsonl"
    zeilen = []
    if frage is not None:
        zeilen.append({"type": "user", "message": {"role": "user", "content": frage}})
    zeilen.append({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": antwort}]}})
    pfad.write_text("".join(json.dumps(z, ensure_ascii=False) + "\n" for z in zeilen),
                    encoding="utf-8")
    return pfad


def _run(tmp_path: Path, payload, env_extra=None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENSPEC_KLARTEXT", "CLAUDE_TOOL_NAME", "CLAUDE_TOOL_INPUT")}
    env.update(env_extra or {})
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK)], input=data, capture_output=True,
                          text=True, cwd=str(tmp_path), env=env, timeout=20)


def _stop(tmp_path: Path, frage, antwort: str, **extra) -> subprocess.CompletedProcess:
    pfad = _transcript(tmp_path, frage, antwort)
    payload = {"hook_event_name": "Stop", "transcript_path": str(pfad),
               "cwd": str(tmp_path), "last_assistant_message": antwort}
    env_extra = extra.pop("env", None)
    payload.update(extra)
    return _run(tmp_path, payload, env_extra)


# --- blockt ------------------------------------------------------------------

def test_blockt_bei_git_woertern(tmp_path):
    r = _stop(tmp_path, "nächstes Issue bitte",
              "Erledigt. Ich habe den Branch fix-1 angelegt, committet und einen PR gemergt.")
    assert r.returncode == 2, r.stderr
    assert "KLARTEXT" in r.stderr
    for wort in ("Branch", "PR", "committet", "gemergt"):
        assert wort in r.stderr, r.stderr
    assert "Henning" not in r.stderr


def test_blockt_einzelne_woerter(tmp_path):
    for satz in ("Läuft jetzt auf main.", "Die CI ist grün.", "Push ist durch.",
                 "Liegt im Worktree.", "Der Pull Request ist offen.", "Zwei Commits."):
        r = _stop(tmp_path, "wie weit?", satz)
        assert r.returncode == 2, f"{satz!r}: rc={r.returncode}"


def test_blockt_ohne_last_assistant_message_ueber_transkript(tmp_path):
    pfad = _transcript(tmp_path, "weiter", "Der Merge ist durch.")
    r = _run(tmp_path, {"transcript_path": str(pfad), "cwd": str(tmp_path)})
    assert r.returncode == 2, r.stderr


# --- frei bei Code, Wortteilen, Pfaden ---------------------------------------

def test_frei_bei_code_angaben(tmp_path):
    antwort = ("Der Fehler ist behoben. Geändert: `betrieb/deploy.sh`, Befehl `git push`.\n"
               "```\ngit commit -m x\ngit merge feature-branch\n```\nAlles läuft.")
    r = _stop(tmp_path, "nächstes Issue", antwort)
    assert r.returncode == 0, r.stderr


def test_frei_bei_wortteilen_und_pfaden(tmp_path):
    antwort = ("Die Prüfung (CIA) läuft, PRAXIS zeigt Commitment. Datei liegt unter "
               "docs/branch/x.md und fix-12-push; Seite https://example.com/pull/3/commits. "
               "Push-Benachrichtigungen kommen an, der Wirtschaftszweig wächst.")
    r = _stop(tmp_path, "Stand?", antwort)
    assert r.returncode == 0, r.stderr


# --- frei, wenn der Nutzer selbst fragt --------------------------------------

def test_frei_wenn_nutzer_selbst_fragt(tmp_path):
    r = _stop(tmp_path, "Was ist ein Branch?", "Ein Branch ist ein Arbeitszweig im Code.")
    assert r.returncode == 0, r.stderr


def test_harness_text_zaehlt_nicht_als_frage(tmp_path):
    """Eine Agenten-Meldung mit Git-Wörtern ist keine Frage des Nutzers."""
    frage = "<task-notification>Agent fertig: PR #5 gemergt, Branch gelöscht</task-notification>"
    r = _stop(tmp_path, frage, "Der PR ist gemergt.")
    assert r.returncode == 2, r.stderr


def test_werkzeug_ergebnis_wird_uebersprungen(tmp_path):
    pfad = tmp_path / "t.jsonl"
    zeilen = [
        {"type": "user", "message": {"content": "Wie heißt der Branch?"}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "1"}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Branch heißt x."}]}},
    ]
    pfad.write_text("".join(json.dumps(z) + "\n" for z in zeilen))
    r = _run(tmp_path, {"transcript_path": str(pfad), "last_assistant_message": "Branch heißt x."})
    assert r.returncode == 0, r.stderr


# --- Schleifenschutz, Schalter, fail-open ------------------------------------

def test_frei_bei_stop_hook_active(tmp_path):
    r = _stop(tmp_path, "x", "Branch und PR sind fertig.", stop_hook_active=True)
    assert r.returncode == 0, r.stderr


def test_frei_bei_abschaltung(tmp_path):
    for wert in ("0", "off", "false"):
        r = _stop(tmp_path, "x", "Branch und PR sind fertig.", env={"OPENSPEC_KLARTEXT": wert})
        assert r.returncode == 0, f"{wert}: {r.stderr}"
    r = _stop(tmp_path, "x", "Branch und PR sind fertig.", env={"OPENSPEC_KLARTEXT": "1"})
    assert r.returncode == 2


def test_fail_open_bei_kaputtem_transkript(tmp_path):
    pfad = tmp_path / "t.jsonl"
    pfad.write_bytes(b"{kaputt\n\xff\xfe nicht json\n[1,2]\n")
    r = _run(tmp_path, {"transcript_path": str(pfad)})
    assert r.returncode == 0, r.stderr
    r = _run(tmp_path, {"transcript_path": str(tmp_path / "fehlt.jsonl")})
    assert r.returncode == 0, r.stderr


def test_fail_open_bei_kaputter_payload(tmp_path):
    for payload in ("", "{kaputt", "[]", json.dumps({"transcript_path": 5}),
                    json.dumps({"last_assistant_message": ["Branch"]})):
        r = _run(tmp_path, payload)
        assert r.returncode == 0, f"{payload!r}: {r.stderr}"


def test_langes_transkript_liest_nur_das_ende(tmp_path):
    pfad = tmp_path / "t.jsonl"
    fueller = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "x" * 1000}]}}) + "\n"
    with open(pfad, "w") as f:
        f.write(json.dumps({"type": "user", "message": {"content": "Branch?"}}) + "\n")
        f.write(fueller * 3000)  # ~3 MB, älter als das Lesefenster
        f.write(json.dumps({"type": "user", "message": {"content": "Stand?"}}) + "\n")
    r = _run(tmp_path, {"transcript_path": str(pfad), "last_assistant_message": "PR ist offen."})
    assert r.returncode == 2, r.stderr


# --- Registrierung -----------------------------------------------------------

def test_registriert_unter_stop():
    data = json.loads(HOOKS_JSON.read_text())
    befehle = [h["command"] for g in data["hooks"]["Stop"] for h in g["hooks"]]
    assert "${CLAUDE_PLUGIN_ROOT}/core/hooks/klartext_gate.py" in befehle
    assert os.access(HOOK, os.X_OK)
