# Context: feat-640-auslieferung-schneller

## Request Summary
PO 2026-11-21 nach #637: „Das ist jetzt aber auch nicht wirklich schnell.“ und „Das hast du doch nach der letzten Version schon gesagt! Was läuft falsch?“ Die Strecke vom fertigen Fix bis zur veröffentlichten Version soll nur noch einen kurzen Testlauf brauchen (#640).

## Befund (gemessen)
- #637: Fix-PR #638 `tests` 19:42:04–19:53:57 (≈12 min), Release-PR #639 `tests` 19:55:20–20:04:45 (≈9,5 min), Veröffentlichung danach 11 s. Gesamtstrecke ab PR ≈ 23 min, davon ≈ 21,5 min zwei Testläufe.
- Die Suite läuft seriell: `.github/workflows/ci.yml` `python3 -m pytest tests/ -q`; Rückfall in `scripts/release_check.py:256` ebenso.
- Probe parallel lokal (4 Kerne, `pytest -n 4`, pytest-xdist): **3935 passed, 30 skipped in 192 s** (seriell zuletzt 708 s), ohne Fehler. GitHub-Runner `ubuntu-latest` haben 4 vCPUs.
- Regel „keine Versionsnummer in Fix-/Feature-PRs, Release als eigener PR“: `CLAUDE.md:20`, `CLAUDE.md:371`, `docs/arbeitsweise.md:77–86`. Der zweite PR ändert nur Versionstexte, kostet aber einen vollen Testlauf.
- `release-readiness` (`release_check.py --pr-gate`) prüft einen Bump schon im PR; der Nachweis aus #633 (`--tested-proof`) greift auch, wenn der Bump im Fix-PR steckt (PR-Head-Baum = Merge-Baum).

## Related Files
| File | Relevance |
|------|-----------|
| `.github/workflows/ci.yml` | `tests`-Job: Installation + Suite seriell |
| `scripts/release_check.py` | Rückfall-Suite (Z. 256) im Release ohne Nachweis |
| `CLAUDE.md`, `docs/arbeitsweise.md` | Regel zum getrennten Release-PR |
| `core/commands/60-validate.md` (+ generiert `skills/60-validate/SKILL.md`) | Auto-Ship-Anleitung; nennt den Ablauf nach Phase 8 |

## Analyse
**Variante A (empfohlen):** (1) Suite parallel über pytest-xdist (`-n auto`) in CI und im Release-Rückfall; xdist als Abhängigkeit in CI installieren. Rückfall seriell, falls xdist fehlt (lokal ohne Plugin). (2) Bei Einzel-Auslieferung kommt der Versions-Bump in den Fix-/Feature-PR; ein getrennter Release-PR nur beim Bündeln mehrerer Issues. Ergebnis: ein Testlauf ≈ 3–4 min, Veröffentlichung ≈ 15 s.

**Alternative B:** Tests in Release-PRs, die nur Versionstexte ändern, überspringen. Verworfen: Der Release-Nachweis (#633) braucht einen grünen `tests`-Check auf dem PR-Head, sonst fällt der Release auf die volle Suite zurück; spart nichts.

**Alternative C:** Suite auf mehrere CI-Jobs verteilen (Matrix-Shards). Verworfen für jetzt: mehr Konfiguration, Job-Start-Overhead je Shard; xdist erreicht den Großteil mit einer Zeile. Würde C gewählt, fiele eine ADR zur Sharding-Strategie.

**ADR:** keine neue Architektur (Testausführung und Prozessregel).

## Risks & Considerations
- Testisolation unter Parallelität: Lauf 1 grün; DoD verlangt 3 Läufe ohne Flake (lokal + CI).
- Tests, die globale Zustände ändern (`TZ`/`time.tzset`, CWD, Env), laufen je Worker in eigenem Prozess; xdist trennt Prozesse, nicht Dateien im Repo. Tests mit festen Pfaden im Repo wären anfällig; Lauf 1 zeigte keine.
- Regeländerung muss in allen Doku-Stellen konsistent sein; `skills/` per `sync_skills.py`.
