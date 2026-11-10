"""Tests fuer Issue #562: Cloud-Cache-Suche fuer Shims, Kurzbefehle und Banner.

Spec: docs/specs/feat-562-cloud-cache-finder.md (AC-1 bis AC-16).

Aufbau (Spec, "Testaufbau"): echte Dateien in tmp_path, echte Subprozesse fuer
Shim, Alias-Einzeiler, Banner und setup.py, kein Mock von Shell oder git. Als
Framework-Quelle dient ein lokales Git-Repo mit annotiertem Tag, erreichbar per
`AGENT_OS_CLOUD_REPO=file://...`; der Pin-Cache liegt per `AGENT_OS_CLOUD_CACHE`
im tmp_path, HOME zeigt auf ein Wegwerf-Verzeichnis (Registry nur, wo der Test
sie anlegt).
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
BOOT_SRC = REPO_ROOT / "core" / "cloud_bootstrap.py"
BANNER = HOOKS_DIR / "session_banner.py"
sys.path.insert(0, str(HOOKS_DIR))
sys.path.insert(0, str(REPO_ROOT))

from alias_sync import alias_content, embeds_full_skill, is_alias_file  # noqa: E402
from migrate_to_plugin import SHIM_MARKER, _is_shim, _render_shim  # noqa: E402

FW_VERSION = "9.9.9"
TAG = f"agent-os-openspec--v{FW_VERSION}"
IMPORT_ERROR = "agent-os-openspec plugin not installed"
NOT_READY = "Cache noch nicht bereit"
SKILL_MARK = "SKILL-AUS-DEM-PIN-CACHE-562"

# Fake-Framework: hook_utils importiert sein Geschwister config_loader (#165).
FW_HOOK_UTILS = (
    "import os\n"
    "import config_loader\n"
    "ORIGIN = os.path.dirname(os.path.abspath(__file__))\n"
)
FW_CONFIG_LOADER = (
    "import os\n"
    "ORIGIN = os.path.dirname(os.path.abspath(__file__))\n"
)
# Projekteigener Hook, wie ihn ein Konsument schreibt.
OWN_HOOK = (
    "import json\n"
    "import hook_utils\n"
    "print(json.dumps({'hu': hook_utils.ORIGIN, 'cl': hook_utils.config_loader.ORIGIN}))\n"
)


# ------------------------------------------------------------------ Umgebung
def _clean_env() -> dict:
    drop = ("CLAUDE_", "GIT_", "AGENT_OS_", "OPENSPEC_", "PYTHON")
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    return env


def _git(args, cwd) -> str:
    r = subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=Test",
                        "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, env=_clean_env())
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


def _make_framework_repo(path: Path, tag: str = TAG) -> str:
    """Fake-Framework-Repo mit annotiertem Tag; liefert die Commit-SHA."""
    hooks = path / "core" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hook_utils.py").write_text(FW_HOOK_UTILS, encoding="utf-8")
    (hooks / "config_loader.py").write_text(FW_CONFIG_LOADER, encoding="utf-8")
    (path / "skills" / "10-context").mkdir(parents=True)
    (path / "skills" / "10-context" / "SKILL.md").write_text(
        f"---\ndescription: x\n---\n\n# {SKILL_MARK}\n", encoding="utf-8")
    (path / ".claude-plugin").mkdir()
    (path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "agent-os-openspec", "version": FW_VERSION}), encoding="utf-8")
    _git(["init", "-q", "-b", "main"], path)
    _git(["add", "-A"], path)
    _git(["commit", "-q", "-m", "release"], path)
    _git(["tag", "-a", tag, "-m", f"release {tag}"], path)
    return _git(["rev-parse", f"{tag}^{{commit}}"], path)


def _write_pin(proj: Path, ref: "str | None", sha: "str | None") -> None:
    data = {"framework_version": None, "plugin_mode": True}
    if ref is not None:
        data["cloud_ref"] = ref
    if sha is not None:
        data["cloud_sha"] = sha
    (proj / ".claude" / ("framework_version" + ".json")).write_text(
        json.dumps(data, indent=2), encoding="utf-8")


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("cloud_bootstrap_562", BOOT_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Ctx:
    """Fake-Framework + Konsumenten-Projekt mit Shims + Cache-Basis."""

    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self.repo = tmp_path / "framework"
        self.sha = _make_framework_repo(self.repo)
        self.url = self.repo.as_uri()
        self.bad_url = (tmp_path / "gibt-es-nicht").as_uri()
        self.proj = tmp_path / "proj mit Leerzeichen"
        self.hooks = self.proj / ".claude" / "hooks"
        self.hooks.mkdir(parents=True)
        self.base = tmp_path / "cache-base"
        self.home = tmp_path / "home"
        self.home.mkdir()
        shutil.copy(BOOT_SRC, self.proj / ".claude" / "cloud_bootstrap.py")
        for name in ("hook_utils", "config_loader"):
            (self.hooks / f"{name}.py").write_text(_render_shim(name), encoding="utf-8")
        (self.hooks / "own_hook.py").write_text(OWN_HOOK, encoding="utf-8")
        _write_pin(self.proj, TAG, self.sha)

    @property
    def cache(self) -> Path:
        return self.base / TAG

    def env(self, url=None, project_env=True, **extra) -> dict:
        env = _clean_env()
        env.update(AGENT_OS_CLOUD_CACHE=str(self.base), AGENT_OS_CLOUD_REPO=url or self.url,
                   HOME=str(self.home), GIT_CEILING_DIRECTORIES=str(self.tmp))
        if project_env:
            env["CLAUDE_PROJECT_DIR"] = str(self.proj)
        env.update(extra)
        return env

    def prefetch(self) -> None:
        """Gueltigen Cache anlegen wie in der Cloud: Baustein `--retry`."""
        r = subprocess.run([sys.executable, str(self.proj / ".claude" / "cloud_bootstrap.py"),
                            "--retry"], cwd=str(self.proj), env=self.env(),
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stdout + r.stderr
        assert self.cache.is_dir()

    def run_hook(self, url=None, project_env=True):
        return subprocess.run([sys.executable, str(self.hooks / "own_hook.py")],
                              cwd=str(self.proj), env=self.env(url, project_env),
                              capture_output=True, text=True, timeout=60)

    def registry(self, install: Path) -> None:
        reg = self.home / ".claude" / "plugins"
        reg.mkdir(parents=True, exist_ok=True)
        (reg / "installed_plugins.json").write_text(json.dumps({
            "version": 2,
            "plugins": {"agent-os-openspec@henemm-private": [
                {"scope": "user", "installPath": str(install), "version": "4.9.0"}]},
        }), encoding="utf-8")


def _origins(r) -> dict:
    assert r.returncode == 0, f"Hook scheiterte:\nstdout={r.stdout}\nstderr={r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def _same(a: str, b: Path) -> bool:
    return os.path.realpath(a) == os.path.realpath(str(b))


def _assert_unchanged_import_error(r) -> None:
    assert r.returncode != 0, f"Import gelang unerwartet: {r.stdout}"
    assert "ImportError" in r.stderr and IMPORT_ERROR in r.stderr, r.stderr
    assert '"hu"' not in r.stdout, r.stdout


# ------------------------------------------------------------------ AC-1
def test_shim_finds_pin_cache_when_registry_missing(tmp_path):
    """AC-1 — GIVEN neuer Shim, gueltiger Pin und Cache, keine Registry
    WHEN ein Hook `import hook_utils` ausfuehrt
    THEN kommt das Modul aus dem Pin-Cache. Der Projektordner ergibt sich aus dem
    Shim-Pfad (ohne CLAUDE_PROJECT_DIR); der Import laesst den Cache gueltig
    (kein `__pycache__`), auch beim zweiten Lauf."""
    ctx = Ctx(tmp_path)
    ctx.prefetch()
    boot = _load_bootstrap()
    for _ in range(2):
        got = _origins(ctx.run_hook(url=ctx.bad_url, project_env=False))
        assert _same(got["hu"], ctx.cache / "core" / "hooks"), got
        assert not list(ctx.cache.rglob("__pycache__")), "Import schrieb Bytecode in den Cache"
        assert boot.cache_valid(ctx.cache, ctx.sha, "hook_utils.py"), \
            "Cache nach dem Import nicht mehr gueltig"


# ------------------------------------------------------------------ AC-2
def test_registry_wins_over_pin_cache(tmp_path):
    """AC-2 — GIVEN Registry auf ein Plugin UND gueltiger Pin-Cache
    WHEN `import hook_utils` laeuft
    THEN stammt das Modul aus dem Plugin der Registry (lokal unveraendert)."""
    ctx = Ctx(tmp_path)
    ctx.prefetch()
    plugin = tmp_path / "plugin-install"
    (plugin / "core" / "hooks").mkdir(parents=True)
    (plugin / "core" / "hooks" / "hook_utils.py").write_text(FW_HOOK_UTILS, encoding="utf-8")
    (plugin / "core" / "hooks" / "config_loader.py").write_text(FW_CONFIG_LOADER,
                                                               encoding="utf-8")
    ctx.registry(plugin)
    got = _origins(ctx.run_hook())
    assert _same(got["hu"], plugin / "core" / "hooks"), got
    assert _same(got["cl"], plugin / "core" / "hooks"), got


# ------------------------------------------------------------------ AC-3
@pytest.mark.parametrize("defect", ["symlink", "wrong_ok", "tampered"])
def test_shim_rejects_invalid_cache_with_unchanged_import_error(tmp_path, defect):
    """AC-3 — GIVEN Pin-Cache als Symlink, mit falscher SHA in `.ok` oder mit
    veraendertem Baum, keine Registry, Abruf nicht moeglich
    WHEN `import hook_utils` laeuft
    THEN bleibt es beim unveraenderten ImportError, nichts aus dem Cache laeuft."""
    ctx = Ctx(tmp_path)
    ctx.prefetch()
    mark = tmp_path / "cache-code-lief.txt"
    if defect == "symlink":
        real = tmp_path / "anderswo"
        shutil.move(str(ctx.cache), str(real))
        os.symlink(str(real), str(ctx.cache))
    elif defect == "wrong_ok":
        (ctx.cache / ".ok").write_text("b" * 40 + "\n", encoding="utf-8")
    else:
        target = ctx.cache / "core" / "hooks" / "hook_utils.py"
        target.write_text(target.read_text(encoding="utf-8")
                          + f"open({str(mark)!r}, 'w').write('x')\n", encoding="utf-8")
    r = ctx.run_hook(url=ctx.bad_url)
    _assert_unchanged_import_error(r)
    assert not mark.exists(), "Code aus dem manipulierten Cache wurde ausgefuehrt"


# ------------------------------------------------------------------ AC-4
def test_sibling_import_works_via_cache(tmp_path):
    """AC-4 — GIVEN Pin-Cache, dessen hook_utils `config_loader` importiert
    WHEN ein projekteigener Hook `import hook_utils` ausfuehrt
    THEN gelingt der Geschwister-Import aus dem Cache (#165), nicht aus dem
    Shim `config_loader.py` des Projekts."""
    ctx = Ctx(tmp_path)
    ctx.prefetch()
    got = _origins(ctx.run_hook(url=ctx.bad_url))
    assert _same(got["hu"], ctx.cache / "core" / "hooks"), got
    assert _same(got["cl"], ctx.cache / "core" / "hooks"), got


# ------------------------------------------------------------------ AC-5
def test_shim_fetches_missing_cache_and_fails_closed_on_fetch_error(tmp_path):
    """AC-5 — GIVEN gueltiger Pin, fehlender Cache, erreichbares Fake-Repo
    WHEN `import hook_utils` laeuft
    THEN holt der Shim den Cache per fetch() und der Import gelingt; bei
    unerreichbarer Quelle oder falscher SHA: unveraenderter ImportError, kein
    (halber) Cache-Ordner."""
    ctx = Ctx(tmp_path)
    assert not ctx.cache.exists()
    got = _origins(ctx.run_hook())
    assert _same(got["hu"], ctx.cache / "core" / "hooks"), got
    assert _load_bootstrap().cache_valid(ctx.cache, ctx.sha, "hook_utils.py")

    for case in ("bad_url", "wrong_sha"):
        sub = Ctx(tmp_path / case)
        if case == "wrong_sha":
            _write_pin(sub.proj, TAG, "c" * 40)
        r = sub.run_hook(url=sub.bad_url if case == "bad_url" else None)
        _assert_unchanged_import_error(r)
        assert not sub.cache.exists(), f"{case}: Cache-Ordner trotz Fehler angelegt"
        leftovers = [p.name for p in sub.base.glob(".tmp-*")] if sub.base.exists() else []
        assert not leftovers, f"{case}: halber Cache-Ordner liegen geblieben: {leftovers}"


# ------------------------------------------------------------------ AC-6
def test_shim_never_uses_current_pointer(tmp_path):
    """AC-6 — GIVEN `<base>/current` zeigt auf einen gueltigen fremden Cache, der
    Pin hat keinen eigenen Cache, Quelle nicht erreichbar, keine Registry
    WHEN `import hook_utils` laeuft
    THEN wird der Zeiger nicht benutzt: unveraenderter ImportError."""
    ctx = Ctx(tmp_path)
    ctx.prefetch()
    foreign = ctx.base / "agent-os-openspec--v8.8.8"
    shutil.move(str(ctx.cache), str(foreign))
    (ctx.base / "current").write_text(str(foreign) + "\n", encoding="utf-8")
    assert _load_bootstrap().cache_valid(foreign, ctx.sha, "hook_utils.py"), \
        "Testaufbau: fremder Cache muss fuer sich gueltig sein"
    _assert_unchanged_import_error(ctx.run_hook(url=ctx.bad_url))


# ------------------------------------------------------------------ Alias-Fallback
ALIAS = "10-context"


def _alias_line(text: str) -> str:
    lines = text.split("\n")
    i = lines.index("```!")
    return lines[i + 1]


def _alias_setup(tmp_path: Path, sha: str = "d" * 40) -> "tuple[Path, Path, Path, str]":
    """Projekt mit Redirect-Alias und Pin, Cache-Basis, Fake-HOME ohne Registry."""
    proj = tmp_path / "konsument"
    (proj / ".claude" / "commands").mkdir(parents=True)
    _write_pin(proj, TAG, sha)
    skill = (REPO_ROOT / "skills" / ALIAS / "SKILL.md").read_text(encoding="utf-8")
    text = alias_content(ALIAS, skill)
    (proj / ".claude" / "commands" / f"{ALIAS}.md").write_text(text, encoding="utf-8")
    base = tmp_path / "cache-base"
    home = tmp_path / "home"
    home.mkdir()
    return proj, base, home, _alias_line(text)


def _make_text_cache(cache: Path, sha: "str | None") -> None:
    (cache / "core" / "hooks").mkdir(parents=True)
    (cache / "skills" / ALIAS).mkdir(parents=True)
    (cache / "skills" / ALIAS / "SKILL.md").write_text(
        f"---\ndescription: x\n---\n\n# {SKILL_MARK}\n", encoding="utf-8")
    if sha is not None:
        (cache / ".ok").write_text(sha + "\n", encoding="utf-8")


def _run_alias(line: str, proj: Path, base: Path, home: Path):
    env = _clean_env()
    env.update(HOME=str(home), CLAUDE_PROJECT_DIR=str(proj), AGENT_OS_CLOUD_CACHE=str(base))
    return subprocess.run(line, shell=True, executable="/bin/bash", cwd=str(proj), env=env,
                          capture_output=True, text=True, timeout=60)


def test_alias_fallback_prints_command_text_from_pin_cache(tmp_path):
    """AC-7 — GIVEN Redirect-Alias, Pin und Cache mit SKILL.md und `.ok` == cloud_sha,
    kein Plugin
    WHEN der Alias-Einzeiler laeuft
    THEN druckt er den Befehlstext samt `export CLAUDE_PLUGIN_ROOT=<cache>`, Exit 0,
    ohne Shell-Operator ausserhalb des Python-Textes."""
    sha = "d" * 40
    proj, base, home, line = _alias_setup(tmp_path, sha)
    cache = base / TAG
    _make_text_cache(cache, sha)

    m = re.fullmatch(r"python3 -c '([^']*)'(.*)", line)
    assert m, f"Einzeiler hat nicht die Form python3 -c '<code>' <args>: {line}"
    rest = m.group(2)
    for op in ("&&", ";", "|"):
        assert op not in rest, f"Shell-Operator {op!r} ausserhalb des Python-Textes: {rest}"

    r = _run_alias(line, proj, base, home)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "BEFEHLSTEXT FEHLT" not in out, out
    assert f"export CLAUDE_PLUGIN_ROOT={cache}" in out.splitlines(), out
    assert SKILL_MARK in out, out


@pytest.mark.parametrize("defect", ["no_ok", "wrong_ok", "skill_symlink", "cache_symlink"])
def test_alias_fallback_rejects_cache_and_reports_not_ready(tmp_path, defect):
    """AC-8 — GIVEN Cache ohne `.ok`, mit fremder SHA oder mit Symlink als SKILL.md
    bzw. Cache-Ordner
    WHEN der Alias-Einzeiler laeuft
    THEN bleibt der Cache ungenutzt: Ausgabe beginnt mit `BEFEHLSTEXT FEHLT`,
    nennt „Cache noch nicht bereit“, Exit 0."""
    sha = "d" * 40
    proj, base, home, line = _alias_setup(tmp_path, sha)
    cache = base / TAG
    if defect == "no_ok":
        _make_text_cache(cache, None)
    elif defect == "wrong_ok":
        _make_text_cache(cache, "e" * 40)
    elif defect == "skill_symlink":
        _make_text_cache(cache, sha)
        real = tmp_path / "fremd.md"
        real.write_text(f"# {SKILL_MARK}\n", encoding="utf-8")
        target = cache / "skills" / ALIAS / "SKILL.md"
        target.unlink()
        os.symlink(str(real), str(target))
    else:
        real = tmp_path / "anderswo"
        _make_text_cache(real, sha)
        base.mkdir(parents=True, exist_ok=True)
        os.symlink(str(real), str(cache))

    r = _run_alias(line, proj, base, home)
    assert r.returncode == 0, r.stderr
    out = r.stdout.lstrip()
    assert out.startswith("BEFEHLSTEXT FEHLT"), out
    assert NOT_READY in out, out
    assert SKILL_MARK not in out, out


# ------------------------------------------------------------------ Banner
def _banner_plugin(tmp_path: Path, version: str = FW_VERSION) -> Path:
    root = tmp_path / "plugin"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "agent-os-openspec", "version": version}), encoding="utf-8")
    return root


def _banner_project(tmp_path: Path, fv: "str | dict | None") -> Path:
    proj = tmp_path / "konsument"
    (proj / ".claude").mkdir(parents=True)
    if fv is not None:
        raw = fv if isinstance(fv, str) else json.dumps(fv)
        (proj / ".claude" / ("framework_version" + ".json")).write_text(raw, encoding="utf-8")
    return proj


def _run_banner(tmp_path: Path, plugin: Path, proj: Path, **extra):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = _clean_env()
    env.update(HOME=str(home), CLAUDE_PLUGIN_ROOT=str(plugin), CLAUDE_PROJECT_DIR=str(proj),
               GIT_CEILING_DIRECTORIES=str(tmp_path))
    env.update(extra)
    r = subprocess.run([sys.executable, str(BANNER)], input="{}", cwd=str(proj), env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip(), f"keine Ausgabe, stderr={r.stderr!r}"
    data = json.loads(r.stdout)
    context = (data.get("hookSpecificOutput") or {}).get("additionalContext") or ""
    return data["systemMessage"], context


def _pin_fv(version: str) -> dict:
    return {"framework_version": None, "plugin_mode": True,
            "cloud_ref": f"agent-os-openspec--v{version}", "cloud_sha": "a" * 40}


def _drift_lines(message: str) -> list:
    return [line for line in message.splitlines() if re.search(r"(?i)cloud", line)]


def test_banner_reports_pin_drift_without_command_for_po(tmp_path):
    """AC-9 — GIVEN Pin aelter als die lokale Plugin-Version, lokale Sitzung
    WHEN der Banner laeuft
    THEN nennt die PO-Ausgabe den veralteten Cloud-Stand ohne Befehl; der Befehl
    `setup.py <projekt> --update` steht nur im additionalContext."""
    plugin = _banner_plugin(tmp_path, "9.9.9")
    proj = _banner_project(tmp_path, _pin_fv("1.0.0"))
    message, context = _run_banner(tmp_path, plugin, proj)
    drift = _drift_lines(message)
    assert drift, f"kein Hinweis zum Cloud-Stand:\n{message}"
    for line in drift:
        for forbidden in ("setup.py", "--update", "python", "`"):
            assert forbidden not in line, f"Befehl in der PO-Zeile: {line}"
    assert "setup.py" in context and "--update" in context, context
    assert str(proj) in context, context


@pytest.mark.parametrize("case", ["no_pin", "cloud", "equal", "newer"])
def test_banner_no_drift_hint_without_pin_in_cloud_or_equal_version(tmp_path, case):
    """AC-10 — GIVEN kein Pin, Cloud-Sitzung, gleiche oder neuere Pin-Version
    WHEN der Banner laeuft
    THEN kein Drift-Hinweis."""
    plugin = _banner_plugin(tmp_path, "9.9.9")
    fv = {"no_pin": {"framework_version": None, "plugin_mode": True},
          "cloud": _pin_fv("1.0.0"), "equal": _pin_fv("9.9.9"),
          "newer": _pin_fv("10.0.0")}[case]
    proj = _banner_project(tmp_path, fv)
    extra = {"CLAUDE_CODE_REMOTE": "true"} if case == "cloud" else {}
    message, context = _run_banner(tmp_path, plugin, proj, **extra)
    assert not _drift_lines(message), message
    assert "--update" not in context, context


@pytest.mark.parametrize("fv", ["{kaputt", {"cloud_ref": "agent-os-openspec--vX", "cloud_sha": "a" * 40},
                                {"cloud_ref": 123, "cloud_sha": "a" * 40}, ["liste"]])
def test_banner_drift_check_is_fail_open(tmp_path, fv):
    """AC-11 — GIVEN kaputte framework_version.json oder unlesbarer cloud_ref
    WHEN der Banner laeuft
    THEN laeuft er ohne Fehler und ohne Drift-Hinweis durch."""
    plugin = _banner_plugin(tmp_path, "9.9.9")
    proj = _banner_project(tmp_path, fv)
    message, context = _run_banner(tmp_path, plugin, proj)
    assert message.startswith("agent-os-openspec 9.9.9"), message
    assert not _drift_lines(message), message
    assert "--update" not in context, context


# ------------------------------------------------------------------ Rollout (setup.py)
_FW_PARTS = ["setup.py", "migrate_to_plugin.py", "config.yaml", ".claude-plugin", "core",
             "hooks", "scripts", "skills", "templates", "modules"]
STALE_SHIM = SHIM_MARKER + "\n# alte Fassung ohne Pin-Cache\n"
OWN_CMD = "# eigener Befehl\n"
REAL_COPY = "# echte lokale Kopie\nX = 1\n"
ALIASES = ("10-context", "40-tdd-red")


@pytest.fixture(scope="module")
def fw_copy(tmp_path_factory) -> Path:
    """Framework-Kopie ohne .git, Version 9.9.9 — Pin-Aufloesung ueber ls-remote."""
    dst = tmp_path_factory.mktemp("fwcopy") / "agent-os-openspec"
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


def _remote(tmp_path) -> "tuple[str, str]":
    repo = tmp_path / "remote"
    return repo.as_uri(), _make_framework_repo(repo)


def _setup(fw: Path, proj: Path, *args, url: str, tmp_path: Path):
    home = tmp_path / "setup-home"
    home.mkdir(exist_ok=True)
    env = _clean_env()
    env.update(AGENT_OS_CLOUD_REPO=url, HOME=str(home), GIT_CEILING_DIRECTORIES=str(fw.parent))
    return subprocess.run([sys.executable, str(fw / "setup.py"), str(proj), *args],
                          cwd=str(fw), env=env, capture_output=True, text=True, timeout=120)


def _expected_alias(fw: Path, name: str) -> str:
    return alias_content(name, (fw / "skills" / name / "SKILL.md").read_text(encoding="utf-8"))


def _stale_alias(fw: Path, name: str) -> str:
    text = _expected_alias(fw, name).replace("Kurz-Alias", "Alter Kurz-Alias", 1)
    assert is_alias_file(text)
    return text


def _consumer(tmp_path: Path, fw: Path, name: str, pin: bool, real_copies: bool = False,
              aliases: bool = True) -> Path:
    proj = tmp_path / name
    hooks = proj / ".claude" / "hooks"
    cmds = proj / ".claude" / "commands"
    hooks.mkdir(parents=True)
    cmds.mkdir(parents=True)
    fv = {"framework_version": None, "version_source": "plugin", "note": "x",
          "installed": "2026-01-01T00:00:00", "installed_modules": [], "plugin_mode": True}
    if pin:
        fv.update(cloud_ref="agent-os-openspec--v0.0.1", cloud_sha="a" * 40)
    (proj / ".claude" / ("framework_version" + ".json")).write_text(json.dumps(fv, indent=2),
                                                                   encoding="utf-8")
    if real_copies:
        (hooks / "hook_utils.py").write_text(REAL_COPY, encoding="utf-8")
        (hooks / "config_loader.py").write_text(REAL_COPY, encoding="utf-8")
    else:
        (hooks / "hook_utils.py").write_text(STALE_SHIM, encoding="utf-8")
        (hooks / "config_loader.py").write_text(STALE_SHIM, encoding="utf-8")
    (hooks / "own_hook.py").write_text(OWN_HOOK, encoding="utf-8")
    (cmds / "my-cmd.md").write_text(OWN_CMD, encoding="utf-8")
    if aliases:
        for alias in ALIASES:
            (cmds / f"{alias}.md").write_text(_stale_alias(fw, alias), encoding="utf-8")
    return proj


def _snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file()}


def _fv(proj: Path) -> dict:
    return json.loads((proj / ".claude" / ("framework_version" + ".json")).read_text(
        encoding="utf-8"))


def _assert_refreshed(proj: Path, fw: Path) -> None:
    hooks = proj / ".claude" / "hooks"
    for name in ("hook_utils", "config_loader"):
        assert (hooks / f"{name}.py").read_text(encoding="utf-8") == _render_shim(name), \
            f"Shim {name}.py nicht erneuert"
    for alias in ALIASES:
        assert (proj / ".claude" / "commands" / f"{alias}.md").read_text(encoding="utf-8") \
            == _expected_alias(fw, alias), f"Kurzbefehl {alias} nicht erneuert"
    assert (hooks / "own_hook.py").read_text(encoding="utf-8") == OWN_HOOK
    assert (proj / ".claude" / "commands" / "my-cmd.md").read_text(encoding="utf-8") == OWN_CMD


def test_cloud_gates_refreshes_stale_shims_and_aliases_idempotently(tmp_path, fw_copy):
    """AC-12 — GIVEN Plugin-Projekt mit Pin, veralteten Shims und Kurzbefehlen
    WHEN `setup.py <projekt> --cloud-gates` laeuft
    THEN sind Shims und Kurzbefehle erneuert, stehen in der Ausgabe, und ein
    zweiter Lauf aendert kein Byte."""
    url, _ = _remote(tmp_path)
    proj = _consumer(tmp_path, fw_copy, "consumer", pin=True)
    r = _setup(fw_copy, proj, "--cloud-gates", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    _assert_refreshed(proj, fw_copy)
    for rel in (".claude/hooks/hook_utils.py", ".claude/hooks/config_loader.py",
                ".claude/commands/10-context.md", ".claude/commands/40-tdd-red.md"):
        assert rel in r.stdout, f"{rel} fehlt in der Ausgabe:\n{r.stdout}"

    before = _snapshot(proj)
    r2 = _setup(fw_copy, proj, "--cloud-gates", url=url, tmp_path=tmp_path)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert _snapshot(proj) == before, "zweiter Lauf hat Dateien geaendert"


def test_update_with_pin_refreshes_shims_and_aliases(tmp_path, fw_copy):
    """AC-13 — GIVEN Plugin-Projekt mit Pin, veralteten Shims und Kurzbefehlen
    WHEN `setup.py <projekt> --update` laeuft
    THEN sind Shims und Kurzbefehle erneuert und der Pin bleibt erhalten."""
    url, commit = _remote(tmp_path)
    proj = _consumer(tmp_path, fw_copy, "consumer", pin=True)
    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    _assert_refreshed(proj, fw_copy)
    fv = _fv(proj)
    assert fv.get("plugin_mode") is True
    assert fv.get("cloud_ref") == TAG and fv.get("cloud_sha") == commit, fv


@pytest.mark.parametrize("mode", ["--cloud-gates", "--update"])
def test_rollout_leaves_real_copies_alone_and_creates_nothing(tmp_path, fw_copy, mode):
    """AC-14 — GIVEN echte Kopien (ohne Shim-Marker), keine Kurzbefehle
    WHEN `--cloud-gates` oder `--update` mit Pin laeuft
    THEN bleiben die Kopien byte-gleich und kein Shim, kein Kurzbefehl entsteht."""
    url, _ = _remote(tmp_path)
    proj = _consumer(tmp_path, fw_copy, "consumer", pin=True, real_copies=True, aliases=False)
    hooks = proj / ".claude" / "hooks"
    cmds = proj / ".claude" / "commands"
    names_before = (sorted(p.name for p in hooks.iterdir()), sorted(p.name for p in cmds.iterdir()))
    r = _setup(fw_copy, proj, mode, url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    for name in ("hook_utils.py", "config_loader.py"):
        assert (hooks / name).read_text(encoding="utf-8") == REAL_COPY, f"{name} veraendert"
    names_after = (sorted(p.name for p in hooks.iterdir() if p.name != "__pycache__"),
                   sorted(p.name for p in cmds.iterdir()))
    assert names_after == names_before, f"Dateien neu angelegt: {names_after} != {names_before}"
    assert not any(_is_shim(p) for p in hooks.iterdir() if p.is_file())
    assert not any(is_alias_file(p.read_text(encoding="utf-8")) for p in cmds.iterdir())


def test_update_without_pin_is_unchanged(tmp_path, fw_copy):
    """AC-15, neu gefasst durch #566 (AC-8) — GIVEN Plugin-Projekt ohne Pin mit
    veralteten Shims und Kurzbefehlen
    WHEN `setup.py <projekt> --update` laeuft
    THEN werden diese erneuert, es wird nichts angelegt, es entsteht kein Pin,
    und die Ausgabe traegt das Praefix `plugin refresh:`."""
    url, _ = _remote(tmp_path)
    proj = _consumer(tmp_path, fw_copy, "consumer", pin=False)
    hooks = proj / ".claude" / "hooks"
    cmds = proj / ".claude" / "commands"
    names_before = (sorted(p.name for p in hooks.iterdir()), sorted(p.name for p in cmds.iterdir()))
    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    _assert_refreshed(proj, fw_copy)
    names_after = (sorted(p.name for p in hooks.iterdir() if p.name != "__pycache__"),
                   sorted(p.name for p in cmds.iterdir()))
    assert names_after == names_before, f"Dateien neu angelegt: {names_after} != {names_before}"
    assert "plugin refresh: .claude/hooks/hook_utils.py" in r.stdout, r.stdout
    assert "cloud refresh:" not in r.stdout, r.stdout
    fv = _fv(proj)
    assert "cloud_ref" not in fv and "cloud_sha" not in fv, fv
    assert not (proj / ".claude" / "cloud_bootstrap.py").exists()


# ------------------------------------------------------------------ AC-16
def test_regenerated_repo_aliases_match_alias_content():
    """AC-16 — GIVEN die Aliase dieses Repos nach der Regenerierung
    WHEN sie mit alias_content() verglichen werden
    THEN sind sie byte-gleich, und jeder Redirect kennt den Pin-Cache (`cloud_ref`)."""
    cmds = sorted((REPO_ROOT / ".claude" / "commands").glob("*.md"))
    assert cmds, "keine Repo-Aliase gefunden"
    for path in cmds:
        text = path.read_text(encoding="utf-8")
        assert is_alias_file(text), path.name
        skill = (REPO_ROOT / "skills" / path.stem / "SKILL.md").read_text(encoding="utf-8")
        assert text == alias_content(path.stem, skill), f"{path.name} weicht ab"
        if not embeds_full_skill(skill):
            assert "cloud_ref" in text, f"{path.name}: Redirect ohne Pin-Cache-Suche"
