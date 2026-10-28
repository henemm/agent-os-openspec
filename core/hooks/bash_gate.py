#!/usr/bin/env python3
"""
Bash Gate v3 — Consolidated PreToolUse Hook for Bash

Replaces 15 separate hooks with 1. Sequential logic:

1. Stop-Lock → BLOCK
2. Git commands → ALLOW (fast path)
3. State-Integrity: protected file + write indicator → BLOCK (whitelist)
4. Secrets: sensitive file + content output → BLOCK
5. Git Commit gates (configurable required staged files, adversary verdict
   plus a valid, stamped dialog artifact — #253)
6. ALLOW

Project-specific gates (sim_enforcer, build_lock) belong in module hooks.

Exit Codes: 0 = allowed, 2 = blocked
"""

from hook_utils import (
    setup_path, find_project_root, get_tool_input, block, allow,
    get_active_workflow_name, gate_diagnostics, strip_heredoc_bodies,
    SECRETS_SENSITIVE_PATTERNS, SECRETS_ALWAYS_BLOCKED, SECRETS_FREETEXT_FLAGS as _SHARED_FREETEXT_FLAGS,
    git_subcommands, git_head_subcommands, is_git_subcommand, is_pure_git_command,
    framework_disabled, _git_segments, git_runs_foreign_code,
    _git_lex, _is_git_redirect, read_state_json, UnsafeStateError,
    is_stop_locked, stop_lock_state,
)
setup_path()

import json
import os
import re
import shlex
import sys
from pathlib import Path

# --- Defaults (overridable via config.yaml) ---

# Geteilte Muster aus hook_utils (Issue #75): identisch mit secrets_guard.py.
# Die frueheren bash_gate-eigenen Breitmuster `_key`/`_secret` blockierten
# Befehle wegen blosser Dateinamen (tests/test_secret_egress_guard.py).
SENSITIVE_PATTERNS = list(SECRETS_SENSITIVE_PATTERNS)

ALWAYS_BLOCKED_SECRETS = list(SECRETS_ALWAYS_BLOCKED)

CONTENT_OUTPUT_COMMANDS = [
    r"\bcat\b", r"\bhead\b", r"\btail\b", r"\bless\b", r"\bmore\b",
    r"\bsed\b.*-n.*p", r"\bawk\b.*print",
]

# Flags, deren Argument Freitext ist (Commit-Message, PR-/Issue-Body, Feld-
# werte) — nie ein Datei-Pfad. Deren Wert wird bei Datei-Token-Analysen
# uebersprungen (Issue #53). Geteilte Quelle: hook_utils (kein Guard-Drift).
SECRETS_FREETEXT_FLAGS = _SHARED_FREETEXT_FLAGS

PROTECTED_FILE_PATTERNS = [
    r"\.claude/workflows/[^\s]*\.json",
    r"workflow_state\.json",
    r"user_override_token\.json",
    r"\.claude/hooks/[^\s]*\.py",
    r"\.claude/settings\.json",
    r"\.claude/pending_validation_[^\s]*\.json",
    r"\.claude/user_approved_validation_[^\s]*",
]

# Simulator-Beleg (#447): Beleg-Datei und Ordner `simulator-run/`. Bewusst NICHT in
# PROTECTED_FILE_PATTERNS — dort trafe 3b schon eine blosse Erwaehnung (`echo "… <pfad>"
# >> notes.md`). Geprueft werden nur echte Schreibziele. Parallelkopie in edit_gate.py.
PROOF_FILE_PATTERNS = [r"(?:^|/)docs/artifacts/[^/]+/simulator-run(?:\.txt|/.*)?$"]

# Zustandsordner als ganzes Token (#407): `.claude`, `.claude/workflows`
# (optional ./, Praefixpfad, abschliessender Slash). Nur fuer 3b. Bewusst
# NICHT `.claude/worktrees/…` und `.claude/hooks` (wie _cd_into_claude).
PROTECTED_DIR_TOKEN_PATTERNS = [
    r"(?<![\w.-])(?:\./)?(?:[^\s'\"]*/)?\.claude(?:/+workflows)?(?:/+\.{1,2})*/*(?=[\s\"';&|)]|$)",
]

# Glob im letzten Pfadteil (#410): `.claude/workflows/fix*`. Wie die Ordner-
# Token nur bei aktivem Workflow (#407 AC-9), daher nicht in der Liste oben.
PROTECTED_GLOB_PATTERNS = [r"\.claude/workflows/[^\s/]*[*?[][^\s]*"]

# Verweis-/Kopierbefehle als KOMMANDOWORT (#407): Segmentanfang, nach
# ; & | ( oder Praefix (sudo/env/VAR=x), im Roh-Text auch nach `-c "`/`eval "`.
# Kein `\bln\b` — das traefe `ls -ln`; `pip install`/`npm install` zaehlen nicht.
_LINK_COMMAND_RE = re.compile(
    r"(?:^|[;&|(\n]|(?:-c|\beval)\s+['\"])\s*"
    r"(?:(?:sudo|env|command|nice|nohup|time|exec|[A-Za-z_]\w*=\S*)\s+)*"
    r"(?:[^\s;&|()'\"]*/)?(?:ln|link|install|rsync)(?=[\s;&|)'\"]|$)"
)

# Approval-/Erfolgs-Marker: Dateien, deren blosse Existenz einen Freigabe-
# oder Erfolgszustand BEHAUPTET. Diese darf der Agent NIEMALS selbst per Bash
# erzeugen/aendern/loeschen — das waere "specification gaming" (der Agent
# manipuliert den Verifier statt die Bedingung echt zu erfuellen). Der einzige
# legitime Erzeuger ist phase_listener.py (UserPromptSubmit-Hook), der nur
# feuert, wenn der echte User eine der konfigurierten Freigabe-Phrasen tippt
# (workflow.approval_phrases / green_phrases, override_token.keywords).
# Deny by default.
# Tier 1: Feldnamen mit hohem Freitext-Risiko (Issue #30) — nur blocken, wenn
# zusaetzlich ein echter Protected-Pfad im selben Kommando referenziert wird.
# Diese Feldnamen tauchen plausibel in Bug-Reports/PR-Texten/Doku auf.
APPROVAL_MARKER_PATTERNS_REQUIRE_PATH = [
    r"adversary_verdict",
    r"_verified\b",
]

# Tier 2: Marker-*Dateinamen*-Praefixe — erscheinen praktisch nie als Freitext,
# bleiben unabhaengig vom Pfad-Kontext blockierend (verhindert cd-Obfuskation
# wie `cd .claude && touch user_approved_validation_x`).
APPROVAL_MARKER_PATTERNS_FILENAME = [
    r"user_approved_",
    r"pending_validation_",
]

# Hinweis: "echo"/"printf" sind bewusst KEINE eigenstaendigen Write-Indicators.
# Sie schreiben nur via Redirect (>, >>) oder Pipe-to-tee — beides wird separat
# erfasst (tee unten; Redirects ueber den >{1,2}-Regex in _has_write_indicator).
# Als Standalone erzeugten sie False Positives: reine Status-Prints (echo "OK",
# printf ...) in Lese-/Diagnosebefehlen, die nebenbei einen geschuetzten Pfad
# referenzieren (z.B. `grep x .claude/hooks/y.py && echo done`), wurden
# faelschlich als State-Manipulation blockiert.
# Kurz-Kommandos MIT Wortgrenze am Anfang (Issue #64): ohne `\b` matchte
# `rm\s` jedes Wort, das auf rm endet ("Langform ", "Plattform ") — Freitext
# in Issue-Bodies/Doku loeste den State-Integrity-Block aus.
WRITE_INDICATORS = [
    # Issue #1478 Teil 1: Wortgrenze noetig, sonst matcht "json\.dump" als
    # Praefix auch innerhalb von "json.dumps(...)" (reines Serialisieren,
    # kein Schreibvorgang).
    r"json\.dump\b", r"open\(", r"write\(", r"\bsed\s+-i", r"\bmv\s", r"\bcp\s",
    r"python3?\s+-c", r"\btee\s", r"\brm\s",
    r"\btouch\s", r"\bcat\s*<<", r"\bunlink\b", r"\btruncate\b",
]

WHITELIST_COMMANDS = [
    "workflow.py", "qa_gate.py",
    "git add", "git commit", "git diff",
    "git status", "git log", "git push",
]

