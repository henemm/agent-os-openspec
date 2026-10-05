#!/usr/bin/env python3
"""
Adversary Dialog System — Structured QA-Tester / Fixer Verification.

Orchestriert einen strukturierten Dialog zwischen QA-Agent und Implementierer.
Parst die Spec, erstellt eine Checkliste aller Expected-Behavior-Punkte,
und validiert das Dialog-Artifact.

Best Practices implementiert:
  - Tri-State Verdict: VERIFIED / BROKEN / AMBIGUOUS
  - Circuit Breaker: Max 3 Iterationen, dann Eskalation
  - Structured Findings: severity, category, evidence, remediation
  - Early-Agreement-Skepticism: Min. 2 Runden Pflicht

Usage (CLI):
  python3 adversary_dialog.py parse <spec-path>
  python3 adversary_dialog.py scaffold <workflow-name> <spec-path>
  python3 adversary_dialog.py validate <artifact-path>
  python3 adversary_dialog.py stamp <artifact-path>
  python3 adversary_dialog.py required-files
  python3 adversary_dialog.py schema
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from hook_utils import (
    extract_ac_entries, find_project_root, find_worktree_root, is_gated_code_path,
    resolve_active_workflow,
)

# Circuit Breaker: max iterations before escalation to user
MAX_ITERATIONS = 3

# Minimum dialog rounds before VERIFIED is accepted
MIN_ROUNDS = 2

# Valid verdicts (tri-state)
VERDICTS = ("VERIFIED", "BROKEN", "AMBIGUOUS")

# Finding severity levels
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

# Finding categories
CATEGORIES = (
    "spec_violation",
    "edge_case",
    "regression",
    "security",
    "anti_pattern",
)


def parse_spec_expected_behavior(spec_path: str) -> list[str]:
    """Parse a spec file and extract Expected-Behavior- und AC-N-Checklist-Punkte.

    Erkennt zwei Formate:
      - '## Expected Behavior': Single-Line-Bullets ('- ' oder 'N. '),
        section-gebunden (unveraendertes Bestandsverhalten).
      - AC-N-Bullets ('- **AC-N:** ...', auch mit Klammer-Zusatz wie
        '(praezisiert)'): global erkannt, inkl. eingerueckter Soft-Wrap-
        Fortsetzungszeilen, exkl. eingerueckter '- Test:'-Sub-Bullets.

    Bei Koexistenz werden die Punkte additiv gemergt: zuerst alle
    Expected-Behavior-Punkte, danach alle AC-N-Punkte (jeweils in
    Dateireihenfolge), ohne Deduplizierung.

    Returns:
        Liste von Strings, jeder ein Checklist-Punkt.
        Leere Liste wenn nichts gefunden.
    """
    path = Path(spec_path)
    if not path.exists():
        return []

    content = path.read_text(errors="replace")
    lines = content.splitlines()

    # Expected-Behavior-Teil: unveraenderte Inline-Logik (section-gebundene
    # Single-Line-Bullets). Der AC-Teil wird von der geteilten Funktion
    # hook_utils.extract_ac_entries uebernommen (Konsolidierung #60/#69).
    section = None  # None | "expected_behavior" | "acceptance_criteria"
    eb_points = []

    for line in lines:
        stripped = line.strip()

        # Section-State pflegen (case-insensitive)
        if re.match(r"^##\s+Expected Behavior", stripped, re.IGNORECASE):
            section = "expected_behavior"
            continue
        if re.match(r"^##\s+Acceptance Criteria", stripped, re.IGNORECASE):
            section = "acceptance_criteria"
            continue
        # Jede andere H2-Section beendet die aktuelle Section
        if re.match(r"^##\s+", stripped):
            section = None
            continue

        if section == "expected_behavior":
            # Bullet-Points und nummerierte Listen (unveraendertes Verhalten)
            if re.match(r"^-\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
                point = re.sub(r"^(-\s+|\d+\.\s+)", "", stripped)
                if point:
                    eb_points.append(point)
            continue

    # AC-Teil ueber die geteilte Funktion; der ORIGINAL-Rohtext (raw) wird
    # unveraendert uebernommen -- kein Rekonstruktions-Template, damit
    # Label-Varianten ohne Bold bzw. mit Doppelpunkt ausserhalb Bold
    # byte-identisch zum Vor-Konsolidierungs-Stand bleiben (Fix F002).
    ac_points = [raw for _label, _desc, raw in extract_ac_entries(content)]

    return eb_points + ac_points


def create_checklist(points: list[str]) -> list[dict]:
    """Erstellt eine Checkliste aus Expected-Behavior-Punkten.

    Jeder Punkt wird zu einem Item mit:
      - description: Der Punkt-Text
      - status: "open" (noch nicht bewiesen)
      - evidence: None (noch kein Beweis)

    Returns:
        Liste von Dicts.
    """
    return [
        {"description": p, "status": "open", "evidence": None}
        for p in points
    ]


def render_finding(
    finding_id: str,
    severity: str,
    category: str,
    description: str,
    evidence: str,
    remediation: str = "",
) -> dict:
    """Erstellt ein strukturiertes Finding-Objekt.

    Args:
        finding_id: Eindeutige ID (z.B. "F001")
        severity: CRITICAL / HIGH / MEDIUM / LOW
        category: spec_violation / edge_case / regression / security / anti_pattern
        description: Was ist das Problem
        evidence: Beweis (Datei:Zeile, Test-Output, Screenshot-Pfad)
        remediation: Empfohlene Behebung

    Returns:
        Dict mit allen Feldern.
    """
    return {
        "id": finding_id,
        "severity": severity.upper() if severity.upper() in SEVERITIES else "MEDIUM",
        "category": category if category in CATEGORIES else "spec_violation",
        "description": description,
        "evidence": evidence,
        "remediation": remediation,
    }


def render_dialog_artifact(
    workflow_name: str,
    spec_path: str,
    checklist: list[dict],
    rounds: list[dict],
    findings: list[dict],
    final_verdict: str,
    iteration: int = 1,
) -> str:
    """Rendert das Dialog-Protokoll als Markdown-Artifact.

    Args:
        workflow_name: Name des Workflows
        spec_path: Pfad zur Spec-Datei
        checklist: Liste von Checklisten-Items (mit status + evidence)
        rounds: Liste von Dialog-Runden (mit round, adversary, implementer, verdict)
        findings: Liste von strukturierten Findings (render_finding output)
        final_verdict: VERIFIED / BROKEN / AMBIGUOUS
        iteration: Aktuelle Iteration des QA-Fixer-Loops (1-3)

    Returns:
        Markdown-String des Artifacts.
    """
    lines = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Header
    lines.append(f"# Adversary Dialog — {workflow_name}")
    lines.append(f"Spec: {spec_path}")
    lines.append(f"Datum: {timestamp}")
    lines.append(f"Iteration: {iteration} / {MAX_ITERATIONS}")
    lines.append("")

    # Checkliste
    lines.append("## Checkliste")
    for item in checklist:
        marker = "x" if item["status"] == "verified" else " "
        evidence = f" — Beweis: {item['evidence']}" if item.get("evidence") else " — OFFEN"
        lines.append(f"- [{marker}] {item['description']}{evidence}")
    lines.append("")

    # Findings (strukturiert)
    if findings:
        lines.append("## Findings")
        lines.append("")
        for f in findings:
            lines.append(f"### {f['id']}: {f['description']}")
            lines.append(f"- **Severity:** {f['severity']}")
            lines.append(f"- **Category:** {f['category']}")
            lines.append(f"- **Evidence:** {f['evidence']}")
            if f.get("remediation"):
                lines.append(f"- **Remediation:** {f['remediation']}")
            lines.append("")

    # Dialog-Runden
    lines.append("## Dialog")

    if len(rounds) < MIN_ROUNDS:
        lines.append("")
        lines.append(
            f"> **Warnung:** Nur {len(rounds)} Runde(n) dokumentiert. "
            f"Minimum sind {MIN_ROUNDS} Runden."
        )
        lines.append("")

    for r in rounds:
        lines.append(f"### Runde {r['round']}")
        lines.append(f"**Adversary:** {r['adversary']}")
        lines.append(f"**Implementierer:** {r['implementer']}")
        if r.get("verdict"):
            lines.append(f"**Bewertung:** {r['verdict']}")
        lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append(f"**{final_verdict}**")

    open_count = sum(1 for item in checklist if item["status"] != "verified")
    total = len(checklist)
    lines.append(f"Offene Punkte: {open_count} / {total}")

    if final_verdict.startswith("AMBIGUOUS"):
        lines.append("")
        lines.append("> Ambiguous findings require human review. "
                      "Pipeline is NOT blocked but user should verify.")

    # Circuit Breaker Status
    if iteration >= MAX_ITERATIONS:
        lines.append("")
        lines.append(f"> **Circuit Breaker:** Max iterations ({MAX_ITERATIONS}) reached. "
                      "Escalating to user.")

    return "\n".join(lines)


def _fence_marker_run(stripped: str) -> tuple[str, int, str] | None:
    """Zerlegt eine bereits von der Einrueckung befreite Zeile in Fence-Bestandteile.

    Returns:
        (marker_char, run_length, rest) wenn die Zeile mit >= 3 gleichen Fence-
        Zeichen (``` oder ~~~) beginnt -- `rest` ist alles nach dem Marker-Lauf
        (Info-String bzw. trailing Whitespace). Sonst None.
    """
    if not stripped:
        return None
    ch = stripped[0]
    if ch not in ("`", "~"):
        return None
    run = len(stripped) - len(stripped.lstrip(ch))
    if run < 3:
        return None
    return ch, run, stripped[run:]


def _fence_line_run(line: str) -> tuple[str, int, str] | None:
    """Wie _fence_marker_run, aber prueft ZUERST die CommonMark-Einrueckungsgrenze.

    CommonMark erlaubt eine Fence-Zeile (Oeffnen UND Schliessen) mit hoechstens
    3 fuehrenden Space-Zeichen; ab 4 Spaces oder bei einem Tab in der Einrueckungs-
    zone ist die Zeile Inhalt (indentierter Code / Text), KEINE Fence.

    Deshalb wird hier NICHT generisch lstrip() angewandt (das schluckte beliebige
    Einrueckung, Fix F006): nur bis zu 3 fuehrende Spaces werden entfernt, ein Tab
    in der Einrueckung disqualifiziert die Zeile als Fence.

    Returns (marker_char, run_length, rest) oder None.
    """
    n_spaces = len(line) - len(line.lstrip(" "))
    if n_spaces > 3:
        return None
    rest = line[n_spaces:]
    # Ein Tab unmittelbar in der Einrueckungszone (>= 4 Spaces-Aequivalent nach
    # CommonMark-Tab-Stop) macht die Zeile zu Inhalt, nicht zu einer Fence.
    if rest[:1] == "\t":
        return None
    return _fence_marker_run(rest)


def _strip_fenced_code_blocks(content: str) -> str:
    """Entfernt Zeilen innerhalb von ```- und ~~~-Fenced-Code-Bloecken.

    Zeilenbasierter Fence-Tracker nach der CommonMark/GFM-Spec, Abschnitt "Fenced
    code blocks". Zweck: ein in einem Codeblock ZITIERTES '## Verdict'/'### Runde'/
    '- [x]' darf nicht als echte Gate-Struktur gewertet werden. Fehlrichtung, die
    hier ausgeschlossen werden MUSS: False-PASS (ein zitiertes VERIFIED ueberschreibt
    ein echtes BROKEN). False-BLOCK (zu viel als Code behandelt -> "nichts gefunden"
    -> blockt) ist die bewusst gewaehlte sichere Richtung.

    ==================== CommonMark-Fence-Bedingungs-Matrix ====================
    Jede Bedingung des Spec-Abschnitts -> Code/Test ODER bewusste Abweichung, deren
    Effekt AUSSCHLIESSLICH False-Block sein kann (nie False-Pass). Ende des
    Whack-a-Mole (F001/F003/F004/F005/F006): die Liste ist hier vollstaendig.

    [C1] Oeffner = Zeile mit >= 3 gleichen Fence-Zeichen (``` oder ~~~).
         CODE: _fence_marker_run() (run >= 3). TEST: alle Fence-Tests (Basis).
    [C2] Oeffner-Einrueckung: 0-3 fuehrende Spaces erlaubt; >= 4 Spaces / Tab =>
         Zeile ist indentierter Inhalt, KEIN Fence-Oeffner.
         CODE: _fence_line_run() (n_spaces > 3 -> None; Tab in Einrueckung -> None).
         TEST: test_close_line_indented_3spaces_still_closes (Kontrolle 3 Spaces).
    [C3] Info-String hinter dem Oeffner-Lauf ist erlaubt (```python).
         CODE: _fence_marker_run() gibt `rest` zurueck, Oeffner ignoriert `rest`.
         TEST: test_info_string_line_does_not_close_open_fence.
    [C4] Backtick-Oeffner: Info-String darf KEINE weiteren Backticks enthalten
         (```a`b => kein gueltiger Oeffner, sondern Absatz). Tilde-Oeffner: Info-
         String darf Backticks enthalten (KEINE Restriktion, nicht ueberregulieren).
         CODE: Oeffner-Zweig -> is_opener = run is not None and not (run[0] == "`"
         and "`" in run[2]); eine Backtick-Zeile mit Backtick im Info-String OEFFNET
         nicht, sie bleibt gewoehnlicher Inhalt. TEST:
         test_backtick_infostring_opener_does_not_swallow_real_opener_false_pass,
         test_backtick_infostring_opener_mirror_real_verified_wins (F007) sowie die
         Tilde-Gegenprobe test_tilde_infostring_opener_still_opens_no_overregulation.
         Warum notwendig (Widerlegung der frueheren Abweichungs-Analyse): Oeffnete die
         Implementierung faelschlich bei Backtick-im-Info-String, wurde die unmittelbar
         folgende ECHTE bare ```-Oeffnerzeile als SCHLIESSER der (faelschlich) offenen
         Fence gewertet -> vorzeitiger Rueckfall in "ausserhalb" -> real versteckter
         Inhalt (inkl. zitiertem VERIFIED) wurde als Struktur freigegeben = False-Pass.
    [C5] Schliesser = Zeile mit DEMSELBEN Fence-Zeichen wie der Oeffner.
         CODE: run[0] == fence_marker. TEST: test_backtick_fence_with_inner_tilde_
         line_* / test_tilde_fence_with_inner_backtick_line_* (F004).
    [C6] Schliesser-Lauflaenge >= Oeffner-Lauflaenge (```` schliesst nicht mit ```).
         CODE: run[1] >= fence_len. TEST: test_longer_*_open_not_closed_by_shorter_
         inner_line, test_shorter_open_closed_by_longer_line_* (F005).
    [C7] Schliesser: nach dem Marker-Lauf nur noch Whitespace (kein Info-String).
         CODE: run[2].strip() == "". TEST: test_info_string_line_does_not_close_open_
         fence (F005).
    [C8] Schliesser-Einrueckung: ebenfalls 0-3 Spaces; >= 4 Spaces / Tab => die
         Zeile ist Fence-Inhalt und schliesst NICHT (frueher via lstrip() faelschlich
         geschlossen => False-Pass, Fix F006).
         CODE: _fence_line_run() (dieselbe Einrueckungspruefung wie C2).
         TEST: test_indented_4space_pseudo_close_does_not_close_fence,
         test_tab_indented_pseudo_close_does_not_close_fence.
    [C9] Unbalancierte Fence: bleibt eine Fence bis Dateiende offen, gilt sie als
         am Dateiende geschlossen; der gesamte Rest ist Fence-Inhalt und wird
         verworfen. CODE: Schleifenende ohne Reset -> restliche out-Zeilen fehlen.
         TEST: test_unbalanced_fence_before_verdict_is_failsafe (+ Tilde-Variante).
         Das ist zugleich der Fail-safe: lieber 'nichts gefunden' (blockt) als ein
         moeglicherweise zitiertes Verdict faelschlich werten.
    [C10] Inhaltszeilen einer offenen Fence werden bis zu N Spaces links entzerrt
          (N = Oeffner-Einrueckung). BEWUSSTE ABWEICHUNG: irrelevant, weil wir
          Inhaltszeilen komplett verwerfen statt sie zu rendern -> kein Effekt.
    ===========================================================================

    Innerhalb einer offenen Fence ist alles andere Inhalt und wird verworfen; die
    Marker-Zeilen selbst werden nie uebernommen (Fix F001/F003/F004/F005/F006).
    """
    out = []
    fence_marker = None  # None = ausserhalb; sonst "`" oder "~" (offener Fence-Typ)
    fence_len = 0        # Lauflaenge der oeffnenden Fence-Zeile
    for line in content.splitlines():
        run = _fence_line_run(line)

        if fence_marker is None:
            # CommonMark C4: ein Backtick-Oeffner darf KEINEN weiteren Backtick im
            # Info-String haben (```a`b => Absatz, kein Oeffner). Tilde-Oeffner haben
            # diese Restriktion NICHT (Info-String mit Backticks/Tilden erlaubt) --
            # nicht ueberregulieren. run[2] ist der Info-String (Rest nach dem Lauf).
            is_opener = run is not None and not (run[0] == "`" and "`" in run[2])
            if is_opener:
                # Fence oeffnen: Info-String (ohne Backtick bei ```) erlaubt, Typ +
                # Laenge merken.
                fence_marker, fence_len = run[0], run[1]
                continue
            out.append(line)
        else:
            # Innerhalb einer Fence: es schliesst NUR dieselbe Marker-Art mit
            # Lauflaenge >= der oeffnenden und ohne Info-String (nur Whitespace).
            if (
                run is not None
                and run[0] == fence_marker
                and run[1] >= fence_len
                and run[2].strip() == ""
            ):
                fence_marker = None
                fence_len = 0
            # Alle anderen Zeilen (anderer Marker, kuerzer, Info-String) verwerfen.
            continue
    return "\n".join(out)


def validate_dialog_artifact(artifact_path: str) -> tuple[bool, str]:
    """Validiert ein Dialog-Artifact. Rueckwaertskompatible 2-Tupel-Form.

    Siehe validate_dialog_artifact_ex() fuer die Variante mit
    Fehlerklassifikation (content vs. format).
    """
    valid, message, _kind = validate_dialog_artifact_ex(artifact_path)
    return valid, message


def validate_dialog_artifact_ex(artifact_path: str,
                                min_rounds: int = MIN_ROUNDS) -> "tuple[bool, str, str | None]":
    """Validiert ein Dialog-Artifact.

    Prueft:
    1. Datei existiert
    2. Alle Checklisten-Punkte sind [x] (abgehakt) — oder, als Fallback,
       Confirmation-Bloecke des implementation-validator ('Status: CONFIRMED')
    3. Mindestens MIN_ROUNDS Dialog-Runden dokumentiert
    4. Verdict ist VERIFIED/HOLDS oder AMBIGUOUS (nicht BROKEN) —
       HOLDS ist das dokumentierte Vokabular des implementation-validator
       und wird als Synonym fuer VERIFIED akzeptiert (Issue #77)
    5. Datei-Identitaet: die im '## Geprüfte Dateien'-Block gehashten Dateien
       (per 'stamp' geschrieben) muessen mit dem Ist-Stand uebereinstimmen —
       Ersatz fuer die fruehere Alters-Pruefung (Issue #131). Laeuft NUR fuer
       Artefakte, die sonst valid=True ergeben wuerden (VERIFIED/HOLDS/
       AMBIGUOUS); ein BROKEN- oder unbekanntes Verdict blockt unabhaengig
       davon bereits — das ist die sichere Richtung und braucht keine
       zusaetzliche Datei-Pruefung.
    6. Circuit Breaker nicht ausgeloest ohne Eskalation

    Returns:
        (valid, message, failure_kind) — failure_kind ist None bei Erfolg,
        'content' wenn das Artefakt ein INHALTLICH negatives Ergebnis belegt
        (BROKEN-Verdict, offene Checklisten-Punkte), 'format' wenn nur die
        FORM nicht lesbar ist (fehlende/unbekannte Marker, fehlender/
        veralteter Datei-Hash-Block, fehlende Datei). Die Unterscheidung
        braucht qa_gate: ein Formfehler darf kein BROKEN-Verdict in den
        Workflow-State schreiben (Issue #77) — das gilt unveraendert auch
        fuer einen Hash-Mismatch: der belegt keinen Adversary-Befund, nur
        dass der Nachweis nicht mehr zum Ist-Stand passt.
    """
    path = Path(artifact_path)

    # 1. Existenz
    if not path.exists():
        return False, f"Dialog artifact not found: {artifact_path}", "format"

    content = path.read_text(errors="replace")
    # Struktur-Checks (Checkliste, Runden, Verdict) laufen auf einem Inhalt OHNE
    # Fenced-Code-Bloecke: zitierte/illustrative '## Verdict'-, '### Runde'- oder
    # '- [x]'-Zeilen in Backtick-Bloecken (Findings, Formatvorlagen) duerfen nicht
    # als echte Struktur gewertet werden (Fix F001).
    scan = _strip_fenced_code_blocks(content)

    # Alle Struktur-Scans sind mit (?m)^ am ZEILENANFANG verankert: '## Verdict',
    # '### Runde' und die Checklisten-Marker zaehlen nur als echte Struktur, wenn sie
    # eine Zeile beginnen. Ein in Prosa MITTEN in einer Zeile zitiertes '## Verdict'
    # ('...siehe ## Verdict') matcht so nicht mehr und kann kein echtes Verdict
    # ueberschreiben (Anker-Fix). RESTRISIKO (bewusst akzeptiert): ein in Prosa
    # zitiertes '## Verdict' das SELBST am Zeilenanfang steht, wird weiter gewertet --
    # das ist korrekt, denn eine Markdown-Ueberschrift IST per Definition
    # zeilenanfangs-definiert und damit ununterscheidbar von einer echten.

    # 2. Checkliste: Alle Punkte muessen [x] sein
    checked = len(re.findall(r"(?m)^- \[x\]", scan, re.IGNORECASE))
    unchecked = len(re.findall(r"(?m)^- \[ \]", scan))

    if unchecked > 0:
        return False, (
            f"{unchecked} Checklisten-Punkt(e) noch offen. "
            "Alle muessen bewiesen sein."
        ), "content"

    if checked == 0:
        # Fallback (Issue #77): der implementation-validator dokumentiert
        # bewiesene ACs als Confirmation-Bloecke ('Status: CONFIRMED') statt
        # als Checkbox-Zeilen. Beide Formen sind gueltige Beweisfuehrung.
        checked = len(re.findall(r"(?mi)^\s*Status:\s*CONFIRMED\b", scan))
        if checked == 0:
            return False, "Keine Checklisten-Punkte gefunden.", "format"

    # 3. Mindestens MIN_ROUNDS Runden
    # H2 und H3 zaehlen (#278): '## Runde N' ist der real geratene Fall vom 2026-09-27.
    rounds = len(re.findall(r"(?m)^#{2,3} Runde \d+", scan))
    if rounds < min_rounds:
        return False, (
            f"Nur {rounds} Dialog-Runde(n) dokumentiert. "
            f"Minimum sind {min_rounds} Runden."
        ), "format"

    # 4. Verdict — gemeinsamer Parser mit dialog_verdict() (#259 F003): drei
    #    Formen (Issue #77), letztes Vorkommen gewinnt, HOLDS = VERIFIED.
    verdict_text = _verdict_text(scan)
    if verdict_text is None:
        return False, "Kein Verdict im Artifact gefunden.", "format"
    v = _normalize_verdict(verdict_text)

    if v == "BROKEN":
        return False, f"Verdict ist '{verdict_text}' — nicht VERIFIED.", "content"

    if v is None:
        return False, f"Unbekanntes Verdict: '{verdict_text}'", "format"

    # 5. Datei-Identitaet (Issue #131): nur fuer Artefakte, die hier sonst
    # valid=True ergeben wuerden. Ein Hash-Mismatch ist kein inhaltliches
    # Urteil des Adversary, sondern ein Formproblem des Nachweises selbst.
    hashes_ok, hashes_msg = _verify_examined_file_hashes(scan)
    if not hashes_ok:
        return False, hashes_msg, "format"

    # 6. Herkunft der Vorbedingungen (Issue #286): als LETZTER Schritt, damit
    # Inhaltsfehler weiter vor Formfehlern gewinnen (#77). mode=warn blockt nicht.
    gate = _precondition_gate_config()
    if gate["enabled"] and not (gate["skip_fast_track"] and _active_workflow_is_fast_track()):
        p_ok, p_msg, p_kind = _verify_precondition_section(scan)
        if not p_ok:
            if gate["mode"] == "block":
                return False, p_msg, p_kind
            print(f"WARNUNG (precondition_section_gate, mode=warn): {p_msg}", file=sys.stderr)

    if v == "AMBIGUOUS":
        return True, (
            f"Dialog valid (AMBIGUOUS): {checked} Punkte bewiesen, "
            f"{rounds} Runden. User-Review empfohlen."
        ), None

    return True, (
        f"Dialog valid: {checked} Punkte bewiesen, "
        f"{rounds} Runden, Verdict VERIFIED."
    ), None


# Verdict-Formen (Issue #77), zeilenanfangs-verankert, auf fence-bereinigtem Text:
#   a) '## Verdict' mit Fettschrift-Folgezeile (render_dialog_artifact)
#   b) einzeilig '## Verdict: X' bzw. '### VERDICT: X'
#   c) 'VERDICT: X' am Zeilenanfang (Abschlussformat des implementation-validator)
_VERDICT_RES = (
    re.compile(r"(?m)^## Verdict\s*\n\*\*(.+?)\*\*"),
    re.compile(r"(?mi)^#{2,3}\s*Verdict\s*:\s*(.+?)\s*$"),
    re.compile(r"(?m)^VERDICT:\s*(.+?)\s*$"),
)


def _verdict_text(scan: str) -> "str | None":
    """Roh-Text des LETZTEN Verdicts (Fix-Loop-Runden: last wins), oder None."""
    matches = [m for rx in _VERDICT_RES for m in rx.finditer(scan)]
    if not matches:
        return None
    return max(matches, key=lambda m: m.start()).group(1).strip().strip("*").strip()


def _normalize_verdict(text: str) -> "str | None":
    """'VERIFIED' | 'BROKEN' | 'AMBIGUOUS' oder None; HOLDS ist VERIFIED (Issue #77)."""
    upper = text.upper()
    if upper.startswith("HOLDS"):
        return "VERIFIED"
    return next((v for v in VERDICTS if upper.startswith(v)), None)


def dialog_verdict(artifact_path: str) -> "str | None":
    """Strukturiert geparstes Verdict eines Dialog-Artefakts (#259 F003).

    Derselbe Parser wie validate_dialog_artifact_ex(); None, wenn die Datei
    nicht lesbar ist oder kein Verdict enthaelt.
    """
    try:
        content = Path(artifact_path).read_text(errors="replace")
    except OSError:
        return None
    text = _verdict_text(_strip_fenced_code_blocks(content))
    return None if text is None else _normalize_verdict(text)


_CODE_REF_RE = re.compile(r"(?im)^\s*Code reference:\s*(\S+)")
_EXAMINED_FILES_HEADER_RE = re.compile(r"(?m)^## Geprüfte Dateien\s*$")
_EXAMINED_FILES_LINE_RE = re.compile(r"(?m)^-\s*sha256:([0-9a-f]{64})\s+(.+?)\s*$")


def _extract_examined_files(scan: str) -> list[str]:
    """Eindeutige Dateipfade aus 'Code reference: <pfad>:<zeile>'-Zeilen.

    Quelle bewusst NICHT die Spec-Source-Section oder `affected_files` im
    Workflow-State (beides vom Issue #131 nur als Beispiel genannt): die
    Code-reference-Zeile ist in implementation-validator.md fuer jedes
    Finding/jede Confirmation bereits verpflichtend und spiegelt exakt, was
    der Adversary tatsaechlich gelesen hat.
    """
    files = set()
    for m in _CODE_REF_RE.finditer(scan):
        token = m.group(1)
        path = re.sub(r":\d[\d,\-]*$", "", token)  # ':<zeile>'-Suffix abtrennen
        if path:
            files.add(path)
    return sorted(files)


def _hash_root() -> Path:
    """Root fuer relative Datei-Pfade — Worktree bevorzugt vor Haupt-Repo.

    Mirrors die in Issue #80/#96 etablierte Regel: eine Worktree-Session
    misst gegen ihren EIGENEN Arbeitsbaum, nicht gegen den geteilten
    Haupt-Repo (der dort eine andere, meist unveraenderte Kopie haelt).
    """
    return find_worktree_root() or find_project_root()


def _resolve_hash_path(rel_path: str) -> Path:
    p = Path(rel_path)
    return p if p.is_absolute() else (_hash_root() / p)


def render_examined_files_section(hashes: dict) -> str:
    """Rendert den '## Geprüfte Dateien'-Block ('- sha256:<hex>  <pfad>')."""
    lines = ["## Geprüfte Dateien", ""]
    for path in sorted(hashes):
        lines.append(f"- sha256:{hashes[path]}  {path}")
    lines.append("")
    return "\n".join(lines)


def _parse_examined_files_section(scan: str) -> "list[tuple[str, str]] | None":
    """(hash, pfad)-Paare aus dem LETZTEN '## Geprüfte Dateien'-Block.

    None wenn KEIN solcher Block existiert (Unterschied zu einer leeren
    Liste: ein vorhandener, aber leerer Block waere kein sinnvoller Fall,
    da 'stamp' ohne Code-reference-Zeilen bereits fehlschlaegt). Mehrere
    Bloecke (Fix-Loop-Iterationen) -> nur der LETZTE zaehlt, exakt wie beim
    Verdict (Issue #77 last-wins).
    """
    headers = list(_EXAMINED_FILES_HEADER_RE.finditer(scan))
    if not headers:
        return None
    rest = scan[headers[-1].end():]
    next_heading = re.search(r"(?m)^##\s", rest)
    body = rest[:next_heading.start()] if next_heading else rest
    return _EXAMINED_FILES_LINE_RE.findall(body)


def _verify_examined_file_hashes(scan: str) -> tuple[bool, str]:
    """Vergleicht den letzten Hash-Block mit dem Ist-Stand im Arbeitsbaum.

    Ersetzt die fruehere Alters-Pruefung (Issue #131): Uebereinstimmung ist
    unabhaengig vom Datei-Alter gueltig, Abweichung blockt sofort.
    """
    entries = _parse_examined_files_section(scan)
    if entries is None:
        return False, (
            "Kein Datei-Hash-Block (## Geprüfte Dateien) im Artifact "
            "gefunden. Re-run dialog."
        )
    rebase = None          # lazy: '## Prüfbasis'-Block erst bei Abweichung lesen
    rebased_ok: set = set()
    for expected_hash, rel_path in entries:
        full = _resolve_hash_path(rel_path)
        try:
            actual_hash = hashlib.sha256(full.read_bytes()).hexdigest()
        except OSError:
            return False, (
                f"Prüfling seit dem Dialog geändert: {rel_path} "
                "(nicht mehr lesbar). Re-run dialog."
            )
        if actual_hash != expected_hash:
            if rel_path in rebased_ok:
                continue
            if rebase is None:
                rebase = _parse_review_base_section(scan)
            if rebase and _own_change_survived_rebase(rel_path, rebase):
                rebased_ok.add(rel_path)
                continue
            return False, (
                f"Prüfling seit dem Dialog geändert: {rel_path}. Re-run dialog. "
                "(Nach Aufsetzen auf main gilt der Nachweis weiter, wenn sich nur die "
                "Basis geändert hat und die eigene Änderung samt 3 Kontextzeilen gleich "
                "geblieben ist — hier nicht der Fall, #289.)"
            )
    return True, ""


# --- Aufsetzen auf main (Issue #289) ---
#
# Der Hash bindet die GANZE Datei. Holt der Zweig nach dem VERIFIED main ein
# (Rebase/Merge, von bash_gate 5b erzwungen) und hat main eine gebundene Datei
# geaendert, passte der Hash nie mehr — ohne dass sich an der eigenen Aenderung
# etwas geaendert hat. Daher haelt der Stempel zusaetzlich die Basis
# (merge-base origin/main) und je Datei einen Fingerabdruck der EIGENEN
# Aenderung fest: Unified-Diff Basis -> Datei mit 3 Kontextzeilen, ohne
# Hunk-Kopf (Zeilennummern verschieben sich legitim). Akzeptiert wird eine
# Abweichung nur, wenn (1) die Basis vorwaerts gerueckt ist (alte Basis ist
# Vorfahre der neuen), (2) main die Datei dazwischen tatsaechlich geaendert hat
# und (3) der Fingerabdruck gegen die NEUE Basis gleich ist. Upstream-Aenderungen
# in Kontextnaehe, verschobene eigene Zeilen oder jede eigene Nacharbeit
# aendern den Fingerabdruck -> neuer Dialog wie bisher (fail-closed).

REVIEW_BASE_SECTION = "## Prüfbasis"
_REVIEW_BASE_HEADER_RE = re.compile(r"(?m)^## Prüfbasis\s*$")
_REVIEW_BASE_LINE_RE = re.compile(r"(?m)^-\s*base:\s*([0-9a-f]{7,64})\s*$")
_REVIEW_DELTA_LINE_RE = re.compile(r"(?m)^-\s*delta:([0-9a-f]{64})\s+(.+?)\s*$")


def _git_out(args: "list[str]", cwd) -> "str | None":
    try:
        proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                              timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="surrogateescape")


