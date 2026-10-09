"""RED-Tests fuer Issue #409: Always-Allowed-Freigabe in `tdd_enforcement.py`
und `post_implementation_gate.py` war ein Teilstring-Test auf den ABSOLUTEN
Pfad (`\\.claude[/\\\\]`). Jeder Worktree liegt unter
`<repo>/.claude/worktrees/<name>/` — damit galt jede Datei einer
Worktree-Sitzung (auch `src/x.py`, `.github/workflows/ci.yml`) als "immer
erlaubt", beide Gates waren in praktisch allen Sitzungen wirkungslos
(False-Pass; Beobachtung gregor_zwanzig #2047 S2b, Herkunft #1197).

Spec: docs/specs/fix-409-worktree-always-allowed.md (AC-1 bis AC-10).

Soll: gemeinsamer Helfer `hook_utils.is_hook_always_allowed(file_path)`
(True = frei). Er bewertet den Pfad RELATIV zur Worktree- bzw. Projektwurzel
(laengste passende Wurzel zuerst, `is_relative_to` statt `startswith`),
schneidet ein Praefix `.claude/worktrees/<n>/` ab, verankert `.claude/` am
Wurzelanfang und gibt Pfade ausserhalb von Projekt und Worktree frei.

Kein Mock-Theater: echte Verzeichnisse auf `tmp_path`; nur die
Wurzel-Aufloesung (`hook_utils._find_worktree_root`, `find_project_root`)
wird injiziert (Muster: tests/test_tdd_enforcement_worktree_artifact_path_1478.py).
Die AC-8-Tests starten beide Gates als echte Prozesse in einer echten
Worktree-Struktur (`.git`-Datei, Hauptrepo darueber).
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import hook_utils  # noqa: E402

# Alte Regex woertlich aus core/hooks/tdd_enforcement.py (Stand vor #409),
# identisch in post_implementation_gate.py. Nur fuer den Mutationsnachweis (AC-9).
_OLD_ALWAYS_ALLOWED = re.compile(
    r"(\.claude[/\\]|[/\\]docs[/\\]|\.md$|\.gitignore|\.txt$|[/\\]specs[/\\]"
    r"|[/\\]\.claude[/\\])"
)

_WF_NAME = "wf-409"
_WF_CREATED = "2026-10-09T10:00:00.000000"


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------

def _allowed(file_path) -> bool:
    """Ruft den (neuen) Helfer auf; fehlt er, scheitert der Test mit klarer Meldung."""
    fn = getattr(hook_utils, "is_hook_always_allowed", None)
    assert fn is not None, (
        "hook_utils.is_hook_always_allowed fehlt — gemeinsamer Freigabe-Helfer "
        "fuer tdd_enforcement und post_implementation_gate (#409) ist nicht implementiert"
    )
    return fn(str(file_path))


def _patch_roots(monkeypatch, worktree, main):
    monkeypatch.setattr(hook_utils, "_find_worktree_root", lambda: worktree)
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: main)


def _make_main_and_worktree(tmp_path: Path) -> "tuple[Path, Path]":
    """Echte Verzeichnisse: Hauptrepo (.git-DIR) und Worktree darunter (.git-DATEI)."""
    base = tmp_path.resolve()
    main = base / "main"
    (main / ".git" / "worktrees" / "wt1").mkdir(parents=True)
    wt = main / ".claude" / "worktrees" / "wt1"
    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'wt1'}\n")
    for d in (wt / "src", wt / "core" / "hooks", wt / ".claude", wt / "docs",
              wt / ".github" / "workflows", main / "src"):
        d.mkdir(parents=True, exist_ok=True)
    return main, wt


def _make_gate_fixture(tmp_path: Path) -> "tuple[Path, Path]":
    """Worktree-Struktur wie im Betrieb fuer die Subprocess-Tests (AC-8).

    Workflow-JSON im Hauptrepo (geteilter State), Workflow-Name worktree-lokal
    in `<wt>/.claude/active_workflow` — genau wie `workflow.py start` es anlegt.
    """
    main, wt = _make_main_and_worktree(tmp_path)
    wf_dir = main / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{_WF_NAME}.json").write_text(json.dumps({
        "name": _WF_NAME,
        "workflow_type": "feature",
        "current_phase": "phase6_implement",
        "created": _WF_CREATED,
        "test_artifacts": [],
    }))
    (wt / ".claude" / "active_workflow").write_text(_WF_NAME + "\n")
    return main, wt


def _env_for(wt: Path) -> dict:
    env = dict(os.environ)
    env.pop("OPENSPEC_FRAMEWORK", None)
    env.update({
        "CLAUDE_PROJECT_DIR": str(wt),
        "OPENSPEC_ACTIVE_WORKFLOW": _WF_NAME,
    })
    return env


def _run_hook(script: str, wt: Path, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)],
        input=json.dumps(payload), capture_output=True, text=True,
        env=_env_for(wt), cwd=str(wt), timeout=60,
    )


def _edit_payload(file_path) -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": str(file_path)}}


# ---------------------------------------------------------------------------
# AC-1
# ---------------------------------------------------------------------------

def test_worktree_code_pfad_ist_nicht_frei(tmp_path, monkeypatch):
    """AC-1.
    GIVEN Worktree-Wurzel <main>/.claude/worktrees/wt1 ist erkannt
    WHEN is_hook_always_allowed absolute Code-Pfade im Worktree bzw. Hauptrepo bewertet
    THEN sind sie NICHT frei (werden geprueft) — der `.claude/`-Teilstring im
    Worktree-Praefix ist keine Freigabe.
    """
    main, wt = _make_main_and_worktree(tmp_path)
    _patch_roots(monkeypatch, wt, main)

    for p in (wt / "src" / "x.py",
              wt / "core" / "hooks" / "x.py",
              wt / ".github" / "workflows" / "ci.yml",
              main / "src" / "x.py"):
        assert _allowed(p) is False, f"{p} darf nicht frei sein (#409 False-Pass)"


# ---------------------------------------------------------------------------
# AC-2
# ---------------------------------------------------------------------------

def test_claude_ordner_am_wurzelanfang_ist_frei(tmp_path, monkeypatch):
    """AC-2.
    GIVEN `<wt>/.claude/foo.json` bzw. `<main>/.claude/foo.json`
    WHEN is_hook_always_allowed sie bewertet
    THEN sind sie frei, weil `.claude/` am Anfang der jeweiligen Wurzel steht.
    """
    main, wt = _make_main_and_worktree(tmp_path)
    _patch_roots(monkeypatch, wt, main)

    assert _allowed(wt / ".claude" / "foo.json") is True
    assert _allowed(main / ".claude" / "foo.json") is True


# ---------------------------------------------------------------------------
# AC-3 (Mutation b)
# ---------------------------------------------------------------------------

def test_fallback_ohne_worktree_erkennung_schneidet_praefix_ab(tmp_path, monkeypatch):
    """AC-3 (Mutation b: Praefix-Abschneiden entfernt -> rot).
    GIVEN `_find_worktree_root()` liefert None, `find_project_root()` das Hauptrepo,
          und der absolute Pfad liegt unter <main>/.claude/worktrees/wt1/
    WHEN is_hook_always_allowed ihn bewertet
    THEN wird `.claude/worktrees/wt1/` abgeschnitten und der Rest bewertet:
         `src/x.py` ist nicht frei, `.claude/foo.json` und `docs/a.md` sind frei.
    """
    main, wt = _make_main_and_worktree(tmp_path)
    _patch_roots(monkeypatch, None, main)

    assert _allowed(main / ".claude" / "worktrees" / "wt1" / "src" / "x.py") is False
    assert _allowed(main / ".claude" / "worktrees" / "wt1" / ".claude" / "foo.json") is True
    assert _allowed(main / ".claude" / "worktrees" / "wt1" / "docs" / "a.md") is True


# ---------------------------------------------------------------------------
# AC-4 (Mutation c)
# ---------------------------------------------------------------------------

def test_geschwisterordner_ist_nicht_relativ_zur_wurzel(tmp_path, monkeypatch):
    """AC-4 (Mutation c: String-startswith statt is_relative_to -> rot).
    GIVEN Wurzel <tmp>/proj und ein Geschwister-Ordner <tmp>/proj2
    WHEN is_hook_always_allowed `<tmp>/proj2/src/x.py` bewertet
    THEN gilt der Pfad als ausserhalb (frei), nicht als `2/src/x.py` relativ zu proj;
         `<tmp>/proj/src/x.py` bleibt geprueft.
    """
    base = tmp_path.resolve()
    proj = base / "proj"
    proj2 = base / "proj2"
    (proj / "src").mkdir(parents=True)
    (proj2 / "src").mkdir(parents=True)
    (proj / ".git").mkdir()
    _patch_roots(monkeypatch, None, proj)

    assert _allowed(proj2 / "src" / "x.py") is True, (
        "Geschwister-Ordner proj2 liegt ausserhalb von proj und ist frei"
    )
    assert _allowed(proj / "src" / "x.py") is False


# ---------------------------------------------------------------------------
# AC-5
# ---------------------------------------------------------------------------

def test_vorfahren_ordner_docs_gibt_projekt_nicht_frei(tmp_path, monkeypatch):
    """AC-5.
    GIVEN ein Projekt unter einem Vorfahren-Ordner `docs` bzw. `specs`
          (z.B. /home/x/docs/proj/)
    WHEN is_hook_always_allowed `src/x.py` darin bewertet
    THEN ist die Datei nicht frei; `docs/a.md`, `src/docs/a.py`, `notes.md`,
         `notes.txt`, `.gitignore` bleiben frei wie bisher.
    """
    for ancestor in ("docs", "specs"):
        proj = tmp_path.resolve() / ancestor / "proj"
        (proj / "src" / "docs").mkdir(parents=True)
        (proj / "docs").mkdir()
        (proj / ".git").mkdir()
        _patch_roots(monkeypatch, None, proj)

        assert _allowed(proj / "src" / "x.py") is False, (
            f"Vorfahren-Ordner '{ancestor}' oberhalb der Projektwurzel darf nicht freigeben"
        )
        for rel in ("docs/a.md", "src/docs/a.py", "notes.md", "notes.txt", ".gitignore"):
            assert _allowed(proj / rel) is True, f"{rel} muss frei bleiben ({ancestor})"


# ---------------------------------------------------------------------------
# AC-6
# ---------------------------------------------------------------------------

def test_pfade_ausserhalb_von_projekt_und_worktree_sind_frei(tmp_path, monkeypatch):
    """AC-6.
    GIVEN Pfade ausserhalb von Projekt und Worktree (Memory unter
          ~/.claude/projects/.../memory/, Sitzungs-Scratchpad)
    WHEN is_hook_always_allowed sie bewertet
    THEN sind sie frei (konsistent mit edit_gate #80 `_is_outside_project`).
    Bewusste kleine Lockerung: Ein Code-Pfad ausserhalb wie `<scratch>/x.py`
    (frueher `/tmp/x.py`, wurde geprueft) ist jetzt frei.
    """
    main, wt = _make_main_and_worktree(tmp_path)
    _patch_roots(monkeypatch, wt, main)

    memory = tmp_path.resolve() / "home" / ".claude" / "projects" / "p" / "memory"
    scratch = tmp_path.resolve() / "scratch"
    memory.mkdir(parents=True)
    scratch.mkdir()

    assert _allowed(memory / "x.md") is True
    # Lockerung: frueher geprueft (alte Regex trifft nicht), jetzt frei.
    assert not _OLD_ALWAYS_ALLOWED.search(str(scratch / "x.py"))
    assert _allowed(scratch / "x.py") is True


# ---------------------------------------------------------------------------
# AC-7
# ---------------------------------------------------------------------------

def test_relative_pfade_funktionieren_weiter(tmp_path, monkeypatch):
    """AC-7.
    GIVEN relative file_path-Werte bei CWD im Projekt
    WHEN is_hook_always_allowed sie bewertet
    THEN bleibt das Verhalten gleich: `src/foo.py` geprueft, `docs/a.md` frei.
    """
    proj = tmp_path.resolve() / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "docs").mkdir()
    (proj / ".git").mkdir()
    monkeypatch.chdir(proj)
    _patch_roots(monkeypatch, None, proj)

    assert _allowed("src/foo.py") is False
    assert _allowed("docs/a.md") is True


# ---------------------------------------------------------------------------
# AC-8
# ---------------------------------------------------------------------------

def test_tdd_enforcement_blockt_code_edit_im_worktree_subprocess(tmp_path):
    """AC-8 (tdd_enforcement als echter Prozess).
    GIVEN echte Worktree-Struktur (Hauptrepo .git-DIR, Worktree .git-DATEI),
          Workflow in phase6_implement ohne RED-Artefakt, cwd und
          CLAUDE_PROJECT_DIR = Worktree (wie im Betrieb)
    WHEN ein Edit auf den ABSOLUTEN Worktree-Pfad `<wt>/src/x.py` eingeht
    THEN blockt tdd_enforcement (Exit 2) — heute gibt der `.claude/`-Teilstring
         des Worktree-Praefixes den Pfad faelschlich frei.
    Gegenprobe: `<wt>/docs/a.md` bleibt frei (Exit 0).
    """
    _main, wt = _make_gate_fixture(tmp_path)

    result = _run_hook("tdd_enforcement.py", wt, _edit_payload(wt / "src" / "x.py"))
    assert result.returncode == 2, (
        f"Code-Edit im Worktree ohne RED-Artefakt muss blocken (#409), "
        f"exit={result.returncode}, stderr={result.stderr!r}"
    )
    assert "tdd_enforcement" in result.stderr

    doc = _run_hook("tdd_enforcement.py", wt, _edit_payload(wt / "docs" / "a.md"))
    assert doc.returncode == 0, f"Doku im Worktree bleibt frei, stderr={doc.stderr!r}"


def test_post_implementation_gate_nutzt_wurzel_des_phase_listener_subprocess(tmp_path):
    """AC-8 (post_implementation_gate + phase_listener als echte Prozesse).
    GIVEN echte Worktree-Struktur, Workflow in phase6_implement, Lock
          `pending_validation_<wf>.json` mit abgelaufenem Batch-Fenster unter der
          Wurzel, die das Gate liest (find_project_root -> Hauptrepo)
    WHEN ein Edit auf `<wt>/src/x.py` eingeht
    THEN blockt das Gate (Exit 2);
    WHEN danach phase_listener (gleiche cwd/env) die GREEN-Phrase "go" erhaelt
    THEN schreibt er den Marker in dieselbe Wurzel, und das Gate erlaubt den
         naechsten Edit (Exit 0) — beide nutzen dieselbe Wurzel.
    """
    main, wt = _make_gate_fixture(tmp_path)
    lock_path = hook_utils.pending_validation_lock_path(main, _WF_NAME)
    lock_created = time.time() - 10 * 3600  # Batch-Fenster sicher abgelaufen
    lock_path.write_text(json.dumps({
        "workflow": _WF_NAME,
        "workflow_created": _WF_CREATED,
        "created": lock_created,
        "created_iso": "irrelevant",
    }))

    code_edit = _edit_payload(wt / "src" / "x.py")

    blocked = _run_hook("post_implementation_gate.py", wt, code_edit)
    assert blocked.returncode == 2, (
        f"Code-Edit im Worktree nach Batch-Fenster ohne Freigabe muss blocken (#409), "
        f"exit={blocked.returncode}, stderr={blocked.stderr!r}"
    )
    assert "post_implementation_gate" in blocked.stderr

    listener = _run_hook("phase_listener.py", wt, {"prompt": "go"})
    assert listener.returncode == 0, f"phase_listener-stderr={listener.stderr!r}"
    marker = hook_utils.approval_marker_path(main, _WF_NAME)
    assert marker.exists(), "phase_listener muss den Marker unter derselben Wurzel schreiben"
    assert marker.read_text().strip() == str(lock_created)

    released = _run_hook("post_implementation_gate.py", wt, code_edit)
    assert released.returncode == 0, (
        f"Nach GREEN-Freigabe muss das Gate den Marker finden, stderr={released.stderr!r}"
    )
    assert not lock_path.exists(), "Lock wird nach gueltiger Freigabe geloescht"


def test_beide_gates_nutzen_gemeinsamen_helfer():
    """AC-8 (Quelltext).
    GIVEN die beiden Gates tdd_enforcement.py und post_implementation_gate.py
    WHEN ihr Quelltext gelesen wird
    THEN rufen beide `is_hook_always_allowed` auf und enthalten keine eigene
         `_ALWAYS_ALLOWED`-Regex mehr (Drift beseitigt).
    """
    for name in ("tdd_enforcement.py", "post_implementation_gate.py"):
        src = (HOOKS_DIR / name).read_text()
        assert "is_hook_always_allowed" in src, f"{name} nutzt den gemeinsamen Helfer nicht"
        assert not re.search(r"_ALWAYS_ALLOWED\s*=\s*re\.compile", src), (
            f"{name} enthaelt noch eine eigene _ALWAYS_ALLOWED-Regex"
        )


# ---------------------------------------------------------------------------
# AC-9 (Mutation a)
# ---------------------------------------------------------------------------

def test_mutation_unverankerte_regex_wuerde_worktree_pfad_freigeben(tmp_path, monkeypatch):
    """AC-9 (Mutation a: unverankerte Regex auf dem absoluten Pfad).
    GIVEN die alte, unverankerte Freigabe-Regex und ein absoluter Worktree-Pfad
          `<main>/.claude/worktrees/wt1/src/x.py`
    WHEN beide den Pfad bewerten
    THEN gibt die alte Regex ihn frei (Bug-Nachweis), der Helfer prueft ihn.
    """
    main, wt = _make_main_and_worktree(tmp_path)
    _patch_roots(monkeypatch, wt, main)
    path = wt / "src" / "x.py"

    assert _OLD_ALWAYS_ALLOWED.search(str(path)), (
        "Mutationsnachweis: alte Regex muss den absoluten Worktree-Pfad freigeben"
    )
    assert _allowed(path) is False, "Helfer darf den Worktree-Code-Pfad nicht freigeben"


# ---------------------------------------------------------------------------
# AC-10
# ---------------------------------------------------------------------------

def _unreleased_entry_409(changelog: str) -> str:
    m = re.search(r"^## \[Unreleased\]\s*$(.*?)(?=^## \[)", changelog, re.M | re.S)
    assert m, "CHANGELOG.md hat keinen [Unreleased]-Abschnitt"
    section = m.group(1)
    lines = section.splitlines()
    start = next((i for i, l in enumerate(lines) if "#409" in l), None)
    assert start is not None, "Kein Eintrag zu #409 unter [Unreleased]"
    entry = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith("- ") or line.startswith("#"):
            break
        entry.append(line)
    return "\n".join(entry)


def test_changelog_nennt_scharfschaltung():
    """AC-10.
    GIVEN die Aenderung ist umgesetzt
    WHEN CHANGELOG.md gelesen wird
    THEN steht unter [Unreleased] ein Eintrag zu #409 mit dem Hinweis, dass beide
         Gates in Worktree-Sitzungen jetzt erstmals greifen (24-h-Artefaktgrenze,
         `tests/` in diesen Gates nicht frei).
    """
    entry = _unreleased_entry_409((REPO_ROOT / "CHANGELOG.md").read_text())
    assert re.search(r"worktree", entry, re.I), "Eintrag nennt Worktree-Sitzungen nicht"
    assert re.search(r"erstmals|scharf", entry, re.I), (
        "Eintrag sagt nicht, dass beide Gates jetzt erstmals greifen (Scharfschaltung)"
    )
    assert "24" in entry, "Eintrag nennt die 24-h-Artefaktgrenze nicht"
    assert "tests/" in entry, "Eintrag nennt nicht, dass tests/ in diesen Gates nicht frei ist"
