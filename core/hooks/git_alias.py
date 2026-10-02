#!/usr/bin/env python3
"""
git-Alias-Aufloesung fuer das Commit-Gate (#281) — Hilfsmodul, KEIN Hook.

`resolve_git_aliases(command)` liefert eine `GitAliasView` (Expansionen, Shell-Ruempfe, nicht sicher
Aufloesbares, das bash_gate.py wie einen Commit prueft). Builtins werden nie nachgeschlagen; die Abfrage
(`git … config -z --get-regexp`) laeuft im nachgespielten Kontext, sieht den Stand VOR dem Befehl.

Rest-Grenzen (Known Limitations, docs/specs/fix-281-…): externe `git-<name>`, Code-Ausfuehrung in
reinem git, Commits ohne `commit` (#297); `bash -lc` & Co. (#298); Whitelist-Gefaelle in 3b (#296);
verschleierte Config-Schreibzugriffe; manipuliertes git, `source`, Funktion `git`, Unterbefehl aus
stdin, Tiefe > 2, bedingtes/nicht literales `cd`, parallele Aufrufe; Unzerlegbares ohne Nicht-Builtin
bleibt fail-open; secrets_guard sieht keine Ruempfe; GIT_BUILTINS = git 2.43; nur Hook-Umgebung.
Adversary-Runden 1/2: Taint und offene cd gelten fuer ALLE Nicht-Builtins des Befehls; hoechstens 64. Rest-Grenzen:
unbekannte Starter, die selbst Verzeichnis oder Benutzer wechseln (`firejail --private-cwd=B git ci`); hinter
unbekannten Wrappern nur Erwaehnung (`mywrap git $(echo ci)`); Indirektion jenseits von `git config $K` und
`export ${P}…=` (Name aus eval, read, printf -v mit Variable o. ae.).
"""

import os
import re
import shlex
from types import SimpleNamespace

from hook_utils import (
    _ENV_ASSIGN_RE, _GIT_COMMAND_PREFIXES, _GIT_OPTS_WITH_VALUE, _GIT_SHELL_BINARY_RE,
    _git_lex, _is_git_separator, _looks_like_git,
)

# `git --list-cmds=builtins` von git 2.43 (140 Namen), exakt und case-sensitiv; Drift-Test: AC-17.
GIT_BUILTINS = frozenset("""add am annotate apply archive bisect blame branch bugreport bundle cat-file
check-attr check-ignore check-mailmap check-ref-format checkout checkout--worker checkout-index cherry
cherry-pick clean clone column commit commit-graph commit-tree config count-objects credential
credential-cache credential-cache--daemon credential-store describe diagnose diff diff-files
diff-index diff-tree difftool fast-export fast-import fetch fetch-pack fmt-merge-msg for-each-ref
for-each-repo format-patch fsck fsck-objects fsmonitor--daemon gc get-tar-commit-id grep hash-object
help hook index-pack init init-db interpret-trailers log ls-files ls-remote ls-tree mailinfo mailsplit
maintenance merge merge-base merge-file merge-index merge-ours merge-recursive merge-recursive-ours
merge-recursive-theirs merge-subtree merge-tree mktag mktree multi-pack-index mv name-rev notes
pack-objects pack-redundant pack-refs patch-id pickaxe prune prune-packed pull push range-diff
read-tree rebase receive-pack reflog remote remote-ext remote-fd repack replace rerere reset restore
rev-list rev-parse revert rm send-pack shortlog show show-branch show-index show-ref sparse-checkout
stage stash status stripspace submodule--helper switch symbolic-ref tag unpack-file unpack-objects
update-index update-ref update-server-info upload-archive upload-archive--writer upload-pack var
verify-commit verify-pack verify-tag version whatchanged worktree write-tree""".split())

# Freigabeliste (Abschnitt 4); nie GIT_TRACE* (liesse selbst `git config` schreiben), LD_*, PATH …
_ALLOWED_ENV = re.compile(
    r"GIT_CONFIG_(?:GLOBAL|SYSTEM|NOSYSTEM|COUNT|PARAMETERS|KEY_\d+|VALUE_\d+)|HOME|XDG_CONFIG_HOME"
    r"|GIT_(?:DIR|WORK_TREE|COMMON_DIR|CEILING_DIRECTORIES|DISCOVERY_ACROSS_FILESYSTEM)")