def _review_base(top: str) -> "str | None":
    out = _git_out(["merge-base", "origin/main", "HEAD"], top)
    out = (out or "").strip()
    return out if re.fullmatch(r"[0-9a-f]{7,64}", out) else None


def _rel_to_top(rel_path: str, top: str) -> "str | None":
    full = os.path.realpath(str(_resolve_hash_path(rel_path)))
    rel = os.path.relpath(full, top)
    return None if rel.startswith("..") or os.path.isabs(rel) else rel


def _blob_text(base: str, git_rel: str, top: str) -> "str | None":
    """Inhalt der Datei in `base`; '' wenn sie dort nicht existiert, None bei Fehler."""
    exists = _git_out(["cat-file", "-e", f"{base}:{git_rel}"], top)
    if exists is None:
        return "" if _git_out(["rev-parse", "--verify", "-q", f"{base}^{{commit}}"], top) else None
    return _git_out(["show", f"{base}:{git_rel}"], top)


def _own_change_digest(base: str, rel_path: str, top: str) -> "str | None":
    """Fingerabdruck der eigenen Aenderung an `rel_path` gegenueber `base`."""
    import difflib
    git_rel = _rel_to_top(rel_path, top)
    if git_rel is None:
        return None
    old = _blob_text(base, git_rel, top)
    if old is None:
        return None
    try:
        new = _resolve_hash_path(rel_path).read_bytes().decode("utf-8", errors="surrogateescape")
    except OSError:
        return None
    lines = [ln for ln in difflib.unified_diff(old.splitlines(), new.splitlines(),
                                               lineterm="", n=3)
             if not ln.startswith(("---", "+++", "@@"))]
    payload = "\n".join(lines).encode("utf-8", errors="surrogateescape")
    return hashlib.sha256(payload).hexdigest()


