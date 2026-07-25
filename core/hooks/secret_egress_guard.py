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
import sys
from pathlib import Path


def _setup():
    hooks_dir = str(Path(__file__).parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


_setup()

from hook_utils import find_project_root  # noqa: E402

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


def _get_config() -> dict:
    cfg = load_config().get("secret_egress_guard", {})
    return {
        "enabled": cfg.get("enabled", True),
        "min_length": int(cfg.get("min_length", _DEFAULT_MIN_LENGTH)),
        "ignore_keys": {str(k).upper() for k in cfg.get("ignore_keys", [])},
        "extra_key_patterns": list(cfg.get("extra_key_patterns", [])),
        "scan_all_keys": bool(cfg.get("scan_all_keys", False)),
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


def _read_payload() -> "tuple[str, dict]":
    ti_env = os.environ.get("CLAUDE_TOOL_INPUT", "")
    tn_env = os.environ.get("CLAUDE_TOOL_NAME", "")
    if ti_env and tn_env:
        try:
            return tn_env, json.loads(ti_env)
        except json.JSONDecodeError:
            return tn_env, {}
    try:
        data = json.load(sys.stdin)
        return data.get("tool_name", ""), data.get("tool_input", {})
    except Exception:
        return "", {}


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


def main() -> None:
    cfg = _get_config()
    if not cfg["enabled"]:
        sys.exit(0)
    tool_name, tool_input = _read_payload()
    hits = find_leaks(tool_name, tool_input, cfg, find_project_root())
    if not hits:
        sys.exit(0)
    names = ", ".join(hits)
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
