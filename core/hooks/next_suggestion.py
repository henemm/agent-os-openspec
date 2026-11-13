#!/usr/bin/env python3
"""Naechster Vorschlag nach dem Abschluss (Issue #589, Teil A). KEIN Hook.

Utility fuer `workflow.py endstate`, Plan und Seitenleiste: Meldet ein Workflow
"fertig", nennt die Schlusszeile die passende naechste Aufgabe
(`/00-intake #M` mit kurzer Begruendung).

- `choose(raw, done_number, claimed, spur=None, now=None)`: reine Auswahl ohne
  Netz-, Datei- oder Config-Zugriff. Rangfolge Epic-Geschwister, gleicher
  Meilenstein, (Spur: #591, hier ohne Wirkung), verwandte Aufgabe, wichtigste
  offene Aufgabe; Ergebnis `{"n", "source", "reason", "title"}` oder None.
- `fetch(root, done_number, timeout_s)`: Rohdaten ausschliesslich per `gh api`
  (REST, nie GraphQL), fail-open: jeder Fehler ergibt None, nie eine Ausnahme.
- `write_cache`/`read_cache`: Rohdaten in `<root>/.claude/next_suggestion.json`
  (atomar, Schluessel erledigte Nummer, TTL); `choose` laeuft bei jedem Lesen
  frisch, damit das Session-Register nie veraltet.
- `settings(config)`: Kill-Switch `next_suggestion.enabled` (nur das Literal
  `false` schaltet ab), `timeout_s`, `cache_ttl_s`.

Netz nur in `workflow.py endstate`; `end_state`, Plan und Seitenleiste lesen
nur den Cache.
"""

import json
import re
import time
from pathlib import Path

CACHE_FILENAME = "next_suggestion.json"
DEFAULT_TIMEOUT_S = 8
DEFAULT_CACHE_TTL_S = 300
TITLE_MAX = 60
SOURCE_TEXT = {
    "epic": "gleiche Sammelaufgabe",
    "milestone": "gleicher Meilenstein",
    "related": "knüpft an eine Aufgabe an",
    "priority": "wichtigste offene Aufgabe",
}
PRIORITY_RANK = {"priority:critical": 0, "priority:high": 1, "priority:medium": 2,
                 "priority:low": 3}
EXCLUDED_LABELS = {"epic", "status:deferred", "spec-proposal"}
_HASH_NUM_RE = re.compile(r"#(\d+)(?!\d)")


# --- Settings ----------------------------------------------------------------

def _positive(value, default):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return default
    return value


def settings(config=None) -> dict:
    """`{"enabled", "timeout_s", "cache_ttl_s"}` aus `next_suggestion` der Config.

    Nur das Literal `false` schaltet ab (Muster `auftrag_settings`); fehlender
    Abschnitt, andere Werte und kaputte Config bedeuten "an". Wirft nie.
    """
    out = {"enabled": True, "timeout_s": DEFAULT_TIMEOUT_S,
           "cache_ttl_s": DEFAULT_CACHE_TTL_S}
    try:
        if config is None:
            from config_loader import load_config
            config = load_config()
        section = config.get("next_suggestion") if isinstance(config, dict) else None
        if isinstance(section, dict):
            if section.get("enabled") is False:
                out["enabled"] = False
            out["timeout_s"] = _positive(section.get("timeout_s"), DEFAULT_TIMEOUT_S)
            out["cache_ttl_s"] = _positive(section.get("cache_ttl_s"), DEFAULT_CACHE_TTL_S)
    except Exception:
        pass
    return out


# --- Reine Auswahl -------------------------------------------------------------

def _num(value) -> "int | None":
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if text.isdigit() and int(text) > 0:
            return int(text)
    return None


def _claimed_set(claimed) -> set:
    """Nummern aus int/str; ein str darf eine Komma-Liste sein ("711,712")."""
    out: set = set()
    if claimed is None:
        return out
    if isinstance(claimed, (str, int)):
        claimed = [claimed]
    try:
        items = list(claimed)
    except TypeError:
        return out
    for item in items:
        parts = item.split(",") if isinstance(item, str) else [item]
        for part in parts:
            n = _num(part)
            if n is not None:
                out.add(n)
    return out


def _labels(issue: dict) -> set:
    names = set()
    for label in issue.get("labels") or []:
        if isinstance(label, dict) and isinstance(label.get("name"), str):
            names.add(label["name"])
        elif isinstance(label, str):
            names.add(label)
    return names


