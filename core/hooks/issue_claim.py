#!/usr/bin/env python3
"""Registrierung je Issue ueber einen GitHub-Kommentar (Issue #461).

Kein Hook (nicht in hooks.json) — ein Utility, das `workflow.py` an seinen
Einhaengepunkten aufruft (`start`, `switch`, `abandon`, `ship-status`,
Phasenwechsel, `claim`). Eintrag = EIN Kommentar je Arbeit am Issue mit dem
versteckten Marker `<!-- openspec-claim v1 id=<zufall> -->` und einem
maschinenlesbaren Block (Status, Sitzung, Ort, Erreichbarkeit, Beginn, Phase).
Aktualisiert wird per PATCH desselben Kommentars, nie per neuem Kommentar.

Doppelstart: eigenen Kommentar schreiben, Kommentare neu lesen; gueltig sind nur
Marker-Kommentare mit `authorAssociation == OWNER`, Status `aktiv` und offenem
Issue; der frueheste (`created_at`, dann Kommentar-ID) gewinnt.

Fail-open: `register` wirft nie. Ohne `gh`, bei Fehler oder Zeitlimit ergibt
sich Status `pending`; Gruende landen in `.claude/issue_claim.log`.
Abschaltung: `issue_claim.enabled: false` oder `OPENSPEC_ISSUE_CLAIM=0`.

Der Kommentartext enthaelt kein `@`, keine Pfade, keine Links und keine
Rechner-Adressen (Konsumenten-Repos koennen oeffentlich sein).
"""

import json
import os
import platform
import re
import secrets
import shutil
import subprocess
from datetime import datetime, timezone

MARKER = "openspec-claim v1"
ACTIVE = "aktiv"
RELEASED = "freigegeben"
WITHDRAWN = "zurückgezogen"
TAKEN = "übernommen"
PENDING = "pending"
CLOUD_REACH = "Sitzungsliste des Claude-Kontos, Antwort am Issue"
DEFAULT_TIMEOUT = 8.0
LOG_NAME = "issue_claim.log"

_MARKER_RE = re.compile(r"<!--\s*openspec-claim v1 id=([A-Za-z0-9_-]+)\s*-->")
_FIELDS = (("status", "Status"), ("session", "Sitzung"), ("place", "Ort"),
           ("reach", "Erreichbar"), ("began", "Beginn"), ("phase", "Phase"))
_SENTENCES = {
    ACTIVE: "Eine Claude-Sitzung arbeitet gerade an diesem Issue. "
            "Bitte keine zweite Sitzung darauf starten.",
    RELEASED: "Die Arbeit dieser Sitzung ist beendet, das Issue ist wieder frei.",
    WITHDRAWN: "Diese Sitzung hat ihren Eintrag zurückgenommen, weil schon eine "
               "andere Sitzung an dem Issue arbeitet.",
    TAKEN: "Eine andere Sitzung hat diese Arbeit ausdrücklich übernommen.",
}
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


class ClaimError(Exception):
    """`gh` fehlt, scheitert, ueberschreitet das Zeitlimit oder liefert Unlesbares."""


def _root():
    from hook_utils import find_project_root
    return find_project_root()


def _log(message: str) -> None:
    """Fehler in `.claude/issue_claim.log` vermerken. Wirft nie."""
    try:
        path = _root() / ".claude" / LOG_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().isoformat(timespec="seconds")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {message}\n")
    except Exception:
        pass


def _env_disabled() -> bool:
    return os.environ.get("OPENSPEC_ISSUE_CLAIM", "").strip().lower() in ("0", "false", "off")


