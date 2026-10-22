# Fixture-Kopie fuer tests/test_evidence_gate_447.py (#447), unveraendert uebernommen aus
# henemm/loose-ends scripts/sim_proof.py @ b9bd75216dcf3f40e1874d005688163d31cae45b
# (Inhalt ab dem Docstring: sha256 1e51ecc8c081329a65de0cf27940164fb0a57542f7e32b711ea61d1de5a7568b,
# gegen `gh api .../contents/scripts/sim_proof.py?ref=b9bd752...` geprueft). Nicht von Hand anpassen.
"""Simulator-Beleg aus einem eigenen `sim.sh test-proof`-Lauf schreiben (#145, Schnitt 1).

Aufruf (nur aus sim.sh): sim_proof.py <workflow> <testklasse> <xcresult> <endzeile> <befehl> <xcodebuild-exit>
Nur Standardbibliothek. Reine Funktionen oben, I/O (git, xcresulttool, Dateien) in main().
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Spiegel von is_gated_code_path im Plugin agent-os-openspec
# (core/hooks/hook_utils.py:694-733, Version 3.34.0, Vorgabelisten ohne config-Override).
# Ändert das Plugin die Regel, muss sie hier gleich mitziehen.
CODE_EXTENSIONS = {
    ".swift", ".kt", ".java", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".cpp", ".c", ".h", ".hpp", ".rb", ".php", ".cs",
}
ALWAYS_ALLOWED_DIRS = [
    "Tests/", "UITests/", "Test/", "test/", "__tests__/", "tests/",
    "spec/", "docs/", ".claude/commands/", "scripts/", "tools/",
]
ALWAYS_ALLOWED_PATTERNS = [
    r"\.md$", r"\.txt$", r"\.json$", r"\.yaml$", r"\.yml$",
    r"\.toml$", r"\.gitignore$", r"README", r"CHANGELOG", r"LICENSE",
]

UNKNOWN = "unbekannt"
COUNTS = {"gesamt": "totalTestCount", "bestanden": "passedTests",
          "fehlgeschlagen": "failedTests", "uebersprungen": "skippedTests"}


def is_gated_code_path(path):
    parts = set(Path(path).parts)
    if any(d.rstrip("/") in parts for d in ALWAYS_ALLOWED_DIRS):
        return False
    if any(re.search(p, path, re.IGNORECASE) for p in ALWAYS_ALLOWED_PATTERNS):
        return False
    return Path(path).suffix.lower() in CODE_EXTENSIONS


def parse_summary(summary, xcodebuild_exit):
    """Felder aus `xcresulttool get test-results summary`; Fehlendes bleibt `unbekannt`."""
    out = {key: summary.get(field, UNKNOWN) for key, field in COUNTS.items()}
    out["start"] = summary.get("startTime", UNKNOWN)
    out["ende"] = summary.get("finishTime", UNKNOWN)
    devices = summary.get("devicesAndConfigurations") or [{}]
    device = devices[0].get("device") or {}
    if str(device.get("platform", "")).startswith("watchOS") and "modelName" in device and "osVersion" in device:
        # #409: for a watch simulator xcresult reports the paired iPhone as deviceName.
        out["geraet"] = f"{device['modelName']}, watchOS {device['osVersion']}"
    elif "deviceName" in device and "osVersion" in device:
        out["geraet"] = f"{device['deviceName']}, iOS {device['osVersion']}"
    else:
        out["geraet"] = UNKNOWN
    result = summary.get("result")
    if result not in ("Passed", "Failed") or UNKNOWN in out.values():
        out["ergebnis"] = "Unbekannt"
    elif result == "Passed" and xcodebuild_exit == 0 and out["gesamt"] >= 1:
        out["ergebnis"] = "Passed"
    else:
        out["ergebnis"] = "Failed"
    return out


def format_proof(header, files):
    lines = ["# Simulator-Beleg"] + [f"{k}: {v}" for k, v in header.items()]
    lines += ["", "## Geprüfte Dateien"]
    lines += [f"- sha256:{sha}  {path}" for sha, path in files] or ["(keine Code-Dateien geändert)"]
    return "\n".join(lines) + "\n"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def changed_code_files(base):
    names = git("diff", "--name-only", "--diff-filter=d", "-z", base).split("\0")
    names += git("ls-files", "--others", "--exclude-standard", "-z").split("\0")
    return sorted({n for n in names if n and is_gated_code_path(n)})


def read_summary(bundle, out_dir):
    """Liest die summary aus dem Bündel und legt sie wörtlich als summary.json ab."""
    if not bundle.is_dir():
        return {}, "fehlt (kein Ergebnisbündel)"
    raw = subprocess.run(["xcrun", "xcresulttool", "get", "test-results", "summary", "--path", str(bundle),
                          "--compact"], capture_output=True, text=True, check=True).stdout
    target = out_dir / "summary.json"
    target.write_text(raw)
    return json.loads(raw), f"{target.relative_to(ROOT)}  sha256:{sha256(target)}"


def export_screenshots(bundle, out_dir):
    if bundle.is_dir():
        subprocess.run(["xcrun", "xcresulttool", "export", "attachments", "--path", str(bundle),
                        "--output-path", str(out_dir), "--filter", "*.png"], capture_output=True, check=True)
    return len(list(out_dir.glob("*.png")))


def write_atomic(path, text):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".simulator-run.")
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
    os.replace(tmp, path)


def main(argv):
    workflow, testklasse, bundle, endzeile, befehl, exit_code = argv
    art = ROOT / "docs" / "artifacts" / workflow
    out_dir, bundle = art / "simulator-run", ROOT / bundle
    out_dir.mkdir(parents=True, exist_ok=True)
    summary, summary_line = read_summary(bundle, out_dir)
    s = parse_summary(summary, int(exit_code))
    shots = export_screenshots(bundle, out_dir)
    base = git("merge-base", "origin/main", "HEAD").strip()
    rel = out_dir.relative_to(ROOT)
    header = {
        "erzeugt": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "befehl": befehl, "workflow": workflow,
        "head": git("rev-parse", "HEAD").strip(), "basis": f"{base} (merge-base origin/main HEAD)",
        "testklasse": testklasse, "ergebnis": s["ergebnis"], "xcodebuild": endzeile,
        "tests": f"{s['gesamt']} gesamt, {s['bestanden']} bestanden, {s['fehlgeschlagen']} fehlgeschlagen, "
                 f"{s['uebersprungen']} übersprungen",
        "start": f"{s['start']}  ende: {s['ende']}", "geraet": s["geraet"], "summary": summary_line,
        "xcresult": f"{rel}/run.xcresult  (gitignored)", "screenshots": f"{rel}/*.png ({shots} Stück)",
    }
    files = [(sha256(ROOT / p), p) for p in changed_code_files(base)]
    write_atomic(art / "simulator-run.txt", format_proof(header, files))
    if s["ergebnis"] != "Passed":
        print(f"[sim_proof] ergebnis: {s['ergebnis']}", file=sys.stderr)
        return 1
    if shots < 1:
        print("[sim_proof] Testklasse liefert keinen Screenshot, Beleg ungültig", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
