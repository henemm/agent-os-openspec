import Foundation

/// Nachgebauter Produktivcode. Schreibt `processedAt` genau einmal, hinter
/// einer `if`-Bedingung; schreibt `title` dreimal; schreibt `energyRaw` nie.
struct EnrichmentWriter {
    static func markProcessed(_ task: inout Task, now: Date) {
        if task.processedAt == nil {
            task.processedAt = now
        }
    }

    static func applyTitle(_ task: inout Task, raw: String) {
        task.title = raw.trimmingCharacters(in: .whitespaces)
    }

    static func fallbackTitle(_ task: inout Task) {
        if task.title.isEmpty {
            task.title = "Untitled"
        }
    }

    static func resetTitle(_ task: inout Task) {
        task.title = ""
    }
}