_SHELL_SYNTAX = re.compile(r"[$`*?\[\]{}]")  # Wert steht erst nach der Shell-Expansion fest
_INCLUDE_KEY = re.compile(r"include.*\.path$", re.IGNORECASE)  # include.path, includeIf.*.path
_SCOPE = re.compile(r"[()`]|^[\n;]*(?:\|&?|&)[\n;]*$")  # Subshell, Pipeline, Hintergrund, $( und Backtick
_UNQUOTE = re.compile(r"\\\r?\n|[\\'\"]")  # fuer bash ist `g""it`, `g\it` das Wort git (F001)
_CD_WORD = re.compile(r"(?<![\w./-])(?:cd|pushd|popd)(?![\w./-])")
_CD, _CTRL = ("cd", "pushd", "popd"), {"if", "then", "else", "elif", "do", "while", "until"}
_SKIP, _SU = _GIT_COMMAND_PREFIXES | _CTRL, {"sudo", "doas", "su", "runuser", "chroot"}
_WD = ("--chdir", "--wd", "--workdir", "--working-directory")  # Starter-Option wechselt das Verzeichnis (F009 A)
_KEEP = set("xargs timeout nice nohup time command exec env stdbuf ionice setsid flock watch parallel chronic unbuffer "
            "find".split())  # Starter, die Verzeichnis und Kontext behalten (F009 B)
_STARTERS, _EXEC = _KEEP | _SU | _SKIP, ("-exec", "-ok", "-execdir", "-okdir")  # find: neue Befehlsposition
_REDIR_OP = re.compile(r"(?:\d*|&)(?:>>?|<<?|<>|>\||>&|<&|&>>?)")
_OPTVAL = {  # wertnehmende Optionen bekannter Starter (F018): ihr Wert haelt die Befehlsposition
    "timeout": {"-s", "--signal", "-k", "--kill-after"}, "flock": {"-w", "--timeout", "-E", "--conflict-exit-code"},
    "stdbuf": {"-i", "-o", "-e"}, "nice": {"-n"}, "ionice": {"-c", "-n", "-p", "-P", "-u"}, "watch": {"-n"},
    "xargs": {"-I", "-L", "-n", "-P", "-a", "-d", "-E", "-s"}, "time": {"-f", "-o"}, "env": {"-u"}}
_POSITIONAL = {"flock": 1}  # Operanden vor dem Befehl (Sperrdatei)
_ARG = re.compile(r"[+-]?\d+(?:\.\d+)?[smhd]?")  # Zahl/Dauer als Starter-Argument (timeout 60, nice -n 5)
_PLAUSIBLE = re.compile(r"[A-Za-z][A-Za-z0-9.-]*")  # Variablenname, `.` aus [alias "a"] b: moeglicher Alias
_COMPLEX = {"for", "while", "until", "select", "if", "case", "function", "trap", "eval", "exec", "builtin",
            "command", "{", "}"}  # nicht einfach sequentiell: dort ist kein cd modellierbar (F002)
_CONFIG_NAMES = (".gitconfig", "git/config", "config.worktree", "$git_config", "${git_config")
_QUERY = ("config", "-z", "--get-regexp", r"^(alias\..*|help\.autocorrect)$")
_NO_TRACE2 = dict.fromkeys(("GIT_TRACE2", "GIT_TRACE2_EVENT", "GIT_TRACE2_PERF"), "0")  # schlaegt trace2.*Target
_NO_AUTOCORRECT = ("0", "false", "off", "no", "never", "show", "prompt")
_MAX_QUERIES, _MAX_STEPS, _MAX_DEPTH, _MAX_WORK, _MAX_BODY = 3, 8, 2, 64, 1 << 16
_SYNTAX, _NO_DIR, _STARTER = "Unterbefehl mit Shell-Syntax", "unbekanntes Arbeitsverzeichnis", "Starter wechselt " \
    "Verzeichnis oder Benutzer (sudo, env mit Option, find -execdir, --chdir …)"
