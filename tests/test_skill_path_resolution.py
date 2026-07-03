"""Tests für die dreistufige Hook-Pfad-Auflösung in den Plugin-Skills (Issue #33 Stufe 1).

Motivation: Der bisherige Zweistufen-Fallback (`CLAUDE_PLUGIN_ROOT` → `.claude/hooks`)
griff in Consumer-Projekten IMMER auf die eingefrorene Legacy-Kopie zurück, weil
`CLAUDE_PLUGIN_ROOT` nur in Harness-Hook-Subprozessen gesetzt ist. Das führte zu
struktureller Doppelentwicklung (real passiert: #960, #29).

Neue Prioritätskette (Spec feat-33-plugin-path-resolution):
  1. CLAUDE_PLUGIN_ROOT (wenn gesetzt)
  2. ~/.claude/plugins/installed_plugins.json → installPath des Plugins
     `agent-os-openspec@*` (user-scope bevorzugt), nur wenn Verzeichnis existiert
  3. .claude/hooks (Fallback wie bisher)

Die Tests extrahieren den Snippet-Block aus einer echten SKILL.md und führen ihn
via `bash` mit präpariertem Fake-HOME aus (hermetisch, kein Zugriff auf das echte
System-HOME oder den echten Plugin-Cache).
"""

import glob
import json
import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_GLOB = str(REPO_ROOT / "skills" / "*" / "SKILL.md")
REFERENCE_SKILL = REPO_ROOT / "skills" / "50-implement" / "SKILL.md"

# Der Snippet-Block reicht von der Kommentarzeile bis inkl. der Fallback-Zuweisung.
_SNIPPET_RE = re.compile(
    r"(# Hook-Pfad:.*?\n_H=\"\$\{_H:-\.claude/hooks\}\")",
    re.DOTALL,
)


def extract_snippet(skill_path: Path) -> str:
    """Extrahiert den Hook-Pfad-Snippet-Block aus einer SKILL.md.

    Gibt None zurück, wenn die Datei keinen solchen Block enthält.
    """
    text = skill_path.read_text()
    m = _SNIPPET_RE.search(text)
    return m.group(1) if m else None


def skills_with_snippet():
    return sorted(p for p in glob.glob(SKILLS_GLOB) if extract_snippet(Path(p)))


def run_snippet(snippet: str, tmp_path: Path, env: dict) -> str:
    """Führt den Snippet aus und gibt den aufgelösten `_H`-Wert zurück.

    Der Snippet wird in ein Script geschrieben und mit `bash` unter dem gegebenen
    `env` (inkl. Fake-HOME) im Verzeichnis `tmp_path` ausgeführt. Vermeidet
    Quote-Nesting-Probleme von `bash -c`.
    """
    script = tmp_path / "snippet.sh"
    script.write_text(snippet + '\necho "$_H"\n')
    # Minimales, kontrolliertes Environment: nur was explizit übergeben wird,
    # plus PATH (python3 muss auffindbar sein).
    full_env = {"PATH": os.environ.get("PATH", "")}
    full_env.update(env)
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=str(tmp_path),
        env=full_env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"snippet exited {proc.returncode}: {proc.stderr}"
    return proc.stdout.strip().splitlines()[-1]


def _write_installed_plugins(home: Path, entries) -> None:
    plugins_dir = home / ".claude" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    data = {"version": 2, "plugins": {"agent-os-openspec@some-market": entries}}
    (plugins_dir / "installed_plugins.json").write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# (a) JSON vorhanden + Verzeichnis existiert → installPath gewinnt
# ---------------------------------------------------------------------------
def test_a_json_installpath_wins(tmp_path):
    snippet = extract_snippet(REFERENCE_SKILL)
    assert snippet, "Snippet konnte nicht aus 50-implement/SKILL.md extrahiert werden"

    fake_home = tmp_path / "home"
    install = tmp_path / "cache" / "agent-os-openspec" / "3.7.0"
    (install / "core" / "hooks").mkdir(parents=True)
    _write_installed_plugins(fake_home, [{"scope": "user", "installPath": str(install)}])

    result = run_snippet(
        snippet,
        tmp_path,
        {"HOME": str(fake_home)},  # CLAUDE_PLUGIN_ROOT bewusst NICHT gesetzt
    )
    assert result == str(install / "core" / "hooks")


