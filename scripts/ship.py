#!/usr/bin/env python3
"""Ausliefern in EINEM Aufruf: pushen, PR anlegen (oder den offenen nutzen), CI abwarten,
optional mergen. Eigenstaendiges Werkzeug, KEIN Hook/Gate (Kontext-Haushalt).

Jeder Einzelschritt (Branch pruefen, `git push`, `gh pr create`, `gh pr checks`, ...)
kostet als eigener Tool-Aufruf das Wiederlesen des ganzen Kontexts. Dieses Skript
buendelt die Kette und gibt nur wenige Zeilen `KEY=value` zurueck. Nur
Standardbibliothek plus `git` und `gh` auf dem PATH. `setup.py` kopiert es in
Konsumenten-Projekte nach `.claude/scripts/ship.py` (neben `ci_spec_gate.py`).

    python3 .claude/scripts/ship.py [--title T] [--body-file F] [--base BRANCH] [--draft]
                                    [--merge squash|merge|rebase] [--branch NAME]
                                    [--timeout S] [--interval S] [--no-wait] [--dry-run]

Ausgabe: `BRANCH=`, `PR=<url>`, `CI=green|red|none|pending|timeout|skipped`,
`FAILED_CHECKS=a,b` (nur bei rot), `MERGED=yes|no|skipped`, dazu Hinweise auf stderr.
Exit 0 = gepusht, PR vorhanden, CI gruen oder ohne Checks und, falls verlangt, gemergt.
Exit 1 = CI rot/Timeout, Merge nicht moeglich. Exit 2 = Vorbedingung verletzt (Default-
Branch ohne --branch, detached HEAD, gh fehlt oder nicht angemeldet). Exit 3 = Push
fehlgeschlagen. Nie `--force`, nie den Default-Branch pushen, nie Schutzregeln umgehen:
blockt eine Schutzregel den Merge, meldet das Skript MERGED=no und endet mit Exit 1.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time

DEFAULT_TIMEOUT_S = 1800
DEFAULT_INTERVAL_S = 30
CHECKS_GRACE_S = 90          # so lange duerfen sich Checks nach dem Push noch registrieren
PUSH_BACKOFF_S = (2, 4, 8)
_OK_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
_PENDING_STATES = {"PENDING", "EXPECTED"}


def _run(args: list[str], timeout: "int | None" = 120) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 124, "", str(exc))


def _git(*args: str) -> subprocess.CompletedProcess:
    return _run(["git", *args])


def _gh(*args: str) -> subprocess.CompletedProcess:
    return _run(["gh", *args], timeout=300)


def _note(text: str) -> None:
    print(text, file=sys.stderr)


def current_branch() -> str:
    res = _git("rev-parse", "--abbrev-ref", "HEAD")
    return res.stdout.strip() if res.returncode == 0 else ""


def default_branch() -> "str | None":
    """Default-Branch des Remotes: `origin/HEAD`, sonst `ls-remote --symref` (#530)."""
    res = _git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip().split("/", 1)[-1]
    res = _git("ls-remote", "--symref", "origin", "HEAD")
    if res.returncode == 0:
        for line in res.stdout.splitlines():
            if line.startswith("ref: refs/heads/"):
                return line.split()[0][len("ref: refs/heads/"):]
    return None


def branch_exists(name: str) -> bool:
    if _git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}").returncode == 0:
        return True
    res = _git("ls-remote", "--heads", "origin", name)
    return res.returncode == 0 and bool(res.stdout.strip())


def unique_branch(name: str) -> str:
    """Name, bei Konflikt lokal oder remote mit Suffix -2, -3 ... (#528)."""
    candidate, n = name, 2
    while branch_exists(candidate):
        candidate = f"{name}-{n}"
        n += 1
    return candidate


def push(branch: str) -> bool:
    for attempt, delay in enumerate((0,) + PUSH_BACKOFF_S):
        if delay:
            time.sleep(delay)
        res = _git("push", "-u", "origin", branch)
        if res.returncode == 0:
            return True
        _note(f"push fehlgeschlagen (Versuch {attempt + 1}): {res.stderr.strip()[:300]}")
        if "rejected" in res.stderr or "protected" in res.stderr:
            return False  # kein Netzfehler: Wiederholen hilft nicht
    return False


def find_pr(branch: str) -> "dict | None":
    res = _gh("pr", "list", "--head", branch, "--state", "open",
              "--json", "number,url,isDraft,baseRefName", "--limit", "1")
    if res.returncode != 0:
        return None
    try:
        rows = json.loads(res.stdout or "[]")
    except json.JSONDecodeError:
        return None
    return rows[0] if rows and isinstance(rows[0], dict) else None


def create_pr(branch: str, base: "str | None", title: "str | None",
              body_file: "str | None", draft: bool) -> "dict | None":
    args = ["pr", "create", "--head", branch]
    if base:
        args += ["--base", base]
    if title:
        args += ["--title", title]
    if body_file:
        args += ["--body-file", body_file]
    elif title:
        args += ["--body", ""]
    if not title and not body_file:
        args.append("--fill")
    if draft:
        args.append("--draft")
    res = _gh(*args)
    if res.returncode != 0:
        _note(f"gh pr create fehlgeschlagen: {res.stderr.strip()[:300]}")
        return None
    return find_pr(branch)


