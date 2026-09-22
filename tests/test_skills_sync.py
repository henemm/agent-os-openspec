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


# --- Versions-Marker (3.24.0) ---------------------------------------------------
#
# Der PO konnte bis 3.23 nur an der Freigabe-Ausgabe erkennen, ob die neue
# Framework-Fassung geladen war. Jede Phase endet deshalb mit Befehl + Version.

def _repo_version() -> str:
    return json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]


def test_every_skill_carries_its_own_marker_line_exactly_once():
    version = _repo_version()
    names = sync_skills.synced_names()
    for name in names:
        text = (REPO_ROOT / "skills" / name / "SKILL.md").read_text()
        own = f"⚙ /{name} · agent-os-openspec {version}"
        if name in sync_skills.MARKER_EXEMPT:
            assert own not in text, name
            continue
        assert text.count(own) == 1, name
        # Kein fremder Marker: faengt eine Verdrahtung, die ueberall denselben
        # Namen einsetzt.
        for other in names:
            if other != name:
                assert f"⚙ /{other} · agent-os-openspec" not in text, (name, other)


def test_marker_uses_real_version_not_placeholder():
    version = _repo_version()
    assert version != sync_skills.VERSION_PLACEHOLDER
    text = (REPO_ROOT / "skills" / "40-tdd-red" / "SKILL.md").read_text()
    assert f"⚙ /40-tdd-red · agent-os-openspec {version}" in text
    assert "{{" not in text.split("## Versions-Marker", 1)[1]


def test_marker_never_lands_inside_code_fence():
    """Im Code-Block waere die Anweisung wirkungslos — und --check bliebe gruen."""
    for name in sync_skills.synced_names():
        if name in sync_skills.MARKER_EXEMPT:
            continue
        text = (REPO_ROOT / "skills" / name / "SKILL.md").read_text()
        idx = text.index("## Versions-Marker")
        assert text[:idx].count("```") % 2 == 0, name


def test_marker_is_last_block_of_the_skill():
    text = (REPO_ROOT / "skills" / "10-context" / "SKILL.md").read_text()
    assert text.count("## Versions-Marker") == 1
    tail = text.split("## Versions-Marker", 1)[1]
    assert "\n## " not in tail
    assert "⚙ /10-context · agent-os-openspec" in tail


def test_write_spec_is_the_only_exemption_and_keeps_its_briefing_marker():
    assert sync_skills.MARKER_EXEMPT == {"30-write-spec"}
    text = (REPO_ROOT / "skills" / "30-write-spec" / "SKILL.md").read_text()
    assert "## Versions-Marker" not in text
    assert f"⚙ PO-Briefing unabhängig erstellt · agent-os-openspec {_repo_version()}" in text


def test_render_skill_marker_opt_in_and_exempt():
    cmd = "# T\n\n## S\n\nText.\n"
    assert "## Versions-Marker" not in sync_skills.render_skill(cmd, FRONTMATTER, "1.2.3")
    with_name = sync_skills.render_skill(cmd, FRONTMATTER, "1.2.3", "40-tdd-red")
    assert with_name.rstrip("\n").endswith(
        "auch wenn die übrigen Zeilen entfallen.")
    assert "⚙ /40-tdd-red · agent-os-openspec 1.2.3" in with_name
    exempt = sync_skills.render_skill(cmd, FRONTMATTER, "1.2.3", "30-write-spec")
    assert "## Versions-Marker" not in exempt


def test_marker_appended_after_setup_block_even_without_h2():
    """Ohne `## `-Ueberschrift faellt der Setup-Block ans Ende — Marker danach."""
    cmd = "# T\n\npython3 .claude/hooks/workflow.py status\n"
    out = sync_skills.render_skill(cmd, FRONTMATTER, "1.2.3", "99-reset")
    assert out.index("## Setup") < out.index("## Versions-Marker")


