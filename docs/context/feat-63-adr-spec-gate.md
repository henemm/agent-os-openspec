# Context: feat-63-adr-spec-gate

## Request Summary

Issue #63: Die ADR-Reflexionsprüfung (Stufe 1 des Zwei-Stufen-ADR-Enforcements) fehlt im
Framework-Core. Beim Übergang Phase 3→4 (Spec-Freigabe) soll erzwungen werden, dass eine
Spec-Sektion `## Architektur-Entscheidung (ADR)` bewusst ausgefüllt ist (ADR-Nummer **oder**
begründetes "keine"), bevor die Freigabe erlaubt wird — analog zum etablierten `spec_approved`-Gate.
Betrifft alle Plugin-Konsumenten, daher gehört der Fix ins Core, nicht in ein Consumer-Projekt.

## Kritischer Befund (Design-relevant, weicht vom Issue-Vorschlag ab)

Das Issue schlägt vor, `_validate_transition` bei der 3→4-Transition zu erweitern. **Das allein
greift im Normalbetrieb nicht.**

Der reale Phase-3→4-Übergang läuft über den **Keyword-Approval-Handler** in
`core/hooks/phase_listener.py:225–236`: Wenn der User "approved"/"freigabe"/"lgtm" sagt, setzt
der Handler direkt `spec_approved = True` und `current_phase = "phase4_approved"` — **ohne
`_validate_transition` aufzurufen**. `_validate_transition` wird nur von `cmd_phase` (workflow.py:603)
und `cmd_complete` (:754) genutzt.

→ Ein ADR-Gate, das nur in `_validate_transition` sitzt, wird durch das automatische Approval-Keyword
umgangen. Die Prüfung muss **an beiden Stellen** greifen (oder über einen gemeinsamen Helfer geteilt
werden): im `phase_listener.py`-Approval-Pfad **und** in `_validate_transition`.

## Related Files

| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py:400–454` | `_validate_transition` — kumulative Schwellen-Gates. `phase4_approved`-Gate an **zwei** Stellen: Standard-`feature` (433–437) + `feature-fast` (411–415). Hier ADR-Check ergänzen. |
| `core/hooks/workflow.py:354–374` | `_new_workflow` — State-Schema. Ggf. neuer Default-Key (z.B. `adr_reflected`) hier. |
| `core/hooks/workflow.py:70–81` | `PHASES`-Liste (Reihenfolge, Index-Schwellen). |
| `core/hooks/workflow.py:623–635` | `cmd_set_field` — generischer Setter; so kommt `spec_file` in den State (kein dedizierter Command). |
| `core/hooks/phase_listener.py:225–236` | **Kritisch:** Keyword-Approval-Pfad 3→4, umgeht `_validate_transition`. Zweiter Einhängepunkt. |
| `docs/specs/_template.md` | Vom write-spec-Flow gelesenes Template. **Enthält aktuell KEINE ADR-Sektion** → muss ergänzt werden, sonst blockt das Gate jede neue Spec. |
| `templates/spec_template.md` | Alternatives Template (mit AC-Sektion), ebenfalls ohne ADR. |
| `core/agents/spec-writer.md:45–120` | Definiert die vom Sonnet-Agent geschriebenen Spec-Sektionen. ADR muss hier ergänzt werden, damit Specs die Sektion überhaupt bekommen. |
| `core/agents/spec-validator.md:37–43` | "Required Sections" — ADR ggf. hier aufnehmen. |
| `skills/30-write-spec/SKILL.md` | write-spec-Ablauf; setzt `spec_file`, triggert Approval. |
| `tests/test_gate_fixes_26_38_34.py:200–262` | **Test-Vorbild:** `_run_phase`-Helper (Subprozess `workflow.py phase <target>`) + `_make_verdict_workflow`-Fixture. Muster für Adversary-Gate → analog für ADR-Gate. |
| `tests/test_phase_listener_keyword_guard.py` | Testet den Keyword-Approval-Pfad (3→4). Relevant für den zweiten Einhängepunkt. (Hinweis: `secrets_guard` blockt aktuell das Lesen wg. Dateiname "guard" — separat prüfen.) |

## Existing Patterns

- **Kumulative Gate-Schwellen:** Alle Gates in `_validate_transition` folgen dem Muster
  `if tgt_idx >= PHASES.index("<phase>"): if not <state-key>: return "<Fehlermeldung>"`.
  Ein ADR-Gate fügt sich als weiterer Block bei `phase4_approved` ein.
- **Doppelte Gate-Pflege:** Das `spec_approved`-Gate existiert bewusst 2x (feature-fast + standard).
  Ein neues Gate muss überlegen, ob es für beide Tracks gilt.
- **gregor_zwanzig Referenz-Design (Issue #885, Stufe 2):** Prüfkriterium ist bewusst tolerant —
  Sektion `## Architektur-Entscheidung (ADR)` vorhanden UND Body enthält `ADR-<n>` **oder**
  `keine`/`none`. Kein Ja/Nein-Feld; stattdessen zwei Bullets:
  `- **ADR-Nr.:** [ADR-NNNN oder "keine"]` + `- **Rationale:** ...`.
