# Mini-Spec: ❗Du-Markierung in der PO-Briefing-Freigabe nachrüsten (#209)

## Problem

Live-Beispiel einer PO-Briefing-Freigabe (agent-os-openspec 3.27.2):

```
⚙ PO-Briefing unabhängig erstellt · agent-os-openspec 3.27.2
Schreibe approved, wenn der Plan so stimmt — danach geht es in die Umsetzung.
```

Die `❗ Du: …`-Zeile aus #174 fehlt. Ursache: `30-write-spec` ist in
`scripts/sync_skills.py::MARKER_EXEMPT` bewusst vom generischen `marker_block()`
ausgenommen (eigene, feste Freigabe-Vorlage). Diese eigene Vorlage in
`core/commands/30-write-spec.md` wurde beim #174-Fix nie nachgezogen — ausgerechnet an
der Stelle, die *immer* eine PO-Entscheidung verlangt.

## Was ändert sich

- `core/commands/30-write-spec.md`, Abschnitt „Freigabe-Ausgabe an den User": neue Zeile
  `❗ Du: \`approved\` — Freigabe der Spec, danach beginnt die Umsetzung` direkt vor der
  `⚙`-Marker-Zeile (konsistent mit `marker_block()`s Konvention: `❗ Du` zuerst, `⚙` als
  letzte Zeile). Die bisherige separate Zeile „Schreibe `approved` …" entfällt — die
  `❗ Du`-Zeile trägt dieselbe Aufforderung bereits in der repo-weiten Standardform.
  Die begleitenden nummerierten Anweisungen (Teile der Ausgabe) werden entsprechend
  angepasst.
- `python3 scripts/sync_skills.py` erneut laufen lassen (generiert `skills/30-write-spec/SKILL.md`
  neu — dort landet der Text wörtlich, da `30-write-spec` `MARKER_EXEMPT` bleibt).

## Was darf sich nicht ändern

- `30-write-spec` bleibt `MARKER_EXEMPT` — der generische `marker_block()` wird weiterhin
  nicht angehängt (würde die strikte Vorlage duplizieren).
- Das Briefing selbst (`docs/briefings/<workflow>.md`) wird unverändert wörtlich ausgegeben.
- Die `⚙`-Zeile bleibt wörtlich wie bisher und bleibt die letzte Zeile der Ausgabe.

## Acceptance Criteria

- **AC-1:** Given die Freigabe-Vorlage in `core/commands/30-write-spec.md`, When sie gelesen
  wird, Then enthält sie eine `❗ Du: \`approved\` — …`-Zeile unmittelbar vor der `⚙`-Zeile.
- **AC-2:** Given `scripts/sync_skills.py --check`, When es nach der Änderung läuft, Then
  meldet es „Skills synchron" (kein Drift zwischen `core/commands` und `skills/`).
- **AC-3:** `30-write-spec` bleibt in `MARKER_EXEMPT` — keine doppelte Marker-Zeile.

## Manuelle Test-Schritte

1. `skills/30-write-spec/SKILL.md` nach dem Sync öffnen: Vorlage zeigt `❗ Du: …` direkt
   vor `⚙ PO-Briefing unabhängig erstellt · agent-os-openspec <Version>`.

## Test Plan

- `python3 scripts/sync_skills.py --check` (AC-2).
- Volle Suite `python3 -m pytest tests/`.
