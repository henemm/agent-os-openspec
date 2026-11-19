#!/usr/bin/env python3
"""Erwähnungs-Sperre (PreToolUse Bash): keine nackten `@name` in gh-Texten (#617).

GitHub wertet jedes nackte `@name` in Issues, Kommentaren, PRs und Releases
als Erwähnung und benachrichtigt den gleichnamigen Nutzer. Claude-Sitzungen
haben Oberflächentexte aus Mockups zitiert, die so einen Namen enthielten, und
damit wiederholt eine fremde Person benachrichtigt. Eine Gedächtnisregel hat
das nicht verhindert; dieser Hook prüft deshalb mechanisch.

Geprüft werden nur Befehle, die Text auf GitHub veröffentlichen:
`gh issue|pr create|comment|edit|close|reopen|review|merge`,
`gh release create|edit` und `gh api`, wenn es schreibt (Methode
POST/PATCH/PUT/DELETE oder Felder `-f/-F/--field/--raw-field/--input` ohne
`-X GET`, wie gh selbst entscheidet). `gh` wird auch hinter Zuweisungen,
Pfaden, `bash -c`/`sh -c`, `timeout`, `nice`, `xargs`, `sudo` und `env`
erkannt. Ist ein Teilbefehl schreibend, wird der GESAMTE Befehl (inklusive
Heredocs, weil `--body-file` oft auf eine Datei zeigt, die derselbe Befehl
erst schreibt) durchsucht, dazu existierende Dateien aus `--body-file`,
`-F <datei>`, `--input`, `-F feld=@datei`, `$(cat <datei>)`, `$(< <datei>)`
und `< <datei>` (höchstens 1 MB je Datei). Ausdrücke hinter
`--jq/-q/--template` (bei `gh api` auch `-t`) zählen nie als Text.

Erwähnung wie bei GitHub: `@` am Anfang oder nach einem Zeichen, das kein
Wortzeichen, kein Backtick und keins von `/ . @ -` ist, dann ein Nutzername
(`[A-Za-z0-9]`, danach bis 38 Zeichen aus `[A-Za-z0-9-]`, nicht auf `-`
endend), dahinter kein Wortzeichen, kein `-` und kein `/`. Code in Backticks
und Codeblöcken zählt nicht; E-Mail-Adressen, Pakete (`@scope/paket`) und
Shell-Formen (`"$@"`, `${a[@]}`) sind dadurch keine Treffer.

Konfiguration (openspec.yaml):
  mention_guard:
    enabled: true
    allowed_users: []   # gewollte Erwähnungen, Groß-/Kleinschreibung egal
Abschalten auch per `OPENSPEC_MENTION_GUARD=0` (bzw. off/false/no/disabled).

TRAGENDE ANFORDERUNG IST FAIL-OPEN: der Hook läuft vor jedem Bash-Befehl in
jedem Projekt. Jeder unklare Fall und jeder Fehler endet mit Exit 0; Befehle
über 200 KB werden nicht geprüft (Laufzeitgrenze).

Exit-Codes: 0 = erlaubt, 2 = blockiert
"""

import json
import os
import re
import shlex
import sys

from hook_utils import setup_path
setup_path()

from hook_utils import adopt_payload_cwd, block, strip_heredoc_bodies  # noqa: E402

_OFF_VALUES = {"off", "0", "false", "no", "disabled"}
_MAX_FILE_BYTES = 1024 * 1024
_MAX_COMMAND_CHARS = 200 * 1024
_MAX_TIEFE = 3

MUSTER = re.compile(
    r"(?<![\w`/.@-])@([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)(?![\w/-])")

_SCHREIBEND = {
    "issue": {"create", "new", "comment", "edit", "close", "reopen"},
    "pr": {"create", "new", "comment", "edit", "close", "reopen", "review", "merge"},
    "release": {"create", "new", "edit"},
}
_SCHREIB_METHODEN = {"POST", "PATCH", "PUT", "DELETE"}
# Optionen, die vor/zwischen den Unterbefehlen einen Wert verbrauchen.
_GLOBAL_VALUE_FLAGS = {"-R", "--repo", "--hostname"}
# Befehlswörter ohne eigene Optionen, die vor dem eigentlichen Befehl stehen.
_PRAEFIXE = {"{", "!", "then", "do", "else", "elif", "if", "while", "until",
             "command", "builtin", "exec", "nohup", "time"}
# Präfix-Befehle mit Optionen: Optionen, die einen Wert verbrauchen.
_PRAEFIX_OPTIONEN = {
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "nice": {"-n", "--adjustment"},
    "xargs": {"-I", "-i", "-n", "-P", "-L", "-l", "-d", "-E", "-e", "-s", "-a",
              "--max-args", "--max-procs", "--delimiter", "--arg-file"},
    "sudo": {"-u", "-g", "-h", "-p", "-U", "-C", "-D", "-r", "-t"},
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
}
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
_ZUWEISUNG = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_TRENN_ZEICHEN = set(";&|()\n")
# Ausdrücke, die gh selbst auswertet und nie veröffentlicht.
_AUSDRUCK_FLAGS = {"--jq", "-q", "--template"}