def render_review_base_section(base: str, deltas: dict) -> str:
    lines = [REVIEW_BASE_SECTION, "", f"- base: {base}"]
    for path in sorted(deltas):
        lines.append(f"- delta:{deltas[path]}  {path}")
    lines.append("")
    return "\n".join(lines)


def _parse_review_base_section(scan: str) -> "dict | None":
    """{'base', 'deltas'} aus dem '## Prüfbasis'-Block HINTER dem letzten Hash-Block."""
    hash_headers = list(_EXAMINED_FILES_HEADER_RE.finditer(scan))
    headers = list(_REVIEW_BASE_HEADER_RE.finditer(scan))
    if not hash_headers or not headers or headers[-1].start() < hash_headers[-1].start():
        return None
    rest = scan[headers[-1].end():]
    nxt = re.search(r"(?m)^##\s", rest)
    body = rest[:nxt.start()] if nxt else rest
    base = _REVIEW_BASE_LINE_RE.search(body)
    if not base:
        return None
    return {"base": base.group(1),
            "deltas": {p: h for h, p in _REVIEW_DELTA_LINE_RE.findall(body)}}


def _own_change_survived_rebase(rel_path: str, rebase: dict) -> bool:
    expected = rebase["deltas"].get(rel_path)
    old_base = rebase["base"]
    if not expected:
        return False
    try:
        top = git_toplevel(_hash_root())
    except ChangeSetError:
        return False
    if not top:
        return False
    new_base = _review_base(top)
    if not new_base or new_base.startswith(old_base) or old_base.startswith(new_base):
        return False  # Basis unveraendert: jede Abweichung ist eigene Nacharbeit
    if _git_out(["merge-base", "--is-ancestor", old_base, new_base], top) is None:
        return False  # keine Vorwaertsbewegung entlang main
    git_rel = _rel_to_top(rel_path, top)
    if git_rel is None:
        return False
    before, after = _blob_text(old_base, git_rel, top), _blob_text(new_base, git_rel, top)
    if before is None or after is None or before == after:
        return False  # main hat die Datei nicht angefasst -> Abweichung ist eigene
    return _own_change_digest(new_base, rel_path, top) == expected