def settings() -> dict:
    """`enabled`, `timeout`, `label` aus `issue_claim:` (mit lokalen Overrides). Wirft nie."""
    out = {"enabled": True, "timeout": DEFAULT_TIMEOUT, "label": None}
    if _env_disabled():  # vor jedem Config-Zugriff: Kill-Switch ohne Seiteneffekt
        out["enabled"] = False
        return out
    try:
        import config_loader
        section = config_loader.load_config().get("issue_claim")
        if isinstance(section, dict):
            if section.get("enabled") is False:
                out["enabled"] = False
            timeout = section.get("timeout_seconds")
            if isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and timeout > 0:
                out["timeout"] = float(timeout)
            label = section.get("location_label")
            if isinstance(label, str) and label.strip():
                out["label"] = label
    except Exception:
        pass
    return out


def _clean(value, limit: int = 80) -> str:
    """Nur unverfaengliche Zeichen: kein `@`, kein `/`, keine Spitzklammern, eine Zeile.
    Punkte fallen weg, damit nie ein Domain-Muster entsteht, das GitHub verlinkt."""
    text = re.sub(r"[^\w ,:()+\-–]", " ", str(value or ""))
    return " ".join(text.split())[:limit].strip()


def detect_location(label=None) -> "tuple[str, str]":
    """(Ort, Erreichbarkeit) der laufenden Sitzung."""
    cloud = os.environ.get("CLAUDE_CODE_REMOTE", "").strip().lower() == "true"
    if cloud:
        place = "Cloud"
    else:
        fallback = {"Darwin": "Mac", "Linux": "Linux-Rechner"}.get(platform.system(), "Rechner")
        place = _clean(label, 40) or fallback
    if os.environ.get("HERDR_ENV") == "1":
        reach = "herdr"
    elif cloud:
        reach = CLOUD_REACH
    else:
        reach = "Terminal"
    return place, reach


