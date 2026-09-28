import Foundation
import OSLog
import SwiftData

/// Runs enrichment for every task that has none yet (ADR-4): right after capture and as the
/// catch-up pass at app start. A failure — model call or save — stays with that one task, leaves
/// it unprocessed for the next pass and does not stop the pass; nothing is swallowed silently.
@MainActor
final class EnrichmentCoordinator {
    static let exampleLimit = 5

    private let enricher: any TaskEnricher
    private let container: ModelContainer
    private let logger = Logger(subsystem: "com.henning.looseends", category: "Enrichment")
    private var isRunning = false

    init(enricher: any TaskEnricher, container: ModelContainer) {
        self.enricher = enricher
        self.container = container
    }

    /// Processes all pending tasks once, oldest first. A call while a pass is running returns at once.
    func processPending() async {
        guard !isRunning else { return }
        isRunning = true
        defer { isRunning = false }

        // An unavailable model ends the model step, not the pass: the rule runs anyway (#95, AC-7).
        let modelUnavailable = enricher.unavailableReason
        if let modelUnavailable {
            logger.notice("Model unavailable, rules only: \(modelUnavailable, privacy: .public)")
        }

        let context = container.mainContext
        do {
            let unprocessed = TaskStatus.unprocessed.rawValue
            let pending = try context.fetch(FetchDescriptor<TaskItem>(
                predicate: #Predicate { $0.processedAt == nil && $0.statusRaw == unprocessed },
                sortBy: [SortDescriptor(\.capturedAt)]
            ))
            guard !pending.isEmpty else { return }

            let contexts = try context.fetch(FetchDescriptor<TaskContext>(sortBy: [SortDescriptor(\.sortOrder)]))
            let projects = try context.fetch(FetchDescriptor<Project>(sortBy: [SortDescriptor(\.sortOrder)]))
            let examples = modelUnavailable == nil ? try Self.examples(in: context) : []
            let recognition = try Self.recognitionInputs(in: context)   // once before the loop (#136)

            for task in pending {
                applyRules(to: task, recognitionPool: recognition.pool, tasksByID: recognition.tasksByID)
                if modelUnavailable == nil {
                    let input = EnrichmentInput(
                        rawText: task.rawText,
                        capturedAt: task.capturedAt,
                        contextVocabulary: contexts.map(\.name),
                        projectNames: projects.map(\.name),
                        examples: examples
                    )
                    do {
                        let draft = try await enricher.enrich(input)
                        let written = EnrichmentWriter.apply(draft, to: task, contexts: contexts, projects: projects)
                        logger.info("Enriched \(task.id, privacy: .public): \(written) fields")
                    } catch {
                        logger.error("Enrichment failed for \(task.id, privacy: .public): \(error, privacy: .public)")
                    }
                }
                // Saving per task, caught per task: a failed save skips this one task, the pass
                // continues with the next (#95). The rule hit is persisted even when the model
                // was unavailable or its call failed.
                do {
                    try context.save()
                } catch {
                    logger.error("Saving failed for \(task.id, privacy: .public): \(error, privacy: .public)")
                }
            }
        } catch {
            logger.error("Enrichment pass failed: \(error, privacy: .public)")
        }
    }

    /// The rule step, before and independent of the model (#95, #117, #136): it writes due date,
    /// importance, urgency and — from a raw text captured before — duration and contexts the way
    /// `EnrichmentWriter` writes a model value — same field source, same revision — but leaves
    /// `processedAt` alone, because that marker means "the model has seen this task" (ADR-4). Each
    /// field only while it is still empty, so the catch-up pass adds no second revision (#95 AC-8,
    /// #117 AC-6, #136 AC-8). The four steps are independent of each other.
    private func applyRules(
        to task: TaskItem,
        recognitionPool: [RecognitionRule.Candidate],
        tasksByID: [UUID: TaskItem]
    ) {
        applyDueDateRule(to: task)
        applyImportanceRule(to: task)
        applyUrgencyRule(to: task)
        applyRecognitionRule(to: task, pool: recognitionPool, tasksByID: tasksByID)
    }

    private func applyDueDateRule(to task: TaskItem) {
        guard task.dueDate == nil,
              let match = DueDateRule.match(in: task.rawText, reference: task.capturedAt) else { return }
        let revision = Revision(
            task: task,
            field: .dueDate,
            oldValue: nil,
            newValue: match.guess.value.ISO8601Format(),
            author: .ai,
            reason: match.guess.reason
        )
        task.revisions = (task.revisions ?? []) + [revision]
        task.dueDate = match.guess.value
        task.dueHasTime = match.hasTime
        task.dueSourceRaw = FieldSource.ai.rawValue
        task.dueConfidence = match.guess.confidence
        logger.info("Rule set due date for \(task.id, privacy: .public)")
    }

    private func applyImportanceRule(to task: TaskItem) {
        guard task.importance == nil,
              let guess = ImportanceUrgencyRule.matchImportance(in: task.rawText) else { return }
        let revision = Revision(
            task: task,
            field: .importance,
            oldValue: nil,
            newValue: guess.value.rawValue,
            author: .ai,
            reason: guess.reason
        )
        task.revisions = (task.revisions ?? []) + [revision]
        task.importance = guess.value
        task.importanceSourceRaw = FieldSource.ai.rawValue
        task.importanceConfidence = guess.confidence
        logger.info("Rule set importance for \(task.id, privacy: .public)")
    }