def _review_base_block(hashes: dict) -> str:
    """'## Prüfbasis'-Block fuer den Stempel; '' ohne Git/origin/main (best-effort)."""
    try:
        top = git_toplevel(_hash_root())
    except ChangeSetError:
        return ""
    if not top:
        return ""
    base = _review_base(top)
    if not base:
        return ""
    deltas = {}
    for rel in hashes:
        d = _own_change_digest(base, rel, top)
        if d:
            deltas[rel] = d
    return render_review_base_section(base, deltas) if deltas else ""

# --- Herkunft der Vorbedingungen (Issue #286) ---

PRECONDITION_SECTION = "## Herkunft der Vorbedingungen"
_PRECONDITION_HEADER_RE = re.compile(r"(?m)^## Herkunft der Vorbedingungen\s*$")
_FAST_TRACK_TYPES = ("feature-fast",)
# Gueltige "nichts zu pruefen"-Inhalte: Hinweis ohne Sprachprofil (50-implement.md
# Step 8a) und die drei Leer-Ausgaben von precondition_origins.py (EMPTY_TABLE_HINT
# sowie die Praefixe der Meldungen ohne Modelldateien bzw. ohne Feldnamen; der
# dynamische Rest — Glob-Liste, Dateizahl, Muster — bleibt bewusst ungeprueft).
_PRECONDITION_EMPTY_HINTS = (
    "kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)",
    "Kein Feld mit Test-Zuweisung gefunden — nichts zu pruefen.",
    "Keine Modelldateien gefunden unter",
    "Keine Feldnamen extrahierbar aus",
)


