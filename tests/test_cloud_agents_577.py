"""Tests fuer Issue #577: Framework-Agenten in Cloud-Sitzungen.

Spec: docs/specs/feat-577-cloud-agents.md (AC-1 bis AC-16).

Aufbau (Spec, "Test Plan"): echte Dateien in tmp_path, Skript per Import bzw.
`subprocess`, `setup.py` gegen eine Framework-Kopie (ohne `.git`, Version 9.9.9)
und ein Plugin-Modus-Projekt mit Pin (Aufbau wie tests/test_cloud_gates_522.py).
Kein Mock von Dateisystem oder git.

`scripts/sync_cloud_agents.py` wird in jedem Test lazy geladen: fehlt das Modul,
scheitert der einzelne Test (ModuleNotFoundError), die Datei bleibt sammelbar.

Erwartete Namen (Spec, Implementation Details):
  sync_cloud_agents.AGENT_MARKER        Markerzeile (ohne Zeilenende)
  sync_cloud_agents.render_agent(text)  Quelle -> Generat (Marker nach Frontmatter)
  sync_cloud_agents.plan(src, dst)      -> (writes, removals, skipped), schreibt nichts
  sync_cloud_agents.sync(root)          schreibt <root>/.claude/agents aus <root>/core/agents
  sync_cloud_agents.check(root)         -> (ok, msg), schreibt nichts
  CLI: --check (Exit 1 bei Drift), --root <pfad>
  release_check.check_cloud_agents(root=None) -> (ok, msg)
"""

import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
AGENTS_SRC = REPO_ROOT / "core" / "agents"
COMMANDS = REPO_ROOT / "core" / "commands"
SCRIPT = SCRIPTS / "sync_cloud_agents.py"
SYNC_HINT = "python3 scripts/sync_cloud_agents.py"

FW_VERSION = "9.9.9"
TAG = f"agent-os-openspec--v{FW_VERSION}"

# AC-10: diese benannten Agenten starten die Befehle in Werkzeug-Syntax.
# Zuordnung Befehl -> Agenten laut Spec (Scope/Affected Files).
COMMAND_AGENTS = {
    "30-write-spec.md": ["spec-writer", "spec-validator", "po-briefer"],
    "50-implement.md": ["developer-agent", "implementation-validator"],
    "60-validate.md": ["docs-updater"],
    "20-analyse.md": ["bug-intake"],
    "01-feature.md": ["feature-planner"],
    "82-test.md": ["test-runner"],
}
ANON_TYPES = ("general-purpose", "Explore", "Plan")


# ------------------------------------------------------------------ Helfer
def _load(name="sync_cloud_agents"):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def _sources(src_dir: Path = AGENTS_SRC) -> list:
    return sorted(p for p in src_dir.glob("*.md") if p.is_file())