def test_marker_version_follows_plugin_version_on_temp_tree(tmp_path):
    commands = tmp_path / "commands"
    skills = tmp_path / "skills"
    commands.mkdir()
    (skills / "40-tdd-red").mkdir(parents=True)
    (commands / "40-tdd-red.md").write_text("# X\n\n## A\n\nText.\n")
    (skills / "40-tdd-red" / "SKILL.md").write_text(f"---\n{FRONTMATTER}---\n\nalt\n")

    sync_skills.write(commands, skills, "9.9.9")
    text = (skills / "40-tdd-red" / "SKILL.md").read_text()
    assert "⚙ /40-tdd-red · agent-os-openspec 9.9.9" in text
    # Idempotent trotz Marker.
    assert sync_skills.write(commands, skills, "9.9.9") == []
    # Versionswechsel schlaegt im Marker durch.
    assert sync_skills.check(commands, skills, "9.9.10") == ["40-tdd-red"]


# --- Checkpoint-Block genau einmal (3.24.0) -------------------------------------

def test_checkpoint_instruction_demands_single_emission():
    for name in ("10-context", "20-analyse", "30-write-spec", "40-tdd-red", "50-implement"):
        for path in (REPO_ROOT / "core" / "commands" / f"{name}.md",
                     REPO_ROOT / "skills" / name / "SKILL.md"):
            text = path.read_text()
            assert "Gesichert auf der Platte" in text, path
            assert "und zwar genau einmal, als letzter inhaltlicher Teil der Nachricht" in text, path
            assert "keine Wiederholung danach" in text, path


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


# --- Wiedereinstieg mit #<N> (3.25.0, AC-4) -----------------------------------
#
# Claude Code verwirft getippte Argumente nie, es haengt sie als `ARGUMENTS: …`
# an. Ohne Anweisung improvisiert Claude den Wiedereinstieg — neun Befehle
# hatten keine. `/60-validate` hatte sie bereits.

COMMANDS_DIR = REPO_ROOT / "core" / "commands"

# Befehle, die sich auf einen LAUFENDEN Workflow beziehen: Aufloesen + switch.
REENTRY_WITH_SWITCH = [
    "10-context", "20-analyse", "30-write-spec", "40-tdd-red", "50-implement",
    "60-validate", "70-deploy", "80-workflow", "81-add-artifact", "82-test",
    "83-user-story", "99-reset",
]

# Bewusste Abweichung: /90-retro analysiert einen ARCHIVIERTEN Workflow.
# `switch` gilt nur fuer laufende Workflows; hier wird im Archiv gesucht und
# mit `retro <name>` weitergearbeitet.
REENTRY_ARCHIVE_ONLY = ["90-retro"]

# Kein Wiedereinstieg: diese drei legen einen Workflow erst an bzw. klassifizieren
# eine Aufgabe — es gibt noch keinen State, den eine Nummer aufloesen koennte.
REENTRY_EXEMPT = ["00-intake", "00-bug", "01-feature"]


def _command(name: str) -> str:
    return (COMMANDS_DIR / f"{name}.md").read_text()


def test_every_command_is_classified_for_reentry():
    covered = set(REENTRY_WITH_SWITCH + REENTRY_ARCHIVE_ONLY + REENTRY_EXEMPT)
    assert covered == set(sync_skills.synced_names())


def test_reentry_commands_resolve_the_workflow_from_disk():
    for name in REENTRY_WITH_SWITCH:
        text = _command(name)
        # Aufruf-Beispiel, je nach Datei `#<N>` oder `#42`.
        assert f"/{name} #" in text, name
        assert ".claude/workflows/*.json" in text, name
        assert "workflow.py switch" in text, name
        assert "workflow.py status" in text, name
        assert "in 2 Sätzen" in text, name


def test_retro_searches_the_archive_instead_of_switching():
    text = _command("90-retro")
    assert "/90-retro #<N>" in text
    assert ".claude/workflows/_archive/*.json" in text
    assert "kein `workflow.py switch`" in text