def _parse_precondition_section(scan: str) -> "list[dict] | None":
    """Zeilen der LETZTEN '## Herkunft der Vorbedingungen'-Sektion, oder None.

    Je Tabellenzeile ein dict {field, test_refs, prod_refs, condition,
    test_for_path}; Kopf-, Trenn- und Zeilen mit falscher Spaltenzahl werden
    uebersprungen. Ohne Tabellenzeile -> [] nur mit einem der Hinweistexte
    (_PRECONDITION_EMPTY_HINTS), sonst None (unausgefuellt = fehlend).
    """
    headers = list(_PRECONDITION_HEADER_RE.finditer(scan))
    if not headers:
        return None
    rest = scan[headers[-1].end():]
    next_heading = re.search(r"(?m)^##\s", rest)
    body = rest[:next_heading.start()] if next_heading else rest
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip() for c in line[1:-1].split("|")]
        if len(cells) != 5 or cells[0] == "Feld" or set(cells[0]) <= set("-: "):
            continue
        rows.append(dict(zip(("field", "test_refs", "prod_refs", "condition",
                              "test_for_path"), cells)))
    if not rows and not any(h in body for h in _PRECONDITION_EMPTY_HINTS):
        return None
    return rows


def _is_suspect_row(row: dict) -> bool:
    """Verdachtsgruppe: hoechstens 1 Produktions-Schreibstelle (#285 AC-7).

    Liest die fuehrende Anzahl ('1 — ...', '**0 — keine Schreibstelle ...**');
    fehlt sie, zaehlen die <br>-getrennten Fundstellen.
    """
    prod = row.get("prod_refs", "").strip()
    m = re.match(r"^\**\s*(\d+)\s*—", prod)
    if m:
        return int(m.group(1)) <= 1
    return len([p for p in prod.split("<br>") if p.strip()]) <= 1