def _open_pr_numbers(pulls) -> set:
    """Issue-Nummern mit offenem PR (Heuristik: `#N` in Titel/Body, Nummer im Branch)."""
    out: set = set()
    for pr in pulls if isinstance(pulls, list) else []:
        if not isinstance(pr, dict) or pr.get("state", "open") != "open":
            continue
        text = f"{pr.get('title') or ''} {pr.get('body') or ''}"
        out.update(int(m) for m in _HASH_NUM_RE.findall(text))
        head = pr.get("head")
        ref = head.get("ref") if isinstance(head, dict) else None
        if isinstance(ref, str):
            try:
                from hook_utils import issue_number_from_name
                n = _num(issue_number_from_name(ref.rsplit("/", 1)[-1]) or "")
            except Exception:
                n = None
            if n is not None:
                out.add(n)
    return out


def _excluded(issue, done_number: int, claimed: set, pr_numbers: set) -> bool:
    if not isinstance(issue, dict):
        return True
    n = _num(issue.get("number"))
    if n is None or n == done_number or n in claimed or n in pr_numbers:
        return True
    if issue.get("state", "open") != "open" or "pull_request" in issue:
        return True
    if _labels(issue) & EXCLUDED_LABELS:
        return True
    summary = issue.get("sub_issues_summary")
    if isinstance(summary, dict):
        total = _num(summary.get("total")) or 0
        done = summary.get("completed")
        done = done if isinstance(done, int) and not isinstance(done, bool) else 0
        if total - done > 0:
            return True  # Eltern mit offenen Sub-Issues: nur Blaetter vorschlagen
    return False


def _milestone_due(issue: dict, milestones) -> "str | None":
    ms = issue.get("milestone")
    if not isinstance(ms, dict):
        return None
    due = ms.get("due_on")
    if not due and isinstance(milestones, list):
        for other in milestones:
            if isinstance(other, dict) and other.get("number") == ms.get("number"):
                due = other.get("due_on")
                break
    return due if isinstance(due, str) and due else None


def _sort_key(issue: dict, milestones):
    has_ms = isinstance(issue.get("milestone"), dict)
    due = _milestone_due(issue, milestones)
    prio = min((PRIORITY_RANK.get(name, 4) for name in _labels(issue)), default=4)
    return (0 if has_ms else 1, (0, due) if due else (1, ""), prio, _num(issue["number"]))


def _related_re(done_number: int):
    return re.compile(
        rf"(?<!\w)(?:Folge zu|aus|Follow-up (?:to|of))\s+#{done_number}(?!\d)",
        re.IGNORECASE)


def _git_free(text: str) -> str:
    """Git-Woerter des Klartext-Gates (#582) aus dem Titel nehmen; fail-open."""
    try:
        from klartext_gate import MUSTER
    except Exception:
        return text
    return " ".join(MUSTER.sub(" ", text).split())


def short_title(title, limit: int = TITLE_MAX) -> str:
    """Eine Zeile, ohne Steuerzeichen und Git-Woerter, hoechstens `limit` Zeichen."""
    if not isinstance(title, str):
        return ""
    text = "".join(ch if ch.isprintable() else " " for ch in title)
    text = _git_free(" ".join(text.split()))
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" .,;:-") + "…"


def choose(raw, done_number, claimed, spur=None, now=None) -> "dict | None":
    """Naechste Aufgabe aus den Rohdaten oder None. Rein, wirft nie.

    `spur` (#591) und `now` sind in Teil A ohne Wirkung.
    """
    try:
        done_n = _num(done_number)
        if not isinstance(raw, dict) or done_n is None:
            return None
        claimed_set = _claimed_set(claimed)
        prs = _open_pr_numbers(raw.get("pulls"))
        milestones = raw.get("milestones")
        issues = raw.get("issues") if isinstance(raw.get("issues"), list) else []
        done = raw.get("done") if isinstance(raw.get("done"), dict) else {}

        stages = []
        if isinstance(raw.get("parent"), dict):
            subs = raw.get("sub_issues")
            stages.append(("epic", subs if isinstance(subs, list) else []))
        ms = done.get("milestone")
        ms_n = ms.get("number") if isinstance(ms, dict) else None
        if ms_n is not None:
            stages.append(("milestone", [i for i in issues if isinstance(i, dict)
                                         and isinstance(i.get("milestone"), dict)
                                         and i["milestone"].get("number") == ms_n]))
        # Stufe 3 Spur: kommt mit #591
        related = _related_re(done_n)
        stages.append(("related", [i for i in issues if isinstance(i, dict)
                                   and isinstance(i.get("body"), str)
                                   and related.search(i["body"])]))
        stages.append(("priority", issues))

        for source, candidates in stages:
            pool = [i for i in candidates if not _excluded(i, done_n, claimed_set, prs)]
            if not pool:
                continue
            best = min(pool, key=lambda i: _sort_key(i, milestones))
            n = _num(best["number"])
            title = short_title(best.get("title")) or f"Aufgabe #{n}"
            return {"n": n, "source": source, "title": title,
                    "reason": f"{SOURCE_TEXT[source]}: {title}"}
        return None
    except Exception:
        return None


