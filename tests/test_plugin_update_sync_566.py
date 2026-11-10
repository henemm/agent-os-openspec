"""Issue #566 — `setup.py <projekt> --update` spiegelt im Plugin-Modus keine Hooks
und Befehle mehr, auch ohne Cloud-Pin.

Echte Dateien in tmp_path, `setup.py` per subprocess; Bausteine aus
tests/test_cache_finder_562.py (Fake-Remote fuer den gepinnten Zweig).
"""
import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))

from test_cache_finder_562 import (  # noqa: E402,F401  (fw_copy ist Fixture)
    ALIASES,
    OWN_CMD,
    OWN_HOOK,
    REAL_COPY,
    TAG,
    _assert_refreshed,
    _consumer,
    _expected_alias,
    _fv,
    _remote,
    _render_shim,
    _setup,
    _snapshot,
    fw_copy,
)

SHIM_FILES = (".claude/hooks/hook_utils.py", ".claude/hooks/config_loader.py")
ALIAS_FILES = tuple(f".claude/commands/{a}.md" for a in ALIASES)


def _names(proj: Path) -> "tuple[list, list]":
    hooks = proj / ".claude" / "hooks"
    cmds = proj / ".claude" / "commands"
    return (sorted(p.name for p in hooks.iterdir() if p.name != "__pycache__"),
            sorted(p.name for p in cmds.iterdir() if p.name != "__pycache__"))


# ------------------------------------------------------------------ AC-1
def test_update_without_pin_creates_no_new_files(tmp_path, fw_copy):
    """AC-1 — GIVEN Plugin-Projekt ohne Pin mit vorhandenen Ordnern
    WHEN `--update` laeuft
    THEN entsteht in .claude/hooks und .claude/commands keine neue Datei."""
    url, _ = _remote(tmp_path)
    proj = _consumer(tmp_path, fw_copy, "consumer", pin=False)
    before = _names(proj)
    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    after = _names(proj)
    assert after == before, f"Dateien neu angelegt: {after} != {before}\n{r.stdout}"


# ------------------------------------------------------------------ AC-2
def test_update_without_pin_refreshes_stale_shims_and_aliases(tmp_path, fw_copy):
    """AC-2 — GIVEN veraltete Shims und markierte veraltete Kurzbefehle ohne Pin
    WHEN `--update` laeuft
    THEN sind sie auf Soll-Inhalt erneuert und ihre Pfade stehen in der Ausgabe."""
    url, _ = _remote(tmp_path)
    proj = _consumer(tmp_path, fw_copy, "consumer", pin=False)
    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    hooks = proj / ".claude" / "hooks"
    for name in ("hook_utils", "config_loader"):
        assert (hooks / f"{name}.py").read_text(encoding="utf-8") == _render_shim(name), \
            f"Shim {name}.py nicht auf Soll-Inhalt erneuert"
    for alias in ALIASES:
        assert (proj / ".claude" / "commands" / f"{alias}.md").read_text(encoding="utf-8") \
            == _expected_alias(fw_copy, alias), f"Kurzbefehl {alias} nicht erneuert"
    for rel in SHIM_FILES + ALIAS_FILES:
        assert f"plugin refresh: {rel}" in r.stdout, \
            f"`plugin refresh: {rel}` fehlt in der Ausgabe:\n{r.stdout}"


# ------------------------------------------------------------------ AC-3
def test_update_without_pin_leaves_real_copies_and_own_files_untouched(tmp_path, fw_copy):
    """AC-3 — GIVEN echte Kopien von hook_utils/config_loader und eigene Dateien ohne Pin
    WHEN `--update` laeuft
    THEN byte-gleich, keine UEBERSCHRIEBEN-Meldung, kein .claude/update-backups/."""
    url, _ = _remote(tmp_path)
    proj = _consumer(tmp_path, fw_copy, "consumer", pin=False, real_copies=True)
    hooks = proj / ".claude" / "hooks"
    cmds = proj / ".claude" / "commands"
    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    for name in ("hook_utils.py", "config_loader.py"):
        assert (hooks / name).read_text(encoding="utf-8") == REAL_COPY, f"{name} veraendert"
    assert (hooks / "own_hook.py").read_text(encoding="utf-8") == OWN_HOOK
    assert (cmds / "my-cmd.md").read_text(encoding="utf-8") == OWN_CMD
    assert "UEBERSCHRIEBEN" not in r.stdout, r.stdout
    assert not (proj / ".claude" / "update-backups").exists(), "Backups angelegt"


