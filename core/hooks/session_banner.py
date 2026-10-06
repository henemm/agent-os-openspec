#!/usr/bin/env python3
"""SessionStart-Banner: zeigt, welche Framework-Version wirklich geladen ist.

Ausgabe (stdout, JSON) → `systemMessage`, die Claude Code dem User anzeigt:

    agent-os-openspec 3.23.0 aktiv

Zusaetzlich eine Warnzeile, wenn `setup.py --command-aliases` erzeugte
Befehls-Kopien in `~/.claude/commands` oder `<projekt>/.claude/commands`
veraltet sind. Solche Vollkopien (Skills mit `disable-model-invocation: true`)
aendern sich bei einem Plugin-Update NICHT mit — der User tippt `/name` und
bekommt still die alte Anleitung. Soll-Inhalt und Vergleich kommen aus
`alias_sync.py`, derselben Logik, mit der setup.py die Kopien schreibt.

Zwei Regeln haelt der Banner dabei ein (#163): Kopien mit einem beweisbar
neueren Versions-Marker als die geladene Fassung bleiben unerwaehnt — ein
Neuerzeugen wuerde sie herabstufen. Und der genannte Reparatur-Befehl kommt
immer aus der INSTALLIERTEN Fassung; laesst sie sich nicht aufloesen, nennt
der Banner gar keinen Pfad.

Der genannte Befehl ist immer `--refresh-aliases` (#205), nie `--command-aliases`:
er ueberschreibt nur vorhandene veraltete Kopien und legt nie eine neue Datei an —
sicher auch im globalen Scope `~`, wo `--command-aliases` projekteigene Befehle
ueberschatten wuerde (#87).

Robust by design: jede Exception → still Exit 0. Ein Banner darf den
Session-Start nie blockieren. Bei `framework: {enabled: false}` bzw.
OPENSPEC_FRAMEWORK=off wird nichts ausgegeben.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent


def plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if env:
        return Path(env)
    # core/hooks/session_banner.py → Plugin-Wurzel zwei Ebenen darueber
    return _HOOK_DIR.parent.parent


def plugin_version(root: Path) -> "str | None":
    try:
        data = json.loads((root / ".claude-plugin" / "plugin.json").read_text())
    except Exception:
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) and version else None


def _payload_cwd() -> "str | None":
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return None
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        cwd = data.get("cwd") if isinstance(data, dict) else None
        return cwd if isinstance(cwd, str) and cwd else None
    except Exception:
        return None


def project_dir(payload_cwd: "str | None") -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    return Path(env or payload_cwd or os.getcwd())


def installed_plugin() -> "tuple[Path, str] | None":
    """setup.py-Pfad und Version der INSTALLIERTEN Fassung, sonst None.

    Wirft nie: fehlende oder defekte Registry-Datei ergibt None.

    Quelle ist `~/.claude/plugins/installed_plugins.json`: der Eintrag, dessen
    Schluessel mit `agent-os-openspec@` beginnt, bevorzugt `scope: user`. Die
    Version kommt aus der `plugin.json` dieser Installation, nicht aus dem
    Verzeichnisnamen. Aufloesbar ist sie nur, wenn dort auch wirklich eine
    `setup.py` liegt — sonst waere der Reparatur-Befehl eine Luege.

    Bewusst NICHT `CLAUDE_PLUGIN_ROOT`: das ist die beim Session-Start
    eingefrorene, moeglicherweise aeltere Fassung (#163).
    """
    registry = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    entries = []
    try:
        data = json.loads(registry.read_text())
        for key, value in (data.get("plugins") or {}).items():
            if key.startswith("agent-os-openspec@") and isinstance(value, list):
                entries.extend(e for e in value if isinstance(e, dict))
    except Exception:
        return None
    if not entries:
        return None
    entry = next((e for e in entries if e.get("scope") == "user"), entries[0])
    install_path = entry.get("installPath")
    if not isinstance(install_path, str) or not install_path:
        return None
    root = Path(install_path)
    setup_py = root / "setup.py"
    version = plugin_version(root)
    if not setup_py.is_file() or not version:
        return None
    return setup_py, version


def _repair_hint(label: str, installed: "tuple[Path, str] | None") -> str:
    """Wie der User die Kopien erneuert — oder warum hier kein Befehl steht."""
    if installed is None:
        return ("installierte Plugin-Fassung nicht auffindbar — bitte Kopien "
                "nach dem Plugin-Update von Hand neu erzeugen")
    setup_py, version = installed
    # --refresh-aliases erneuert nur vorhandene, veraltete Kopien und legt nie
    # eine neue Datei an — kann daher nichts ueberschatten (#87), auch nicht
    # im globalen Scope `~` (#205).
    return f"aktualisieren mit {version}: python3 {setup_py} {label} --refresh-aliases"


def _alias_scopes(project: Path) -> "list[tuple[str, Path]]":
    """Scopes (Label, Pfad) fuer Alias-Pruefungen: ~ und, falls verschieden, das Projekt."""
    home = Path.home()
    scopes = [("~", home)]
    try:
        same = project.resolve() == home.resolve()
    except Exception:
        same = False
    if not same:
        scopes.append((str(project), project))
    return scopes


def stale_alias_lines(root: Path, project: Path) -> "list[str]":
    """Eine Warnzeile je Scope (~ bzw. Projekt) mit veralteten Alias-Kopien."""
    from alias_sync import find_stale_aliases

    skills_dir = root / "skills"
    scopes = _alias_scopes(project)

    loaded = plugin_version(root)
    try:
        installed = installed_plugin()
    except Exception:
        installed = None

    lines = []
    for label, scope in scopes:
        try:
            stale = find_stale_aliases(
                skills_dir, scope / ".claude" / "commands", loaded_version=loaded
            )
        except Exception:
            continue
        if stale:
            lines.append(
                f"Veraltete Befehls-Kopien: {', '.join(stale)} "
                f"(Scope {label}) — {_repair_hint(label, installed)}"
            )
    return lines


def removed_alias_lines(project: Path) -> "list[str]":
    """Eine Warnzeile je Scope mit markierten Aliasen entfernter Befehle (#333)."""
    from alias_sync import find_removed_aliases

    try:
        installed = installed_plugin()
    except Exception:
        installed = None

    lines = []
    for label, scope in _alias_scopes(project):
        try:
            found = find_removed_aliases(scope / ".claude" / "commands")
        except Exception:
            continue
        if not found:
            continue
        if installed is None:
            hint = (f"aufraeumen per --refresh-aliases im Scope {label} "
                    "(installierte Plugin-Fassung nicht auffindbar)")
        else:
            hint = f"aufraeumen mit: python3 {installed[0]} {label} --refresh-aliases"
        names = ", ".join(p.stem for p in found)
        lines.append(
            f"{len(found)} Kurz-Alias(e) entfernter Befehle: {names} "
            f"(Scope {label}) — {hint}"
        )
    return lines


_FETCH_TIMEOUT_S = 3


_PLINK_VARIANTS = ("plink", "putty", "tortoiseplink")


def _ssh_program(cmd: str) -> str:
    """Basisname des Programms im ssh-Kommando, klein und ohne .exe.

    Kein POSIX-shlex: der wuerde Backslashes unquotierter Windows-Pfade
    (C:\\...\\ssh.exe) verschlucken (#379).
    """
    cmd = cmd.strip()
    if cmd[:1] in ("'", '"'):
        end = cmd.find(cmd[0], 1)
        prog = cmd[1:end] if end > 0 else cmd[1:]
    else:
        prog = cmd.split()[0] if cmd.split() else ""
    base = prog.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return base[:-4] if base.endswith(".exe") else base


def _core_ssh_command(cwd) -> str:
    """`core.sshCommand` aus der Git-Config oder "" — wirft nie."""
    import subprocess
    if cwd is None:
        return ""
    try:
        r = subprocess.run(["git", "config", "--get", "core.sshCommand"], cwd=str(cwd),
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL, text=True, timeout=1)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _batch_ssh(env: dict, cwd=None) -> None:
    """Eigenes ssh-Kommando des Users behalten, aber nie ohne BatchMode (#371).

    `-oBatchMode=yes` versteht nur OpenSSH. Bei plink/putty brach der Fetch
    sonst ab und die Warnung fiel still weg (#379) — dort bleibt alles, wie es
    ist. Ein gesetztes GIT_SSH ohne GIT_SSH_COMMAND bleibt ebenfalls unberuehrt:
    GIT_SSH_COMMAND hat Vorrang und wuerde den Client des Users ersetzen. Aus
    demselben Grund dient ein konfiguriertes `core.sshCommand` als Basis statt
    eines nackten `ssh`.
    """
    ssh = env.get("GIT_SSH_COMMAND", "").strip()
    if not ssh and env.get("GIT_SSH", "").strip():
        return
    if env.get("GIT_SSH_VARIANT", "").strip().lower() in _PLINK_VARIANTS:
        return
    if not ssh:
        ssh = _core_ssh_command(cwd)
    ssh = ssh or "ssh"
    if "BatchMode" in ssh:
        return
    if _ssh_program(ssh) == "ssh":
        env["GIT_SSH_COMMAND"] = f"{ssh} -oBatchMode=yes"


def _git(args: "list[str]", cwd: Path, timeout: float) -> "str | None":
    """git-Ausgabe oder None (Fehler, Timeout, kein Repo) — wirft nie."""
    import subprocess
    # Kein Dialog beim Session-Start: weder Terminal- noch GUI-Abfrage (VS Code
    # setzt GIT_ASKPASS), weder ssh-askpass noch Git Credential Manager.
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="", SSH_ASKPASS="",
               SSH_ASKPASS_REQUIRE="never", GCM_INTERACTIVE="never")
    try:
        _batch_ssh(env, cwd)
    except Exception:
        pass
    try:
        # Eigene Prozessgruppe: beim Timeout endet die GANZE Kette (remote-http,
        # Credential-Helper, ssh) — nicht nur git selbst (#371).
        proc = subprocess.Popen(["git", *args], cwd=str(cwd), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                text=True, env=env, start_new_session=True)
    except Exception:
        return None
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        return None
    except Exception:
        _kill_group(proc)
        return None
    return out.strip() if proc.returncode == 0 else None


def _kill_group(proc) -> None:
    """Prozessgruppe beenden; wirft nie."""
    import signal
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=1)
    except Exception:
        pass


