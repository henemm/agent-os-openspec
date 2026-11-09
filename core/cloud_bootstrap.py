#!/usr/bin/env python3
"""Cloud-Startbaustein fuer Plugin-Konsumenten (#522).

Claude Code on the web laedt keine Plugins. `setup.py <projekt> --cloud-gates`
kopiert diese Datei deshalb nach `<projekt>/.claude/cloud_bootstrap.py` und
traegt jeden Hook aus `hooks/hooks.json` so in `.claude/settings.json` ein:

    [ "$CLAUDE_CODE_REMOTE" != "true" ] || \\
        python3 -I "${CLAUDE_PROJECT_DIR}/.claude/cloud_bootstrap.py" <datei>.py [args]

`-I` haelt `.claude/` und PYTHONPATH aus `sys.path`: sonst ersetzte etwa eine Datei
`.claude/json.py` ein Stdlib-Modul und liefe vor jeder Cache-Pruefung (Adversary F008).
Fuer Alt-Eintraege ohne `-I` entfernt der Baustein ganz oben selbst Skriptverzeichnis,
`''` und `'.'` aus `sys.path`, bevor er etwas anderes importiert.

Ablauf je Hook-Aufruf (stdin = Hook-JSON):
1. Pin `cloud_ref` (Release-Tag) + `cloud_sha` (Commit) aus
   `.claude/framework_version.json` lesen.
2. Cache `<base>/<cloud_ref>` (`<base>` = ~/.cache/agent-os-openspec) nutzen, wenn
   er unversehrt ist (keine Symlinks, HEAD == Pin, Arbeitsbaum sauber); sonst den
   Tag unter Datei-Sperre klonen, Commit pruefen, atomar umbenennen.
3. Hook-Skript aus dem Cache mit `CLAUDE_PLUGIN_ROOT=<cache>` und unveraendertem
   stdin starten; dessen Exit-Code ist der Exit-Code dieses Bausteins.

Scheitert das, sind nur noch lesende Werkzeuge erlaubt (fail-closed); der PO
kann per `override` die Sitzung 1 h freigeben. CLI: `--retry` holt neu.

Nur Standardbibliothek, Python >= 3.8.
"""

# Bewusst KEIN `from __future__ import annotations`: auch das ist ein Laufzeit-Import
# und kaeme vor der Bereinigung von sys.path. Annotationen deshalb als Strings, wo
# sie auf Python 3.8 nicht auswertbar waeren.
import sys  # builtin, wird nie ueber sys.path geladen


def _strip_script_dir() -> None:
    """Skriptverzeichnis, `''` und `'.'` aus sys.path entfernen (Adversary F008).

    Schutz fuer Alt-Eintraege ohne `-I`. Ohne `-I`/`-P` setzt Python das
    Skriptverzeichnis an sys.path[0]; das faellt zuerst weg, damit schon `import os`
    nicht aus `.claude/` geladen werden kann. Danach per realpath-Vergleich jede
    weitere Schreibweise desselben Ordners (etwa ueber PYTHONPATH).
    """
    isolated = sys.flags.isolated or getattr(sys.flags, "safe_path", False)
    if not isolated and sys.path:
        del sys.path[0]
    sys.path[:] = [p for p in sys.path if p not in ("", ".")]
    import os.path as osp  # sys.path ist hier schon ohne Skriptverzeichnis

    here = set()
    for name in (globals().get("__file__"), sys.argv[0] if sys.argv else ""):
        if name:
            here.add(osp.realpath(osp.dirname(osp.abspath(name))))
    sys.path[:] = [p for p in sys.path if osp.realpath(p) not in here]


if __name__ == "__main__":  # nur als Skript; ein importierender Aufrufer behaelt sein sys.path
    _strip_script_dir()

# Imports erst nach der Bereinigung von sys.path (daher nach Code, Adversary F008).
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shlex  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

try:
    import fcntl
except ImportError:  # pragma: no cover - nur Nicht-POSIX
    fcntl = None

DEFAULT_REPO = "https://github.com/henemm/agent-os-openspec"
RETRY_CMD = "python3 .claude/cloud_bootstrap.py --retry"
REF_RE = re.compile(r"^agent-os-openspec--v[0-9]+\.[0-9]+\.[0-9]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SCRIPT_RE = re.compile(r"^[A-Za-z0-9_]+\.py$")
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]+$")
CLONE_TIMEOUT = 20
OVERRIDE_TTL = 3600

