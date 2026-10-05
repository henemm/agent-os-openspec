"""Tests für Issue #372 — fremde `config.yaml` nicht als Plugin-Config lesen,
Freigabe-Sperre für Claude sichtbar (Spec docs/specs/fast/fix-app-config-yaml-372.md).

Fundfall: Ein Go-Dienst hat eine eigene `config.yaml` im Projekt-Root (gitignored,
enthält ein Bot-Token). `config_loader` las sie als Plugin-Config, bestimmte damit
die Projektwurzel und meldete „Grenzen aus: …/config.yaml". Das CI-Gate kannte
`openspec.yaml` gar nicht. Eine gescheiterte Freigabe sah nur der Nutzer.

AC-1 .. AC-7 je mindestens ein Test.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
SCRIPT = REPO_ROOT / "scripts" / "ci_spec_gate.py"
sys.path.insert(0, str(HOOKS_DIR))

import config_loader  # noqa: E402

APP_CONFIG = (
    "# App-Config eines fremden Dienstes (#372)\n"
    "bot_token: \"123456:SECRET\"\n"
    "project:\n"
    "  name: GoBot\n"
    "listen: \":8080\"\n"
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """tmp-Projekt als CLAUDE_PROJECT_DIR, mit frischem config_loader-Cache."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    config_loader.find_project_root.cache_clear()
    config_loader.load_config.cache_clear()
    yield tmp_path
    config_loader.find_project_root.cache_clear()
    config_loader.load_config.cache_clear()


# --- AC-1 -------------------------------------------------------------------

def test_ac1_app_config_yaml_is_ignored(project):
    """#372 AC-1: Root-config.yaml ohne Plugin-Block → Voreinstellungen gelten."""
    (project / "config.yaml").write_text(APP_CONFIG)
    cfg = config_loader.load_config()
    assert cfg["project"]["name"] == "Unnamed Project", cfg["project"]
    assert "bot_token" not in cfg
    assert config_loader._find_config_file(project) is None


def test_ac1_config_source_note_names_skipped_file(project):
    """#372 AC-1: config_source_note() nennt die übergangene Datei."""
    (project / "config.yaml").write_text(APP_CONFIG)
    note = config_loader.config_source_note()
    assert "übergangen" in note, note
    assert str(project / "config.yaml") in note, note
    assert "openspec.yaml" in note, note
    assert "<eingebaute Voreinstellung>" in note, note


def test_ac1_is_plugin_config_never_raises(tmp_path):
    """#372 AC-1: kaputtes YAML / fehlende Datei → False, keine Exception."""
    broken = tmp_path / "config.yaml"
    broken.write_text("bot_token: [unclosed\n  - : :\n")
    assert config_loader.is_plugin_config(broken) is False
    assert config_loader.is_plugin_config(tmp_path / "missing.yaml") is False


def test_ac1_generic_keys_alone_do_not_qualify(tmp_path):
    """#372 AC-1: nur allgemeine Namen (project/agents/deploy/modules/hooks) reichen nicht."""
    p = tmp_path / "config.yaml"
    p.write_text("project:\n  name: x\ndeploy:\n  target: y\nhooks:\n  a: 1\n")
    assert config_loader.is_plugin_config(p) is False


# --- AC-2 -------------------------------------------------------------------

@pytest.mark.parametrize("block", [
    "adr_gate:\n  enabled: false\n",
    "scope_guard:\n  max_loc_delta: 999\n",
])
def test_ac2_plugin_config_yaml_still_read(project, block):
    """#372 AC-2: Root-config.yaml mit Plugin-Block gilt wie bisher."""
    (project / "config.yaml").write_text("project:\n  name: Plugin\n" + block)
    cfg = config_loader.load_config()
    assert cfg["project"]["name"] == "Plugin"
    assert config_loader._find_config_file(project) == project / "config.yaml"
    assert "übergangen" not in config_loader.config_source_note()


def test_ac2_claude_dir_config_yaml_unchecked(project):
    """#372 AC-2: .claude/config.yaml bleibt ungeprüft gültig (Plugin-Ordner)."""
    (project / ".claude").mkdir()
    (project / ".claude" / "config.yaml").write_text("project:\n  name: InClaude\n")
    assert config_loader.load_config()["project"]["name"] == "InClaude"


def test_ac2_app_root_config_falls_through_to_claude_dir(project):
    """#372 AC-2: App-config.yaml im Root wird übersprungen, .claude/config.yaml greift."""
    (project / "config.yaml").write_text(APP_CONFIG)
    (project / ".claude").mkdir()
    (project / ".claude" / "config.yaml").write_text("project:\n  name: InClaude\n")
    assert config_loader.load_config()["project"]["name"] == "InClaude"


