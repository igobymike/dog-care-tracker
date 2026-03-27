import Foundation
import SwiftUI

// =============================================================================
// DogCareStore.swift
// =============================================================================
// This file owns the app's local state, persistence, and derived dashboard
// summaries.
//
// Why JSON file storage for MVP:
// - Works offline.
// - No database migration burden on day one.
// - Easy to inspect and debug.
// - Easy to replace later with SwiftData or CloudKit if the product grows.
// =============================================================================

/// Central state container for the app.
///
/// The UI reads from this object, and every mutation funnels through here so we
/// have one consistent place for persistence and business logic.
@MainActor
final class DogCareStore: ObservableObject {
    /// Current dog settings / preferences.
    @Published var profile: DogProfile

    /// Timeline of walks and feedings.
    @Published var events: [CareEvent]

    /// Convenient user-facing error hook.
    @Published var lastError: String?

    /// JSON encoder used for file persistence.
    private let encoder: JSONEncoder

    /// JSON decoder used to load state.
    private let decoder: JSONDecoder

    init() {
        self.encoder = JSONEncoder()
        self.decoder = JSONDecoder()

        // Human-readable dates make debugging saved files much easier.
        self.encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        self.encoder.dateEncodingStrategy = .iso8601
        self.decoder.dateDecodingStrategy = .iso8601

        // Load persisted state if it exists; otherwise start with sensible
        // defaults so the app is immediately usable.
        if let snapshot = Self.loadSnapshot(decoder: decoder) {
            self.profile = snapshot.profile
            self.events = snapshot.events.sorted(by: { $0.startedAt > $1.startedAt })
        } else {
            self.profile = .default
            self.events = []
        }
    }

    // MARK: - Derived state

    /// The currently active walk, if Mike started one and has not ended it yet.
    var activeWalk: CareEvent? {
        events.first(where: { $0.isActiveWalk })
    }

    /// Feedings and walks that started today in the user's local calendar.
    var todaysEvents: [CareEvent] {
        events.filter { Calendar.current.isDateInToday($0.startedAt) }
            .sorted(by: { $0.startedAt > $1.startedAt })
    }

    /// Daily walk total in minutes.
    var todaysWalkMinutes: Int {
        todaysEvents
            .filter { $0.kind == .walk }
            .compactMap { $0.durationMinutes }
            .reduce(0, +)
    }

    /// Count of today's completed or active walks.
    var todaysWalkCount: Int {
        todaysEvents.filter { $0.kind == .walk }.count
    }

    /// Count of today's feedings.
    var todaysFeedingCount: Int {
        todaysEvents.filter { $0.kind == .feeding }.count
    }

    /// Most recent feeding time, if one exists.
    var lastFeeding: CareEvent? {
        events.first(where: { $0.kind == .feeding })
    }

    /// Most recent walk event, active or completed.
    var lastWalk: CareEvent? {
        events.first(where: { $0.kind == .walk })
    }

    /// How the feeding schedule looks right now.
    var feedingStatusText: String {
        guard let lastFeeding else {
            return "No feeding logged yet"
        }

        let hoursSince = Date().timeIntervalSince(lastFeeding.startedAt) / 3600
        if hoursSince >= profile.feedingReminderHours {
            return "Feeding overdue"
        }

        let remaining = max(profile.feedingReminderHours - hoursSince, 0)
        return String(format: "Next feeding due in %.1f h", remaining)
    }

    /// How the walking schedule looks right now.
    var walkStatusText: String {
        if activeWalk != nil {
            return "Walk in progress"
        }

        guard let lastWalk else {
            return "No walk logged yet"
        }

        let referenceDate = lastWalk.endedAt ?? lastWalk.startedAt
        let hoursSince = Date().timeIntervalSince(referenceDate) / 3600
        if hoursSince >= profile.walkReminderHours {
            return "Walk overdue"
        }

        let remaining = max(profile.walkReminderHours - hoursSince, 0)
        return String(format: "Next walk due in %.1f h", remaining)
    }