READ_TOOLS = {"Read", "Grep", "Glob", "LS", "TodoWrite", "AskUserQuestion", "ToolSearch"}
# Ohne `rg`: `--pre`/`--hostname-bin` starten Programme (Adversary F001).
READ_COMMANDS = {"ls", "cat", "head", "tail", "grep", "pwd"}
GIT_READ = {"status", "diff", "log", "show"}
# git-Optionen, die schreiben (`--output`) oder Programme starten (externer Diff,
# textconv-Filter, gpg fuer Signaturen).
GIT_FORBIDDEN_OPTS = ("--output", "--ext-diff", "--textconv", "--show-signature")
# Strenger als die Mindestliste der Spec: einzelnes `&`, `<` (Prozess-Substitution)
# und Zeilenumbruch trennen bzw. starten ebenfalls Befehle.
BASH_FORBIDDEN = (">", "<", "|", ";", "&", "`", "$(", "\n", "\r")

PO_EXIT = "PO: `override` tippen (gilt 1 h für diese Sitzung)"


class FetchError(Exception):
    """Abruf/Pruefung des gepinnten Framework-Stands gescheitert (Text = Grund)."""


# ------------------------------------------------------------------ Orte
def project_dir() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent


def cache_base() -> Path:
    env = os.environ.get("AGENT_OS_CLOUD_CACHE")
    return Path(env) if env else Path.home() / ".cache" / "agent-os-openspec"


def read_pin() -> "tuple[str, str]":
    path = project_dir() / ".claude" / "framework_version.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FetchError(f"Pin nicht lesbar ({path.name}: {exc})")
    ref = data.get("cloud_ref") if isinstance(data, dict) else None
    sha = data.get("cloud_sha") if isinstance(data, dict) else None
    if not isinstance(ref, str) or not REF_RE.match(ref):
        raise FetchError("kein gültiger Pin `cloud_ref` in .claude/framework_version.json "
                         "(setup.py <projekt> --cloud-gates ausführen)")
    if not isinstance(sha, str) or not SHA_RE.match(sha):
        raise FetchError("kein gültiger Pin `cloud_sha` in .claude/framework_version.json")
    return ref, sha


def _git_check(cache: Path, args: list) -> "bytes | None":
    """Nur lesendes git im Cache (`rev-parse`, `ls-tree`): ohne System-/globale Config,
    Replace-Objekte, System-Attribute und fsmonitor. Nie `status` o. ae., weil das
    Filter, Attribute und fsmonitor der Cache-Config auswertet (Adversary F007)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_NO_REPLACE_OBJECTS="1", GIT_CONFIG_NOSYSTEM="1", GIT_ATTR_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    cmd = ["git", "--no-optional-locks", "--git-dir", str(cache / ".git"),
           "-c", "core.fsmonitor=false", *args]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _blob_sha(data: bytes) -> str:
    """Git-Blob-Hash wie `git hash-object --no-filters` (ohne Filter/Attribute)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _tree_matches(cache: Path, expected: dict, rel: bytes = b"") -> bool:
    """Arbeitsbaum unter `rel` == `expected` ({pfad: (mode, sha)}): kein fremder,
    fehlender oder geaenderter Eintrag, Symlinks nur wo der Commit welche hat."""
    try:
        entries = list(os.scandir(os.path.join(bytes(cache), rel) if rel else bytes(cache)))
    except OSError:
        return False
    for entry in entries:
        path = rel + b"/" + entry.name if rel else entry.name
        if not rel and entry.name in (b".git", b".ok"):
            continue
        want = expected.pop(path, None)
        try:
            if entry.is_symlink():
                if want is None or want[0] != b"120000":
                    return False
                if _blob_sha(os.readlink(entry.path)) != want[1]:
                    return False
            elif entry.is_dir(follow_symlinks=False):
                if want is not None and want[0] != b"dir":
                    if want[0] != b"160000" or os.listdir(entry.path):
                        return False
                    continue
                if want is None or not _tree_matches(cache, expected, path):
                    return False
            elif entry.is_file(follow_symlinks=False):
                if want is None or want[0] not in (b"100644", b"100755"):
                    return False
                with open(entry.path, "rb") as fh:
                    if _blob_sha(fh.read()) != want[1]:
                        return False
            else:
                return False  # FIFO, Socket, Geraetedatei
        except OSError:
            return False
    return True


