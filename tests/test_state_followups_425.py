"""Folgebefunde aus #422: Fehlalarm beim Ersetzen, lange Zielnamen,
unsichtbarer Token-Fehler — #425.

Spec: docs/specs/fix-425-state-reader-followups.md

- F001: `_read_state_bytes` wertet `st_nlink == 0` (Datei nach dem Öffnen per
  `os.replace` ersetzt) als harten Verweis. Nur `nlink > 1` ist einer.
- F002: `_atomic_write_at` baut den tmp-Namen aus dem Zielnamen — ab 234
  Zeichen `OSError 63 File name too long`.
- F003: `override_token._save_tokens` schluckt `UnsafeStateError`,
  `phase_listener` meldet trotzdem „Override token created".

Richtungen: Bei „hard"/„symlink_file" bricht der atomare Schreiber den
Verweis (neuer Inode) — dort gibt es auch nach dem Fix keine Ausnahme, das
Verweisziel bleibt byte-gleich. Einen Schreibfund (UnsafeStateError) gibt es
nur, wenn ein ORDNER der Kette ein Verweis ist („symlink_dir"/
„claude_symlink"; für Dateien direkt unter `.claude` ist das dasselbe).

Import-Strategie: neue APIs per getattr, damit jeder Test einzeln RED wird.
"""

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
for _p in (str(HOOKS_DIR), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hook_utils  # noqa: E402
from test_state_reader_source_416 import RICHTUNGEN  # noqa: E402
from test_state_files_source_422 import (  # noqa: E402
    WF, _sandbox, _verweis, _run_py, _hook_env, _out, _token_json,
    _kein_traceback,
)

DATEI_RICHTUNGEN = ("hard", "symlink_file")
ORDNER_RICHTUNGEN = ("symlink_dir", "claude_symlink")
TOKEN = "user_override_token.json"
TMP_NAME = re.compile(r"^\.[0-9a-f]{16}\.tmp$")


def _require_api(*names):
    """Neue hook_utils-API holen; fehlt sie, klarer Fehlschlag statt AttributeError."""
    found = []
    for name in names:
        obj = getattr(hook_utils, name, None)
        if obj is None:
            pytest.fail(f"hook_utils.{name} fehlt (#425)")
        found.append(obj)
    return found[0] if len(found) == 1 else tuple(found)


def _tmp_reste(ordner: Path) -> list:
    return sorted(n for n in os.listdir(ordner) if n.endswith(".tmp"))


# --------------------------------------------------------------------- #
# F001 — AC-1, AC-2, AC-3, AC-13
# --------------------------------------------------------------------- #

def test_f001_nlink0_liefert_alten_inhalt(tmp_path):
    """AC-1: fd geöffnet, danach os.replace → nlink 0 → alter Inhalt."""
    read_checked_fd = _require_api("_read_checked_fd")
    root = _sandbox(tmp_path)
    pfad = root / ".claude" / "stop_lock.json"
    pfad.write_bytes(b'{"stand": "alt"}')
    fd = hook_utils._open_state_fd(pfad, root)
    try:
        neu = pfad.with_name("neu.json")
        neu.write_bytes(b'{"stand": "neu"}')
        os.replace(neu, pfad)
        assert os.fstat(fd).st_nlink == 0, "Nachstellung: nlink nach Ersetzen nicht 0"
    except BaseException:
        os.close(fd)
        raise
    assert read_checked_fd(fd, pfad) == b'{"stand": "alt"}'


def test_f001_nlink2_bleibt_unsafe_state_error(tmp_path):
    """AC-2: zweiter harter Verweis bleibt Fund — über beide Wege."""
    read_checked_fd = _require_api("_read_checked_fd")
    root = _sandbox(tmp_path)
    pfad = root / ".claude" / "stop_lock.json"
    pfad.write_bytes(b'{"enabled": false}')
    os.link(pfad, root / "docs" / "zweiter_name")
    assert os.stat(pfad).st_nlink == 2

    fd = hook_utils._open_state_fd(pfad, root)
    with pytest.raises(hook_utils.UnsafeStateError, match="Linkzahl 2"):
        read_checked_fd(fd, pfad)
    with pytest.raises(hook_utils.UnsafeStateError,
                       match="harter Verweis, Linkzahl 2"):
        hook_utils._read_state_bytes(pfad, root)


def test_f001_normaldatei_und_verzeichnis_wie_bisher(tmp_path, monkeypatch):
    """AC-3: nlink 1 → Inhalt, Verzeichnis → Fund; _read_state_bytes = Öffnen + Prüfen."""
    read_checked_fd = _require_api("_read_checked_fd")
    root = _sandbox(tmp_path)
    pfad = root / ".claude" / "stop_lock.json"
    pfad.write_bytes(b'{"enabled": true}')
    ordner = root / ".claude" / "ordner"
    ordner.mkdir()

    assert hook_utils._read_state_bytes(pfad, root) == b'{"enabled": true}'
    assert read_checked_fd(hook_utils._open_state_fd(pfad, root), pfad) \
        == b'{"enabled": true}'
    with pytest.raises(hook_utils.UnsafeStateError, match="keine normale Datei"):
        hook_utils._read_state_bytes(ordner, root)

    # Summe: _read_state_bytes gibt den Deskriptor an _read_checked_fd weiter
    aufrufe = []

    def _attrappe(fd, path):
        aufrufe.append(path)
        os.close(fd)
        return b"ATTRAPPE"
    monkeypatch.setattr(hook_utils, "_read_checked_fd", _attrappe)
    assert hook_utils._read_state_bytes(pfad, root) == b"ATTRAPPE"
    assert [str(p) for p in aufrufe] == [str(pfad)]


def test_f001_paralleler_ersetzer_ohne_fehlalarm(tmp_path):
    """AC-13: 4 Schreiber ersetzen fortlaufend, 500 Lesezugriffe ohne Fund."""
    root = _sandbox(tmp_path)
    pfad = root / ".claude" / "footer_gate_state.json"
    pad = "x" * 2000
    hook_utils.atomic_write_json(pfad, {"w": -1, "n": 0, "pad": pad}, root=root)
    stop = threading.Event()

    def _schreiber(w):
        n = 0
        while not stop.is_set():
            n += 1
            hook_utils.atomic_write_json(pfad, {"w": w, "n": n, "pad": pad},
                                         root=root)

    threads = [threading.Thread(target=_schreiber, args=(w,)) for w in range(4)]
    for t in threads:
        t.start()
    fehlalarme, unvollstaendig = 0, []
    try:
        for _ in range(500):
            try:
                data = hook_utils.read_state_json(pfad, root)
            except hook_utils.UnsafeStateError:
                fehlalarme += 1
                continue
            except ValueError as exc:  # halber Stand → JSONDecodeError
                unvollstaendig.append(repr(exc)[:80])
                continue
            if not (isinstance(data, dict) and data.get("pad") == pad
                    and data.get("w") in (-1, 0, 1, 2, 3)):
                unvollstaendig.append(repr(data)[:80])
    finally:
        stop.set()
        for t in threads:
            t.join()
    assert fehlalarme == 0, f"{fehlalarme} von 500 Lesezugriffen: UnsafeStateError"
    assert not unvollstaendig, f"unvollständige Stände: {unvollstaendig[:3]}"


# --------------------------------------------------------------------- #
# F002 — AC-4, AC-5
# --------------------------------------------------------------------- #

def test_f002_ziel_mit_255_zeichen_ist_schreib_und_lesbar(tmp_path):
    """AC-4: 255 Zeichen Zielname, Text und JSON, mit root."""
    root = _sandbox(tmp_path)
    text_ziel = root / ".claude" / ("t" * 250 + ".json")
    json_ziel = root / ".claude" / ("j" * 250 + ".json")
    assert len(text_ziel.name) == len(json_ziel.name) == 255
    fehler = []
    try:
        hook_utils.atomic_write_text(text_ziel, "hallo", root=root)
        if hook_utils.read_state_text(text_ziel, root) != "hallo":
            fehler.append("Text: Inhalt stimmt nicht")
    except OSError as exc:
        fehler.append(f"Text: {type(exc).__name__}: {exc}")
    try:
        hook_utils.atomic_write_json(json_ziel, {"a": 1}, root=root)
        if hook_utils.read_state_json(json_ziel, root) != {"a": 1}:
            fehler.append("JSON: Inhalt stimmt nicht")
    except OSError as exc:
        fehler.append(f"JSON: {type(exc).__name__}: {exc}")
    assert not fehler, fehler


def test_f002_kein_tmp_rest_und_tmp_name_zielunabhaengig(tmp_path, monkeypatch):
    """AC-5: kein *.tmp nach Erfolg/Fehlschlag; tmp-Name `.`+16 Hex+`.tmp`."""
    root = _sandbox(tmp_path)
    claude = root / ".claude"
    tmp_namen = []
    echtes_open, echtes_fdopen = os.open, os.fdopen

    def _open_spion(path, flags, *args, **kwargs):
        if flags & os.O_CREAT and kwargs.get("dir_fd") is not None:
            tmp_namen.append(str(path))
        return echtes_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", _open_spion)

    fehler = []
    for ziel in ("k.json", "l" * 250 + ".json"):
        try:
            hook_utils.atomic_write_text(claude / ziel, "x", root=root)
        except OSError as exc:
            fehler.append(f"Erfolgsfall {ziel[:12]}…: {type(exc).__name__}: {exc}")

    def _fdopen_kaputt(fd, *args, **kwargs):
        os.close(fd)
        raise OSError(5, "Schreiben der Nutzlast fehlgeschlagen (Test)")
    monkeypatch.setattr(os, "fdopen", _fdopen_kaputt)
    for ziel in ("m.json", "n" * 250 + ".json"):
        with pytest.raises(OSError):
            hook_utils.atomic_write_text(claude / ziel, "x", root=root)
    monkeypatch.setattr(os, "fdopen", echtes_fdopen)

    if _tmp_reste(claude):
        fehler.append(f"tmp-Reste: {[n[:30] for n in _tmp_reste(claude)]}")
    if len(tmp_namen) != 4:
        fehler.append(f"{len(tmp_namen)} tmp-Anlagen beobachtet (erwartet 4)")
    for name in tmp_namen:
        if not (TMP_NAME.match(name) and len(name) == 21):
            fehler.append(f"tmp-Name nicht zielunabhängig: {name[:40]!r} "
                          f"({len(name)} Zeichen)")
    assert not fehler, fehler


# --------------------------------------------------------------------- #
# F003 — AC-6, AC-7: override_token reicht UnsafeStateError durch
# --------------------------------------------------------------------- #

def _ergebnis_zeile(r: subprocess.CompletedProcess) -> str:
    zeilen = r.stdout.strip().splitlines()
    return zeilen[-1] if zeilen else ""


@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_f003_create_token_wirft_bei_verweis(tmp_path, richtung):
    """AC-6: Ordner-Verweis → UnsafeStateError; Datei-Verweis wird gebrochen
    (keine Ausnahme). In beiden Fällen bleibt das Verweisziel byte-gleich."""
    root = _sandbox(tmp_path)
    target = _verweis(root, TOKEN, richtung, _token_json())
    vorher = target.read_bytes()
    r = _run_py(root, (
        "import override_token\n"
        "try:\n"
        f"    override_token.create_token({WF!r})\n"
        "except Exception as e:\n"
        "    print('EXC', type(e).__name__)\n"
        "else:\n"
        "    print('OK')\n"))
    assert r.returncode == 0, f"{richtung}: {_out(r, root)[-400:]!r}"
    erwartet = "OK" if richtung in DATEI_RICHTUNGEN else "EXC UnsafeStateError"
    assert _ergebnis_zeile(r) == erwartet, (
        f"{richtung}: {_ergebnis_zeile(r)!r} (erwartet {erwartet!r}); "
        f"stderr: {r.stderr[-300:]!r}")
    assert target.read_bytes() == vorher, f"{richtung}: Verweisziel verändert"


@pytest.mark.parametrize("richtung", RICHTUNGEN)
def test_f003_remove_token_wirft_bei_verweis(tmp_path, monkeypatch, richtung):
    """AC-7: gültiges Token gelesen, danach erscheint der Verweis (zwischen
    Lesen und Schreiben — sonst findet schon der Leser nichts und es wird
    nichts geschrieben) → Ordner-Verweis: UnsafeStateError; Datei-Verweis:
    gebrochen. Verweisziel byte-gleich."""
    root = _sandbox(tmp_path)
    (root / ".claude" / TOKEN).write_text(_token_json())
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    import override_token as ot
    echtes_laden = ot._load_tokens
    ziel = {}

    def _laden_dann_verweis():
        tokens = echtes_laden()
        assert WF in tokens, "Vorbedingung: gültiges Token nicht gelesen"
        if richtung in DATEI_RICHTUNGEN:
            (root / ".claude" / TOKEN).unlink()
        ziel["pfad"] = _verweis(root, TOKEN, richtung, _token_json())
        ziel["vorher"] = ziel["pfad"].read_bytes()
        return tokens
    monkeypatch.setattr(ot, "_load_tokens", _laden_dann_verweis)

    try:
        ot.remove_token(WF)
        ergebnis = "OK"
    except Exception as exc:  # noqa: BLE001
        ergebnis = f"EXC {type(exc).__name__}"
    erwartet = "OK" if richtung in DATEI_RICHTUNGEN else "EXC UnsafeStateError"
    assert ergebnis == erwartet, f"{richtung}: {ergebnis!r} (erwartet {erwartet!r})"
    assert ziel["pfad"].read_bytes() == ziel["vorher"], (
        f"{richtung}: Verweisziel verändert")


# --------------------------------------------------------------------- #
# F003 — AC-8, AC-9, AC-10: phase_listener
# --------------------------------------------------------------------- #

def _sandbox_ohne_workflow(tmp_path: Path, richtung: "str | None") -> Path:
    """Kein aktiver Workflow (wf_name `__global__`): der Override-Zweig wird
    auch dann erreicht, wenn `.claude` hinter einem Verweis liegt."""
    root = _sandbox(tmp_path)
    (root / ".claude" / "active_workflow").unlink()
    if richtung is not None:
        _verweis(root, TOKEN, richtung, _token_json())
    return root


def _env_ohne_wf(root: Path) -> dict:
    env = _hook_env(root)
    env.pop("OPENSPEC_ACTIVE_WORKFLOW", None)
    return env


def _run_listener(root: Path, env: dict, vorab: str = "") -> subprocess.CompletedProcess:
    """phase_listener.py als UserPromptSubmit-Hook mit Prompt „override"."""
    skript = str(HOOKS_DIR / "phase_listener.py")
    prog = (f"import sys, runpy; sys.path.insert(0, {str(HOOKS_DIR)!r})\n" + vorab
            + f"sys.argv = [{skript!r}]\nrunpy.run_path({skript!r}, run_name='__main__')\n")
    return subprocess.run(
        [sys.executable, "-c", prog], input=json.dumps({"prompt": "override"}),
        capture_output=True, text=True, env=env, cwd=str(root), timeout=60)


def _system_message(r: subprocess.CompletedProcess) -> str:
    for zeile in reversed(r.stdout.strip().splitlines()):
        try:
            data = json.loads(zeile)
        except ValueError:
            continue
        if isinstance(data, dict) and "systemMessage" in data:
            return data["systemMessage"]
    return ""


@pytest.mark.parametrize("richtung", ORDNER_RICHTUNGEN)
def test_f003_phase_listener_override_mit_verweis_warnt_ohne_erfolgsmeldung(
        tmp_path, richtung):
    """AC-8: Token-Pfad hinter Verweis → Warnung, keine Erfolgsmeldung."""
    root = _sandbox_ohne_workflow(tmp_path, richtung)
    r = _run_listener(root, _env_ohne_wf(root))
    msg = _system_message(r)
    fehler = []
    if r.returncode != 0 or not _kein_traceback(r):
        fehler.append(f"rc={r.returncode}: {_out(r, root)[-400:]!r}")
    if "Override-Token nicht geschrieben" not in msg:
        fehler.append(f"keine Warnung in systemMessage: {msg[:300]!r}")
    if "Override token created" in msg:
        fehler.append("Erfolgsmeldung trotz nicht geschriebenem Token")
    assert not fehler, f"{richtung}: {fehler}"


def test_f003_phase_listener_override_normalfall_meldet_erfolg(tmp_path):
    """AC-9: normale Struktur → Erfolgsmeldung, keine Warnung, Token gültig."""
    root = _sandbox(tmp_path)
    r = _run_listener(root, _hook_env(root))
    msg = _system_message(r)
    assert r.returncode == 0 and _kein_traceback(r), _out(r, root)[-400:]
    assert f"Override token created for workflow: {WF}" in msg, msg[:300]
    assert "WARNUNG" not in msg and "nicht geschrieben" not in msg, msg[:300]
    r = _run_py(root, f"import override_token\nprint(override_token.has_valid_token({WF!r}))")
    assert _ergebnis_zeile(r) == "True", _out(r, root)[-300:]


BLOCK_OVERRIDE_TOKEN = "sys.modules['override_token'] = None\n"


@pytest.mark.parametrize("fall", ["verweis", "normal"])
def test_f003_import_fallback_erfolgsmeldung_nur_bei_erfolg(tmp_path, fall):
    """AC-10: Fallback-Zweig gibt False+Warnung bzw. True zurück; die
    Erfolgsmeldung des Hooks erscheint nur im Normalfall."""
    root = _sandbox_ohne_workflow(tmp_path, "claude_symlink" if fall == "verweis" else None)
    env = _env_ohne_wf(root)
    fehler = []

    r = subprocess.run(
        [sys.executable, "-c",
         f"import sys, json; sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
         + BLOCK_OVERRIDE_TOKEN
         + "import phase_listener\n"
           "rv = phase_listener._create_override_token('x')\n"
           "print(json.dumps({'rv': rv, 'notices': phase_listener._NOTICES}))\n"],
        capture_output=True, text=True, env=env, cwd=str(root), timeout=60)
    if r.returncode != 0:
        fehler.append(f"Direktaufruf rc={r.returncode}: {_out(r, root)[-300:]!r}")
    else:
        ergebnis = json.loads(_ergebnis_zeile(r))
        warnt = any("Override-Token nicht geschrieben" in n for n in ergebnis["notices"])
        erwartet = (False, True) if fall == "verweis" else (True, False)
        if (ergebnis["rv"], warnt) != erwartet:
            fehler.append(f"Direktaufruf: rv={ergebnis['rv']!r}, Warnung={warnt} "
                          f"(erwartet rv={erwartet[0]}, Warnung={erwartet[1]})")

    r = _run_listener(root, env, vorab=BLOCK_OVERRIDE_TOKEN)
    msg = _system_message(r)
    if r.returncode != 0 or not _kein_traceback(r):
        fehler.append(f"Hook rc={r.returncode}: {_out(r, root)[-300:]!r}")
    erfolg = "Override token created" in msg
    if erfolg != (fall == "normal"):
        fehler.append(f"Hook: Erfolgsmeldung={erfolg}: {msg[:300]!r}")
    assert not fehler, f"{fall}: {fehler}"


# --------------------------------------------------------------------- #
# AC-12: CHANGELOG
# --------------------------------------------------------------------- #

def test_changelog_nennt_425_und_qa_gate_ausnahme():
    # Release-stabil: Eintrag über den Marker finden, nicht über [Unreleased]
    # (wie tests/test_always_allowed_worktree_409.py).
    lines = (REPO_ROOT / "CHANGELOG.md").read_text().splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("- **#425")), None)
    assert start is not None, "Kein Eintrag zu #425 im CHANGELOG"
    entry = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith("- ") or line.startswith("#"):
            break
        entry.append(line)
    block = "\n".join(entry)
    fehler = [f"CHANGELOG-Eintrag #425 nennt {muss!r} nicht"
              for muss in ("#425", "qa_gate") if muss not in block]
    assert not fehler, fehler