# ---------------------------------------------------------------------------
# (b) CLAUDE_PLUGIN_ROOT gesetzt → gewinnt über JSON
# ---------------------------------------------------------------------------
def test_b_plugin_root_wins_over_json(tmp_path):
    snippet = extract_snippet(REFERENCE_SKILL)

    fake_home = tmp_path / "home"
    install = tmp_path / "cache" / "agent-os-openspec" / "3.7.0"
    (install / "core" / "hooks").mkdir(parents=True)
    _write_installed_plugins(fake_home, [{"scope": "user", "installPath": str(install)}])

    plugin_root = tmp_path / "harness_plugin_root"
    result = run_snippet(
        snippet,
        tmp_path,
        {"HOME": str(fake_home), "CLAUDE_PLUGIN_ROOT": str(plugin_root)},
    )
    assert result == str(plugin_root / "core" / "hooks")


# ---------------------------------------------------------------------------
# (c) kein JSON → .claude/hooks-Fallback
# ---------------------------------------------------------------------------
def test_c_no_json_falls_back(tmp_path):
    snippet = extract_snippet(REFERENCE_SKILL)

    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)  # aber KEINE installed_plugins.json

    result = run_snippet(snippet, tmp_path, {"HOME": str(fake_home)})
    assert result == ".claude/hooks"


# ---------------------------------------------------------------------------
# (d) JSON zeigt auf nicht-existentes Verzeichnis → Fallback
# ---------------------------------------------------------------------------
def test_d_stale_installpath_falls_back(tmp_path):
    snippet = extract_snippet(REFERENCE_SKILL)

    fake_home = tmp_path / "home"
    _write_installed_plugins(
        fake_home,
        [{"scope": "user", "installPath": str(tmp_path / "does" / "not" / "exist")}],
    )

    result = run_snippet(snippet, tmp_path, {"HOME": str(fake_home)})
    assert result == ".claude/hooks"


def test_d2_broken_json_falls_back(tmp_path):
    """Kaputtes JSON darf keinen Fehler werfen, sondern sauber durchfallen."""
    snippet = extract_snippet(REFERENCE_SKILL)

    fake_home = tmp_path / "home"
    plugins_dir = fake_home / ".claude" / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "installed_plugins.json").write_text("not json {{{")

    result = run_snippet(snippet, tmp_path, {"HOME": str(fake_home)})
    assert result == ".claude/hooks"


def test_d3_user_scope_preferred_over_project(tmp_path):
    """Bei mehreren Einträgen wird der user-scope-Eintrag bevorzugt."""
    snippet = extract_snippet(REFERENCE_SKILL)

    fake_home = tmp_path / "home"
    user_install = tmp_path / "user_cache"
    proj_install = tmp_path / "proj_cache"
    (user_install / "core" / "hooks").mkdir(parents=True)
    (proj_install / "core" / "hooks").mkdir(parents=True)
    _write_installed_plugins(
        fake_home,
        [
            {"scope": "project", "installPath": str(proj_install)},
            {"scope": "user", "installPath": str(user_install)},
        ],
    )

    result = run_snippet(snippet, tmp_path, {"HOME": str(fake_home)})
    assert result == str(user_install / "core" / "hooks")


# ---------------------------------------------------------------------------
# (e) Alle Skills, die den Snippet nutzen, enthalten exakt denselben Block
# ---------------------------------------------------------------------------
def test_e_all_skills_share_identical_snippet():
    snippet_files = skills_with_snippet()
    # Die 11 hook-nutzenden Skills müssen alle den Snippet tragen.
    assert len(snippet_files) == 11, (
        f"Erwartet 11 Skills mit Hook-Setup-Snippet, gefunden {len(snippet_files)}: "
        f"{snippet_files}"
    )

    snippets = {p: extract_snippet(Path(p)) for p in snippet_files}
    reference = snippets[str(REFERENCE_SKILL)]
    for path, snip in snippets.items():
        assert snip == reference, f"Snippet in {path} weicht von der Referenz ab"


def test_e2_non_hook_skills_have_no_snippet():
    """Die 5 Skills ohne Hook-Aufrufe tragen bewusst keinen Snippet-Block."""
    all_skills = set(glob.glob(SKILLS_GLOB))
    with_snippet = set(skills_with_snippet())
    without = all_skills - with_snippet
    # Genau diese 5 Skills invozieren keine workflow.py-Hooks.
    assert len(without) == 5, f"Erwartet 5 Skills ohne Snippet, gefunden: {sorted(without)}"
    for p in without:
        assert "CLAUDE_PLUGIN_ROOT" not in Path(p).read_text(), (
            f"{p} sollte keinen Hook-Setup-Block enthalten"
        )