def cache_valid(cache: Path, sha: str, script: str = "") -> bool:
    """Cache nur gueltig, wenn `.ok`, HEAD und Arbeitsbaum zum Pin passen (Adversary F003/F007).

    Keine Symlinks auf dem Weg zum Skript; HEAD == Pin; der ganze Arbeitsbaum (ausser
    `.git/` und `.ok`) gleicht Datei fuer Datei dem Commit `sha` laut `git ls-tree`,
    verglichen per selbst berechnetem Blob-Hash (keine Filter, Attribute, Index, fsmonitor).
    """
    parts = [cache, cache / ".git", cache / "core", cache / "core" / "hooks"]
    if any(os.path.islink(p) or not p.is_dir() for p in parts):
        return False
    if script and os.path.islink(cache / "core" / "hooks" / script):
        return False
    try:
        if (cache / ".ok").read_text(encoding="utf-8").strip() != sha:
            return False
    except OSError:
        return False
    head = _git_check(cache, ["rev-parse", "--verify", "--quiet", "HEAD^{commit}"])
    if head is None or head.strip() != sha.encode("ascii"):
        return False
    listing = _git_check(cache, ["ls-tree", "-r", "-t", "-z", "--full-tree", sha])
    if not listing:
        return False
    expected = {}
    for record in listing.split(b"\0"):
        if not record:
            continue
        meta, _, path = record.partition(b"\t")
        fields = meta.split(b" ")
        if len(fields) != 3 or not path:
            return False
        mode, kind, obj = fields
        expected[path] = (b"dir", b"") if kind == b"tree" else (mode, obj.decode("ascii"))
    return _tree_matches(cache, expected) and not expected


# ------------------------------------------------------------------ Abruf
def _git(args: list, timeout: int = CLONE_TIMEOUT) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              timeout=timeout, env=env)
    except FileNotFoundError:
        raise FetchError("git nicht gefunden")
    except subprocess.TimeoutExpired:
        raise FetchError(f"Abruf dauerte länger als {timeout} s (Netz?)")


def _clone(ref: str, sha: str, tmp: Path) -> None:
    url = os.environ.get("AGENT_OS_CLOUD_REPO") or DEFAULT_REPO
    r = _git(["clone", "--quiet", "--depth", "1", "--branch", ref, "--", url, str(tmp)])
    if r.returncode != 0:
        detail = (r.stderr.strip().splitlines() or ["unbekannter Fehler"])[-1]
        raise FetchError(f"Tag {ref} nicht abrufbar von {url}: {detail}")
    head = _git(["-C", str(tmp), "rev-parse", "HEAD"]).stdout.strip()
    if head != sha:
        raise FetchError(f"SHA weicht ab: Tag {ref} zeigt auf {head or '?'}, "
                         f"gepinnt ist {sha}")
    (tmp / ".ok").write_text(sha + "\n", encoding="utf-8")


def _write_pointer(base: Path, cache: Path) -> None:
    tmp = base / f".current.{os.getpid()}"
    tmp.write_text(str(cache) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(base / "current"))


def fetch(ref: str, sha: str, force: bool = False, script: str = "") -> Path:
    """Cache fuer den Pin sicherstellen (unter Sperre, atomar); liefert den Cache-Pfad.

    Ein ungueltiger oder manipulierter Cache wird verworfen und neu geholt."""
    base = cache_base()
    cache = base / ref
    if not force and cache_valid(cache, sha, script):
        return cache
    base.mkdir(parents=True, exist_ok=True)
    with open(base / ".lock", "a+") as lock:
        if fcntl is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if not force and cache_valid(cache, sha, script):
            return cache
        tmp = base / f".tmp-{ref}-{os.getpid()}"
        shutil.rmtree(str(tmp), ignore_errors=True)
        try:
            if os.path.islink(cache):
                os.unlink(str(cache))
            elif force or os.path.lexists(cache):
                shutil.rmtree(str(cache), ignore_errors=True)
            _clone(ref, sha, tmp)
            os.rename(str(tmp), str(cache))
            _write_pointer(base, cache)
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    return cache


def resolve_script(cache: Path, script: str) -> Path:
    if not SCRIPT_RE.match(script or ""):
        raise FetchError(f"ungültiger Skriptname {script!r}")
    path = cache / "core" / "hooks" / script
    if os.path.islink(path) or not path.is_file():
        raise FetchError(f"Hook-Skript {script} fehlt im Framework-Stand {cache.name}")
    return path


def forward(cache: Path, script: Path, args: list, raw: bytes) -> int:
    # `-E -s`: kein PYTHONPATH/PYTHONSTARTUP o. ae. und keine User-site (Adversary F008).
    # Nicht `-I`: die Hooks importieren Geschwister aus ihrem Skriptverzeichnis core/hooks.
    # `-B` statt PYTHONDONTWRITEBYTECODE (das `-E` ignoriert): `__pycache__` im Cache
    # hiesse fuer cache_valid "manipuliert".
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(cache), PYTHONDONTWRITEBYTECODE="1")
    sys.stdout.flush()
    sys.stderr.flush()
    cmd = [sys.executable, "-E", "-s", "-B", str(script), *args]
    rc = subprocess.run(cmd, input=raw, env=env).returncode
    return rc if rc >= 0 else 1