def test_reentry_section_reaches_the_generated_skills():
    """Der Plugin-Nutzer sieht nur skills/ — dort muss es ankommen."""
    for name in REENTRY_WITH_SWITCH + REENTRY_ARCHIVE_ONLY:
        text = (REPO_ROOT / "skills" / name / "SKILL.md").read_text()
        assert f"/{name} #" in text, name


# --- Statuszeile im Marker-Block (3.25.0, AC-3) -------------------------------

def test_marker_block_demands_a_status_line_above_the_version_marker():
    block = sync_skills.marker_block("60-validate", "9.9.9")
    action_idx = block.index("❗ Du:")
    status_idx = block.index("ℹ️ Status: Workflow")
    marker_idx = block.index("⚙ /60-validate · agent-os-openspec 9.9.9")
    assert action_idx < status_idx < marker_idx, block
    assert "Phase `<x>` von 8" in block


def test_marker_block_says_who_is_on_turn_with_one_of_two_lines():
    """#174: Die Fußzeile darf nicht wie eine Aufgabe wirken, wenn Claude
    selbst arbeitet. Die erste Zeile ist entweder ❗ (PO ist dran) oder
    ℹ️ (nichts zu tun) — und nennt trotzdem den nächsten Schritt."""
    block = sync_skills.marker_block("60-validate", "9.9.9")
    assert "`❗ Du: …`" in block
    assert "ℹ️ Nichts zu tun:" in block
    assert "danach: /<befehl> #<N>" in block
    assert "‼️" in block
    # Das Wort „Pflicht-Schritt“ ist nur noch der Name im Hook-Hinweis,
    # keine Zeile mehr, die der PO als Aufforderung liest.
    assert "Nächster Pflicht-Schritt: `/<befehl> #<N>`" not in block


def test_marker_block_forbids_optional_wording_before_phase_8():
    block = sync_skills.marker_block("60-validate", "9.9.9")
    for forbidden in ("bei Bedarf", "optional", "fertig", "abgeschlossen", "erledigt"):
        assert forbidden in block, forbidden
    assert "/clear" in block and "Kosten-Empfehlung" in block


def test_status_line_rule_is_in_every_non_exempt_skill():
    for name in sync_skills.synced_names():
        if name in sync_skills.MARKER_EXEMPT:
            continue
        text = (REPO_ROOT / "skills" / name / "SKILL.md").read_text()
        assert "❗ Du:" in text, name
        assert "ℹ️ Nichts zu tun:" in text, name
        assert "ℹ️ Status: Workflow" in text, name


def test_status_line_wording_matches_the_hook_note():
    sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))
    import workflow

    note = workflow.status_note({"name": "fix-1761-x",
                                 "current_phase": "phase7_validate"})
    # Der Hook nennt den Schritt unter diesem Namen; der Baustein verweist
    # darauf, damit „wörtlich von dort“ eindeutig bleibt.
    assert "Nächster Pflicht-Schritt: /60-validate" in note
    assert "„Nächster Pflicht-Schritt“" in sync_skills.marker_block("60-validate", "9.9.9")
    # Beide Seiten kennen dieselben zwei Kennzeichnungen.
    for label in ("❗ Du:", "ℹ️ Nichts zu tun:"):
        assert label in note
        assert label in sync_skills.marker_block("60-validate", "9.9.9")


def test_marker_block_does_not_contradict_the_verbatim_handover_blocks():
    """Der Übergabe-Block von `/50-implement` nennt `/clear` bewusst VOR dem
    Folgebefehl. Die Sprachregel gilt deshalb ausdrücklich nur für frei
    formulierte Meldungen — sonst stünden zwei Anweisungen gegeneinander."""
    block = sync_skills.marker_block("50-implement", "9.9.9")
    assert "frei formulierten Arbeitsstandsmeldungen" in block
    assert "Übergabe-Blöcke oben bleiben unverändert" in block
