# Bug Analysis (Analysis-First)

Analyze a bug following the **Analysis-First** principle.

**NEVER fix directly!** First understand completely, then document, then (after approval) fix.

## Step 0: GitHub Issues durchsuchen (IMMER ZUERST)

```bash
# Offene Bug-Issues anzeigen
gh issue list --label "bug" --state open

# Keyword-Suche nach aehnlichen Bugs
gh issue list --search "$ARGUMENTS" --state open
```

Falls Duplikat gefunden → vorhandenes Issue referenzieren, kein neues erstellen.
Falls kein Duplikat → `bug-investigator` erstellt am Ende ein neues Issue.

---

## Phase 1: Understand the Bug

1. **Capture symptoms:**
   - What exactly happens? (User description)
   - Where does it happen? (View, feature, context)
   - When does it happen? (Always? Sometimes? After specific action?)

2. **Define reproduction steps:**
   - Step-by-step instructions to reproduce
   - Expected behavior vs. actual behavior

## Phase 2: Find Root Cause

3. **Analyze code:**
   - Identify affected files
   - Trace data flow completely (NOT just fragments!)
   - Question: "Where does the problem ORIGINATE?"

4. **Identify root cause with certainty:**
   - Name concrete code location(s) (file:line)
   - WHY does this location cause the problem?
   - No speculation - only proven causes!

## Phase 3: Document

5. **Create entry in bug tracking:**

```markdown
## Bug: [Short Description]

- **Location:** [File(s)]
- **Problem:** [What goes wrong]
- **Expected:** [What should happen]
- **Root Cause:** [Why it happens - code location]
- **Test:** [How to verify fix]
- **Effort:** [Small/Medium/Large]
```

## Phase 4: Fix (only after approval!)

After documentation and user approval:
1. `/20-analyse` - Start workflow
2. `/30-write-spec` - Specify fix
3. User: "approved"
4. `/50-implement` - Implement fix
5. `/60-validate` - Test

## STOP Conditions

Stop and ask when:
- Root cause unclear (need more info)
- Bug not reproducible (need steps)
- Multiple possible causes (prioritize)
- Fix would change >5 files (split?)

## Output to User

Summarize (NO code, understandable language):

1. **What is the problem?** (1-2 sentences)
2. **Where is the cause?** (File + short explanation)
3. **How do we test the fix?** (Concrete steps)
4. **Estimated effort** (Small/Medium/Large)

---

## Fast Track (triviale Bugs — ≤3 Dateien, bekannte Ursache)

Wenn Ursache klar und Fix klein → direkt implementieren ohne vollständigen 8-Phasen-Workflow.

**Voraussetzungen:**
- Ursache mit Sicherheit bekannt (konkrete Datei + Zeile)
- Fix berührt ≤3 Dateien
- Kein neues API-Design oder Breaking Changes

**Ablauf:**
```bash
# 1. Bug-Workflow starten (startet direkt bei phase6_implement)
python3 .claude/hooks/workflow.py start BUG-<N> --type bug
export OPENSPEC_ACTIVE_WORKFLOW=BUG-<N>

# 2. Fix implementieren (kein Spec, kein TDD-Red erforderlich)
# ...edit files...

# 3. Manuell testen
# Reproduktionsschritte durchgehen, Fix verifizieren

# 4. Abschließen
python3 .claude/hooks/workflow.py write-log success
python3 .claude/hooks/workflow.py complete
```

**Was wegfällt beim Fast Track:**
- Phasen 1–5 (Kontext, Analyse, Spec, Approval, TDD-Red)
- Adversary-Validierung vor `git commit`
- TDD-Artefakt-Pflicht

**Was bleibt aktiv:**
- Rebase-Gate (Branch muss auf `origin/main` stehen)
- Stop-Lock / Override-Token
- Secrets Guard