# Credential patterns to detect hardcoded secrets in bash commands
HARDCODED_CREDENTIAL_PATTERNS = [
    (r"sk-[A-Za-z0-9]{20,}", "API key (sk- prefix)"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub Personal Access Token"),
    (r"xoxb-[A-Za-z0-9-]{20,}", "Slack Bot token"),
    (r"Bearer\s+(?!\$|\{|<)[A-Za-z0-9._~+/=-]{40,}", "hardcoded Bearer token"),
    (r"(?:password|passwd)\s*=\s*['\"][^'\"\$\{<]{8,}['\"]", "hardcoded password"),
    (r"(?:api_key|apikey|api-key)\s*=\s*['\"][^'\"\$\{<]{8,}['\"]", "hardcoded API key"),
]

# E2E scope detection patterns (configurable via config.yaml → e2e_scope)
E2E_DOCS_PATTERNS = [r'^docs/', r'\.md$', r'^\.claude/']
E2E_FRONTEND_PATTERNS = [r'^(frontend|ui|client)/', r'^src/.*\.(svelte|vue|tsx|jsx|css|scss|html)$']
E2E_BACKEND_PATTERNS = [r'^(src|api|internal|cmd|backend|server)/']


# --- Config loading ---

def _load_config_values() -> dict:
    try:
        from config_loader import load_config
        return load_config()
    except Exception:
        return {}


# --- Helpers ---

_root = find_project_root()


def _measurement_root() -> Path:
    """Arbeitsbaum, in dem der Commit wirklich passiert — Ziel jedes `git diff`.

    `_root` loest einen Worktree bewusst auf das HAUPTREPO auf. Richtig fuer
    geteilten ZUSTAND (`.claude/workflows/*.json` liegen dort fuer alle
    Sitzungen), falsch fuer eine MESSUNG am Arbeitsbaum: der Commit passiert im
    Worktree, im Hauptrepo ist nichts vorgemerkt. Die Liste kommt leer zurueck,
    `_detect_e2e_scope` meldet dann immer `docs-only` (und `/70-deploy`
    ueberspringt die Staging-Validierung), `required_staged_files` kann nie
    greifen — Issue #155, gleiche Fehlerklasse wie #96 und #144.

    Pro Aufruf aufgeloest, nicht beim Import: der Worktree-Kontext haengt am CWD.
    """
    try:
        from hook_utils import find_worktree_root
        worktree_root = find_worktree_root()
    except Exception:
        worktree_root = None
    return worktree_root if worktree_root is not None else _root



def _whitelist_matches(command: str, entry: str) -> bool:
    """Ein Whitelist-Eintrag greift nur bei echtem AUFRUF, nicht bei Erwaehnung.

    Zwei Eintragsformen, eine Semantik (Issue #1431):
      * "git <unterbefehl>" -> tokenbasierte git-Erkennung, deckt damit auch
        `git -C /pfad add`, `git -c k=v commit`, `git --no-pager push` ab.
      * alles andere ("workflow.py", "qa_gate.py", Projekt-Whitelist) ->
        Token-Folge im Kommando. Das erste Wort darf als Pfad auftreten
        (`python3 .claude/hooks/workflow.py` trifft "workflow.py"), Folgewoerter
        muessen exakt als eigene Token stehen.

    Unzerlegbares Kommando (kaputte Quotes) -> altes Teilstring-Verhalten,
    damit die Whitelist fail-open bleibt und niemand ausgesperrt wird.
    """
    parts = entry.split()
    if not parts:
        return False
    if len(parts) == 2 and parts[0] == "git":
        # Bewusst die STRENGE Variante: ein Whitelist-Treffer ueberspringt
        # State-Integrity und Credential-Pruefung. Ueber-Erkennung ist hier die
        # gefaehrliche Richtung — die Zweifels-Regel von is_git_subcommand()
        # darf eine blosse Erwaehnung nicht zum Freifahrtschein machen
        # (`python3 -c "…"  # git commit`).
        return parts[1] in git_head_subcommands(command)
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return entry in command
    n = len(parts)
    for i in range(len(tokens) - n + 1):
        head = tokens[i]
        if head != parts[0] and not head.endswith("/" + parts[0]):
            continue
        if tokens[i + 1:i + n] == parts[1:]:
            return True
    return False


def _is_whitelisted(command: str) -> bool:
    """Whitelisted nur, wenn JEDES Segment einen Whitelist-Eintrag trifft (#299).

    `git status && sed -i … <state>` ist damit nicht mehr whitelisted. Nicht
    zerlegbare Kommandos (kaputte Quotes) behalten das alte Verhalten
    (irgendein Treffer genuegt), damit niemand ausgesperrt wird.
    """
    entries = _whitelist_entries()
    segments = _git_segments(command)
    if segments is None:
        return any(_whitelist_matches(command, allowed) for allowed in entries)
    return bool(segments) and all(_segment_whitelisted(seg, entries) for seg in segments)


def _whitelist_entries() -> list:
    config = _load_config_values()
    return WHITELIST_COMMANDS + config.get("bash_gate", {}).get("whitelist", [])


def _segment_whitelisted(segment: list, entries: list) -> bool:
    return any(_whitelist_matches(shlex.join(segment), allowed) for allowed in entries)


def _protected_outside_whitelist(scan_cmd: str, command: str, dirs: bool = False) -> bool:
    """Nennt ein NICHT-whitelisted Segment einen geschuetzten Pfad? (#299, 2b)

    `workflow.py status 2>&1 | tee out.log`: der Pfad steht nur im
    whitelisted Segment -> zaehlt fuer 3b nicht. Nicht zerlegbar -> wie
    bisher auf den ganzen Befehl (fail-open). `dirs`: Zustandsordner (#407).
    """
    def hit(text: str) -> bool:
        return _references_protected(text) or (dirs and (
            _writes_state_dir(text) or _matches_file_token(text, PROTECTED_GLOB_PATTERNS)))

    segments = _git_segments(scan_cmd)
    if segments is None:
        return hit(scan_cmd) and not _is_whitelisted(command)
    entries = _whitelist_entries()
    return any(
        hit(shlex.join(seg)) and not _segment_whitelisted(seg, entries)
        for seg in segments
    )


def _writes_state_dir(text: str) -> bool:
    """Zustandsordner-Token UND Schreib-/Verweisbefehl im selben Segment (#407).

    `ls .claude && rm docs/x` bleibt frei: der Ordner wird nur gelesen.
    """
    return (_matches_file_token(text, PROTECTED_DIR_TOKEN_PATTERNS)
            and _has_write_indicator(text, links=True))


def _strip_leading_separators(token: str) -> str:
    """Fuehrende Trenner vor einer Umleitung abschneiden (`;>` -> `>`).

    Der Lexer verschmilzt `git status;>x` zu `;>`. `&>`, `&>>` und `>|`
    bleiben erhalten; nur `&&` vorne ist ein Trenner, ein einzelnes `&` nicht.
    """
    tok = token.lstrip(";()|\n")
    while tok.startswith("&&"):
        tok = tok[2:].lstrip(";()|\n")
    return tok


def _redirects_to_protected(scan_cmd: str) -> bool:
    """Leitet irgendein Segment (auch whitelisted) Ausgabe auf State/Marker um? (#316)

    `git status > <state>`: der Pfad ist nur Umleitungsziel hinter einem
    erlaubten Befehl. `>&N`, `>&-` und `/dev/null` sind kein Datei-Write.
    Nicht zerlegbar -> False (fail-open, wie bisher).
    """
    tokens = _git_lex(scan_cmd)
    if tokens is None:
        return False
    patterns = PROTECTED_FILE_PATTERNS + APPROVAL_MARKER_PATTERNS_FILENAME
    for raw, target in zip(tokens, tokens[1:]):
        tok = _strip_leading_separators(raw)
        if not (_is_git_redirect(tok) and ">" in tok and "<" not in tok):
            continue
        if target == "/dev/null" or target == "-" or target.isdigit():
            continue
        if any(re.search(p, target) for p in patterns):
            return True
    return False


def _cd_into_claude(segment: list) -> bool:
    """Wechselt das Segment per cd/pushd in `.claude` oder `.claude/workflows`?

    Nur dort liegen State-Dateien und Marker. `.claude/worktrees/<name>`,
    `.claude/hooks` usw. zaehlen nicht — sonst blockt jede Arbeit im Worktree.
    """
    if not segment or segment[0] not in ("cd", "pushd"):
        return False
    args = [a for a in segment[1:] if not a.startswith("-")]
    if not args:
        return False
    parts = [p for p in args[0].split("/") if p]
    return any(
        p == ".claude" and (i == len(parts) - 1 or parts[i + 1] == "workflows")
        for i, p in enumerate(parts)
    )


def _cd_context_protected(scan_cmd: str) -> bool:
    """Nach `cd .claude/…` gelten bloße `.json`-/Marker-Namen als geschuetzt (#316).

    Nicht zerlegbar -> False (fail-open).
    """
    segments = _git_segments(scan_cmd)
    if segments is None:
        return False
    patterns = [r"\.json\b"] + APPROVAL_MARKER_PATTERNS_FILENAME
    in_claude = False
    for seg in segments:
        if in_claude and _matches_file_token(shlex.join(seg), patterns):
            return True
        in_claude = in_claude or _cd_into_claude(seg)
    return False


def _dir_token_in_cd_context(segments: list) -> bool:
    """Nach `cd .claude[/workflows]` ein nacktes `workflows`/`.` mit Verweis-/Schreibbefehl (#410).

    `cd .claude && ln -s workflows ../w` blockt; `cd .claude && ls workflows`
    und `cd .claude/worktrees/x && cp a b` bleiben frei.
    """
    in_claude = False
    for seg in segments:
        if in_claude and any(t.rstrip("/") in ("workflows", ".") for t in seg
                             if t and t != "/") \
                and _has_write_indicator(shlex.join(seg), links=True):
            return True
        in_claude = in_claude or _cd_into_claude(seg)
    return False


def _split_redirects(seg: list) -> tuple:
    """Schreib-Umleitungsziele und Restsegment ohne Umleitungen (#418).

    `>`, `>>`, `>|`, `&>`, `>&`: Ziel ist das naechste Token, ausser fd-Ziffer,
    `-` und `/dev/null`. Eingabe-Umleitungen und die fd-Ziffer davor (`2>x`)
    fallen nur aus dem Rest, damit `cp a b 2>/dev/null` `b` als letztes behaelt.
    """
    targets, rest, i = [], [], 0
    while i < len(seg):
        tok = seg[i]
        if tok.isdigit() and i + 1 < len(seg) and _is_git_redirect(seg[i + 1]):
            i += 1
            continue
        if _is_git_redirect(tok):
            dest = seg[i + 1] if i + 1 < len(seg) else ""
            if ">" in tok and "<" not in tok and not (
                    dest.isdigit() or dest in ("-", "/dev/null")):
                targets.append(dest)
            i += 2
            continue
        rest.append(tok)
        i += 1
    return targets, rest


def _command_args(rest: list) -> tuple:
    """Kommandowort (ohne Pfad) und Argumente; Praefixe und Freitext raus (#418)."""
    i = 0
    while i < len(rest) and (rest[i] in ("sudo", "command", "env")
                             or re.match(r"^[A-Za-z_]\w*=", rest[i])):
        i += 1
    if i >= len(rest):
        return "", []
    args, skip = [], False
    for tok in rest[i + 1:]:
        if skip:
            skip = False
        elif tok in SECRETS_FREETEXT_FLAGS:
            skip = True
        else:
            args.append(tok)
    return os.path.basename(rest[i]), args


_QA_STAMP_NAME_RE = re.compile(r"\b(?:write_)?qa_run_stamp\b")
_PYTHON_EXEC_RE = re.compile(r"(?<![\w.-])python[\d.]*(?![\w-])")


def _forges_qa_stamp(command: str) -> bool:
    """Stempel-Name + Python-Ausfuehrung im Kommando, Freitext ausgenommen (#404 F003).

    Roh-Tokens des VOLLEN Kommandos (Heredoc-Bodies und `-c`-Code sind Code,
    kein Freitext); nur Werte von SECRETS_FREETEXT_FLAGS fallen weg (#30/#53).
    Nicht zerlegbar -> Roh-Scan (fail-closed).
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = [command]
    kept, skip = [], False
    for tok in tokens:
        if skip:
            skip = False
        elif tok in SECRETS_FREETEXT_FLAGS:
            skip = True
        else:
            kept.append(tok)
    text = "\n".join(kept)
    return bool(_QA_STAMP_NAME_RE.search(text) and _PYTHON_EXEC_RE.search(text))


def _positional(args: list, value_flags: tuple = ()) -> list:
    """Nicht-Flag-Argumente; Werte von `value_flags` und Flags fallen weg, `--` beendet Flags."""
    out, skip, only_pos = [], False, False
    for tok in args:
        if skip:
            skip = False
        elif only_pos or not tok.startswith("-") or tok == "-":
            out.append(tok)
        elif tok == "--":
            only_pos = True
        elif tok in value_flags:
            skip = True
    return out


def _copy_targets(args: list) -> list:
    """cp/install/ln: letztes Argument, bei `-t DIR` je Quelle `DIR/<basename>`."""
    target_dir = None
    for i, tok in enumerate(args):
        if tok == "-t" and i + 1 < len(args):
            target_dir = args[i + 1]
        elif tok.startswith("--target-directory="):
            target_dir = tok.split("=", 1)[1]
    pos = _positional(args, ("-t", "-m", "-o", "-g", "-S"))
    if target_dir is not None:
        return [os.path.join(target_dir, os.path.basename(p.rstrip("/"))) for p in pos]
    return pos[-1:]


def _sed_targets(args: list) -> list:
    """sed nur In-Place (`-i`, `-ni`, `-i.bak`, `-i ''`, `--in-place[=SUF]`)."""
    inplace = explicit = skip = False
    pos = []
    for tok in args:
        if skip:
            skip = False
        elif tok.startswith("--in-place"):
            inplace = True
        elif tok in ("--expression", "--file"):
            explicit = skip = True
        elif tok.startswith(("--expression=", "--file=")):
            explicit = True
        elif tok.startswith("-") and not tok.startswith("--") and len(tok) > 1:
            for j, ch in enumerate(tok[1:]):
                if ch == "i":
                    inplace = True
                    break
                if ch in "ef":
                    explicit = True
                    skip = j == len(tok) - 2
                    break
        elif tok:
            pos.append(tok)
    if not inplace:
        return []
    return pos if explicit else pos[1:]


def _perl_targets(args: list) -> list:
    """perl nur mit `-i`-Cluster (`-pi`, `-i.bak`); `-e`-Skript wird uebersprungen."""
    inplace = has_e = skip = False
    pos = []
    for tok in args:
        if skip:
            skip = False
        elif tok.startswith("-") and not tok.startswith("--") and len(tok) > 1:
            for j, ch in enumerate(tok[1:]):
                if ch == "i":
                    inplace = True
                    break
                if ch in "eE":
                    has_e = True
                    skip = j == len(tok) - 2
                    break
                if ch in "IMmlx0FCdD":
                    break
        elif tok:
            pos.append(tok)
    if not inplace:
        return []
    return pos if has_e else pos[1:]


def _git_write_targets(args: list) -> list:
    """git checkout/restore/rm/mv: alle Pfadargumente (Branchnamen loesen nie auf die Config auf).

    `-C <pfad>` (auch mehrfach, kumulativ) wird relativen Pfaden vorangestellt (#417).
    """
    pos = _positional(args, ("-C", "-c"))
    if not pos or pos[0] not in ("checkout", "restore", "rm", "mv"):
        return []
    sub = args.index(pos[0])
    cdir = ""
    for i, tok in enumerate(args[:sub]):
        if tok == "-C" and i + 1 < sub:
            cdir = os.path.join(cdir, args[i + 1])
    paths = _positional(args[sub + 1:], ("-s", "--source", "-b", "-B"))
    return [os.path.join(cdir, p) for p in paths] if cdir else paths


_CONFIG_WRITERS = {
    "cp": _copy_targets, "install": _copy_targets, "ln": _copy_targets,
    # mv: Quellen UND Ziel zaehlen; bei `-t DIR` zusaetzlich `DIR/<basename>` (#417).
    "mv": lambda a: list(dict.fromkeys(_positional(a, ("-t", "-S")) + _copy_targets(a))),
    "rm": _positional, "unlink": _positional, "tee": _positional,
    "truncate": lambda a: _positional(a, ("-s", "-r")),
    "touch": lambda a: _positional(a, ("-d", "-t", "-r")),
    "sed": _sed_targets, "perl": _perl_targets, "git": _git_write_targets,
    "dd": lambda a: [t[3:] for t in a if t.startswith("of=")],
    "yq": lambda a: _positional(a) if ("-i" in a or "--inplace" in a) else [],
}


def _config_write_targets(seg: list) -> list:
    """Nur die Tokens, die das Segment beschreibt, ersetzt, entfernt oder verlinkt (#418).

    Lese-Quellen zaehlen nie. Leere Tokens (`sed -i ''`) fallen weg, sonst
    traefe die Aufloesung die Basis selbst.
    """
    targets, rest = _split_redirects(seg)
    cmd, args = _command_args(rest)
    writer = _CONFIG_WRITERS.get(cmd)
    if writer is not None:
        targets += writer(args)
    return [t for t in targets if t]


def _cd_bases(seg: list, bases: list, cwd: Path) -> list:
    """Basis nach `cd`/`pushd` nachfuehren (#418).

    Nicht aufloesbar (`cd $X`, `cd -`, `cd` ohne Ziel, Glob, Backtick, `popd`):
    alte Basis UND cwd bleiben im Spiel — kein neuer Block-Grund.
    """
    args = [a for a in seg[1:] if not a.startswith("-")]
    target = args[0] if args else ""
    if seg[0] == "popd" or not target or any(ch in target for ch in "$`*?["):
        return list(dict.fromkeys(bases + [cwd]))
    return [(b / os.path.expanduser(target)).resolve() for b in bases]


def _segment_write_targets(segments: list, cwd: Path):
    """Je Schreib-Segment `(basen, ziele)`; Basis ueber `cd`/`pushd`/`popd` nachgefuehrt (#418, #417).

    Gemeinsame Zielerkennung fuer 1b (wirksame Config) und 1c (Haupt-Ordner).
    Segmente ohne Schreibziel fallen weg. Fehler in einem Segment beenden die
    Aufzaehlung (fail-open beim Aufrufer).
    """
    bases = [cwd]
    for seg in segments:
        if seg[0] in ("cd", "pushd", "popd"):
            bases = _cd_bases(seg, bases, cwd)
            continue
        targets = _config_write_targets(seg)
        if targets:
            yield bases, targets, seg


def _dir_removal_targets(cmd: str, args: list) -> list:
    """Pfade, die `rm`/`mv`/`git rm|mv|checkout|restore` samt Inhalt entfernt,
    wegbewegt oder ueberschreibt (#473 F002).

    Beim Verschieben nur die Quellen: `mv x .claude` legt etwas IN den Ordner,
    das ist kein Entfernen.
    """
    if cmd == "rm":
        return _positional(args)
    if cmd == "mv":
        pos = _positional(args, ("-t", "-S"))
        if "-t" in args or any(a.startswith("--target-directory") for a in args):
            return pos
        return pos[:-1]
    if cmd == "git":
        paths = _git_write_targets(args)
        sub = _positional(args, ("-C", "-c"))[:1]
        return paths[:-1] if sub == ["mv"] else paths
    return []


def _lexical_path(base: Path, token: str) -> str:
    """Absoluter Pfad, nur der Elternordner aufgeloest (#473 F002).

    Der letzte Bestandteil bleibt ungeloest: `rm link` entfernt nur den Link,
    nicht dessen Ziel-Ordner.
    """
    norm = os.path.normpath(os.path.abspath(base / os.path.expanduser(token)))
    return os.path.join(os.path.realpath(os.path.dirname(norm)), os.path.basename(norm))


def _removes_config_dir(seg: list, bases: list, protected: list, root: Path) -> bool:
    """`mv|rm|git … <ordner>`: liegt eine vorhandene geschuetzte Config IN dem Ordner? (#473 F002)

    Nur echte Vorfahren innerhalb der Projektwurzel, nie die Wurzel selbst:
    `rm -rf <projekt>` ist kein gezielter Kill-Switch-Umweg, sondern loescht
    Hooks und Repo gleich mit — und ein Block auf `.`/die Wurzel traefe
    alltaegliche Aufraeumbefehle (`git checkout .`, `git restore .`).
    """
    targets = _dir_removal_targets(*_command_args(_split_redirects(seg)[1]))
    if not targets:
        return False
    root_real = os.path.realpath(str(root))
    existing = [os.path.realpath(str(p)) for p in protected if Path(p).exists()]
    for b in bases:
        for t in targets:
            if any(ch in t for ch in "$`*?["):
                continue
            hit = _lexical_path(b, t)
            if hit == root_real or not hit.startswith(root_real + os.sep):
                continue
            if any(p.startswith(hit + os.sep) for p in existing):
                return True
    return False


def _writes_effective_config(segments: list, cwd: Path) -> bool:
    """Schreibt ein Segment auf die WIRKSAME Gate-Config (#410, #418) oder legt
    eine vorrangige an (#473)?

    Geschuetzt = `protected_config_paths(find_project_root())` (im Worktree der
    Hauptordner; ohne Inhalt, Shell-Inhalt ist nicht zuverlaessig lesbar).
    Verglichen werden nur echte Schreibziele, aufgeloest gegen die ueber
    `cd`/`pushd` nachgefuehrte Basis. Die Worktree-Kopie loest auf eine andere
    Datei auf und bleibt frei. `mv|rm|git` auf einen Ordner, der die wirksame
    Config enthaelt (`rm -rf .claude`), zaehlt ebenfalls (#473 F002). Fehler: fail-open.
    """
    protected = None
    try:
        for bases, targets, seg in _segment_write_targets(segments, cwd):
            if protected is None:
                from config_loader import protected_config_paths, config_path_hit
                root = find_project_root()
                protected = protected_config_paths(root)
                if not protected:
                    return False
            if any(config_path_hit(b / os.path.expanduser(t), protected)
                   for b in bases for t in targets):
                return True
            if _removes_config_dir(seg, bases, protected, root):
                return True
    except Exception:
        return False
    return False


# Bewusste Parallelkopie des Regex aus worktree_write_guard.py (kein geteilter Import).
_WORKTREE_CWD_RE = re.compile(r"^(?P<main>.*)/\.claude/worktrees/(?P<name>[^/]+)")


def _into_dir_targets(seg: list, bases: list) -> list:
    """`cp|mv|install|ln SRC… DIR`: je Quelle `DIR/<basename>` (#447).

    Nur wenn das Ziel auf `/` endet oder gegen eine Basis ein vorhandener Ordner ist;
    `-t DIR` deckt `_copy_targets` bereits ab.
    """
    cmd, args = _command_args(_split_redirects(seg)[1])
    if cmd not in ("cp", "mv", "install", "ln") or "-t" in args \
            or any(a.startswith("--target-directory") for a in args):
        return []
    pos = _positional(args, ("-m", "-o", "-g", "-S"))
    if len(pos) < 2:
        return []
    dest = pos[-1]
    if not (dest.endswith("/") or any((b / os.path.expanduser(dest)).is_dir() for b in bases)):
        return []
    return [os.path.join(dest, os.path.basename(p.rstrip("/"))) for p in pos[:-1]]


# --- 1d-Haertung (#448): nur fuer den Beleg, `_CONFIG_WRITERS` bleibt fuer 1b/1c unveraendert (#452).
# Vorfahr-/Link-Regel: `docs/artifacts`, `docs/artifacts/<x>` oder ein Beleg-Pfad.
_PROOF_LINK_PATTERNS = PROOF_FILE_PATTERNS + [r"(?:^|/)docs/artifacts(?:/[^/]+)?$"]
# Ordnerziel (`tar -C`, `unzip -d`): Beleg-Bereich `docs/artifacts` und darunter.
_PROOF_AREA_PATTERNS = [r"(?:^|/)docs/artifacts(?:/.*)?$"]
_PROOF_MENTION_RE = re.compile(r"docs/artifacts/[^/\s'\"]+/simulator-run")
# Enger Schreibindikator fuer Inline-Code (ADR 3): reines `open(PROOF)` bleibt frei.
_INLINE_WRITE_RE = re.compile(
    # #453: eine Klammerebene im ersten Argument (`os.getenv('X')`), Keyword `mode=`.
    r"open\s*\((?:[^()]|\([^()]*\))*,\s*(?:mode\s*=\s*)?['\"][rbt]*[wax+][rwabxt+]*['\"]"
    r"|open\s*\(\s*(?:my\s+)?[$\w]+\s*,\s*['\"]\s*\+?>"
    r"|write_text|write_bytes|writeFile|appendFile|createWriteStream"
    r"|shutil\.(?:copy\w*|move)|os\.(?:rename|replace|remove|unlink|symlink|link)\b"
    r"|\.(?:touch|unlink|rename|symlink_to)\s*\("
    # #453: ruby-Schreiber und Shell-Aufrufe aus dem Inline-Code (F006).
    r"|\bFile\.(?:bin)?write|\bIO\.(?:bin)?write"
    r"|os\.(?:system|popen|exec\w*|spawn\w*)|subprocess\."
    # `exec(` nicht als Methode (`/re/.exec(…)`); Backtick nur ruby/perl (`_inline_hit`).
    r"|child_process|execSync|execFileSync|spawnSync|\bsystem\s*\(|(?<![.\w])exec\s*\(|\bqx\b")
_INTERPRETER_RE = re.compile(r"^(?:python[\d.]*|node|perl|ruby)$")
# Je Interpreter: Code-Flag (Regex) und Optionen, die den naechsten Token als Wert nehmen (#453).
_INTERP_OPTS = {
    "python": (r"^-[A-Za-z]*c$", ("-W", "-X", "-Q")),
    "node": (r"^-[A-Za-z]*[ep]$|^--(?:eval|print)(?:=|$)",
             ("-r", "--require", "--input-type", "-C", "--conditions", "--import", "--loader")),
    "perl": (r"^-[A-Za-z]*[eE]$", ("-I", "-M", "-x")),
    "ruby": (r"^-[A-Za-z]*e$", ("-I", "-r", "-C", "-E", "--encoding")),
}
# Inline-Code liest die Umgebung (Praefix-Zuweisung `X=P python3 -c …`, #453 F005).
_ENV_READ_RE = re.compile(r"environ|getenv|process\.env|\$ENV\{|\bENV\[")
# Einstufige Zuweisung eines Literals bzw. `Path('…')` an einen Bezeichner (ADR-3, #453).
_LITERAL_ASSIGN_RE = re.compile(
    r"^\s*(?:(?:my|let|const|var)\s+)?\$?([A-Za-z_]\w*)\s*=\s*"
    r"(?:[\w.]+\(\s*)?(['\"])[^'\"]*\2\s*\)?\s*$")
_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")
# Praefixe vor dem Kommandowort -> Flags, die einen Wert nehmen.
_PROOF_PREFIXES = {
    "sudo": ("-u", "-g", "-C", "-D", "-h", "-p", "-U", "-r", "-t"), "command": (),
    "env": ("-u", "-C", "-S"), "timeout": ("-s", "--signal", "-k", "--kill-after"),
    "nohup": (), "nice": ("-n", "--adjustment"), "stdbuf": ("-i", "-o", "-e"),
    "time": ("-f", "-o"), "exec": ("-a",),
    # #453 (F002, ADR-2): geschlossene Liste erweitert.
    "doas": ("-u", "-C"), "busybox": (), "flock": ("-w", "-E", "--timeout", "--conflict-exit-code"),
    "ionice": ("-c", "-n", "-p", "--class", "--classdata", "--pid"), "setsid": (), "taskset": (), "chronic": (), "builtin": (),
    "xargs": ("-a", "-d", "-E", "-I", "-L", "-n", "-P", "-s", "--arg-file", "--delimiter",
              "--eof", "--replace", "--max-lines", "--max-args", "--max-procs", "--max-chars"),
}


def _opt_values(args: list, flags: tuple) -> list:
    """Werte von `-o X`, `-sSo X` (Buendel endet auf das Flag), `--output X`, `--output=X`.

    #453: angehaengter Wert (`-oDATEI`, `-sSoDATEI`): getopt, Rest nach dem ersten Flag-Buchstaben.
    """
    out = []
    for i, tok in enumerate(args):
        nxt = args[i + 1] if i + 1 < len(args) else ""
        for f in flags:
            attached = len(f) == 2 and re.match(rf"^-[A-Za-z]*?{f[1]}(.+)$", tok)
            if f.startswith("--") and tok.startswith(f + "="):
                out.append(tok.split("=", 1)[1])
            elif tok == f or (len(f) == 2 and re.match(rf"^-[A-Za-z]*{f[1]}$", tok)):
                out.append(nxt)
            elif attached:
                out.append(attached.group(1))
    return [o for o in out if o]


def _tar_dir(a: list) -> list:
    """`tar -C DIR` nur beim Entpacken (`-x`, `xf`, `--extract`); Packen liest nur."""
    extract = any(re.match(r"^-?[A-Za-z]*x[A-Za-z]*$", t) or t in ("--extract", "--get")
                  for t in a[:1] + [t for t in a if t.startswith("-")])
    return _opt_values(a, ("-C", "--directory")) if extract else []


def _tar_archive(a: list) -> list:
    """`tar` packen (`c`/`r`/`u`/`A`, `--create`/`--append`/`--update`): Archiv `-f` ist Ziel (#453)."""
    # Modus-Buchstaben bis zum ersten `f`; danach ist der Rest der Archivpfad (getopt, `-cfP`).
    bundles = [m.group(1) for m in (re.match(r"^-([A-Za-z]+)", t) for t in a) if m] + \
        [t for t in a[:1] if re.match(r"^[A-Za-z]+$", t)]
    create = any(re.search(r"[cruA]", t.split("f")[0]) for t in bundles) or any(
        t in ("--create", "--append", "--update", "--catenate", "--concatenate") for t in a)
    if not create:
        return []
    old = a[1:2] if a and re.match(r"^[A-Za-z]*f[A-Za-z]*$", a[0]) else []
    return _opt_values(a, ("-f", "--file")) + old


# Zusatz-Schreiber nur fuer 1d; `rsync` deckt die Vorfahr-/Link-Regel (Quelle UND Ziel) ab.
_PROOF_WRITERS = {
    "curl": lambda a: _opt_values(a, ("-o", "--output")),
    "wget": lambda a: _opt_values(a, ("-O", "--output-document")),
    "patch": lambda a: _positional(a, ("-o", "-i", "-p", "-d", "-r", "-D", "-B", "-F", "-V", "-z"))[:1]
    + _opt_values(a, ("-o", "--output")),
    "ed": _positional, "ex": _positional, "tar": _tar_archive,
    # #453 (F003f, ADR-1): nur der exakte Beleg-Pfad; Modus/Eigentuemer trifft nie das Muster.
    "shred": lambda a: _positional(a, ("-n", "-s", "--iterations", "--size", "--random-source")),
    "chmod": _positional, "chown": _positional,
}
_PROOF_DIR_WRITERS = {"tar": _tar_dir, "unzip": lambda a: _opt_values(a, ("-d",))}


def _skip_prefixes(rest: list) -> tuple:
    """Praefixe (`sudo`, `env`, `timeout 5`, `nice -n 5`, `VAR=…`, …) bis zum Kommandowort.

    Liefert `(rest, zuweisungen)`; die Praefix-Zuweisungen bilden die Kindumgebung (#453 F005).
    `flock DATEI -c CMD` wird zu `sh -c CMD`, `taskset MASKE` und `flock DATEI` ueberspringen
    ein Positionsargument.
    """
    i, local = 0, {}
    while i < len(rest):
        word = os.path.basename(rest[i])
        if _ASSIGN_RE.match(rest[i]):
            name, value = rest[i].split("=", 1)
            local[name] = value
            i += 1
            continue
        if word not in _PROOF_PREFIXES:
            break
        i += 1
        while i < len(rest) and rest[i][:1] == "-" and rest[i] != "-":
            if word == "flock" and rest[i] in ("-c", "--command"):
                return ["sh", "-c"] + rest[i + 1:i + 2], local
            i += 2 if rest[i] in _PROOF_PREFIXES[word] else 1
        if word in ("timeout", "taskset", "flock") and i < len(rest):
            i += 1  # Dauer, CPU-Maske bzw. Lock-Datei
            if word == "flock" and i < len(rest) and rest[i] in ("-c", "--command"):
                return ["sh", "-c"] + rest[i + 1:i + 2], local
    return rest[i:], local


def _nested_payload(cmd: str, args: list) -> "str | None":
    """Nutzlast von `bash|sh|zsh|dash|ksh -c '…'` (Buendel mit `c`) bzw. `eval …`."""
    if cmd == "eval":
        return " ".join(args)
    if cmd not in ("bash", "sh", "zsh", "dash", "ksh"):
        return None
    i = 0
    while i < len(args):
        tok = args[i]
        if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", tok):
            return next((a for a in args[i + 1:] if not a.startswith("-")), "")
        if tok in ("-o", "-O", "+o", "+O"):
            i += 1
        elif not tok.startswith(("-", "+")):
            return None  # Skriptdatei: Inhalt unsichtbar (Known Limitation)
        i += 1
    return None


def _inline_code(cmd: str, args: list, raw: str) -> "str | None":
    """Inline-Code eines Interpreters: `-c`/`-e`-Argument, ohne Skript der Rohtext (stdin)."""
    if not _INTERPRETER_RE.match(cmd):
        return None
    code_re, value_opts = _INTERP_OPTS[re.sub(r"[\d.]+$", "", cmd)]
    i = 0
    while i < len(args):
        tok = args[i]
        if re.match(code_re, tok):
            if tok.startswith("--") and "=" in tok:
                return tok.split("=", 1)[1]
            return args[i + 1] if i + 1 < len(args) else ""
        if not tok.startswith("-") or (cmd.startswith("python") and tok.startswith("-m")):
            return None  # Skriptdatei bzw. `-m MODUL` (Erzeuger `scripts/sim_proof.py`) zaehlt nicht
        i += 2 if tok in value_opts else 1
    return raw  # `-` bzw. ohne Argument: Code kommt per Heredoc/Pipe aus dem Befehl


def _statements(code: str) -> list:
    """Anweisungen: Trennung an Zeilenumbruch, `;` nur ausserhalb von Quotes derselben Zeile (#453)."""
    out = []
    for line in code.split("\n"):
        cur, quote, esc = "", "", False
        for ch in line:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif quote:
                quote = "" if ch == quote else quote
            elif ch in "'\"`":
                quote = ch
            elif ch == ";":
                out.append(cur)
                cur = ""
                continue
            cur += ch
        out.append(cur)
    return out


def _inline_hit(code: str, env: dict, backtick: bool = False) -> bool:
    """Eine Anweisung mit Beleg-Erwaehnung UND Schreibindikator (ADR-3, #453)?

    Erwaehnung: Beleg-Pfad, ein zuvor einstufig damit belegter Bezeichner oder ein
    Umgebungs-Lesezugriff, wenn die Kindumgebung den Beleg-Pfad traegt (F005).
    """
    env_hit = any(_PROOF_MENTION_RE.search(v) for v in env.values())
    names = []
    for stmt in _statements(code):
        mention = (bool(_PROOF_MENTION_RE.search(stmt))
                   or (env_hit and bool(_ENV_READ_RE.search(stmt)))
                   or any(re.search(rf"\b{n}\b", stmt) for n in names))
        if mention and (_INLINE_WRITE_RE.search(stmt) or (backtick and "`" in stmt)):
            return True
        m = _LITERAL_ASSIGN_RE.match(stmt)
        if m and _PROOF_MENTION_RE.search(stmt):
            names.append(m.group(1))
    return False


def _cp_target_dir(args: list) -> tuple:
    """`cp -t DIR`, `-vt DIR`, `-tDIR`, `--target-directory[=]DIR` (getopt) -> `(DIR, quellen)` (#453)."""
    tdir, pos, i = None, [], 0
    while i < len(args):
        tok, nxt = args[i], (args[i + 1] if i + 1 < len(args) else "")
        m = re.match(r"^-([A-Za-z]*?)t(.*)$", tok)
        if tok == "--target-directory":
            tdir, i = nxt, i + 1
        elif tok.startswith("--target-directory="):
            tdir = tok.split("=", 1)[1]
        elif m and "S" not in m.group(1):
            tdir = m.group(2) or nxt
            i += 0 if m.group(2) else 1
        elif tok in ("-S", "--suffix"):
            i += 1
        elif not tok.startswith("-") or tok == "-":
            pos.append(tok)
        i += 1
    return tdir, pos


def _cp_dir_targets(cmd: str, args: list) -> list:
    """`cp`/`install` mit Zielordner-Option: je Quelle `DIR/<basename>` (#453 F003b)."""
    if cmd not in ("cp", "install"):
        return []
    tdir, pos = _cp_target_dir(args)
    return [os.path.join(tdir, os.path.basename(p.rstrip("/"))) for p in pos] if tdir else []


def _recursive_copy_hit(cmd: str, args: list, bases: list) -> bool:
    """`cp -r/-R/-a` nach `docs/artifacts[/<x>]`: liegt `simulator-run(.txt)` an Beleg-Stelle (#453)?

    Quelle `X` landet unter `DEST/basename(X)`, `X/.` (oder fehlendes DEST) direkt in `DEST`.
    Geprueft werden nur zwei Ebenen der Quelle, tiefer kann das Muster nicht treffen.
    """
    if cmd != "cp" or not any(t in ("--recursive", "--archive") or re.match(r"^-[A-Za-z]*[rRa]", t)
                              for t in args):
        return False
    tdir, pos = _cp_target_dir(args)
    dest, srcs = (tdir, pos) if tdir else ((pos or [""])[-1], pos[:-1])
    if not srcs or not re.search(r"(?:^|/)docs/artifacts(?:/[^/]+)?$", dest.rstrip("/")):
        return False
    for b in bases:
        d = b / os.path.expanduser(dest)
        for s in srcs:
            src = b / os.path.expanduser(s)
            name = os.path.basename(s.rstrip("/"))
            into = d if name in (".", "") or not d.is_dir() else d / name
            try:  # unlesbar: kein Treffer hier, Rest des Befehls wird weiter geprueft
                if not src.is_dir():
                    continue
                rels = [e.name for e in os.scandir(src)]
                rels += [os.path.join(n, e.name) for n in rels if (src / n).is_dir()
                         for e in os.scandir(src / n)]
            except OSError:
                continue
            if any(re.search(p, str(into / r).replace(os.sep, "/"))
                   for r in rels for p in PROOF_FILE_PATTERNS):
                return True
    return False


def _link_paths(cmd: str, args: list) -> list:
    """Quellen UND Ziele von mv, ln, cp -l/-s/-al, rsync, `git mv` (Vorfahr-/Link-Regel)."""
    if cmd == "git":  # #453 F003d: nur `git mv`; `git rm` ist Zerstoerer (ADR-1)
        return _git_write_targets(args) if _positional(args, ("-C", "-c"))[:1] == ["mv"] else []
    if cmd == "cp" and not any(t in ("--link", "--symbolic-link") or
                               re.match(r"^-[A-Za-z]*[ls]", t) for t in args):
        return []
    if cmd not in ("mv", "ln", "cp", "rsync"):
        return []
    return _positional(args, ("-S", "-e", "--suffix", "--rsh"))


def _expand_target(t: str, bases: list, star: bool = True) -> "list | None":
    """Brace-Listen (verschachtelt, mit Komma) und Globs `?`/`[`/`*` gegen Vorhandenes (#453 F003a).

    Ohne Glob-Treffer bleibt der Literal-Pfad (Bash-Semantik); `${X}` bleibt unberuehrt.
    Ueberlauf der Brace-Expansion: `None` (Aufrufer wertet fail-closed). Unlesbare Ordner:
    kein Glob-Treffer fuer dieses Ziel, der Rest des Befehls wird weiter geprueft.
    """
    import glob
    out, todo = [], [t]
    while todo and len(out) + len(todo) < 128:
        cur = todo.pop()
        m = re.search(r"\{([^{}]*,[^{}]*)\}", cur)
        if m:
            todo += [cur[:m.start()] + alt + cur[m.end():] for alt in m.group(1).split(",")]
        else:
            out.append(cur)
    if todo:
        return None
    hits = []
    for c in (c for c in out if any(ch in c for ch in ("?[*" if star else "?["))):
        for b in bases:
            try:
                hits += glob.glob(os.path.join(str(b), os.path.expanduser(c)))
            except OSError:
                continue
    return out + hits


def _proof_path_hit(t: str, bases: list, patterns: list, star: bool = True) -> bool:
    """Trifft ein Ziel (nach Brace/Glob, #453) normalisiert ODER aufgeloest ein Muster?

    Brace-Ueberlauf mit `simulator-run` im Token: Treffer (fail-closed, #453).
    """
    variants = _expand_target(t, bases, star)
    if variants is None:
        return "simulator-run" in t
    return any(_proof_path_hit_one(v, bases, patterns) for v in variants)


def _proof_path_hit_one(t: str, bases: list, patterns: list) -> bool:
    """Trifft das Ziel normalisiert ODER aufgeloest (Symlinks, ADR 2) ein Muster?"""
    paths = [t] + [str(b / os.path.expanduser(t)) for b in bases]
    if any(re.search(p, os.path.normpath(c).replace(os.sep, "/")) for c in paths for p in patterns):
        return True
    for b in bases:
        try:
            real = str((b / os.path.expanduser(t)).resolve()).replace(os.sep, "/")
        except (OSError, RuntimeError, ValueError):
            continue
        if any(re.search(p, real) for p in patterns):
            return True
    return False


def _proof_fallback(text: str) -> bool:
    """Tiefe > 3 oder Parse-Fehler in der Nutzlast (AC-20): Erwaehnung + Schreibindikator."""
    return bool(_PROOF_MENTION_RE.search(text)) and (
        _has_write_indicator(text) or bool(_INLINE_WRITE_RE.search(text)))


def _env_subst(text: str, env: dict) -> str:
    """`$X`/`${X}` aus der Kindumgebung ersetzen (nur Nutzlast, nie eigene Argumente, #453)."""
    return re.sub(r"\$(?:\{(\w+)\}|(\w+))",
                  lambda m: env.get(m.group(1) or m.group(2), m.group(0)), text)


def _proof_segment_hit(seg: list, cwd: Path, bases: list, depth: int, raw: str,
                       child: "dict | None" = None) -> bool:
    """Ein Segment: Umleitungen, verschachtelte Shell, Inline-Code, Schreiber, Link-Regel.

    `child`: exportierte Variablen; Praefix-Zuweisungen des Segments kommen hinzu (#453 F005).
    """
    targets, rest = _split_redirects(seg)
    rest, local = _skip_prefixes(rest)
    env = {**(child or {}), **local}
    dirs = []
    if rest:
        cmd, args = os.path.basename(rest[0]), rest[1:]
        payload = _nested_payload(cmd, args)
        if payload is not None:
            payload = _env_subst(payload, env)
            if _proof_text_hit(payload, payload, cwd, bases, depth + 1):
                return True
        code = _inline_code(cmd, args, raw)
        if code and _inline_hit(code, env, cmd in ("perl", "ruby")):  # Backtick = Shell
            return True
        if any(_proof_path_hit(t, bases, _PROOF_LINK_PATTERNS) for t in _link_paths(cmd, args)):
            return True
        if _recursive_copy_hit(cmd, args, bases):
            return True
        targets += (_config_write_targets(rest) + _into_dir_targets(rest, bases)
                    + _cp_dir_targets(cmd, args) + _PROOF_WRITERS.get(cmd, lambda a: [])(args))
        dirs = _PROOF_DIR_WRITERS.get(cmd, lambda a: [])(args)
    star = not rest or os.path.basename(rest[0]) not in ("rm", "unlink")  # Zerstoerer: kein `*` (ADR-1)
    return (any(_proof_path_hit(t, bases, PROOF_FILE_PATTERNS, star) for t in targets if t)
            or any(_proof_path_hit(d, bases, _PROOF_AREA_PATTERNS) for d in dirs))


def _proof_text_hit(text: str, raw: str, cwd: Path, bases: list, depth: int) -> bool:
    """Befehlstext zerlegen; Zuweisungen (`X=…`, `export X=…`) ersetzen `$X`/`${X}`, `cd` fuehrt nach.

    Verschachtelte Shells rekursiv bis Tiefe 3; darueber oder bei Parse-Fehler der
    Nutzlast Rueckfall auf `_proof_fallback`. Parse-Fehler auf oberster Ebene: frei.
    """
    if depth > 3:
        return _proof_fallback(text)
    segments = _git_segments(text)
    if segments is None:
        return depth > 0 and _proof_fallback(text)
    env, exported = {}, set()

    def subst(tok: str) -> str:
        return re.sub(r"\$(?:\{(\w+)\}|(\w+))",
                      lambda m: env.get(m.group(1) or m.group(2), m.group(0)), tok)

    for seg in segments:
        if seg[0] == "export" or all(_ASSIGN_RE.match(t) for t in seg):
            for t in seg:
                if _ASSIGN_RE.match(t):
                    name, value = t.split("=", 1)
                    env[name] = subst(value)
                if seg[0] == "export":
                    exported.add(t.split("=", 1)[0])
            continue
        seg = [subst(t) for t in seg]
        if seg[0] in ("cd", "pushd", "popd"):
            bases = _cd_bases(seg, bases, cwd)
        elif _proof_segment_hit(seg, cwd, bases, depth, raw,
                                {k: v for k, v in env.items() if k in exported}):
            return True
    return False


def _writes_proof_file(scan_cmd: str, cwd: Path, raw: str = "") -> bool:
    """Schreibt, verlinkt oder verschiebt der Befehl den Simulator-Beleg (#447, #448)?

    Nur echte Schreibziele (plus Vorfahr-/Link-Regel); zerlegt wird `scan_cmd`
    (Daten-Heredocs entfernt), Inline-Interpreter-Code kommt aus dem Rohtext `raw`.
    Ausnahmen: fail-open wie 1b/1c.
    """
    try:
        return _proof_text_hit(scan_cmd, raw or scan_cmd, cwd, [cwd], 0)
    except Exception:
        return False


# --- Suche ab Wurzel/Home (#462) -------------------------------------------
# Eine Suche ueber die ganze Platte laeuft Stunden und treibt die Maschine in
# Dauerlast (31 h `bfs -S dfs /`). Reine Mustererkennung ohne Modell; ein
# Unterordner (`find ./docs`) bleibt frei.
_SEARCH_BROAD = {"/", "~", "$HOME", "${HOME}", "/home", "/Users", "/root", "/Volumes", "/mnt"}
_FIND_FLAGS = {"-H", "-L", "-P", "-E", "-X", "-x", "-s", "-d"}
_FIND_VALUE_OPTS = {"-S", "-j", "-D", "-f"}
_FD_VALUE_OPTS = ("-e", "-E", "-t", "-d", "-x", "-X", "-j", "-S", "-c",
                  "--extension", "--exclude", "--type", "--max-depth")
_GREP_VALUE_OPTS = ("-e", "-f", "-m", "-A", "-B", "-C", "--include", "--exclude",
                    "--exclude-dir", "--file", "--regexp")
_RG_VALUE_OPTS = ("-e", "-f", "-g", "-t", "-T", "-m", "-A", "-B", "-C", "-j", "--glob",
                  "--type", "--max-count", "--regexp", "--file", "--iglob")


def _is_broad_root(path: str) -> bool:
    p = path.rstrip("/") or "/"
    home = os.path.expanduser("~").rstrip("/")
    return p in _SEARCH_BROAD or (bool(home) and p == home)


def _search_roots(cmd: str, args: list) -> list:
    """Suchwurzeln eines rekursiven Such-Aufrufs; leer, wenn `cmd` keiner ist."""
    if cmd in ("find", "bfs"):
        roots, skip = [], False
        for tok in args:
            if skip:
                skip = False
            elif tok in _FIND_VALUE_OPTS:
                skip = True
            elif tok in _FIND_FLAGS:
                continue
            elif tok.startswith(("-", "(", "!")) or tok == ",":
                break
            else:
                roots.append(tok)
        return roots
    if cmd in ("fd", "fdfind"):
        return _positional(args, _FD_VALUE_OPTS)[1:]
    if cmd in ("rg", "ag", "ack"):
        pos = _positional(args, _RG_VALUE_OPTS)
    elif cmd in ("grep", "egrep", "fgrep"):
        recursive = any(a in ("--recursive", "--dereference-recursive")
                        or (a.startswith("-") and not a.startswith("--") and re.search(r"[rR]", a))
                        for a in args)
        if not recursive:
            return []
        pos = _positional(args, _GREP_VALUE_OPTS)
    else:
        return []
    has_pattern = any(a in ("-e", "-f", "--regexp", "--file") for a in args)
    return pos if has_pattern else pos[1:]


def _broad_search_hit(scan_cmd: str) -> "str | None":
    """Erstes Such-Kommando, das ab `/`, `~` oder $HOME sucht; sonst None (fail-open)."""
    try:
        for seg in _git_segments(scan_cmd) or []:
            rest, _ = _skip_prefixes(seg)
            if not rest:
                continue
            cmd = os.path.basename(rest[0])
            for root in _search_roots(cmd, rest[1:]):
                if _is_broad_root(root):
                    return f"{cmd} {root}"
    except Exception:
        return None
    return None


def _writes_main_repo(segments: list, cwd: Path) -> "str | None":
    """Schreibziel im Haupt-Ordner, aber ausserhalb des eigenen Worktrees (#417)?

    Nur aktiv, wenn `cwd` in einem Worktree liegt; sonst `None` (Haupt-Ordner-
    Sitzung unveraendert). Fremde Worktrees unter dem Haupt-Ordner bleiben
    gesperrt. Nicht aufloesbare Ziele (`$VAR`, Glob, Backtick) und Fehler:
    fail-open. Liefert das aufgeloeste Ziel oder `None`.
    """
    try:
        m = _WORKTREE_CWD_RE.match(str(cwd))
        if not m:
            return None
        main_dir = Path(m.group("main")).resolve()
        own = (Path(m.group("main")) / ".claude" / "worktrees" / m.group("name")).resolve()
        for bases, targets, _seg in _segment_write_targets(segments, cwd):
            for t in targets:
                if any(ch in t for ch in "$`*?["):
                    continue
                for b in bases:
                    hit = (b / os.path.expanduser(t)).resolve()
                    if hit.is_relative_to(main_dir) and not hit.is_relative_to(own):
                        return str(hit)
    except Exception:
        return None
    return None


def _references_protected(command: str) -> bool:
    """True, wenn ein Protected-Muster auf ein echtes DATEI-Token passt.

    Token-Analyse mit Freitext-Flag-Ausnahme — dieselbe Logik wie beim
    Secrets-Check (Issue #53), jetzt auch fuer den State-Integrity-Pfad
    (Issue #64): ein Protected-Pfad, der nur in einem -m/--body/--title/-F-
    Freitext ZITIERT wird (Issue-Body, Doku), ist keine Datei-Referenz.
    Nested Shell/eval und shlex-Fehler fallen konservativ auf den Roh-Scan
    zurueck (kein Gate-Bypass ueber quoted Code).
    """
    return _matches_file_token(command, PROTECTED_FILE_PATTERNS)


def _references_filename_marker(command: str) -> bool:
    """Tier 2: Marker-Dateinamen-Praefix erwaehnt (pfad-unabhaengig blockierend)."""
    return any(re.search(p, command) for p in APPROVAL_MARKER_PATTERNS_FILENAME)


def _references_fieldname_marker(command: str) -> bool:
    """Tier 1: Feldname-Marker erwaehnt (blockt nur mit Protected-Pfad-Referenz)."""
    return any(re.search(p, command) for p in APPROVAL_MARKER_PATTERNS_REQUIRE_PATH)


def _strip_trailing_shell_noise(target: str) -> str:
    """Entfernt ';', '&', '|', ')' am RECHTEN Rand eines Umleitungs-Ziels (#237).

    Bewusste PARALLEL-KOPIE von secret_egress_guard.py::
    _strip_trailing_shell_noise() — kein geteilter Import zwischen den Guards
    (Konvention aus CLAUDE.md, Abschnitt Hook-Entwicklung, bereits in der ADR
    von #97 festgehalten). Hier ohne Geraete-Liste und ohne Scratchpad-Begriff:
    bash_gate.py kennt weiterhin nur '/dev/null' und hat keine Sicherheitszone.

    Reihenfolge bindend: erst bereinigen, DANN die '/dev/null'-/'^&\\d+$'-
    Ausnahmen pruefen. Ein FUEHRENDES '&' ('>&2') bleibt unberuehrt.
    """
    return target.rstrip(";&|)")


def _raw_redirect(command: str) -> bool:
    """Roher Redirect-Scan ueber den gesamten String (konservativ).

    Issue #1478 Teil 1: ein Bindestrich direkt vor '>' ist die Arrow-Notation
    ('->', z.B. in printf-Formatstrings wie '%-52s -> %s\\n'), kein Redirect-
    Operator -- analog zum bestehenden Ziffern-Lookbehind fuer '2>&1'.
    """
    for m in re.finditer(r"(?<![\d-])>{1,2}\s*(\S+)", command):
        target = _strip_trailing_shell_noise(m.group(1))
        if not target or target == "/dev/null":
            continue
        if re.match(r"^&\d+$", target):
            continue  # FD-Duplizierung (2>&1, >&2, ...) ist kein Datei-Write
        return True
    return False


def _has_real_redirect(command: str) -> bool:
    """True, wenn das Kommando einen echten Shell-Redirect auf ein Ziel != /dev/null hat.

    Nutzt shlex, damit ein '>' INNERHALB von quoted Argument-Text (z.B.
    `gh pr create --body "... a > b ..."`) NICHT als Redirect fehlinterpretiert
    wird — der haeufigste False-Positive der State-Integrity-Regel.

    Sicherheit: Bei verschachtelter Shell (`sh -c "…"`, `eval`) oder Parse-Fehler
    faellt die Pruefung auf den rohen Scan zurueck — sonst koennte ein Redirect in
    quoted Code (`bash -c "echo x > geschuetzt"`) den Gate umgehen.
    """
    if re.search(r"\b(?:ba|z|da|k)?sh\s+-c\b|\beval\b", command):
        return _raw_redirect(command)
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return _raw_redirect(command)
    for i, tok in enumerate(tokens):
        m = re.match(r"^\d*>{1,2}(.*)$", tok)  # echter Operator-Token: >  >>  2>  >file
        if not m:
            continue
        target = m.group(1) or (tokens[i + 1] if i + 1 < len(tokens) else "")
        target = _strip_trailing_shell_noise(target)
        if not target or target == "/dev/null":
            continue
        if re.match(r"^&\d+$", target):
            continue  # FD-Duplizierung (2>&1, >&2, ...) ist kein Datei-Write
        return True
    return False


def _has_write_indicator(command: str, links: bool = False) -> bool:
    for p in WRITE_INDICATORS:
        if re.search(p, command):
            return True
    if links and _LINK_COMMAND_RE.search(command):  # ln/link/install/rsync (#407)
        return True
    return _has_real_redirect(command)


def _is_sensitive(path: str, patterns: list) -> bool:
    return any(re.search(p, path, re.IGNORECASE) for p in patterns)


def _matches_file_token(command: str, patterns: list) -> bool:
    """True, wenn eines der Muster auf ein echtes DATEI-Token des Befehls passt.

    Freitext-Argumente von -m/--body/--title/-F (Commit-Messages, PR-/Issue-
    Bodies, grep-Muster hinter diesen Flags) sind keine Datei-Token und werden
    ausgenommen — genau diese Freitexte erzeugten die False-Positives aus #53.

    Sicherheit: Bei verschachtelter Shell (`sh -c "…"`, `eval`) oder shlex-
    Parse-Fehler (kaputte Quotes) faellt die Pruefung auf den bisherigen Roh-
    Scan zurueck — sonst koennte ein Zugriff in quoted Code das Gate umgehen.
    Identisches Muster wie `_has_real_redirect()` (3.4.15) und wie die gleich-
    namige Funktion in secrets_guard.py (kein Guard-Drift).
    """
    if re.search(r"\b(?:ba|z|da|k)?sh\s+-c\b|\beval\b", command):
        return _is_sensitive(command, patterns)
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return _is_sensitive(command, patterns)
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in SECRETS_FREETEXT_FLAGS:
            skip_next = True
            continue
        if tok.startswith("-"):
            continue  # Flag (auch --body=… Attached-Form) — kein Datei-Token
        if _is_sensitive(tok, patterns):
            return True
    return False


def _references_sensitive_file(command: str, patterns: list) -> bool:
    """Sensibles Muster auf echtem Datei-Token (Issue #53) — siehe _matches_file_token."""
    return _matches_file_token(command, patterns)


def _outputs_content(command: str) -> bool:
    return any(re.search(p, command) for p in CONTENT_OUTPUT_COMMANDS)


def _read_active_workflow() -> dict | None:
    """Read active workflow via OPENSPEC_ACTIVE_WORKFLOW env var or settings.local.json fallback.

    Resolution is env/settings only — the .active symlink is intentionally
    not used (single source of truth, matching workflow.py).

    #416: nur aus echter eigener Datei; ein Verweis wirft `UnsafeStateError`
    an den Aufrufer (Commit-Gate verweigert, kein "kein Workflow").
    """
    name = get_active_workflow_name()
    if not name:
        return None
    wf_file = _root / ".claude" / "workflows" / f"{name}.json"
    if wf_file.exists():
        try:
            return read_state_json(wf_file, _root)
        except (OSError, json.JSONDecodeError):
            pass
    return None


def _contains_hardcoded_credentials(command: str, config: dict) -> str | None:
    """Return credential type if command contains a hardcoded secret, else None."""
    patterns = config.get("credentials_guard", {}).get("patterns", HARDCODED_CREDENTIAL_PATTERNS)
    for pattern, cred_type in patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return cred_type
    return None


def _is_amend(command: str) -> bool:
    return re.search(r"(?<!\S)--amend(?!\S)", command) is not None


def _creates_commit(command: str) -> bool:
    """Erzeugt der Befehl einen Commit, der durch die Commit-Gates muss?

    `git commit` und der Abschluss eines Merges per `git merge --continue` (#355):
    der eine fuehrt intern genau den anderen aus. Ueber-Erkennung (`--continue`
    gehoert zu einem anderen Segment) heisst nur, dass zusaetzlich geprueft wird.
    """
    if is_git_subcommand(command, "commit"):
        return True
    # git akzeptiert eindeutige Praefixe langer Optionen: `--con` == `--continue`
    # (`--co` ist mehrdeutig, `--commit`).
    return (is_git_subcommand(command, "merge")
            and re.search(r"(?<![^\s\"'])--con(?:t(?:i(?:n(?:u(?:e)?)?)?)?)?(?![^\s;&|)\"'])", command) is not None)


def _commit_content_files(staged_list: list, measure_root: Path, command: str) -> list:
    """Dateien, die der ENTSTEHENDE Commit enthaelt.

    Drei Aufrufformen, drei Antworten:

    - Normalfall: der Index.
    - `git commit -a` / `-am`: git merkt erst beim Commit selbst vor, zum
      Hook-Zeitpunkt ist der Index leer, obwohl der Commit Produktivcode
      traegt. Dann zaehlt der Arbeitsbaum gegen HEAD.
    - `git commit --amend`: das Ergebnis enthaelt den bisherigen Commit PLUS
      die Nachbesserung. Gemessen wird deshalb immer gegen `HEAD~1`, nicht
      gegen den Index — sonst meldete ein Amend mit sauberem Baum `docs-only`
      und ueberschriebe einen zuvor korrekten Wert.

    Nur fuer die Scope-Erkennung (informativ, blockt nie). `required_staged_files`
    behaelt bewusst die strenge Index-Semantik: dort ist "nicht vorgemerkt"
    genau die Bedingung, auf die das Gate hinweisen soll.

    Bekannte Untergrenze: laesst sich der Inhalt nicht ermitteln (kaputtes Repo,
    Amend des Wurzel-Commits ohne `HEAD~1`), faellt die Liste leer aus und
    `_detect_e2e_scope` meldet `docs-only`. Fail-open — die Scope-Erkennung ist
    informativ und darf keinen Commit verhindern.
    """
    import subprocess

    def _diff(*args: str) -> "list | None":
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only", *args],
                cwd=measure_root, capture_output=True, text=True, timeout=5
            )
        except (subprocess.SubprocessError, OSError):
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout.strip().splitlines()

    if _is_amend(command):
        amended = _diff("HEAD~1")
        if amended:
            return amended
        return staged_list  # Wurzel-Commit: kein HEAD~1 vorhanden
    if staged_list:
        return staged_list
    return _diff("HEAD") or []


def _detect_e2e_scope(staged_files: list, config: dict) -> str:
    """Determine E2E test scope from staged file paths."""
    docs = config.get("e2e_scope", {}).get("docs_patterns", E2E_DOCS_PATTERNS)
    front = config.get("e2e_scope", {}).get("frontend_patterns", E2E_FRONTEND_PATTERNS)
    back = config.get("e2e_scope", {}).get("backend_patterns", E2E_BACKEND_PATTERNS)
    non_doc = [f for f in staged_files if not any(re.search(p, f) for p in docs)]
    if not non_doc:
        return "docs-only"
    has_front = any(any(re.search(p, f) for p in front) for f in non_doc)
    has_back = any(any(re.search(p, f) for p in back) for f in non_doc)
    if has_front and has_back:
        return "full-stack"
    if has_front:
        return "frontend-only"
    if has_back:
        return "backend"
    return "full-stack"


def _write_e2e_scope(wf: dict, scope: str) -> None:
    """Write e2e_scope to the active workflow JSON atomically (never raises)."""
    import tempfile
    name = wf.get("name", "")
    if not name:
        return
    wf_file = _root / ".claude" / "workflows" / f"{name}.json"
    if not wf_file.exists():
        return
    try:
        data = read_state_json(wf_file, _root)
        data["e2e_scope"] = scope
        fd, tmp = tempfile.mkstemp(dir=str(wf_file.parent), suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp, str(wf_file))
    except (OSError, json.JSONDecodeError, UnsafeStateError):
        pass  # #416: bei Verweis nicht zurueckschreiben (kein "Waschen")


# Wertnehmende Optionen von `git commit` (#259 §3): ihr Wert ist keine Pfadangabe.
_COMMIT_VALUE_OPTS = {
    "-m", "-F", "-C", "-c", "-t", "--author", "--date", "--cleanup", "--fixup",
    "--squash", "--trailer", "--message", "--file", "--reuse-message",
    "--reedit-message", "--template",
}


def _commit_form(command: str) -> "tuple[bool, bool, bool, bool]":
    """(-a/--all, Pfadangabe, begleitendes `git add`, --amend) des Commit-Aufrufs (#259 §3).

    Jedes Nicht-Options-Token der commit-Argumente, das kein Wert einer
    wertnehmenden Option ist, gilt als Pfadangabe, ebenso alles nach `--`.
    `--amend` zaehlt nur als Options-Token (auch abgekuerzt wie `--amen`, das
    git akzeptiert), nie im Wert von `-m` & Co. (F101). Unsicherheit (nicht
    zerlegbar, kein direkter commit-Aufruf) ergibt (True, True, True, True) —
    die groessere Menge, nie die kleinere.
    """
    from hook_utils import _git_segments, _looks_like_git
    commits = [seg[seg.index("commit") + 1:] for seg in (_git_segments(command) or [])
               if "commit" in seg and any(_looks_like_git(t) for t in seg[:seg.index("commit")])]
    if not commits:
        merges = [seg for seg in (_git_segments(command) or [])
                  if "merge" in seg and any(_looks_like_git(t) for t in seg[:seg.index("merge")])]
        if merges and _creates_commit(command):
            # `git merge --continue` (#355) committet den Index — ohne -a, Pfade, --amend
            return False, False, "add" in git_subcommands(command), False
        return True, True, True, True
    all_files = pathspec = amend = False
    for args in commits:
        skip = False
        for i, tok in enumerate(args):
            if skip:
                skip = False
            elif tok == "--":
                pathspec |= i + 1 < len(args)
                break
            elif tok.startswith("--"):
                all_files |= tok == "--all"
                amend |= "--amend".startswith(tok)
                pathspec |= tok.startswith("--pathspec-from-file")
                skip = tok in _COMMIT_VALUE_OPTS
            elif tok.startswith("-") and len(tok) > 1:
                for j, ch in enumerate(tok[1:]):  # gebuendelt: -am <msg>
                    all_files |= ch == "a"
                    if ch in "mFCct":
                        skip = j + 2 == len(tok)  # Wert folgt als eigenes Token
                        break
            else:
                pathspec = True
    return all_files, pathspec, "add" in git_subcommands(command), amend


def _commit_change_set(command: str) -> "tuple[list | None, list, str | None]":
    """(Commit-Menge, teilweise gestagte Dateien, git-Fehler) — Code-Dateien, realpath-absolut.

    Commit-Menge (#259 §3), immer als Vereinigung mit dem Index (nie kleiner als er):
    bei -a, Pfadangabe, leerem Index oder begleitendem `git add` plus Arbeitsbaum gegen
    HEAD (mit `add` plus untrackte Dateien); bei --amend plus Index und Arbeitsbaum
    gegen HEAD~1 (F101). Teilstaging (§4) nur, wenn der Commit aus dem Index kommt.
    Menge None: kein Git-Repository, die Pruefung entfaellt; git-Fehler trotz
    Repository (F102) → Fehlertext.
    """
    from adversary_dialog import (
        DIFF_NAMES, ChangeSetError, code_files, git_code_files, git_names, git_toplevel, run_git,
    )
    all_files, pathspec, with_add, amend = _commit_form(command)

    def has(rev: str) -> bool:
        return run_git(["rev-parse", "--verify", "-q", rev], top, probe=True) is not None

    try:
        top = git_toplevel(_measurement_root())
        if top is None:
            return None, [], None
        # Laufender Merge (#355): gegen MERGE_HEAD messen, nicht gegen HEAD — sonst
        # zaehlte jede per `git merge origin/main` hereingeholte Datei als eigene
        # Aenderung, die der Dialog binden muesste (dieselbe Menge wie Phase 8
        # gegen merge-base).
        # Nur wenn MERGE_HEAD aus origin/main stammt: das Merge-Ziel waehlt der Agent
        # selbst (`git stash; git merge --no-commit stash@{0}` versteckte sonst eigenen
        # Code). Sonst gegen HEAD — die groessere Menge.
        base = "HEAD"
        if has("MERGE_HEAD") and run_git(
                ["merge-base", "--is-ancestor", "MERGE_HEAD", "origin/main"], top,
                probe=True) is not None:
            base = "MERGE_HEAD"
        staged = git_names(["diff", "--cached", *DIFF_NAMES, *([base] if base != "HEAD" else [])],
                           top)  # leer = leerer Index
        files = index = code_files(staged, top)
        if (all_files or pathspec or with_add or not staged) and has(base):
            files = files + git_code_files(["diff", *DIFF_NAMES, base, "--"], top)
        if amend and has("HEAD~1"):  # Vereinigung: --amend vergroessert die Menge nur
            files = files + git_code_files(["diff", *DIFF_NAMES, "HEAD~1", "--"], top) \
                + git_code_files(["diff", "--cached", *DIFF_NAMES, "HEAD~1", "--"], top)
        if with_add:
            files = files + git_code_files(["ls-files", "-z", "--others", "--exclude-standard"], top)
        partial = []
        if not (all_files or pathspec or with_add):
            unstaged = set(git_code_files(["diff", "-z", "--name-only"], top))
            partial = [f for f in index if f in unstaged]
    except ChangeSetError as exc:
        return None, [], str(exc)
    return sorted(set(files)), partial, None


def _require_dialog_evidence(wf: dict, verdict: str, command: str) -> None:
    """VERIFIED bzw. AMBIGUOUS+Override zaehlen nur mit gueltigem Dialog-Artefakt (#253),
    das jede Code-Datei des entstehenden Commits bindet (#259).

    Dieselbe Regel wie der Phase-8-Uebergang (adversary_dialog.check_dialog_evidence);
    Commit-Menge und Teilstaging nur bei aktivem Kill-Switch adversary_coverage_gate.
    Scheitert der Import, gilt der Nachweis als nicht erbracht. Ein gueltiger
    User-Override-Token hebt jeden dieser Blocks auf — dieselbe Notbremse wie beim
    fehlenden Verdict.
    """
    reasons = []
    try:
        from adversary_dialog import check_dialog_evidence, coverage_gate_enabled, display_path
        changed, partial, git_error = None, [], None
        if coverage_gate_enabled():
            changed, partial, git_error = _commit_change_set(command)
        reasons.append(git_error or check_dialog_evidence(wf, changed_files=changed))
        reasons += [
            f"teilweise gestagt: `{display_path(f)}` — geprüft wurde der Arbeitsbaum, committet "
            f"würde der Index-Stand (Ausweg: `git add {display_path(f)}` oder `git commit -a`)"
            for f in partial
        ]
    except Exception as exc:
        reasons.append(f"Nachweis-Prüfung nicht verfügbar ({type(exc).__name__}: {exc})")
    reason = "; ".join(r for r in reasons if r)
    if not reason:
        return
    try:
        from override_token import has_valid_token
        if has_valid_token(wf.get("name")):
            return
    except ImportError:
        pass
    name = wf.get("name")
    where = (f"Protokoll unter\n  docs/artifacts/{name}/adversary-dialog.md speichern, dann\n"
             if name else "Protokoll speichern (ohne Workflow-Namen\n"
             "  gibt es keinen Standardpfad), dann\n")
    block(
        f"BLOCKED: Adversary verdict ohne gültigen Dialog-Nachweis — {reason}\n"
        "  Ein grüner Testlauf ersetzt den Adversary-Dialog nicht.\n"
        f"  Weg (/50-implement Step 8): Adversary-Dialog führen, {where}"
        "    adversary_dialog.py stamp <pfad>\n"
        "    workflow.py add-artifact adversary_dialog <pfad> \"Adversary Dialog Protokoll\" phase6b_adversary\n"
        "  " + gate_diagnostics(wf, verdict=verdict)
    )


# --- Abhaengigkeits-Ordner (Issue #293) ---

DEFAULT_DEPENDENCY_DIRS = [
    "node_modules", ".venv", "venv", "vendor", "bower_components", ".pnpm-store",
]
_DELETE_COMMANDS = frozenset({"rm", "rmdir", "unlink", "rimraf", "trash", "trash-put"})
_PKG_RUNNERS = frozenset({"npx", "pnpx", "bunx"})
_CMD_PREFIXES = frozenset({"sudo", "command", "nice", "nohup", "time", "env", "exec"})


def _dependency_dirs(config: dict) -> "list[str] | None":
    """Konfigurierte Ordnernamen, None wenn der Guard abgeschaltet ist."""
    block_cfg = (config or {}).get("dependency_dir_guard") or {}
    if not isinstance(block_cfg, dict):
        block_cfg = {}
    if block_cfg.get("enabled") is False:
        return None
    dirs = block_cfg.get("dirs", DEFAULT_DEPENDENCY_DIRS)
    return [str(d) for d in dirs] if isinstance(dirs, list) else DEFAULT_DEPENDENCY_DIRS


def _dep_target(arg: str, dirs: "list[str]") -> "str | None":
    """Der Ordner selbst oder sein gesamter Inhalt (`x/`, `x/*`, `x/.`) — nicht tiefer.

    `rm -rf node_modules/.cache` bleibt erlaubt: ein Cache-Reset trifft nicht
    die Abhaengigkeiten. Symlink-Aufloesung ist bewusst NICHT Voraussetzung.
    """
    path = arg.strip("'\"")
    for suffix in ("/*", "/.", "/"):
        while path.endswith(suffix) and len(path) > len(suffix):
            path = path[: -len(suffix)]
    base = path.rsplit("/", 1)[-1]
    return base if base in dirs else None


def _segment_dep_hit(seg: "list[str]", dirs: "list[str]") -> "str | None":
    i = 0
    while i < len(seg) and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[i])
                            or seg[i] in _CMD_PREFIXES):
        i += 1
    if i >= len(seg):
        return None
    head = seg[i].rsplit("/", 1)[-1]
    args = seg[i + 1:]
    if head in _PKG_RUNNERS:
        rest = [a for a in args if not a.startswith("-")]
        if rest and rest[0].rsplit("/", 1)[-1].split("@")[0] in ("rimraf", "del-cli", "trash-cli"):
            args = args[args.index(rest[0]) + 1:]
            head = "rimraf"
        else:
            return None
    if head in _DELETE_COMMANDS:
        targets = [a for a in args if not a.startswith("-")]
    elif head == "mv":
        plain = [a for a in args if not a.startswith("-")]
        targets = plain[:-1]  # letzte Angabe ist das Ziel
    elif head == "find" and any(a in ("-delete", "-exec", "-execdir") for a in args):
        targets = []
        for a in args:
            if a.startswith("-") or a in ("(", "!"):
                break
            targets.append(a)
        # `find . -name node_modules -exec rm -rf {} +` / `-delete`
        for k, a in enumerate(args[:-1]):
            if a in ("-name", "-iname", "-path") and _dep_target(args[k + 1], dirs):
                targets.append(args[k + 1])
    else:
        return None
    for t in targets:
        hit = _dep_target(t, dirs)
        if hit:
            return hit
    return None


def _deletes_dependency_dir(command: str, config: dict) -> "str | None":
    """Name des Abhaengigkeits-Ordners, den das Kommando loescht/verschiebt, sonst None."""
    dirs = _dependency_dirs(config)
    if not dirs or not any(d in command for d in dirs):
        return None
    nested = re.search(r"\b(?:ba|z|da|k)?sh\s+-c\b|\beval\b|\bxargs\b", command)
    segments = None if nested else _git_segments(command)
    if segments is None:
        # Verschachtelte Shell / nicht zerlegbar: konservativer Roh-Scan.
        names = "|".join(re.escape(d) for d in dirs)
        m = re.search(
            rf"\b(?:rm|rmdir|unlink|rimraf|trash|mv)\b[^;&|\n]*?(?<![\w.-])({names})(?:/\*?|/\.)?"
            r"(?=$|[\s'\";&|)])",
            command,
        )
        return m.group(1) if m else None
    for seg in segments:
        hit = _segment_dep_hit(seg, dirs)
        if hit:
            return hit
    return None


def _any_override_token() -> bool:
    try:
        from override_token import has_valid_token
        name = get_active_workflow_name()
        return has_valid_token(name) if name else has_valid_token()
    except Exception:
        return False


# --- Main ---

def main():
    tool_input = get_tool_input()
    command = tool_input.get("command", "")
    if not command:
        allow()

    config = _load_config_values()

    # Heredoc-Bodies sind stdin-DATEN, kein Kommandotext (Issues #64/#75):
    # fuer die Muster-Scans (Protected-Pfad, Write-Indicator, Secrets-Token)
    # werden sie entfernt. Konservativ: Bodies, die ein Interpreter auf der
    # Oeffner-Zeile ausfuehrt (python/sh/node/...), bleiben im Scan-Text.
    # Der Credentials-Scan (4b) laeuft bewusst weiter auf dem VOLLEN Text —
    # ein hartkodiertes Secret in einem Heredoc (z.B. .env-Schreiben) muss
    # weiterhin auffallen.
    scan_cmd = strip_heredoc_bodies(command)

    # Dieses Gate ist das einzige gemischte: Schritte 1, 3a, 3b und 5 sind
    # Workflow-Zwang, Schritte 2, 4 und 4b sind Schutz. Der Projekt-Schalter
    # (#132) nimmt deshalb nur die erste Haelfte raus — ein Schalter, der auch
    # den Secret-Schutz mitnimmt, entfernt still Schutz, den niemand abwaehlen
    # wollte.
    workflow_enforced = not framework_disabled()

    # 1. Stop-lock
    if workflow_enforced and is_stop_locked(_root):
        block(f"BLOCKED: Stop-lock active. {stop_lock_state(_root)[1]}".rstrip())

    # 1b. Wirksame Gate-Config (#410): Schutz, kein Workflow-Zwang — gilt ohne
    #     Workflow und vor jedem Schnellweg; Ausweg nur der Override-Token.
    if _writes_effective_config(_git_segments(scan_cmd) or [], Path.cwd()) \
            and not _any_override_token():
        block(
            "BLOCKED: Schreibzugriff auf die wirksame Gate-Config (Kill-Switches) "
            "oder Anlegen einer vorrangigen Config.\n"
            "  Aenderungen gehoeren in die Worktree-Kopie und wirken nach dem Merge.\n"
            "  Bewusst gewollt? User tippt 'override'."
        )

    # 1c. Haupt-Ordner aus einer Worktree-Sitzung (#417): Schutz vor Split-Brain,
    #     kein Workflow-Zwang — gilt wie 1b ohne Workflow und bei framework_disabled().
    main_hit = _writes_main_repo(_git_segments(scan_cmd) or [], Path.cwd())
    if main_hit and not _any_override_token():
        block(
            "BLOCKED: Schreibzugriff aus dem Worktree in den Haupt-Ordner (Worktree-Pflicht).\n"
            f"  Ziel: {main_hit}\n"
            "  Aenderungen gehoeren in den eigenen Worktree und kommen per Merge an.\n"
            "  Bewusst gewollt? User tippt 'override'."
        )

    # 1d. Simulator-Beleg (#447): nur echte Schreibziele, VOR dem Git-Schnellweg
    #     (`git status > <beleg>`). Lesen und der Erzeuger-Aufruf bleiben frei.
    if workflow_enforced and _writes_proof_file(scan_cmd, Path.cwd(), command):
        block("BLOCKED: Simulator-Beleg (#447) — nur der Erzeuger schreibt ihn "
              "(scripts/sim.sh test-proof).\n"
              "  Auch Umbenennen, Verlinken oder Kopieren des Ordners docs/artifacts/<wf> "
              "zaehlt als Zugriff auf den Beleg (#448).")

    # 1e. Suche ab Wurzel/Home (#462): Schutz vor Dauerlast, kein Workflow-Zwang.
    search_hit = _broad_search_hit(scan_cmd)
    if search_hit and not _any_override_token():
        block(
            f"BLOCKED: Suche ueber die ganze Platte ({search_hit}) — Dauerlast-Schutz (#462).\n"
            "  Suche im Projekt (`find ./docs ...`) oder nutze den bekannten Pfad.\n"
            "  Plugin-Skripte (adversary_dialog.py, workflow.py, ...) liegen unter\n"
            "  ${CLAUDE_PLUGIN_ROOT}/core/hooks/ bzw. $_H aus dem Setup-Block — nie suchen.\n"
            "  Bewusst gewollt? User tippt 'override'."
        )

    # Umleitung auf State/Marker hinter einem erlaubten Befehl (#316): VOR dem
    # Git-Schnellweg berechnen, sonst endet `git status > <state>` dort.
    redirect_hit = workflow_enforced and _redirects_to_protected(scan_cmd)

    # 2. Git commands fast path
    # Tokenbasiert (Issue #1431). Die alte Form
    #   command.lstrip().startswith("git ") and "git commit" not in command
    # war doppelt zu weit: `git -C /pfad commit` erfuellte BEIDE Bedingungen und
    # beendete den Hook VOR Secrets-Guard, Credential-Pruefung und den Commit-
    # Gates; und `git status && touch <freigabe-marker>` beginnt zwar mit "git ",
    # ist aber genau der Angriffsvektor, den Abschnitt 3a abwehren soll.
    # Der Fast Path greift jetzt nur, wenn JEDES Segment ein git-Aufruf ist.
    git_only = is_pure_git_command(command)
    if (
        not git_only
        and not git_subcommands(command)          # nicht zerlegbar (kaputte Quotes)
        and command.lstrip().startswith("git ")
        and "git commit" not in command
        and not git_runs_foreign_code(command)    # Shell-Alias, `-c core.pager=…` (#297)
    ):
        git_only = True  # fail-open: exakt das bisherige Verhalten
    if git_only and not _creates_commit(command) and not redirect_hit:
        allow()

    # 3a. Approval-/Erfolgs-Marker: deny by default, kein Bash-Weg erlaubt.
    #     "approve" ist eine High-Risk-Operation, die NUR ein Mensch ausloesen
    #     darf (vgl. specification gaming / reward hacking bei Coding-Agenten).
    #     git ist ausgenommen: eine Commit-Message oder Doku DARF die Marker-
    #     Namen erwaehnen — das ist keine Datei-Manipulation. Der Angriffsvektor
    #     (touch/echo/sed/rm) startet nie mit "git ".
    #     Tokenbasiert (Issue #1431): die Ausnahme gilt nur, wenn JEDES Segment
    #     ein git-Aufruf ist (`git commit -m "... user_approved ..."` ja,
    #     `git status && touch <marker>` nein).
    is_git_command = git_only
    _marker_block_msg = (
        "BLOCKED: Freigabe-/Erfolgs-Marker duerfen NICHT per Bash erzeugt, "
        "geaendert oder geloescht werden.\n"
        "\n"
        "  Diese Datei behauptet eine Freigabe, die NUR der User erteilen kann.\n"
        "  Du kannst dieses Gate nicht selbst oeffnen — das waere die Manipulation\n"
        "  des Pruefpunkts statt der echten Erfuellung der Bedingung.\n"
        "\n"
        "  Der einzige legitime Weg:\n"
        "  -> Lege dem User die Ergebnisse vor und WARTE auf seine ausdrueckliche\n"
        "     Freigabe. Der phase_listener-Hook setzt den Marker dann selbst."
    )
    if workflow_enforced and not is_git_command and _has_write_indicator(scan_cmd):
        # Tier 2 (Dateinamen-Marker): pfad-unabhaengig blocken. Verhindert
        # cd-Obfuskation (`cd .claude && touch user_approved_validation_x`).
        if _references_filename_marker(scan_cmd):
            block(_marker_block_msg)
        # Tier 1 (Feldname-Marker): nur blocken, wenn zusaetzlich ein echter
        # Protected-Pfad referenziert wird (Issue #30 — Freitext-Toleranz).
        elif _references_fieldname_marker(scan_cmd) and _references_protected(scan_cmd):
            block(_marker_block_msg)

    # 3b. State-integrity: protected file + write indicator
    #     Ein Whitelist-Treffer ueberspringt NUR diesen Block, nicht 4/4b/5
    #     (#296: `git commit -m x -- <state>` darf das Commit-Gate nicht umgehen).
    #     Gezaehlt werden nur geschuetzte Pfade in nicht-whitelisted Segmenten (2b),
    #     dazu Umleitungsziele und bloße .json-Namen nach `cd .claude/…` (#316).
    _state_msg = "BLOCKED: Direct state file manipulation. Use workflow.py CLI."
    if redirect_hit:
        block(_state_msg)
    # #407: Verweis-Befehle und Zustandsordner nur bei aktivem Workflow (AC-9).
    wf_active = workflow_enforced and bool(get_active_workflow_name())
    if workflow_enforced and (
        _protected_outside_whitelist(scan_cmd, command, wf_active)
        or _cd_context_protected(scan_cmd)
        or (wf_active and _dir_token_in_cd_context(_git_segments(scan_cmd) or []))
    ):
        if _has_write_indicator(scan_cmd, links=wf_active):
            block(_state_msg)

    # 3c. QA-Stempel (#404 F003): Schreibversuch per Python im Bash-Kommando.
    if workflow_enforced and _forges_qa_stamp(command):
        block("BLOCKED: QA-Stempel darf nur qa_gate.py --run schreiben "
              "(write_qa_run_stamp per Python ist gesperrt, #404).")

    # 4. Secrets guard
    sensitive_patterns = config.get("secrets_guard", {}).get("sensitive_patterns", SENSITIVE_PATTERNS)
    always_blocked = config.get("secrets_guard", {}).get("always_blocked", ALWAYS_BLOCKED_SECRETS)
    try:
        from config_loader import secrets_guard_patterns  # Zweig-Muster mit Untergrenze (#292)
        sensitive_patterns, always_blocked = secrets_guard_patterns(config)
    except Exception:
        pass

    def _secrets_check(sensitive: list, always: list) -> None:
        if _references_sensitive_file(scan_cmd, sensitive) and _outputs_content(scan_cmd):
            if _references_sensitive_file(scan_cmd, always):
                block("BLOCKED: Secrets guard — sensitive credentials/keys.")
            staging = (_root / ".claude" / "staging").exists()
            if not staging:
                block("BLOCKED: Secrets guard — .env file. Enable staging mode with: touch .claude/staging")

    # #292: wirken Zweig-Muster, entscheiden zuerst die Grundmuster allein.
    try:
        from config_loader import secrets_guard_floor
        floor = secrets_guard_floor()
    except Exception:
        floor = None
    if floor is not None:
        _secrets_check(*floor)
    try:
        _secrets_check(sensitive_patterns, always_blocked)
    except Exception as exc:  # fehlerhaftes Muster: blockieren statt Exit 1 (fail-closed)
        block(f"BLOCKED: Secrets guard — Muster nicht auswertbar ({type(exc).__name__}); "
              "secrets_guard-Abschnitt der Config pruefen.")

    # 4b. Hardcoded credentials in command
    if not _is_whitelisted(command):
        cred_type = _contains_hardcoded_credentials(command, config)
        if cred_type:
            block(f"BLOCKED: Hardcoded {cred_type} detected. Use env vars or secrets.env instead.")

    # 4c. Abhaengigkeits-Ordner (#293): Schutz, kein Workflow-Zwang — gilt
    #     auch ohne Workflow. In Worktrees ist node_modules oft ein Symlink auf
    #     den geteilten Ordner; ein `rm -rf` trifft dann alle Sitzungen.
    dep_hit = _deletes_dependency_dir(scan_cmd, config)
    if dep_hit and not _any_override_token():
        block(
            f"BLOCKED: Abhaengigkeits-Ordner '{dep_hit}' wird geloescht oder verschoben.\n"
            "  In Worktrees ist er oft ein Symlink auf den GETEILTEN Ordner im Haupt-Repo —\n"
            "  das Loeschen traefe alle Worktrees und Sitzungen.\n"
            "  Stattdessen in place neu installieren: `npm ci` / `npm install`,\n"
            "  `pnpm install --force`, `pip install --force-reinstall -r requirements.txt`,\n"
            "  `composer install`. Bewusst gewollt? User tippt 'override'.\n"
            "  Ordnerliste: config.yaml -> dependency_dir_guard.dirs (Kill-Switch: enabled: false)."
        )

    # 5. Git commit gates (tokenbasiert, Issue #1431 — Erwaehnung ist kein Aufruf)
    if workflow_enforced and _creates_commit(command):
        import subprocess

        # Gemessen wird im Arbeitsbaum, nicht im Hauptrepo (Issue #155).
        measure_root = _measurement_root()

        # Get staged files (reused across 5a, 5b, 5c)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=measure_root, capture_output=True, text=True
        )
        staged_list = staged.stdout.strip().splitlines()

        # 5a. Configurable required staged files
        required_files = config.get("pre_commit", {}).get("required_staged_files", [])
        for req_file in required_files:
            if req_file not in staged_list:
                diff = subprocess.run(
                    ["git", "diff", "--name-only", "--", req_file],
                    cwd=measure_root, capture_output=True, text=True
                )
                if diff.stdout.strip():
                    block(f"BLOCKED: {req_file} has unstaged changes. Stage it first.")

        # 5b. Rebase-Pflicht: Branch darf nicht hinter origin/main zurückliegen
        try:
            wf = _read_active_workflow()
        except UnsafeStateError as exc:
            # #416: kein vertrauenswuerdiger State = keine Commit-Freigabe
            block(f"BLOCKED: {exc}")
        if wf:
            try:
                fetch = subprocess.run(
                    ["git", "fetch", "origin", "main", "--quiet"],
                    cwd=os.getcwd(), capture_output=True, timeout=10
                )
                if fetch.returncode == 0:
                    # Laufender Merge: Rueckstand gegen MERGE_HEAD messen (#352)
                    basis = "HEAD"
                    try:
                        mh = subprocess.run(
                            ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"],
                            cwd=os.getcwd(), capture_output=True, text=True, timeout=5
                        )
                        if mh.returncode == 0 and mh.stdout.strip():
                            basis = "MERGE_HEAD"
                    except (subprocess.TimeoutExpired, OSError):
                        basis = "HEAD"
                    behind_result = subprocess.run(
                        ["git", "rev-list", "--count", f"{basis}..origin/main"],
                        cwd=os.getcwd(), capture_output=True, text=True, timeout=5
                    )
                    behind = int(behind_result.stdout.strip() or "0")
                    if behind > 0 and basis == "MERGE_HEAD":
                        block(
                            "BLOCKED — Merge bringt origin/main nicht vollständig herein "
                            f"({behind} Commit(s) fehlen).\n"
                            "Bitte erst: git fetch origin && git merge origin/main"
                        )
                    if behind > 0:
                        # --autostash: vorgemerkte Dateien ueberleben den Rebase (#284)
                        block(
                            f"BLOCKED — Branch ist {behind} Commit(s) hinter origin/main.\n"
                            "Bitte erst: git fetch origin && git rebase --autostash origin/main\n"
                            "Ein gestempelter Adversary-Nachweis bleibt dabei gueltig, solange sich\n"
                            "die eigene Aenderung konfliktfrei auf main setzen laesst (#289)."
                        )
                # fetch returncode != 0 → kein Netz → silent skip
            except (subprocess.TimeoutExpired, OSError, ValueError):
                pass  # Netzwerk nicht erreichbar → kein Block

        # 5c. Adversary verdict check (if in phase6+)
        if wf:
            phase = wf.get("current_phase", "")
            if phase in ("phase6_implement", "phase6b_adversary", "phase7_validate"):
                # Feature fast-track: no adversary verdict required
                if wf.get("workflow_type") == "feature-fast":
                    pass
                else:
                    verdict = str(wf.get("adversary_verdict", "") or "")
                    if verdict.startswith("VERIFIED"):
                        _require_dialog_evidence(wf, verdict, command)  # #253, #259
                    elif verdict.startswith("AMBIGUOUS"):
                        if not wf.get("adversary_ambiguous_override"):
                            block("BLOCKED: Adversary verdict is AMBIGUOUS. "
                                  "Review findings, then: workflow.py override-ambiguous '<reason>' "
                                  + gate_diagnostics(wf, verdict="AMBIGUOUS"))
                        _require_dialog_evidence(wf, verdict, command)  # #253, #259
                    else:
                        has_override = False
                        try:
                            from override_token import has_valid_token
                            has_override = has_valid_token(wf.get("name"))
                        except ImportError:
                            pass
                        if not has_override:
                            block("BLOCKED: Adversary verdict missing or not VERIFIED. Run adversary validation first. "
                                  + gate_diagnostics(wf, verdict=(verdict or "keins")))

            # 5d. E2E scope detection (informational — never blocks)
            scope = _detect_e2e_scope(
                _commit_content_files(staged_list, measure_root, command), config
            )
            _write_e2e_scope(wf, scope)
            print(f"E2E scope: {scope}", file=sys.stderr)

    # 6. Allow
    allow()


if __name__ == "__main__":
    main()