_RANGE, _TAINT = "Zuweisung mit unbestimmbarer Reichweite", "Konfiguration im selben Aufruf geändert"
_BIG = f"Befehl zu groß: mehr als {_MAX_WORK} Nicht-Builtin-Aufrufe/Rümpfe oder 64 KiB Rumpf-Text"


class GitAliasView(SimpleNamespace):
    """Sicht auf einen Bash-Befehl (Spec, Abschnitt 1): fuenf Listen, alle leer = nichts zu tun."""

    def __init__(self):
        super().__init__(expansions=[], shell_bodies=[], unresolved=[], unresolved_subs=[],
                         resolutions=[])

    def add_unresolved(self, reason: str, sub: str) -> None:
        """Nicht sicher aufloesbaren Unterbefehl vermerken — Gruende und Namen ohne Duplikate."""
        self.unresolved += [] if reason in self.unresolved else [reason]
        self.unresolved_subs += [] if sub in self.unresolved_subs else [sub]


class _Unresolved(Exception):
    """Interner Abbruch: dieser Aufruf ist nicht sicher aufloesbar (Grund als Text)."""


class _TooBig(Exception):
    """Arbeitsgrenze ueberschritten (F008, F014): Durchlauf endet sofort, die Sicht ist unresolved."""


def _run_git(argv, cwd, env):
    """Standard-Runner: `git` aus dem PATH der Umgebung, stdin geschlossen, stderr verworfen, 2 s."""
    import subprocess  # erst bei einer Abfrage: Builtins zahlen den Import nicht
    proc = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2)
    return proc.returncode, proc.stdout


def _split_call(tokens: list, i: int) -> tuple:
    """(Optionen als (Option, Wert), Index, Unterbefehl) ab i — Semantik von _git_subcommand_after."""
    opts = []
    while i < len(tokens) and not _is_git_separator(tokens[i]):
        tok = tokens[i]
        if tok in _GIT_OPTS_WITH_VALUE:
            opts.append((tok, tokens[i + 1] if i + 1 < len(tokens) else ""))
            i += 2
        elif tok.startswith("-"):
            opts += [tok.partition("=")[::2]] if "=" in tok else []  # --git-dir=…, --config-env=…
            i += 1
        else:
            return opts, i, tok
    return opts, i, None


def _segments(tokens: list):
    """(Segment, Trenner, {Index eines Shell-Texts (sh -c, eval/trap, $(/`): Stellung}, Stellungen) — _stellungen."""
    seg = []
    for tok in [*tokens, None]:
        if tok is not None and not _is_git_separator(tok):
            seg.append(tok)
        elif seg:
            bases = [word.rsplit("/", 1)[-1] for word in seg]
            klass = _stellungen(seg, bases)
            first = next((i for i, b in enumerate(bases) if b in ("eval", "trap")), len(seg))
            texts = [(i + 2, klass[i]) for i, b in enumerate(bases)
                     if _GIT_SHELL_BINARY_RE.match(b) and seg[i + 1:i + 2] == ["-c"]]
            texts += [(j, klass[first]) for j in range(first + 1, len(seg))]  # eval/trap: alle Argumente
            nested = {j: "head" for j, t in enumerate(seg) if "$(" in t or "`" in t}  # "x$(…)" als ein Token (F004)
            nested.update((j, m) for j, m in texts if j < len(seg) and not (m[0] == "C" and j in nested))
            yield seg, tok or "", nested, klass
            seg = []


def _redirects(seg: list) -> set:
    """Indizes von Umleitungs-Operatoren samt Ziel (`>`, `2`, `>&`, `/dev/null` …): kein Befehlswort."""
    out = set()
    for i, t in enumerate(seg):
        if t and _REDIR_OP.fullmatch(t) and not t.isdigit():
            out |= {i, i + 1}
            if i and seg[i - 1].isdigit():
                out.add(i - 1)
    return out


def _head(seg: list) -> int:
    """Index des ersten Tokens nach Praefix-Zuweisungen, Wrappern (env, nice, time …) und Kontrollwoertern."""
    skip = _redirects(seg)
    heads = (i for i, t in enumerate(seg) if i not in skip and not (_ENV_ASSIGN_RE.match(t) or t in _SKIP))
    return next(heads, len(seg))


