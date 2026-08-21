#!/usr/bin/env python3
"""
OpenSpec Framework - Hook Utilities

Shared bootstrap module for all hooks. Handles:
- sys.path setup for same-directory imports
- Common input parsing (tool_input from env or stdin)
- Standardized exit helpers

Usage in any hook:
    from hook_utils import setup_path, get_tool_input, block, allow
    setup_path()
    from config_loader import load_config, find_project_root
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path


# --- git-Aufrufform-Erkennung (Issue #1431) --------------------------------
# Ersetzt die naive Teilstring-Pruefung `"git commit" in command`, die in
# BEIDE Richtungen falsch lag: jede Form mit etwas zwischen `git` und dem
# Unterbefehl (`git -C /pfad commit`, `git -c k=v commit`, `git --no-pager
# commit`) rutschte still durch, waehrend die blosse ERWAEHNUNG der Zeichen-
# folge (`grep -rn "git commit"`, `gh issue create --body "... git commit ..."`)
# faelschlich anschlug.
#
# GRUNDHALTUNG (PO-Richtungswechsel nach drei Adversary-Runden): NICHT
# "erkenne ich einen Aufruf? nein -> durchlassen", sondern "bin ich sicher,
# dass hier keiner drinsteckt? nur dann durchlassen". Eine Kommandozeile ist
# beliebig verschachtelbar (Backticks, `$( … )`, Schleifen-Schluesselwoerter,
# `eval`, Heredocs) — wer sie vollstaendig verstehen will, jagt endlos die
# naechste Variante. Drei Faelle:
#
#   1. Zerlegung findet den Aufruf                       -> pruefen
#   2. Zerlegung findet nichts, Kommando sauber zerlegbar -> durchlassen
#   3. Zerlegung findet nichts, Kommando NICHT sicher
#      zerlegbar, Zeichenfolge kommt vor                 -> im Zweifel pruefen
#
# Damit ist die alte Teilstring-Pruefung die Untergrenze: was sie fing, wird
# weiterhin geprueft — ausser das Kommando ist sauber zerlegbar und enthaelt
# nachweislich nur eine Erwaehnung (das behebt den `grep`-Fehlalarm).

_GIT_SHELL_BINARY_RE = re.compile(r"^(?:ba|z|da|k)?sh$")
# Zeichen, die shlex als eigenstaendige Punktuations-Token liefern soll. Der
# Standardsatz von punctuation_chars=True ist "();<>|&"; "\n" und der Backtick
# kommen dazu (s. _git_lex bzw. Adversary-Befund F005).
_GIT_PUNCTUATION = "();<>|&\n`"
_GIT_PUNCTUATION_CHARS = frozenset(_GIT_PUNCTUATION)
# Zeichen, die ein Kommando-Segment BEENDEN. "<" und ">" allein tun das NICHT —
# ein Redirect gehoert zum selben Kommando (`git show x > y` ist EIN Aufruf).
# Prozess-Substitution "<(" beendet es dagegen sehr wohl; deshalb entscheidet
# nicht der ganze Token, sondern ob ein echtes Trenner-Zeichen darin vorkommt.
_GIT_SEPARATOR_CHARS = frozenset("&|;()\n`")
# Trenner-Woerter: Gruppierungszeichen, die shlex nur bei umgebendem
# Whitespace abtrennt.
#
# Bash-Schluesselwoerter (`do`, `then`, `fi`, …) standen hier zwischenzeitlich
# ebenfalls, als Antwort auf Adversary-Befund F006 (`for … do git commit …`).
# Sie sind wieder raus: die Positions-Suche (_git_subcommands_in_segment)
# erledigt denselben Fall allgemeiner, und KEINE Mutation der Schluesselwort-
# Liste konnte danach noch einen Test roten — unfalsifizierbarer Code, der nur
# neue Fehlerquellen mitbringt (ein Dateiname "do" haette Segmente zerrissen).
_GIT_SEPARATOR_WORDS = frozenset({"{", "}", "!"})
# Zeilenfortsetzung: "\" + Zeilenumbruch ist in der Shell schlicht NICHTS —
# sie wird ERSATZLOS entfernt, sie ist kein Trennzeichen. Ohne Normalisierung
# zerfaellt `git \<umbruch> commit` in zwei Segmente; mit einem Leerzeichen als
# Ersatz zerfaellt umgekehrt `gi\<umbruch>t` in zwei Woerter und es bleibt gar
# kein git-Token uebrig (Adversary-Befund F009). Beide Zeilenenden, weil
# `\`+CRLF sonst als maskiertes "\r" ueberlebt und als Unterbefehl gilt.
# Bewusst NICHT betroffen: "\" + Leerzeichen (maskiertes Leerzeichen in einem
# Dateinamen) und jeder andere Backslash.
_GIT_LINE_CONTINUATIONS = ("\\\r\n", "\\\n")
# git-Vor-Optionen (vor dem Unterbefehl), deren WERT ein eigenes Token ist.
_GIT_OPTS_WITH_VALUE = {
    "-c", "-C", "--exec-path", "--git-dir", "--work-tree",
    "--namespace", "--super-prefix", "--config-env",
}
# Wrapper, die vor `git` stehen duerfen, ohne die Bedeutung zu aendern.
_GIT_COMMAND_PREFIXES = {"sudo", "env", "nice", "command", "time", "nohup"}
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _looks_like_git(token: str) -> bool:
    return token == "git" or token.endswith("/git")


def _git_subcommand_after(tokens: "list[str]", i: int) -> "str | None":
    """Erstes Nicht-Options-Token nach einem `git`-Token (= der Unterbefehl)."""
    while i < len(tokens):
        tok = tokens[i]
        if _is_git_separator(tok):
            return None  # Kommando endet, bevor ein Unterbefehl kam
        if tok in _GIT_OPTS_WITH_VALUE:
            i += 2  # Vor-Option + ihr Wert (`-C /pfad`, `-c k=v`)
            continue
        if tok.startswith("-"):
            i += 1  # `--no-pager`, `--git-dir=…`, `-p`, …
            continue
        return tok
    return None


def _git_subcommand_of_segment(tokens: "list[str]") -> "str | None":
    """Unterbefehl EINES Kommando-Segments, wenn `git` ganz vorn steht.

    Streng kopf-gebunden — das ist die Grundlage von `is_pure_git_command`.
    Fuer 'git steckt irgendwo drin' (`xargs … git commit`) dient
    `_git_subcommands_in_segment`.
    """
    i = 0
    while i < len(tokens) and (
        _ENV_ASSIGN_RE.match(tokens[i]) or tokens[i] in _GIT_COMMAND_PREFIXES
    ):
        i += 1
    if i >= len(tokens) or not _looks_like_git(tokens[i]):
        return None
    return _git_subcommand_after(tokens, i + 1)


def _git_subcommands_in_segment(tokens: "list[str]") -> "list[str]":
    """Unterbefehle zu JEDEM `git`-Token des Segments, nicht nur zum ersten.

    Faengt Wrapper, die wir nicht namentlich kennen (`xargs -I{} git commit`,
    `timeout 5 git commit`). Der Preis ist Ueber-Erkennung bei UNGEQUOTETER
    Erwaehnung (`echo the git commit is broken`) — die sichere Richtung: das
    Gate laeuft zusaetzlich, statt zu fehlen. Eine gequotete Erwaehnung
    (`grep -rn "git commit"`) ist EIN Token und wird hier nicht getroffen.
    """
    out: "list[str]" = []
    for i, tok in enumerate(tokens):
        if _looks_like_git(tok):
            sub = _git_subcommand_after(tokens, i + 1)
            if sub:
                out.append(sub)
    return out


def _git_nested_subcommands(segment: "list[str]", depth: int) -> "list[str]":
    """Unterbefehle aus verschachtelten Shells (`sh -c "…"`, `eval "…"`)."""
    if depth >= 2:
        return []
    found: "list[str]" = []
    for i, tok in enumerate(segment):
        base = tok.rsplit("/", 1)[-1]
        if _GIT_SHELL_BINARY_RE.match(base):
            if i + 2 < len(segment) and segment[i + 1] == "-c":
                found.extend(git_subcommands(segment[i + 2], depth + 1))
        elif base == "eval":
            for nested in segment[i + 1:]:
                found.extend(git_subcommands(nested, depth + 1))
    return found


def _git_lex(command: str) -> "list[str] | None":
    """Tokenisieren, mit Shell-Trennern als EIGENE Token; None bei kaputten Quotes.

    `shlex.split()` genuegt hier nicht (Adversary-Befunde F001/F002 zu #1431):

      * `cd /tmp&&git commit -m x` — ohne Leerzeichen um den Trenner verklebt
        split() `/tmp&&git` zu EINEM Token; die Verkettung wird unsichtbar.
        Das war eine Verschlechterung gegenueber der alten Teilstring-Pruefung,
        die diesen Fall noch fing.
      * `git status\\ntouch <marker>` — den Zeilenumbruch verschluckt split()
        als gewoehnlichen Whitespace; das angehaengte Kommando verschwand.

    `punctuation_chars` loest beides mit Bordmitteln: shlex liefert
    "&& || ; | & ( )" als eigene Token, unabhaengig von Leerzeichen, und laesst
    Quoting unberuehrt — `-m "a && b"` und mehrzeilige Commit-Messages bleiben
    EIN Token. Der Zeilenumbruch wird zusaetzlich aus dem Whitespace-Satz
    genommen, sonst greift die Whitespace-Regel vor der Punktuations-Regel.
    `commenters` wird geleert, damit `#` wie bei `shlex.split()` normaler Text
    bleibt (sonst wuerde `git log --grep=#1431` abgeschnitten).
    """
    for _continuation in _GIT_LINE_CONTINUATIONS:
        command = command.replace(_continuation, "")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=_GIT_PUNCTUATION)
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return None


def _is_git_separator(token: str) -> bool:
    """Ist das Token ein Kommando-Trenner (und kein Argument)?

    Zwei Sorten:
      * Trenner-WOERTER — Bash-Schluesselwoerter (`do`, `then`, `fi`, …) und
        Gruppierungszeichen. Nur als eigenstaendiges Token, eine gequotete
        Erwaehnung ("do") ist Teil eines groesseren Tokens und faellt nicht auf.
      * Trenner-ZEICHEN — shlex fasst aufeinanderfolgende Punktuationszeichen
        zu einem Token zusammen ("&&", ";\\n", "\\n\\n", "|&", "<("), deshalb
        Zeichen-Pruefung statt Gleichheit. Ein Token muss ausschliesslich aus
        Punktuationszeichen bestehen UND mindestens ein echtes Trenner-Zeichen
        enthalten: ">" / ">>" / "<" sind Redirects und trennen NICHT, "<(" und
        ">(" (Prozess-Substitution) dagegen schon.
    """
    if not token:
        return False
    if token in _GIT_SEPARATOR_WORDS:
        return True
    if not all(ch in _GIT_PUNCTUATION_CHARS for ch in token):
        return False
    return any(ch in _GIT_SEPARATOR_CHARS for ch in token)


def _is_confidently_decomposed(command: str) -> bool:
    """Traut sich die Zerlegung eine vollstaendige Aussage zu?

    Nein, wenn der Lexer scheitert — kaputte oder absichtlich unbalancierte
    Quotes. Genau dieser Fall loest 'im Zweifel pruefen' aus.

    Heredocs (`<<EOF`) standen hier zwischenzeitlich als zweiter Grund. Sie
    sind wieder raus: ihr Rumpf wird mit-tokenisiert, ein `git commit` darin
    findet die Positions-Suche ohnehin (Fall 1), und ein Rumpf mit ungeraden
    Anfuehrungszeichen laesst den Lexer scheitern (Fall 3). Eine Mutation der
    Heredoc-Sonderregel konnte keinen Test roten — sie war wirkungslos.
    """
    return _git_lex(command) is not None


def _git_segments(command: str) -> "list[list[str]] | None":
    """Kommando in Segmente zerlegen; None, wenn nicht verlaesslich zerlegbar."""
    tokens = _git_lex(command)
    if tokens is None:
        return None
    segments: "list[list[str]]" = [[]]
    for tok in tokens:
        if _is_git_separator(tok):
            segments.append([])
        else:
            segments[-1].append(tok)
    return [s for s in segments if s]


def git_subcommands(command: str, depth: int = 0) -> "list[str]":
    """Alle git-Unterbefehle, die in `command` tatsaechlich AUFGERUFEN werden.

    Erkennt: direkte Form, `-c k=v`, `-C /pfad`, `--no-pager`,
    `--git-dir=… --work-tree=…`, Verkettungen (`x && git commit …`),
    absolute Pfade (`/usr/bin/git commit`) und verschachtelte Shells
    (`bash -c "git commit"`).

    Erkennt NICHT (korrekt so): blosse Erwaehnung in `grep`/`echo`, in
    `--body`/`-m`-Freitext oder in `git log --grep="commit"`.

    Fail-open: ein nicht zerlegbares Kommando (kaputte Quotes) liefert eine
    leere Liste — ein Gate darf daran weder blockieren noch abstuerzen.
    """
    segments = _git_segments(command)
    if segments is None:
        return []
    found: "list[str]" = []
    for segment in segments:
        found.extend(_git_subcommands_in_segment(segment))
        found.extend(_git_nested_subcommands(segment, depth))
    return found


def git_head_subcommands(command: str) -> "list[str]":
    """Nur Unterbefehle, bei denen `git` am ANFANG eines Segments steht.

    Strenge Variante ohne Zweifels-Regel — fuer Entscheidungen, bei denen
    Ueber-Erkennung die GEFAEHRLICHE Richtung ist (Whitelist: ein Treffer
    ueberspringt Schutzpruefungen). Unter-Erkennung heisst dort nur, dass
    zusaetzlich geprueft wird.
    """
    segments = _git_segments(command)
    if segments is None:
        return []
    return [s for s in (_git_subcommand_of_segment(seg) for seg in segments) if s]


def is_git_subcommand(command: str, subcommand: str) -> bool:
    """Muss dieses Kommando als `git <subcommand>` behandelt werden?

    Nicht "erkenne ich einen Aufruf?", sondern "bin ich sicher, dass keiner
    drinsteckt?" — die drei Faelle stehen oben im Modul-Kommentar. Fall 3 ist
    die Untergrenze: was die alte Teilstring-Pruefung fing, wird weiterhin
    geprueft, sobald die Zerlegung sich keine vollstaendige Aussage zutraut.
    """
    if subcommand in git_subcommands(command):
        return True  # Fall 1
    if _is_confidently_decomposed(command):
        return False  # Fall 2 — behebt den grep-/echo-Fehlalarm
    return f"git {subcommand}" in command  # Fall 3 — im Zweifel pruefen


def is_pure_git_command(command: str) -> bool:
    """True, wenn JEDES Segment des Kommandos ein reiner git-Aufruf ist.

    Fuer Ausnahmen, die 'das ist nur git' voraussetzen: `git commit -m "…"`
    bleibt ausgenommen, `git status && touch <freigabe-marker>` NICHT. Im
    Zweifel (nicht sicher zerlegbar) wird die Ausnahme NICHT gewaehrt.
    """
    if not _is_confidently_decomposed(command):
        return False
    segments = _git_segments(command)
    if not segments:
        return False
    return all(_git_subcommand_of_segment(s) is not None for s in segments)


# AC-Bullet-Start: unindentierte '- ...AC-N...:'-Zeile. Deckt fuenf
# Label-Varianten ab:
#   '- **AC-1:** ...'            (Doppelpunkt innerhalb Bold)
#   '- **AC-1**: ...'            (Doppelpunkt ausserhalb Bold)
#   '- **AC-8 (praezisiert):** ' (Klammer-Zusatz + Doppelpunkt in Bold)
#   '- AC-1: ...'                (ganz ohne Bold)
#   '- **AC-S6-1:** ...'         (Scheiben-Label zwischen 'AC-' und der Zahl,
#                                 z.B. gregor_zwanzig Epic #1703 Scheiben-
#                                 Nummerierung AC-S<Scheibe>-<N>)
# Das optionale '([A-Za-z0-9]+-)?' vor der Zahl deckt den Scheiben-Praefix ab,
# ohne Bestandsformate ('AC-1', 'AC-8 (...)') zu beruehren -- ein Praefix
# erfordert einen eigenen Bindestrich vor der Zahl, ein reines 'AC-12' bleibt
# unveraendert eine einzelne Zahl (Backtracking macht den Praefix optional).
_AC_BULLET_RE = re.compile(r"^-\s+\*{0,2}AC-(?:[A-Za-z0-9]+-)?\d+[^:*]*\*{0,2}\s*:")
# Split-Variante: trennt Label (inkl. Klammer-Zusatz) vom Beschreibungstext.
# Konsumiert Bold-Marker auf beiden Seiten des Doppelpunkts.
_AC_SPLIT_RE = re.compile(
    r"^-\s+\*{0,2}(AC-(?:[A-Za-z0-9]+-)?\d+[^:*]*?)\*{0,2}\s*:\s*\*{0,2}\s*(.*)$"
)


def extract_ac_entries(content: str) -> "list[tuple[str, str, str]]":
    """Section-gebunden AC-N-Bullets aus '## Acceptance Criteria' extrahieren.

    Liefert (label, description, raw) je Bullet, z.B.
    ("AC-1", "Given ... Then ...", "**AC-1:** Given ... Then ...").
    raw = Original-Bulletzeile (inkl. Soft-Wrap-Fortsetzungen) OHNE fuehrendes
    "- ", damit Konsumenten den unveraenderten Quelltext erhalten koennen.
    Soft-Wrap-Fortsetzungszeilen werden angehaengt, eingerueckte Sub-Bullets
    (z.B. '- Test:') verworfen. Nur Bullets INNERHALB der Section zaehlen --
    weder Fliesstext-Querverweise noch Tabellenzellen noch Vorkommen in
    anderen Sections.

    Section-gebundene State-Machine, 1:1 aus der bisherigen Inline-Logik in
    adversary_dialog.parse_spec_expected_behavior uebernommen; einziger
    Unterschied: Label, Beschreibungstext UND der Original-Rohtext werden
    getrennt zurueckgegeben statt als ein rekonstruierter String.
    """
    lines = content.splitlines()
    in_section = False
    ac_active = False
    entries: "list[list[str]]" = []  # [label, description, raw], mutable fuer Soft-Wrap

    for line in lines:
        stripped = line.strip()
        indented = line[:1].isspace()

        # Section-State pflegen (case-insensitive)
        if re.match(r"^##\s+Expected Behavior", stripped, re.IGNORECASE):
            in_section = False
            ac_active = False
            continue
        if re.match(r"^##\s+Acceptance Criteria", stripped, re.IGNORECASE):
            in_section = True
            ac_active = False
            continue
        # Jede andere H2-Section beendet die aktuelle Section
        if re.match(r"^##\s+", stripped):
            in_section = False
            ac_active = False
            continue

        if not in_section:
            continue

        # AC-Bullet nur INNERHALB der Acceptance-Criteria-Section (unindentiert)
        if not indented and _AC_BULLET_RE.match(stripped):
            raw = re.sub(r"^-\s+", "", stripped)  # Original-Bullet ohne "- "
            m = _AC_SPLIT_RE.match(stripped)
            if m:
                label = m.group(1).strip()
                desc = m.group(2).strip()
            else:  # Defensive: sollte nie eintreten (Split ist Superset)
                label = ""
                desc = raw
            entries.append([label, desc, raw])
            ac_active = True
            continue
        # Innerhalb eines offenen AC-Blocks: Sub-Bullet vs. Fortsetzung
        if ac_active and indented:
            if stripped.startswith("-"):
                # Eingerueckter Sub-Bullet (z.B. '- Test:') -> verwerfen
                continue
            if stripped:
                # Fortsetzungszeile (Soft-Wrap) -> an desc UND raw anhaengen
                entries[-1][1] = (entries[-1][1] + " " + stripped).strip()
                entries[-1][2] = (entries[-1][2] + " " + stripped).strip()
            continue
        # Unindentierte Nicht-AC-Zeile beendet einen offenen AC-Block
        if not indented and stripped:
            ac_active = False

    return [(label, desc, raw) for label, desc, raw in entries]


def setup_path():
    """Add the hooks directory to sys.path for same-directory imports.
    Call this BEFORE importing config_loader or other hook modules."""
    hooks_dir = str(Path(__file__).parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


def get_tool_input() -> dict:
    """Parse tool input from CLAUDE_TOOL_INPUT env var or stdin.
    Returns parsed dict or empty dict on failure."""
    tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")

    if not tool_input:
        try:
            data = json.load(sys.stdin)
            return data.get("tool_input", {})
        except (json.JSONDecodeError, Exception):
            return {}

    try:
        return json.loads(tool_input) if isinstance(tool_input, str) else tool_input
    except json.JSONDecodeError:
        return {}


def get_user_message() -> str:
    """Parse user message from stdin (for UserPromptSubmit hooks).

    Claude Code sendet den Prompt-Text im Feld "prompt" (offizielle Hook-API).
    "user_message" wird als Fallback fuer aeltere Versionen/Wrapper beibehalten.
    Vor diesem Fix las der Hook ausschliesslich "user_message" und bekam daher
    IMMER einen leeren String — der gesamte phase_listener (override, go/approval,
    stop-lock, GREEN) war dadurch funktionslos.
    """
    try:
        data = json.load(sys.stdin)
        return data.get("prompt") or data.get("user_message", "")
    except (json.JSONDecodeError, Exception):
        return ""


def get_tool_result() -> dict:
    """Parse tool result from stdin (for PostToolUse hooks)."""
    try:
        data = json.load(sys.stdin)
        return data
    except (json.JSONDecodeError, Exception):
        return {}


def block(message: str):
    """Block the operation with an error message and exit."""
    print(message, file=sys.stderr)
    sys.exit(2)


def allow():
    """Allow the operation and exit."""
    sys.exit(0)


# --- Geteilte Secrets-Muster (Issue #75) ---
# EINE Quelle fuer bash_gate.py UND secrets_guard.py. Vorher fuehrte bash_gate
# die aelteren Breitmuster `_key`/`_secret` (Substring ohne Anker), waehrend
# secrets_guard bereits die geschaerften Formen hatte — der Drift blockierte
# Befehle wegen blosser Dateinamen (tests/test_secret_egress_guard.py).
SECRETS_SENSITIVE_PATTERNS = [
    r"\.env",
    r"credentials\.json",
    r"service[_-]?account.*\.json",
    r"private[_.]key",
    r"[_.]secret\.",
    r"\.pem$",
    r"\.key$",
]

SECRETS_ALWAYS_BLOCKED = [
    r"credentials\.json",
    r"service[_-]?account.*\.json",
    r"private[_.]key",
    r"[_.]secret\.",
    r"\.pem$",
    r"\.key$",
]

# Flags, deren Argument Freitext ist (Commit-Message, PR-/Issue-Body) — nie
# ein Datei-Pfad. Wird bei Datei-Token-Analysen uebersprungen (Issue #53).
SECRETS_FREETEXT_FLAGS = {"-m", "--message", "--body", "--title", "-F"}


# Heredoc-Body-Stripping (Issues #64/#75): shlex kennt keine Heredoc-Syntax,
# darum landeten Body-Woerter (Doku-Freitext, Commit-Messages) als normale
# Tokens in den Datei-/Kommando-Scans. Ein Heredoc-Body ist DATEN, kein
# Kommando — ausser ein Interpreter auf der Oeffner-Zeile fuehrt ihn aus.
_HEREDOC_OPEN_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_HEREDOC_INTERPRETER_RE = re.compile(
    r"\b(python3?|node|perl|ruby|php|(?:ba|z|da|k)?sh)\b"
)


def strip_heredoc_bodies(command: str) -> str:
    """Entfernt Heredoc-BODIES aus einem Kommandotext, Oeffner-Zeilen bleiben.

    Sicherheitsmodell:
    - Der Body ist stdin-DATEN des empfangenden Kommandos; Schreibziele
      (Redirects, tee-Argumente) stehen auf der Oeffner-Zeile und bleiben
      fuer die Gates sichtbar.
    - Steht auf der Oeffner-Zeile ein Interpreter (python/sh/node/...), ist
      der Body potenziell CODE — dann wird er NICHT entfernt (konservativ).
    - Terminator-Erkennung POSIX-genau: Zeile == Marker; bei `<<-` sind
      fuehrende Tabs erlaubt. Ein nie geschlossenes Heredoc verschluckt den
      Rest — exakt wie die Shell selbst.
    """
    if "<<" not in command:
        return command
    out = []
    pending: list[tuple[str, bool]] = []  # (marker, allow_tab_indent)
    for line in command.split("\n"):
        if pending:
            marker, dash = pending[0]
            candidate = line.lstrip("\t") if dash else line
            if candidate == marker:
                pending.pop(0)
            continue  # Body-Zeile (oder Terminator) — nie uebernehmen
        openers = [
            (m.group(2), m.group(0).startswith("<<-"))
            for m in _HEREDOC_OPEN_RE.finditer(line)
            # `<<<` (Here-String) ist kein Heredoc-Oeffner
            if not (m.start() > 0 and line[m.start() - 1] == "<")
        ]
        if openers and not _HEREDOC_INTERPRETER_RE.search(line):
            pending.extend(openers)
        out.append(line)
    return "\n".join(out)


def get_file_path(tool_input: dict = None) -> str:
    """Extract file_path from tool input."""
    if tool_input is None:
        tool_input = get_tool_input()
    return tool_input.get("file_path", "")


def get_command(tool_input: dict = None) -> str:
    """Extract command from tool input (for Bash hooks)."""
    if tool_input is None:
        tool_input = get_tool_input()
    return tool_input.get("command", "")


def is_code_file(file_path: str) -> bool:
    """Check if a file is a code file based on extension."""
    code_extensions = [
        ".py", ".js", ".ts", ".tsx", ".jsx",
        ".swift", ".kt", ".java",
        ".go", ".rs", ".cpp", ".c", ".h",
        ".rb", ".php", ".cs",
    ]
    return any(file_path.endswith(ext) for ext in code_extensions)


def find_main_repo_from_worktree(start: Path) -> "Path | None":
    """If start is inside a git worktree, return the linked main repo root.

    Git worktrees place a .git FILE (not directory) pointing at the main repo:
      gitdir: <main>/.git/worktrees/<name>
    Returns None if start is not in a worktree.
    """
    current = start
    while current != current.parent:
        git_marker = current / ".git"
        if git_marker.is_file():
            try:
                content = git_marker.read_text(errors="ignore").strip()
            except OSError:
                return None
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("gitdir:"):
                    gitdir = Path(line[len("gitdir:"):].strip())
                    if not gitdir.is_absolute():
                        gitdir = (current / gitdir).resolve()
                    # Walk up until we find the .git directory itself
                    walker = gitdir
                    while walker.name != ".git" and walker != walker.parent:
                        walker = walker.parent
                    if walker.name == ".git":
                        return walker.parent
            return None
        if git_marker.is_dir():
            return None
        current = current.parent
    return None


def find_project_root() -> Path:
    """Find project root. Resolves git worktrees to the main repo root.

    Priority:
    1. CLAUDE_PROJECT_DIR env var (set by Claude Code) — resolved through worktree if needed
    2. Walk up from CWD looking for .git, resolving worktrees transparently
    """
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        p = Path(env_dir)
        main = find_main_repo_from_worktree(p)
        return main if main is not None else p
    cwd = Path.cwd()
    main = find_main_repo_from_worktree(cwd)
    if main is not None:
        return main
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").is_dir():
            return parent
    return cwd


def _workflow_file_exists(root: Path, name: str) -> bool:
    """Return True if workflows/<name>.json exists under the project root."""
    try:
        return (root / ".claude" / "workflows" / f"{name}.json").exists()
    except OSError:
        return False


def resolve_active_workflow() -> "tuple[str, str]":
    """Return (name, source). source ∈ {'file', 'settings', 'env', 'none'}.

    Single source of truth for active-workflow name resolution. Both
    workflow._read_active() and workflow.read_active_workflow_fast() delegate here
    instead of duplicating the priority chain — keep this function authoritative
    and change resolution behaviour ONLY here.

    Worktree-aware priority — prevents cross-session contamination:

    In a worktree session:
      1. Worktree-local active_workflow file ({worktree_root}/.claude/active_workflow)
         Written by workflow.py start/switch within THIS worktree. Never shared.
      2. Worktree-local settings.local.json env section (written live by workflow.py
         start/switch — not frozen, reflects the latest call in this session).
         Validated: skipped if workflows/<name>.json does not exist.
      (The frozen OPENSPEC_ACTIVE_WORKFLOW env var is NOT a source here — see below.)
      (Shared {project_root}/.claude/active_workflow is SKIPPED — it might belong to
      a parallel session and would contaminate this session's context.)

      The env var (frozen at session start by Claude Code) is deliberately NOT used
      as a positive source inside a worktree (Issue #58). All workflow JSONs live in
      the SHARED {main_repo}/.claude/workflows/ dir, so a frozen value pointing at a
      parallel session's workflow would pass a mere "file exists" check and hijack
      this session's identity (false-block, symmetric false-pass risk). The documented
      flow (workflow.py start) always writes an active workflow worktree-locally
      (priorities 1 and 2), so dropping the env fallback loses nothing legitimate: if
      both worktree-local sources are empty, this worktree has no active workflow.

    In a main repo session (not a worktree):
      1. Shared active_workflow file ({project_root}/.claude/active_workflow)
      2. {project_root}/.claude/settings.local.json env section
      3. OPENSPEC_ACTIVE_WORKFLOW env var (frozen at session start)
    """
    root = find_project_root()
    worktree_root = _find_worktree_root()

    if worktree_root is not None:
        # 1. Worktree-local active_workflow file (written by workflow.py start/switch)
        try:
            active_file = worktree_root / ".claude" / "active_workflow"
            if active_file.exists():
                name = active_file.read_text().strip()
                if name:
                    return name, "file"
        except OSError:
            pass
        # 2. Worktree-local settings.local.json (updated live, not frozen like env)
        try:
            settings_path = worktree_root / ".claude" / "settings.local.json"
            if settings_path.exists():
                settings = json.loads(settings_path.read_text())
                name = (settings.get("env") or {}).get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
                if name and _workflow_file_exists(root, name):
                    return name, "settings"
        except (OSError, json.JSONDecodeError, KeyError):
            pass
        # No worktree-local source → no active workflow for THIS worktree.
        # The frozen env var is intentionally NOT consulted here (Issue #58): it may
        # carry a parallel session's workflow name, which would pass a shared-dir
        # "file exists" check and hijack this session.
        return "", "none"

    # Main repo session: existing priority chain
    try:
        active_file = root / ".claude" / "active_workflow"
        if active_file.exists():
            name = active_file.read_text().strip()
            if name:
                return name, "file"
    except OSError:
        pass
    try:
        settings_path = root / ".claude" / "settings.local.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
            name = (settings.get("env") or {}).get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
            if name:
                return name, "settings"
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    name = os.environ.get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
    if name:
        return name, "env"
    return "", "none"


def find_worktree_root() -> "Path | None":
    """Root of the working tree the session actually works in, or None.

    Counterpart to find_project_root(): that one resolves worktrees to the MAIN
    repo (correct for shared state — workflow JSONs, artifact registry, all of
    which must live in one place regardless of worktree). This one deliberately
    does NOT resolve, and is the right root for MEASUREMENTS against the working
    tree (`git diff`, `git status`, LoC, scope).

    Mixing the two is a silent failure mode: measuring the main repo from inside
    a worktree reports the delta of a different, usually clean tree — the limit
    then never triggers (Issue #96, fail-open) and, in the other direction,
    attributes a foreign delta to the session's own work (false alarm).

    Returns None when the session runs in the main repo; callers should fall
    back to find_project_root() then.
    """
    return _find_worktree_root()


def _find_worktree_root() -> "Path | None":
    """If CWD is inside a git worktree, return the worktree root (dir with .git FILE).

    Returns None if in the main repo (where .git is a directory, not a file).
    Mirrors workflow._worktree_root_if_any() — kept local to avoid circular imports.

    Implementation behind find_worktree_root(); kept as the patch point that
    existing tests inject (tests/test_workflow_resolution_consolidation.py et al.).
    """
    current = Path.cwd()
    while current != current.parent:
        git_marker = current / ".git"
        if git_marker.is_file():
            return current
        if git_marker.is_dir():
            return None
        current = current.parent
    return None


def get_active_workflow_name() -> str:
    """Unverändertes Verhalten — delegiert an resolve_active_workflow()."""
    return resolve_active_workflow()[0]


def gate_diagnostics(workflow: "dict | None" = None, **extra) -> str:
    """Bracketed diagnostics for block messages.

    Beispiel: '[wf=feature-login (env) | token=keins | phase=phase6_implement]'
    Fail-safe: jede Teilinfo, die nicht ermittelbar ist, wird zu '?' —
    der Builder wirft nie.
    """
    try:
        name, source = resolve_active_workflow()
    except Exception:
        name, source = "?", "?"
    parts = [f"wf={name or '—'} ({source})"]
    try:
        from override_token import has_valid_token
        parts.append("token=gültig" if has_valid_token(name or None) else "token=keins")
    except Exception:
        parts.append("token=?")
    try:
        if workflow:
            parts.append(f"phase={workflow.get('current_phase', '?')}")
    except Exception:
        parts.append("phase=?")
    try:
        for key, value in extra.items():
            parts.append(f"{key}={value}")
    except Exception:
        pass
    return "[" + " | ".join(parts) + "]"


def find_plugin_root() -> Path:
    """Plugin-Root: wo die Hook-Skripte liegen."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if env:
        return Path(env)
    # Fallback: hook_utils.py liegt in plugin_root/core/hooks/
    candidate = Path(__file__).parent.parent.parent
    if (candidate / ".claude-plugin" / "plugin.json").exists():
        return candidate
    return candidate


def is_module_enabled(module_id: str) -> bool:
    """Check if a plugin module is enabled via OPENSPEC_ENABLED_MODULES env var."""
    enabled = os.environ.get("OPENSPEC_ENABLED_MODULES", "")
    return module_id in [m.strip() for m in enabled.split(",") if m.strip()]


def is_test_file(file_path: str) -> bool:
    """Check if a file is a test file."""
    test_patterns = [
        "test_", "_test.", ".test.", "tests/", "spec/", "_spec.",
        "Test.", "Tests/", "UITests/",
    ]
    return any(pattern in file_path for pattern in test_patterns)