def utc_text(ts: "datetime | None" = None) -> str:
    ts = ts or datetime.now(timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _parse_ts(value) -> "datetime | None":
    try:
        return datetime.strptime(str(value), _TS_FMT).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def build_comment(fields: dict) -> str:
    """Kommentartext aus `fields` (token, status, session, place, reach, began, phase)."""
    token = _clean(fields.get("token"), 32).replace(" ", "") or secrets.token_hex(4)
    status = fields.get("status") if fields.get("status") in _SENTENCES else ACTIVE
    lines = [f"<!-- {MARKER} id={token} -->",
             f"**Registrierung einer Claude-Sitzung:** {_SENTENCES[status]}", ""]
    for key, label in _FIELDS:
        value = status if key == "status" else _clean(fields.get(key))
        lines.append(f"- {label}: {value or '–'}")
    return "\n".join(lines) + "\n"


def parse_comment(body) -> "dict | None":
    """Felder eines Eintrags oder None (kein Marker)."""
    if not isinstance(body, str):
        return None
    m = _MARKER_RE.search(body)
    if not m:
        return None
    out = {"token": m.group(1)}
    for key, label in _FIELDS:
        hit = re.search(rf"(?m)^- {label}:\s*(.*?)\s*$", body)
        if hit:
            out[key] = hit.group(1)
    return out


def _json_stream(text: str):
    """JSON aus `gh api` lesen; `--paginate` haengt Arrays aneinander."""
    decoder = json.JSONDecoder()
    items, pos, text = [], 0, text.strip()
    while pos < len(text):
        obj, end = decoder.raw_decode(text, pos)
        items.append(obj)
        pos = end
        while pos < len(text) and text[pos].isspace():
            pos += 1
    if len(items) == 1:
        return items[0]
    if items and all(isinstance(i, list) for i in items):
        return [x for i in items for x in i]
    raise ValueError("mehrdeutige Antwort")


def _gh(args: list, timeout: float):
    """`gh <args>` mit Zeitlimit; JSON-Antwort zurueck. Wirft ClaimError."""
    gh = shutil.which("gh")
    if not gh:
        raise ClaimError("gh nicht gefunden")
    try:
        res = subprocess.run([gh, *args], capture_output=True, text=True, timeout=timeout,
                             cwd=str(_root()), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise ClaimError(f"gh Zeitlimit {timeout:g}s")
    except OSError as exc:
        raise ClaimError(f"gh nicht startbar ({type(exc).__name__})")
    if res.returncode != 0:
        raise ClaimError(f"gh Exit {res.returncode}: {(res.stderr or '').strip()[:200]}")
    try:
        return _json_stream(res.stdout or "")
    except ValueError:
        raise ClaimError("gh lieferte kein lesbares JSON")


def _issue_ep(issue) -> str:
    return f"repos/{{owner}}/{{repo}}/issues/{issue}"


def _comment_ep(cid) -> str:
    return f"repos/{{owner}}/{{repo}}/issues/comments/{cid}"


def _post(issue, body: str, timeout: float) -> dict:
    obj = _gh(["api", "-X", "POST", f"{_issue_ep(issue)}/comments", "-f", f"body={body}"], timeout)
    if not isinstance(obj, dict) or not obj.get("id"):
        raise ClaimError("Antwort ohne Kommentar-ID")
    return obj


def _patch(cid, body: str, timeout: float) -> dict:
    obj = _gh(["api", "-X", "PATCH", _comment_ep(cid), "-f", f"body={body}"], timeout)
    return obj if isinstance(obj, dict) else {}


def read_claims(issue, timeout: float = DEFAULT_TIMEOUT) -> "tuple[bool, list]":
    """(Issue offen?, Eintraege mit Marker). Wirft ClaimError."""
    comments = _gh(["api", f"{_issue_ep(issue)}/comments?per_page=100", "--paginate"], timeout)
    info = _gh(["api", _issue_ep(issue)], timeout)
    is_open = str((info or {}).get("state", "open")).lower() == "open"
    entries = []
    for c in comments if isinstance(comments, list) else []:
        fields = parse_comment(c.get("body")) if isinstance(c, dict) else None
        if fields is None:
            continue
        entries.append({"id": c.get("id"), "created_at": c.get("created_at") or c.get("createdAt"),
                        "association": c.get("author_association") or c.get("authorAssociation"),
                        "fields": fields})
    return is_open, entries


def valid_entries(entries: list, is_open: bool) -> list:
    """Nur OWNER-Eintraege mit Status aktiv an einem offenen Issue zaehlen."""
    if not is_open:
        return []
    return [e for e in entries if str(e.get("association") or "").upper() == "OWNER"
            and (e.get("fields") or {}).get("status") == ACTIVE]


def pick_winner(entries: list) -> "dict | None":
    """Fruehester Eintrag (`created_at`, danach Kommentar-ID)."""
    def key(e):
        try:
            num = int(e.get("id"))
        except (TypeError, ValueError):
            num = 0
        return (str(e.get("created_at") or "9999"), num)
    return min(entries, key=key) if entries else None


def _claim_state(issue, fields: dict, cid, created_at, status: str) -> dict:
    return {"issue": str(issue), "comment_id": cid, "status": status,
            "token": fields.get("token"), "place": fields.get("place"),
            "reach": fields.get("reach"), "began": fields.get("began"),
            "created_at": created_at,
            "updated_at": datetime.now(timezone.utc).strftime(_TS_FMT)}


def _ensure_own(issue, fields: dict, existing: dict, timeout: float) -> dict:
    """Eigenen Kommentar anlegen oder (vorhandene ID) auf aktiv bearbeiten."""
    body = build_comment(fields)
    cid = existing.get("comment_id")
    if cid:
        try:
            obj = _patch(cid, body, timeout)
            return {"id": cid, "created_at": obj.get("created_at") or existing.get("created_at")}
        except ClaimError as exc:
            if "404" not in str(exc):
                raise
    obj = _post(issue, body, timeout)
    return {"id": obj.get("id"), "created_at": obj.get("created_at")}


def _fields_for(name: str, phase: str, existing: dict, cfg: dict) -> dict:
    place, reach = detect_location(cfg.get("label"))
    return {"token": existing.get("token") or secrets.token_hex(4), "status": ACTIVE,
            "session": name, "place": place, "reach": reach,
            "began": existing.get("began") or utc_text(), "phase": phase}


def _decide(issue, fields, own, take_over, timeout) -> "tuple[str, dict | None]":
    """Neu lesen, fremde Eintraege ggf. uebernehmen, Gewinner bestimmen."""
    is_open, entries = read_claims(issue, timeout)
    for e in entries:
        if str(e.get("id")) == str(own["id"]) and e.get("created_at"):
            own["created_at"] = e["created_at"]
    foreign = [e for e in valid_entries(entries, is_open) if str(e.get("id")) != str(own["id"])]
    if take_over:
        for e in foreign:
            _patch(e["id"], build_comment({**e["fields"], "status": TAKEN}), timeout)
        foreign = []
    winner = pick_winner(foreign + [own])
    if winner is own:
        return "ok", None
    fields["status"] = WITHDRAWN
    try:  # Abbruch gilt auch, wenn das Zurueckziehen scheitert (F002)
        _patch(own["id"], build_comment(fields), timeout)
    except ClaimError as exc:
        _log(f"withdraw #{issue} {fields.get('session')}: {exc}")
    return "conflict", winner


def register(issue, name: str, phase: str, take_over: bool = False,
             existing: "dict | None" = None, cfg: "dict | None" = None) -> dict:
    """Eintrag anlegen bzw. nachholen. Ergebnis: `result` ok|conflict|pending,
    `claim` (State fuer `issue_claim`), bei Konflikt `winner`. Wirft nie."""
    existing = dict(existing or {})
    own = None
    fields = {}
    try:
        cfg = cfg or settings()
        timeout = cfg["timeout"]
        fields = _fields_for(name, phase, existing, cfg)
        own = _ensure_own(issue, fields, existing, timeout)
        result, winner = _decide(issue, fields, own, take_over, timeout)
        status = ACTIVE if result == "ok" else WITHDRAWN
        return {"result": result, "winner": winner,
                "claim": _claim_state(issue, fields, own["id"], own.get("created_at"), status)}
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ClaimError) else f"Fehler {type(exc).__name__}"
        _log(f"register #{issue} {name}: {reason}")
        cid = own["id"] if own else existing.get("comment_id")
        created = own.get("created_at") if own else existing.get("created_at")
        claim = _claim_state(issue, fields or existing, cid, created, PENDING)
        return {"result": "pending", "claim": claim, "error": reason}


def refresh(claim: dict, name: str, phase: str, status: str = ACTIVE,
            cfg: "dict | None" = None) -> dict:
    """Eigenen Kommentar per PATCH auf Stand bringen. Wirft ClaimError."""
    cfg = cfg or settings()
    if not claim.get("comment_id"):
        raise ClaimError("keine Kommentar-ID")
    fields = {"token": claim.get("token"), "status": status, "session": name,
              "place": claim.get("place"), "reach": claim.get("reach"),
              "began": claim.get("began"), "phase": phase}
    _patch(claim["comment_id"], build_comment(fields), cfg["timeout"])
    out = dict(claim)
    out["status"] = status
    out["updated_at"] = datetime.now(timezone.utc).strftime(_TS_FMT)
    return out


def remote_status(claim: dict, cfg: "dict | None" = None) -> "str | None":
    """Status des eigenen Kommentars am Issue (F003). Wirft ClaimError."""
    cfg = cfg or settings()
    obj = _gh(["api", _comment_ep(claim.get("comment_id"))], cfg["timeout"])
    fields = parse_comment(obj.get("body")) if isinstance(obj, dict) else None
    return (fields or {}).get("status")


def release(claim: dict, name: str, phase: str, cfg: "dict | None" = None) -> "tuple[dict, str | None]":
    """Eintrag freigeben. (neuer Claim-State, Fehlergrund oder None). Wirft nie."""
    try:
        return refresh(claim, name, phase, RELEASED, cfg), None
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ClaimError) else f"Fehler {type(exc).__name__}"
        _log(f"release #{claim.get('issue')} {name}: {reason}")
        return claim, reason