def _verify_precondition_section(scan: str) -> "tuple[bool, str, str | None]":
    """Fehlt -> (False, msg, 'format'); Verdachtszeile ohne 'Bedingung davor'
    oder 'Test für diesen Weg' -> (False, msg, 'content'); sonst (True, msg, None)."""
    rows = _parse_precondition_section(scan)
    if rows is None:
        return False, (
            f"Sektion '{PRECONDITION_SECTION}' fehlt im Artifact "
            "(Tabelle aus precondition_origins.py oder Hinweistext)."
        ), "format"
    incomplete = [r["field"] for r in rows
                  if _is_suspect_row(r) and not (r["condition"] and r["test_for_path"])]
    if incomplete:
        return False, (
            f"'{PRECONDITION_SECTION}': Verdachtszeile(n) ohne 'Bedingung davor' oder "
            f"'Test für diesen Weg': {', '.join(incomplete)}"
        ), "content"
    return True, f"'{PRECONDITION_SECTION}' vollständig ({len(rows)} Zeile(n)).", None


def _precondition_gate_config() -> dict:
    """`precondition_section_gate` mit Defaults; ungueltiger mode zaehlt als 'warn'."""
    gate = {"enabled": True, "mode": "warn", "skip_fast_track": True}
    try:
        from config_loader import load_config
        section = load_config().get("precondition_section_gate", {})
    except Exception:
        section = {}
    if isinstance(section, dict):
        gate.update({k: section[k] for k in gate if k in section})
    if gate["mode"] != "block":
        gate["mode"] = "warn"
    gate["enabled"] = gate["enabled"] is not False
    return gate


def _active_workflow_is_fast_track() -> bool:
    """workflow_type des aktiven Workflows ist 'feature-fast'.

    Kein aktiver Workflow oder State nicht lesbar -> False (die Pruefung laeuft).
    """
    try:
        name = resolve_active_workflow()[0]
        if not name:
            return False
        state = find_project_root() / ".claude" / "workflows" / f"{name}.json"
        wf = json.loads(state.read_text())
    except (OSError, ValueError):
        return False
    return isinstance(wf, dict) and wf.get("workflow_type") in _FAST_TRACK_TYPES


def stamp_dialog_artifact(artifact_path: str) -> tuple[bool, str]:
    """Haengt einen '## Geprüfte Dateien'-Hash-Block ans Dialog-Artifact an.

    Liest jede 'Code reference: <pfad>:<zeile>'-Zeile aus Findings/
    Confirmations, hasht die referenzierten Dateien (SHA-256, aktueller
    Arbeitsbaum-Stand) und schreibt sie als maschinenlesbaren Block ins
    Artifact. Vom implementation-validator-Agenten als letzter Schritt
    nach dem Verdict aufzurufen — validate_dialog_artifact_ex() vergleicht
    spaeter gegen genau diese Hashes statt gegen die Datei-mtime.
    """
    path = Path(artifact_path)
    if not path.exists():
        return False, f"Dialog artifact not found: {artifact_path}"

    content = path.read_text(errors="replace")
    scan = _strip_fenced_code_blocks(content)
    files = _extract_examined_files(scan)
    if not files:
        return False, (
            "Keine 'Code reference:'-Zeilen im Artifact gefunden — "
            "nichts zu hashen. Jedes Finding/jede Confirmation braucht "
            "eine 'Code reference: <pfad>:<zeile>'-Zeile."
        )

    hashes = {}
    skipped = []
    for rel in files:
        full = _resolve_hash_path(rel)
        try:
            hashes[rel] = hashlib.sha256(full.read_bytes()).hexdigest()
        except OSError:
            skipped.append(rel)

    if not hashes:
        return False, f"Keine der referenzierten Dateien war lesbar: {', '.join(files)}"

    section = render_examined_files_section(hashes)
    base_block = _review_base_block(hashes)  # #289: Basis + eigene Aenderung
    if base_block:
        section += "\n" + base_block
    path.write_text(content.rstrip("\n") + "\n\n" + section)

    msg = f"{len(hashes)} Datei(en) gehasht und in {artifact_path} gespeichert."
    if skipped:
        msg += f" Uebersprungen (nicht lesbar): {', '.join(skipped)}"
    # Best-effort NACH dem Hash-Block (#278): ein Fehler hier entwertet den Stempel nicht.
    return True, msg + " " + _persist_adversary_metrics(scan)


def _count_findings(scan: str) -> int:
    """Eindeutige Finding-IDs (`ID: F\\d+`) im fence-bereinigten Text (#278)."""
    return len(set(re.findall(r"(?m)^\s*(?:-\s*)?ID:\s*(F\d+)\b", scan)))


def _persist_adversary_metrics(scan: str) -> str:
    """Schreibt adversary_findings_total und affected_files in den aktiven State (#278).

    Best-effort: liefert eine Meldung (auch bei Warnungen), wirft nie.
    """
    name = resolve_active_workflow()[0]
    if not name:
        return "WARNUNG: Kein aktiver Workflow — Kennzahlen nicht persistiert."
    state = find_project_root() / ".claude" / "workflows" / f"{name}.json"
    try:
        wf = json.loads(state.read_text())
    except (OSError, ValueError):
        wf = None
    if not isinstance(wf, dict):
        return f"WARNUNG: State von {name} nicht lesbar — Kennzahlen nicht persistiert."

    workflow_py = Path(__file__).parent / "workflow.py"
    n = _count_findings(scan)
    calls = [["set-field", "adversary_findings_total", str(n)]]
    try:
        files, _info = phase8_code_files(wf)
    except ChangeSetError:
        files = None
    if files is not None:
        calls.append(["set-affected-files", "--replace", *files])

    warnings = []
    for args in calls:
        try:
            r = subprocess.run([sys.executable, str(workflow_py), *args],
                               capture_output=True, text=True)
            if r.returncode != 0:
                warnings.append(f"{args[0]}: {r.stderr.strip() or r.stdout.strip()}")
        except OSError as exc:
            warnings.append(f"{args[0]}: {exc}")
    if warnings:
        return "WARNUNG: Kennzahlen nicht vollständig persistiert — " + "; ".join(warnings)
    count = "unverändert" if files is None else str(len(files))
    return f"Kennzahlen persistiert: {n} Finding(s), affected_files {count}."


# --- Dialog-Nachweis fuer Commit-Gate und Phase 8 (Issue #253) ---

DEFAULT_DIALOG_ARTIFACT = "docs/artifacts/{name}/adversary-dialog.md"


def _resolve_artifact_path(raw: str) -> Path:
    """Relativ: Worktree-Root, falls die Datei dort liegt, sonst Projekt-Root.

    Absolute Pfade bleiben unveraendert (Muster aus #80/#96/#131).
    """
    path = Path(raw)
    if path.is_absolute():
        return path
    worktree = find_worktree_root()
    if worktree is not None and (worktree / path).exists():
        return worktree / path
    return find_project_root() / path


def find_dialog_artifact(wf: dict) -> "Path | None":
    """Dialog-Artefakt eines Workflows, oder None wenn es keins gibt.

    (a) das zuletzt registrierte `test_artifacts`-Element vom Typ
        'adversary_dialog' (neuestes gewinnt) — auch wenn die Datei fehlt:
        die ausdrueckliche Registrierung gewinnt, kein stiller Rueckfall;
    (b) sonst der Standardpfad, falls er existiert — nur mit Workflow-Namen:
        ohne Namen gibt es keinen Standardpfad (#259 F004).
    Ob der Pfad innerhalb von Projekt/Worktree liegt (F002), prueft
    check_dialog_evidence().
    """
    registered = [
        a for a in (wf.get("test_artifacts") or [])
        if isinstance(a, dict) and a.get("type") == "adversary_dialog" and a.get("path")
    ]
    if registered:
        return _resolve_artifact_path(str(registered[-1]["path"]))
    if not wf.get("name"):
        return None
    default = _resolve_artifact_path(DEFAULT_DIALOG_ARTIFACT.format(name=wf["name"]))
    return default if default.exists() else None


def _outside_roots(path: Path) -> bool:
    """F002 (#259 §8): liegt der Pfad (Symlinks aufgeloest) ausserhalb von Worktree und Projekt?"""
    resolved = path.resolve()
    roots = [r.resolve() for r in (find_worktree_root(), find_project_root()) if r is not None]
    return not any(r == resolved or r in resolved.parents for r in roots)