def _stellungen(seg: list, bases: list) -> list:
    """Stellung jedes Tokens als git-/Shell-Aufruf (F009), linear. Befehlsposition: davor nur Starter, Zuweisungen,
    Optionen, Zahlen (neu ab find -exec/-execdir). Dort "head" (Kopf), "A" hinter sudo & Co., env mit Option,
    find -execdir/-okdir, --chdir … (Verzeichnis offen), sonst "B"; ausserhalb Erwaehnung "C", hinter A "C!"."""
    execdir, find, h = not {"-execdir", "-okdir"}.isdisjoint(seg), "find" in bases, _head(seg)
    out, ok, a, redir, cur, val, pos = [], True, False, _redirects(seg), "", False, 0
    for i, (b, t) in enumerate(zip(bases, seg)):
        out.append(("A" if a else "head" if i == h else "B") if ok else "C!" if a else "C")
        a = a or b in _SU or t.partition("=")[0] in _WD or b == "find" and execdir or (
            b == "env" and "".join(seg[i + 1:i + 2])[:1] == "-")
        operand = val  # Wert einer wertnehmenden Starter-Option
        val = False
        if not operand and b in _STARTERS:
            cur, pos = b, _POSITIONAL.get(b, 0)
        elif not operand and t in _OPTVAL.get(cur, ()):
            val = True
        elif not operand and pos and t[:1] != "-" and not _ENV_ASSIGN_RE.match(t) and i not in redir:
            pos, operand = pos - 1, True
        ok = find and t in _EXEC or ok and bool(b in _STARTERS or t[:1] == "-" or _ENV_ASSIGN_RE.match(t)
                                                 or _ARG.fullmatch(t) or i in redir or operand)
    return out


def _allowed(tok: str) -> bool:
    """Zuweisung eines Namens der Freigabeliste (`HOME=…`, `GIT_CONFIG_GLOBAL=…`)?"""
    return bool(_ENV_ASSIGN_RE.match(tok) and _ALLOWED_ENV.fullmatch(tok.partition("=")[0]))


def _naive_subs(text: str) -> list:
    """Nicht-Builtin-Unterbefehle nach naiver Zerlegung an Whitespace und Shell-Trennern (Abschnitt 15, F006);
    eine Erwaehnung (Stellung C) nur mit moeglichem Alias-Namen."""
    subs = []
    for seg, _sep, _nested, klass in _segments(re.findall(r"[;&|()`\n]+|[^\s;&|()`<>]+", _UNQUOTE.sub("", text))):
        nxt = 0
        for i, tok in enumerate(seg):
            if i >= nxt and _looks_like_git(tok):  # git als Optionswert (`-c git`) ist kein Aufruf: linear
                _, nxt, sub = _split_call(seg, i + 1)
                if sub and sub not in GIT_BUILTINS and (klass[i][0] != "C" or _PLAUSIBLE.fullmatch(sub)):
                    subs.append(sub)
    return list(dict.fromkeys(subs))[:_MAX_WORK + 1]


def _all_tokens(text: str, depth: int = 0) -> list:
    """Alle Tokens; verschachtelte Shell-Texte zaehlen mit ihren Tokens, nicht als Ganzes."""
    out = []
    for seg, _sep, nested, _klass in _segments(_git_lex(text) or [text]):
        for i, tok in enumerate(seg):
            out += _all_tokens(tok, depth + 1) if i in nested and depth < _MAX_DEPTH else [tok]
    return out


