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
    """Parse a spec file and extract Expected Behavior bullet points.

    Sucht nach einer '## Expected Behavior' Section und extrahiert
    alle Bullet-Points (Zeilen die mit '- ' beginnen) bis zur naechsten
    '## ' Section oder Dateiende.

    Returns:
        Liste von Strings, jeder ein Expected-Behavior-Punkt.
        Leere Liste wenn keine Section gefunden.
    """
    path = Path(spec_path)
    if not path.exists():
        return []

    content = path.read_text(errors="replace")
    lines = content.splitlines()

    in_section = False
    points = []

    for line in lines:
        stripped = line.strip()

        # Section-Start erkennen (case-insensitive)
        if re.match(r"^##\s+Expected Behavior", stripped, re.IGNORECASE):
            in_section = True
            continue

        # Naechste Section beendet Expected Behavior
        if in_section and re.match(r"^##\s+", stripped):
            break

        # Bullet-Points und nummerierte Listen sammeln
        if in_section and (
            re.match(r"^-\s+", stripped) or re.match(r"^\d+\.\s+", stripped)
        ):
            point = re.sub(r"^(-\s+|\d+\.\s+)", "", stripped)
            if point:
                points.append(point)

    return points


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

    # 3. Checkliste: Alle Punkte muessen [x] sein
    checked = len(re.findall(r"- \[x\]", content, re.IGNORECASE))
    unchecked = len(re.findall(r"- \[ \]", content))

    if unchecked > 0:
        return False, (
            f"{unchecked} Checklisten-Punkt(e) noch offen. "
            "Alle muessen bewiesen sein."
        )

    if checked == 0:
        return False, "Keine Checklisten-Punkte gefunden."

    # 4. Mindestens MIN_ROUNDS Runden
    rounds = len(re.findall(r"### Runde \d+", content))
    if rounds < MIN_ROUNDS:
        return False, (
            f"Nur {rounds} Dialog-Runde(n) dokumentiert. "
            f"Minimum sind {MIN_ROUNDS} Runden."
        )

    # 5. Verdict
    verdict_match = re.search(r"## Verdict\s*\n\*\*(.+?)\*\*", content)
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