def required_rounds() -> int:
    """Mindestzahl der Dialog-Runden nach Risiko (#342). MIN_ROUNDS bei hohem
    Risiko, sonst der geprueft gueltige `low_risk_min_rounds` (echter int
    1..MIN_ROUNDS). Jeder Fehler, jeder ungueltige Wert: MIN_ROUNDS."""
    try:
        from hook_utils import adversary_risk_report
        report = adversary_risk_report()
        value = report.get("min_rounds")
        if (report.get("risk") == "niedrig" and type(value) is int
                and 1 <= value <= MIN_ROUNDS):
            return value
    except Exception:
        pass
    return MIN_ROUNDS


def check_dialog_evidence(wf: dict, changed_files: "list[str] | None" = None) -> "str | None":
    """Die eine Regel fuer Commit-Gate (bash_gate.py 5c) und Phase 8 (workflow.py).

    None: ein gueltiges, gestempeltes, zum Ist-Stand passendes Dialog-Artefakt
    innerhalb von Projekt/Worktree deckt das Verdict im State — und bindet, falls
    `changed_files` uebergeben ist (realpath-absolute Pfade, vom Aufrufer
    ermittelt), jede dieser Dateien im letzten '## Geprüfte Dateien'-Block (#259).
    Sonst der Grund als Text. Wirft nie — ein interner Fehler wird zur
    Grund-Meldung (fail-closed).
    """
    try:
        path = find_dialog_artifact(wf)
        if path is None:
            if not wf.get("name"):
                return (
                    "kein Dialog-Artefakt registriert (workflow.py add-artifact "
                    "adversary_dialog <pfad>) — ohne Workflow-Namen gibt es keinen Standardpfad"
                )
            default = DEFAULT_DIALOG_ARTIFACT.format(name=wf["name"])
            return (
                "kein Dialog-Artefakt registriert (workflow.py add-artifact "
                f"adversary_dialog <pfad>) und keins am Standardpfad {default}"
            )
        if _outside_roots(path):
            return f"Dialog-Artefakt liegt außerhalb von Projekt und Worktree: `{path}`"
        if not path.exists():
            return (
                f"registriertes Dialog-Artefakt nicht gefunden: {path} "
                "(die Registrierung gilt — kein Rückfall auf den Standardpfad)"
            )
        # Nur bei NIEDRIGEM Risiko weicht die Mindestzahl vom Standard ab; sonst
        # bleibt der Aufruf unveraendert (Standard MIN_ROUNDS).
        rounds_needed = required_rounds()
        if rounds_needed == MIN_ROUNDS:
            valid, message, _kind = validate_dialog_artifact_ex(str(path))
        else:
            valid, message, _kind = validate_dialog_artifact_ex(
                str(path), min_rounds=rounds_needed)
        if not valid:
            return f"{path}: {message}"
        if changed_files is not None:
            missing = _uncovered_files(path, changed_files)
            if missing:
                return _uncovered_reason(missing)
        verdict = str(wf.get("adversary_verdict") or "")
        if verdict.startswith("VERIFIED") and dialog_verdict(str(path)) == "AMBIGUOUS":
            return f"Widerspruch: der State behauptet VERIFIED, {path} belegt nur AMBIGUOUS"
        return None
    except Exception as exc:  # fail-closed
        return f"Nachweis-Prüfung fehlgeschlagen ({type(exc).__name__}: {exc})"


# --- Abdeckung der Änderungsmenge (Issue #259) ---

DEGRADED_BASE_NOTE = (
    "Basis nur HEAD — kein `base_commit` und kein `origin/main`; "
    "bereits committete Änderungen sind nicht erfasst"
)
_UNCOVERED_LIMIT = 10
# Namensliste NUL-getrennt (Nicht-ASCII-Pfade kommen sonst C-gequotet), ohne Loeschungen.
DIFF_NAMES = ("-z", "--name-only", "--diff-filter=d")


class ChangeSetError(Exception):
    """git-Fehler in einem gueltigen Arbeitsbaum — fail-closed (#259 §6)."""


def coverage_gate_enabled() -> bool:
    """Kill-Switch (#259 §11): nur ein ausdrueckliches `enabled: false` schaltet ab.

    Fehlender Schluessel, Tippfehler oder kaputte Config lassen das Gate an.
    Umschliesst nur Abdeckung und Teilstaging — nicht #253 und nicht F002–F004.
    """
    try:
        from config_loader import load_config
        section = load_config().get("adversary_coverage_gate", {})
    except Exception:
        return True
    return not (isinstance(section, dict) and section.get("enabled") is False)


def display_path(path: str) -> str:
    """Form fuer 'Code reference:': relativ zu _hash_root(), wenn darunter, sonst absolut."""
    rel = os.path.relpath(path, os.path.realpath(_hash_root()))
    return path if rel == os.pardir or rel.startswith(os.pardir + os.sep) else Path(rel).as_posix()


def _uncovered_files(artifact: Path, changed_files: "list[str]") -> "list[str]":
    """Dateien der Änderungsmenge, die der letzte Hash-Block nicht bindet (#259 §7)."""
    scan = _strip_fenced_code_blocks(artifact.read_text(errors="replace"))
    entries = _parse_examined_files_section(scan) or []
    covered = {os.path.realpath(_resolve_hash_path(rel)) for _hash, rel in entries}
    return [f for f in changed_files if f not in covered]


def _uncovered_reason(missing: "list[str]") -> str:
    shown = ", ".join(f"`{display_path(f)}`" for f in missing[:_UNCOVERED_LIMIT])
    extra = len(missing) - _UNCOVERED_LIMIT
    more = f" (+{extra} weitere)" if extra > 0 else ""
    return (
        f"Dialog-Nachweis deckt die Änderung nicht ab — nicht zitiert und gehasht: {shown}{more}. "
        "Weg: Dialog erneut führen, jede Datei aus `adversary_dialog.py required-files` "
        "per `Code reference:` zitieren, danach `stamp`"
    )


def run_git(args: "list[str]", cwd, probe: bool = False) -> "str | None":
    """`git <args>` in `cwd`. probe=True: Fehlschlag = strukturelles Fehlen → None.

    Sonst ist jeder Fehlschlag ein ChangeSetError, der den Befehl nennt —
    fail-closed, denn der Aufrufer hat den Arbeitsbaum bereits als gueltig erkannt.
    """
    cmd = " ".join(["git", *args])
    try:
        proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                              encoding="utf-8", errors="surrogateescape", timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        if probe:
            return None
        raise ChangeSetError(f"Änderungsmenge nicht ermittelbar (`{cmd}`: `{type(exc).__name__}: {exc}`)")
    if proc.returncode == 0:
        return proc.stdout
    if probe:
        return None
    detail = (proc.stderr.strip().splitlines() or [f"Exit {proc.returncode}"])[-1]
    raise ChangeSetError(f"Änderungsmenge nicht ermittelbar (`{cmd}`: `{detail}`)")


def _has_repo_marker(root) -> bool:
    """Liegt `root` in einem Git-Repository? Dateisystem-Befund statt git-Ausgabe (F102).

    Auf `root` oder einem Vorfahren: Verzeichnis `.git` mit `HEAD` oder Datei `.git`
    mit `gitdir: <pfad>` (relativ zu ihrem Ordner), dessen Ziel `HEAD` enthaelt
    (Worktree, Submodul); ebenso ein gesetztes GIT_DIR.
    """
    if os.environ.get("GIT_DIR"):
        return True
    start = Path(root).resolve()
    for d in (start, *start.parents):
        dot = d / ".git"
        try:
            lines = dot.read_text(errors="replace").splitlines() if dot.is_file() else []
            target = next((ln[7:].strip() for ln in lines if ln.startswith("gitdir:")), "")
            if ((d / target) if target else dot).joinpath("HEAD").is_file():
                return True
        except OSError:
            return True  # nicht pruefbar: fail-closed wie ein vorhandener Marker
    return False