- **Grandfathering (gregor):** Nur Specs mit `created >= 2026-06-25` unterliegen dem Spec-Gate;
  ältere sind ausgenommen. Verankert in `docs/adr/README.md`, nicht im Guard-Code.
- **Kein ENV-/globaler Bypass by design (gregor):** Einziger Ausweg ist die bewusste Verneinung
  in der Spec selbst ("keine" mit Rationale).

## Dependencies

- **Upstream (was das Gate nutzt):** `data["spec_file"]` (Pfad zur Spec-Datei), Dateisystem-Read
  der Spec, `PHASES`-Index. Für Grandfathering ggf. `data["created"]`.
- **Downstream (was betroffen ist):** Jeder Plugin-Konsument, der den 8-Phasen-Feature-Workflow
  fährt. Bei zu striktem Default würde das Gate **alle** neuen Specs blocken (auch die des Frameworks
  selbst — das Framework nutzt seinen eigenen Workflow).

## Existing Specs (Framework)

- `docs/specs/_template.md` — kanonisches Template, **ohne** ADR-Sektion.
- Keine bestehende Framework-Spec nutzt eine `## Architektur-Entscheidung (ADR)`-Sektion. Am
  nächsten: informelle `## Architektur-Notiz`-Prosa in `session-singleton-guard.md:253`,
  `user-initiated-bug-workflow.md:143` — kein strukturiertes ADR-Feld.
- **Das Framework hat aktuell KEINE ADR-Infrastruktur:** kein `docs/adr/`-Verzeichnis, kein
  `adr_guard.py`, keine ADR-Konventions-Doku. Issue #63 fokussiert bewusst nur auf Stufe 1
  (Spec-Gate). Stufe 2 (Commit-Gate) existiert nur im Consumer `gregor_zwanzig`.

## Referenz-Artefakte (gregor_zwanzig, Consumer)

- `/home/hem/gregor_zwanzig/docs/specs/modules/issue_885_adr_enforcement.md` — Original-Spec des
  Zwei-Stufen-Designs. Stufe-2-Prüftext (Z. 79–83): Sektion vorhanden UND `ADR-<n>` ODER `keine`/`none`.
- `/home/hem/gregor_zwanzig/docs/adr/README.md` — ADR-Konventionen, Grandfathering-Grenze, Enforcement-Beschreibung.
- `/home/hem/gregor_zwanzig/.claude/hooks/adr_guard.py` — Commit-Gate (Stufe 2), reine Funktion
  `check(staged_files, commit_message, config) -> str | None`.
- `/home/hem/gregor_zwanzig/docs/specs/_template.md:69–72` — kanonische ADR-Sektion (Bullet-Format).

## Risks & Considerations

1. **Bypass-Falle (höchstes Risiko):** Gate nur in `_validate_transition` verfehlt den realen
   Approval-Pfad (`phase_listener.py`). Muss an beiden Stellen greifen. Sonst ist das Feature ein
   No-Op im Normalbetrieb — genau der Fehler, den das Issue vermeiden will.
2. **Selbstblockade des Frameworks:** Ohne ADR-Sektion im Template + spec-writer blockt das Gate
   jede neue Spec (inkl. dieser Spec hier). Template + Agent-Definition müssen mitgezogen werden,
   sonst ist der Feature-Workflow des Frameworks selbst blockiert.