    private func applyUrgencyRule(to task: TaskItem) {
        guard task.urgency == nil,
              let guess = ImportanceUrgencyRule.matchUrgency(in: task.rawText) else { return }
        let revision = Revision(
            task: task,
            field: .urgency,
            oldValue: nil,
            newValue: guess.value.rawValue,
            author: .ai,
            reason: guess.reason
        )
        task.revisions = (task.revisions ?? []) + [revision]
        task.urgency = guess.value
        task.urgencySourceRaw = FieldSource.ai.rawValue
        task.urgencyConfidence = guess.confidence
        logger.info("Rule set urgency for \(task.id, privacy: .public)")
    }

    /// The comparison set for the recognition, fetched once per pass and from **already processed**
    /// tasks only (#136): a task of this very catch-up pass can structurally never feed another one,
    /// so an AI mistake cannot multiply — no runtime filter needed, it follows from the fetch. No
    /// `done` filter either: a re-capture should take the values of a still open task too, unlike
    /// `examples`. The map resolves a hit back to its `TaskContext` objects.
    private static func recognitionInputs(
        in context: ModelContext
    ) throws -> (pool: [RecognitionRule.Candidate], tasksByID: [UUID: TaskItem]) {
        let processed = try context.fetch(FetchDescriptor<TaskItem>(predicate: #Predicate { $0.processedAt != nil }))
        return (recognitionCandidates(in: processed),
                Dictionary(processed.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first }))
    }

    private static func recognitionCandidates(in tasks: [TaskItem]) -> [RecognitionRule.Candidate] {
        tasks.map { task in
            RecognitionRule.Candidate(
                id: task.id,
                rawText: task.rawText,
                duration: task.duration,
                durationSourceRaw: task.durationSourceRaw,
                contextNames: (task.contexts ?? []).map(\.name),
                contextsSourceRaw: task.contextsSourceRaw
            )
        }
    }

    /// Takes duration and contexts of a task whose raw text carries the same word set (#136, ADR-5).
    /// Contexts come over as the neighbour's `TaskContext` objects — same store, so no name can drift,
    /// unlike the name match in `EnrichmentWriter`. Energy stays untouched: the rule does not know it.
    private func applyRecognitionRule(
        to task: TaskItem, pool: [RecognitionRule.Candidate], tasksByID: [UUID: TaskItem]
    ) {
        guard let match = RecognitionRule.match(rawText: task.rawText, in: pool) else { return }

        // Empty is not the same as emptied by the user: `FieldCodec` clears `durationSourceRaw` along
        // with the value (`FieldCodec.swift:56`), so the origin marker cannot tell a field the user
        // reset (`RevisionService`) from one that was never set — only the user `Revision` can, and
        // revisions are never deleted (ADR-5: "corrections by the user stay first-class examples").
        if task.duration == nil, !EnrichmentWriter.userHasTouched(.duration, on: task),
           let hit = match.duration {
            let revision = Revision(
                task: task, field: .duration, oldValue: nil,
                newValue: hit.guess.value.rawValue, author: .ai, reason: hit.guess.reason
            )
            task.revisions = (task.revisions ?? []) + [revision]
            task.duration = hit.guess.value
            task.durationSourceRaw = FieldSource.ai.rawValue
            task.durationConfidence = hit.guess.confidence
            logger.info("Recognition set duration for \(task.id, privacy: .public)")
        }

        // An empty relationship counts as unset: SwiftData hands a to-many relationship back as an
        // empty array as readily as `nil`, and both mean "no context yet". Same second condition as
        // above, for the same reason: `FieldCodec` clears `contextsSourceRaw` when the list becomes
        // empty (`FieldCodec.swift:65`), so only a user `Revision` marks a list the user cleared.
        if (task.contexts ?? []).isEmpty, !EnrichmentWriter.userHasTouched(.contexts, on: task),
           let hit = match.contexts, let source = tasksByID[hit.sourceID] {
            let revision = Revision(
                task: task, field: .contexts, oldValue: nil,
                newValue: EnrichmentWriter.encode(hit.guess.value), author: .ai, reason: hit.guess.reason
            )
            task.revisions = (task.revisions ?? []) + [revision]
            task.contexts = source.contexts
            task.contextsSourceRaw = FieldSource.ai.rawValue
            task.contextsConfidence = hit.guess.confidence
            logger.info("Recognition set contexts for \(task.id, privacy: .public)")
        }
    }

    /// The most recent completed tasks with their final attributes, by recency. The similarity-picked
    /// examples ADR-5 once promised are gone (B1 decided 2026-09-27): measured word overlap only
    /// carries where the text recurs almost verbatim, and that case is `RecognitionRule` (#136).
    static func examples(in context: ModelContext, limit: Int = exampleLimit) throws -> [EnrichmentExample] {
        let done = TaskStatus.done.rawValue
        var descriptor = FetchDescriptor<TaskItem>(
            predicate: #Predicate { $0.statusRaw == done },
            sortBy: [SortDescriptor(\.completedAt, order: .reverse)]
        )
        descriptor.fetchLimit = limit
        return try context.fetch(descriptor).map { task in
            EnrichmentExample(
                rawText: task.rawText,
                title: task.title,
                importance: task.importance,
                urgency: task.urgency,
                duration: task.duration,
                energy: task.energy,
                contexts: (task.contexts ?? []).map(\.name)
            )
        }
    }
}