class _Resolver:
    """Ein Durchlauf ueber einen Bash-Befehl: Sicht, Abfrage-Cache, Taint, gesehene Nicht-Builtins."""

    def __init__(self, command, cwd, environ, run):
        self.command, self.cwd, self.environ, self.run = command, cwd, environ, run
        self.view, self.cache, self.taint, self.tokens, self.subs = GitAliasView(), {}, None, None, []
        self.cdpath = "CDPATH" in _UNQUOTE.sub("", command) or "CDPATH" in environ  # einmal (F021)

    def walk(self, text: str, scope: SimpleNamespace, depth: int) -> None:
        """Text auswerten: git-Aufrufe, verschachtelte Shells, cd-Modell, Taint (Abschnitte 5, 6).
        scope: pre (-C-Kette und Optionen), env (Overlay), why (Sperrgrund), body (Shell-Rumpf)."""
        toks = _git_lex(text) if depth <= _MAX_DEPTH else []
        if toks is None:  # fuer shlex unzerlegbar: nur die naive Kandidatensuche (Abschnitt 15)
            for sub in (s for s in _naive_subs(text) if not scope.mention or _PLAUSIBLE.fullmatch(s)):
                self.note(sub)
                self.view.add_unresolved("Befehl nicht zerlegbar", sub)
            return
        simple = not any(t in _COMPLEX or _SCOPE.search(t) for t in toks)  # einfach sequentiell (F002)
        if (not simple and _CD_WORD.search(_UNQUOTE.sub("", text))) or any(
                t in _CD and i and not _is_git_separator(toks[i - 1]) for i, t in enumerate(toks)):
            scope.why = scope.why or _NO_DIR  # cd ausserhalb der Kopfform: offen fuer ALLE Aufrufe (F004)
        for seg, sep, nested, klass in _segments(toks):
            plain, subs, nxt = [tok for i, tok in enumerate(seg) if i not in nested], set(), 0
            for gi in [i for i, tok in enumerate(seg) if _looks_like_git(tok)]:
                if gi >= nxt:  # git als Optionswert (`-c git`) ist kein Aufruf: haelt die Arbeit linear
                    opts, nxt, sub = _split_call(seg, gi + 1)
                    k = ("C!" if klass[gi] in ("A", "C!") else "C") if scope.mention else klass[gi]
                    subs.add(sub)  # auch eine Erwaehnung: ein unbekannter Starter kann sie ausfuehren
                    self.call(seg, gi, sep, scope, depth, opts, nxt, sub, k)
            self.taint_config(subs, seg)
            why = scope.why or (_RANGE if any(map(_allowed, plain)) else None)
            for j, mode in nested.items():  # startet beim Modell-Stand; cd wirkt nicht nach aussen; Stellung wie git
                inner = {"why": why or (_NO_DIR if mode in ("A", "C!") else None),
                         "mention": scope.mention or mode[0] == "C"}  # Stellung des Shell-Aufrufs wie bei git
                self.walk(seg[j], SimpleNamespace(**{**vars(scope), **inner}), depth + 1)
            self.cd(seg, scope)
            self.mark_taint(seg, plain)

    def call(self, seg: list, gi: int, sep: str, scope, depth: int, opts: list, si: int, sub, k: str) -> None:
        """Ein git-Token der Stellung k: Builtin, Shell-Syntax, Taint, Kontext, Kette (Abschnitte 2 bis 8)."""
        if (sub is None and "`" not in sep) or sub in GIT_BUILTINS:  # Builtins: nie nachschlagen
            return
        if k[0] == "C" and not _PLAUSIBLE.fullmatch(sub or ""):  # Erwaehnung: nur ein moeglicher Alias-Name zaehlt,
            return  # dann wie ein echter Aufruf (Taint, offenes Verzeichnis, Quellen, Fehler → unresolved)
        if k[0] == "C" and "." in sub and (scope.why or k == "C!") and not self.taint:  # README.md: nur Taint
            return self.note(sub)  # (auch nachtraeglich) macht ihn unresolved, nicht das offene Verzeichnis
        self.note(sub := sub or "`…`")  # `…`: vom Backtick-Trenner verschluckt, an jeder Position (F011)
        try:
            why = scope.why or (_STARTER if k in ("A", "C!") else None)
            if _SHELL_SYNTAX.search(sub) or self.taint or why:
                raise _Unresolved(_SYNTAX if _SHELL_SYNTAX.search(sub) else self.taint or why)
            self.chain(sub, seg, si, *self.context(seg, gi, opts, scope, k), depth, k)
        except _Unresolved as exc:
            self.view.add_unresolved(str(exc), sub)

    def note(self, sub: str, big: bool = False, real: bool = True) -> None:
        """Nicht-Builtin vermerken (Taint gilt nachtraeglich fuer alle echten, F004); Arbeitsgrenze (F008, F014)."""
        self.subs.append(sub if real else None)  # Erwaehnung mit Alias: zaehlt, aber ohne Taint-Wirkung (F009)
        if big or len(self.subs) > _MAX_WORK:
            self.view.add_unresolved(_BIG, sub)
            raise _TooBig

    def context(self, seg: list, gi: int, opts: list, scope: SimpleNamespace, k: str) -> tuple:
        """Kontext nachspielen (Abschnitt 4) → (pre, env); Praefixe nur am Kopf, Erwaehnung ohne Quellen (F009)."""
        before = seg[:gi] if k == "head" else []
        assigns = {tok.partition("=")[0]: tok for tok in before if _ENV_ASSIGN_RE.match(tok)}
        own = {n: self.literal(t.partition("=")[2]) for n, t in assigns.items() if _allowed(t)}
        if "include" in own.get("GIT_CONFIG_PARAMETERS", "").lower():
            raise _Unresolved("GIT_CONFIG_PARAMETERS mit include")
        values = {n.replace("_VALUE_", "_KEY_"): n for n in own if n.startswith("GIT_CONFIG_VALUE_")}
        sources = [(own[n], assigns[n]) for n in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM") if n in own]
        sources += [(own[v], assigns[v]) for k, v in values.items() if _INCLUDE_KEY.match(own.get(k, ""))]
        pre = list(scope.pre)
        for opt, val in opts:
            tok = val
            if opt == "--config-env":  # K=VAR → -c K=<Wert>; Hook-Umgebung nur, wenn der Befehl VAR
                key, _, var = val.rpartition("=")  # sonst nirgends nennt (export, read …: F005)
                tok = assigns.get(var)
                text = _UNQUOTE.sub("", "\n".join([self.command, *self.view.shell_bodies])) if k[0] != "C" else ""
                if tok is None and (k[0] == "C" or var not in self.environ  # Zaehler auf normalisiertem Text (F020)
                                    or len(re.findall(rf"(?<!\w){re.escape(var)}(?!\w)", text)) > 1):
                    raise _Unresolved("--config-env: Variable ungesetzt oder im Befehl verändert")
                opt, val = "-c", key + "=" + (tok.partition("=")[2] if tok else self.environ[var])
            if opt in ("-C", "-c", "--git-dir", "--work-tree"):
                pre += [opt, self.literal(val)]
                if opt == "-c" and tok and _INCLUDE_KEY.match(val.partition("=")[0]):
                    sources.append((val.partition("=")[2], tok))
        for path, tok in sources:
            self.check_source(path, tok, pre)
        return pre, {**scope.env, **own}

    def literal(self, value: str) -> str:
        """Wert, wie ihn die Shell uebergibt: Shell-Syntax → unresolved, fuehrendes ~ → HOME."""
        if _SHELL_SYNTAX.search(value):
            raise _Unresolved("Shell-Syntax im nachgespielten Wert")
        return self.environ.get("HOME", "~") + value[1:] if value[:2] in ("~", "~/") else value

    def check_source(self, path: str, tok: str, pre: list) -> None:
        """Im Befehl benannte Konfigurationsdatei: muss existieren, kein anderes Token nennt sie."""
        where = os.path.join(self.cwd, *[val for opt, val in zip(pre[::2], pre[1::2]) if opt == "-C"])
        self.tokens = _all_tokens(self.command) if self.tokens is None else self.tokens
        if not os.path.exists(os.path.join(where, self.literal(path))) or any(
                os.path.basename(path) in other for other in self.tokens if other != tok):
            raise _Unresolved("Konfigurationsdatei fehlt oder steht erneut im Befehl: " + path)

    def lookup(self, pre: list, env: dict) -> dict:
        """Tabelle `alias.*` und `help.autocorrect` des Kontexts (Abschnitte 3, 14): gecacht, hoechstens drei
        Abfragen; GIT_TRACE* der Hook-Umgebung entfernt, trace2 per Umgebung aus (schreibt nichts, F012)."""
        import subprocess
        key = (tuple(pre), tuple(sorted(env.items())))
        if key not in self.cache:
            if len(self.cache) >= _MAX_QUERIES:
                raise _Unresolved("Budget: mehr als drei Abfragen")
            base = {k: v for k, v in self.environ.items() if k != "GIT_CONFIG" and not k.startswith("GIT_TRACE")}
            try:
                rc, out = self.run(["git", *pre, *_QUERY], self.cwd, {**base, **env, **_NO_TRACE2})
                failed = None if rc in (0, 1) else f"rc {rc}"  # rc 1: kein Treffer, auch ohne Repo
            except (OSError, subprocess.TimeoutExpired) as exc:
                failed, out = type(exc).__name__, b""
            entries = [e.partition("\n") for e in out.decode("utf-8", "replace").split("\0")]
            self.cache[key] = f"Abfrage gescheitert: {failed}" if failed else {
                k.lower(): v for k, nl, v in entries if nl}
        if isinstance(self.cache[key], str):
            raise _Unresolved(self.cache[key])
        return self.cache[key]

    def chain(self, sub: str, seg: list, si: int, pre: list, env: dict, depth: int, k: str) -> None:
        """Kette bis zum Builtin (Abschnitt 7); Shell-Alias als Rumpf-Text (Abschnitt 8)."""
        table, name, opts, line, seen = self.lookup(pre, env), sub, [], ["git " + sub], set()
        args = seg[si + 1:] if "alias." + sub.lower() in table else []  # Argumente nur fuer einen Alias: linear
        while name not in GIT_BUILTINS and (key := "alias." + name.lower()) in table:
            if key in seen or len(seen) == _MAX_STEPS:
                raise _Unresolved("Alias-Schleife" if key in seen else "mehr als 8 Schritte")
            seen.add(key)
            if table[key].startswith("!"):  # beliebiger Shell-Code; git haengt die Argumente an
                body = table[key][1:]
                text = body + " " + shlex.join(args)  # git-<builtin> aus dem exec-path wie git <builtin> (F007)
                dashed = [re.fullmatch(r"(?:.*/)?git-([\w-]+)", t) for t in _all_tokens(text)]
                text += "".join("\ngit " + m[1] for m in dashed if m and m[1] in GIT_BUILTINS)  # lexer-basiert (F019)
                self.view.shell_bodies += [] if text in self.view.shell_bodies else [text]  # je Text einmal
                self.note(sub, sum(map(len, self.view.shell_bodies)) > _MAX_BODY, False)  # Rumpf zaehlt (F014)
                self.view.resolutions.append(" → ".join(line + [table[key]]))
                return self.walk(text, SimpleNamespace(pre=pre, env=env, why=None, body=True, mention=False), depth + 1)
            try:  # git zerlegt mit split_cmdline: ein Backslash wirkt dort anders als in shlex (F003)
                parts = [] if "\\" in table[key] else shlex.split(table[key])
            except ValueError:
                parts = []
            if not parts:
                raise _Unresolved("leerer oder nicht sicher zerlegbarer Alias-Wert")
            parts += args  # git haengt die Argumente an; Optionen im Wert wie beim Aufruf
            value_opts, i, name = _split_call(parts, 0)
            if any(o in ("-c", "--config-env") and v.lower().startswith(("alias.", "include"))
                   for o, v in value_opts):
                raise _Unresolved("Alias-Wert ändert die Alias-Tabelle")
            if name is None:
                return  # nur Optionen: git zeigt seine Hilfe
            if _SHELL_SYNTAX.search(name):
                raise _Unresolved(_SYNTAX)
            opts, args, line = opts + parts[:i], parts[i + 1:], line + ["git " + name]
        inline = any(v.lower().startswith("help.autocorrect") for v in pre)  # im Aufruf gesetzt: auch fuer C (F018)
        if (k[0] != "C" or len(line) > 1 or inline) and name not in GIT_BUILTINS and table.get(  # sonst C: nichts
                "help.autocorrect", "0").lower() not in _NO_AUTOCORRECT:
            raise _Unresolved("help.autocorrect aktiv: Unterbefehl weder Builtin noch Alias")  # F013
        if len(line) > 1:  # Kette endet am Builtin oder an einem Namen ohne Alias (git-<name>)
            expansion = ["git", *opts, name, *args]
            self.view.expansions.append(expansion)
            self.view.resolutions.append(" → ".join(line))
            self.taint_config({name}, seg + expansion)

    def cd(self, seg: list, scope: SimpleNamespace) -> None:
        """cd/pushd mit genau einem literalen Pfad → implizites -C, sonst unbekannt (Abschnitt 6)."""
        if seg[0] in _CD:  # jede andere Stellung macht walk() schon zu „unbekannt“
            try:
                path = self.literal(seg[1]) if len(seg) == 2 and seg[0] in ("cd", "pushd") else "-"
            except _Unresolved:
                path = "-"
            rel = not os.path.isabs(path) and (scope.body or self.cdpath)
            if path.startswith("-") or rel or len(scope.pre) > _MAX_WORK:  # Rumpf: Wurzel; CDPATH (F002);
                scope.why = scope.why or _NO_DIR  # mehr als 32 cd: bleibt linear (F008)
            else:
                scope.pre = scope.pre + ["-C", path]

    def taint_config(self, subs: set, tokens: list) -> None:
        """Taint (a), einmal je Segment: `git config`/`clone` mit `alias.`/`include`, `config -e|--edit`,
        `init`/`clone`/`submodule` mit `--template` (F017)."""
        if subs & {"config", "clone", "init", "submodule"}:
            low = [t.lower() for t in tokens]
            key = next((t for t in low[low.index("config") + 1:] if t[:1] != "-"), "") if "config" in low else ""
            if (subs & {"config", "clone"} and any("alias." in t or "include" in t for t in low)
                    or "config" in subs and _SHELL_SYNTAX.search(key)  # Schluessel erst zur Laufzeit (F023)
                    or "config" in subs and any(t == "-e" or len(t) > 2 and "--edit".startswith(t) for t in low)
                    or any(len(t.partition("=")[0]) > 2 and "--template".startswith(t.partition("=")[0]) for t in low)):
                self.taint = self.taint or _TAINT

    def mark_taint(self, seg: list, plain: list) -> None:
        """Taint (b)/(c): Config-Dateinamen, `$GIT_CONFIG…`, jede Nennung eines Namens der Freigabeliste
        (Zuweisung, export, unset, read, for …) — ohne die Praefix-Zuweisungen eines git-Aufrufs am
        Segmentkopf (sein eigener Kontext, Abschnitt 4)."""
        h, setter = _head(seg), plain[:1] in (["export"], ["declare"], ["typeset"], ["readonly"], ["local"])
        mine = set(seg[:h]) if h < len(seg) and _looks_like_git(seg[h]) else set()
        if any(tok not in mine and (any(n in tok.lower() for n in _CONFIG_NAMES)
               or _ALLOWED_ENV.fullmatch(tok.partition("=")[0])
               or setter and "=" in tok and _SHELL_SYNTAX.search(tok.partition("=")[0])) for tok in plain):  # F023
            self.taint = self.taint or _TAINT


def resolve_git_aliases(command: str, cwd=None, environ=None, run=None) -> GitAliasView:
    """Alias-Sicht auf `command`; wirft nie, blockt nie. None → os.getcwd(), os.environ, Standard-
    Runner; run(argv, cwd, env) -> (rc, stdout_bytes) darf OSError/TimeoutExpired werfen."""
    view = GitAliasView()
    if "git" not in _UNQUOTE.sub("", command):
        return view
    try:
        resolver = _Resolver(command, cwd or os.getcwd(),
                             os.environ if environ is None else environ, run or _run_git)
        resolver.walk(command, SimpleNamespace(pre=[], env={}, why=None, body=False, mention=False), 0)
        for sub in filter(None, resolver.subs) if resolver.taint else ():  # Taint: ALLE echten Nicht-Builtins (F004)
            resolver.view.add_unresolved(resolver.taint, sub)
        return resolver.view
    except _TooBig:
        return resolver.view
    except Exception as exc:  # Rueckfall (Abschnitt 13): naive Kandidatensuche, nichts aufloesen
        for sub in _naive_subs(command):
            view.add_unresolved(f"interner Fehler: {type(exc).__name__}", sub)
        return view
