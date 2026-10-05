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
import subprocess
import sys
from datetime import datetime, timezone
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
# `--exec-path` gehoert NICHT dazu: laut git(1) `--exec-path[=<path>]`, ein Wert
# nur mit `=` — sonst wuerde `git --exec-path commit` den Unterbefehl schlucken.
_GIT_OPTS_WITH_VALUE = {
    "-c", "-C", "--git-dir", "--work-tree", "--attr-source",
    "--namespace", "--super-prefix", "--config-env",
}
# Shell-Optionen vor `-c`, deren Wert ein eigenes Token ist (#298).
_SHELL_OPTS_WITH_VALUE = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}
# Wrapper, die vor `git` stehen duerfen, ohne die Bedeutung zu aendern.
_GIT_COMMAND_PREFIXES = {"sudo", "env", "nice", "command", "time", "nohup"}
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _looks_like_git(token: str) -> bool:
    return token == "git" or token.endswith("/git")


def _repo_aliases() -> "dict[str, str]":
    """Aliase aus der git-Konfiguration des Aufrufverzeichnisses (#281).

    Eine einzige Abfrage (`git config --get-regexp ^alias\\.`), je Prozess
    einmal. Fail-open: jeder Fehler (kein git, kein Repo, Timeout) ergibt {}.
    """
    global _REPO_ALIASES
    if _REPO_ALIASES is None:
        _REPO_ALIASES = {}
        try:
            out = subprocess.run(["git", "config", "--get-regexp", r"^alias\."],
                                 capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                key, _, value = line.partition(" ")
                _REPO_ALIASES[key[len("alias."):].lower()] = value
        except (OSError, subprocess.SubprocessError):
            pass
    return _REPO_ALIASES


_REPO_ALIASES: "dict[str, str] | None" = None


def _inline_aliases(tokens: "list[str]", i: int) -> "dict[str, str]":
    """`-c alias.<name>=<wert>` zwischen `git` und Unterbefehl (#281)."""
    found: "dict[str, str]" = {}
    while i + 1 < len(tokens) and tokens[i].startswith("-"):
        if tokens[i] == "-c" and tokens[i + 1].lower().startswith("alias."):
            key, _, value = tokens[i + 1].partition("=")
            found[key[len("alias."):].lower()] = value
        i += 2 if tokens[i] in _GIT_OPTS_WITH_VALUE else 1
    return found


def _config_env_aliases(tokens: "list[str]", table: "dict[str, str]") -> "dict[str, str]":
    """`--config-env=alias.<name>=<VAR>` ab einem `git`-Token (#324).

    Wert aus der Zeilen-Tabelle, sonst aus `os.environ`; unauffindbar gilt
    `commit` — dann ist genau dieser Aliasname commit-verdaechtig.
    """
    found: "dict[str, str]" = {}
    after_git = False
    for i, tok in enumerate(tokens):
        after_git = after_git or _looks_like_git(tok)
        if not after_git:
            continue
        if tok.startswith("--config-env="):
            spec = tok[len("--config-env="):]
        elif tok == "--config-env" and i + 1 < len(tokens):
            spec = tokens[i + 1]
        else:
            continue
        key, sep, var = spec.rpartition("=")
        if sep and var and key.lower().startswith("alias."):
            found[key[len("alias."):].lower()] = table.get(var, os.environ.get(var, "commit"))
    return found


def _command_env_aliases(segments: "list[list[str]]") -> "dict[str, str]":
    """Aliase aus git-Umgebungsvariablen, command-weit ueber alle Segmente (#324).

    `GIT_CONFIG_COUNT`/`KEY_<n>`/`VALUE_<n>`, `GIT_CONFIG_PARAMETERS` und
    `--config-env`. Bewusst grosszuegig: jede `VAR=wert`-Zuweisung der Zeile
    zaehlt (Praefix, `env`, `export`, anderes Segment). Fail-open: kaputte
    Eintraege werden ignoriert, nie eine Exception.
    """
    table: "dict[str, str]" = {}
    for tok in (t for seg in segments for t in seg):
        if _ENV_ASSIGN_RE.match(tok):
            name, _, value = tok.partition("=")
            table[name] = value
    found: "dict[str, str]" = {}
    count = table.get("GIT_CONFIG_COUNT", "")
    numeric = count.isascii() and count.isdigit()  # "²" ist isdigit, aber kein int (F001)
    for n in range(min(int(count), len(table)) if numeric else 0):
        key, value = table.get(f"GIT_CONFIG_KEY_{n}"), table.get(f"GIT_CONFIG_VALUE_{n}")
        if key is not None and value is not None and key.lower().startswith("alias."):
            found[key[len("alias."):].lower()] = value
    try:
        params = shlex.split(table.get("GIT_CONFIG_PARAMETERS", ""))
    except ValueError:
        params = []
    for param in params:
        key, sep, value = param.partition("=")
        if sep and key.lower().startswith("alias."):
            found[key[len("alias."):].lower()] = value
    for seg in segments:
        found.update(_config_env_aliases(seg, table))
    return found


def _resolve_alias(sub: str, inline: "dict[str, str]",
                   env_aliases: "dict[str, str] | None" = None) -> str:
    """Alias-Kette zum echten Unterbefehl aufloesen (#281).

    Ergebnis ist das erste Wort des Alias-Werts; ein Shell-Alias (`!...`) bleibt
    als `!<rumpf>` stehen — der Aufrufer behandelt ihn als nicht-reines git und
    zerlegt den Rumpf als eigenes Kommando. Eingebaute Kommandos gewinnen in git
    immer gegen gleichnamige Aliase; `commit` ist daher nie ein Alias-Ziel.
    """
    aliases = {**_repo_aliases(), **(env_aliases or {}), **inline}  # Repo < Env < -c (#324)
    for _ in range(5):
        value = aliases.get(sub.lower()) if sub != "commit" else None
        if value is None:
            return sub
        if value.startswith("!"):
            return value
        try:
            words = shlex.split(value)
        except ValueError:
            return sub
        if not words:
            return sub
        sub = words[0]
    return sub


def _git_subcommand_after(tokens: "list[str]", i: int,
                          env_aliases: "dict[str, str] | None" = None) -> "str | None":
    """Erstes Nicht-Options-Token nach einem `git`-Token (= der Unterbefehl).

    Ein Alias wird zum echten Unterbefehl aufgeloest (#281).
    """
    start = i
    while i < len(tokens):
        tok = tokens[i]
        if _is_git_separator(tok):
            return None  # Kommando endet, bevor ein Unterbefehl kam
        if _is_git_redirect(tok):
            i += 2  # Umleitung + ihr Ziel (`>/dev/null`, `>& 1`) (#304)
            continue
        if tok.isdigit() and i + 1 < len(tokens) and _is_git_redirect(tokens[i + 1]):
            i += 1  # Ziffern-Praefix einer Umleitung (`2>&1` -> `2`, `>&`, `1`)
            continue
        if tok in _GIT_OPTS_WITH_VALUE:
            i += 2  # Vor-Option + ihr Wert (`-C /pfad`, `-c k=v`)
            continue
        if tok.startswith("-"):
            i += 1  # `--no-pager`, `--git-dir=...`, `-p`, ...
            continue
        return _resolve_alias(tok, _inline_aliases(tokens, start), env_aliases)
    return None


# Konfigurationsschluessel, die git beim Aufruf fremden Code ausfuehren lassen (#297).
_GIT_CODE_CONFIG_KEYS = (
    "core.pager", "core.editor", "core.sshcommand", "core.fsmonitor", "core.hookspath",
    "core.askpass", "sequence.editor", "diff.external", "credential.helper",
    "gpg.program", "pager.",
)
# Unterbefehle, die ein Kommando ausfuehren (#297).
_GIT_CODE_SUBCOMMANDS = {"difftool", "mergetool", "filter-branch"}
_GIT_CODE_SUBCOMMAND_PAIRS = {("bisect", "run"), ("submodule", "foreach")}


def _git_runs_foreign_code(tokens: "list[str]", i: int,
                           env_aliases: "dict[str, str] | None" = None) -> bool:
    """Fuehrt dieser git-Aufruf (Unterbefehl-Suche ab Token i) fremden Code aus? (#297)

    Gefaehrliche `-c`-Schluessel, Kommando-Unterbefehle, `rebase --exec` und
    Shell-Aliase. Dann gilt der Aufruf nicht als „reines git“ — Marker-Schutz
    und Secrets-Guard laufen wieder; zusaetzlich blockt dadurch nichts.
    """
    j = i
    while j + 1 < len(tokens) and tokens[j].startswith("-"):
        if tokens[j] == "-c" and tokens[j + 1].lower().startswith(_GIT_CODE_CONFIG_KEYS):
            return True
        j += 2 if tokens[j] in _GIT_OPTS_WITH_VALUE else 1
    sub = _git_subcommand_after(tokens, i, env_aliases)
    if sub is None:
        return False
    if sub.startswith("!") or sub in _GIT_CODE_SUBCOMMANDS:
        return True
    rest = [t for t in tokens[i:] if not _is_git_separator(t)]
    rest = rest[rest.index(sub) + 1:] if sub in rest else []
    if rest and (sub, rest[0]) in _GIT_CODE_SUBCOMMAND_PAIRS:
        return True
    return sub == "rebase" and any(t in ("-x", "--exec") or t.startswith("--exec=") for t in rest)


def git_runs_foreign_code(command: str) -> bool:
    """Fuehrt irgendein git-Aufruf im Kommando fremden Code aus? (#297)"""
    segments = _git_segments(command) or []
    env_aliases = _command_env_aliases(segments)
    return any(
        _git_runs_foreign_code(seg, i + 1, env_aliases)
        for seg in segments
        for i, tok in enumerate(seg) if _looks_like_git(tok)
    )


def _git_subcommand_of_segment(tokens: "list[str]",
                               env_aliases: "dict[str, str] | None" = None) -> "str | None":
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
    if _git_runs_foreign_code(tokens, i + 1, env_aliases):
        return None  # fremder Code: nicht „reines git“ (#297)
    return _git_subcommand_after(tokens, i + 1, env_aliases)


def _git_subcommands_in_segment(tokens: "list[str]",
                                env_aliases: "dict[str, str] | None" = None) -> "list[str]":
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
            sub = _git_subcommand_after(tokens, i + 1, env_aliases)
            if sub and sub.startswith("!"):
                out.extend(git_subcommands(sub[1:], 1))  # Shell-Alias: Rumpf zerlegen
            elif sub:
                out.append(sub)
    return out


def _shell_c_argument(segment: "list[str]", j: int) -> "str | None":
    """Kommando-Token hinter `-c` einer Shell, Optionen davor uebersprungen (#298, #318).

    `-c` darf in einem Buendel stecken (`-lc`, `-ec`). Werte von `-o`/`-O`/
    `--rcfile`/`--init-file` (auch am Ende eines Buendels: `-eo pipefail`) sind
    kein Kommando, Umleitungen (`2>&1`, `>/dev/null`) ebenfalls nicht. Wie in
    bash ist das Kommando das erste Nicht-Options-Token NACH `-c` (`-c -l "…"`).
    Ein Nicht-Options-Token ohne vorheriges `-c` ist eine Skriptdatei: dann
    gibt es kein `-c`.
    """
    seen_c = False
    while j < len(segment):
        tok = segment[j]
        if _is_git_redirect(tok):
            j += 2  # Umleitung + Ziel
        elif tok.isdigit() and j + 1 < len(segment) and _is_git_redirect(segment[j + 1]):
            j += 1  # Ziffern-Praefix (`2>&1`)
        elif tok in _SHELL_OPTS_WITH_VALUE:
            j += 2
        elif tok.startswith("--"):
            j += 1  # `--login`, `--noprofile`, `--norc`, `--posix`, …
        elif tok.startswith(("-", "+")) and len(tok) > 1:
            seen_c |= tok[0] == "-" and "c" in tok[1:]
            j += 2 if tok[-1] in "oO" and "c" not in tok else 1  # `-eo pipefail`
        else:
            return tok if seen_c else None
    return None


def _git_nested_subcommands(segment: "list[str]", depth: int) -> "list[str]":
    """Unterbefehle aus verschachtelten Shells (`sh -c "…"`, `eval "…"`)."""
    if depth >= 2:
        return []
    found: "list[str]" = []
    for i, tok in enumerate(segment):
        base = tok.rsplit("/", 1)[-1]
        if _GIT_SHELL_BINARY_RE.match(base):
            nested = _shell_c_argument(segment, i + 1)
            if nested is not None:
                found.extend(git_subcommands(nested, depth + 1))
        elif base == "eval":
            for nested in segment[i + 1:]:
                found.extend(git_subcommands(nested, depth + 1))
    return found


# Zeichen, nach denen ein `#` am Wortanfang steht (#319).
# `)` fehlt bewusst: nach `$(..)` beginnt kein neues Wort, `$(..)#x` ist Text.
_COMMENT_WORD_START = " \t\r\n;&|("


def _strip_shell_comments(command: str) -> str:
    """Shell-Kommentare entfernen, quote- und escape-bewusst (#319).

    Ein `#` beginnt nur dann einen Kommentar, wenn es ausserhalb von `'…'`,
    `"…"` und `$'…'` steht, nicht durch `\\` maskiert ist und am Wortanfang
    steht (Textanfang oder nach Leerraum/Zeilenumbruch/`; & | (`). Der
    Kommentar reicht bis zum Zeilenende, der Zeilenumbruch bleibt (er trennt
    Befehle). `a#b`, `$#`, `${#x}`, `--grep=#1431`, `-m "x # y"` bleiben.
    Endet der Scan in einem offenen Quote, kommt der Befehl UNVERAENDERT
    zurueck (fail-open, Verhalten wie vorher).
    """
    out: "list[str]" = []
    quote = None  # None, "'", '"' oder "$'"
    word_start = True
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote is not None:
            if quote != "'" and ch == "\\":
                out.append(command[i:i + 2])
                i += 2
                continue
            if ch == quote[-1]:
                quote = None
            out.append(ch)
            i += 1
            continue
        if ch == "#" and word_start:
            end = command.find("\n", i)
            i = n if end == -1 else end
            continue
        cont = next((c for c in _GIT_LINE_CONTINUATIONS if command.startswith(c, i)), "")
        if cont:  # Zeilenfortsetzung: aendert den Wortanfang nicht
            out.append(cont)
            i += len(cont)
            continue
        step = 2 if ch == "\\" or command.startswith("$'", i) else 1
        if step == 2 and ch == "$":
            quote = "$'"
        elif ch in "'\"":
            quote = ch
        word_start = step == 1 and ch in _COMMENT_WORD_START
        out.append(command[i:i + step])
        i += step
    return command if quote is not None else "".join(out)


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
    # Erst Kommentare (enden am Zeilenende, auch nach `\`), dann Fortsetzungen.
    command = _strip_shell_comments(command)
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


def _is_git_redirect(token: str) -> bool:
    """Umleitungs-Token: nur aus `<>&`, mit mindestens einem `<` oder `>`.

    Deckt `>`, `>>`, `<`, `>&`, `&>`, `&>>` und `>|` (#318). Ein einzelnes `&`
    (Hintergrund), `&&`, `|&` und `<(`/`>(` sind KEINE Umleitung.
    """
    return (bool(token) and all(ch in "<>&|" for ch in token)
            and ("<" in token or ">" in token))


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
    if _is_git_redirect(token):
        return False  # `>&`, `&>`, `&>>` sind Umleitungen, keine Trenner (#304)
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
    env_aliases = _command_env_aliases(segments)
    found: "list[str]" = []
    for segment in segments:
        found.extend(_git_subcommands_in_segment(segment, env_aliases))
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
    env_aliases = _command_env_aliases(segments)
    return [s for s in (_git_subcommand_of_segment(seg, env_aliases) for seg in segments) if s]


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


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    """Entfernt ANSI-Steuercodes (Farben, Cursor) aus einer Testausgabe (#275).

    Einzige ANSI-Entfernung im Framework: Gates wenden ihre Textmuster erst
    auf den bereinigten Text an, sonst verdeckt z.B. '\\x1b[31mFAIL' das Wort.
    """
    return _ANSI_RE.sub("", text)


def setup_path():
    """Add the hooks directory to sys.path for same-directory imports.
    Call this BEFORE importing config_loader or other hook modules."""
    hooks_dir = str(Path(__file__).parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


# Zuletzt ueber stdin gelieferte Hook-Eingabe (tool_name, tool_input). Claude Code uebergibt sie
# per stdin, nicht per Umgebungsvariable; ohne diesen Zwischenspeicher kennt block() sie nicht und
# das Gate-Event-Log bleibt ohne Ausschnitt (#328).
_STDIN_PAYLOAD: dict = {}


def get_tool_input() -> dict:
    """Parse tool input from CLAUDE_TOOL_INPUT env var or stdin.
    Returns parsed dict or empty dict on failure."""
    tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")

    if not tool_input:
        try:
            data = json.load(sys.stdin)
            if isinstance(data, dict):
                _STDIN_PAYLOAD.clear()
                _STDIN_PAYLOAD.update(data)
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


def block(message: str, *, hook: "str | None" = None, tool: "str | None" = None,
          command_excerpt: "str | None" = None):
    """Block the operation with an error message and exit.

    Also logs a gate event (Issue #181) before exiting — best effort, never
    raises, never changes the exit code. Existing callers need no changes:
    `hook` defaults to the calling script's filename, `tool`/`command_excerpt`
    default to the CLAUDE_TOOL_NAME/CLAUDE_TOOL_INPUT env vars that every hook
    already receives. Pass them explicitly only when a hook has better
    information at hand (e.g. a file_path it already extracted) or, as in
    secret_egress_guard.py, to deliberately withhold a command_excerpt that
    would otherwise carry the very secret the block is preventing from leaking.
    """
    try:
        _log_gate_event_for_block(message, hook, tool, command_excerpt)
    except Exception:
        pass
    print(message, file=sys.stderr)
    sys.exit(2)


# --- Gate-Event-Log (Issue #181) --------------------------------------------
# Bisher waren Blockaden nur im Transcript sichtbar — kein Zaehler, kein Weg
# von einem Fehlalarm zum Regressionstest. Diese Funktion beobachtet nur: sie
# schreibt eine JSON-Zeile pro Blockade nach .claude/gate-events.jsonl und
# entscheidet nichts. Keine Rotation, keine Auswertung hier — das ist bewusst
# ausgeklammert, bis genug Daten vorliegen, um zu wissen, was gebraucht wird.
#
# Sicherheitsregel: log_gate_event() darf NIE eine Ausnahme nach aussen
# durchlassen und NIE den Exit-Code eines Gates veraendern. Ein Logger, der
# ein Gate zum Absturz bringt, waere der teuerste Fehler, den dieses Ticket
# machen koennte — schlimmer als gar kein Log.
GATE_EVENTS_RELATIVE_PATH = Path(".claude") / "gate-events.jsonl"

_EXCERPT_LIMIT = 200

# Findet die erste Stelle, an der ein bekanntes Geheimnis-Schluesselwort direkt
# von einem Zuweisungs-/Trenner-Zeichen gefolgt wird ("API_KEY=", "password:",
# "Authorization:"). Ab dort wird der GESAMTE Rest des Ausschnitts verworfen —
# nicht nur das naechste Token — weil Formen wie "Authorization: Bearer <tok>"
# sonst nur das Wort "Bearer" maskieren wuerden und das eigentliche Token
# dahinter stehen liesse. Bewusst grosszuegig statt praezise: ein zu kurzer
# Ausschnitt ist ein akzeptabler Verlust, ein geleaktes Geheimnis nicht.
# Erkennt keine geheimnisartigen Werte OHNE Schluesselwort-Kontext (z.B. ein
# nackt eingefuegtes Token) — das ist eine bekannte Grenze, kein Versprechen:
# dieses Log beobachtet bereits blockierte Vorgaenge, es ist keine zweite
# Verteidigungslinie fuer Secrets. Die Guards selbst bleiben das.
_SECRET_KEYWORD_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?key|secret|password|passwd|pwd|token"
    r"|authorization|bearer|private[_.]?key)\w*\s*[:=]"
)


def mask_and_truncate_excerpt(text: "str | None") -> str:
    """Best-effort Maskierung + Laengenbegrenzung fuer command_excerpt.

    Oeffentlich (nicht nur intern), weil aufrufende Hooks damit auch eigene
    Roh-Werte vor der Uebergabe pruefen koennen, statt der Funktion blind zu
    vertrauen.
    """
    if not text:
        return ""
    text = str(text)
    match = _SECRET_KEYWORD_RE.search(text)
    if match:
        text = text[:match.end()] + "***"
    if len(text) > _EXCERPT_LIMIT:
        text = text[:_EXCERPT_LIMIT] + "…"
    return text


_FRAMEWORK_VERSION_CACHE: "list[str]" = []


def _framework_version() -> str:
    """Version aus .claude-plugin/plugin.json neben dem Hook-Ordner; leer, wenn nicht ermittelbar
    (z. B. Copy-Modus). Damit koennen Auswertungen Fixes ueber die Zeit einer Version zuordnen (#328)."""
    if not _FRAMEWORK_VERSION_CACHE:
        version = ""
        try:
            manifest = Path(__file__).resolve().parent.parent.parent / ".claude-plugin" / "plugin.json"
            version = str(json.loads(manifest.read_text(encoding="utf-8")).get("version", ""))
        except Exception:
            version = ""
        _FRAMEWORK_VERSION_CACHE.append(version)
    return _FRAMEWORK_VERSION_CACHE[0]


def _gate_events_root() -> Path:
    """Wurzel fuer das Gate-Event-Log: der eigene Worktree (#280) — aber nur,
    wenn er zum Projekt gehoert (#295).

    Laeuft ein Hook mit `CLAUDE_PROJECT_DIR` auf ein fremdes Projekt (jeder
    Test mit tmp_path-Projekt), waehrend die CWD in einem Worktree dieses
    Repositories steht, gewann bisher der Worktree: Testlaeufe schrieben
    Blockaden ins echte Log und verfaelschten die Auswertung (gate_audit).
    """
    project = find_project_root()
    worktree = find_worktree_root()
    if worktree is not None:
        try:
            main = find_main_repo_from_worktree(worktree)
            if main is not None:
                main_r, project_r = main.resolve(), project.resolve()
                # Projekt = Haupt-Repo oder ein Unterordner davon
                if project_r == main_r or main_r in project_r.parents:
                    return worktree
        except OSError:
            pass
    return project


def log_gate_event(hook: str, tool: str, reason: str, command_excerpt: str = "") -> None:
    """Eine Blockade als JSON-Zeile anhaengen. Schlaegt niemals sichtbar fehl.

    Schema pro Zeile: ts (UTC ISO8601), hook, tool, reason (erste Zeile,
    gekappt), command_excerpt (maskiert + gekappt), session_id (leer wenn
    nicht ermittelbar), framework_version (leer wenn nicht ermittelbar).
    """
    try:
        path = _gate_events_root() / GATE_EVENTS_RELATIVE_PATH
        reason_line = (reason or "").strip().splitlines()[0] if reason else ""
        event = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "hook": hook or "",
            "tool": tool or "",
            "reason": reason_line[:300],
            "command_excerpt": mask_and_truncate_excerpt(command_excerpt),
            "session_id": os.environ.get("CLAUDE_CODE_SESSION_ID", ""),
            "framework_version": _framework_version(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _log_gate_event_for_block(message: str, hook: "str | None", tool: "str | None",
                              command_excerpt: "str | None") -> None:
    """Fehlende hook/tool/command_excerpt aus Umgebung/Aufrufkontext ableiten.

    Laesst bestehende block()-Aufrufer unveraendert: sie liefern nur die
    Nachricht, die drei Zusatzfelder werden hier best-effort ergaenzt.
    """
    if hook is None:
        try:
            hook = Path(sys.argv[0]).stem
        except Exception:
            hook = ""
    if tool is None:
        tool = (os.environ.get("CLAUDE_TOOL_NAME", "") or os.environ.get("CLAUDE_TOOL", "")
                or str(_STDIN_PAYLOAD.get("tool_name") or ""))
    if command_excerpt is None:
        command_excerpt = ""
        ti_raw = os.environ.get("CLAUDE_TOOL_INPUT", "")
        try:
            ti = json.loads(ti_raw) if ti_raw else _STDIN_PAYLOAD.get("tool_input")
            if isinstance(ti, dict):
                command_excerpt = (
                    ti.get("command") or ti.get("file_path") or ti.get("content", "")
                )
        except Exception:
            command_excerpt = ""
    log_gate_event(hook, tool, message, command_excerpt)


def allow():
    """Allow the operation and exit."""
    sys.exit(0)


# --- Geteilte Secrets-Muster (Issue #75) ---
# EINE Quelle fuer bash_gate.py UND secrets_guard.py. Vorher fuehrte bash_gate
# die aelteren Breitmuster `_key`/`_secret` (Substring ohne Anker), waehrend
# secrets_guard bereits die geschaerften Formen hatte — der Drift blockierte
# Befehle wegen blosser Dateinamen (tests/test_secret_egress_guard.py).
SECRETS_SENSITIVE_PATTERNS = [
    # `\b` nach `env`: trifft `.env`, `.env.local`, `.envrc`, `config/.env`,
    # aber NICHT SwiftUI-Modifier wie `.environment(...)`/`.environmentObject(...)`,
    # die in jeder SwiftUI-Datei stehen und grep/sed darauf sonst blockieren.
    r"\.env(rc)?\b",
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


# Heredoc-Body-Stripping (Issues #64/#75, gehaertet in #357): shlex kennt keine
# Heredoc-Syntax, darum landeten Body-Woerter (Doku-Freitext, Commit-Messages)
# als normale Tokens in den Datei-/Kommando-Scans. Ein Heredoc-Body ist DATEN,
# kein Kommando — aber NUR, wenn das eindeutig feststeht.
#
# Sicherheitsmodell (#357; Differenztest gegen bash als Orakel):
# 1. Ein zusammenhaengender Scan des GANZEN Befehls (Quotes ueber Zeilen,
#    Kommentare nur am Wortanfang, $(...) vs. Subshell) muss jeden Oeffner
#    zweifelsfrei finden. Bei jeder Unsicherheit — Backtick, Arithmetik,
#    ${...}, $'...', [[ ]], case, Zeilenfortsetzung, CR, offenes Heredoc,
#    offene Quotes, unbekannte Endwort-Form, Body ueber Verschachtelungs-
#    ebenen hinweg, Body-Zeile, die mit dem Endwort beginnt — bleibt der
#    Befehl UNVERAENDERT (fail-closed).
# 2. POSITIVLISTE statt Negativliste: Entfernt wird ein Body nur, wenn das
#    Kommando, das ihn liest, ein reiner Daten-Konsument ist
#    (_HEREDOC_SAFE_CONSUMERS), und nur ausserhalb von Subshell und $(...):
#    bash 3.2 beendet eine Ersetzung schon an einer ")" im Body (#365).
#    Jede Pipe im uebrigen Befehl muss ebenfalls in einen solchen Konsumenten
#    fuehren. Eine Liste "gefaehrlicher" Programme ist nie vollstaendig
#    ($SHELL, sed e, s\h ...).
# 3. Zusaetzlich (Verteidigung in der Tiefe): Interpreter-Namen, ./ und
#    chmod im uebrigen Befehl, Umdefinitionen gelisteter Konsumenten
#    (Funktion, Alias, git -c), ungequotetes Endwort mit $ oder ` im Body.
# Bekannte Grenze: Schreibt ein Heredoc eine Datei, die ein spaeterer Befehl
# ausfuehrt (make, Git-Hook, Testlauf), sieht der Guard den Inhalt nicht. Das
# geht ebenso in zwei getrennten Aufrufen und ist fuer keinen Text-Guard
# erkennbar; das Schreibziel selbst bleibt auf der Oeffner-Zeile sichtbar.
_HEREDOC_MARKER_RE = re.compile(
    r"<<(-?)[ \t]*(?:'([A-Za-z_][A-Za-z0-9_]*)'|\"([A-Za-z_][A-Za-z0-9_]*)\"|"
    r"\\([A-Za-z_][A-Za-z0-9_]*)|([A-Za-z_][A-Za-z0-9_]*))(?=$|[\s;&|)<>])"
)
_HEREDOC_INTERPRETER_RE = re.compile(
    r"\b(python[0-9.]*|node|nodejs|deno|bun|perl|ruby|php|lua|tclsh|"
    r"(?:ba|z|da|k|c|tc|fi|mk|a)?sh|busybox|source|eval|exec|xargs|ssh|su|sudo|"
    r"osascript|powershell|pwsh|chmod)\b|(?:^|[;&|({\s])\.\.?/|(?:^|[;&|({\s])\.\s"
)
# Kommandos, die einen Heredoc nur als Daten lesen (kein Ausfuehren).
_HEREDOC_SAFE_CONSUMERS = frozenset({
    "cat", "tee", "git", "gh", "wc", "grep", "head", "tail", "sort", "uniq",
    "tr", "cut", "column", "diff", "cmp", "base64", "md5sum", "sha256sum",
    "shasum", "jq",
})
# Umdefinitionen und Konfiguration, die einen gelisteten Konsumenten in einen
# Ausfuehrer verwandeln (Funktion `cat(){ bash; }`, Alias, `git -c alias.x=!sh`).
_HEREDOC_REDEFINE_RE = re.compile(
    r"\b[A-Za-z_][\w.-]*\s*\(\s*\)|\b(?:function|alias|shopt|enable|hash)\b|"
    r"\bgit\b[^\n;&|]*\s(?:-c\b|--config-env\b|--exec-path\b)"
)


class _HeredocUnsure(Exception):
    """Der Befehl laesst sich nicht zweifelsfrei zerlegen — nichts entfernen."""


def _segment_command_word(text: str) -> "str | None":
    """Erstes Wort des letzten einfachen Kommandos in `text` (ohne Zuweisungen).

    None bei leerem Segment, Redirect/Variable/Quote/Escape im Befehlswort.
    """
    seg = re.split(r"\|\||&&|[;&|(\n]", text)[-1]
    for tok in seg.split():
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
            continue  # Zuweisung vor dem Befehl
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", tok):
            return None  # $SHELL, "bash", s\h, >f, ./x ...
        return tok
    return None


def _heredoc_bodies(command: str) -> "list[tuple[int, int, bool]]":
    """(start, end, strippable) je Heredoc-Body; wirft _HeredocUnsure.

    start/end umfassen Body UND Terminator-Zeile (inkl. Zeilenumbruch).
    """
    n = len(command)
    stack = ["code"]          # "code" | "sub" (Subshell) | "subst" ($(...)) | "dq"
    pending: "list[tuple[str, bool, bool, bool, int]]" = []  # marker, dash, quoted, ok, depth
    bodies: "list[tuple[int, int, bool]]" = []
    word_start = True
    i = 0
    while i < n:
        c = command[i]
        top = stack[-1]
        if c == "\n":
            if pending:
                if top == "dq" or any(d != len(stack) for *_, d in pending):
                    raise _HeredocUnsure  # Body-Beginn in Quotes/anderer Ebene
                i += 1
                for marker, dash, quoted, ok, _d in pending:
                    start = i
                    while True:
                        if i >= n:
                            raise _HeredocUnsure  # nie geschlossen
                        j = command.find("\n", i)
                        j = n if j < 0 else j
                        line = command[i:j]
                        i = j + 1 if j < n else n
                        cand = line.lstrip("\t") if dash else line
                        if cand == marker:
                            break
                        if cand.startswith(marker):
                            raise _HeredocUnsure  # z.B. "E)" in $(...) (bash 5.2)
                    body = command[start:i]
                    if not quoted and ("$" in body or "`" in body):
                        ok = False  # ungequotet: die Shell expandiert den Body
                    bodies.append((start, i, ok))
                pending = []
                word_start = True
                continue
            i += 1
            word_start = True
            continue
        if c == "`":
            raise _HeredocUnsure
        if c == "\\":
            if i + 1 < n and command[i + 1] == "\n":
                raise _HeredocUnsure  # Zeilenfortsetzung
            i += 2
            word_start = False
            continue
        if c == "$" and i + 1 < n:
            nxt = command[i + 1]
            if nxt == "(":
                if command.startswith("$((", i):
                    raise _HeredocUnsure  # Arithmetik
                # Heredoc-Bodies in $(...) werden nie entfernt (#365): bash 3.2
                # beendet die Ersetzung an einer unausgeglichenen ")" im Body
                # und fuehrt die Folgezeilen als Befehle aus.
                stack.append("subst")
                i += 2
                word_start = True
                continue
            if nxt in "{['":
                raise _HeredocUnsure
            i += 1
            word_start = False
            continue
        if top == "dq":
            if c == '"':
                stack.pop()
            i += 1
            word_start = False
            continue
        # --- Code-Kontext (Ebene, Subshell oder $(...)) ---
        if c in " \t":
            i += 1
            word_start = True
            continue
        if c == "'":
            j = command.find("'", i + 1)
            if j < 0 or (pending and "\n" in command[i:j]):
                raise _HeredocUnsure
            i = j + 1
            word_start = False
            continue
        if c == '"':
            stack.append("dq")
            i += 1
            word_start = False
            continue
        if c == "#" and word_start:
            j = command.find("\n", i)
            i = n if j < 0 else j
            continue
        if word_start and re.match(r"(case|esac|coproc|select)\b", command[i:i + 7]):
            raise _HeredocUnsure
        if c == "(":
            if command.startswith("((", i):
                raise _HeredocUnsure
            stack.append("sub")
            i += 1
            word_start = True
            continue
        if c == ")":
            if len(stack) > 1:
                closed = stack.pop()
                word_start = closed == "sub"  # nach $(...) geht das Wort weiter
            else:
                word_start = True
            i += 1
            continue
        if c == "[" and command.startswith("[[", i):
            raise _HeredocUnsure
        if command.startswith("<<<", i):
            i += 3
            word_start = True
            continue
        if command.startswith("<<", i):
            m = _HEREDOC_MARKER_RE.match(command, i)
            if not m:
                raise _HeredocUnsure
            name = m.group(2) or m.group(3) or m.group(4) or m.group(5)
            quoted = m.group(5) is None
            line_head = command[command.rfind("\n", 0, i) + 1:i]
            consumer = _segment_command_word(line_head)
            # Nur auf oberster Ebene: hier ist "dq" nie oben, also heisst
            # len(stack) > 1, dass eine Subshell oder $(...) offen ist.
            ok = len(stack) == 1 and consumer in _HEREDOC_SAFE_CONSUMERS
            pending.append((name, m.group(1) == "-", quoted, ok, len(stack)))
            i = m.end()
            word_start = True
            continue
        word_start = c in ";&|<>"
        i += 1
    if pending or stack != ["code"]:
        raise _HeredocUnsure
    return bodies


def _residual_pipes_safe(residual: str) -> bool:
    """Jede Pipe im uebrigen Befehl muss in einen reinen Daten-Konsumenten fuehren."""
    if ">(" in residual or "<(" in residual:
        return False
    for m in re.finditer(r"(?<!\|)\|(?!\|)&?", residual):
        rest = residual[m.end():].split(None, 1)
        if not rest or rest[0] not in _HEREDOC_SAFE_CONSUMERS:
            return False  # Ziel fehlt, ist $VAR, "bash", s\h, sed ...
    return True


def strip_heredoc_bodies(command: str) -> str:
    """Entfernt Heredoc-BODIES, die zweifelsfrei reine Daten sind (#64/#75/#357).

    Oeffner-Zeilen bleiben stehen: Schreibziele (Redirects, tee-Argumente)
    bleiben fuer die Gates sichtbar. Fail-closed: im Zweifel kommt der Befehl
    unveraendert zurueck — ein falsch erkannter Oeffner darf nie echte Befehle
    aus dem Scan entfernen.
    """
    if "<<" not in command or "\r" in command:
        return command
    try:
        bodies = _heredoc_bodies(command)
    except _HeredocUnsure:
        return command
    keep, pos = [], 0
    for start, end, ok in bodies:
        if ok:
            keep.append(command[pos:start])
            pos = end
    keep.append(command[pos:])
    residual = "".join(keep)
    if residual == command:
        return command
    # Ausfuehrende Konsumenten irgendwo im uebrigen Befehl (Pipe auf der
    # Folgezeile, eval $(...), source /dev/stdin, ./skript ...).
    if (_HEREDOC_INTERPRETER_RE.search(residual) or _HEREDOC_REDEFINE_RE.search(residual)
            or not _residual_pipes_safe(residual)):
        return command
    return residual


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


# --- Code-Klassifikation: TDD-Gate (edit_gate.py) und Nachweis-Gate (#259) ---
# Eine Definition fuer beide Gates; per config.yaml → strict_code_gate
# ueberschreibbar. edit_gate.py importiert die drei Listen unter denselben Namen.
CODE_EXTENSIONS = {
    ".swift", ".kt", ".java", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".cpp", ".c", ".h", ".hpp", ".rb", ".php", ".cs",
}

ALWAYS_ALLOWED_DIRS = [
    "Tests/", "UITests/", "Test/", "test/", "__tests__/", "tests/",
    "spec/", "docs/", ".claude/commands/", "scripts/", "tools/",
]

ALWAYS_ALLOWED_PATTERNS = [
    r"\.md$", r"\.txt$", r"\.json$", r"\.yaml$", r"\.yml$",
    r"\.toml$", r"\.gitignore$", r"README", r"CHANGELOG", r"LICENSE",
]


def is_gated_code_path(file_path: str, config: "dict | None" = None) -> bool:
    """Ist das eine Code-Datei nach der TDD-Gate-Definition (edit_gate.py 2/2b/3)?

    Freigestellter Ordner (komponentenweise) oder Muster → nein; sonst zaehlt die
    kleingeschriebene Endung. Ohne `config` wird config.yaml geladen. Ob der Pfad
    im Projekt liegt, entscheidet diese Funktion bewusst nicht (#259 §1).
    """
    if config is None:
        try:
            from config_loader import load_config
            config = load_config()
        except Exception:
            config = {}
    section = config.get("strict_code_gate") if isinstance(config, dict) else None
    section = section if isinstance(section, dict) else {}
    code_ext = set(section.get("code_extensions", list(CODE_EXTENSIONS)))
    allowed_dirs = section.get("always_allowed_dirs", ALWAYS_ALLOWED_DIRS)
    allowed_patterns = section.get("always_allowed_patterns", ALWAYS_ALLOWED_PATTERNS)
    parts = set(Path(file_path).parts)
    if any(d.rstrip("/") in parts for d in allowed_dirs):
        return False
    if any(re.search(p, file_path, re.IGNORECASE) for p in allowed_patterns):
        return False
    return Path(file_path).suffix.lower() in code_ext


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


def pending_validation_lock_path(project_root: Path, wf_name: str) -> Path:
    """Lock-Datei des post_implementation_gate fuer einen Workflow (#134)."""
    return project_root / ".claude" / f"pending_validation_{wf_name}.json"


def read_pending_validation_lock(lock_path: Path) -> "dict | None":
    """Lock lesen; fehlend oder kaputt → None."""
    if not lock_path.exists():
        return None
    try:
        return json.loads(lock_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def approval_marker_path(project_root: Path, wf_name: str) -> Path:
    """Freigabe-Marker; Inhalt = `created`-Wert des Locks bei Freigabe (#134)."""
    return project_root / ".claude" / f"user_approved_validation_{wf_name}"


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


# Werte, die "aus" bedeuten. Alles andere laesst das Framework an.
_FRAMEWORK_OFF_VALUES = {"off", "0", "false", "no", "disabled"}


def framework_disabled() -> bool:
    """True, wenn dieses Projekt den Workflow-Zwang abgeschaltet hat (#132).

    Zwei Wege, beide absichtlich:

        OPENSPEC_FRAMEWORK=off          eine Sitzung, ohne etwas zu committen
        framework:                      in der Projekt-Konfiguration
          enabled: false                (openspec.yaml / config.yaml / .claude/)

    Der Konfigurations-Weg ist der eigentliche, weil er das kann, was Claude
    Codes `enabledPlugins: false` nicht kann: einen git-Worktree ueberleben.
    Jene Datei wird pro VERZEICHNIS gelesen, ein Worktree bekommt eine leere —
    also feuerten dort alle Gates wieder, obwohl das Haupt-Checkout sie aus
    hatte. `find_project_root()` loest einen Worktree auf das Hauptrepo auf,
    eine Datei dort wird deshalb aus jedem Worktree gefunden; und weil sie im
    Repo liegt, ueberlebt sie auch einen frischen Klon und ein Plugin-Update.

    Abgeschaltet wird die Ceremony — Phasen, Spec-Pflicht, TDD-Gate,
    Freigabe-Gate, Stop-Lock. NICHT die Schutz-Guards: Secrets, Credentials,
    CLAUDE.md-Schutz und der Worktree-Schutz laufen weiter. Ein Schalter, der
    beides mitnimmt, entfernt still Schutz, den niemand abwaehlen wollte.

    Nur ein ausdrueckliches `enabled: false` schaltet ab. Fehlender Schluessel,
    leerer Abschnitt, Tippfehler: Gates bleiben an — ein Projekt darf seinen
    Schutz nicht durch eine Zeile verlieren, die niemand gelesen hat. Dieselbe
    Regel wie beim ADR-Gate in workflow.py.

    Wirft nie. Laesst sich die Konfiguration nicht lesen, ist die Antwort
    "nicht abgeschaltet" — eine kaputte YAML-Datei darf das Framework nicht
    stillschweigend ausknipsen.
    """
    if os.environ.get("OPENSPEC_FRAMEWORK", "").strip().lower() in _FRAMEWORK_OFF_VALUES:
        return True
    try:
        from config_loader import load_config
        section = load_config().get("framework", {})
    except Exception:
        return False
    return isinstance(section, dict) and section.get("enabled") is False


def is_test_file(file_path: str) -> bool:
    """Check if a file is a test file."""
    test_patterns = [
        "test_", "_test.", ".test.", "tests/", "spec/", "_spec.",
        "Test.", "Tests/", "UITests/",
    ]
    return any(pattern in file_path for pattern in test_patterns)


# --- Beobachtbare Oberflaeche (Issue #260) ---------------------------------
# Zwei Musterlisten als Modul-Konstanten, per Config ueberschreibbar (Vorbild
# bash_gate.E2E_*_PATTERNS), geprueft per re.search gegen den Pfad, wie git ihn
# liefert: repo-relativ, Forward-Slashes. `is_code_file()` prueft die falsche
# Achse und passt NICHT: ein .swift-Service ist Code ohne Oberflaeche, eine
# .strings-Datei ist kein Code, hat aber eine.

# Die ersten vier Muster setzen PO-Entscheidung E1 um: Befehlstexte, die der PO
# beim Tippen eines Slash-Befehls liest, sind Oberflaeche — nicht Doku.
OBSERVABLE_SURFACE_PATTERNS = [
    r"(^|/)core/commands/.*\.md$",
    r"(^|/)\.claude/commands/.*\.md$",
    r"(^|/)skills/[^/]+/SKILL\.md$",
    r"(^|/)CLAUDE\.md$",
    r"(^|/)lovelace/.*\.ya?ml$",
    r"\.(strings|xcstrings)$",
    r"\.xcassets/",
]

# Bewusst NICHT enthalten: kein pauschales \.md$, kein pauschales ^\.claude/,
# keine generische YAML-Regel. Was keine der beiden Listen trifft, gilt als
# "unbekannt" und damit als streng (Schritt 9) — diese Regel traegt die
# Sicherheit des ganzen Verfahrens.
OBSERVABLE_NON_SURFACE_PATTERNS = [
    r"^docs/",
    r"^tests?/",
    r"(^|/)test_[^/]+\.py$",
    r"(^|/)[^/]+_test\.(py|go|js|ts)$",
    r"(^|/)[^/]+Tests?\.swift$",
    r"^core/hooks/",
    r"^scripts/",
    r"^\.github/",
    r"(^|/)(CHANGELOG|README|CONTRIBUTING)\.md$",
    r"(^|/)\.gitignore$",
    r"(^|/)\.editorconfig$",
]


def _observable_str_list(value) -> bool:
    """Form-Pruefung (Schritt 1): Liste aus Strings?"""
    return isinstance(value, list) and all(isinstance(i, str) for i in value)


def _observable_compile(patterns: "list[str]") -> "list | None":
    """Muster vorab uebersetzen; None, wenn eines kaputt ist. Eines davon
    stillschweigend zu ueberspringen waere fail-open."""
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern))
        except re.error:
            return None
    return compiled


def _observable_matches(path: str, compiled: "list") -> bool:
    return any(rx.search(path) for rx in compiled)


def _observable_git(args: "list[str]", cwd: Path) -> "tuple[int, str]":
    """`git <args>` in `cwd` → (rc, stdout). Wirft nie. `subprocess` bewusst
    lokal importiert: das Modul zieht es auf oberster Ebene nicht herein."""
    import subprocess
    try:
        proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                              text=True, timeout=30)
        return proc.returncode, proc.stdout or ""
    except Exception:
        return 1, ""


def _observable_base(cwd: Path, base_branch: str) -> "tuple[str | None, str]":
    """Merge-Base gegen den Basis-Stand → (merge_base, fehlergrund). KEIN
    literaler Rueckfallwert wie "origin/main": ohne Config-Wert und ohne
    `origin/HEAD` ist die Antwort "no-base" (streng), kein geratener Zweig."""
    base = base_branch.strip()
    if not base:
        rc, out = _observable_git(
            ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd)
        if rc != 0 or not out.strip():
            return None, "no-base"
        base = out.strip()
    rc, out = _observable_git(["merge-base", base, "HEAD"], cwd)
    if rc != 0:
        return None, "git-error"
    if not out.strip():
        return None, "no-base"
    return out.strip(), ""


def _observable_files(cwd: Path, merge_base: str) -> "tuple[list[str] | None, str]":
    """Vereinigung aus vier git-Quellen → (sortierte Pfade, fehlergrund). Je
    nach Stand der Phase 7 ist alles, nichts oder nur ein Teil eingecheckt;
    Quelle 4 (`ls-files --others`) ist Pflicht, sonst erschiene eine neu
    angelegte, noch nicht hinzugefuegte Datei als "keine Aenderung"."""
    sources = (
        ["diff", "--name-only", "--no-renames", f"{merge_base}...HEAD"],
        ["diff", "--name-only", "--no-renames", "--cached"],
        ["diff", "--name-only", "--no-renames"],
        ["ls-files", "--others", "--exclude-standard"],
    )
    found = set()
    for args in sources:
        rc, out = _observable_git(args, cwd)
        if rc != 0:
            return None, "git-error"
        found.update(line.strip() for line in out.splitlines() if line.strip())
    return sorted(found), ""


def observable_surface_report() -> dict:
    """Zaehlende Variante: {'surface', 'reason', 'files', 'root'}. Die
    CLI-Auskunft braucht neben Urteil und Begruendung auch Dateianzahl und
    Messwurzel. Die neun Vertragsschritte stehen ausschliesslich hier."""
    try:
        root = find_worktree_root() or find_project_root()
    except Exception:
        root = Path.cwd()
    root_str = str(root)

    def result(surface: bool, reason: str, files: int = 0) -> dict:
        return {"surface": surface, "reason": reason, "files": files, "root": root_str}

    # Schritt 1: Form des Config-Blocks. Ein FEHLENDER Block ist NICHT
    # ungueltig — dann gelten die Modul-Konstanten und enabled=true.
    try:
        from config_loader import load_config
        raw = load_config().get("observable_surface", {})
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        return result(True, "config-invalid")
    surface_patterns = raw.get("surface_patterns", OBSERVABLE_SURFACE_PATTERNS)
    non_surface_patterns = raw.get("non_surface_patterns",
                                   OBSERVABLE_NON_SURFACE_PATTERNS)
    base_branch = raw.get("base_branch")
    if not _observable_str_list(surface_patterns):
        return result(True, "config-invalid")
    if not _observable_str_list(non_surface_patterns):
        return result(True, "config-invalid")
    if base_branch is not None and not isinstance(base_branch, str):
        return result(True, "config-invalid")
    surface_rx = _observable_compile(surface_patterns)
    non_surface_rx = _observable_compile(non_surface_patterns)
    if surface_rx is None or non_surface_rx is None:
        return result(True, "config-invalid")

    # Schritt 2: abgeschaltet ist streng.
    if not raw.get("enabled", True):
        return result(True, "disabled")

    # Schritt 3/4/5: Messwurzel (oben), Basis-Stand, git-Fehler.
    merge_base, error = _observable_base(root, base_branch or "")
    if merge_base is None:
        return result(True, error)
    paths, error = _observable_files(root, merge_base)
    if paths is None:
        return result(True, error)

    # Schritt 6: leere Liste VOR Schritt 7/8 — `all([])` ist True, eine leere
    # Liste wuerde sonst faelschlich als "keine Oberflaeche" durchgehen.
    count = len(paths)
    if count == 0:
        return result(True, "empty-list")

    # Schritt 7: ein einziger Surface-Treffer genuegt.
    for path in paths:
        if _observable_matches(path, surface_rx):
            return result(True, f"{path} trifft surface", count)

    # Schritt 8: der EINZIGE Weg zu "keine Oberflaeche".
    if all(_observable_matches(path, non_surface_rx) for path in paths):
        return result(False, f"alle {count} Dateien ohne Oberfläche", count)

    # Schritt 9: unbekannte Datei → streng.
    for path in paths:
        if not _observable_matches(path, non_surface_rx):
            return result(True, f"{path} unbekannt", count)
    return result(True, "unbekannt", count)


# --- Gegenpruefung nach Risiko (#342) ---------------------------------------
# Startwerte; identisch zum Block `adversary_risk` in config.yaml und dessen
# Rueckfall, wenn der Block fehlt. Das Risiko kommt NUR aus der Dateiliste,
# nie aus Selbsteinstufung oder Zeilenzahl. Was keine Liste trifft, ist hoch.
ADVERSARY_HIGH_RISK_PATTERNS = [
    r"^core/hooks/",
    r"^hooks/",
    r"^core/agents/",
    r"^scripts/",
    r"^modules/",
    r"^setup\.py$",
    r"^config\.yaml$",
    r"^\.github/",
    r"^\.claude-plugin/",
    r"(^|/)\.env",
    r"secret",
]
ADVERSARY_LOW_RISK_PATTERNS = [
    r"^docs/",
    r"^tests?/",
    r"(^|/)test_[^/]+\.py$",
    r"^core/commands/[^/]+\.md$",
    r"^skills/[^/]+/SKILL\.md$",
    r"(^|/)(CHANGELOG|README|CONTRIBUTING)\.md$",
    r"(^|/)CLAUDE\.md$",
    r"(^|/)\.gitignore$",
]
ADVERSARY_LOW_RISK_MIN_ROUNDS = 1
ADVERSARY_HIGH_MIN_ROUNDS = 2


def adversary_risk_report() -> dict:
    """Schwester von `observable_surface_report`: {'risk', 'reason', 'files',
    'root', 'min_rounds'}. `risk` ist "hoch" oder "niedrig"; `files` die Anzahl.
    Fail-closed: jeder Fehler, jede Unsicherheit, jede unbekannte Datei ergibt
    "hoch" mit 2 Runden. Liest nur, schreibt nichts, blockt nichts. Auch ein
    unerwarteter Fehler ergibt "hoch" (aeusserer Fangschirm)."""
    try:
        root = find_worktree_root() or find_project_root()
    except Exception:
        root = Path.cwd()
    root_str = str(root)

    def result(risk: str, reason: str, files: int = 0, rounds: int = 2) -> dict:
        return {"risk": risk, "reason": reason, "files": files, "root": root_str,
                "min_rounds": rounds}

    try:
        # Schritt 1: Form des Config-Blocks. Fehlender Block = Modul-Konstanten.
        try:
            from config_loader import load_config
            raw = load_config().get("adversary_risk", {})
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            return result("hoch", "config-invalid")
        high_patterns = raw.get("high_risk_patterns", ADVERSARY_HIGH_RISK_PATTERNS)
        low_patterns = raw.get("low_risk_patterns", ADVERSARY_LOW_RISK_PATTERNS)
        base_branch = raw.get("base_branch")
        if not _observable_str_list(high_patterns) or not _observable_str_list(low_patterns):
            return result("hoch", "config-invalid")
        if base_branch is not None and not isinstance(base_branch, str):
            return result("hoch", "config-invalid")
        high_rx = _observable_compile(high_patterns)
        low_rx = _observable_compile(low_patterns)
        if high_rx is None or low_rx is None:
            return result("hoch", "config-invalid")

        # Schritt 2: nur ein ausdrueckliches `true` (bzw. fehlender Schluessel)
        # laesst die Staffelung zu; alles andere ist streng.
        if raw.get("enabled", True) is not True:
            return result("hoch", "disabled")

        # Schritt 3-5: Basis-Stand, Dateiliste, git-Fehler.
        merge_base, error = _observable_base(root, base_branch or "")
        if merge_base is None:
            return result("hoch", error)
        paths, error = _observable_files(root, merge_base)
        if paths is None:
            return result("hoch", error)

        # Schritt 6: leere Liste VOR `all(...)` (all([]) ist True).
        count = len(paths)
        if count == 0:
            return result("hoch", "empty-list")

        # Schritt 7: ein Hochrisiko-Treffer genuegt.
        for path in paths:
            if _observable_matches(path, high_rx):
                return result("hoch", f"{path} trifft hoch", count)

        # Schritt 8: unbekannte Datei -> hoch.
        for path in paths:
            if not _observable_matches(path, low_rx):
                return result("hoch", f"{path} unbekannt", count)

        # Schritt 9: der EINZIGE Weg zu "niedrig". Der Rundenwert gilt nur,
        # wenn er ein echter int 1..2 ist (bool/Text/Float/0/negativ -> 2).
        value = raw.get("low_risk_min_rounds", ADVERSARY_LOW_RISK_MIN_ROUNDS)
        rounds = value if (type(value) is int and 1 <= value <= 2) else 2
        return result("niedrig", f"alle {count} Dateien nur Text, Doku, Tests", count, rounds)
    except Exception:
        return result("hoch", "error")


def has_observable_surface() -> "tuple[bool, str]":
    """Hat der Arbeitsstand eine fuer den PO beobachtbare Oberflaeche?

    `(True, grund)`: hat oder koennte eine haben → die Schlussfrage in
    `/60-validate` bleibt. `(False, grund)`: sicher keine → sie entfaellt.
    Fail-CLOSED — nur der positive Nachweis, dass JEDE geaenderte Datei
    nachweislich keine Oberflaeche beruehrt, fuehrt zu False; jede Unsicherheit
    (kaputte oder abgeschaltete Config, kein Basis-Stand, git-Fehler, leere
    Dateiliste, unbekannte Endung) liefert True. Die Reihenfolge der neun
    Pruefungen ist Vertragsbestandteil (siehe `observable_surface_report()`).
    Liest nur, schreibt nichts, blockt nichts: sie unterdrueckt eine
    Rueckfrage, sie erlaubt nichts.
    """
    report = observable_surface_report()
    return bool(report["surface"]), str(report["reason"])