def _frontmatter(path: Path) -> dict:
    """name/model/tools-Werte aus dem YAML-Frontmatter (einfacher Zeilenparser)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].strip() == "---", f"{path.name}: kein Frontmatter"
    out = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _agent_models() -> dict:
    return {_frontmatter(p)["name"]: _frontmatter(p)["model"] for p in _sources()}


def _closing_fm_index(lines: list) -> int:
    assert lines[0].strip() == "---"
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    raise AssertionError("Frontmatter nicht geschlossen")


def _assert_copy_of(dst_text: str, src_text: str, marker: str, name: str) -> None:
    """Generat == Quelle bis auf genau eine Markerzeile direkt nach dem Frontmatter."""
    dst_lines = dst_text.splitlines(keepends=True)
    hits = [i for i, ln in enumerate(dst_lines) if ln.strip() == marker.strip()]
    assert len(hits) == 1, f"{name}: erwartet genau eine Markerzeile, gefunden {len(hits)}"
    rest = dst_lines[:hits[0]] + dst_lines[hits[0] + 1:]
    assert "".join(rest) == src_text, f"{name}: Generat weicht ausser der Markerzeile von der Quelle ab"
    src_lines = src_text.splitlines(keepends=True)
    if src_lines and src_lines[0].strip() == "---":
        assert hits[0] == _closing_fm_index(src_lines) + 1, \
            f"{name}: Marker steht nicht direkt hinter dem Frontmatter"


def _make_root(tmp_path: Path, names=None) -> Path:
    """Mini-Repo mit core/agents (Kopien echter Quellen), ohne .claude/agents."""
    root = tmp_path / "repo"
    (root / "core" / "agents").mkdir(parents=True)
    for src in _sources():
        if names is None or src.stem in names:
            shutil.copy2(src, root / "core" / "agents" / src.name)
    return root


def _run_script(root: Path, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *args],
                          capture_output=True, text=True, timeout=60)


def _snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _lines_with(text: str, *needles) -> list:
    return [ln for ln in text.splitlines() if all(n in ln for n in needles)]


# ------------------------------------------------------------------ AC-1
def test_generated_copy_equals_source_except_marker(tmp_path):
    mod = _load()
    marker = mod.AGENT_MARKER
    assert marker.strip().startswith("<!--") and marker.strip().endswith("-->"), \
        "AGENT_MARKER soll ein HTML-Kommentar sein"
    assert "\n" not in marker.strip()

    # Quelle ohne Frontmatter: Marker als erste Zeile
    plain = "Kein Frontmatter\nzweite Zeile\n"
    rendered = mod.render_agent(plain)
    assert rendered.splitlines()[0].strip() == marker.strip()
    _assert_copy_of(rendered, plain, marker, "ohne-frontmatter")

    # sync in ein leeres Ziel
    root = _make_root(tmp_path)
    assert not (root / ".claude" / "agents").exists()
    mod.sync(root)
    dst_dir = root / ".claude" / "agents"
    srcs = _sources(root / "core" / "agents")
    assert sorted(p.name for p in dst_dir.glob("*.md")) == [p.name for p in srcs]
    for src in srcs:
        dst = dst_dir / src.name
        assert not dst.is_symlink(), f"{src.name}: Kopie erwartet, kein Symlink"
        src_text = src.read_text(encoding="utf-8")
        _assert_copy_of(dst.read_text(encoding="utf-8"), src_text, marker, src.name)
        assert _frontmatter(dst) == _frontmatter(src), f"{src.name}: Frontmatter veraendert"
        assert mod.render_agent(src_text) == dst.read_text(encoding="utf-8")

    # Generat im Framework-Repo: vorhanden, synchron, nicht ignoriert
    repo_dst = REPO_ROOT / ".claude" / "agents"
    for src in _sources():
        dst = repo_dst / src.name
        assert dst.is_file() and not dst.is_symlink(), f".claude/agents/{src.name} fehlt im Repo"
        _assert_copy_of(dst.read_text(encoding="utf-8"), src.read_text(encoding="utf-8"),
                        marker, f"repo:{src.name}")
        ignored = subprocess.run(["git", "check-ignore", "-q", str(dst)], cwd=str(REPO_ROOT),
                                 capture_output=True)
        assert ignored.returncode == 1, f".claude/agents/{src.name} ist gitignored"
    r = subprocess.run([sys.executable, str(SCRIPT), "--check"], cwd=str(REPO_ROOT),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


# ------------------------------------------------------------------ AC-2
def test_check_detects_missing_diverged_and_stale(tmp_path):
    mod = _load()
    root = _make_root(tmp_path)
    mod.sync(root)
    dst_dir = root / ".claude" / "agents"
    # fehlt
    (dst_dir / "spec-writer.md").unlink()
    # abweichend (markiert, Inhalt anders)
    div = dst_dir / "po-briefer.md"
    div.write_text(div.read_text(encoding="utf-8") + "\nlokal veraendert\n", encoding="utf-8")
    # veraltet (markiert, Quelle entfernt)
    (root / "core" / "agents" / "test-runner.md").unlink()

    before = _snapshot(root)
    r = _run_script(root, "--check")
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert _lines_with(out, "fehlt", "spec-writer"), out
    assert _lines_with(out, "abweichend", "po-briefer"), out
    assert _lines_with(out, "veraltet", "test-runner"), out
    assert _snapshot(root) == before, "--check darf nichts schreiben"

    r = _run_script(root)
    assert r.returncode == 0, r.stdout + r.stderr
    r = _run_script(root, "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (dst_dir / "test-runner.md").exists()
    assert (dst_dir / "spec-writer.md").exists()


# ------------------------------------------------------------------ AC-3
def test_unmarked_files_never_overwritten_or_deleted(tmp_path):
    _load()
    root = _make_root(tmp_path)
    dst_dir = root / ".claude" / "agents"
    dst_dir.mkdir(parents=True)
    own = dst_dir / "po-briefer.md"
    own.write_bytes(b"---\nname: po-briefer\nmodel: opus\n---\n\nEigene Fassung \xc3\xa4\n")
    module_agent = dst_dir / "ios-helper.md"
    module_agent.write_bytes(b"---\nname: ios-helper\n---\n\nModul-Agent\n")
    own_bytes, mod_bytes = own.read_bytes(), module_agent.read_bytes()

    r = _run_script(root)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert own.read_bytes() == own_bytes
    assert module_agent.read_bytes() == mod_bytes
    assert _lines_with(out, "Skipped", "po-briefer"), out
    assert _lines_with(out, "Skipped", "ios-helper"), out
    assert (dst_dir / "spec-writer.md").exists(), "andere Agenten muessen geschrieben werden"

    r = _run_script(root, "--check")
    assert r.returncode == 0, "unmarkierte Dateien zaehlen nicht als Drift: " + r.stdout + r.stderr
    assert own.read_bytes() == own_bytes
    assert module_agent.read_bytes() == mod_bytes


# ------------------------------------------------------------------ AC-4
def test_stale_marked_files_are_removed(tmp_path):
    mod = _load()
    root = _make_root(tmp_path)
    mod.sync(root)
    dst_dir = root / ".claude" / "agents"
    ghost = dst_dir / "ghost.md"
    ghost.write_text(mod.render_agent("---\nname: ghost\nmodel: haiku\n---\n\nalt\n"),
                     encoding="utf-8")
    keep = {p.name: p.read_bytes() for p in dst_dir.glob("*.md") if p.name != "ghost.md"}

    before = _snapshot(root)
    writes, removals, skipped = mod.plan(root / "core" / "agents", dst_dir)
    assert _snapshot(root) == before, "plan() darf nichts schreiben"
    assert [Path(str(r)).name for r in removals] == ["ghost.md"], removals
    assert not writes, writes
    assert not skipped, skipped

    mod.sync(root)
    assert not ghost.exists(), "veraltete markierte Datei nicht entfernt"
    assert {p.name: p.read_bytes() for p in dst_dir.glob("*.md")} == keep


# ------------------------------------------------------------------ AC-5
def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _fake_release_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    origin = tmp_path / "origin.git"
    _git(["init", "--bare", "-b", "main", str(origin)], tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    _git(["init", "-b", "main"], work)
    _git(["config", "user.email", "test@example.invalid"], work)
    _git(["config", "user.name", "Test"], work)
    _git(["config", "commit.gpgsign", "false"], work)
    _write_release_files(work, "1.0.0")
    _git(["add", "-A"], work)
    _git(["commit", "-m", "release 1.0.0"], work)
    _git(["remote", "add", "origin", str(origin)], work)
    _git(["push", "-u", "origin", "main"], work)
    return work


def _write_release_files(work: Path, version: str) -> None:
    (work / ".claude-plugin").mkdir(exist_ok=True)
    (work / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "agent-os-openspec", "version": version}))
    (work / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [Unreleased]\n\n\n## [{version}] - 2026-11-11\n\nx\n")
    (work / "README.md").write_text(f"**Version**: {version} · [Changelog](CHANGELOG.md)\n")
    (work / "CLAUDE.md").write_text(f"# Projekt\n\n**Version**: {version}\n")


def _labels(out: str) -> list:
    return [m.group(2) for m in re.finditer(r"^\s+(OK|FAIL)\s+(\S+)", out, re.M)]


def test_release_check_has_cloud_agents_line(tmp_path, monkeypatch, capsys):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    release_check = importlib.import_module("release_check")
    mod = _load()

    # Funktion: gruen bei synchronem Ziel, rot mit Hinweis bei Drift
    ok, msg = release_check.check_cloud_agents()
    assert ok, msg
    root = _make_root(tmp_path / "agents")
    mod.sync(root)
    ok, msg = release_check.check_cloud_agents(root)
    assert ok, msg
    victim = root / ".claude" / "agents" / "spec-writer.md"
    victim.write_text(victim.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
    ok, msg = release_check.check_cloud_agents(root)
    assert not ok, msg
    assert SYNC_HINT in msg, msg

    # Zeile "Cloud-Agenten" direkt hinter "Cloud-Hooks" in Voll- und Vorab-Check
    work = _fake_release_repo(tmp_path / "rel")
    monkeypatch.setattr(release_check, "REPO_ROOT", work)
    monkeypatch.setattr(release_check, "PLUGIN_JSON", work / ".claude-plugin" / "plugin.json")
    monkeypatch.setattr(release_check, "CHANGELOG", work / "CHANGELOG.md")
    monkeypatch.setattr(release_check, "README", work / "README.md")
    monkeypatch.setattr(release_check, "CLAUDE_MD", work / "CLAUDE.md")
    monkeypatch.setattr(release_check, "check_skills_sync", lambda: (True, "stub"))

    monkeypatch.setattr(sys, "argv", ["release_check.py", "--no-tests"])
    release_check.main()
    labels = _labels(capsys.readouterr().out)
    assert "Cloud-Agenten" in labels, labels
    assert labels.index("Cloud-Agenten") == labels.index("Cloud-Hooks") + 1, labels

    _write_release_files(work, "1.1.0")
    release_check.run_pr_gate("origin/main")
    labels = _labels(capsys.readouterr().out)
    assert "Cloud-Agenten" in labels, labels
    assert labels.index("Cloud-Agenten") == labels.index("Cloud-Hooks") + 1, labels


# ------------------------------------------------------------------ setup.py-Aufbau (wie #522)
_FW_PARTS = ["setup.py", "config.yaml", ".claude-plugin", "core", "hooks", "scripts", "skills",
             "templates", "modules", "migrate_to_plugin.py"]


def _clean_env() -> dict:
    drop = ("CLAUDE_", "GIT_", "AGENT_OS_", "OPENSPEC_")
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    return env


def _git_env(args, cwd) -> str:
    r = subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=Test",
                        "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, env=_clean_env())
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


@pytest.fixture(scope="module")
def fw_copy(tmp_path_factory) -> Path:
    """Framework-Kopie ohne .git, Version 9.9.9 — Pin-Aufloesung nur ueber ls-remote."""
    dst = tmp_path_factory.mktemp("fwcopy577") / "agent-os-openspec"
    dst.mkdir()
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for part in _FW_PARTS:
        src = REPO_ROOT / part
        if src.is_dir():
            shutil.copytree(src, dst / part, ignore=ignore)
        elif src.exists():
            shutil.copy2(src, dst / part)
    pj = dst / ".claude-plugin" / "plugin.json"
    data = json.loads(pj.read_text(encoding="utf-8"))
    data["version"] = FW_VERSION
    pj.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return dst


def _remote(tmp_path: Path) -> "tuple[str, str]":
    """Fake-Framework-Remote mit annotiertem Tag; liefert (URL, Commit-SHA)."""
    repo = tmp_path / "remote"
    (repo / "core" / "hooks").mkdir(parents=True)
    (repo / "core" / "hooks" / "probe.py").write_text("print('x')\n", encoding="utf-8")
    _git_env(["init", "-q", "-b", "main"], repo)
    _git_env(["add", "-A"], repo)
    _git_env(["commit", "-q", "-m", "release"], repo)
    _git_env(["tag", "-a", TAG, "-m", f"release {TAG}"], repo)
    return repo.as_uri(), _git_env(["rev-parse", f"{TAG}^{{commit}}"], repo)


def _setup(fw: Path, proj: Path, *args, url: str, tmp_path: Path):
    home = tmp_path / "setup-home"
    home.mkdir(exist_ok=True)
    env = _clean_env()
    env.update(AGENT_OS_CLOUD_REPO=url, HOME=str(home), GIT_CEILING_DIRECTORIES=str(fw.parent))
    return subprocess.run([sys.executable, str(fw / "setup.py"), str(proj), *args],
                          cwd=str(fw), env=env, capture_output=True, text=True, timeout=120)


def _plugin_project(tmp_path: Path, name="consumer", **fv_extra) -> Path:
    proj = tmp_path / name
    (proj / ".claude").mkdir(parents=True)
    fv = {"framework_version": None, "version_source": "plugin", "note": "x",
          "installed": "2026-01-01T00:00:00", "installed_modules": [], "plugin_mode": True}
    fv.update(fv_extra)
    (proj / ".claude" / "framework_version.json").write_text(json.dumps(fv, indent=2),
                                                             encoding="utf-8")
    return proj


def _assert_marked_copies(proj: Path, fw: Path, marker: str, skip=()) -> None:
    dst_dir = proj / ".claude" / "agents"
    for src in _sources(fw / "core" / "agents"):
        if src.stem in skip:
            continue
        dst = dst_dir / src.name
        assert dst.is_file(), f".claude/agents/{src.name} fehlt"
        _assert_copy_of(dst.read_text(encoding="utf-8"), src.read_text(encoding="utf-8"),
                        marker, src.name)


def _new_files(root: Path) -> list:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*.new"))


# ------------------------------------------------------------------ AC-6
def test_cloud_gates_writes_marked_agent_copies(tmp_path, fw_copy):
    mod = _load()
    marker = mod.AGENT_MARKER
    url, _ = _remote(tmp_path)
    proj = _plugin_project(tmp_path)
    dst_dir = proj / ".claude" / "agents"
    dst_dir.mkdir()
    own = dst_dir / "po-briefer.md"
    own.write_bytes(b"---\nname: po-briefer\nmodel: opus\n---\n\nEigene Fassung\n")
    own_bytes = own.read_bytes()
    stale = dst_dir / "ghost.md"
    stale.write_text(mod.render_agent("---\nname: ghost\nmodel: haiku\n---\n\nalt\n"),
                     encoding="utf-8")

    r = _setup(fw_copy, proj, "--cloud-gates", url=url, tmp_path=tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    _assert_marked_copies(proj, fw_copy, marker, skip={"po-briefer"})
    for src in _sources(fw_copy / "core" / "agents"):
        if src.stem != "po-briefer":
            assert f"Geschrieben: .claude/agents/{src.name}" in r.stdout, \
                f"{src.name} fehlt unter 'Geschrieben':\n{r.stdout}"
    assert not stale.exists(), "veraltet markierte Kopie nicht entfernt"
    assert own.read_bytes() == own_bytes, "unmarkierte gleichnamige Datei veraendert"
    assert _lines_with(out, "Skipped", "po-briefer"), out

    before = _snapshot(proj)
    r = _setup(fw_copy, proj, "--cloud-gates", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _snapshot(proj) == before, "zweiter Lauf hat Dateien geaendert"


# ------------------------------------------------------------------ AC-7
def test_update_with_pin_refreshes_copies_without_pin_does_not(tmp_path, fw_copy):
    mod = _load()
    marker = mod.AGENT_MARKER
    url, commit = _remote(tmp_path)

    proj = _plugin_project(tmp_path, cloud_ref="agent-os-openspec--v0.0.1", cloud_sha="a" * 40)
    dst_dir = proj / ".claude" / "agents"
    dst_dir.mkdir()
    old = dst_dir / "spec-writer.md"
    old.write_text(mod.render_agent("---\nname: spec-writer\nmodel: opus\n---\n\nveraltet\n"),
                   encoding="utf-8")
    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    _assert_marked_copies(proj, fw_copy, marker)
    assert "veraltet" not in old.read_text(encoding="utf-8")
    fv = json.loads((proj / ".claude" / "framework_version.json").read_text(encoding="utf-8"))
    assert fv.get("cloud_ref") == TAG and fv.get("cloud_sha") == commit, fv

    # Plugin-Modus ohne Pin: --update schreibt keine Agenten
    plain = _plugin_project(tmp_path, name="ohne-pin")
    (plain / ".claude" / "agents").mkdir()
    r = _setup(fw_copy, plain, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert list((plain / ".claude" / "agents").iterdir()) == [], \
        "ohne Pin darf --update im Plugin-Modus keine Agenten schreiben"
    plain2 = _plugin_project(tmp_path, name="ohne-pin-ohne-ordner")
    r = _setup(fw_copy, plain2, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (plain2 / ".claude" / "agents").exists()

    # Copy-Modus: --cloud-gates bleibt abgewiesen, schreibt nichts
    copy_proj = tmp_path / "copymode"
    (copy_proj / ".claude" / "hooks").mkdir(parents=True)
    (copy_proj / ".claude" / "framework_version.json").write_text(
        json.dumps({"framework_version": "4.9.0", "installed_modules": []}), encoding="utf-8")
    before = _snapshot(copy_proj)
    r = _setup(fw_copy, copy_proj, "--cloud-gates", url=url, tmp_path=tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert _snapshot(copy_proj) == before


# ------------------------------------------------------------------ AC-8
def test_update_in_plugin_mode_does_not_flip_flop(tmp_path, fw_copy):
    mod = _load()
    marker = mod.AGENT_MARKER
    url, _ = _remote(tmp_path)
    proj = _plugin_project(tmp_path, cloud_ref="agent-os-openspec--v0.0.1", cloud_sha="a" * 40)
    (proj / ".claude" / "agents").mkdir()

    def check_state():
        _assert_marked_copies(proj, fw_copy, marker)
        assert _new_files(proj) == [], _new_files(proj)
        manifest_path = proj / ".claude" / "framework_manifest.json"
        if manifest_path.exists():
            files = json.loads(manifest_path.read_text(encoding="utf-8")).get("files", {})
            agent_entries = [k for k in files if k.startswith(".claude/agents/")]
            assert agent_entries == [], f"Manifest fuehrt Agenten: {agent_entries}"

    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    check_state()
    before = {k: v for k, v in _snapshot(proj).items()
              if k != str(Path(".claude") / "framework_version.json")}

    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    check_state()
    after = {k: v for k, v in _snapshot(proj).items()
             if k != str(Path(".claude") / "framework_version.json")}
    assert after == before, "zweiter --update-Lauf hat Dateien geaendert"


# ------------------------------------------------------------------ AC-9
def test_copy_mode_agents_unchanged(tmp_path, fw_copy):
    mod = _load()
    marker = mod.AGENT_MARKER
    url, _ = _remote(tmp_path)
    proj = tmp_path / "copyproj"
    proj.mkdir()
    r = _setup(fw_copy, proj, url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    dst_dir = proj / ".claude" / "agents"
    srcs = _sources(fw_copy / "core" / "agents")
    for src in srcs:
        dst = dst_dir / src.name
        assert dst.read_bytes() == src.read_bytes(), f"{src.name}: Copy-Modus-Kopie weicht ab"
        assert marker.strip() not in dst.read_text(encoding="utf-8")
    manifest_path = proj / ".claude" / "framework_manifest.json"
    files = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
    for src in srcs:
        assert f".claude/agents/{src.name}" in files, f"Manifest-Eintrag fehlt: {src.name}"

    # Veraltete, unveraenderte Kopie (Hash laut Manifest) wird per --update erneuert
    target = dst_dir / "spec-writer.md"
    target.write_bytes(b"alte Framework-Fassung\n")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["files"][".claude/agents/spec-writer.md"] = hashlib.sha256(
        b"alte Framework-Fassung\n").hexdigest()
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert target.read_bytes() == (fw_copy / "core" / "agents" / "spec-writer.md").read_bytes()
    for src in srcs:
        assert marker.strip() not in (dst_dir / src.name).read_text(encoding="utf-8")
    assert not (dst_dir / "spec-writer.md.new").exists()


# ------------------------------------------------------------------ AC-15
def _write_manifest(proj: Path, files: dict) -> Path:
    path = proj / ".claude" / "framework_manifest.json"
    path.write_text(json.dumps({"version": 1, "framework_version": "4.9.0", "files": files},
                               indent=2) + "\n", encoding="utf-8")
    return path


def _manifest_files(proj: Path) -> dict:
    path = proj / ".claude" / "framework_manifest.json"
    return json.loads(path.read_text(encoding="utf-8")).get("files", {})


def _without_version_file(snapshot: dict) -> dict:
    return {k: v for k, v in snapshot.items()
            if k != str(Path(".claude") / "framework_version.json")}


@pytest.mark.parametrize("pinned", [True, False], ids=["mit-pin", "ohne-pin"])
def test_update_adopts_unchanged_manifest_copies(tmp_path, fw_copy, pinned):
    """AC-15: unmarkierte, laut Manifest unveraenderte Framework-Kopien werden uebernommen."""
    mod = _load()
    marker = mod.AGENT_MARKER
    url, _ = _remote(tmp_path)
    pin = {"cloud_ref": "agent-os-openspec--v0.0.1", "cloud_sha": "a" * 40} if pinned else {}
    proj = _plugin_project(tmp_path, name=f"umsteiger-{'pin' if pinned else 'ohne'}", **pin)
    dst_dir = proj / ".claude" / "agents"
    dst_dir.mkdir()
    fw_agents = fw_copy / "core" / "agents"

    # Unveraenderte Copy-Modus-Kopien (Hash == Manifest): alte und aktuelle Fassung
    old_copy = dst_dir / "spec-writer.md"
    old_copy.write_bytes(b"---\nname: spec-writer\nmodel: sonnet\n---\n\nalte Framework-Fassung\n")
    current_copy = dst_dir / "docs-updater.md"
    current_copy.write_bytes((fw_agents / "docs-updater.md").read_bytes())
    # Unmarkiert, lokal geaendert (Hash weicht ab)
    changed = dst_dir / "po-briefer.md"
    changed.write_bytes(b"---\nname: po-briefer\nmodel: opus\n---\n\nlokal angepasst\n")
    # Unmarkiert, ohne Manifest-Eintrag
    unlisted = dst_dir / "test-runner.md"
    unlisted.write_bytes(b"---\nname: test-runner\nmodel: haiku\n---\n\nEigenbau\n")
    changed_bytes, unlisted_bytes = changed.read_bytes(), unlisted.read_bytes()

    _write_manifest(proj, {
        ".claude/agents/spec-writer.md": hashlib.sha256(old_copy.read_bytes()).hexdigest(),
        ".claude/agents/docs-updater.md": hashlib.sha256(current_copy.read_bytes()).hexdigest(),
        ".claude/agents/po-briefer.md": hashlib.sha256(b"Framework-Fassung von damals\n").hexdigest(),
    })

    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out

    # Uebernommen: markierte Kopie, Manifest-Eintrag weg, Meldung
    for name in ("spec-writer", "docs-updater"):
        dst = dst_dir / f"{name}.md"
        src_text = (fw_agents / f"{name}.md").read_text(encoding="utf-8")
        _assert_copy_of(dst.read_text(encoding="utf-8"), src_text, marker, name)
        assert f".claude/agents/{name}.md" not in _manifest_files(proj), \
            f"Manifest-Eintrag fuer {name} nicht entfernt"
        assert [ln for ln in out.splitlines()
                if f"{name}.md" in ln and "bernommen" in ln.lower()], \
            f"Uebernahme von {name} nicht gemeldet:\n{out}"

    # Nicht uebernommen: byte-gleich, "Skipped"
    assert changed.read_bytes() == changed_bytes, "unmarkierte Datei mit abweichendem Hash veraendert"
    assert unlisted.read_bytes() == unlisted_bytes, "unmarkierte Datei ohne Manifest-Eintrag veraendert"
    assert _lines_with(out, "Skipped", "po-briefer"), out
    assert _lines_with(out, "Skipped", "test-runner"), out
    assert _new_files(proj) == [], _new_files(proj)

    # Zweiter Lauf: stabil
    before = _without_version_file(_snapshot(proj))
    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _without_version_file(_snapshot(proj)) == before, "zweiter --update-Lauf hat Dateien geaendert"


# ------------------------------------------------------------------ AC-16
def test_update_without_pin_refreshes_existing_marked_only(tmp_path, fw_copy):
    """AC-16: ohne Pin vorhandene markierte Kopien erneuern, veraltete entfernen, nie anlegen."""
    mod = _load()
    marker = mod.AGENT_MARKER
    url, _ = _remote(tmp_path)
    proj = _plugin_project(tmp_path, name="ohne-pin-markiert")
    dst_dir = proj / ".claude" / "agents"
    dst_dir.mkdir()
    stale = dst_dir / "spec-writer.md"
    stale.write_text(mod.render_agent("---\nname: spec-writer\nmodel: opus\n---\n\nveraltet\n"),
                     encoding="utf-8")
    ghost = dst_dir / "ghost.md"
    ghost.write_text(mod.render_agent("---\nname: ghost\nmodel: haiku\n---\n\nalt\n"),
                     encoding="utf-8")
    own = dst_dir / "po-briefer.md"
    own.write_bytes(b"---\nname: po-briefer\nmodel: opus\n---\n\nEigene Fassung\n")
    own_bytes = own.read_bytes()

    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out

    src_text = (fw_copy / "core" / "agents" / "spec-writer.md").read_text(encoding="utf-8")
    _assert_copy_of(stale.read_text(encoding="utf-8"), src_text, marker, "spec-writer")
    assert not ghost.exists(), "veraltete markierte Kopie ohne Quelle nicht entfernt"
    assert own.read_bytes() == own_bytes, "unmarkierte Datei veraendert"
    assert sorted(p.name for p in dst_dir.iterdir()) == ["po-briefer.md", "spec-writer.md"], \
        "ohne Pin duerfen fehlende Kopien nicht angelegt werden"
    assert _new_files(proj) == [], _new_files(proj)
    fv = json.loads((proj / ".claude" / "framework_version.json").read_text(encoding="utf-8"))
    assert not fv.get("cloud_ref") and not fv.get("cloud_sha"), f"ohne Pin kein Pin setzen: {fv}"

    before = _without_version_file(_snapshot(proj))
    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _without_version_file(_snapshot(proj)) == before, "zweiter --update-Lauf hat Dateien geaendert"


# ------------------------------------------------------------------ Befehlstexte (AC-10..AC-12)
_CALL_RE = re.compile(r"\b(?:Agent|Task)\(")
_TYPE_RE = re.compile(r"""subagent_type\s*=\s*["']([^"']+)["']""")
_MODEL_RE = re.compile(r"""\bmodel\s*=\s*["']([^"']+)["']""")
# Alte Prosa-Starts: `Task (general-purpose/haiku, …)`, `Task 1 (Explore/haiku, …)`,
# `Task (developer-agent/opus, …)`, `Task (implementation-validator, …)`
_PROSE_RE = re.compile(r"\bTask(?:\s+\d+)?\s+\(([\w-]+)(?:/(\w+))?\s*,")


def _command_text(name: str) -> str:
    return (COMMANDS / name).read_text(encoding="utf-8")


def _calls(text: str) -> list:
    """Werkzeug-Aufrufe: (subagent_type, model|None, Kopf) — Kopf reicht bis `prompt=` oder `)`."""
    out = []
    for m in _CALL_RE.finditer(text):
        tail = text[m.end():m.end() + 400]
        cut = len(tail)
        for stop in ("prompt=", ")"):
            idx = tail.find(stop)
            if idx != -1:
                cut = min(cut, idx)
        head = tail[:cut]
        t = _TYPE_RE.search(head)
        if not t:
            continue
        model = _MODEL_RE.search(head)
        out.append((t.group(1), model.group(1) if model else None, head))
    return out


def test_commands_name_agents_in_tool_syntax_without_model():
    agent_names = set(_agent_models())
    problems = []
    for cmd, agents in COMMAND_AGENTS.items():
        text = _command_text(cmd)
        calls = _calls(text)
        for agent in agents:
            assert agent in agent_names, f"{agent} nicht in core/agents"
            named = [c for c in calls if c[0] == agent]
            if not named:
                problems.append(f"{cmd}: kein Aufruf subagent_type=\"{agent}\"")
            for _, model, head in named:
                if model is not None:
                    problems.append(f"{cmd}: {agent} mit model={model!r} ({head.strip()[:80]})")
            if re.search(rf"Du bist der\s+`?{re.escape(agent)}`?\s+Agent", text):
                problems.append(f"{cmd}: Prosa-Form 'Du bist der {agent} Agent' noch vorhanden")
            for p in _PROSE_RE.finditer(text):
                if p.group(1) == agent:
                    problems.append(f"{cmd}: Prosa-Start {p.group(0)!r} fuer {agent}")
    for path in sorted(COMMANDS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for agent in agent_names:
            if re.search(rf"Du bist der\s+`?{re.escape(agent)}`?\s+Agent", text):
                problems.append(f"{path.name}: Prosa-Form 'Du bist der {agent} Agent'")
    assert not problems, "\n".join(problems)


def _fallback_windows(text: str, agent: str) -> list:
    """Textstuecke hinter `agent-os-openspec:<agent>` bis zum naechsten Absatz/Fallback."""
    windows = []
    needle = f"agent-os-openspec:{agent}"
    for m in re.finditer(re.escape(needle) + r"(?![\w-])", text):
        rest = text[m.end():m.end() + 600]
        cut = len(rest)
        for stop in ("\n\n", "agent-os-openspec:"):
            idx = rest.find(stop)
            if idx != -1:
                cut = min(cut, idx)
        windows.append(rest[:cut])
    return windows


def test_fallback_model_matches_agent_frontmatter():
    models = _agent_models()
    problems = []
    for cmd, agents in COMMAND_AGENTS.items():
        text = _command_text(cmd)
        for agent in agents:
            expected = models[agent]
            windows = _fallback_windows(text, agent)
            if not windows:
                problems.append(f"{cmd}: Fallback-Kette fehlt (agent-os-openspec:{agent})")
                continue
            fallbacks = [c for w in windows for c in _calls(w) if c[0] == "general-purpose"]
            if not fallbacks:
                problems.append(f"{cmd}: {agent} ohne general-purpose-Fallback hinter "
                                f"agent-os-openspec:{agent}")
            for _, model, head in fallbacks:
                if model != expected:
                    problems.append(f"{cmd}: Fallback fuer {agent} mit model={model!r}, "
                                    f"Frontmatter sagt {expected!r}")
    assert not problems, "\n".join(problems)


def test_anonymous_agent_starts_carry_explicit_model():
    problems = []
    tool_starts = {}
    for path in sorted(COMMANDS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for p in _PROSE_RE.finditer(text):
            if p.group(1) in ANON_TYPES:
                problems.append(f"{path.name}: Prosa-Start ohne model-Parameter: {p.group(0)!r}")
        for typ, model, head in _calls(text):
            if typ not in ANON_TYPES:
                continue
            tool_starts[path.name] = tool_starts.get(path.name, 0) + 1
            if model not in ("haiku", "sonnet", "opus"):
                problems.append(f"{path.name}: {typ}-Start ohne gueltiges model "
                                f"({head.strip()[:80]})")
    for cmd in ("20-analyse.md", "50-implement.md", "60-validate.md"):
        if not tool_starts.get(cmd):
            problems.append(f"{cmd}: keine anonymen Starts in Werkzeug-Syntax gefunden")
    assert not problems, "\n".join(problems)


# ------------------------------------------------------------------ AC-13
def test_skills_in_sync_and_template_documents_rule():
    text = (REPO_ROOT / "templates" / "agent_orchestration.md").read_text(encoding="utf-8")
    agent_names = set(_agent_models())
    calls = _calls(text)
    named = [c for c in calls if c[0] in agent_names]
    assert named, "Template zeigt keinen benannten Agenten-Typ in Werkzeug-Syntax"
    assert all(model is None for _, model, _ in named), \
        f"benannter Typ im Template mit model: {named}"
    assert re.search(r"agent-os-openspec:[\w-]+", text), \
        "Template nennt die Fallback-Kette agent-os-openspec:<name> nicht"
    assert any(t == "general-purpose" and m in ("haiku", "sonnet", "opus") for t, m, _ in calls)
    assert re.search(r"ohne\s+`?model`?", text), "Regel 'benannter Typ ohne model' fehlt"

    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    # Nicht aus sys.modules entfernen: test_skills_sync.py patcht das geladene Modulobjekt.
    sync_skills = importlib.import_module("sync_skills")
    assert sync_skills.check() == [], "skills/ weicht von core/commands ab"


# ------------------------------------------------------------------ AC-14
def test_changelog_and_claude_md_document_feature():
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # Ab [Unreleased] abwaerts: nach einem Release steht der Eintrag im Versionsabschnitt.
    start = changelog.index("## [Unreleased]")
    assert "#577" in changelog[start:], "CHANGELOG ohne #577-Eintrag"

    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "scripts/sync_cloud_agents.py" in claude_md
    assert ".claude/agents/" in claude_md