def git_toplevel(root) -> "str | None":
    """Physischer Toplevel des Arbeitsbaums um `root`; None ohne Git-Repository.

    Alle Namenslisten laufen mit cwd = Toplevel: `git diff` liefert Pfade immer
    toplevel-relativ, `git ls-files` dagegen cwd-relativ (#259 §2). Scheitert
    `rev-parse`, entscheidet der Repo-Marker (F102): mit Marker ist es ein
    git-Fehler (ChangeSetError, fail-closed), ohne Marker kein Repository.
    """
    try:
        out = run_git(["rev-parse", "--show-toplevel"], root).strip()
        if not out:
            raise ChangeSetError(
                "Änderungsmenge nicht ermittelbar (`git rev-parse --show-toplevel`: leere Ausgabe)")
    except ChangeSetError:
        if _has_repo_marker(root):
            raise
        return None
    return os.path.realpath(out)


def git_names(args: "list[str]", top: str) -> "list[str]":
    """Rohe, NUL-getrennte git-Namensliste (toplevel-relativ); Fehler → ChangeSetError."""
    return [n for n in run_git(args, top).split("\0") if n]


def code_files(names: "list[str]", top: str) -> "list[str]":
    """Code-Dateien (is_gated_code_path auf dem git-Pfad) als realpath-absolute Pfade."""
    return [os.path.realpath(os.path.join(top, n)) for n in names if is_gated_code_path(n)]


def git_code_files(args: "list[str]", top: str) -> "list[str]":
    return code_files(git_names(args, top), top)


def _phase8_base(wf: dict, top: str) -> "tuple[str | None, str]":
    """Basis der Phase-8-Menge (#259 §5): der juengere gueltige Vorfahre von HEAD.

    base_commit (S) gewinnt, wenn er Vorfahre von HEAD ist und merge-base(origin/main,
    HEAD) (M) fehlt oder Vorfahre von S ist; sonst M. Rueckfall: nur HEAD (degradiert),
    ohne HEAD None (Index plus untrackte Dateien).
    """
    def holds(*args: str) -> bool:
        return run_git(list(args), top, probe=True) is not None

    if not holds("rev-parse", "--verify", "-q", "HEAD"):
        return None, "Basis: kein HEAD — Index und untrackte Dateien zählen"
    m = (run_git(["merge-base", "origin/main", "HEAD"], top, probe=True) or "").strip()
    s = str(wf.get("base_commit") or "").strip()
    if (s and not s.startswith("-") and holds("merge-base", "--is-ancestor", s, "HEAD")
            and (not m or holds("merge-base", "--is-ancestor", m, s))):
        return s, f"Basis: base_commit {s}"
    if m:
        return m, f"Basis: merge-base(origin/main, HEAD) {m}"
    return "HEAD", DEGRADED_BASE_NOTE


def phase8_code_files(wf: dict) -> "tuple[list[str] | None, str]":
    """Phase-8-Änderungsmenge (#259 §5): (Code-Dateien realpath-absolut, Basis-Info).

    Arbeitsbaum gegen die Basis plus untrackte Dateien, ohne Loeschungen. None statt
    Liste: kein Git-Arbeitsbaum — die Abdeckungspruefung entfaellt. Wirft
    ChangeSetError bei einem git-Fehler im gueltigen Arbeitsbaum.
    """
    top = git_toplevel(_hash_root())
    if top is None:
        return None, "kein Git-Arbeitsbaum — Abdeckungsprüfung entfällt"
    base, info = _phase8_base(wf, top)
    untracked = ["ls-files", "-z", "--others", "--exclude-standard"]
    if base is None:
        files = git_code_files([*untracked, "--cached"], top)
    else:
        files = git_code_files(["diff", *DIFF_NAMES, base, "--"], top) + git_code_files(untracked, top)
    return sorted(set(files)), info


def _cmd_required_files() -> int:
    """CLI `required-files` (#259 §12): Phase-8-Menge auf stdout, Basis auf stderr.

    Rein lesend und unabhaengig vom Kill-Switch: zeigt, was Phase 8 bei aktivem
    Gate prueft. Exit 1 ohne aktiven Workflow oder bei einem git-Fehler.
    """
    name = resolve_active_workflow()[0]
    state = find_project_root() / ".claude" / "workflows" / f"{name}.json"
    try:
        wf = json.loads(state.read_text()) if name else None
    except (OSError, ValueError):
        wf = None
    if not isinstance(wf, dict):
        print("Kein aktiver Workflow mit lesbarem State (workflow.py start/switch).", file=sys.stderr)
        return 1
    try:
        files, info = phase8_code_files(wf)
    except ChangeSetError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(info, file=sys.stderr)
    for path in files or []:
        print(display_path(path))
    return 0


def scaffold_dialog_artifact(workflow_name: str, spec_path: str) -> str:
    """Formal korrektes, inhaltlich leeres Dialog-Geruest (#278) — Quelle des Formats."""
    checklist = create_checklist(parse_spec_expected_behavior(spec_path))
    lines = [
        f"# Adversary Dialog — {workflow_name}",
        f"Spec: {spec_path}",
        f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Checkliste",
        *[f"- [ ] {item['description']}" for item in checklist],
        "",
        "## Dialog",
        "",
    ]
    for i in range(1, MIN_ROUNDS + 1):
        lines += [f"### Runde {i}", "**Adversary:**", "**Implementierer:**", ""]
    lines += [
        PRECONDITION_SECTION, "",
        "<!-- vom Prüfer auszufüllen, siehe `precondition_origins.py` -->", "",
    ]
    lines += ["## Verdict", ""]
    return "\n".join(lines)


def print_finding_schema():
    """Gibt das Finding-Schema aus (fuer Referenz)."""
    print("Structured Finding Schema:")
    print("  {")
    print('    "id": "F001",')
    print('    "severity": "CRITICAL | HIGH | MEDIUM | LOW",')
    print('    "category": "spec_violation | edge_case | regression | security | anti_pattern",')
    print('    "description": "What is the problem",')
    print('    "evidence": "file:line or test output or screenshot path",')
    print('    "remediation": "Suggested fix"')
    print("  }")
    print()
    print(f"Verdicts: {', '.join(VERDICTS)}")
    print(f"Circuit Breaker: max {MAX_ITERATIONS} iterations")
    print(f"Min Rounds: {MIN_ROUNDS}")


def _cmd_risk() -> int:
    """Auskunft zur Risikostufe (#342); kein Gate, Exit-Code immer 0."""
    from hook_utils import adversary_risk_report
    report = adversary_risk_report()
    print(f"Risiko: {report['risk']}")
    print(f"Grund: {report['reason']}")
    print(f"Dateien: {report['files']}")
    print(f"Geforderte Runden: {required_rounds()}")
    return 0


def main():
    """CLI-Einstiegspunkt."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 adversary_dialog.py parse <spec-path>")
        print("  python3 adversary_dialog.py scaffold <workflow-name> <spec-path>")
        print("  python3 adversary_dialog.py validate <artifact-path>")
        print("  python3 adversary_dialog.py stamp <artifact-path>")
        print("  python3 adversary_dialog.py required-files")
        print("  python3 adversary_dialog.py risk")
        print("  python3 adversary_dialog.py schema")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "parse":
        if len(sys.argv) < 3:
            print("Error: spec-path required")
            sys.exit(1)
        spec_path = sys.argv[2]
        points = parse_spec_expected_behavior(spec_path)
        if not points:
            print("Keine Expected-Behavior-Punkte gefunden.")
            sys.exit(0)
        print(f"{len(points)} Expected-Behavior-Punkte gefunden:")
        for i, p in enumerate(points, 1):
            print(f"  {i}. {p}")

    elif cmd == "scaffold":
        if len(sys.argv) < 4:
            print("Error: workflow-name and spec-path required")
            sys.exit(1)
        print(scaffold_dialog_artifact(sys.argv[2], sys.argv[3]), end="")

    elif cmd == "validate":
        if len(sys.argv) < 3:
            print("Error: artifact-path required")
            sys.exit(1)
        artifact_path = sys.argv[2]
        valid, message = validate_dialog_artifact(artifact_path)
        print(message)
        sys.exit(0 if valid else 1)

    elif cmd == "stamp":
        if len(sys.argv) < 3:
            print("Error: artifact-path required")
            sys.exit(1)
        artifact_path = sys.argv[2]
        ok, message = stamp_dialog_artifact(artifact_path)
        print(message)
        sys.exit(0 if ok else 1)

    elif cmd == "required-files":
        sys.exit(_cmd_required_files())

    elif cmd == "risk":
        sys.exit(_cmd_risk())

    elif cmd == "schema":
        print_finding_schema()

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
