import Foundation

/// Minimal, nachgebautes Beispielmodell für die Regelweg-Tests von
/// `precondition_origins.py`. Trägt vier Felder:
/// `processedAt` (1x Produktions-Schreibstelle), `energyRaw` (0x),
/// `title` (3x) -- alle drei mit mindestens einer Test-Zuweisung --, und
/// `notes`, das aus dem Modell gelesen wird (AC-1a), aber von KEINER
/// Testdatei je zugewiesen wird und deshalb nicht in der gefilterten
/// Ausgabetabelle erscheinen darf (AC-1b).
struct Task {
    var processedAt: Date?
    var energyRaw: Int?
    var title: String
    var notes: String?
}
