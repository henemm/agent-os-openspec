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
  python3 adversary_dialog.py validate <artifact-path>
  python3 adversary_dialog.py schema
"""

import re
import sys
import time
from datetime import datetime
from pathlib import Path

from hook_utils import extract_ac_entries

# Circuit Breaker: max iterations before escalation to user
MAX_ITERATIONS = 3

# Minimum dialog rounds before VERIFIED is accepted
MIN_ROUNDS = 2

# Max age of artifact in minutes
MAX_AGE_MINUTES = 60

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
    """Validiert ein Dialog-Artifact.

    Prueft:
    1. Datei existiert
    2. Datei ist < MAX_AGE_MINUTES alt
    3. Alle Checklisten-Punkte sind [x] (abgehakt)
    4. Mindestens MIN_ROUNDS Dialog-Runden dokumentiert
    5. Verdict ist VERIFIED oder AMBIGUOUS (nicht BROKEN)
    6. Circuit Breaker nicht ausgeloest ohne Eskalation

    Returns:
        (valid: bool, message: str)
    """
    path = Path(artifact_path)

    # 1. Existenz
    if not path.exists():
        return False, f"Dialog artifact not found: {artifact_path}"

    # 2. Alter
    age_min = (time.time() - path.stat().st_mtime) / 60
    if age_min > MAX_AGE_MINUTES:
        return False, (
            f"Dialog artifact is {age_min:.0f} min old "
            f"(max {MAX_AGE_MINUTES}). Re-run dialog."
        )

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

    # 3. Checkliste: Alle Punkte muessen [x] sein
    checked = len(re.findall(r"(?m)^- \[x\]", scan, re.IGNORECASE))
    unchecked = len(re.findall(r"(?m)^- \[ \]", scan))

    if unchecked > 0:
        return False, (
            f"{unchecked} Checklisten-Punkt(e) noch offen. "
            "Alle muessen bewiesen sein."
        )

    if checked == 0:
        return False, "Keine Checklisten-Punkte gefunden."

    # 4. Mindestens MIN_ROUNDS Runden
    rounds = len(re.findall(r"(?m)^### Runde \d+", scan))
    if rounds < MIN_ROUNDS:
        return False, (
            f"Nur {rounds} Dialog-Runde(n) dokumentiert. "
            f"Minimum sind {MIN_ROUNDS} Runden."
        )

    # 5. Verdict — bei mehreren Bloecken (Fix-Loop-Runden) zaehlt der LETZTE.
    verdict_matches = list(re.finditer(r"(?m)^## Verdict\s*\n\*\*(.+?)\*\*", scan))
    verdict_match = verdict_matches[-1] if verdict_matches else None
    if not verdict_match:
        return False, "Kein Verdict im Artifact gefunden."

    verdict_text = verdict_match.group(1).strip()

    if verdict_text.startswith("BROKEN"):
        return False, f"Verdict ist '{verdict_text}' — nicht VERIFIED."

    if verdict_text.startswith("AMBIGUOUS"):
        return True, (
            f"Dialog valid (AMBIGUOUS): {checked} Punkte bewiesen, "
            f"{rounds} Runden. User-Review empfohlen."
        )

    if not verdict_text.startswith("VERIFIED"):
        return False, f"Unbekanntes Verdict: '{verdict_text}'"

    return True, (
        f"Dialog valid: {checked} Punkte bewiesen, "
        f"{rounds} Runden, Verdict VERIFIED."
    )


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


def main():
    """CLI-Einstiegspunkt."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 adversary_dialog.py parse <spec-path>")
        print("  python3 adversary_dialog.py validate <artifact-path>")
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

    elif cmd == "validate":
        if len(sys.argv) < 3:
            print("Error: artifact-path required")
            sys.exit(1)
        artifact_path = sys.argv[2]
        valid, message = validate_dialog_artifact(artifact_path)
        print(message)
        sys.exit(0 if valid else 1)

    elif cmd == "schema":
        print_finding_schema()

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
