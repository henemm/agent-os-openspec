"""Issue #252 (#245, #246): Pfadvergleich gegen extra_allowed_write_dirs.

#245: der rohe Pfad-String bestand die Musterpruefung — `/tmp/../etc/passwd`
passte auf `^/tmp/`. Jetzt zaehlen nur Schreibweisen, die nachweislich dasselbe
Ziel bezeichnen (aufgeloest oder ueber System-Symlinks wie /tmp auf macOS).

#246 (Gross-/Kleinschreibung auf APFS) ist bewusst NICHT normalisiert: der
Fehler blockiert nur, er oeffnet nichts; ein `.lower()` wuerde auf
case-sensitiven Dateisystemen die Grenze aufweichen (Test unten).
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

import secret_egress_guard as seg  # noqa: E402


def _outside(target, root, patterns):
    return seg._is_outside_safe_zone(target, root, {"extra_allowed_write_dirs": patterns})


def test_dotdot_escape_from_allowed_dir_is_blocked(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (tmp_path / "etc").mkdir()
    project = tmp_path / "project"
    project.mkdir()
    pattern = "^" + str(allowed) + "/"
    target = f"{allowed}/../etc/passwd"
    assert _outside(target, project, [pattern]) is True


def test_literal_tmp_dotdot_is_blocked(tmp_path):
    assert _outside("/tmp/../etc/passwd", tmp_path, [r"^/tmp/"]) is True


def test_target_inside_allowed_dir_still_allowed(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    assert _outside(f"{allowed}/sub/x.log", project, ["^" + str(allowed) + "/"]) is False


def test_agent_made_symlink_is_no_master_key(tmp_path):
    """Symlink in einem fuer alle beschreibbaren Ordner (wie /tmp) zaehlt nicht."""
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o1777)
    secret = tmp_path / "secret"
    secret.mkdir()
    (shared / "link").symlink_to(secret)
    project = tmp_path / "project"
    project.mkdir()
    pattern = "^" + str(shared) + "/"
    assert _outside(f"{shared}/link/x.txt", project, [pattern]) is True


def test_system_symlink_alias_allowed(tmp_path, monkeypatch):
    """#239 bleibt: /tmp -> /private/tmp (macOS), Muster in /tmp-Schreibweise."""
    real = tmp_path / "private" / "tmp"
    real.mkdir(parents=True)
    alias = tmp_path / "tmp"
    alias.symlink_to(real)
    monkeypatch.setattr(seg, "_is_system_symlink", lambda p: Path(p) == alias)
    project = tmp_path / "project"
    project.mkdir()
    pattern = "^" + str(alias) + "/"
    assert _outside(f"{alias}/out.log", project, [pattern]) is False
    assert _outside(f"{alias}/../etc/x", project, [pattern]) is True


def test_is_system_symlink_rejects_world_writable_parent(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o1777)
    (shared / "l").symlink_to(tmp_path)
    assert seg._is_system_symlink(shared / "l") is False


def test_case_is_not_folded(tmp_path):
    """#246 bewusst nicht normalisiert: ein anderer Name bleibt ein anderer Ort."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    upper = str(allowed).replace("allowed", "ALLOWED")
    assert _outside(f"{upper}/x.log", project, ["^" + str(allowed) + "/"]) is True


# --- Pruefrunde 1 (F1): Symlink-Kette und root-Agent ---

def test_path_below_agent_symlink_to_root_is_blocked(tmp_path):
    """`<dir>/x -> /` und dann `<dir>/x/etc/...`: lstat von `<dir>/x/etc` landete
    ueber den fremden Link auf einem root-eigenen Ziel."""
    (tmp_path / "x").symlink_to("/")
    project = tmp_path / "project"
    project.mkdir()
    pattern = "^" + str(tmp_path) + "/"
    assert _outside(f"{tmp_path}/x/etc/evil.conf", project, [pattern]) is True
    assert _outside(f"{tmp_path}/x/usr/bin/evil", project, [pattern]) is True
    for top in Path("/").iterdir():  # z.B. /bin -> usr/bin (Linux), /etc -> private/etc (macOS)
        if top.is_symlink():
            assert _outside(f"{tmp_path}/x/{top.name}/evil", project, [pattern]) is True, top


def test_symlink_in_private_dir_is_no_alias_even_for_root(tmp_path):
    """Ein root-Agent legt jeden Symlink root-eigen an — nur `/`-Ebene zaehlt."""
    d = tmp_path / "d"
    d.mkdir()
    d.chmod(0o755)
    (d / "link").symlink_to(tmp_path / "secret")
    (tmp_path / "secret").mkdir()
    project = tmp_path / "project"
    project.mkdir()
    assert seg._is_system_symlink(d / "link") is False
    assert _outside(f"{d}/link/passwd", project, ["^" + str(d) + "/"]) is True


def test_top_level_root_symlink_counts(tmp_path):
    """Die macOS-Form: Symlink direkt unter `/`. Hier: jeder vorhandene Top-Level-Link."""
    import pytest
    links = [p for p in Path("/").iterdir() if p.is_symlink() and p.lstat().st_uid == 0]
    if not links:
        pytest.skip("kein root-eigener Symlink unter / auf diesem System")
    assert seg._is_system_symlink(links[0]) is True


def test_symlink_loop_does_not_open_the_guard(tmp_path):
    """Pruefrunde 2 (vorbestehend): RuntimeError bei Symlink-Schleife (Python 3.11)."""
    (tmp_path / "l1").symlink_to(tmp_path / "l2")
    (tmp_path / "l2").symlink_to(tmp_path / "l1")
    project = tmp_path / "project"
    project.mkdir()
    cfg = {"extra_allowed_write_dirs": [], "redirect_guard_enabled": True}
    hits = seg.find_unsafe_redirects(
        "Bash", {"command": f"echo hi > /etc/rv_evil; echo > {tmp_path}/l1/x"}, cfg, project)
    assert any("/etc/rv_evil" in h for h in hits), hits
