# Context: fix-134-approval-marker-binding

## Request Summary
`post_implementation_gate.py` prüft die menschliche Freigabe nur über die Existenz einer leeren
Datei `user_approved_validation_<workflow>`. Ein Marker, der seinen Workflow überlebt (liegt
dauerhaft herum, siehe Issue-Beleg: 9 solcher Dateien im Arbeitsbaum), entsperrt jeden späteren
Workflow desselben Namens beim ersten Code-Edit — ohne dass ein Mensch die neuen Änderungen
gesehen hat. Der Marker muss an den konkreten Prüflauf gebunden werden, nicht an den Namen.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/post_implementation_gate.py` | Liest den Marker (Zeile 134–138: `approval_path.exists()` → sofort `allow()`, keine Inhaltsprüfung). Muss auf Inhaltsvergleich gegen `pending_validation_<name>.json.created` umgestellt werden. |
| `core/hooks/phase_listener.py` (Zeile 484–499, GREEN-Handler) | Schreibt den Marker aktuell per `approval_path.touch()` — leer. Muss stattdessen den `created`-Wert des aktuellen `pending_validation_<name>.json` als Inhalt schreiben. |
| `core/hooks/hook_utils.py` (`log_gate_event`, Zeile 529) | Vorhandene Diagnose-Funktion — für AC-5 nutzen (verworfener Marker geht ins Gate-Event-Log). |
| `core/hooks/workflow.py` (Zeile 1727–1744) | Kennt bereits alle `user_approved_validation_*`-Dateien (für Cleanup-Zwecke) — nicht Teil dieses Fixes, nur zur Kenntnis: das Aufräum-Verhalten selbst ist ein eigenes, begleitendes Issue. |

## Existing Patterns
- **#131** hat exakt dasselbe Problem für den Adversary-Dialog bereits gelöst: die frühere
  Alters-Prüfung ("60 Minuten alt?") wurde durch eine Identitäts-/Übereinstimmungs-Prüfung
  ersetzt (`adversary_dialog.py`, Kommentare bei Zeile 432, 511, 639: "Ersatz für die frühere
  Alters-Prüfung", "Übereinstimmung ist"). Dieser Fix wendet dasselbe Muster an: Bindung an den
  `created`-Wert des lebenden Locks statt an Name oder Uhrzeit.
- `_write_lock()` in `post_implementation_gate.py` schreibt bereits `created` (Unix-Timestamp,
  `time.time()`) in die Lock-Datei — dieser Wert existiert schon, muss nur auch im Marker
  landen und beim Lesen verglichen werden.

## Dependencies
- Upstream: `hook_utils.get_active_workflow_name`, `find_project_root`, `log_gate_event`.
- Downstream: Kein anderer Hook liest `user_approved_validation_*` inhaltlich — nur
  `bash_gate.py` (blockt das *Anlegen* per Bash, unverändert relevant) und `workflow.py`
  (Cleanup, unverändert relevant). Die Inhaltsänderung des Markers (leer → Timestamp-String)
  bricht keine dieser beiden Stellen, da sie nur auf Dateinamen/Existenz reagieren.

## Existing Specs
- Keine bestehende Spec zu `post_implementation_gate` — dies wäre die erste.

## Risks & Considerations
- **Keine Tests vorhanden.** `tests/` enthält keine Datei für `post_implementation_gate.py`
  selbst (nur `test_phase_listener_dropped_approval_90.py` für verwandte, aber andere Logik in
  `phase_listener.py`). Die TDD-RED-Phase legt die erste Testdatei für dieses Modul an.
- **Float-Vergleich:** `created` ist `time.time()` (float). Der Marker-Inhalt muss exakt
  round-trip-fähig sein (`str(created)` → `float(text)` == `created`). Python garantiert das für
  `str(float)`, trotzdem beim Schreiben/Lesen denselben Konvertierungsweg verwenden.
  Whitespace/Newline beim Lesen abstreifen.
  Falls dieselbe Marker-Datei zeitgleich mit unterschiedlichen Locks aus zwei Workflows
  desselben Namens beschrieben würde, entscheidet der zuletzt gültige `created`-Wert — bereits
  heute nicht anders (ein Workflow-Name ist ohnehin nur einmal gleichzeitig aktiv).
- **AC-2-Randfall:** Schreibt `phase_listener` den Marker, bevor überhaupt ein Lock existiert
  (Freigabe kommt, bevor der erste Edit einen Lock angelegt hat), gibt es noch keinen `created`-
  Wert zum Binden. Für diesen seltenen Fall (praktisch nie, da `phase6_implement` per Definition
  mit einem Edit beginnt) fail-closed behandeln: Marker ohne passenden Lock beim nächsten
  Gate-Lauf verwerfen, genau wie AC-2 es verlangt — kein Sonderfall nötig, dieselbe Vergleichslogik
  deckt es ab.

## Analysis

### Type
Bug (Sicherheitslücke im Freigabe-Gate, nicht ausnutzbar durch Claude selbst, aber ein
menschliches Ja für Lauf N wirkt fälschlich auch für Lauf N+1 desselben Workflow-Namens).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|--------------|
| `core/hooks/post_implementation_gate.py` | MODIFY | Marker-Prüfung von "existiert?" auf "Inhalt passt zum `created`-Wert des aktuellen `pending_validation_<name>.json`?" umstellen. Bei Mismatch: `block()` (nutzt automatisch `log_gate_event`, erfüllt AC-1+AC-5). Bei Marker ohne Lock: verwerfen und regulär in den "kein Lock"-Zweig weiterlaufen (AC-2/AC-4), zusätzlich expliziter `log_gate_event`-Aufruf, weil dieser Zweig nicht blockiert. |
| `core/hooks/phase_listener.py` | MODIFY | GREEN-Handler (Zeile 492–499) schreibt statt `approval_path.touch()` den `created`-Wert des aktuellen Locks als Inhalt. Existiert noch kein Lock (seltener Randfall), wird kein Marker geschrieben (fail-closed, kein Sonderfall auf der Lese-Seite nötig). |
| `core/hooks/hook_utils.py` | MODIFY | Kleine gemeinsame Helper (Lock-Pfad bilden, Lock lesen) ergänzen, damit `phase_listener.py` nicht die privaten `_lock_path`/`_read_lock`-Funktionen aus `post_implementation_gate.py` dupliziert oder importiert. |
| `tests/test_post_implementation_gate_marker_binding.py` | CREATE | Erste Testdatei für dieses Modul (RED-Phase): AC-1 bis AC-5 je ein Fall. |

### Scope Assessment
- Files: 4 (innerhalb des 4–5-Limits)
- Geschätztes LoC: ca. +90/-10 (Grossteil in der neuen Testdatei)
- Risk Level: NIEDRIG — isolierte Änderung an genau einer Gate-Prüfung, betrifft nur den
  Freigabe-Marker-Mechanismus; `bash_gate.py`s Tier-2-Schutz (blockt `touch` per Bash) und
  `workflow.py`s Cleanup bleiben unverändert nutzbar, da beide nur auf Dateiname/Existenz reagieren.

### Technical Approach
Bindung an den Lauf statt an den Namen — genau der Ansatz, den #131 für den Adversary-Dialog
bereits etabliert hat:
- `phase_listener` schreibt beim GREEN-Trigger den `created`-Timestamp des aktuellen
  `pending_validation_<name>.json` als Textinhalt in den Marker (statt einer leeren Datei).
- `post_implementation_gate` vergleicht beim Lesen den Marker-Inhalt mit dem `created`-Wert des
  *aktuell* existierenden Locks (`str(float)` ist in Python round-trip-sicher, kein Rundungsrisiko).
- Stimmt der Inhalt überein → Freigabe gilt, Lock+Marker löschen, erlauben (AC-3).
- Existiert gar kein Lock (Workflow-Name wiederverwendet, alter Marker liegt noch herum) → Marker
  wird verworfen, Gate verhält sich wie bei einem unbekannten Workflow: legt beim nächsten Edit
  einen frischen Lock an und startet das Batch-Fenster neu (AC-2, AC-4).
- Stimmt der Inhalt nicht überein (Marker existiert, aber zu einem anderen `created`-Wert als der
  lebende Lock) → verwerfen und weiter blockieren, neue Freigabe verlangen (AC-1).
- Jede Ablehnung eines Markers (Mismatch oder Lock-los) wird geloggt (AC-5): der Mismatch-Fall
  automatisch über `block()` → `log_gate_event`, der Lock-lose Verwurf-Fall durch einen expliziten
  `log_gate_event`-Aufruf, weil dort kein `block()` stattfindet.

**Alternative geprüft, verworfen:** Den Marker als eigenständige Datei ganz abschaffen und den
Freigabe-Status stattdessen als Feld direkt in `pending_validation_<name>.json` führen (ein Lock,
kein zweites File). Sauberer, aber `bash_gate.py`s Tier-2-Schutz blockt aktuell gezielt das
*Anlegen der Marker-Datei per Bash* (Namens-Muster) — dieser Schutz müsste dann stattdessen das
Schreiben eines Felds *in* der Lock-Datei absichern, was den Blockmechanismus selbst anfasst statt
nur die Prüfung. Das sprengt den Rahmen dieses Tickets (mehr Dateien, Risiko an einer zweiten,
unabhängigen Sicherheitsgrenze) und liefert für #134 keinen zusätzlichen Nutzen. Empfehlung bleibt
die Inhalts-Bindung aus dem Issue-Vorschlag.

### Dependencies
- Upstream: `hook_utils.get_active_workflow_name`, `find_project_root`, `log_gate_event`.
- Downstream: `bash_gate.py` (Tier-2-Schutz auf Marker-Dateiname, unverändert relevant) und
  `workflow.py` (Cleanup alter Marker, unverändert relevant, eigenes begleitendes Issue).

### Open Questions
Keine — technischer Weg ist eindeutig, keine Produktentscheidung nötig.
