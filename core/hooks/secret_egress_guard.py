#!/usr/bin/env python3
"""
Secret Egress Guard — PreToolUse (alle Tools)

Gegenstueck zu secrets_guard.py: der bewacht die LESE-Richtung (cat .env,
Read .env), dieser hier die AUSGANGS-Richtung. Ist ein Secret einmal legitim
gelesen (secrets_guard hat einen Staging-Modus, der genau das erlaubt), kann
der Wert danach ungehindert in jede Datei, jeden Befehl, jede WebFetch-URL
oder jedes veroeffentlichte Artifact geschrieben werden. Genau so entstanden
~310 Wegwerf-Dateien mit gueltigen Zugangsdaten im Klartext.

Prinzip: Der Hook vergleicht den Nutzinhalt eines Tool-Calls gegen die
LITERALEN, AKTUELL GUELTIGEN Werte aus den .env-Dateien des Projekts.
Variablen-REFERENZEN ($GZ_SMTP_PASS) sind erwuenscht und gehen immer durch —
nur der ausgeschriebene Wert blockt.

Die .env wird bei JEDEM Aufruf frisch gelesen (kein Cache) — sonst greift der
Guard nach einer Passwort-Rotation ins Leere.

Fail-open by design: Jeder interne Fehler (keine .env, Parse-Fehler,
unerwartetes Payload-Format) endet mit Exit 0. Ein Guard, der bei eigenem
Defekt jede Arbeit blockiert, wird binnen einer Stunde abgeschaltet und
schuetzt dann gar nichts mehr.

Konfigurierbar via openspec.yaml:
  secret_egress_guard:
    enabled: true
    min_length: 8
    ignore_keys: [GZ_PUBLIC_ID]      # nie als Secret behandeln
    extra_key_patterns: ["MEIN_.*"]  # zusaetzlich als Secret behandeln
    scan_all_keys: false             # true = jeder .env-Wert gilt als Secret

Exit-Codes: 0 = erlaubt, 2 = blockiert
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path


def _setup():
    hooks_dir = str(Path(__file__).parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


_setup()

from hook_utils import find_project_root, log_gate_event  # noqa: E402
from override_token import has_valid_token  # noqa: E402

try:
    from config_loader import load_config
except ImportError:
    def load_config():
        return {}

# Mindestlaenge eines Wertes, ab der er ueberhaupt als Secret gilt.
# Begruendung: Unterhalb von 8 Zeichen liegen fast ausschliesslich Dummy-/
# Platzhalterwerte (test, 1234, admin, dev, local). Solche Strings kommen in
# normalem Code und Fliesstext staendig vor — jeder Treffer waere ein
# Fehlalarm, und ein Guard mit Dauerfehlalarm wird abgeschaltet. 8 ist
# zugleich die uebliche Untergrenze echter Passwortrichtlinien, echte
# API-Keys/SMTP-Keys liegen deutlich darueber (Resend: >30 Zeichen).
_DEFAULT_MIN_LENGTH = 8

# Key-Namen, deren Wert als Secret gilt. Ohne diese Einschraenkung wuerden
# harmlose Konfigwerte (GZ_SMTP_HOST=smtp.resend.com) blocken — die stehen in
# jeder Doku und wuerden den Guard unbenutzbar machen.
_SECRET_KEY_PATTERNS = [
    r"PASS", r"PWD", r"SECRET", r"TOKEN", r"APIKEY", r"API_KEY",
    r"KEY$", r"_KEY_", r"^KEY_", r"CREDENTIAL", r"AUTH", r"PRIVATE",
    r"SIGNING", r"SALT", r"COOKIE", r"SESSION", r"DSN", r"WEBHOOK",
]

# Platzhalter — nie ein echtes Secret.
_PLACEHOLDER_VALUES = {
    "changeme", "change_me", "change-me", "placeholder", "password",
    "passwort", "secret", "yoursecret", "your_secret", "your-secret",
    "your-key-here", "your_api_key", "your-api-key", "todo", "dummy",
    "example", "unset", "none", "null", "undefined", "test1234",
    "testtest", "12345678", "deadbeef",
}
_PLACEHOLDER_RE = re.compile(
    r"^(?:x+|y+|z+|\*+|\.+|-+|_+)$"          # xxxxxxxx, ********
    r"|^<.*>$"                                # <dein-key>
    r"|^your[-_ ]"                            # your-api-key-here
    r"|^(?:true|false|\d+(?:\.\d+)?)$",       # Flags/Zahlen
    re.IGNORECASE,
)
# Reine Pfade und credential-freie URLs sind Konfiguration, kein Secret —
# sie stehen in Doku/Skripten und wuerden sonst dauernd blocken.
_PATHLIKE_RE = re.compile(r"^(?:[~.]?/|[A-Za-z]:\\)")
_PLAIN_URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://(?![^/\s@]*:[^/\s@]+@)", re.IGNORECASE)
# Credentials, die IN einer URL stecken: postgres://user:passwort@host/db
_URL_CREDENTIAL_RE = re.compile(r"://[^/\s:@]+:([^@/\s]+)@")

# Tools ohne Ausgangsrichtung — nichts verlaesst hier das System.
_NO_EGRESS_TOOLS = {
    "Read", "Glob", "Grep", "TodoWrite", "BashOutput", "KillShell",
    "NotebookRead", "TaskGet", "TaskList",
}
# Tools, deren Nutzlast eine DATEI ist (Pfad im Input, Inhalt geht raus).
_FILE_PAYLOAD_TOOLS = {"SendUserFile", "Artifact"}

_MAX_ENV_BYTES = 256 * 1024
_MAX_HAYSTACK = 4 * 1024 * 1024
_MAX_PAYLOAD_FILE_BYTES = 1024 * 1024

# Geraete-Ziele, die kein Datei-Write sind: der Inhalt landet im Nirwana bzw.
# in den Standard-Kanaelen des eigenen Prozesses, verlaesst das System also
# nicht als Datei (Issue #237). /dev/tty und /dev/fd/N stehen bewusst NICHT
# hier: /dev/fd/N zeigt auf einen beliebigen offenen Deskriptor und koennte
# den Guard genau in dem Fall aushebeln, den er verhindern soll.
_ALLOWED_DEVICES = {"/dev/null", "/dev/stdout", "/dev/stderr"}

# Shell-Trennzeichen, die ohne Leerzeichen direkt am Umleitungs-Ziel kleben
# koennen ('2>/dev/null; echo x', 'cmd 2>/dev/null&', '(cmd 2>/dev/null)').
_TRAILING_SHELL_NOISE = ";&|)"


def _strip_trailing_shell_noise(target: str) -> str:
    """Entfernt eine beliebige Folge aus ';', '&', '|', ')' am RECHTEN Rand
    eines gefundenen Umleitungs-Ziels (Issue #237).

    Reihenfolge bindend: erst bereinigen, DANN die Ausnahme-Pruefungen
    (_ALLOWED_DEVICES, '^&\\d+$'). Andersherum bliebe '2>&1; echo x' ein
    Fehlalarm, weil '^&\\d+$' gegen den unbereinigten String '&1;' nicht passt.
    Ein FUEHRENDES '&' (wie in '>&2') wird von einer rein rechtsseitigen
    Bereinigung nie beruehrt — die FD-Duplizierungs-Ausnahme bleibt intakt.
    """
    return target.rstrip(_TRAILING_SHELL_NOISE)


def _get_config() -> dict:
    cfg = load_config().get("secret_egress_guard", {})
    return {
        "enabled": cfg.get("enabled", True),
        "min_length": int(cfg.get("min_length", _DEFAULT_MIN_LENGTH)),
        "ignore_keys": {str(k).upper() for k in cfg.get("ignore_keys", [])},
        "extra_key_patterns": list(cfg.get("extra_key_patterns", [])),
        "scan_all_keys": bool(cfg.get("scan_all_keys", False)),
        "redirect_guard_enabled": bool(cfg.get("redirect_guard_enabled", True)),
        "extra_allowed_write_dirs": list(cfg.get("extra_allowed_write_dirs", [])),
    }


def _env_files(root: Path) -> "list[Path]":
    """.env-Dateien des Projekts. Beispiel-/Template-Dateien ausgenommen."""
    skip_suffixes = (".example", ".sample", ".template", ".dist", ".md")
    seen, out = set(), []
    for base in (root, Path.cwd()):
        try:
            candidates = sorted(base.glob(".env*"))
        except OSError:
            continue
        for p in candidates:
            if p.name.endswith(skip_suffixes) or not p.is_file():
                continue
            real = str(p.resolve())
            if real in seen:
                continue
            seen.add(real)
            out.append(p)
    return out[:10]


def _parse_env(text: str) -> "list[tuple[str, str]]":
    pairs = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            # Unquoted: bash-artiger Trailing-Kommentar (nur mit Whitespace davor)
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        pairs.append((key, value))
    return pairs


def _is_secret_key(key: str, cfg: dict) -> bool:
    if key.upper() in cfg["ignore_keys"]:
        return False
    if cfg["scan_all_keys"]:
        return True
    patterns = _SECRET_KEY_PATTERNS + cfg["extra_key_patterns"]
    return any(re.search(p, key, re.IGNORECASE) for p in patterns)


def _is_secret_value(value: str, cfg: dict) -> bool:
    if len(value) < cfg["min_length"]:
        return False
    if value.lower() in _PLACEHOLDER_VALUES or _PLACEHOLDER_RE.search(value):
        return False
    if _PATHLIKE_RE.match(value) or _PLAIN_URL_RE.match(value):
        return False
    return True


def collect_secrets(cfg: dict, root: Path) -> "list[tuple[str, str]]":
    """(key, value)-Paare, frisch von Platte. Bewusst ohne Cache."""
    secrets = []
    for path in _env_files(root):
        try:
            if path.stat().st_size > _MAX_ENV_BYTES:
                continue
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for key, value in _parse_env(text):
            embedded = _URL_CREDENTIAL_RE.search(value)
            if embedded and _is_secret_value(embedded.group(1), cfg):
                # Passwort in einer Verbindungs-URL — unabhaengig vom Key-Namen
                secrets.append((key, embedded.group(1)))
            if _is_secret_key(key, cfg) and _is_secret_value(value, cfg):
                secrets.append((key, value))
    return secrets


def _walk_strings(node, out: list, budget: list) -> None:
    if budget[0] <= 0:
        return
    if isinstance(node, str):
        out.append(node)
        budget[0] -= len(node)
    elif isinstance(node, dict):
        for value in node.values():
            _walk_strings(value, out, budget)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _walk_strings(value, out, budget)


def _payload_file_contents(strings: "list[str]") -> "list[str]":
    """Inhalt referenzierter Dateien (SendUserFile/Artifact tragen den Inhalt
    einer Datei nach aussen, nicht den Text im Tool-Input)."""
    out = []
    for candidate in strings[:20]:
        if len(candidate) > 4096 or "\n" in candidate:
            continue
        try:
            p = Path(candidate).expanduser()
            if not p.is_file() or p.stat().st_size > _MAX_PAYLOAD_FILE_BYTES:
                continue
            out.append(p.read_text(errors="ignore"))
        except (OSError, ValueError):
            continue
    return out


def build_haystack(tool_name: str, tool_input: dict) -> str:
    strings: "list[str]" = []
    _walk_strings(tool_input, strings, [_MAX_HAYSTACK])
    if tool_name in _FILE_PAYLOAD_TOOLS:
        strings.extend(_payload_file_contents(strings))
    return "\n".join(strings)


def _targets_env_file(tool_input: dict, root: Path) -> bool:
    """Schreiben in die .env am angestammten Ort ist legitim (dafuer ist
    secrets_guard zustaendig, nicht dieser Hook)."""
    raw = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not raw:
        return False
    try:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        p = p.resolve()
        return p.name.startswith(".env") and str(p).startswith(str(root.resolve()))
    except (OSError, ValueError):
        return False


def _read_payload() -> "tuple[str, dict, str | None]":
    """(tool_name, tool_input, scratchpad_dir) — `scratchpad_dir` ist das
    Payload-Feld der aktuellen Sitzung (Issue #237, verfuegbar ab Claude Code
    v2.1.257). Der Env-Zweig (Alt-Pfad ohne stdin) liefert dafuer None: aus zwei
    isolierten Umgebungsvariablen laesst sich kein Scratchpad-Pfad gewinnen.
    """
    ti_env = os.environ.get("CLAUDE_TOOL_INPUT", "")
    tn_env = os.environ.get("CLAUDE_TOOL_NAME", "")
    if ti_env and tn_env:
        try:
            return tn_env, json.loads(ti_env), None
        except json.JSONDecodeError:
            return tn_env, {}, None
    try:
        data = json.load(sys.stdin)
        return data.get("tool_name", ""), data.get("tool_input", {}), data.get("scratchpad_dir")
    except Exception:
        return "", {}, None


def find_leaks(tool_name: str, tool_input: dict, cfg: dict, root: Path) -> "list[str]":
    """Namen der Secret-Variablen, deren Wert im Nutzinhalt steckt."""
    if tool_name in _NO_EGRESS_TOOLS or not isinstance(tool_input, dict):
        return []
    if _targets_env_file(tool_input, root):
        return []
    secrets = collect_secrets(cfg, root)
    if not secrets:
        return []
    haystack = build_haystack(tool_name, tool_input)
    if not haystack:
        return []
    hits = []
    for key, value in secrets:
        if value in haystack and key not in hits:
            hits.append(key)
    return hits


def _shell_write_targets(command: str) -> "list[str]":
    """Ziel-Pfade von '>', '>>' und 'tee' in einem Bash-Kommando (Issue #97).

    Tokenisierung identisch zu bash_gate.py::_has_real_redirect() (shlex mit
    Fallback auf den Roh-Scan bei verschachtelter Shell/eval oder Parse-Fehler,
    kein Guard-Drift-Import — bewusst eine parallele, kommentierte Kopie, wie
    zwischen bash_gate.py und secrets_guard.py bereits etabliert) — hier um die
    Ziel-STRINGS statt eine reine Bool-Erkennung erweitert.

    Beim sh -c/eval-Fallback liefert nur der rohe '>'-Scan Ziele (kein
    'tee'-Ziel aus dem Rohtext extrahierbar) — ein Redirect-Fund im Rohtext
    reicht bereits zum Block, siehe find_unsafe_redirects().
    """
    if re.search(r"\b(?:ba|z|da|k)?sh\s+-c\b|\beval\b", command):
        raw = [
            _strip_trailing_shell_noise(m.group(1))
            for m in re.finditer(r"(?<![\d-])>{1,2}\s*(\S+)", command)
        ]
        return [
            t for t in raw
            if t and t not in _ALLOWED_DEVICES and not re.match(r"^&\d+$", t)
        ]
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        raw = [
            _strip_trailing_shell_noise(m.group(1))
            for m in re.finditer(r"(?<![\d-])>{1,2}\s*(\S+)", command)
        ]
        return [
            t for t in raw
            if t and t not in _ALLOWED_DEVICES and not re.match(r"^&\d+$", t)
        ]

    targets = []
    for i, tok in enumerate(tokens):
        m = re.match(r"^\d*>{1,2}(.*)$", tok)
        if m:
            target = m.group(1) or (tokens[i + 1] if i + 1 < len(tokens) else "")
            target = _strip_trailing_shell_noise(target)
            if target and target not in _ALLOWED_DEVICES and not re.match(r"^&\d+$", target):
                targets.append(target)
        elif tok == "tee" or tok.endswith("/tee"):
            for nxt in tokens[i + 1:]:
                if nxt in ("-a", "--append"):
                    continue
                if nxt.startswith("-"):
                    break  # andere Flag (-i, --output-error, ...) — kein Ziel-Token
                nxt = _strip_trailing_shell_noise(nxt)
                if nxt and nxt not in _ALLOWED_DEVICES:
                    targets.append(nxt)
                break
    return targets


def _is_outside_safe_zone(target: str, root: Path, cfg: dict,
                          scratchpad_dir: "str | None" = None) -> bool:
    """True, wenn `target` ausserhalb Projekt UND ausserhalb aller konfigurierten
    Ausnahme-Verzeichnisse liegt.

    Relative Ziele werden wie in _targets_env_file() gegen Path.cwd() aufgeloest
    (dieselbe Annahme, die der Rest dieser Datei bereits trifft: die
    Hook-Subprocess-CWD entspricht der Ausfuehrungs-CWD des Bash-Tools).

    `scratchpad_dir` ist das private Sitzungs-Scratchpad aus dem Hook-Payload
    (Issue #237). Fehlt das Feld, existiert fuer diese Sitzung auch kein
    Scratchpad — dann wird der Zweig komplett uebersprungen (kein
    Muster-Fallback, der fremde Sitzungen derselben Maschine mit einschliessen
    wuerde).
    """
    try:
        p = Path(target).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        unresolved = str(p)
        resolved = str(p.resolve())
    except (OSError, ValueError):
        return False  # nicht als Pfad interpretierbar -> fail-open, wie der Rest der Datei
    root_str = str(root.resolve())
    if resolved == root_str or resolved.startswith(root_str + os.sep):
        return False
    if scratchpad_dir:
        # BEIDE Seiten durch dieselbe Aufloesung schicken und nur die
        # aufgeloesten Formen vergleichen. Das Problem war nie, dass ein Ziel in
        # zwei Schreibweisen vorliegen kann, sondern dass Ziel und
        # scratchpad_dir in UNTERSCHIEDLICHEN Formen verglichen wurden:
        # scratchpad_dir kommt als /tmp/claude-<uid>/... aus der Payload,
        # waehrend das Ziel auf macOS zu /private/tmp/... aufloest.
        #
        # Gegen die unaufgeloeste Ziel-Form zu vergleichen waere die falsche
        # Reparatur: dieser String normalisiert weder '..' noch folgt er
        # Symlinks, '<scratchpad>/../../fremd/leak.txt' bestuende die
        # Praefix-Pruefung und die Ausnahme waere ein Generalschluessel.
        # resolve() auf beiden Seiten entschaerft beides.
        #
        # Schlaegt das Aufloesen fehl, wird der Zweig uebersprungen (= nicht
        # erlaubt). Das ist die bewusste Ausnahme vom Fail-open-Prinzip dieser
        # Datei: ein Fehler waere hier eine Erlaubnis, nicht nur ein
        # ausgelassener Hinweis.
        try:
            sp = str(Path(scratchpad_dir).expanduser().resolve())
        except (OSError, ValueError):
            sp = None
        if sp and (resolved == sp or resolved.startswith(sp + os.sep)):
            # Praefix-Pruefung an os.sep gebunden, damit '/x/scratchpad-evil'
            # kein Unterordner von '/x/scratchpad' wird (AC-9).
            return False
    for pattern in cfg["extra_allowed_write_dirs"]:
        # Issue #239: bis hierher wurde nur gegen den AUFGELOESTEN Pfad geprueft —
        # ein Muster wie '^/tmp/' konnte damit nie greifen, weil /tmp auf macOS
        # zu /private/tmp aufloest. Jetzt zaehlt ein Treffer auf EINER der
        # beiden Pfad-Formen.
        if re.match(pattern, resolved) or re.match(pattern, unresolved):
            return False
    return True


def find_unsafe_redirects(tool_name: str, tool_input: dict, cfg: dict, root: Path,
                          scratchpad_dir: "str | None" = None) -> "list[str]":
    """Schreibziele ausserhalb der Sicherheitszone, nur fuer Bash-Kommandos (Issue #97)."""
    if not cfg["redirect_guard_enabled"] or tool_name != "Bash" or not isinstance(tool_input, dict):
        return []
    command = tool_input.get("command", "")
    if not command:
        return []
    targets = _shell_write_targets(command)
    unsafe = []
    for t in targets:
        if _is_outside_safe_zone(t, root, cfg, scratchpad_dir) and t not in unsafe:
            unsafe.append(t)
    return unsafe


def _block_unsafe_redirect(tool_name: str, unsafe: "list[str]",
                           scratchpad_dir: "str | None" = None) -> None:
    targets = ", ".join(unsafe)
    try:
        log_gate_event(
            hook="secret_egress_guard",
            tool=tool_name,
            reason=f"write target(s) outside safe zone: {targets}",
            command_excerpt="",
        )
    except Exception:
        pass
    # AC-15: Das Scratchpad nur empfehlen, wenn die Sitzung eins hat. Ein Rat,
    # der auf ein nicht existierendes Verzeichnis zeigt, kostet bei jedem
    # Treffer einen Fehlversuch — genau der Vorwurf aus Issue #237.
    if scratchpad_dir:
        right_target = ("  Richtiges Ziel: eine Datei innerhalb des Projekts, oder das private\n"
                        "  Sitzungs-Scratchpad.\n")
    else:
        right_target = "  Richtiges Ziel: eine Datei innerhalb des Projekts.\n"
    print(
        f"BLOCKED [secret_egress_guard]: {tool_name} schreibt per Umleitung (>, >>, tee) "
        f"auf ein Ziel ausserhalb von Projekt und erlaubten Verzeichnissen:\n"
        f"  {targets}\n"
        "  Zugangsdaten, die als Prozess-AUSGABE entstehen (z.B. eine fehlschlagende\n"
        "  Test-Assertion), waeren sonst unsichtbar fuer die Wert-Pruefung dieses Guards\n"
        "  (Issue #97).\n"
        + right_target +
        "  Fehlalarm? config.yaml -> secret_egress_guard.extra_allowed_write_dirs: "
        "[\"^<pfad-praefix>\"]\n"
        "  Einmaliger Bypass: 'override' tippen (1h gueltig).",
        file=sys.stderr,
    )
    sys.exit(2)


def main() -> None:
    cfg = _get_config()
    if not cfg["enabled"]:
        sys.exit(0)
    tool_name, tool_input, scratchpad_dir = _read_payload()
    root = find_project_root()
    hits = find_leaks(tool_name, tool_input, cfg, root)
    if not hits:
        unsafe = find_unsafe_redirects(tool_name, tool_input, cfg, root, scratchpad_dir)
        if unsafe and not has_valid_token():
            _block_unsafe_redirect(tool_name, unsafe, scratchpad_dir)
        sys.exit(0)
    names = ", ".join(hits)
    # command_excerpt bewusst NICHT befuellt: tool_input traegt hier per
    # Definition den ausgeschriebenen Geheimnis-Wert, den dieser Guard gerade
    # verhindert. Nur die (bereits im User-Text offengelegten) Schluessel-
    # NAMEN gehen ins Log — derselbe Verzicht, den die Meldung selbst schon
    # macht ("Der Wert selbst wird hier bewusst nicht ausgegeben").
    try:
        log_gate_event(
            hook="secret_egress_guard",
            tool=tool_name,
            reason=f"env var(s) leaked: {names}",
            command_excerpt="",
        )
    except Exception:
        pass
    print(
        f"BLOCKED [secret_egress_guard]: {tool_name} enthaelt den ausgeschriebenen "
        f"Wert von: {names} (aus .env).\n"
        "  Zugangsdaten duerfen nie in Dateien, Befehlen oder ausgehenden Inhalten\n"
        "  landen — auch nicht kurz in /tmp oder im Scratchpad.\n"
        "  Stattdessen zur Laufzeit aus der Umgebung lesen:\n"
        f'    Bash:   set -a; . "$CLAUDE_PROJECT_DIR/.env"; set +a   dann "${names.split(", ")[0]}"\n'
        f'    Python: os.environ["{hits[0]}"]\n'
        "  Der Wert selbst wird hier bewusst nicht ausgegeben (auch nicht maskiert).\n"
        "  Fehlalarm? openspec.yaml -> secret_egress_guard.ignore_keys: [" + hits[0] + "]",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Fail-open: ein defekter Guard darf keine Arbeit blockieren.
        sys.exit(0)