# --- AC-3 -------------------------------------------------------------------

def test_ac3_openspec_yaml_wins_over_app_config(project):
    """#372 AC-3: openspec.yaml + App-config.yaml → openspec.yaml gilt."""
    (project / "config.yaml").write_text(APP_CONFIG)
    (project / "openspec.yaml").write_text("project:\n  name: FromOpenspec\n")
    cfg = config_loader.load_config()
    assert cfg["project"]["name"] == "FromOpenspec"
    assert "bot_token" not in cfg
    note = config_loader.config_source_note()
    assert f"Grenzen aus: {project / 'openspec.yaml'}" in note, note


# --- AC-4 -------------------------------------------------------------------

def test_ac4_app_config_does_not_mark_root(tmp_path, monkeypatch):
    """#372 AC-4: Unterordner mit App-config.yaml → Wurzel ist das Git-Repo."""
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "services" / "bot"
    sub.mkdir(parents=True)
    (sub / "config.yaml").write_text(APP_CONFIG)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(sub)
    config_loader.find_project_root.cache_clear()
    try:
        assert config_loader.find_project_root() == tmp_path
    finally:
        config_loader.find_project_root.cache_clear()
        config_loader.load_config.cache_clear()


def test_ac4_plugin_config_still_marks_root(tmp_path, monkeypatch):
    """#372 AC-4 (Gegenprobe): Plugin-config.yaml im Unterordner markiert ihn weiter."""
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "config.yaml").write_text("adr_gate:\n  enabled: true\n")
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(sub)
    config_loader.find_project_root.cache_clear()
    try:
        assert config_loader.find_project_root() == sub
    finally:
        config_loader.find_project_root.cache_clear()
        config_loader.load_config.cache_clear()


# --- AC-5 -------------------------------------------------------------------

CODE_REL = "src/app.py"


def _run_ci(root: Path, changed: list[str]):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--changed-files", *changed],
        capture_output=True, text=True, env=dict(os.environ),
    )


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_ac5_kill_switch_from_openspec_yaml(tmp_path):
    """#372 AC-5: ci_spec_gate.enabled: false in openspec.yaml schaltet das CI-Gate ab."""
    _write(tmp_path, CODE_REL, "def f():\n    return 1\n")
    _write(tmp_path, "openspec.yaml", "ci_spec_gate:\n  enabled: false\n")
    r = _run_ci(tmp_path, [CODE_REL])
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"


def test_ac5_app_config_yaml_not_read_by_ci_gate(tmp_path):
    """#372 AC-5: App-config.yaml ohne Plugin-Block wird vom CI-Gate nicht gelesen."""
    sys.path.insert(0, str(SCRIPT.parent))
    import ci_spec_gate
    _write(tmp_path, "config.yaml", "project:\n  enabled: false\nbot_token: x\n")
    assert ci_spec_gate._config(tmp_path, "project") == {}


def test_ac5_ci_gate_fallback_without_config_loader(tmp_path, monkeypatch):
    """#372 AC-5: auch ohne importierbaren config_loader (Fallback-Resolver)."""
    sys.path.insert(0, str(SCRIPT.parent))
    import ci_spec_gate
    monkeypatch.setattr(ci_spec_gate, "_load_hook_module", lambda root, name: None)
    _write(tmp_path, "config.yaml", "project:\n  enabled: false\nbot_token: x\n")
    assert ci_spec_gate._config(tmp_path, "project") == {}
    _write(tmp_path, "openspec.yaml", "ci_spec_gate:\n  enabled: false\n")
    assert ci_spec_gate._config(tmp_path)["enabled"] is False


def test_ac5_plugin_config_yaml_still_read_by_ci_gate(tmp_path):
    """#372 AC-5 (Gegenprobe): Plugin-config.yaml bleibt Quelle des Kill-Switch."""
    _write(tmp_path, CODE_REL, "def f():\n    return 1\n")
    _write(tmp_path, "config.yaml", "ci_spec_gate:\n  enabled: false\n")
    r = _run_ci(tmp_path, [CODE_REL])
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"


# --- AC-6 -------------------------------------------------------------------

ADR_MISSING_VALUE = (
    "## Architektur-Entscheidung (ADR)\n\n"
    "- **ADR-Nr.:** \n"
    "- **Begründung:** Fließtext ohne Entscheidung.\n"
)

