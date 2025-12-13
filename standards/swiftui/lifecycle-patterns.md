# SwiftUI Lifecycle Patterns

## Guard Flag Pattern (Preventing Duplicate Execution)

**Problem:** SwiftUI `.onDisappear` lifecycle hook fires AFTER session completion callbacks, causing methods to execute twice.

**Example Bug:**
```swift
// THREE call sites for endSession():
ProgressRingsView(onSessionEnd: { await endSession(manual: false) })  // Timer completion
await endSession(manual: true)  // Manual stop button
.onDisappear { await endSession(manual: true) }  // View lifecycle

// When session completes normally:
// 1. Timer fires -> callback executes endSession()
// 2. View disappears -> .onDisappear executes endSession() AGAIN
// Result: Cleanup code called twice
```

**Solution:**
```swift
@State private var sessionEnded: Bool = false

func endSession(manual: Bool) async {
    // Guard: Prevent double execution
    if sessionEnded {
        print("[Debug] endSession already executed, skipping")
        return
    }

    // Set flag SYNCHRONOUSLY before any async work
    sessionEnded = true

    // ... rest of cleanup code ...
}
```

**Rules:**
- DON'T rely on SwiftUI lifecycle hooks alone for cleanup
- DON'T call side-effect methods from both callbacks AND .onDisappear without guards
- DON'T set guard flags AFTER async tasks (race conditions!)
- DO use Guard Flag Pattern for methods called from multiple points
- DO set flags synchronously BEFORE async operations
- DO log guard hits for debugging

## WORK vs REST Phase UI

**Problem:** Same pause display for semantically different phases shows redundant information.

**Solution:** Split behavior based on phase type:
```swift
if isPaused {
    if currentPhase.isWork {
        // WORK phase paused: show current info
        currentInfoDisplay()
    } else {
        // REST phase paused: show ONLY next info
        nextInfoDisplay()
    }
}
```

**Pattern:**
- DO differentiate UI based on phase type
- DO match pause display to running display for same phase
- DON'T use same UI state for semantically different phases

## Text Styling Consistency

**Problem:** Multi-styled text not consistently displayed with correct fonts.

**Solution:** Split text into separate views:
```swift
VStack(spacing: 4) {
    Text(labelText)
        .font(.caption)
        .foregroundStyle(.secondary)

    Text(mainText)
        .font(.headline)
}
```

**Rule:** DON'T combine text with different styles in single Text view

## Understanding Existing UI Behavior

**Before modifying ANY user interaction:**
1. Read the CURRENT code to understand what it does
2. Test the CURRENT behavior (or ask user)
3. Document WHY the change is needed
4. Get explicit approval for breaking changes

**Example:**
- Original: Element tap -> show tooltip
- Wrong change: Element tap -> open sheet (breaking!)
- Correct: Ask "Element tap shows tooltip - should I change this?"