def _when(entry: dict) -> str:
    began = (entry.get("fields") or {}).get("began")
    if began:
        return began
    ts = _parse_ts(entry.get("created_at"))
    return utc_text(ts) if ts else "unbekannt"


def conflict_text(issue, winner: dict, own_name: str) -> str:
    """Klartext fuer den Abbruch bei fremdem gueltigem Eintrag."""
    f = winner.get("fields") or {}
    return "\n".join([
        f"ABGEBROCHEN: An Issue #{issue} arbeitet bereits eine andere Sitzung.",
        f"  Sitzung:    {f.get('session') or 'unbekannt'}",
        f"  Ort:        {f.get('place') or 'unbekannt'}",
        f"  Seit:       {_when(winner)}",
        f"  Erreichbar: {f.get('reach') or 'unbekannt'}",
        "Bitte dort weiterarbeiten oder die andere Sitzung fragen.",
        "Der eigene Eintrag am Issue ist zurueckgezogen, es wurde kein Workflow angelegt.",
        "Wer die Arbeit bewusst uebernehmen will:",
        f"  workflow.py start {own_name} --uebernehmen",
    ])


def age_text(created_at, now: "datetime | None" = None) -> str:
    ts = _parse_ts(created_at)
    if ts is None:
        return "unbekannt"
    minutes = max(0, int(((now or datetime.now(timezone.utc)) - ts).total_seconds() // 60))
    if minutes < 60:
        return f"{minutes} Min."
    if minutes < 48 * 60:
        return f"{minutes // 60} Std. {minutes % 60} Min."
    return f"{minutes // 1440} Tg."


def open_pulls(issue, timeout: float) -> list:
    """Offene Pull Requests, die das Issue nennen (Titel, Text oder Zweigname)."""
    from hook_utils import issue_number_from_name
    pulls = _gh(["api", "repos/{owner}/{repo}/pulls?state=open&per_page=100", "--paginate"],
                timeout)
    pat = re.compile(rf"#{re.escape(str(issue))}(?!\d)")
    out = []
    for p in pulls if isinstance(pulls, list) else []:
        if not isinstance(p, dict):
            continue
        ref = (p.get("head") or {}).get("ref") or p.get("headRefName") or ""
        text = f"{p.get('title') or ''}\n{p.get('body') or ''}"
        if pat.search(text) or issue_number_from_name(ref) == str(issue):
            out.append(p)
    return out


def _entry_line(entry: dict, own_id) -> str:
    f = entry.get("fields") or {}
    mine = " (eigener Eintrag)" if own_id and str(entry.get("id")) == str(own_id) else ""
    return (f"  - {f.get('session') or 'unbekannt'}: {f.get('status') or '?'}, "
            f"Ort {f.get('place') or '?'}, erreichbar über {f.get('reach') or '?'}, "
            f"seit {_when(entry)}, Alter {age_text(entry.get('created_at'))}{mine}")


def status_lines(issue, claim: "dict | None", cfg: "dict | None" = None) -> list:
    """Uebersicht fuer `workflow.py claim status` (nur lesend). Wirft ClaimError."""
    cfg = cfg or settings()
    is_open, entries = read_claims(issue, cfg["timeout"])
    owner_entries = [e for e in entries if str(e.get("association") or "").upper() == "OWNER"]
    own_id = (claim or {}).get("comment_id")
    lines = [f"Registrierungen an Issue #{issue}:"]
    lines += [_entry_line(e, own_id) for e in owner_entries] or ["  (keine)"]
    if not is_open:
        lines.append("  Das Issue ist geschlossen und gilt damit als frei.")
    lines.append(f"Eigener Stand: {(claim or {}).get('status') or 'nicht registriert'}")
    pulls = open_pulls(issue, cfg["timeout"])
    lines.append("Offene Pull Requests zum Issue:" if pulls else "Offene Pull Requests zum Issue: keine")
    lines += [f"  - #{p.get('number')} {p.get('title') or ''}".rstrip() for p in pulls]
    return lines