BRIEFING_REL = "docs/briefings/wf372.md"
BRIEFING_BODY = (
    "# PO-Briefing: wf372\n\n"
    "## Was gebaut wird\n\nEine kleine, klar umrissene Änderung am Modul.\n\n"
    "## Definition of Done\n\nFertig, wenn das beschriebene Verhalten sichtbar eintritt.\n\n"
    "## Wie geprüft wird\n\nEin automatischer Test prüft genau dieses Verhalten.\n\n"
    "## Kritische Anmerkungen\n\n- Keine offenen Punkte erkennbar.\n"
)


def _spec_phase_workflow(root: Path, with_briefing: bool) -> Path:
    rel_spec = "docs/specs/m/spec.md"
    _write(root, rel_spec, "# Spec\n\n## Purpose\n\nInhalt.\n\n" + ADR_MISSING_VALUE)
    wf_dir = root / ".claude" / "workflows"
    (wf_dir / "_log").mkdir(parents=True, exist_ok=True)
    data = {
        "name": "wf372",
        "workflow_type": "feature",
        "current_phase": "phase3_spec",
        "context_file": "docs/context.md",
        "spec_file": rel_spec,
        "spec_approved": False,
        "phase_transitions": [],
        "phase_log": [],
    }
    if with_briefing:
        _write(root, BRIEFING_REL, BRIEFING_BODY)
        data["po_briefing"] = {"file": BRIEFING_REL, "created": "2026-01-01T00:00:00"}
    wf_file = wf_dir / "wf372.json"
    wf_file.write_text(json.dumps(data))
    return wf_file


def _approve(root: Path) -> tuple[subprocess.CompletedProcess, dict]:
    env = dict(os.environ)
    env.update({"CLAUDE_PROJECT_DIR": str(root), "OPENSPEC_ACTIVE_WORKFLOW": "wf372"})
    r = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "phase_listener.py")],
        input=json.dumps({"prompt": "approved"}),
        capture_output=True, text=True, env=env, cwd=str(root),
    )
    out = None
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            out = json.loads(line)
    assert out is not None, f"kein JSON auf stdout: {r.stdout!r} stderr={r.stderr!r}"
    return r, out


def test_ac6_blocked_approval_reason_in_additional_context(tmp_path):
    """#372 AC-6: leeres ADR-Feld → Sperrgrund als additionalContext für Claude."""
    wf_file = _spec_phase_workflow(tmp_path, with_briefing=True)
    _, out = _approve(tmp_path)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "ADR" in ctx, out
    assert "spec_approved" in ctx and "NICHT" in ctx, ctx
    assert json.loads(wf_file.read_text())["spec_approved"] is False


def test_ac6_both_reasons_listed(tmp_path):
    """#372 AC-6: scheitern ADR und Briefing, stehen beide Gründe darin."""
    _spec_phase_workflow(tmp_path, with_briefing=False)
    _, out = _approve(tmp_path)
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "ADR" in ctx, ctx
    assert "PO-Briefing" in ctx, ctx
    sysmsg = out.get("systemMessage", "")
    assert "ADR" in sysmsg and "PO-Briefing" in sysmsg, sysmsg


# --- AC-7 -------------------------------------------------------------------

def _top_level_keys(text: str) -> set[str]:
    return set(re.findall(r"^([A-Za-z_][\w-]*)\s*:", text, re.MULTILINE))


def test_ac7_template_keys_classified():
    """#372 AC-7: jeder Top-Level-Schlüssel der Template-config.yaml ist eingeordnet."""
    keys = _top_level_keys((REPO_ROOT / "config.yaml").read_text())
    known = config_loader.PLUGIN_CONFIG_KEYS | config_loader.GENERIC_CONFIG_KEYS
    assert keys, "keine Top-Level-Schlüssel gefunden"
    assert keys <= known, f"nicht eingeordnet: {sorted(keys - known)}"
    assert not (config_loader.PLUGIN_CONFIG_KEYS & config_loader.GENERIC_CONFIG_KEYS)


def test_ac7_repo_config_is_plugin_config():
    """#372 AC-7: die eigene Template-config.yaml besteht is_plugin_config()."""
    assert config_loader.is_plugin_config(REPO_ROOT / "config.yaml") is True


def test_ac2_flow_style_plugin_config_recognized(tmp_path):
    """#372 AC-2: Plugin-config.yaml im Flow-/JSON-Stil wird weiter erkannt."""
    p = tmp_path / "config.yaml"
    p.write_text('{"strict_code_gate": {"code_extensions": [".py"]}}\n')
    assert config_loader.is_plugin_config(p) is True


