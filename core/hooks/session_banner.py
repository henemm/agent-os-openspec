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

Seit #399 erledigt der Start die ungefaehrliche Wartung selbst, statt dem User
Befehle zu nennen: veraltete Kurzbefehle in `~` werden aufgefrischt, ein
sauberer Haupt-Ordner wird fast-forward nachgezogen. Sichtbar bleibt nur
Klartext ("Kurzbefehle aktualisiert (N)", "Projektstand aktualisiert (N
Änderungen)"). Was der Start nicht beheben darf (Projekt-Kurzbefehle sind
versioniert; Haupt-Ordner mit lokalen Aenderungen), geht nur als
`additionalContext` an Claude. Bei `source == "compact"` keine Wartung.

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


def _read_payload() -> dict:
    """SessionStart-Payload von stdin (einmal gelesen), sonst {} — wirft nie."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _payload_str(payload: dict, key: str) -> "str | None":
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


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


def refresh_home_aliases(root: Path) -> "list[str]":
    """Kurzbefehle in `~` selbst auffrischen (#399); sichtbare Zeile oder nichts.

    Gleiche Regeln wie `setup.py --refresh-aliases`: legt nie an, stuft nie
    herab (#163), fasst nur markierte Dateien an. Fehler → still nichts;
    Uebersprungenes (Symlink, Schreibschutz) wird mitgezaehlt (#400).
    """
    skipped: list = []
    try:
        from alias_sync import refresh_aliases
        refreshed, removed = refresh_aliases(
            root / "skills", Path.home() / ".claude" / "commands", plugin_version(root),
            skipped=skipped,
        )
    except Exception:
        return []
    count = len(refreshed) + len(removed)
    if count and skipped:
        return [f"Kurzbefehle aktualisiert ({count}) · {len(skipped)} übersprungen"]
    if count:
        return [f"Kurzbefehle aktualisiert ({count})"]
    if skipped:
        return [f"Kurzbefehle: {len(skipped)} übersprungen"]
    return []


def project_alias_context(root: Path, project: Path) -> "list[str]":
    """Hinweise an Claude zu veralteten Kurzbefehlen im Projekt-Scope (#399).

    Das Projekt-Scope ist versioniert — der Start schreibt dort nie; ein
    Schreiben wuerde den Haupt-Ordner aendern und das Nachziehen blockieren.
    """
    from alias_sync import find_removed_aliases, find_stale_aliases

    try:
        installed = installed_plugin()
    except Exception:
        installed = None
    lines = []
    for label, scope in _alias_scopes(project)[1:]:
        commands = scope / ".claude" / "commands"
        try:
            stale = find_stale_aliases(root / "skills", commands,
                                       loaded_version=plugin_version(root))
            removed = [p.stem for p in find_removed_aliases(commands)]
        except Exception:
            continue
        hint = _repair_hint(label, installed)
        if stale:
            lines.append(f"Veraltete Kurzbefehl-Kopien im Projekt: {', '.join(stale)} "
                         f"(Scope {label}) — {hint}")
        if removed:
            if installed is None:
                hint = (f"aufraeumen per --refresh-aliases im Scope {label} "
                        "(installierte Plugin-Fassung nicht auffindbar)")
            lines.append(f"Kurz-Alias(e) entfernter Befehle im Projekt: {', '.join(removed)} "
                         f"(Scope {label}) — {hint}")
    if lines:
        lines.append("Diese Dateien sind versioniert und wurden beim Start nicht geaendert: "
                     "im Arbeitsordner mit --refresh-aliases auffrischen und mit der "
                     "naechsten Aenderung mitliefern.")
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


def _core_ssh_command(cwd, timeout: float = 1) -> str:
    """`core.sshCommand` aus der Git-Config oder "" — wirft nie."""
    import subprocess
    if cwd is None:
        return ""
    try:
        r = subprocess.run(["git", "config", "--get", "core.sshCommand"], cwd=str(cwd),
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _batch_ssh(env: dict, cwd=None, timeout: float = 1) -> None:
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
        ssh = _core_ssh_command(cwd, timeout)
    ssh = ssh or "ssh"
    if "BatchMode" in ssh:
        return
    if _ssh_program(ssh) == "ssh":
        env["GIT_SSH_COMMAND"] = f"{ssh} -oBatchMode=yes"


def _monotonic() -> float:
    import time
    return time.monotonic()


def _git_env() -> dict:
    # Kein Dialog beim Session-Start: weder Terminal- noch GUI-Abfrage (VS Code
    # setzt GIT_ASKPASS), weder ssh-askpass noch Git Credential Manager.
    return dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="", SSH_ASKPASS="",
                SSH_ASKPASS_REQUIRE="never", GCM_INTERACTIVE="never")


def _git(args: "list[str]", cwd: Path, timeout: float) -> "str | None":
    """git-Ausgabe oder None (Fehler, Timeout, kein Repo) — wirft nie."""
    import subprocess
    env = _git_env()
    if "fetch" in args:
        # Nur der Fetch nutzt ssh. Das Config-Lesen zaehlt zum Timeout des
        # Aufrufs, damit ein haengendes `git config` das Budget nicht sprengt (#382).
        start = _monotonic()
        try:
            _batch_ssh(env, cwd, min(1.0, timeout))
        except Exception:
            pass
        timeout = max(0.1, timeout - (_monotonic() - start))
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


_TOTAL_BUDGET_S = 8.0  # Hook-Timeout ist 10 s (#399); Rest fuer Start und Ausgabe
_MERGE_TIMEOUT_S = 4.0
_MIN_MERGE_S = 0.5


def _term_group(proc) -> None:
    """Prozessgruppe mit SIGTERM beenden, nie SIGKILL — git raeumt dann seine
    `index.lock` selbst weg (#399). Wirft nie."""
    import signal
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=1)
    except Exception:
        pass


def _ff_merge(folder: Path, upstream: str, timeout: float) -> bool:
    """`git merge --ff-only` mit eigenem Zeitbudget; True bei Erfolg — wirft nie."""
    import subprocess
    try:
        proc = subprocess.Popen(
            ["git", "-c", "maintenance.auto=false", "-c", "gc.auto=0",
             "merge", "--ff-only", "--quiet", upstream],
            cwd=str(folder), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, env=_git_env(), start_new_session=True)
    except Exception:
        return False
    try:
        proc.wait(timeout=timeout)
    except Exception:
        _term_group(proc)
        return False
    return proc.returncode == 0


def _behind_check_enabled() -> bool:
    try:
        from config_loader import load_config
        return (load_config().get("session_banner") or {}).get("behind_check", True) is not False
    except Exception:
        return True


def _main_checkout(cwd: Path, left) -> "tuple[Path, str] | None":
    """(Haupt-Ordner, Zweig-Kurzname) — nur wenn cwd der Haupt-Ordner ist.

    Erster Eintrag von `git worktree list` = Haupt-Ordner. Aus einem Worktree
    heraus wird nichts gemessen und nichts gemeldet (#399): Worktrees verzweigen
    vom Remote-Stand, ein veralteter Haupt-Ordner schadet dort nicht.
    """
    listing = _git(["worktree", "list", "--porcelain"], cwd, left(1))
    if not listing:
        return None
    first = listing.split("\n\n", 1)[0].splitlines()
    path = next((ln.split(" ", 1)[1] for ln in first if ln.startswith("worktree ")), None)
    branch = next((ln.split(" ", 1)[1] for ln in first if ln.startswith("branch ")), None)
    if not path or not branch:
        return None  # Haupt-Ordner ohne Zweig (detached) — nichts zu vergleichen
    try:
        if Path(path).resolve() != Path(cwd).resolve():
            return None
    except Exception:
        return None
    return Path(path), branch.removeprefix("refs/heads/")  # `<ref>@{u}` will den Kurznamen


def _blocker(folder: Path, upstream: str, left) -> "str | None":
    """Grund, warum nicht nachgezogen werden darf (Regeln wie `sync-main`), sonst None."""
    for name in ("MERGE_HEAD", "rebase-merge", "rebase-apply"):
        marker = _git(["rev-parse", "--git-path", name], folder, left(1))
        if marker is None:
            return "Git-Zustand nicht lesbar"
        if (folder / marker).exists():
            return f"laufender Merge/Rebase ({name})"
    status = _git(["status", "--porcelain", "--untracked-files=no"], folder, left(2))
    if status is None:
        return "git status fehlgeschlagen"
    if status:
        return "lokale Aenderungen an versionierten Dateien"
    if _git(["merge-base", "--is-ancestor", "HEAD", upstream], folder, left(1)) is None:
        return "lokale Commits, die im Upstream fehlen (Historie abgewichen)"
    return None


def _stale_main_context(folder: Path, upstream: str, count: int, reason: str) -> str:
    guard = _HOOK_DIR / "session_singleton_guard.py"
    return (f"Der Haupt-Ordner {folder} liegt {count} Commit(s) hinter {upstream} und wurde "
            f"beim Start NICHT nachgezogen. Grund: {reason}. Auftrag an Claude: Erklaere dem "
            "PO in Klartext ohne Git-Vokabular, dass der Projektstand im Haupt-Ordner veraltet "
            "ist und warum; analysiere Fehler nicht gegen diesen veralteten Stand. Nach "
            f"Behebung des Grundes nachziehen aus einer Sitzung im Haupt-Ordner: "
            f"python3 {guard} sync-main")


def _pull_forward(folder: Path, upstream: str, count: int, deadline: float,
                  left) -> "tuple[list[str], list[str]]":
    """Haupt-Ordner fast-forward nachziehen oder Claude den Grund nennen."""
    reason = _blocker(folder, upstream, left)
    if reason is None:
        budget = deadline - _monotonic()
        if budget < _MIN_MERGE_S:
            reason = "Zeitbudget beim Start erschoepft"
        elif not _ff_merge(folder, upstream, min(_MERGE_TIMEOUT_S, budget)):
            reason = "git merge --ff-only fehlgeschlagen oder Zeitueberschreitung"
    if reason is None:
        return [f"Projektstand aktualisiert ({count} Änderungen)"], []
    return [], [_stale_main_context(folder, upstream, count, reason)]


def main_folder_sync(cwd: Path) -> "tuple[list[str], list[str]]":
    """(sichtbare Zeilen, Hinweise an Claude) zum Haupt-Ordner (#185, #399).

    Nur wenn cwd der Haupt-Ordner ist. Ein `git fetch` mit 3 s Timeout holt den
    Remote-Stand; scheitert er (offline, VPN, Zugangsdaten), gibt es keine
    Meldung — lieber nichts als ein veralteter Vergleich. Liegt der Haupt-Ordner
    zurueck, wird er fast-forward nachgezogen, sofern die Regeln von `sync-main`
    es erlauben. Abschaltbar ueber config.yaml → session_banner.behind_check: false.
    """
    if not _behind_check_enabled():
        return [], []
    deadline = _monotonic() + _TOTAL_BUDGET_S

    def left(cap: float) -> float:
        return max(0.1, min(cap, deadline - _monotonic()))

    checkout = _main_checkout(cwd, left)
    if checkout is None:
        return [], []
    folder, branch = checkout
    upstream = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{branch}@{{u}}"],
                    folder, left(1))
    remote = _git(["config", f"branch.{branch}.remote"], folder, left(1))  # darf `/` enthalten
    if not upstream or not remote or remote == ".":
        return [], []
    if _monotonic() >= deadline or _git(
            ["-c", "maintenance.auto=false", "-c", "gc.auto=0", "fetch", "--quiet",
             "--no-recurse-submodules", remote], folder, left(_FETCH_TIMEOUT_S)) is None:
        return [], []
    count = _git(["rev-list", "--count", f"{branch}..{upstream}"], folder, left(1))
    if not count or not count.isdigit() or int(count) == 0:
        return [], []
    return _pull_forward(folder, upstream, int(count), deadline, left)


def behind_lines(cwd: Path) -> "list[str]":
    """Sichtbare Zeilen zum Haupt-Ordner (Kompatibilitaet; siehe main_folder_sync)."""
    return main_folder_sync(cwd)[0]


def build_output(root: Path, project: Path, cwd: "Path | None" = None,
                 source: "str | None" = None) -> "dict | None":
    """Hook-Ausgabe: sichtbare `systemMessage`, optional `additionalContext` fuer Claude."""
    version = plugin_version(root)
    if not version:
        return None
    lines = [f"agent-os-openspec {version} aktiv"]
    context: "list[str]" = []
    if source != "compact":  # nach Kontext-Kompaktierung keine Wartung (#399)
        lines.extend(refresh_home_aliases(root))
        try:
            context.extend(project_alias_context(root, project))
        except Exception:
            pass
        try:
            visible, hints = main_folder_sync(cwd or project)
        except Exception:
            visible, hints = [], []
        lines.extend(visible)
        context.extend(hints)
    output: dict = {"systemMessage": "\n".join(lines)}
    if context:
        output["hookSpecificOutput"] = {"hookEventName": "SessionStart",
                                        "additionalContext": "\n".join(context)}
    return output


def main() -> None:
    sys.path.insert(0, str(_HOOK_DIR))
    from hook_utils import framework_disabled

    payload = _read_payload()
    payload_cwd = _payload_str(payload, "cwd")
    if framework_disabled():
        return
    output = build_output(plugin_root(), project_dir(payload_cwd),
                          Path(payload_cwd) if payload_cwd else None,
                          _payload_str(payload, "source"))
    if output:
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