def behind_lines(cwd: Path) -> "list[str]":
    """Warnzeile, wenn der Haupt-Ordner hinter seinem Upstream liegt (#185).

    Gemessen wird der Zweig, den der HAUPT-Ordner ausgecheckt hat — auch aus
    einer Worktree-Sitzung, ueber die geteilten Refs, ohne Git-Aufruf auf den
    Haupt-Ordner selbst (#169). Ein `git fetch` mit 3 s Timeout holt den
    Remote-Stand; scheitert er (offline, VPN, Zugangsdaten), erscheint keine
    Zeile — lieber nichts als ein veralteter Vergleich. Abschaltbar ueber
    config.yaml → session_banner.behind_check: false.
    """
    try:
        from config_loader import load_config
        if (load_config().get("session_banner") or {}).get("behind_check", True) is False:
            return []
    except Exception:
        pass
    import time
    deadline = time.monotonic() + 4.0  # Hook-Timeout ist 5 s; Banner und Alias-Warnungen gehen vor

    def left(cap: float) -> float:
        return max(0.1, min(cap, deadline - time.monotonic()))

    listing = _git(["worktree", "list", "--porcelain"], cwd, left(1))
    if not listing:
        return []
    main_branch = next((ln.split(" ", 1)[1] for ln in listing.splitlines()
                        if ln.startswith("branch ")), None)  # erster Eintrag = Haupt-Ordner
    first_block = listing.split("\n\n", 1)[0]
    if not main_branch or f"branch {main_branch}" not in first_block:
        return []  # Haupt-Ordner ohne Zweig (detached) — nichts zu vergleichen
    main_branch = main_branch.removeprefix("refs/heads/")  # `<ref>@{u}` will den Kurznamen
    upstream = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{main_branch}@{{u}}"],
                    cwd, left(1))
    remote = _git(["config", f"branch.{main_branch}.remote"], cwd, left(1))  # darf `/` enthalten
    if not upstream or not remote or remote == ".":
        return []
    if time.monotonic() >= deadline or _git(
            ["-c", "maintenance.auto=false", "-c", "gc.auto=0", "fetch", "--quiet",
             "--no-recurse-submodules", remote], cwd, left(_FETCH_TIMEOUT_S)) is None:
        return []
    count = _git(["rev-list", "--count", f"{main_branch}..{upstream}"], cwd, left(1))
    if not count or not count.isdigit() or int(count) == 0:
        return []
    guard = _HOOK_DIR / "session_singleton_guard.py"
    return [f"Haupt-Ordner {count} Commit(s) hinter {upstream} — Bugs nicht gegen veralteten "
            f"Code analysieren. Nachziehen aus einer Sitzung im Haupt-Ordner: "
            f"python3 {guard} sync-main"]


def build_message(root: Path, project: Path, cwd: "Path | None" = None) -> "str | None":
    version = plugin_version(root)
    if not version:
        return None
    lines = [f"agent-os-openspec {version} aktiv"]
    lines.extend(stale_alias_lines(root, project))
    lines.extend(removed_alias_lines(project))
    lines.extend(behind_lines(cwd or project))
    return "\n".join(lines)


def main() -> None:
    sys.path.insert(0, str(_HOOK_DIR))
    from hook_utils import framework_disabled

    payload_cwd = _payload_cwd()
    if framework_disabled():
        return
    message = build_message(plugin_root(), project_dir(payload_cwd),
                            Path(payload_cwd) if payload_cwd else None)
    if message:
        print(json.dumps({"systemMessage": message}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