    /// Timeline grouped by local day for the history screen.
    var groupedEvents: [(date: Date, events: [CareEvent])] {
        let grouped = Dictionary(grouping: events) { event in
            Calendar.current.startOfDay(for: event.startedAt)
        }

        return grouped
            .map { key, value in
                (date: key, events: value.sorted(by: { $0.startedAt > $1.startedAt }))
            }
            .sorted(by: { $0.date > $1.date })
    }

    // MARK: - Mutations

    /// Start a new live walk if one isn't already running.
    func startWalk(now: Date = Date()) {
        guard activeWalk == nil else { return }

        let event = CareEvent(kind: .walk, startedAt: now)
        events.insert(event, at: 0)
        persist()
    }

    /// Finish the current active walk.
    func finishWalk(reliefStatus: WalkReliefStatus, notes: String, now: Date = Date()) {
        guard let activeWalk, let index = events.firstIndex(where: { $0.id == activeWalk.id }) else {
            return
        }

        events[index].endedAt = now
        events[index].reliefStatus = reliefStatus
        events[index].notes = notes.trimmingCharacters(in: .whitespacesAndNewlines)
        sortAndPersist()
    }

    /// Manual walk entry for cases where Mike forgot to press start.
    func addManualWalk(durationMinutes: Int, reliefStatus: WalkReliefStatus, notes: String, endedAt: Date = Date()) {
        let safeDuration = max(durationMinutes, 1)
        let startedAt = endedAt.addingTimeInterval(TimeInterval(-safeDuration * 60))

        let event = CareEvent(
            kind: .walk,
            startedAt: startedAt,
            endedAt: endedAt,
            notes: notes.trimmingCharacters(in: .whitespacesAndNewlines),
            reliefStatus: reliefStatus
        )

        events.append(event)
        sortAndPersist()
    }

    /// Feeding log entry.
    func addFeeding(mealKind: MealKind, amount: String, notes: String, at date: Date = Date()) {
        let cleanedAmount = amount.trimmingCharacters(in: .whitespacesAndNewlines)
        let event = CareEvent(
            kind: .feeding,
            startedAt: date,
            notes: notes.trimmingCharacters(in: .whitespacesAndNewlines),
            mealKind: mealKind,
            amountDescription: cleanedAmount.isEmpty ? profile.defaultMealAmount : cleanedAmount
        )

        events.append(event)
        sortAndPersist()
    }

    /// Allow deletion from the history view.
    func deleteEvents(at offsets: IndexSet, within source: [CareEvent]) {
        let idsToDelete = offsets.compactMap { source[$0].id }
        events.removeAll { idsToDelete.contains($0.id) }
        sortAndPersist()
    }

    /// Save updated settings.
    func updateProfile(_ profile: DogProfile) {
        self.profile = profile
        persist()
    }

    // MARK: - Persistence

    /// Sort events newest-first and then save to disk.
    private func sortAndPersist() {
        events.sort(by: { $0.startedAt > $1.startedAt })
        persist()
    }

    /// Write the current snapshot to local storage.
    private func persist() {
        do {
            let snapshot = DogCareSnapshot(profile: profile, events: events)
            let data = try encoder.encode(snapshot)
            try data.write(to: Self.snapshotURL, options: [.atomic])
            lastError = nil
        } catch {
            lastError = "Failed to save dog-care data: \(error.localizedDescription)"
        }
    }

    /// Fixed file location in the app's documents directory.
    private static var snapshotURL: URL {
        FileManager.default
            .urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("dog-care-snapshot.json")
    }

    /// Best-effort startup loader.
    private static func loadSnapshot(decoder: JSONDecoder) -> DogCareSnapshot? {
        let url = snapshotURL
        guard FileManager.default.fileExists(atPath: url.path) else {
            return nil
        }

        do {
            let data = try Data(contentsOf: url)
            return try decoder.decode(DogCareSnapshot.self, from: data)
        } catch {
            return nil
        }
    }
}