# ------------------------------------------------------------------ AC-4
def test_update_without_pin_creates_no_pin_and_keeps_plugin_mode(tmp_path, fw_copy):
    """AC-4 — GIVEN Plugin-Projekt ohne Pin
    WHEN `--update` laeuft
    THEN kein Pin, kein .claude/cloud_bootstrap.py, plugin_mode bleibt true."""
    url, _ = _remote(tmp_path)
    proj = _consumer(tmp_path, fw_copy, "consumer", pin=False)
    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    fv = _fv(proj)
    assert "cloud_ref" not in fv and "cloud_sha" not in fv, fv
    assert fv.get("plugin_mode") is True, fv
    assert not (proj / ".claude" / "cloud_bootstrap.py").exists()


# ------------------------------------------------------------------ AC-5
def test_update_without_pin_is_idempotent(tmp_path, fw_copy):
    """AC-5 — GIVEN Plugin-Projekt ohne Pin nach einem ersten `--update`
    WHEN ein zweiter `--update` laeuft
    THEN aendert sich kein Byte im Projekt; der erste Lauf legte nichts an."""
    url, _ = _remote(tmp_path)
    proj = _consumer(tmp_path, fw_copy, "consumer", pin=False)
    names = _names(proj)
    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _names(proj) == names, "erster Lauf hat Hooks/Befehle angelegt"
    before = {k: v for k, v in _snapshot(proj).items() if "__pycache__" not in k
              and not k.endswith("framework_version.json")}
    r2 = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    after = {k: v for k, v in _snapshot(proj).items() if "__pycache__" not in k
             and not k.endswith("framework_version.json")}
    assert after == before, "zweiter Lauf hat Dateien geaendert"
    assert "plugin refresh:" not in r2.stdout, r2.stdout


# ------------------------------------------------------------------ AC-6
def test_copy_mode_update_still_syncs_hooks_and_commands(tmp_path, fw_copy):
    """AC-6 — GIVEN Copy-Modus-Projekt (plugin_mode fehlt) mit vorhandenen Ordnern
    WHEN `--update` laeuft
    THEN werden Framework-Hooks und -Befehle wie bisher gespiegelt."""
    url, _ = _remote(tmp_path)
    proj = tmp_path / "copymode"
    hooks = proj / ".claude" / "hooks"
    cmds = proj / ".claude" / "commands"
    hooks.mkdir(parents=True)
    cmds.mkdir(parents=True)
    fv = {"framework_version": "0.0.1", "installed": "2026-01-01T00:00:00",
          "installed_modules": []}
    (proj / ".claude" / "framework_version.json").write_text(json.dumps(fv), encoding="utf-8")
    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (hooks / "workflow.py").read_bytes() == \
        (fw_copy / "core" / "hooks" / "workflow.py").read_bytes()
    assert (hooks / "edit_gate.py").is_file()
    assert (cmds / "40-tdd-red.md").is_file()
    assert (cmds / "00-intake.md").is_file()
    assert "plugin refresh:" not in r.stdout
    assert "plugin_mode" not in _fv(proj)


# ------------------------------------------------------------------ AC-7
def test_update_with_pin_behaves_as_in_562(tmp_path, fw_copy):
    """AC-7 — GIVEN Plugin-Projekt mit Pin
    WHEN `--update` laeuft
    THEN wie in #562: erneuert, nichts angelegt, Pin erhalten, Praefix `cloud refresh:`."""
    url, commit = _remote(tmp_path)
    proj = _consumer(tmp_path, fw_copy, "consumer", pin=True)
    names = _names(proj)
    r = _setup(fw_copy, proj, "--update", url=url, tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    _assert_refreshed(proj, fw_copy)
    assert _names(proj) == names, "mit Pin Dateien angelegt"
    fv = _fv(proj)
    assert fv.get("plugin_mode") is True
    assert fv.get("cloud_ref") == TAG and fv.get("cloud_sha") == commit, fv
    for rel in SHIM_FILES + ALIAS_FILES:
        assert f"cloud refresh: {rel}" in r.stdout, r.stdout
    assert "plugin refresh:" not in r.stdout, r.stdout
