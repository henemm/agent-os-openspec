import Foundation
import SwiftData

/// One captured thing. `rawText` is the only user input and is never changed.
/// Every derived field is optional and carries a source and a confidence (ADR-3).
/// Named `TaskItem` to avoid clashing with Swift Concurrency's `Task`.
@Model
final class TaskItem {
    // Identity and capture
    var id: UUID = UUID()
    var ownerID: String = ""
    var rawText: String = ""
    var capturedAt: Date = Date()
    var capturedViaRaw: String = CaptureChannel.app.rawValue
    var sourceURL: URL?

    // Lifecycle
    var statusRaw: String = TaskStatus.unprocessed.rawValue
    var processedAt: Date?
    var nextRank: Double?
    var completedAt: Date?
    var parkedAt: Date?

    // Calendar (ADR-13)
    var showInCalendar: Bool = false
    var calendarEventID: String?

    // Repeat (ADR-7)
    var repeatRule: RepeatRule?

    // Derived: title
    var title: String?
    var titleSourceRaw: String?
    var titleConfidence: Double?

    // Derived: due
    var dueDate: Date?
    var dueHasTime: Bool = false
    var dueSourceRaw: String?
    var dueConfidence: Double?

    // Derived: importance, urgency, duration, energy
    var importanceRaw: String?
    var importanceSourceRaw: String?
    var importanceConfidence: Double?

    var urgencyRaw: String?
    var urgencySourceRaw: String?
    var urgencyConfidence: Double?

    var durationRaw: String?
    var durationSourceRaw: String?
    var durationConfidence: Double?

    var energyRaw: String?
    var energySourceRaw: String?
    var energyConfidence: Double?

    // Derived: people (names from the text, no Contacts access in v1)
    var people: [String] = []
    var peopleSourceRaw: String?
    var peopleConfidence: Double?

    // Derived: contexts
    var contextsSourceRaw: String?
    var contextsConfidence: Double?

    // Relationships (all optional: CloudKit requirement)
    var project: Project?
    var parent: TaskItem?
    @Relationship(deleteRule: .cascade, inverse: \TaskItem.parent) var subtasks: [TaskItem]?
    @Relationship(inverse: \TaskItem.blocks) var blockedBy: [TaskItem]?
    var blocks: [TaskItem]?
    var contexts: [TaskContext]?
    @Relationship(deleteRule: .cascade, inverse: \Revision.task) var revisions: [Revision]?
    @Relationship(deleteRule: .cascade, inverse: \CompletionRecord.task) var completions: [CompletionRecord]?

    init(rawText: String, capturedVia: CaptureChannel = .app, sourceURL: URL? = nil, ownerID: String = "") {
        self.rawText = rawText
        self.capturedViaRaw = capturedVia.rawValue
        self.sourceURL = sourceURL
        self.ownerID = ownerID
    }
}

// MARK: - Typed accessors

extension TaskItem {
    var status: TaskStatus {
        get { TaskStatus(rawValue: statusRaw) ?? .unprocessed }
        set { statusRaw = newValue.rawValue }
    }
    var capturedVia: CaptureChannel {
        get { CaptureChannel(rawValue: capturedViaRaw) ?? .app }
        set { capturedViaRaw = newValue.rawValue }
    }
    var importance: Importance? {
        get { importanceRaw.flatMap(Importance.init(rawValue:)) }
        set { importanceRaw = newValue?.rawValue }
    }
    var urgency: Urgency? {
        get { urgencyRaw.flatMap(Urgency.init(rawValue:)) }
        set { urgencyRaw = newValue?.rawValue }
    }
    var duration: DurationBucket? {
        get { durationRaw.flatMap(DurationBucket.init(rawValue:)) }
        set { durationRaw = newValue?.rawValue }
    }
    var energy: Energy? {
        get { energyRaw.flatMap(Energy.init(rawValue:)) }
        set { energyRaw = newValue?.rawValue }
    }

    /// What the list shows: the title, or the raw text while unverified.
    var displayTitle: String {
        if let title, !title.isEmpty, status != .unverified { return title }
        return rawText
    }

    var isOpen: Bool {
        status == .unprocessed || status == .unverified || status == .active
    }

    /// Blocked means at least one blocker is still open.
    var isBlocked: Bool {
        (blockedBy ?? []).contains { $0.isOpen }
    }

    /// Unseen AI revisions drive the marker in the list (Variante C).
    var hasUnseenAIRevisions: Bool {
        (revisions ?? []).contains { $0.author == .ai && $0.seenAt == nil }
    }
}