# Grobe Ersatz-Erkennung, falls der Befehl sich nicht zerlegen lässt.
_GROB = re.compile(
    r"(?:^|[;&|(\n{'\"]|\b(?:then|do)\b)\s*(?:[A-Za-z_]\w*=\S*\s+)*(?:\S*/)?gh\s+"
    r"(?:(?:-R|--repo)[\s=]+\S+\s+)?"
    r"(?:(?:issue|pr)\s+(?:(?:-R|--repo)[\s=]+\S+\s+)?"
    r"(?:create|new|comment|edit|close|reopen|review|merge)\b"
    r"|release\s+(?:(?:-R|--repo)[\s=]+\S+\s+)?(?:create|new|edit)\b"
    r"|(api)\b)"
)
_GROB_METHODE = re.compile(r"(?:-X\s*|--method[\s=]+)['\"]?([A-Za-z]+)")
_GROB_FELD = re.compile(r"(?:^|\s)(?:-[fF]|--field|--raw-field|--input)(?=[\s=]|\S)")

# Dateien, deren Inhalt per Shell in den Text gelangt.
_PFAD = r"""(?:"[^"\n]+"|'[^'\n]+'|[^\s)`'"<>;&|]+)"""
_DATEI_QUELLEN = (
    re.compile(r"\$\(\s*cat\s+([^)`]*?)\s*\)"),
    re.compile(r"`\s*cat\s+([^`)]*?)\s*`"),
    # Eingabe-Umleitung `< datei`; deckt auch `$(< datei)` ab.
    re.compile(r"(?<![<\d&])\d?<(?![<(&])\s*(" + _PFAD + r")"),
)