# ------------------------------------------------------------------ PO-Ausnahme
def _override_path(session: str) -> "Path | None":
    if not isinstance(session, str) or not SESSION_RE.match(session):
        return None
    return cache_base() / f"override-{session}.json"


def override_active(session: str) -> bool:
    path = _override_path(session)
    if path is None:
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        created = float(data["created"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
    age = time.time() - created
    return data.get("session_id") == session and -60 <= age < OVERRIDE_TTL


def _log_event(session: str) -> None:
    path = project_dir() / ".claude" / "gate-events.jsonl"
    event = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "hook": "cloud_bootstrap", "tool": "UserPromptSubmit",
             "reason": "override: gates not loaded", "command_excerpt": "",
             "session_id": session}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass


def set_override(data: dict) -> None:
    """Echter UserPromptSubmit mit genau `override`: Ausnahme fuer diese Sitzung."""
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or prompt.strip().lower() != "override":
        return
    session = data.get("session_id")
    path = _override_path(session)
    if path is None:
        return
    now = time.time()
    record = {"session_id": session, "created": now,
              "created_iso": datetime.fromtimestamp(now, timezone.utc).isoformat()}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record), encoding="utf-8")
    except OSError as exc:
        print(f"Ausnahme nicht gesetzt: {exc}")
        return
    _log_event(session)
    print("Ausnahme gesetzt: Gates nicht geladen, schreibende Werkzeuge 1 h freigegeben, "
          f"Abhilfe: `{RETRY_CMD}`")


# ------------------------------------------------------------------ Fehlschlag
def bash_allowed(command: str) -> bool:
    """Retry-Aufruf oder ein einzelner Lese-Befehl ohne Verkettung/Umleitung."""
    if not isinstance(command, str):
        return False
    if command.strip() == RETRY_CMD:
        return True
    if any(tok in command for tok in BASH_FORBIDDEN):
        return False
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    if not words:
        return False
    if words[0] == "git":
        return (len(words) > 1 and words[1] in GIT_READ
                and not any(w.startswith(GIT_FORBIDDEN_OPTS) for w in words))
    return words[0] in READ_COMMANDS


def block_message(reason: str) -> str:
    return (f"BLOCKED: Gates nicht geladen (cloud_bootstrap, #522): {reason}.\n"
            "  Ohne geladene Gates sind nur lesende Werkzeuge erlaubt.\n"
            f"  Abhilfe: `{RETRY_CMD}` (die Umgebung muss github.com erreichen).\n"
            f"  Ausweg: {PO_EXIT}.")


def fail_response(data: dict, reason: str) -> int:
    """Verhalten, wenn der gepinnte Stand nicht ladbar ist (Spec Punkt 5 und 7)."""
    event = data.get("hook_event_name")
    if event == "UserPromptSubmit":
        set_override(data)
        return 0
    if event == "SessionStart":
        text = ("WARNUNG: Die Gates des Frameworks sind in dieser Cloud-Sitzung nicht geladen "
                f"({reason}). Schreibende Werkzeuge sind gesperrt, Lesen bleibt möglich. "
                f"Abhilfe: `{RETRY_CMD}` (die Umgebung muss github.com erreichen). "
                f"Ausweg: {PO_EXIT}.")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": text}},
                         ensure_ascii=False))
        return 0
    if event != "PreToolUse":
        return 0
    tool = data.get("tool_name")
    if tool in READ_TOOLS or override_active(data.get("session_id")):
        return 0
    tool_input = data.get("tool_input")
    if tool == "Bash" and isinstance(tool_input, dict) and bash_allowed(tool_input.get("command")):
        return 0
    print(block_message(reason), file=sys.stderr)
    return 2


# ------------------------------------------------------------------ Einstieg
def retry() -> int:
    try:
        ref, sha = read_pin()
        cache = fetch(ref, sha, force=True)
    except (FetchError, OSError) as exc:
        print(f"Abruf gescheitert: {exc}. Die Umgebung muss github.com erreichen.",
              file=sys.stderr)
        return 1
    print(f"Gates geladen: {ref} ({sha[:12]}) in {cache}")
    return 0


def _parse(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def main(argv: list) -> int:
    if argv[:1] == ["--retry"]:
        return retry()
    try:
        raw = sys.stdin.buffer.read()
    except (OSError, ValueError):
        raw = b""
    script, args = (argv[0], argv[1:]) if argv else ("", [])
    try:
        ref, sha = read_pin()
        cache = fetch(ref, sha, script=script if SCRIPT_RE.match(script) else "")
        path = resolve_script(cache, script)
    except (FetchError, OSError) as exc:
        return fail_response(_parse(raw), str(exc))
    return forward(cache, path, args, raw)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
