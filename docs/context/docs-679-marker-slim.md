# Kontext: docs-679-marker-slim (#679, Epic #649)

## Request Summary
Folgeschnitt aus #674: Der Versions-Marker-Block, den `scripts/sync_skills.py::marker_block` an jeden der 15 Befehlstexte hängt (heute 3 259 Bytes je Befehl), und der Hook-Hinweis je Zug (`[agent-os-openspec] AKTIVER WORKFLOW …`, heute 1 886 Bytes je Nutzer-Nachricht) werden auf das Nötige gekürzt. Begründungen wandern nach `docs/befehle/fusszeile.md`. Gate-Verhalten bleibt unverändert. DoD: Marker-Block ≤ 1,2 KB, Hook-Hinweis gemessen vorher/nachher, Suite grün, CHANGELOG, Version. Orchestrator-Vorgabe: Messung vorher/nachher wie #580 an #649.

## Related Files
- `scripts/sync_skills.py:77-141` — `marker_block(name, version)`; generiert in `skills/*/SKILL.md` (15 Skills, `MARKER_EXEMPT` ausgenommen).
- `core/hooks/workflow.py:400-415` — `END_STATE_RULE` (872 Bytes), nur von `_status_note_base` genutzt.
- `core/hooks/workflow.py:1459-1532` — `status_note` / `_status_note_base` (Normalfall + Auto-Freigabe-Fall #470). Aufgerufen von `core/hooks/phase_listener.py:442` (UserPromptSubmit, jeder Zug).
- `core/hooks/alias_sync.py:148-150` — Fallback-Alias erkennt die Zeile, die mit `⚙ ` beginnt; diese Zeile muss unverändert bleiben.
- `core/hooks/footer_gate.py` (Stop-Hook) — prüft die Fußzeile mechanisch; liest Erwartung aus `workflow.py` (`expected_footer…`, Zeile ~325), nicht aus dem Marker-Text.
- `docs/befehle/` — Zielort für Hintergrund (Muster #674/#677/#678).

## Existing Patterns
- #580/#674/#677/#678: Ablauf und Pflichten bleiben, Begründungen wörtlich nach `docs/`, Größenwächter-Test (`tests/test_commands_slim_67x.py`).
- Summenwächter `tests/test_commands_slim_678.py` gilt nur für `core/commands/*.md` (82 831 / 83 000); der Marker-Block lebt nur in `skills/`, berührt die Summe nicht.

## Tests, die Wortlaut festschreiben (müssen grün bleiben)
- `tests/test_skills_sync.py:309-387`: Block enthält `❗ Du:` < `ℹ️ Status: Workflow` < `⚙ /<name> · agent-os-openspec <v>`, `Phase \`<x>\` von 8`, `` `❗ Du: …` ``, `` `✅ Erledigt: <was>. ``, `` `⏳ Läuft noch: <worauf gewartet wird>. ``, `workflow.py waiting`, `workflow.py endstate`, `‼️`, die Wörter „bei Bedarf“, „optional“, „fertig“, „abgeschlossen“, „erledigt“, `/clear`, `Kosten-Empfehlung`, `frei formulierten Arbeitsstandsmeldungen`, `Übergabe-Blöcke oben bleiben unverändert`, `AM ENDE dieser Nachricht`, `workflow.py status`, `„Nächster Pflicht-Schritt“`; nicht: `wörtlich von dort`, `Nichts zu tun`.
- `tests/test_skills_sync.py:62-136`: genau ein `## Versions-Marker`, nach `## Setup`, keine `{{`.
- `tests/test_endzustand_550.py:284-300`: Block und Hook-Hinweis enthalten `✅ Erledigt`, `⏳ Läuft noch`, `❗ Du`, `workflow.py waiting`.
- `tests/test_status_note_325.py:80-104`: Hinweis enthält Name, `Phase 7 von 8`, `phase7_validate`, `/60-validate #1761`, „bei Bedarf“, „optional“, „fertig“, `phase8_complete`, `/clear`, `❗ Du:`, `⏳ Läuft noch:`, `✅ Erledigt:`.
- `tests/test_spec_ampel_470.py:462-472,766`: Auto-Fall ohne `❗`, manueller Fall mit `❗`.
- `tests/test_issue_number_513.py`, `test_sitzungs_backlog_613_610.py`, `test_auftrag_551.py`: Issue-Nummer, Auftragssatz.

## Analyse (Summe 2: Kontext + Analyse kombiniert)
- **Marker-Block:** 3 259 → Ziel ≤ 1 200 Bytes. Redundanz: drei Absätze erklären Begründungen (Turn-Beginn-Stand, Übergabe-Blöcke, Platzhalter). Kern-Regeln passen in eine Vorlage + einen Absatz mit allen Pflicht-Stichworten; Begründungen wörtlich nach `docs/befehle/fusszeile.md`.
- **Hook-Hinweis:** 1 886 Bytes je Zug. `END_STATE_RULE` wiederholt die Drei-Formen-Regel aus dem Marker-Block in Langform; Absätze zu Phasenwechsel und Emoji-Verbot sind Begründungsprosa. Ziel: ≤ 900 Bytes bei gleichen Pflicht-Stichworten. Der Auftragssatz (`auftrag_note_text`, enthält den PO-Wortlaut) bleibt unverändert — er dient der Wiederherstellung nach Kontextverlust.
- **Messung:** Grundlast der ersten Anfrage ändert sich durch den Schnitt kaum (Skills sind beim Start nur als Beschreibung gelistet). Wirkung zeigt sich je Befehlsaufruf (−≈2 KB) und je Zug mit aktivem Workflow (−≈1 KB). Messung daher: (a) Byte-Messung beider Texte vorher/nachher, (b) zwei frische Cloud-Sitzungen (main vs. Branch) mit identischem Auftrag „Skill laden, nichts ausführen“, Eingabe-Token des Modellaufrufs nach dem Skill-Laden (Nutzungsdaten), analog #580.

## Dependencies / Dependents
- Generat `skills/*/SKILL.md` per `python3 scripts/sync_skills.py`; `.claude/agents/` unberührt.
- Konsumentenprojekte erhalten den neuen Block über das Plugin-Update; der Alias-Fallback druckt die Skill-Datei, `⚙`-Zeile unverändert.

## Risks
- Kürzung darf keine Fußzeilen-Pflicht verlieren; `footer_gate.py` erzwingt das Format zusätzlich mechanisch (Stop-Hook), daher geringes Verhaltensrisiko.
- Hook-Code (`workflow.py`) → Adversary-Risiko hoch, 2 Dialogrunden.
- Größenwächter: neuer Test `tests/test_marker_slim_679.py` (Block ≤ 1 200 Bytes, Hinweis ≤ 900 Bytes).

## Analysis
- **Type:** Feature (Verschlankung, Summe 2: Kontext und Analyse kombiniert, keine Explore-Agenten)
- **Affected Files:** `scripts/sync_skills.py` (MODIFY), `core/hooks/workflow.py` (MODIFY: `END_STATE_RULE`, `_status_note_base`), `skills/*/SKILL.md` (Generat), `docs/befehle/fusszeile.md` (CREATE), `tests/test_marker_slim_679.py` (CREATE), `CHANGELOG.md`, `.claude-plugin/plugin.json`
- **Scope/Risk:** ~5 Quelldateien, ~150 LoC Text; Risiko hoch (Hook-Code) → 2 Adversary-Runden
- **Technical Approach:** siehe „Analyse“ oben; Pflicht-Stichworte aus den Tests erhalten, Prosa nach docs.
- **Open Questions:** keine