def ohne_code(text: str) -> str:
    """Codeblöcke und Code in Backticks entfernen (wie im Klartext-Gate)."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", " ", text)


def erwaehnungen(text: str) -> "list[str]":
    """Eindeutige Namen nackter Erwähnungen außerhalb von Code, in Fundreihenfolge."""
    gesehen, namen = set(), []
    for m in MUSTER.finditer(ohne_code(text)):
        name = m.group(1)
        if name.lower() not in gesehen:
            gesehen.add(name.lower())
            namen.append(name)
    return namen


def _abgeschaltet() -> bool:
    return os.environ.get("OPENSPEC_MENTION_GUARD", "").strip().lower() in _OFF_VALUES


def _segmente(command: str) -> "list[tuple[list[str], str]] | None":
    """Befehl in (Kommando, Trenner davor) zerlegen; None, wenn shlex scheitert.

    Heredoc-Bodies werden vorher entfernt: sie sind reine Daten (der Rohtext
    wird trotzdem geprüft), und ein Apostroph darin ließe shlex scheitern —
    dann gingen die Body-Dateien des Befehls verloren.
    """
    lex = shlex.shlex(strip_heredoc_bodies(command), posix=True,
                      punctuation_chars=";&|()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError:
        return None
    segmente, aktuell, trenner = [], [], ""
    for tok in tokens:
        if tok and set(tok) <= _TRENN_ZEICHEN:
            if aktuell:
                segmente.append((aktuell, trenner))
                trenner = tok
            elif tok != "\n":
                trenner = tok
            aktuell = []
        else:
            aktuell.append(tok)
    if aktuell:
        segmente.append((aktuell, trenner))
    return segmente


def _liest_stdin(args: "list[str]") -> bool:
    """True, wenn der Aufruf seinen Text per `--body-file -`, `-F -` oder `--input -` liest."""
    for i, tok in enumerate(args):
        if tok in ("--body-file", "--notes-file", "--input", "-F") and \
                i + 1 < len(args) and args[i + 1] == "-":
            return True
        if tok in ("--body-file=-", "--notes-file=-", "--input=-"):
            return True
    return False


def _cat_dateien(seg: "list[str]") -> "list[str]":
    """Dateiargumente eines `cat`-Segments, sonst leer."""
    i = _befehl_start(seg)
    if i >= len(seg) or os.path.basename(seg[i]) != "cat":
        return []
    return [t for t in seg[i + 1:] if t and not t.startswith("-")]


def _befehl_start(seg: "list[str]") -> int:
    """Index des eigentlichen Befehlsworts (Zuweisungen und Präfixe übersprungen)."""
    i = 0
    while i < len(seg):
        tok = seg[i]
        wort = os.path.basename(tok)
        if _ZUWEISUNG.match(tok) or tok in _PRAEFIXE:
            i += 1
            continue
        if wort in _PRAEFIX_OPTIONEN:
            mit_wert = _PRAEFIX_OPTIONEN[wort]
            i += 1
            while i < len(seg) and seg[i].startswith("-") and seg[i] != "-":
                i += 2 if seg[i] in mit_wert else 1
            if wort == "timeout" and i < len(seg):
                i += 1  # Dauer
            continue
        break
    return i


def _shell_argument(seg: "list[str]", i: int) -> "str | None":
    """Text hinter `bash -c` / `sh -lc` usw., sonst None."""
    if i >= len(seg) or os.path.basename(seg[i]) not in _SHELLS:
        return None
    j = i + 1
    while j < len(seg) and seg[j].startswith("-"):
        if not seg[j].startswith("--") and "c" in seg[j][1:]:
            return seg[j + 1] if j + 1 < len(seg) else None
        j += 1
    return None


def _positionen(args: "list[str]", anzahl: int) -> "list[str]":
    """Die ersten `anzahl` Positionsargumente, globale Wert-Optionen übersprungen."""
    pos, i = [], 0
    while i < len(args) and len(pos) < anzahl:
        tok = args[i]
        if tok in _GLOBAL_VALUE_FLAGS:
            i += 2
            continue
        if not tok.startswith("-"):
            pos.append(tok)
        i += 1
    return pos


def _api_methode(args: "list[str]") -> "str | None":
    for i, tok in enumerate(args):
        if tok in ("-X", "--method") and i + 1 < len(args):
            return args[i + 1].upper()
        if tok.startswith("--method="):
            return tok[len("--method="):].upper()
        if tok.startswith("-X") and len(tok) > 2:
            return tok[2:].upper()
    return None


def _api_hat_felder(args: "list[str]") -> bool:
    for tok in args:
        if tok in ("-f", "-F", "--field", "--raw-field", "--input"):
            return True
        if tok.startswith(("--field=", "--raw-field=", "--input=")):
            return True
        if len(tok) > 2 and tok[:2] in ("-f", "-F"):
            return True
    return False


def _schreibend(args: "list[str]") -> "str | None":
    """Gruppe (issue/pr/release/api), wenn der gh-Aufruf Text veröffentlicht."""
    pos = _positionen(args, 2)
    if not pos:
        return None
    gruppe = pos[0]
    if gruppe == "api":
        methode = _api_methode(args)
        if methode in _SCHREIB_METHODEN:
            return "api"
        if methode is None and _api_hat_felder(args):
            return "api"
        return None
    if len(pos) >= 2 and pos[1] in _SCHREIBEND.get(gruppe, ()):
        return gruppe
    return None


def _ausdruecke(args: "list[str]") -> "list[str]":
    """Werte von --jq/-q/--template (bei api auch -t): nie veröffentlichter Text."""
    pos = _positionen(args, 1)
    flags = _AUSDRUCK_FLAGS | ({"-t"} if pos and pos[0] == "api" else set())
    werte = []
    for i, tok in enumerate(args):
        if tok in flags and i + 1 < len(args):
            werte.append(args[i + 1])
        for f in ("--jq=", "--template="):
            if tok.startswith(f):
                werte.append(tok[len(f):])
    return [w for w in werte if w]


def _datei_verweise(gruppe: str, args: "list[str]") -> "tuple[list[str], list[str]]":
    """(Dateipfade, rohe Feld-Argumente `k=@datei`) eines schreibenden Aufrufs."""
    pfade, felder = [], []
    i = 0
    while i < len(args):
        tok = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else None
        if tok in ("--body-file", "--notes-file", "--input") and nxt is not None:
            pfade.append(nxt)
            i += 2
            continue
        for praefix in ("--body-file=", "--notes-file=", "--input="):
            if tok.startswith(praefix):
                pfade.append(tok[len(praefix):])
        wert = None
        if tok in ("-F", "--field") and nxt is not None:
            wert = nxt
            i += 1
        elif tok.startswith("--field="):
            wert = tok[len("--field="):]
        elif tok.startswith("-F") and len(tok) > 2:
            wert = tok[2:]
        if wert is not None:
            if gruppe == "api":
                _k, sep, v = wert.partition("=")
                if sep and v.startswith("@"):
                    pfade.append(v[1:])
                    felder.append(wert)
            else:
                pfade.append(wert)  # bei issue/pr/release: Body-/Notes-Datei
        i += 1
    return pfade, felder


def _shell_dateien(command: str) -> "list[str]":
    """Pfade aus `$(cat …)`, `` `cat …` ``, `$(< …)` und `< …` im Befehl."""
    pfade = []
    for muster in _DATEI_QUELLEN:
        for m in muster.finditer(command):
            try:
                teile = shlex.split(m.group(1))
            except ValueError:
                continue
            pfade.extend(t for t in teile if t and not t.startswith("-"))
    return pfade


def _lies(pfad: str) -> str:
    if not pfad or pfad == "-":
        return ""
    try:
        voll = os.path.expanduser(pfad)
        if not os.path.isabs(voll):
            voll = os.path.join(os.getcwd(), voll)
        if not os.path.isfile(voll):
            return ""
        with open(voll, "rb") as f:
            return f.read(_MAX_FILE_BYTES).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _grob_schreibend(command: str) -> bool:
    """Ersatz-Erkennung ohne Zerlegung (offene Anführungszeichen u. ä.)."""
    for m in _GROB.finditer(command):
        if not m.group(1):
            return True
        rest = command[m.end():]
        methode = _GROB_METHODE.search(rest)
        if methode:
            if methode.group(1).upper() in _SCHREIB_METHODEN:
                return True
            continue
        if _GROB_FELD.search(rest):
            return True
    return False


def _analysiere(command: str, tiefe: int = 0
                ) -> "tuple[bool, list[str], list[str], list[str]] | None":
    """(schreibend, Dateipfade, Feld-Argumente, Ausdrücke); None = nicht zerlegbar."""
    segmente = _segmente(command)
    if segmente is None:
        return None
    schreibend, pfade, felder, ausdruecke = False, [], [], []
    vorher: "list[str]" = []
    for seg, trenner in segmente:
        vorgaenger, vorher = vorher, seg
        i = _befehl_start(seg)
        inner = _shell_argument(seg, i)
        if inner is not None:
            if tiefe < _MAX_TIEFE:
                sub = _analysiere(inner, tiefe + 1)
                if sub is None:
                    sub = (_grob_schreibend(inner), [], [], [])
                schreibend = schreibend or sub[0]
                pfade += sub[1]
                felder += sub[2]
                ausdruecke += sub[3]
            continue
        if i >= len(seg) or os.path.basename(seg[i]) != "gh":
            continue
        args = seg[i + 1:]
        ausdruecke += _ausdruecke(args)
        gruppe = _schreibend(args)
        if gruppe is None:
            continue
        schreibend = True
        p, f = _datei_verweise(gruppe, args)
        pfade += p
        felder += f
        if trenner in ("|", "|&") and _liest_stdin(args):
            pfade += _cat_dateien(vorgaenger)  # cat datei | gh … --body-file -
    return schreibend, pfade, felder, ausdruecke


def pruefe(command: str) -> "list[str]":
    """Gefundene Namen nackter Erwähnungen in einem veröffentlichenden Befehl."""
    if "gh" not in command or len(command) > _MAX_COMMAND_CHARS:
        return []
    ergebnis = _analysiere(command)
    if ergebnis is None:
        ergebnis = (_grob_schreibend(command), [], [], [])
    schreibend, pfade, felder, ausdruecke = ergebnis
    if not schreibend:
        return []
    befehl = command
    for teil in felder + ausdruecke:
        befehl = befehl.replace(teil, " ")
    texte = [_lies(p) for p in pfade + _shell_dateien(command)]
    return erwaehnungen("\n".join([befehl] + texte))


def _config() -> "tuple[bool, set]":
    try:
        from config_loader import load_config
        cfg = load_config().get("mention_guard") or {}
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    erlaubt = cfg.get("allowed_users") or []
    if not isinstance(erlaubt, list):
        erlaubt = []
    return cfg.get("enabled", True) is not False, {
        str(n).lstrip("@").lower() for n in erlaubt if isinstance(n, (str, int))}


def main() -> None:
    if _abgeschaltet():
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        sys.exit(0)
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or "gh" not in command:
        sys.exit(0)
    adopt_payload_cwd(payload)

    gefunden = pruefe(command)
    if not gefunden:
        sys.exit(0)
    enabled, erlaubt = _config()
    if not enabled:
        sys.exit(0)
    gefunden = [n for n in gefunden if n.lower() not in erlaubt]
    if not gefunden:
        sys.exit(0)

    namen = ", ".join("@" + n for n in gefunden)
    block(
        "ERWÄHNUNGS-SPERRE: Der Text, den dieser gh-Befehl auf GitHub veröffentlicht, "
        f"enthält nackte Erwähnungen ({namen}).\n"
        "GitHub benachrichtigt sonst die gleichnamigen GitHub-Nutzer, meist fremde "
        "Personen.\n"
        "Setz jeden Namen in Backticks (`@name`) oder lass das @ weg. Ist die "
        "Erwähnung gewollt: Namen in openspec.yaml unter mention_guard.allowed_users "
        "eintragen.",
        hook="mention_guard",
        tool="Bash",
        command_excerpt=command,
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Fail-open: ein Absturz hier würde jeden Bash-Befehl stören.
        sys.exit(0)
