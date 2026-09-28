import XCTest
@testable import App

/// Nachgebaute Testdatei. Weist `task.processedAt` an fünf Stellen zu, weist
/// `task.energyRaw` an einer Stelle zu (obwohl das Feld 0
/// Produktions-Schreibstellen hat) und `task.title` an zwei Stellen -- alle
/// drei Felder brauchen mindestens eine Test-Zuweisung, sonst fielen sie
/// unter der Filterregel aus der Ausgabetabelle heraus. `notes` wird bewusst
/// NIE zugewiesen (Beleg für AC-1b). Dazu Rauschen, das keinen Treffer
/// erzeugen darf: eine lokale Variable gleichen Namens ohne Objektbezug und
/// Vergleiche mit `==`.
final class TaskTests: XCTestCase {
    private func makeProcessedTask(minutesAgo: Int) -> Task {
        var task = Task(processedAt: nil, energyRaw: nil, title: "Sample", notes: nil)
        task.processedAt = Date().addingTimeInterval(TimeInterval(-minutesAgo * 60))
        return task
    }

    func testProcessedAtIsSetForMorningTask() {
        var task = Task(processedAt: nil, energyRaw: nil, title: "Morning", notes: nil)
        task.processedAt = Date()
        XCTAssertNotNil(task.processedAt)
    }

    func testProcessedAtIsSetForEveningTask() {
        var task = Task(processedAt: nil, energyRaw: nil, title: "Evening", notes: nil)
        task.processedAt = Date().addingTimeInterval(-3600)
        XCTAssertNotNil(task.processedAt)
    }

    func testProcessedAtIsSetForRecurringTask() {
        var task = makeProcessedTask(minutesAgo: 5)
        task.processedAt = Date()
        XCTAssertNotNil(task.processedAt)
    }

    func testProcessedAtIsSetForBatchTask() {
        var task = Task(processedAt: nil, energyRaw: nil, title: "Batch", notes: nil)
        task.processedAt = Date().addingTimeInterval(-7200)
        XCTAssertNotNil(task.processedAt)
    }

    func testProcessedAtStaysNilUntilAssigned() {
        let processedAt = Date()
        let task = Task(processedAt: nil, energyRaw: nil, title: "Untouched", notes: nil)
        XCTAssertNil(task.processedAt)
        XCTAssertNotEqual(task.processedAt, processedAt)
    }

    func testProcessedAtComparisonAgainstNil() {
        let task = Task(processedAt: nil, energyRaw: nil, title: "Comparison", notes: nil)
        XCTAssertTrue(task.processedAt == nil)
    }

    func testEnergyRawDefaultsToZero() {
        var task = Task(processedAt: nil, energyRaw: nil, title: "Energy", notes: nil)
        task.energyRaw = 0
        XCTAssertEqual(task.energyRaw, 0)
    }

    func testTitleIsRenamed() {
        var task = Task(processedAt: nil, energyRaw: nil, title: "Old", notes: nil)
        task.title = "Renamed"
        XCTAssertEqual(task.title, "Renamed")
    }

    func testTitleIsRenamedAgain() {
        var task = Task(processedAt: nil, energyRaw: nil, title: "Old", notes: nil)
        task.title = "Renamed Again"
        XCTAssertEqual(task.title, "Renamed Again")
    }

    func testTitleComparisonIsNotAnAssignment() {
        let task = Task(processedAt: nil, energyRaw: nil, title: "Fixed", notes: nil)
        XCTAssertTrue(task.title == "Fixed")
    }
}
