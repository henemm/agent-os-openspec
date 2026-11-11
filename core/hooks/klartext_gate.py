#!/usr/bin/env python3
"""Klartext-Gate (Stop-Hook): prüft die Antwort an den Nutzer auf Git-Fachwörter (#582).

Der Nutzer hat kein Technikprofil (siehe CLAUDE.md des Nutzers). Git ist allein
Claudes Sache; in Abschlussmeldungen gehören Ergebnis und Alltagssprache, keine
Begriffe wie Branch, Commit, PR, Merge, Push, Worktree oder CI. Regeln in
Texten haben das nicht verlässlich verhindert, deshalb prüft dieser Hook die
letzte Antwort mechanisch und erzwingt bei einem Treffer per Exit 2 eine
Neufassung.

Keine Treffer zählen:
- Code-Angaben in Backticks und Codeblöcken, Adressen (http…) und Pfade
  (Wörter mit `/`, `.` oder `-` direkt daneben),
- Wortteile (CIA, PRAXIS, Commitment): verglichen wird nur das ganze Wort.

Frei bleibt der Zug außerdem,
- wenn die letzte echte Nutzernachricht selbst solche Wörter enthält (der
  Nutzer hat danach gefragt),
- bei `stop_hook_active` (höchstens eine Neufassung je Zug, keine Schleife),
- bei `OPENSPEC_KLARTEXT=0` (bzw. off/false/no/disabled).

TRAGENDE ANFORDERUNG IST FAIL-OPEN: der Hook läuft im Plugin-Modus bei jedem
Turn-Ende in jedem Projekt. Jeder unklare Fall und jeder Fehler endet mit
Exit 0; keine Ausnahme darf nach außen dringen.
"""

import json
import os
import re
import sys

from hook_utils import setup_path
setup_path()

from hook_utils import adopt_payload_cwd, block  # noqa: E402

_OFF_VALUES = {"off", "0", "false", "no", "disabled"}

# Lange Wörter ohne Rücksicht auf Groß-/Kleinschreibung; die Kürzel PR und CI
# nur großgeschrieben, sonst träfe es Allerweltsfolgen wie „ci" oder „pr".
_WOERTER = (
    r"(?i:Branch(?:es)?|Zweig(?:e|en)?|Commits?|committ(?:e[tdn]?|est)|Merges?|gemergt|mergen|"
    r"Pull[- ]Requests?|Worktrees?|Push|gepusht|pushen|Rebase|rebasen|"
    r"Cherry-?picks?|Checkout|origin/main|main-Zweig|auf main|Stash)"
    r"|PRs?|CI"
)
# Kein Treffer, wenn direkt davor ein Wortzeichen, `/`, `.` oder `-` steht
# oder direkt danach ein Wortzeichen, `/` oder `-` (Wortteile, Pfade, Namen
# wie `fix-12-push`).
MUSTER = re.compile(rf"(?<![\w/.-])({_WOERTER})(?![\w/-])")

# Vom Harness eingefügte Blöcke in Nutzer-Einträgen des Transkripts. Sie
# stammen nicht vom Nutzer und dürfen die Ausnahme „Nutzer fragt selbst"
# nicht auslösen (Vorbild: phase_listener.NOTIFICATION_MARKERS, #46).
_HARNESS_BLOCK_RE = re.compile(
    r"<(system-reminder|task-notification|local-command-stdout|local-command-stderr|"
    r"local-command-caveat|command-name|command-message|command-args|bash-input|"
    r"bash-stdout|bash-stderr)>.*?</\1>",
    re.S,
)
_HARNESS_MARKERS = ("[SYSTEM NOTIFICATION", "[Subagent hand-back]", '<agent-message from="')

# Nur das Ende des Transkripts lesen: die letzte Nutzernachricht liegt dort.
_TAIL_BYTES = 2 * 1024 * 1024


def ohne_code(text: str) -> str:
    """Codeblöcke, Code in Backticks und Adressen entfernen."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    return re.sub(r"\b(?:https?|file)://\S+", " ", text)


def treffer(text: str) -> "list[str]":
    """Sortierte, eindeutige Git-Wörter außerhalb von Code-Angaben."""
    return sorted({m.group(1) for m in MUSTER.finditer(ohne_code(text))})


def _abgeschaltet() -> bool:
    return os.environ.get("OPENSPEC_KLARTEXT", "").strip().lower() in _OFF_VALUES


def _nutzertext(eintrag: dict) -> "str | None":
    """Text einer echten Nutzernachricht, sonst None (Werkzeug-Ergebnis, Harness)."""
    if eintrag.get("isMeta"):
        return None
    inhalt = (eintrag.get("message") or {}).get("content")
    if isinstance(inhalt, str):
        text = inhalt
    elif isinstance(inhalt, list):
        teile = [b.get("text", "") for b in inhalt
                 if isinstance(b, dict) and b.get("type") == "text"]
        if not teile:
            return None
        text = "\n".join(t for t in teile if isinstance(t, str))
    else:
        return None
    if any(m in text for m in _HARNESS_MARKERS):
        return None
    text = _HARNESS_BLOCK_RE.sub(" ", text).strip()
    return text or None


def letzte_texte(pfad: str) -> "tuple[str, str]":
    """(Antworttext seit der letzten Nutzernachricht, letzte Nutzernachricht)."""
    with open(pfad, "rb") as f:
        f.seek(0, os.SEEK_END)
        groesse = f.tell()
        f.seek(max(0, groesse - _TAIL_BYTES))
        roh = f.read()
    zeilen = roh.decode("utf-8", "replace").splitlines()
    if groesse > _TAIL_BYTES and zeilen:
        zeilen = zeilen[1:]  # angeschnittene erste Zeile
    antwort: list = []
    for zeile in reversed(zeilen):
        if not zeile.strip():
            continue
        try:
            e = json.loads(zeile)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        if e.get("type") == "user":
            frage = _nutzertext(e)
            if frage is not None:
                return "\n".join(antwort), frage
            continue
        inhalt = (e.get("message") or {}).get("content")
        if e.get("type") == "assistant" and isinstance(inhalt, list):
            antwort[:0] = [b.get("text", "") for b in inhalt
                           if isinstance(b, dict) and b.get("type") == "text"
                           and isinstance(b.get("text"), str)]
    return "\n".join(antwort), ""


def main() -> None:
    if _abgeschaltet():
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        sys.exit(0)
    adopt_payload_cwd(payload)

    antwort = payload.get("last_assistant_message")
    frage = ""
    pfad = payload.get("transcript_path")
    if isinstance(pfad, str) and pfad:
        try:
            antwort_t, frage = letzte_texte(pfad)
        except Exception:
            antwort_t, frage = "", ""
        if not isinstance(antwort, str) or not antwort:
            antwort = antwort_t
    if not isinstance(antwort, str) or not antwort:
        sys.exit(0)

    if treffer(frage):
        sys.exit(0)  # der Nutzer hat selbst danach gefragt
    gefunden = treffer(antwort)
    if not gefunden:
        sys.exit(0)

    block(
        "KLARTEXT-PRÜFUNG: Die Antwort enthält Git-/Technik-Wörter ("
        + ", ".join(gefunden) + ").\n"
        "Der Nutzer hat kein Technikprofil (siehe CLAUDE.md des Nutzers). Schreib die "
        "Antwort neu: nur das fachliche Ergebnis in Alltagssprache; Git-Schritte "
        "erledigst du still."
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Fail-open: ein Absturz hier würde jedes Turn-Ende stören.
        sys.exit(0)
