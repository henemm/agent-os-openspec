#!/usr/bin/env python3
"""
Bash Gate v3 — Consolidated PreToolUse Hook for Bash

Replaces 15 separate hooks with 1. Sequential logic:

1. Stop-Lock → BLOCK
2. Git commands → ALLOW (fast path)
3. State-Integrity: protected file + write indicator → BLOCK (whitelist)
4. Secrets: sensitive file + content output → BLOCK
5. Git Commit gates (configurable required staged files, adversary verdict)
6. ALLOW

Project-specific gates (sim_enforcer, build_lock) belong in module hooks.

Exit Codes: 0 = allowed, 2 = blocked
"""

from hook_utils import (
    setup_path, find_project_root, get_tool_input, block, allow,
    get_active_workflow_name, gate_diagnostics, strip_heredoc_bodies,
    SECRETS_SENSITIVE_PATTERNS, SECRETS_ALWAYS_BLOCKED, SECRETS_FREETEXT_FLAGS as _SHARED_FREETEXT_FLAGS,
    git_subcommands, git_head_subcommands, is_git_subcommand, is_pure_git_command,
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

# Approval-/Erfolgs-Marker: Dateien, deren blosse Existenz einen Freigabe-
# oder Erfolgszustand BEHAUPTET. Diese darf der Agent NIEMALS selbst per Bash
# erzeugen/aendern/loeschen — das waere "specification gaming" (der Agent
# manipuliert den Verifier statt die Bedingung echt zu erfuellen). Der einzige
# legitime Erzeuger ist phase_listener.py (UserPromptSubmit-Hook), der nur
# feuert, wenn der echte User "go"/"freigabe"/"approved" tippt. Deny by default.
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


def _is_stop_locked() -> bool:
    try:
        from hook_utils import _find_worktree_root
        wt = _find_worktree_root()
        lock = (wt / ".claude" / "stop_lock.json") if wt is not None else (_root / ".claude" / "stop_lock.json")
    except Exception:
        lock = _root / ".claude" / "stop_lock.json"
    if not lock.exists():
        return False
    try:
        return json.loads(lock.read_text()).get("enabled", False)
    except (json.JSONDecodeError, OSError):
        return False


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
    config = _load_config_values()
    project_whitelist = config.get("bash_gate", {}).get("whitelist", [])
    return any(
        _whitelist_matches(command, allowed)
        for allowed in WHITELIST_COMMANDS + project_whitelist
    )


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


def _raw_redirect(command: str) -> bool:
    """Roher Redirect-Scan ueber den gesamten String (konservativ).

    Issue #1478 Teil 1: ein Bindestrich direkt vor '>' ist die Arrow-Notation
    ('->', z.B. in printf-Formatstrings wie '%-52s -> %s\\n'), kein Redirect-
    Operator -- analog zum bestehenden Ziffern-Lookbehind fuer '2>&1'.
    """
    for m in re.finditer(r"(?<![\d-])>{1,2}\s*(\S+)", command):
        target = m.group(1)
        if target == "/dev/null":
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
        if not target or target == "/dev/null":
            continue
        if re.match(r"^&\d+$", target):
            continue  # FD-Duplizierung (2>&1, >&2, ...) ist kein Datei-Write
        return True
    return False


def _has_write_indicator(command: str) -> bool:
    for p in WRITE_INDICATORS:
        if re.search(p, command):
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
    """
    name = get_active_workflow_name()
    if not name:
        return None
    wf_file = _root / ".claude" / "workflows" / f"{name}.json"
    if wf_file.exists():
        try:
            return json.loads(wf_file.read_text())
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
        data = json.loads(wf_file.read_text())
        data["e2e_scope"] = scope
        fd, tmp = tempfile.mkstemp(dir=str(wf_file.parent), suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp, str(wf_file))
    except (OSError, json.JSONDecodeError):
        pass


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

    # 1. Stop-lock
    if _is_stop_locked():
        block("BLOCKED: Stop-lock active.")

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
    ):
        git_only = True  # fail-open: exakt das bisherige Verhalten
    if git_only and not is_git_subcommand(command, "commit"):
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
        "  -> Lege dem User die Ergebnisse vor und WARTE auf sein 'go' / 'freigabe'\n"
        "     / 'approved'. Der phase_listener-Hook setzt den Marker dann selbst."
    )
    if not is_git_command and _has_write_indicator(scan_cmd):
        # Tier 2 (Dateinamen-Marker): pfad-unabhaengig blocken. Verhindert
        # cd-Obfuskation (`cd .claude && touch user_approved_validation_x`).
        if _references_filename_marker(scan_cmd):
            block(_marker_block_msg)
        # Tier 1 (Feldname-Marker): nur blocken, wenn zusaetzlich ein echter
        # Protected-Pfad referenziert wird (Issue #30 — Freitext-Toleranz).
        elif _references_fieldname_marker(scan_cmd) and _references_protected(scan_cmd):
            block(_marker_block_msg)

    # 3b. State-integrity: protected file + write indicator
    if _references_protected(scan_cmd):
        if _is_whitelisted(command):
            allow()
        if _has_write_indicator(scan_cmd):
            block("BLOCKED: Direct state file manipulation. Use workflow.py CLI.")

    # 4. Secrets guard
    sensitive_patterns = config.get("secrets_guard", {}).get("sensitive_patterns", SENSITIVE_PATTERNS)
    always_blocked = config.get("secrets_guard", {}).get("always_blocked", ALWAYS_BLOCKED_SECRETS)

    if _references_sensitive_file(scan_cmd, sensitive_patterns) and _outputs_content(scan_cmd):
        if _references_sensitive_file(scan_cmd, always_blocked):
            block("BLOCKED: Secrets guard — sensitive credentials/keys.")
        staging = (_root / ".claude" / "staging").exists()
        if not staging:
            block("BLOCKED: Secrets guard — .env file. Enable staging mode with: touch .claude/staging")

    # 4b. Hardcoded credentials in command
    if not _is_whitelisted(command):
        cred_type = _contains_hardcoded_credentials(command, config)
        if cred_type:
            block(f"BLOCKED: Hardcoded {cred_type} detected. Use env vars or secrets.env instead.")

    # 5. Git commit gates (tokenbasiert, Issue #1431 — Erwaehnung ist kein Aufruf)
    if is_git_subcommand(command, "commit"):
        import subprocess

        # Get staged files (reused across 5a, 5b, 5c)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=_root, capture_output=True, text=True
        )
        staged_list = staged.stdout.strip().splitlines()

        # 5a. Configurable required staged files
        required_files = config.get("pre_commit", {}).get("required_staged_files", [])
        for req_file in required_files:
            if req_file not in staged_list:
                diff = subprocess.run(
                    ["git", "diff", "--name-only", "--", req_file],
                    cwd=_root, capture_output=True, text=True
                )
                if diff.stdout.strip():
                    block(f"BLOCKED: {req_file} has unstaged changes. Stage it first.")

        # 5b. Rebase-Pflicht: Branch darf nicht hinter origin/main zurückliegen
        wf = _read_active_workflow()
        if wf:
            try:
                fetch = subprocess.run(
                    ["git", "fetch", "origin", "main", "--quiet"],
                    cwd=os.getcwd(), capture_output=True, timeout=10
                )
                if fetch.returncode == 0:
                    behind_result = subprocess.run(
                        ["git", "rev-list", "--count", "HEAD..origin/main"],
                        cwd=os.getcwd(), capture_output=True, text=True, timeout=5
                    )
                    behind = int(behind_result.stdout.strip() or "0")
                    if behind > 0:
                        block(
                            f"BLOCKED — Branch ist {behind} Commit(s) hinter origin/main.\n"
                            "Bitte erst: git fetch origin && git rebase origin/main"
                        )
                # fetch returncode != 0 → kein Netz → silent skip
            except (subprocess.TimeoutExpired, OSError, ValueError):
                pass  # Netzwerk nicht erreichbar → kein Block

        # 5c. Adversary verdict check (if in phase6+)
        if wf:
            phase = wf.get("current_phase", "")
            if phase in ("phase6_implement", "phase6b_adversary", "phase7_validate"):
                # Bug + Feature fast-track: no adversary verdict required
                if wf.get("workflow_type") in ("bug", "feature-fast"):
                    pass
                else:
                    verdict = str(wf.get("adversary_verdict", "") or "")
                    if verdict.startswith("VERIFIED"):
                        pass  # green
                    elif verdict.startswith("AMBIGUOUS"):
                        if not wf.get("adversary_ambiguous_override"):
                            block("BLOCKED: Adversary verdict is AMBIGUOUS. "
                                  "Review findings, then: workflow.py override-ambiguous '<reason>' "
                                  + gate_diagnostics(wf, verdict="AMBIGUOUS"))
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
            scope = _detect_e2e_scope(staged_list, config)
            _write_e2e_scope(wf, scope)
            print(f"E2E scope: {scope}", file=sys.stderr)

    # 6. Allow
    allow()


if __name__ == "__main__":
    main()