3. **Grandfathering / Rückwärtskompatibilität:** Bestehende Specs ohne ADR-Sektion dürfen nicht
   blockiert werden. Braucht eine Ausnahmeregel (Datum-basiert wie gregor, oder: Gate greift nur,
   wenn die Sektion existiert aber leer ist — "opt-in per Vorhandensein").
4. **Konfigurierbarkeit / Opt-in:** Nicht jedes Consumer-Projekt pflegt ADR-Kultur. Ein hart
   erzwungenes Gate könnte Projekte ohne ADR-Konvention brechen. Design-Frage: Default-an mit
   Grandfathering, oder config-gesteuert (`openspec.yaml`)?
5. **Prüfkriterium festlegen:** Was zählt als "ausgefüllt"? gregor-Kriterium (`ADR-<n>` ODER
   `keine`/`none` im Sektions-Body) übernehmen — tolerant, aber verhindert leere Platzhalter wie
   `[ADR-NNNN oder "keine"]`. Platzhalter-Erkennung nötig, damit unausgefüllte Templates blocken.
6. **Doppelter Gate-Pfad:** feature-fast vs. standard — gilt das ADR-Gate für beide? (Fast Track
   hat bewusst reduzierte Gates.)
7. **Override-Token:** Soll der bestehende Override-Mechanismus das ADR-Gate umgehen dürfen, oder
   ist es (wie gregor) bewusst bypass-frei?

## Analysis

### Type
Feature (neues Workflow-Gate im Framework-Core).

### Technischer Ansatz (empfohlen — bestätigt durch Plan/Sonnet-Bewertung)

**Geteilter Helfer + zwei Einhängepunkte.** Ein Gate nur in `_validate_transition` ist im Alltag
ein No-Op (siehe kritischer Befund oben).

- **Helfer `_check_adr(data) -> str | None`** in `workflow.py`, neben `_validate_transition`.
  Reine, testbare Funktion. Rückgabe: Fehlermeldung oder `None`.
- **Einhängepunkt A** — `_validate_transition`: im `phase4_approved`-Block nach dem `spec_approved`-Check
  (Standard-feature nach Z.437; feature-fast nach Z.415). Deckt `cmd_phase` + `cmd_complete` ab.
- **Einhängepunkt B** — `phase_listener.py:225–236` (der reale Approval-Pfad): vor `spec_approved = True`.
  Import via `from workflow import _check_adr` (analog zum bestehenden `_log_phase_transition`-Import).
  In `try/except`, **lenient-on-error** — der Hook muss den Exit-0-Vertrag wahren. Bei ADR-Fehler wird
  `spec_approved` schlicht nicht gesetzt + klare stderr-Meldung; der nachfolgende `/40-tdd-red` blockt
  dann zusätzlich über Einhängepunkt A (Belt-and-suspenders).
- **Spec-Pfad auflösen** relativ zum Projekt-Root (`find_project_root() / data["spec_file"]`, Muster
  `edit_gate.py:167`); Worktree-Root beachten (`phase_listener.py:164`). Lese-/Existenzfehler → lenient.

### Prüfkriterium (KRITISCH — weicht bewusst von gregor ab)

**Neuer Befund:** Der gregor-Platzhalter `- **ADR-Nr.:** [ADR-NNNN oder "keine"]` enthält bereits das
Wort „keine" UND das Muster „ADR-N…". Ein **naiver Substring-Test** (wie in gregor issue_885 Z.81–83)
würde den **unausgefüllten Platzhalter fälschlich durchwinken** — das Feature wäre wirkungslos.

Korrekte Regel in `_check_adr`:
1. Heading `## Architektur-Entscheidung (ADR)` finden, Body bis zum nächsten `## ` extrahieren.
2. **Bracket-Platzhalter zuerst entfernen:** `re.sub(r"\[[^\]]*\]", "", body)`.
3. Auf dem Rest (lowercased): `re.search(r"adr-\d+", rest)` ODER `re.search(r"\bkeine\b|\bnone\b", rest)`.
4. Kein Treffer → block. Fehlt die Sektion ganz → `None` (Grandfathering, s.u.).

Damit: `ADR-0001` ✅, ausgefülltes `keine` ✅, Platzhalter `[ADR-NNNN oder "keine"]` ❌.

