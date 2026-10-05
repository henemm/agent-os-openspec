"""Kurz-Befehle: Entfernen und Auffrischen trotz unerwarteter Dateien (Issue #350).

Folge der Gegenpruefung von #251 (Befunde F001-F003). Soll laut Spec
`docs/specs/fix-350-remove-aliases-robust.md`:
- Eine unlesbare `.md`-Datei (nicht UTF-8 oder Rechte entzogen) bringt
  `find_aliases`, `find_stale_aliases` und `find_removed_aliases` nicht zum
  Absturz; sie ist nie ein Alias, wird nie geloescht und steht unter `Kept:`.
- Die Kept-Liste von `--remove-aliases` enthaelt nur echte Dateien.
- `--global` ohne `--remove-aliases` warnt auf stderr.
- `_frontmatter_close` erkennt Frontmatter mit CRLF bzw. Leerzeichen hinter
  `---`; der Marker landet dann hinter dem Frontmatter.

setup.py laeuft als echter Prozess mit Test-Home, damit weder
`~/.claude/commands/` des Rechners noch das Repo beruehrt wird.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

import alias_sync  # noqa: E402

SETUP_PY = REPO_ROOT / "setup.py"
MARKER = alias_sync.ALIAS_MARKER
BAD_BYTES = b"\xff\xfe\x00bad"


def _new_format_redirect(name: str) -> str:
    """Weiterleitung im neuen Format (Marker direkt nach dem Frontmatter)."""
    return (
        "---\n"
        f"description: Kurz-Alias für /agent-os-openspec:{name}\n"
        "---\n"
        f"{MARKER}\n"
        "\n"
        f"/agent-os-openspec:{name} $ARGUMENTS\n"
    )


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def _run_setup(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home))
    return subprocess.run(
        [sys.executable, str(SETUP_PY), *args],
        capture_output=True, text=True, env=env, cwd=str(home),
        stdin=subprocess.DEVNULL,
    )


def _commands(base: Path) -> Path:
    d = base / ".claude" / "commands"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _project(tmp_path: Path, name: str = "proj") -> Path:
    p = tmp_path / name
    p.mkdir()
    return p


# --- AC-1 -------------------------------------------------------------------

def test_remove_aliases_ueberlebt_unlesbare_datei(tmp_path, home):
    proj = _project(tmp_path)
    cmd = _commands(proj)
    alias = cmd / "10-context.md"
    alias.write_text(_new_format_redirect("10-context"))
    broken = cmd / "kaputt.md"
    broken.write_bytes(BAD_BYTES)

    result = _run_setup(home, str(proj), "--remove-aliases")

    assert result.returncode == 0, result.stderr
    assert not alias.exists(), "markierter Alias muss entfernt sein"
    assert broken.exists(), "unlesbare Datei darf nie geloescht werden"
    assert broken.read_bytes() == BAD_BYTES
    assert "Removed: 10-context.md" in result.stdout
    assert "Kept: kaputt.md" in result.stdout
    assert "1 removed, 1 kept" in result.stdout


# --- AC-2 -------------------------------------------------------------------

def test_find_aliases_ueberspringt_nicht_lesbare_datei(tmp_path):
    # Teil 1: Rechte entzogen
    cmd = _commands(tmp_path / "perm")
    alias = cmd / "10-context.md"
    alias.write_text(_new_format_redirect("10-context"))
    locked = cmd / "gesperrt.md"
    locked.write_text(_new_format_redirect("20-analyse"))
    locked.chmod(0o000)
    try:
        if os.geteuid() == 0 or os.access(locked, os.R_OK):
            pytest.skip("Datei bleibt lesbar (root oder Dateisystem ohne Rechte)")
        found = alias_sync.find_aliases(cmd)
    finally:
        locked.chmod(0o644)
    assert locked not in found
    assert alias in found

    # Teil 2: nicht UTF-8
    cmd2 = _commands(tmp_path / "bytes")
    alias2 = cmd2 / "10-context.md"
    alias2.write_text(_new_format_redirect("10-context"))
    broken = cmd2 / "kaputt.md"
    broken.write_bytes(BAD_BYTES)
    found2 = alias_sync.find_aliases(cmd2)
    assert broken not in found2
    assert found2 == [alias2]


# --- AC-3 -------------------------------------------------------------------

_SKILL_TEXT = (
    "---\n"
    "description: Testskill\n"
    "disable-model-invocation: true\n"
    "---\n"
    "# Inhalt der aktuellen Fassung\n"
)


def test_stale_und_removed_finden_trotz_unlesbarer_datei(tmp_path):
    skills = tmp_path / "skills"
    for name in ("10-context", "20-analyse", "30-spec"):
        (skills / name).mkdir(parents=True)
    (skills / "10-context" / "SKILL.md").write_text(_SKILL_TEXT)
    (skills / "20-analyse" / "SKILL.md").write_text(_SKILL_TEXT)
    # SKILL.md selbst unlesbar
    (skills / "30-spec" / "SKILL.md").write_bytes(BAD_BYTES)

    cmd = _commands(tmp_path / "scope")
    # veralteter markierter Alias: Vollkopie einer aelteren Fassung
    stale_text = alias_sync.alias_content(
        "10-context", _SKILL_TEXT.replace("aktuellen", "alten"))
    assert alias_sync.is_alias_file(stale_text)
    (cmd / "10-context.md").write_text(stale_text)
    # Alias-Datei mit Skill-Namen, aber nicht UTF-8
    (cmd / "20-analyse.md").write_bytes(BAD_BYTES)
    # markierter Alias zu einem Skill mit unlesbarer SKILL.md
    (cmd / "30-spec.md").write_text(_new_format_redirect("30-spec"))
    (cmd / "kaputt.md").write_bytes(BAD_BYTES)
    # markierter Alias eines entfernten Befehls
    removed_alias = cmd / "00-bug.md"
    removed_alias.write_text(_new_format_redirect("00-bug"))

    stale = alias_sync.find_stale_aliases(skills, cmd, None)
    assert stale == ["10-context"]
    assert alias_sync.find_removed_aliases(cmd) == [removed_alias]

    # 00-bug.md selbst nicht UTF-8: kein Absturz, kein Treffer
    cmd2 = _commands(tmp_path / "scope2")
    (cmd2 / "00-bug.md").write_bytes(BAD_BYTES)
    assert alias_sync.find_removed_aliases(cmd2) == []


# --- AC-4 -------------------------------------------------------------------

def test_kept_liste_nur_echte_dateien(tmp_path, home):
    proj = _project(tmp_path)
    cmd = _commands(proj)
    (cmd / "ordner.md").mkdir()
    (cmd / "link.md").symlink_to(cmd / "gibt-es-nicht.md")
    radar = cmd / "radar.md"
    radar.write_text("# Radar\n\nprojekteigener Befehl\n")
    alias = cmd / "10-context.md"
    alias.write_text(_new_format_redirect("10-context"))

    result = _run_setup(home, str(proj), "--remove-aliases")

    assert result.returncode == 0, result.stderr
    assert not alias.exists()
    assert radar.exists()
    assert "Kept: radar.md" in result.stdout
    assert "ordner.md" not in result.stdout
    assert "link.md" not in result.stdout
    assert "1 removed, 1 kept" in result.stdout


# --- AC-5 -------------------------------------------------------------------

def test_global_ohne_remove_aliases_warnt(tmp_path, home):
    proj_plain = _project(tmp_path, "proj_plain")
    proj_global = _project(tmp_path, "proj_global")

    plain = _run_setup(home, str(proj_plain))
    flagged = _run_setup(home, str(proj_global), "--global")

    assert "WARNING" in flagged.stderr
    assert "--global" in flagged.stderr
    assert "--remove-aliases" in flagged.stderr
    assert flagged.returncode == plain.returncode

    # Kontrolle: zusammen mit --remove-aliases keine Warnung
    combined = _run_setup(home, str(proj_plain), "--remove-aliases", "--global")
    assert combined.returncode == 0, combined.stderr
    assert "WARNING" not in combined.stderr


# --- AC-6 -------------------------------------------------------------------

def _assert_marker_after_frontmatter(result: str, close_index: int) -> None:
    lines = result.split("\n")
    assert not lines[0].startswith(MARKER), "Marker darf nicht in Zeile 1 stehen"
    assert lines[close_index].rstrip() == "---"
    assert lines[close_index + 1] == MARKER
    assert alias_sync.is_alias_file(result)


def test_frontmatter_mit_crlf_marker_hinter_frontmatter():
    skill_text = (
        "---\r\n"
        "description: Testskill\r\n"
        "disable-model-invocation: true\r\n"
        "---\r\n"
        "# Inhalt\r\n"
    )
    assert alias_sync.embeds_full_skill(skill_text)
    result = alias_sync.alias_content("10-context", skill_text)
    _assert_marker_after_frontmatter(result, 3)


# --- AC-7 -------------------------------------------------------------------

def test_frontmatter_mit_leerzeichen_nach_trennstrich():
    skill_text = (
        "---  \n"
        "description: Testskill\n"
        "disable-model-invocation: true\n"
        "---  \n"
        "# Inhalt\n"
    )
    assert alias_sync.embeds_full_skill(skill_text)
    result = alias_sync.alias_content("10-context", skill_text)
    _assert_marker_after_frontmatter(result, 3)


# --- AC-8 -------------------------------------------------------------------

def test_ohne_geschlossenes_frontmatter_unveraendert():
    no_frontmatter = "disable-model-invocation: true\n# Inhalt\n"
    unclosed = "---\ndescription: x\ndisable-model-invocation: true\n# Inhalt\n"
    for skill_text in (no_frontmatter, unclosed):
        result = alias_sync.alias_content("10-context", skill_text)
        assert result.startswith(MARKER)
        assert result == f"{MARKER}\n{skill_text}"


# --- #353: --command-aliases (Anlegen) uebersteht unlesbare Dateien ---

def test_command_aliases_skips_unreadable_file(home, tmp_path):
    proj = tmp_path / "proj"
    cmds = proj / ".claude" / "commands"
    cmds.mkdir(parents=True)
    bad = cmds / "50-implement.md"
    bad.write_bytes(BAD_BYTES)
    r = _run_setup(home, str(proj), "--command-aliases")
    assert r.returncode == 0, r.stdout + r.stderr
    assert bad.read_bytes() == BAD_BYTES, "unlesbare Datei nie ueberschreiben"
    assert "50-implement.md (unlesbar)" in r.stdout
    assert (cmds / "60-validate.md").exists(), "die uebrigen Aliase entstehen trotzdem"
