# SwiftUI State Management

## InfoButton + InfoSheet Pattern

**Purpose:** Contextual help without cluttering UI.

**Components:**
- `InfoButton.swift` - Reusable button
- `InfoSheet.swift` - Modal sheet with title, description, tips

**Usage:**
```swift
@State private var showInfo = false

HStack(spacing: 8) {
    Text("Feature Title")
    InfoButton { showInfo = true }
}

.sheet(isPresented: $showInfo) {
    InfoSheet(
        title: "Feature Name",
        description: "What this does",
        usageTips: ["Tip 1", "Tip 2"]
    )
}
```

**When to Use:**
- Tab-specific features
- Complex UI elements needing explanation
- Non-obvious functionality

**When NOT to Use:**
- Settings screens (already modal -> use inline text)
- Simple, self-explanatory UI
- Features with extensive documentation needs

**Design Decisions:**
- No decorative icons (information, not decoration)
- Minimal whitespace (8pt top padding)
- `.font(.caption)` for secondary text
- Close button: xmark.circle.fill in toolbar

## Modal Context Awareness

**Rule:** Avoid nested modals. Use inline text for already-modal contexts.

```swift
// WRONG: Info button in Settings (already modal)
Section(header: Text("Goals")) {
    InfoButton { showInfo = true }  // Sheet in Sheet!
}

// CORRECT: Inline text
Section(header: Text("Goals")) {
    Text("Set your daily goals. Progress shown in calendar.")
        .font(.caption)
        .foregroundStyle(.secondary)
}
```

## Tab Content vs Toolbar Placement

**Rule:** Info buttons belong in tab content, not toolbar.

- **Toolbar** = global navigation (Settings, Calendar nav)
- **Tab Content** = tab-specific features

```swift
// WRONG: In toolbar
.toolbar {
    InfoButton { showInfo = true }  // Which tab?
}

// CORRECT: In content
VStack {
    HStack {
        Text("Feature Title")
        InfoButton { showInfo = true }  // Clear context
    }
}
```

## Feature Philosophy Categories

Apps have different feature types - design UI accordingly:

1. **Primary Features:** Main app functionality
   - Prominent UI, explicit interaction

2. **Support Features:** Statistics, History, Settings
   - Visible but secondary

3. **Passive Features:** Background tracking, Smart notifications
   - "Unterschwellig", notification-driven
   - Should NOT have prominent manual-entry UI

**Ask which category before designing UI!**
