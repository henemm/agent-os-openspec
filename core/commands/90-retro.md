# /90-retro — Workflow-Retro

Analysiere einen abgeschlossenen Workflow aus dem Archiv: Zeiten pro Phase, Qualitätssignale, Optimierungshinweise. Aufruf: `/90-retro` (zuletzt abgeschlossener), `/90-retro <name>`, `/90-retro list`.

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Aufruf als `/90-retro #<N>`?** Der Workflow ist **archiviert** — deshalb kein `workflow.py switch` (nur für laufende Workflows), sondern Suche im Archiv, danach `retro <name>`:

```bash
ISSUE=42   # die übergebene Nummer (ohne #)
python3 - "$ISSUE" <<'PY'
import sys, json, glob, re, os
i = sys.argv[1].lstrip('#'); pat = re.compile(rf'(^|[-_]){re.escape(i)}([-_]|$)')
fs = [f for f in glob.glob('.claude/workflows/_archive/*.json') + glob.glob('.claude/workflows/*.json') if pat.search(os.path.basename(f)[:-5])]
for f in fs: print('GEFUNDEN:', os.path.basename(f)[:-5], '| Phase=' + str(json.load(open(f)).get('current_phase')), '|', 'archiviert' if '_archive' in f else 'LAEUFT NOCH')
print('\nNAME=' + os.path.basename(fs[0])[:-5] if fs else f'KEIN Workflow fuer #{i}.')
PY
```

**Fasse dem User in 2 Sätzen zusammen**, welchen Workflow du analysierst; bei `LAEUFT NOCH` zuerst das sagen und den offenen Pflicht-Schritt nennen (Retro verfrüht).

## Ablauf

1. `list` → `python3 .claude/hooks/workflow.py retro-list`, fragen: "Welchen Workflow möchtest du analysieren?", dann `retro <name>`.
   Ohne Argument: `retro-list` kurz zeigen, dann ohne Nachfrage `python3 .claude/hooks/workflow.py retro`.
2. `python3 .claude/hooks/workflow.py retro <name>`
3. PO-Zusammenfassung in einfacher Sprache (2–4 Sätze): Gesamtdauer, Qualitätsprobleme (Fix-Loops, Override, fehlendes TDD), langsamste Phase und warum, was gut lief. Kein Fachjargon, keine Dateinamen.