def classify(rollup: list) -> "tuple[str, list[str]]":
    """('none'|'pending'|'red'|'green', rote Check-Namen) aus `statusCheckRollup`."""
    if not rollup:
        return "none", []
    pending, failed = False, []
    for item in rollup:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("context") or "?"
        if item.get("__typename") == "StatusContext" or ("state" in item and "status" not in item):
            state = str(item.get("state", "")).upper()
            if state in _PENDING_STATES:
                pending = True
            elif state != "SUCCESS":
                failed.append(name)
            continue
        status = str(item.get("status", "")).upper()
        if status != "COMPLETED":
            pending = True
            continue
        if str(item.get("conclusion", "")).upper() not in _OK_CONCLUSIONS:
            failed.append(name)
    if failed:
        return "red", failed
    return ("pending", []) if pending else ("green", [])


def pr_view(number: int) -> "dict | None":
    res = _gh("pr", "view", str(number), "--json",
              "statusCheckRollup,mergeStateStatus,mergeable,url,isDraft")
    if res.returncode != 0:
        return None
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def wait_ci(number: int, timeout_s: int, interval_s: int) -> "tuple[str, list[str], dict]":
    start = time.monotonic()
    view: dict = {}
    while True:
        view = pr_view(number) or view
        state, failed = classify(view.get("statusCheckRollup") or [])
        elapsed = time.monotonic() - start
        if state in {"red", "green"}:
            return state, failed, view
        if state == "none" and elapsed >= CHECKS_GRACE_S:
            return "none", [], view
        if elapsed >= timeout_s:
            return "timeout", [], view
        time.sleep(max(5, interval_s))


def merge_pr(number: int, method: str, is_draft: bool) -> bool:
    if is_draft:
        res = _gh("pr", "ready", str(number))
        if res.returncode != 0:
            _note(f"gh pr ready fehlgeschlagen: {res.stderr.strip()[:300]}")
            return False
    res = _gh("pr", "merge", str(number), f"--{method}")
    if res.returncode != 0:
        _note(f"gh pr merge fehlgeschlagen: {res.stderr.strip()[:300]}")
        return False
    return True


def parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--title")
    ap.add_argument("--body-file")
    ap.add_argument("--base", help="Ziel-Branch (Default: Default-Branch des Remotes)")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--merge", choices=("squash", "merge", "rebase"),
                    help="bei gruener CI (oder ohne Checks) mergen")
    ap.add_argument("--branch", help="Feature-Branch anlegen, wenn HEAD auf dem Default-Branch steht")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_S)
    ap.add_argument("--no-wait", action="store_true", help="CI nicht abwarten")
    ap.add_argument("--dry-run", action="store_true", help="nur zeigen, nichts pushen")
    return ap.parse_args(argv)


def main(argv: "list[str] | None" = None) -> int:
    args = parse_args(argv)
    if _git("rev-parse", "--git-dir").returncode != 0:
        _note("kein Git-Repository")
        return 2
    branch = current_branch()
    base = args.base or default_branch()
    on_default = branch in {"HEAD", "", "main", "master"} or bool(base and branch == base)
    if on_default:
        if branch == "HEAD" or not branch:
            _note("detached HEAD: erst einen Branch auschecken")
            return 2
        if not args.branch:
            _note(f"HEAD steht auf {branch!r} (Default-Branch): nicht pushen; "
                  "--branch <name> legt den Feature-Branch an")
            return 2
        target = unique_branch(args.branch)
        if args.dry_run:
            _note(f"dry-run: git switch -c {target}")
        elif _git("switch", "-c", target).returncode != 0:
            _note(f"git switch -c {target} fehlgeschlagen")
            return 2
        branch = target
    if _git("status", "--porcelain").stdout.strip():
        _note("Hinweis: uncommittete Aenderungen bleiben lokal (nicht Teil des PR)")
    print(f"BRANCH={branch}")
    if args.dry_run:
        _note(f"dry-run: git push -u origin {branch}; gh pr create --base {base or '?'}; CI abwarten"
              + (f"; gh pr merge --{args.merge}" if args.merge else ""))
        return 0
    if not push(branch):
        print("PR=none")
        return 3
    if not shutil.which("gh"):
        print("PR=none")
        _note("gh fehlt: gepusht, PR und CI bleiben offen")
        return 2
    if _gh("auth", "status").returncode != 0:
        print("PR=none")
        _note("gh nicht angemeldet: gepusht, PR und CI bleiben offen")
        return 2
    pr = find_pr(branch) or create_pr(branch, base, args.title, args.body_file, args.draft)
    if not pr:
        print("PR=none")
        return 1
    number = int(pr["number"])
    print(f"PR={pr.get('url', '')}")
    if args.no_wait:
        print("CI=skipped")
        print("MERGED=skipped")
        return 0
    state, failed, view = wait_ci(number, args.timeout, args.interval)
    print(f"CI={state}")
    if failed:
        print("FAILED_CHECKS=" + ",".join(failed))
    if state not in {"green", "none"}:
        print("MERGED=no")
        return 1
    if not args.merge:
        print("MERGED=skipped")
        return 0
    if str(view.get("mergeable", "")).upper() == "CONFLICTING":
        _note("Merge-Konflikt mit dem Default-Branch: erst aufloesen")
        print("MERGED=no")
        return 1
    merged = merge_pr(number, args.merge, bool(pr.get("isDraft") or view.get("isDraft")))
    print(f"MERGED={'yes' if merged else 'no'}")
    return 0 if merged else 1


if __name__ == "__main__":
    sys.exit(main())