# --- Abruf per gh api (REST) ----------------------------------------------------

class _NotFound(Exception):
    pass


def _gh_json(gh: str, path: str, root, deadline: float):
    import subprocess
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Zeitbudget aufgebraucht")
    res = subprocess.run([gh, "api", f"repos/{{owner}}/{{repo}}/{path}"],
                         capture_output=True, text=True, timeout=remaining,
                         cwd=str(root), stdin=subprocess.DEVNULL)
    if res.returncode != 0:
        if "HTTP 404" in (res.stderr or ""):
            raise _NotFound(path)
        raise RuntimeError(f"gh api Exit {res.returncode}")
    return json.loads(res.stdout)


def fetch(root, done_number, timeout_s=DEFAULT_TIMEOUT_S) -> "dict | None":
    """Rohdaten fuer `choose` per `gh api` (REST) oder None. Wirft nie.

    `timeout_s` ist das Zeitbudget fuer alle Aufrufe zusammen. `issues/N/parent`
    mit HTTP 404 heisst "kein Eltern-Issue"; der PR-Abruf ist optional ([] bei
    Fehler). Die Issue-Liste ist auf eine 100er-Seite gedeckelt.
    """
    try:
        import shutil
        done_n = _num(done_number)
        gh = shutil.which("gh")
        if done_n is None or not gh:
            return None
        deadline = time.monotonic() + float(_positive(timeout_s, DEFAULT_TIMEOUT_S))
        done = _gh_json(gh, f"issues/{done_n}", root, deadline)
        try:
            parent = _gh_json(gh, f"issues/{done_n}/parent", root, deadline)
        except _NotFound:
            parent = None
        subs = []
        if isinstance(parent, dict) and _num(parent.get("number")):
            subs = _gh_json(gh, f"issues/{_num(parent['number'])}/sub_issues?per_page=100",
                            root, deadline)
        issues = _gh_json(gh, "issues?state=open&per_page=100", root, deadline)
        milestones = _gh_json(gh, "milestones?state=open", root, deadline)
        try:
            pulls = _gh_json(gh, "pulls?state=open&per_page=100", root, deadline)
        except Exception:
            pulls = []
        if not isinstance(done, dict) or not isinstance(issues, list) \
                or not isinstance(milestones, list) or not isinstance(subs, list):
            return None
        return {"done": done, "parent": parent if isinstance(parent, dict) else None,
                "sub_issues": subs, "issues": issues, "milestones": milestones,
                "pulls": pulls if isinstance(pulls, list) else []}
    except Exception:
        return None


# --- Cache -------------------------------------------------------------------------

def cache_path(root) -> Path:
    return Path(root) / ".claude" / CACHE_FILENAME


def write_cache(root, done_number, raw, now=None) -> bool:
    """Rohdaten atomar nach `<root>/.claude/next_suggestion.json`. Wirft nie."""
    try:
        from hook_utils import atomic_write_text
        stamp = float(now) if now is not None else time.time()
        payload = {"done": _num(done_number), "ts": stamp, "raw": raw}
        atomic_write_text(cache_path(root), json.dumps(payload, ensure_ascii=False),
                          root=Path(root))
        return True
    except Exception:
        return False


def read_cache(root, done_number, ttl_s=DEFAULT_CACHE_TTL_S, now=None) -> "dict | None":
    """Rohdaten aus dem Cache, wenn gueltig (gleiche Nummer, innerhalb TTL). Wirft nie."""
    try:
        from hook_utils import read_state_text
        data = json.loads(read_state_text(cache_path(root), Path(root)))
        if not isinstance(data, dict) or data.get("done") != _num(done_number):
            return None
        stamp = data.get("ts")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
            return None
        age = (float(now) if now is not None else time.time()) - stamp
        if age < 0 or age > _positive(ttl_s, DEFAULT_CACHE_TTL_S):
            return None
        raw = data.get("raw")
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None
