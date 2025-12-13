# SwiftUI Localization Standards

## When to Use Which Method

### LocalizedStringKey (Default for SwiftUI)

Use for static text in SwiftUI views:
```swift
Text("key_name")  // Automatically uses LocalizedStringKey
```

### NSLocalizedString (For Dynamic/Computed)

Use for:
- String interpolation
- Computed properties
- Non-View contexts

```swift
let message = NSLocalizedString("key_name", comment: "Context for translators")
```

### String(localized:) (iOS 15+)

Modern alternative to NSLocalizedString:
```swift
let title = String(localized: "key_name")
```

## Localizable.xcstrings Format

```json
{
  "key_name" : {
    "localizations" : {
      "de" : {
        "stringUnit" : {
          "state" : "translated",
          "value" : "German translation"
        }
      },
      "en" : {
        "stringUnit" : {
          "state" : "translated",
          "value" : "English translation"
        }
      }
    }
  }
}
```

## Localization Workflow

1. Find hardcoded strings (Grep for text in .swift files)
2. Add key to Localizable.xcstrings with all languages
3. Replace hardcoded string with localized key
4. Test all languages on device

## Common Mistakes

- DON'T hardcode any user-visible text
- DON'T forget to add ALL language translations
- DON'T use different keys for same concept
- DO maintain consistency with existing vocabulary
- DO test all languages after changes