### Grandfathering / Opt-in: präsenzbasiert (Option a)

`_check_adr` gibt `None`, wenn die Sektion **fehlt**; blockt nur, wenn Sektion **vorhanden aber
leer/Platzhalter**. Vorteile: Alt-Specs ohne Sektion → automatisch grandfathered; Consumer ohne
ADR-Kultur (Template ohne Sektion) → nie geblockt; kein Datums-Cutoff, kein State-Key, minimal breaking.
Datumsbasiertes Grandfathering (gregor) verworfen — für heterogene Consumer bedeutungslos.
Optional: `adr_gate.enabled`-Toggle in `config.yaml` als expliziter Kill-Switch (config_loader existiert,
config.yaml hat bereits Gate-Sektionen wie `adversary_gate:`).

### Atomarer Template-/Agent-Mitzug (Pflicht, sonst Selbstblockade)

Der Feature-Workflow schreibt Specs über das **inline-Template in `spec-writer.md:45–106`**, NICHT nur
über `docs/specs/_template.md`. Beide + Validator müssen im selben Change:
1. **`core/agents/spec-writer.md`** (kritischste Datei): ADR-Sektion ins emittierte Template + Regel.
2. **`docs/specs/_template.md`**: ADR-Sektion (manuelles Authoring / Konsistenz).
3. **`core/agents/spec-validator.md`**: ADR in „Required Sections" + Platzhalter-Erkennung (fängt leere
   ADR vor der Freigabe → bessere UX als harter Transition-Block; Defense-in-depth).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | `_check_adr`-Helfer (~25 LoC) + Call-Sites in beiden phase4-Blöcken (~6 LoC) |
| `core/hooks/phase_listener.py` | MODIFY | ADR-Check im Approval-Block (~8 LoC), lenient-on-error |
| `core/agents/spec-writer.md` | MODIFY | ADR-Sektion ins emittierte Template + Regel (~8 Z.) |
| `docs/specs/_template.md` | MODIFY | ADR-Sektion (~4 Z.) |
| `core/agents/spec-validator.md` | MODIFY | ADR in Required Sections + Platzhalter-Check (~5 Z.) |
| `config.yaml` | MODIFY | optional `adr_gate.enabled`-Toggle (~3 Z.) |
| `tests/test_adr_gate.py` | CREATE | Beide Pfade + Grandfathering + Platzhalter-Block (~80–120 LoC) |

### Scope Assessment
- Files: 6–7
- Estimated LoC: ~150–200 (inkl. Tests)
- Risk Level: **MEDIUM-HIGH** — Gate im kritischen Pfad, alle Consumer betroffen; Hauptrisiken
  Selbstblockade (atomarer Mitzug) und Platzhalter-False-Pass (Bracket-Strip).

### Test-Muster
Neue Datei nach Vorbild `tests/test_gate_fixes_26_38_34.py:200–262` (`_run_phase`-Subprozess-Helper).
Muss abdecken: (i) Approval-Keyword blockt bei leerer/Platzhalter-ADR, (ii) `cmd_phase` blockt,
(iii) `ADR-0001`/`keine` passiert, (iv) Alt-Spec ohne Sektion passiert (Grandfathering),
(v) Platzhalter blockt. Zusätzlich Keyword-Pfad-Test analog `tests/test_phase_listener_keyword_guard.py`.

### Resolved Decisions (User + Tech Lead)
- [x] **Durchsetzung: Standard-an + config-Not-Aus** (User-Entscheidung). ADR-Sektion wird per Default
      in jeder neuen Spec ausgeliefert (`spec-writer.md` + `_template.md`); Gate erzwingt sie
      (präsenzbasiert). Consumer ohne ADR-Kultur schalten via `config.yaml → adr_gate.enabled: false` ab.
- [x] **Config-Kill-Switch:** `adr_gate.enabled` (Default `true`) in `config.yaml` — ja.
- [x] **Fast-Track:** ADR-Gate gilt auch für `feature-fast` (über denselben Helfer) — ja.
- [x] **Override:** bypass-frei wie gregor — kein Override-Anschluss. „keine" mit Rationale ist der
      eingebaute, bewusste Ausweg.