def test_ac7_ci_gate_fallback_keys_match_config_loader():
    """#372 AC-7: _FALLBACK_PLUGIN_KEYS im CI-Gate ist eine vollständige Kopie."""
    sys.path.insert(0, str(SCRIPT.parent))
    import ci_spec_gate
    assert ci_spec_gate._FALLBACK_PLUGIN_KEYS == config_loader.PLUGIN_CONFIG_KEYS


# --- Adversary-Runde (#372) ---------------------------------------------------

@pytest.mark.parametrize("key", ["bug_fix", "e2e_tests", "output_specs"])
def test_legacy_plugin_blocks_recognized(tmp_path, key):
    """#372: bug_fix / e2e_tests / output_specs gelten als Plugin-Blöcke."""
    p = tmp_path / "config.yaml"
    p.write_text(f"{key}:\n  enabled: true\n")
    assert config_loader.is_plugin_config(p) is True
    assert key in config_loader.PLUGIN_CONFIG_KEYS


def test_is_plugin_config_skips_fifo(tmp_path):
    """#372: FIFO als config.yaml → False, ohne zu hängen."""
    fifo = tmp_path / "config.yaml"
    os.mkfifo(fifo)
    assert config_loader.is_plugin_config(fifo) is False


def test_is_plugin_config_large_file_regex_only(tmp_path, monkeypatch):
    """#372: Datei > 256 KB → kein YAML-Parse, Regex auf den Anfang."""
    p = tmp_path / "config.yaml"
    p.write_text("adr_gate:\n  enabled: true\n" + "# x\n" * 100_000)

    class _Boom:
        @staticmethod
        def safe_load(_):
            raise AssertionError("YAML-Parse bei großer Datei")

    monkeypatch.setattr(config_loader, "yaml", _Boom)
    assert config_loader.is_plugin_config(p) is True
    big_app = tmp_path / "app.yaml"
    big_app.write_text("# x\n" * 100_000 + "adr_gate:\n  enabled: true\n")
    assert config_loader.is_plugin_config(big_app) is False


def test_ci_fallback_skips_fifo(tmp_path, monkeypatch):
    """#372: CI-Fallback-Resolver liest keinen FIFO."""
    sys.path.insert(0, str(SCRIPT.parent))
    import ci_spec_gate
    monkeypatch.setattr(ci_spec_gate, "_load_hook_module", lambda root, name: None)
    os.mkfifo(tmp_path / "config.yaml")
    assert ci_spec_gate._find_config_file(tmp_path) is None


def test_note_silent_when_openspec_yaml_wins(project):
    """#372: openspec.yaml gewinnt ohnehin → kein 'übergangen'-Hinweis."""
    (project / "config.yaml").write_text(APP_CONFIG)
    (project / "openspec.yaml").write_text("project:\n  name: X\n")
    assert "übergangen" not in config_loader.config_source_note()


def _deploy_config(root: Path) -> str:
    env = {k: v for k, v in os.environ.items() if k != "OPENSPEC_FRAMEWORK"}
    env.update({"CLAUDE_PROJECT_DIR": str(root), "OPENSPEC_ACTIVE_WORKFLOW": ""})
    r = subprocess.run([sys.executable, str(HOOKS_DIR / "workflow.py"), "deploy-config"],
                       capture_output=True, text=True, env=env, cwd=str(root))
    assert r.returncode == 0, r.stderr
    return r.stdout


DEPLOY_ONLY = ('deploy:\n  command: "./deploy.sh"\n  verify: "./verify.sh"\n')


def test_deploy_config_hints_skipped_config_yaml(tmp_path):
    """#372: deploy-only config.yaml wird übergangen — deploy-config nennt sie."""
    (tmp_path / "config.yaml").write_text(DEPLOY_ONLY)
    lines = _deploy_config(tmp_path).splitlines()
    assert lines[0] == "DEPLOY_CONFIGURED=no"
    assert lines[-1].startswith("HINWEIS: ") and "übergangen" in lines[-1], lines


def test_deploy_config_from_openspec_yaml_no_hint(tmp_path):
    """#372: deploy: in openspec.yaml → konfiguriert, kein HINWEIS."""
    (tmp_path / "openspec.yaml").write_text(DEPLOY_ONLY)
    out = _deploy_config(tmp_path)
    assert out.splitlines()[0] == "DEPLOY_CONFIGURED=yes"
    assert "HINWEIS" not in out


def test_70_deploy_points_to_openspec_yaml():
    """#372: /70-deploy lässt deploy: in openspec.yaml eintragen."""
    text = (REPO_ROOT / "core" / "commands" / "70-deploy.md").read_text()
    assert "in `openspec.yaml` unter `deploy:`" in text
    assert "(`config.yaml` bzw. `openspec.yaml`)" not in text
