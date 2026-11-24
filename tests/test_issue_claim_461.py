"""Verpflichtende Registrierung je Issue ueber GitHub-Kommentare (Issue #461).

Spec: docs/specs/feat-461-issue-registrierung.md (AC-1 bis AC-15).

Aufbau
------
- `gh` ist die Netzgrenze. Ein Ersatzprogramm (`_FAKE_GH`, Python) liegt in einem
  eigenen PATH-Verzeichnis, haelt den Zustand von GitHub in einer JSON-Datei
  (Issues offen/geschlossen, Kommentare, offene Pull Requests) und protokolliert
  jeden Aufruf als JSON-Zeile (argv, Methode, Endpunkt, Art, Felder).
- `workflow.py` laeuft als Subprozess in temporaeren Projekten (`.git` als
  Verzeichnis, `.claude/config.yaml` mit Abschnitt `issue_claim:`). Mehrere
  Projekte teilen sich denselben Fake-Zustand: so spielen zwei Projekte zwei
  Sitzungen auf verschiedenen Rechnern, die dasselbe Issue sehen.
- Der Titel-Cache (`.claude/issue_titles.json`, `issue_briefs.json`) ist vorbelegt,
  damit der bestehende abgekoppelte Titelabruf (#490) kein `gh` ruft und das
  Protokoll nur die Registrierung zeigt.
- `tests/conftest.py` setzt (nach Umsetzung) `OPENSPEC_ISSUE_CLAIM=0` per autouse;
  die Tests dieser Datei entfernen die Variable gezielt wieder (monkeypatch),
  ausser AC-14, das genau diese Fixture prueft.

Die Tests legen kein Kommentarformat ueber die Spec hinaus fest: Marker
`openspec-claim v1`, Status-Woerter `aktiv`/`freigegeben`/`zurückgezogen`/
`übernommen` (bevorzugt in einer Zeile `Status: <wort>` o. ae., ersatzweise das
einzige vorkommende Status-Wort), Ort, Sitzungsname, Beginn, Phase.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WORKFLOW_PY = HOOKS_DIR / "workflow.py"
COMMANDS_DIR = REPO_ROOT / "core" / "commands"
SYNC_SKILLS = REPO_ROOT / "scripts" / "sync_skills.py"
CONFTEST = Path(__file__).resolve().parent / "conftest.py"

MARKER = "openspec-claim v1"
STATUS_WORDS = ("aktiv", "freigegeben", "zurückgezogen", "übernommen")
CLOUD_REACH = "Sitzungsliste des Claude-Kontos, Antwort am Issue"
ALPHA = "feat-461-alpha"
BETA = "feat-461-beta"


# --------------------------------------------------------------------------
# Fake-gh
# --------------------------------------------------------------------------

_FAKE_GH = r'''#!{python}
"""Ersatz fuer `gh` (Tests zu #461). Zustand: $FAKE_GH_STATE, Protokoll: $FAKE_GH_LOG.

Unterstuetzte Aufrufformen
--------------------------
gh api <endpunkt> [Optionen]
    Endpunkt mit oder ohne fuehrenden `/`, `{owner}/{repo}` oder beliebiger
    Besitzer/Repo-Name, Query-String wird ignoriert bzw. fuer `state=` gelesen:
      repos/O/R/issues/N/comments        GET listet, POST legt an
      repos/O/R/issues/comments/ID       GET, PATCH (auch POST) bearbeitet, DELETE
      repos/O/R/issues/N                 GET (Status open/closed, Titel)
      repos/O/R/pulls                    GET offene Pull Requests
      search/issues?q=...                GET (items = offene Pull Requests)
    Methode: -X/--method M (auch --method=M); ohne Angabe GET, mit Feldern
    oder --input POST (wie echtes gh).
    Felder: -f/--raw-field k=v, -F/--field k=v (v=@datei liest Datei, @- stdin),
    --input DATEI|- (JSON-Objekt).
    --jq/-q EXPR wird ueber das echte jq ($FAKE_GH_JQ) mit `jq -r` angewandt.
    Ignoriert: --paginate, --slurp, --silent, -i/--include, --verbose,
    -H/--header V, --hostname V, --cache V, -p/--preview V.
gh issue view N [--json felder] [--jq EXPR]   Status OPEN/CLOSED, comments[]
gh issue comment N --body T | --body-file DATEI|-   legt Kommentar an
gh pr list [--state open] [--search S] [--json felder] [--limit N] [--jq EXPR]
gh repo view [--json ...]                      nameWithOwner
gh auth status | gh auth token                 Exit 0

Kommentare tragen REST- und GraphQL-Feldnamen zugleich (id, body, created_at/
createdAt, updated_at/updatedAt, author_association/authorAssociation,
user.login/author.login).

Fehlermodi (Zustandsdatei, Schluessel "mode"; ersatzweise $FAKE_GH_MODE):
  "exit1"  -> stderr + Exit 1
  "sleep"  -> schlaeft "sleep_seconds" (Standard 3) und arbeitet dann normal
  "only_kinds": [...] beschraenkt den Fehlermodus auf Aufrufarten
  (z. B. ["edit_comment"]). Jeder Aufruf wird VOR dem Fehlermodus protokolliert.
"""
import fcntl, json, os, re, subprocess, sys, time
from datetime import datetime, timezone

STATE = os.environ["FAKE_GH_STATE"]
LOG = os.environ["FAKE_GH_LOG"]
LOCK = STATE + ".lock"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def locked(fn):
    with open(LOCK, "a+") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            with open(STATE, encoding="utf-8") as fh:
                st = json.load(fh)
            result, changed = fn(st)
            if changed:
                tmp = STATE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(st, fh, ensure_ascii=False, indent=1)
                os.replace(tmp, STATE)
            return result
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def log(entry):
    with open(LOCK, "a+") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            with open(LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


_STDIN = None


def stdin_text():
    global _STDIN
    if _STDIN is None:
        _STDIN = sys.stdin.read()
    return _STDIN


def issue_obj(st, n, upper=False):
    iss = st["issues"].get(str(n), {"state": "open", "title": "Issue %s" % n})
    state = iss.get("state", "open")
    return {"number": int(n), "state": state.upper() if upper else state,
            "title": iss.get("title", ""), "body": iss.get("body", "")}


def comment_out(c):
    out = dict(c)
    out["createdAt"] = c["created_at"]
    out["updatedAt"] = c["updated_at"]
    out["authorAssociation"] = c["author_association"]
    out["author"] = {"login": c["user"]["login"]}
    return out


def pull_out(p, upper=False):
    return {"number": p["number"], "title": p.get("title", ""), "body": p.get("body", ""),
            "state": "OPEN" if upper else "open", "head": {"ref": p.get("headRefName", "")},
            "headRefName": p.get("headRefName", ""), "isDraft": False,
            "pull_request": {}}


def create_comment(st, n, body):
    cid = st["next_id"]
    st["next_id"] = cid + 1
    ts = now()
    c = {"id": cid, "node_id": "IC_%d" % cid, "body": body, "created_at": ts,
         "updated_at": ts, "author_association": st.get("new_author_association", "OWNER"),
         "user": {"login": "owner"}, "issue": str(n)}
    st["comments"].setdefault(str(n), []).append(c)
    return c


def find_comment(st, cid):
    for lst in st["comments"].values():
        for c in lst:
            if str(c["id"]) == str(cid) or c.get("node_id") == str(cid):
                return lst, c
    return None, None


def emit(obj, jq):
    text = json.dumps(obj, ensure_ascii=False)
    if jq:
        jqbin = os.environ.get("FAKE_GH_JQ")
        if not jqbin:
            sys.stderr.write("fake gh: --jq ohne jq\n")
            sys.exit(1)
        res = subprocess.run([jqbin, "-r", jq], input=text, capture_output=True, text=True)
        if res.returncode != 0:
            sys.stderr.write(res.stderr)
            sys.exit(1)
        sys.stdout.write(res.stdout)
    else:
        sys.stdout.write(text + "\n")


VALUE_OPTS = {"-H", "--header", "--hostname", "--cache", "-p", "--preview", "-t",
              "--template", "--repo", "-R", "--limit", "-L", "--state", "-s",
              "--search", "-S", "--base", "-B", "--head", "--label", "-l",
              "--author", "-A", "--assignee", "-a"}


def split_eq(argv):
    out = []
    for a in argv:
        if a.startswith("--") and "=" in a and a.split("=", 1)[0] in (
                "--method", "--jq", "--input", "--raw-field", "--field", "--json",
                "--body", "--body-file", "--repo", "--state", "--search", "--limit",
                "--header", "--hostname", "--cache", "--template", "--preview"):
            k, v = a.split("=", 1)
            out += [k, v]
        else:
            out.append(a)
    return out


def parse(argv):
    o = {"pos": [], "fields": {}, "method": None, "jq": None, "input": None,
         "json": None, "body": None, "body_file": None, "opts": {}}
    i = 0
    while i < len(argv):
        a = argv[i]
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        if a in ("-X", "--method"):
            o["method"] = (nxt or "").upper(); i += 2
        elif a in ("--jq", "-q"):
            o["jq"] = nxt; i += 2
        elif a == "--input":
            o["input"] = nxt; i += 2
        elif a in ("-f", "--raw-field", "-F", "--field"):
            k, _, v = (nxt or "").partition("=")
            if a in ("-F", "--field") and v.startswith("@"):
                src = v[1:]
                v = stdin_text() if src == "-" else open(src, encoding="utf-8").read()
            o["fields"][k] = v; i += 2
        elif a == "--json":
            o["json"] = nxt; i += 2
        elif a in ("--body", "-b"):
            o["body"] = nxt; i += 2
        elif a == "--body-file":
            o["body_file"] = nxt; i += 2
        elif a in VALUE_OPTS:
            o["opts"][a] = nxt; i += 2
        elif a.startswith("-"):
            i += 1
        else:
            o["pos"].append(a); i += 1
    return o


def body_from(o):
    if "body" in o["fields"]:
        return o["fields"]["body"]
    if o["input"] is not None:
        raw = stdin_text() if o["input"] == "-" else open(o["input"], encoding="utf-8").read()
        try:
            data = json.loads(raw)
            return data.get("body") if isinstance(data, dict) else None
        except ValueError:
            return None
    if o["body"] is not None:
        return o["body"]
    if o["body_file"] is not None:
        return stdin_text() if o["body_file"] == "-" else open(o["body_file"], encoding="utf-8").read()
    return None


def classify(argv, o):
    """(kind, details) eines Aufrufs bestimmen, ohne Zustand zu aendern."""
    if not argv:
        return "unknown", {}
    if argv[0] == "api":
        ep = (o["pos"][1] if len(o["pos"]) > 1 else "").lstrip("/")
        path, _, query = ep.partition("?")
        has_payload = bool(o["fields"]) or o["input"] is not None
        method = o["method"] or ("POST" if has_payload else "GET")
        m = re.fullmatch(r"repos/[^/]+/[^/]+/issues/(\d+)/comments", path)
        if m:
            kind = "create_comment" if method == "POST" else "list_comments"
            return kind, {"issue": m.group(1), "method": method}
        m = re.fullmatch(r"repos/[^/]+/[^/]+/issues/comments/(\d+)", path)
        if m:
            kind = {"PATCH": "edit_comment", "POST": "edit_comment",
                    "DELETE": "delete_comment"}.get(method, "get_comment")
            return kind, {"comment_id": m.group(1), "method": method}
        m = re.fullmatch(r"repos/[^/]+/[^/]+/issues/(\d+)", path)
        if m:
            return "get_issue", {"issue": m.group(1), "method": method}
        if re.fullmatch(r"repos/[^/]+/[^/]+/pulls", path):
            return "list_pulls", {"method": method, "query": query}
        if path == "search/issues":
            return "search", {"method": method, "query": query}
        return "unknown", {"endpoint": ep, "method": method}
    if argv[0] == "issue" and len(o["pos"]) > 1 and o["pos"][1] == "view":
        return "issue_view", {"issue": o["pos"][2] if len(o["pos"]) > 2 else ""}
    if argv[0] == "issue" and len(o["pos"]) > 1 and o["pos"][1] == "comment":
        return "create_comment", {"issue": o["pos"][2] if len(o["pos"]) > 2 else "",
                                  "method": "POST"}
    if argv[0] == "pr" and len(o["pos"]) > 1 and o["pos"][1] == "list":
        return "pr_list", {}
    if argv[0] == "repo" and len(o["pos"]) > 1 and o["pos"][1] == "view":
        return "repo_view", {}
    if argv[0] == "auth":
        return "auth", {}
    return "unknown", {}


def main():
    argv = split_eq(sys.argv[1:])
    o = parse(argv)
    kind, det = classify(argv, o)
    body = body_from(o) if kind in ("create_comment", "edit_comment") else None
    entry = {"t": time.time(), "argv": sys.argv[1:], "kind": kind, "body": body}
    entry.update(det)
    log(entry)

    st0 = locked(lambda st: (st, False))
    mode = st0.get("mode") or os.environ.get("FAKE_GH_MODE")
    only = st0.get("only_kinds")
    if mode and (not only or kind in only):
        if mode == "exit1":
            sys.stderr.write("gh: HTTP 502 Bad Gateway (Fake)\n")
            sys.exit(1)
        if mode == "sleep":
            time.sleep(float(st0.get("sleep_seconds", 3)))

    jq = o["jq"]
    if kind == "list_comments":
        cs = locked(lambda st: ([comment_out(c) for c in st["comments"].get(det["issue"], [])], False))
        return emit(cs, jq)
    if kind == "create_comment":
        if not body:
            sys.stderr.write("gh: body fehlt (Fake)\n"); sys.exit(1)
        c = locked(lambda st: (create_comment(st, det["issue"], body), True))
        if argv[0] == "issue":
            sys.stdout.write("https://github.invalid/issue#comment-%s\n" % c["id"])
            return
        return emit(comment_out(c), jq)
    if kind in ("edit_comment", "get_comment", "delete_comment"):
        def op(st):
            lst, c = find_comment(st, det["comment_id"])
            if c is None:
                return None, False
            if kind == "edit_comment":
                if body is not None:
                    c["body"] = body
                c["updated_at"] = now()
                return comment_out(c), True
            if kind == "delete_comment":
                lst.remove(c)
                return {}, True
            return comment_out(c), False
        res = locked(op)
        if res is None:
            sys.stderr.write("gh: HTTP 404 Not Found (Fake)\n"); sys.exit(1)
        return emit(res, jq)
    if kind == "get_issue":
        return emit(locked(lambda st: (issue_obj(st, det["issue"]), False)), jq)
    if kind == "list_pulls":
        return emit(locked(lambda st: ([pull_out(p) for p in st["pulls"]], False)), jq)
    if kind == "search":
        items = locked(lambda st: ([pull_out(p) for p in st["pulls"]], False))
        return emit({"total_count": len(items), "items": items}, jq)
    if kind == "issue_view":
        def op(st):
            obj = issue_obj(st, det["issue"], upper=True)
            obj["comments"] = [comment_out(c) for c in st["comments"].get(det["issue"], [])]
            return obj, False
        obj = locked(op)
        if o["json"] is None and not jq:
            sys.stdout.write("%s\t%s\n" % (obj["title"], obj["state"]))
            return
        return emit(obj, jq)
    if kind == "pr_list":
        items = locked(lambda st: ([pull_out(p, upper=True) for p in st["pulls"]], False))
        if o["json"] is None and not jq:
            for p in items:
                sys.stdout.write("%d\t%s\t%s\tOPEN\n" % (p["number"], p["title"], p["headRefName"]))
            return
        return emit(items, jq)
    if kind == "repo_view":
        return emit({"nameWithOwner": "owner/repo", "name": "repo",
                     "owner": {"login": "owner"}}, jq)
    if kind == "auth":
        if len(argv) > 1 and argv[1] == "token":
            sys.stdout.write("gho_fake_token_nicht_echt\n")
        return
    sys.stderr.write("fake gh: unbekannter Aufruf: %r\n" % (sys.argv[1:],))
    sys.exit(1)


main()
'''


class GhWorld:
    """Gemeinsamer Fake-GitHub-Zustand plus Hilfen fuer Temp-Projekte."""

    def __init__(self, root: Path):
        self.root = root
        self.state_file = root / "gh-state.json"
        self.log_file = root / "gh-calls.jsonl"
        self.save({"issues": {"461": {"state": "open", "title": "Registrierung"}},
                   "comments": {}, "pulls": [], "next_id": 5001, "mode": None,
                   "only_kinds": None, "sleep_seconds": 3})
        self.log_file.write_text("")
        self.bin_gh = self._bin_dir(with_gh=True)
        self.bin_nogh = self._bin_dir(with_gh=False)

    # --- Zustand -----------------------------------------------------------
    def load(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def save(self, data: dict) -> None:
        self.state_file.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                   encoding="utf-8")

    def update(self, **fields) -> None:
        data = self.load()
        data.update(fields)
        self.save(data)

    def comments(self, issue="461") -> list:
        return self.load()["comments"].get(str(issue), [])

    def claims(self, issue="461") -> list:
        return [c for c in self.comments(issue) if MARKER in (c.get("body") or "")]

    def claim_of(self, name: str, issue="461") -> "dict | None":
        pat = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
        hits = [c for c in self.claims(issue) if pat.search(c["body"])]
        assert len(hits) <= 1, f"mehr als ein Eintrag fuer {name}: {hits}"
        return hits[0] if hits else None

    def calls(self) -> list:
        out = []
        for line in self.log_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out

    def creates(self, issue="461") -> list:
        return [c for c in self.calls()
                if c["kind"] == "create_comment" and str(c.get("issue")) == str(issue)]

    def edits(self) -> list:
        return [c for c in self.calls() if c["kind"] == "edit_comment"]

    # --- Umgebung ----------------------------------------------------------
    def _bin_dir(self, with_gh: bool) -> Path:
        bindir = self.root / ("bin-gh" if with_gh else "bin-nogh")
        bindir.mkdir()
        for tool, target in (("python3", sys.executable), ("git", shutil.which("git"))):
            if target:
                (bindir / tool).symlink_to(target)
        if with_gh:
            gh = bindir / "gh"
            gh.write_text(_FAKE_GH.replace("{python}", sys.executable, 1))
            gh.chmod(0o755)
        return bindir

    def project(self, name: str, label: "str | None" = "iMac", enabled: bool = True,
                timeout: float = 1) -> Path:
        proj = self.root / name
        (proj / ".git").mkdir(parents=True)
        wf = proj / ".claude" / "workflows"
        (wf / "_log").mkdir(parents=True)
        (wf / "_archive").mkdir()
        (proj / "_home").mkdir()
        cfg = ["issue_claim:", f"  enabled: {'true' if enabled else 'false'}",
               f"  timeout_seconds: {timeout}"]
        if label is not None:
            cfg.append(f'  location_label: "{label}"')
        (proj / ".claude" / "config.yaml").write_text("\n".join(cfg) + "\n")
        issues = [str(n) for n in range(461, 470)]
        (proj / ".claude" / "issue_titles.json").write_text(
            json.dumps({n: f"Titel {n}" for n in issues}))
        (proj / ".claude" / "issue_briefs.json").write_text(json.dumps(
            {n: {"title": f"Titel {n}", "problem": "p", "goal": "g", "source": "manual",
                 "at": "2026-11-24T08:00:00"} for n in issues}))
        return proj

    def env(self, proj: Path, with_gh: bool = True, **extra) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("OPENSPEC_", "HERDR_", "STUB_", "FAKE_GH_"))
               and k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_CODE_SESSION_ID",
                             "CLAUDE_PLUGIN_ROOT", "CLAUDE_CODE_REMOTE",
                             "GH_TOKEN", "GITHUB_TOKEN")}
        env["CLAUDE_PROJECT_DIR"] = str(proj)
        env["HOME"] = str(proj / "_home")
        env["PATH"] = str(self.bin_gh if with_gh else self.bin_nogh)
        env["FAKE_GH_STATE"] = str(self.state_file)
        env["FAKE_GH_LOG"] = str(self.log_file)
        jq = shutil.which("jq")
        if jq:
            env["FAKE_GH_JQ"] = jq
        env.update({k: str(v) for k, v in extra.items()})
        return env

    def run(self, proj: Path, *args, with_gh: bool = True, timeout: float = 60,
            **extra) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(WORKFLOW_PY), *args],
                              capture_output=True, text=True, cwd=str(proj),
                              env=self.env(proj, with_gh=with_gh, **extra),
                              timeout=timeout)


@pytest.fixture
def world(tmp_path, monkeypatch):
    # Nach Umsetzung setzt conftest OPENSPEC_ISSUE_CLAIM=0; hier gezielt zurueck.
    monkeypatch.delenv("OPENSPEC_ISSUE_CLAIM", raising=False)
    return GhWorld(tmp_path)


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------

def _out(res: subprocess.CompletedProcess) -> str:
    return (res.stdout or "") + "\n" + (res.stderr or "")


def _ok(res: subprocess.CompletedProcess, what: str) -> None:
    assert res.returncode == 0, f"{what}: Exit {res.returncode}\n{_out(res)}"


def _wf_file(proj: Path, name: str) -> Path:
    return proj / ".claude" / "workflows" / f"{name}.json"


def _wf_state(proj: Path, name: str) -> dict:
    return json.loads(_wf_file(proj, name).read_text())


def _claim_state(proj: Path, name: str) -> dict:
    claim = _wf_state(proj, name).get("issue_claim")
    assert isinstance(claim, dict), f"issue_claim fehlt im Workflow-State von {name}: {claim!r}"
    return claim


def _claim_id(claim: dict):
    for key in ("comment_id", "id"):
        if claim.get(key) not in (None, ""):
            return str(claim[key])
    return None


def _status(body: str) -> "str | None":
    """Status aus dem maschinenlesbaren Block, ersatzweise einziges Status-Wort."""
    words = "|".join(STATUS_WORDS)
    m = re.search(rf"(?i)status\W{{0,6}}?[:=|]\s*[*`\"']*\s*({words})", body)
    if m:
        return m.group(1).lower()
    found = [w for w in STATUS_WORDS if re.search(rf"(?i)(?<!\w){w}(?!\w)", body)]
    return found[0] if len(found) == 1 else None


def _wait(pred, timeout: float = 6.0, step: float = 0.1):
    end = time.monotonic() + timeout
    value = pred()
    while not value and time.monotonic() < end:
        time.sleep(step)
        value = pred()
    return value


def _start_registered(world: GhWorld, proj: Path, name: str, issue="461") -> dict:
    """`start` und Vorbedingung: genau ein aktiver Eintrag dieser Sitzung am Issue."""
    res = world.run(proj, "start", name)
    _ok(res, f"start {name}")
    claim = world.claim_of(name, issue)
    assert claim is not None, (
        f"start {name} hat keinen Eintrag am Issue #{issue} angelegt.\n"
        f"gh-Aufrufe: {world.calls()}\nAusgabe:\n{_out(res)}")
    assert _status(claim["body"]) == "aktiv", f"Eintrag nicht aktiv: {claim['body']!r}"
    return claim


def _date_forms(iso_ts: str) -> list:
    ts = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    local = ts.astimezone()
    forms = {ts.strftime("%Y-%m-%d"), ts.strftime("%d.%m.%Y"), ts.strftime("%d.%m."),
             ts.strftime("%H:%M"), local.strftime("%H:%M"), local.strftime("%d.%m.")}
    forms.add(f"{ts.day}.{ts.month}.")
    return sorted(forms)


# --------------------------------------------------------------------------
# AC-1
# --------------------------------------------------------------------------

def test_start_registriert_kommentar_mit_marker_ohne_at_pfade_links(world):
    """AC-1: genau ein Kommentar mit Marker, Ort, Name, Beginn (UTC), Phase, aktiv;
    kein `@`, keine Pfade, keine Links."""
    proj = world.project("proj-a", label="iMac")
    before = datetime.now(timezone.utc)
    res = world.run(proj, "start", ALPHA)
    _ok(res, "start")
    assert _wf_file(proj, ALPHA).exists(), "Workflow-Datei fehlt nach start"

    creates = world.creates("461")
    assert len(creates) == 1, f"genau ein Anlegen am Issue erwartet, war {len(creates)}: {world.calls()}"
    claims = world.claims("461")
    assert len(claims) == 1, f"genau ein Eintrag mit Marker erwartet: {world.comments()}"
    body = claims[0]["body"]

    assert MARKER in body
    assert "iMac" in body, f"Ort fehlt: {body!r}"
    assert ALPHA in body, f"Sitzungsname fehlt: {body!r}"
    assert re.search(r"(?i)phase1_context|kontext|context", body), f"Phase fehlt: {body!r}"
    assert _status(body) == "aktiv", f"Status aktiv fehlt: {body!r}"
    assert any(f in body for f in {before.strftime("%Y-%m-%d"), before.strftime("%d.%m.%Y")}), \
        f"Beginn (Datum) fehlt: {body!r}"
    assert re.search(r"UTC|\d{2}:\d{2}(:\d{2})?(Z|\+00:00)", body), f"Beginn nicht als UTC: {body!r}"

    assert "@" not in body, f"`@` im Kommentar: {body!r}"
    assert "http" not in body.lower() and "www." not in body.lower(), f"Link im Kommentar: {body!r}"
    assert str(world.root) not in body and str(proj) not in body, "Projektpfad im Kommentar"
    assert not re.search(r"(^|[\s(`'\"])(~|\.{0,2})/\w|\w/\w", body), f"Pfad im Kommentar: {body!r}"

    claim = _claim_state(proj, ALPHA)
    assert _claim_id(claim) == str(claims[0]["id"]), f"Kommentar-ID nicht im State: {claim}"


# --------------------------------------------------------------------------
# AC-2
# --------------------------------------------------------------------------

def test_doppelstart_fruehester_gewinnt_verlierer_zieht_zurueck_ohne_workflow_datei(world):
    """AC-2: zweite Sitzung auf demselben Issue bricht ab, zieht ihren Eintrag
    zurueck, schreibt keine Workflow-Datei und nennt den Gewinner im Klartext."""
    proj_a = world.project("rechner-a", label="iMac")
    proj_b = world.project("rechner-b", label="Server")
    winner = _start_registered(world, proj_a, ALPHA)

    res = world.run(proj_b, "start", BETA)
    out = _out(res)
    assert res.returncode != 0, f"zweiter start muss abbrechen:\n{out}"
    assert not _wf_file(proj_b, BETA).exists(), "Verlierer darf keine Workflow-Datei schreiben"

    a_now = world.claim_of(ALPHA)
    assert _status(a_now["body"]) == "aktiv", f"Gewinner muss aktiv bleiben: {a_now['body']!r}"
    loser = world.claim_of(BETA)
    assert loser is not None, f"Verlierer muss erst eintragen, dann zurueckziehen: {world.comments()}"
    assert _status(loser["body"]) == "zurückgezogen", f"Verlierer nicht zurueckgezogen: {loser['body']!r}"

    assert ALPHA in out, f"Klartext nennt die Sitzung nicht:\n{out}"
    assert "iMac" in out, f"Klartext nennt den Ort nicht:\n{out}"
    assert "Terminal" in out, f"Klartext nennt die Erreichbarkeit nicht:\n{out}"
    assert any(f in out for f in _date_forms(winner["created_at"])), \
        f"Klartext nennt den Beginn nicht:\n{out}"
    assert "--uebernehmen" in out, f"Hinweis auf --uebernehmen fehlt:\n{out}"


# --------------------------------------------------------------------------
# AC-3
# --------------------------------------------------------------------------

def test_uebernehmen_setzt_fremden_eintrag_und_startet(world):
    """AC-3: `start <name> --uebernehmen` setzt den fremden Eintrag auf
    `übernommen`, legt einen eigenen an und schreibt die Workflow-Datei."""
    proj_a = world.project("rechner-a", label="iMac")
    proj_b = world.project("rechner-b", label="Server")
    _start_registered(world, proj_a, ALPHA)

    res = world.run(proj_b, "start", BETA, "--uebernehmen")
    _ok(res, "start --uebernehmen")
    assert _wf_file(proj_b, BETA).exists(), "Workflow-Datei fehlt nach Uebernahme"

    a_now = world.claim_of(ALPHA)
    assert _status(a_now["body"]) == "übernommen", f"fremder Eintrag nicht übernommen: {a_now['body']!r}"
    own = world.claim_of(BETA)
    assert own is not None, f"eigener Eintrag fehlt: {world.comments()}"
    assert _status(own["body"]) == "aktiv", f"eigener Eintrag nicht aktiv: {own['body']!r}"
    assert _claim_id(_claim_state(proj_b, BETA)) == str(own["id"])


# --------------------------------------------------------------------------
# AC-4
# --------------------------------------------------------------------------

def test_nicht_owner_und_markerlose_kommentare_werden_ignoriert(world):
    """AC-4: Marker-Kommentare ohne `authorAssociation == OWNER` und Kommentare
    ohne Marker blockieren den Start nicht und werden nicht angefasst."""
    proj_a = world.project("rechner-a", label="iMac")
    proj_b = world.project("rechner-b", label="Server")
    _start_registered(world, proj_a, ALPHA)

    data = world.load()
    for c in data["comments"]["461"]:
        c["author_association"] = "CONTRIBUTOR"
    data["comments"]["461"].append({
        "id": 4000, "node_id": "IC_4000", "body": "Ich arbeite gerade an diesem Issue.",
        "created_at": "2026-11-20T08:00:00Z", "updated_at": "2026-11-20T08:00:00Z",
        "author_association": "OWNER", "user": {"login": "owner"}, "issue": "461"})
    world.save(data)
    foreign_body = world.claim_of(ALPHA)["body"]

    res = world.run(proj_b, "start", BETA)
    _ok(res, "start trotz Nicht-OWNER-/markerlosem Kommentar")
    assert _wf_file(proj_b, BETA).exists()
    own = world.claim_of(BETA)
    assert own is not None and _status(own["body"]) == "aktiv", f"eigener Eintrag fehlt/nicht aktiv: {own}"
    assert world.claim_of(ALPHA)["body"] == foreign_body, "Nicht-OWNER-Eintrag darf nicht bearbeitet werden"
    markerless = [c for c in world.comments() if c["id"] == 4000][0]
    assert markerless["body"] == "Ich arbeite gerade an diesem Issue."


# --------------------------------------------------------------------------
# AC-5
# --------------------------------------------------------------------------

def test_geschlossenes_issue_gilt_als_frei(world):
    """AC-5: geschlossenes Issue mit aktivem fremdem Eintrag -> Start gelingt."""
    proj_a = world.project("rechner-a", label="iMac")
    proj_b = world.project("rechner-b", label="Server")
    _start_registered(world, proj_a, ALPHA)
    data = world.load()
    data["issues"]["461"]["state"] = "closed"
    world.save(data)

    res = world.run(proj_b, "start", BETA)
    _ok(res, "start auf geschlossenem Issue")
    assert _wf_file(proj_b, BETA).exists(), "Workflow-Datei fehlt"


# --------------------------------------------------------------------------
# AC-6
# --------------------------------------------------------------------------

def test_offline_startet_mit_warnung_pending_und_holt_bei_switch_und_phasenwechsel_nach(world):
    """AC-6: ohne gh / gh-Fehler / Zeitlimit -> Start mit Warnung, Status
    `pending`; `switch` bzw. der naechste Phasenwechsel holen bei erreichbarem gh
    nach und setzen den Status auf aktiv."""
    cases = [  # (Fall, Issue, Nachholweg)
        ("ohne-gh", "462", "switch"),
        ("exit1", "463", "phase"),
        ("zeitlimit", "464", "switch"),
    ]
    for case, issue, catch_up in cases:
        name = f"feat-{issue}-{case}"
        proj = world.project(f"proj-{case}", label="iMac", timeout=1)
        with_gh = case != "ohne-gh"
        world.update(mode={"exit1": "exit1", "zeitlimit": "sleep"}.get(case),
                     only_kinds=None, sleep_seconds=4)

        t0 = time.monotonic()
        res = world.run(proj, "start", name, with_gh=with_gh)
        elapsed = time.monotonic() - t0
        world.update(mode=None)
        out = _out(res)
        _ok(res, f"[{case}] start muss trotz gh-Problem laufen")
        assert _wf_file(proj, name).exists(), f"[{case}] Workflow-Datei fehlt"
        assert re.search(r"(?i)warn|⚠", out), f"[{case}] Warnung fehlt:\n{out}"
        assert _claim_state(proj, name).get("status") == "pending", \
            f"[{case}] issue_claim.status != pending: {_wf_state(proj, name).get('issue_claim')}"
        if case == "zeitlimit":
            assert elapsed < 15, f"[{case}] Zeitlimit nicht eingehalten: {elapsed:.1f}s"

        if catch_up == "switch":
            res2 = world.run(proj, "switch", name)
            _ok(res2, f"[{case}] switch")
        else:
            data = _wf_state(proj, name)
            data["context_file"] = "docs/context/x.md"
            _wf_file(proj, name).write_text(json.dumps(data))
            res2 = world.run(proj, "phase", "phase2_analyse")
            _ok(res2, f"[{case}] Phasenwechsel")

        def caught_up(proj=proj, name=name):
            claim = _wf_state(proj, name).get("issue_claim") or {}
            return claim.get("status") in ("aktiv", "active") and _claim_id(claim)

        assert _wait(caught_up, timeout=8), \
            f"[{case}] Registrierung nicht nachgeholt: {_wf_state(proj, name).get('issue_claim')}"
        own = world.claim_of(name, issue)
        assert own is not None and _status(own["body"]) == "aktiv", \
            f"[{case}] kein aktiver Eintrag am Issue nach Nachholen: {world.comments(issue)}"


# --------------------------------------------------------------------------
# AC-7
# --------------------------------------------------------------------------

def test_ohne_issue_nummer_keine_registrierung_kein_block(world):
    """AC-7: ohne Issue-Nummer kein gh-Aufruf, eine Notiz, kein Block."""
    proj = world.project("proj-ohne", label="iMac")
    res = world.run(proj, "start", "doku-pflege")
    out = _out(res)
    _ok(res, "start ohne Issue-Nummer")
    assert _wf_file(proj, "doku-pflege").exists()
    assert world.calls() == [], f"kein gh-Aufruf erwartet: {world.calls()}"
    notes = [ln for ln in out.splitlines() if re.search(r"(?i)regist", ln)]
    assert len(notes) == 1, f"genau eine Notiz zur ausbleibenden Registrierung erwartet:\n{out}"

    # Gegenprobe im selben Projekt: mit Nummer wird registriert.
    _start_registered(world, proj, ALPHA)


# --------------------------------------------------------------------------
# AC-8
# --------------------------------------------------------------------------

def test_kommentar_id_im_state_ueberlebt_switch(world):
    """AC-8: Kommentar-ID bleibt ueber `switch` im State, kein zweiter Kommentar."""
    proj = world.project("proj-switch", label="iMac")
    claim = _start_registered(world, proj, ALPHA)
    cid = _claim_id(_claim_state(proj, ALPHA))
    assert cid == str(claim["id"])

    _start_registered(world, proj, "feat-462-gamma", issue="462")
    res = world.run(proj, "switch", ALPHA)
    _ok(res, "switch zurueck")
    res = world.run(proj, "switch", ALPHA)  # erneuter Einstieg wie nach /clear
    _ok(res, "switch nach /clear")

    assert _claim_id(_claim_state(proj, ALPHA)) == cid, "Kommentar-ID ging bei switch verloren"
    assert len(world.creates("461")) == 1, f"zweiter Kommentar angelegt: {world.creates('461')}"
    assert len(world.claims("461")) == 1


# --------------------------------------------------------------------------
# AC-9
# --------------------------------------------------------------------------

def _make_completable(proj: Path, name: str) -> None:
    """Workflow-State so setzen, dass `complete` durchlaeuft (Muster test_auftrag_551)."""
    spec = proj / "docs" / "specs" / "x.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("## Architektur-Entscheidung (ADR)\n\n- **ADR-Nr.:** keine\n")
    data = _wf_state(proj, name)
    data.update({"workflow_type": "feature-fast", "spec_file": "docs/specs/x.md",
                 "spec_approved": True, "current_phase": "phase8_complete",
                 "context_file": "docs/context/x.md", "affected_files": [],
                 "test_artifacts": [], "adversary_verdict": None})
    _wf_file(proj, name).write_text(json.dumps(data))
    (proj / ".claude" / "workflows" / "_log" / f"20261124100000_{name}.yaml").write_text(
        "outcome: success\n")


def test_freigabe_bei_ship_status_done_skipped_und_abandon_nicht_bei_complete(world):
    """AC-9: `ship-status done|skipped` und `abandon` geben frei, `complete` nicht."""
    for issue, how in (("462", "done"), ("463", "skipped"), ("464", "abandon")):
        name = f"feat-{issue}-{how}"
        proj = world.project(f"proj-{how}", label="iMac")
        claim = _start_registered(world, proj, name, issue=issue)
        if how == "abandon":
            res = world.run(proj, "abandon", "--reason", "Test")
        else:
            res = world.run(proj, "ship-status", how)
        _ok(res, how)

        def released(issue=issue, cid=claim["id"]):
            c = [x for x in world.comments(issue) if x["id"] == cid]
            return c and _status(c[0]["body"]) == "freigegeben"

        assert _wait(released, timeout=6), \
            f"[{how}] Eintrag nicht freigegeben: {world.comments(issue)}"

    name = "feat-465-complete"
    proj = world.project("proj-complete", label="iMac")
    claim = _start_registered(world, proj, name, issue="465")
    _make_completable(proj, name)
    res = world.run(proj, "complete")
    _ok(res, "complete")
    time.sleep(1.0)
    c = [x for x in world.comments("465") if x["id"] == claim["id"]][0]
    assert _status(c["body"]) == "aktiv", f"complete darf nicht freigeben: {c['body']!r}"


# --------------------------------------------------------------------------
# AC-10
# --------------------------------------------------------------------------

def test_phasenwechsel_aktualisiert_per_patch_abgekoppelt(world):
    """AC-10: Phasenwechsel bearbeitet denselben Kommentar (PATCH) und wartet
    nicht auf GitHub."""
    proj = world.project("proj-phase", label="iMac", timeout=8)
    claim = _start_registered(world, proj, ALPHA)
    data = _wf_state(proj, ALPHA)
    data["context_file"] = "docs/context/x.md"
    _wf_file(proj, ALPHA).write_text(json.dumps(data))
    world.update(mode="sleep", only_kinds=["edit_comment"], sleep_seconds=4)

    t0 = time.monotonic()
    res = world.run(proj, "phase", "phase2_analyse")
    elapsed = time.monotonic() - t0
    _ok(res, "Phasenwechsel")
    assert elapsed < 2.5, f"Phasenwechsel wartet auf GitHub ({elapsed:.1f}s)"

    def patched():
        c = [x for x in world.comments() if x["id"] == claim["id"]]
        return c and re.search(r"(?i)phase2_analyse|analyse", c[0]["body"])

    assert _wait(patched, timeout=10), f"Phase im Kommentar nicht aktualisiert: {world.comments()}"
    edits = [e for e in world.edits() if str(e.get("comment_id")) == str(claim["id"])]
    assert edits and all(e.get("method") in ("PATCH",) for e in edits), \
        f"Aktualisierung nicht per PATCH am selben Kommentar: {world.edits()}"
    assert len(world.creates("461")) == 1, "Phasenwechsel darf keinen neuen Kommentar anlegen"


# --------------------------------------------------------------------------
# AC-11
# --------------------------------------------------------------------------

def test_claim_status_zeigt_fremden_eintrag_mit_alter_und_offenen_prs(world):
    """AC-11: `claim status` zeigt Besitzer, Ort, Alter und offene PRs, aendert nichts."""
    proj_a = world.project("rechner-a", label="iMac")
    _start_registered(world, proj_a, ALPHA)

    # Eintrag um drei Stunden zurueckdatieren (createdAt und Zeitangaben im Text).
    back = datetime.now(timezone.utc) - timedelta(hours=3)
    data = world.load()
    for c in data["comments"]["461"]:
        old = datetime.strptime(c["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        c["created_at"] = c["updated_at"] = back.strftime("%Y-%m-%dT%H:%M:%SZ")
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S+00:00", "%Y-%m-%d %H:%M UTC",
                    "%Y-%m-%dT%H:%MZ", "%Y-%m-%d %H:%M:%S UTC", "%H:%M UTC", "%H:%M"):
            c["body"] = c["body"].replace(old.strftime(fmt), back.strftime(fmt))
    data["pulls"] = [{"number": 777, "title": "Registrierung je Issue (#461)",
                      "body": "Closes #461", "headRefName": "worktree-issue-461"}]
    world.save(data)

    proj_b = world.project("rechner-b", label="Server")
    (proj_b / ".claude" / "workflows" / f"{BETA}.json").write_text(json.dumps({
        "name": BETA, "workflow_type": "feature", "current_phase": "phase1_context",
        "phase_transitions": [], "phase_log": [], "issue_claim": {"status": "pending"}}))
    (proj_b / ".claude" / "active_workflow").write_text(BETA)
    before_comments = world.comments()
    before_calls = len(world.calls())

    res = world.run(proj_b, "claim", "status")
    out = _out(res)
    _ok(res, "claim status")
    assert ALPHA in out, f"Besitzer-Sitzung fehlt:\n{out}"
    assert "iMac" in out, f"Ort fehlt:\n{out}"
    assert re.search(r"(?i)\b3\s*(h\b|std|stunde)|\b18\d\s*min", out), f"Alter (3 Std.) fehlt:\n{out}"
    assert "777" in out, f"offener Pull Request fehlt:\n{out}"

    new_calls = world.calls()[before_calls:]
    assert not [c for c in new_calls if c["kind"] in ("create_comment", "edit_comment",
                                                       "delete_comment")], \
        f"claim status darf nichts aendern: {new_calls}"
    assert world.comments() == before_comments


# --------------------------------------------------------------------------
# AC-12
# --------------------------------------------------------------------------

def test_kill_switch_config_und_umgebungsvariable(world):
    """AC-12: `issue_claim.enabled: false` oder `OPENSPEC_ISSUE_CLAIM=0` -> kein gh."""
    # Gegenprobe: ohne Schalter wird registriert (sonst bewiese das Folgende nichts).
    proj_on = world.project("proj-an", label="iMac")
    _start_registered(world, proj_on, ALPHA)

    proj_cfg = world.project("proj-cfg-aus", label="iMac", enabled=False)
    n = len(world.calls())
    res = world.run(proj_cfg, "start", "feat-462-cfg")
    _ok(res, "start mit enabled: false")
    assert _wf_file(proj_cfg, "feat-462-cfg").exists()
    time.sleep(0.5)
    assert world.calls()[n:] == [], f"gh trotz enabled: false: {world.calls()[n:]}"
    assert "issue_claim" not in _wf_state(proj_cfg, "feat-462-cfg") or \
        _wf_state(proj_cfg, "feat-462-cfg")["issue_claim"].get("status") != "pending"

    proj_env = world.project("proj-env-aus", label="iMac", enabled=True)
    n = len(world.calls())
    res = world.run(proj_env, "start", "feat-463-env", OPENSPEC_ISSUE_CLAIM="0")
    _ok(res, "start mit OPENSPEC_ISSUE_CLAIM=0")
    assert _wf_file(proj_env, "feat-463-env").exists()
    time.sleep(0.5)
    assert world.calls()[n:] == [], f"gh trotz OPENSPEC_ISSUE_CLAIM=0: {world.calls()[n:]}"


# --------------------------------------------------------------------------
# AC-13
# --------------------------------------------------------------------------

def test_ort_und_erreichbarkeit_cloud_label_und_fallback(world):
    """AC-13: Cloud vor Label vor Systembezeichnung; Erreichbarkeit herdr, Cloud-Text
    oder Terminal. Geprueft am Kommentar, den `start` anlegt."""
    fallback = {"Darwin": "Mac", "Linux": "Linux-Rechner"}.get(platform.system(), "Rechner")
    cases = [
        # (Issue, Label, Umgebung, erwarteter Ort, erwartete Erreichbarkeit, verboten)
        ("462", "iMac", {"CLAUDE_CODE_REMOTE": "true"}, "Cloud", CLOUD_REACH, ["iMac"]),
        ("463", "Server", {}, "Server", "Terminal", ["herdr", "Cloud"]),
        ("464", "Server", {"HERDR_ENV": "1"}, "Server", "herdr", ["Terminal"]),
        ("465", None, {}, fallback, "Terminal", ["iMac", "Server", "Cloud"]),
    ]
    for issue, label, env, place, reach, forbidden in cases:
        name = f"feat-{issue}-ort"
        proj = world.project(f"proj-ort-{issue}", label=label)
        res = world.run(proj, "start", name, **env)
        _ok(res, f"[{issue}] start")
        claim = world.claim_of(name, issue)
        assert claim is not None, f"[{issue}] kein Eintrag: {world.calls()}"
        body = claim["body"]
        assert place in body, f"[{issue}] Ort {place!r} fehlt: {body!r}"
        assert reach in body, f"[{issue}] Erreichbarkeit {reach!r} fehlt: {body!r}"
        for word in forbidden:
            assert word not in body, f"[{issue}] {word!r} darf nicht im Eintrag stehen: {body!r}"


# --------------------------------------------------------------------------
# AC-14
# --------------------------------------------------------------------------

def test_conftest_setzt_kill_switch_automatisch():
    """AC-14: die conftest-Autouse-Fixture setzt OPENSPEC_ISSUE_CLAIM=0.

    Bewusst ohne `world`-Fixture: hier darf nichts die Variable zuruecksetzen.
    """
    assert os.environ.get("OPENSPEC_ISSUE_CLAIM") == "0", \
        "tests/conftest.py setzt OPENSPEC_ISSUE_CLAIM=0 nicht per autouse"
    assert "OPENSPEC_ISSUE_CLAIM" in CONFTEST.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# AC-15
# --------------------------------------------------------------------------

def test_befehlstexte_nennen_uebernehmen_skills_ohne_drift():
    """AC-15: 00-intake, 10-context, 80-workflow nennen den Abbruch bei fremder
    Registrierung und `--uebernehmen`; `sync_skills.py --check` ohne Drift."""
    for fname in ("00-intake.md", "10-context.md", "80-workflow.md"):
        text = (COMMANDS_DIR / fname).read_text(encoding="utf-8")
        assert "--uebernehmen" in text, f"{fname} nennt --uebernehmen nicht"
        assert re.search(r"(?i)registrier", text), f"{fname} nennt die Registrierung nicht"
    res = subprocess.run([sys.executable, str(SYNC_SKILLS), "--check"], capture_output=True,
                         text=True, cwd=str(REPO_ROOT), timeout=60)
    assert res.returncode == 0, f"Skills-Drift:\n{res.stdout}\n{res.stderr}"
