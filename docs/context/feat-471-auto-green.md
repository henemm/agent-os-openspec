# Context: feat-471-auto-green

## Request Summary
Teil C von #468: Im Auto-Modus entfällt die GREEN-Freigabe („go“) nach der Implementierung. Setzt #469 (`autonomy_mode`, `record_approval`), #470 (`trusted_config`) und #473 (Config-Schutz) voraus.
Gesamtanalyse: `docs/context/feat-468-autonomie-modus.md`.

## PO-Entscheidungen
- GREEN immer automatisch im Auto-Modus, auch bei gemeldeten Auffälligkeiten; Auffälligkeiten gehen an Adversary und Abschlussmeldung
- Immer menschlich bleiben: AMBIGUOUS, zweites BROKEN/Circuit Breaker, Override, Deploy, Stop-Lock

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/post_implementation_gate.py` | Gate nur in `phase6_implement` (`_GATED_PHASES`), Bypass-Phasen; erster Code-Edit → Lock, 15-min-Batch-Fenster, danach Block bis Marker `user_approved_validation_<wf>` (nur vom Listener geschrieben, bash_gate schützt ihn) |
| `core/hooks/phase_listener.py:603-660` | GREEN-Phrase setzt `green_approved=True` + Marker |
| `core/hooks/workflow.py` | `autonomy_mode()` (liest `trusted_config()`), `record_approval()`, `green_approved` (:694 Init, :1631 status, :1683 Reset beim Rücksprung), `_validate_transition` (phase6→6b prüft `green_approved` nicht), `next_step` (phase6_implement → `/50-implement`), `COMMANDS` |
| `core/commands/50-implement.md` | Step 4 (GREEN-Artefakt), Step 6 (STOP, User-Freigabe `go`), Step 7 (`phase phase6b_adversary`) |
| `skills/50-implement/SKILL.md` | generiert via `scripts/sync_skills.py` |

## Analysis
- `workflow.py auto-green` → stdout `AUTO_GREEN=done|human` + `REASON=…`, Exit 0, fail-closed, State bei human byte-identisch. Bedingungen: `autonomy_mode()=="auto"` (nur trusted_config), Phase `phase6_implement`, `red_test_done`, mindestens ein `test_output`-Artefakt der Phase `phase6_implement`, Stop-Lock nicht aktiv, noch nicht `green_approved`. Wirkung: `green_approved=True`, `record_approval(data,"green","auto",…, evidence{artifact})`, speichern. Kein Phasenwechsel (der bleibt `phase phase6b_adversary` in Step 7).
- `post_implementation_gate.py`: im Auto-Modus kein Lock und kein Block (direkt `allow()` nach den Bypass-Prüfungen) — kein gefälschter Marker. Modus über `workflow.autonomy_mode()` (lazy import, fail → manual = bisheriges Verhalten).
- `50-implement.md` Step 6: `workflow.py autonomy` prüfen; bei `AUTONOMY=auto` → `auto-green`; `AUTO_GREEN=done` → Zusammenfassung als Info ausgeben, direkt Step 7; sonst bisherige Freigabe-Ausgabe mit `go`.
- `next_step`/`status_note`: unverändert (`/50-implement`), keine Freitext-Freigabe nötig.
- Risiken: Modus-Flip mitten in phase6 (Lock existiert schon → im Auto-Modus ignorieren); Listener-Pfad `go` muss weiter wirken.
- Scope: workflow.py, post_implementation_gate.py, 50-implement.md (+Skill), CHANGELOG, Tests.
