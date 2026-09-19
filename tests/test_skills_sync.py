"""Tests fuer scripts/sync_skills.py — core/commands ist die einzige Quelle.

Das Plugin liefert nur skills/<name>/SKILL.md aus. Zwischen 3.18 und 3.22
erreichte deshalb keine Aenderung an core/commands einen Plugin-Nutzer. Der
Drift-Test hier (und der Release-Check) macht das zu einem roten Build.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import sync_skills  # noqa: E402

FRONTMATTER = 'description: "Beispiel"\ndisable-model-invocation: true\n'


# --- Drift-Wächter ------------------------------------------------------------

def test_repo_skills_are_in_sync_with_commands():
    """Jede SKILL.md entspricht exakt dem Generat aus core/commands."""
    drift = sync_skills.check()
    assert drift == [], (
        f"Skills weichen von core/commands ab: {drift} — "
        "python3 scripts/sync_skills.py ausführen"
    )


def test_check_cli_exit_code_zero_when_in_sync():
    result = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"),
                             "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_all_sixteen_skills_are_covered_and_legacy_names_ignored():
    names = sync_skills.synced_names()
    assert len(names) == 16, names
    for legacy in ("tdd-red", "implement", "validate"):
        assert legacy not in names


def test_setup_block_never_lands_inside_code_fence():
    """`^## ` darf nicht innerhalb eines ```-Blocks gematcht worden sein."""
    for skill in (REPO_ROOT / "skills").glob("*/SKILL.md"):
        text = skill.read_text()
        idx = text.find("## Setup")
        if idx >= 0:
            assert text[:idx].count("```") % 2 == 0, skill


def test_no_placeholder_left_in_generated_skills():
    version = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    text = (REPO_ROOT / "skills" / "30-write-spec" / "SKILL.md").read_text()
    for skill in (REPO_ROOT / "skills").glob("*/SKILL.md"):
        assert sync_skills.VERSION_PLACEHOLDER not in skill.read_text(), skill
    assert f"⚙ PO-Briefing unabhängig erstellt · agent-os-openspec {version}" in text


# --- Transformationen -----------------------------------------------------------

def test_frontmatter_is_preserved():
    out = sync_skills.render_skill("# Titel\n\nText.\n", FRONTMATTER, "1.2.3")
    assert out.startswith(f"---\n{FRONTMATTER}---\n\n# Titel\n")


def test_extract_frontmatter_roundtrip():
    skill = f"---\n{FRONTMATTER}---\n\n# Titel\n"
    assert sync_skills.extract_frontmatter(skill) == FRONTMATTER
    assert sync_skills.extract_frontmatter("# ohne Frontmatter\n") is None


def test_setup_block_inserted_before_first_h2_only_with_hook_paths():
    cmd = "# Titel\n\nIntro.\n\n## Schritt 1\n\n```bash\npython3 .claude/hooks/workflow.py status\n```\n"
    out = sync_skills.render_skill(cmd, FRONTMATTER, "1.2.3")
    assert "Intro.\n\n" + sync_skills.SETUP_BLOCK + "## Schritt 1" in out
    assert out.count("## Setup") == 1

    no_hooks = sync_skills.render_skill("# Titel\n\n## Schritt\n\nNur Text.\n", FRONTMATTER, "1")
    assert "## Setup" not in no_hooks


def test_hook_paths_are_rewritten():
    cmd = (
        "# T\n\n## S\n\n"
        "python3 .claude/hooks/workflow.py phase phase3_spec\n"
        "python3 .claude/hooks/qa_gate.py out.txt\n"
        "python3 .claude/hooks/session_singleton_guard.py claim --issue 4\n"
        "Siehe .claude/hooks/edit_gate.py\n"
    )
    out = sync_skills.render_skill(cmd, FRONTMATTER, "1")
    assert "$WF phase phase3_spec" in out
    assert "python3 ${_H}/qa_gate.py out.txt" in out
    assert "python3 ${_H}/session_singleton_guard.py claim --issue 4" in out
    assert "Siehe ${_H}/edit_gate.py" in out
    body = out.split("```\n\n## S", 1)[1]
    assert ".claude/hooks/" not in body


def test_version_placeholder_replaced():
    out = sync_skills.render_skill("# T\n\nVersion {{OPENSPEC_VERSION}}\n", FRONTMATTER, "3.23.0")
    assert "Version 3.23.0" in out
    assert "{{OPENSPEC_VERSION}}" not in out


def test_check_and_write_on_temp_tree(tmp_path):
    commands = tmp_path / "commands"
    skills = tmp_path / "skills"
    commands.mkdir()
    (skills / "10-x").mkdir(parents=True)
    (commands / "10-x.md").write_text("# X\n\n## A\n\npython3 .claude/hooks/workflow.py status\n")
    (commands / "tdd-red.md").write_text("# Legacy ohne Skill\n")
    (skills / "10-x" / "SKILL.md").write_text(f"---\n{FRONTMATTER}---\n\nalt\n")

    assert sync_skills.check(commands, skills, "1.0") == ["10-x"]
    assert sync_skills.write(commands, skills, "1.0") == ["10-x"]
    assert sync_skills.check(commands, skills, "1.0") == []
    written = (skills / "10-x" / "SKILL.md").read_text()
    assert written.startswith(f"---\n{FRONTMATTER}---\n")
    assert "$WF status" in written
    assert not (skills / "tdd-red").exists()
    # Idempotent: zweiter Lauf aendert nichts.
    assert sync_skills.write(commands, skills, "1.0") == []


def test_release_check_blocks_on_skill_drift(monkeypatch):
    import release_check

    monkeypatch.setattr(sync_skills, "check", lambda *a, **k: ["30-write-spec"])
    ok, detail = release_check.check_skills_sync()
    assert ok is False
    assert "30-write-spec" in detail
    assert "python3 scripts/sync_skills.py ausführen" in detail

    monkeypatch.setattr(sync_skills, "check", lambda *a, **k: [])
    ok, _ = release_check.check_skills_sync()
    assert ok is True
