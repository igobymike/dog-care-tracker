import Foundation

// =============================================================================
// CareModels.swift
// =============================================================================
// This file defines the core data structures for the Dog Care app.
//
// Design goals:
// - Keep the data model simple enough to persist as JSON without extra database
//   dependencies in MVP phase 1.
// - Capture the real-world actions Mike asked for first: walks, feedings,
//   timing, notes, and quick daily review.
// - Leave enough flexibility for future upgrades like cloud sync, multiple dogs,
//   richer analytics, and reminders without forcing a rewrite.
// =============================================================================

/// The two core event types we care about in the MVP.
///
/// We intentionally keep the enum small and explicit. The app is about tracking
/// the two highest-value care actions first: feeding and walking.
enum CareEventKind: String, Codable, CaseIterable, Identifiable {
    case walk
    case feeding

    var id: String { rawValue }

    /// User-facing label for the UI.
    var title: String {
        switch self {
        case .walk:
            return "Walk"
        case .feeding:
            return "Feeding"
        }
    }

    /// SF Symbol used for dashboards and history rows.
    var systemImage: String {
        switch self {
        case .walk:
            return "figure.walk"
        case .feeding:
            return "fork.knife"
        }
    }
}

/// Simple meal buckets so logging stays fast.
///
/// We do NOT over-model nutrition in v1. Mike needs speed and consistency more
/// than a veterinary-grade nutrition schema on day one.
enum MealKind: String, Codable, CaseIterable, Identifiable {
    case breakfast
    case lunch
    case dinner
    case snack

    var id: String { rawValue }

    var title: String {
        rawValue.capitalized
    }
}

/// Lightweight summary of what happened on a walk.
///
/// This is intentionally human-friendly. The app wants "pee / poop / both /
/// neither" because that's how people actually remember and communicate walks.
enum WalkReliefStatus: String, Codable, CaseIterable, Identifiable {
    case none
    case pee
    case poop
    case both

    var id: String { rawValue }

    var title: String {
        switch self {
        case .none:
            return "No relief"
        case .pee:
            return "Pee"
        case .poop:
            return "Poop"
        case .both:
            return "Pee + poop"
        }
    }
}

/// One row in the dog-care timeline.
///
/// Rather than split into multiple database tables, we use a single timeline
/// event with optional fields for walk/feed specifics. That keeps persistence
/// dead simple while still allowing useful dashboards.
struct CareEvent: Identifiable, Codable, Equatable {
    /// Stable unique identifier for list rendering and persistence.
    let id: UUID

    /// Walk or feeding.
    var kind: CareEventKind

    /// Primary timestamp for the event.
    /// - For feeding: this is the meal time.
    /// - For walking: this is the walk start time.
    var startedAt: Date

    /// End time for a walk. Feedings leave this nil.
    var endedAt: Date?

    /// Freeform operator notes.
    var notes: String

    /// Feeding-specific fields.
    var mealKind: MealKind?
    var amountDescription: String?

    /// Walk-specific summary.
    var reliefStatus: WalkReliefStatus?

    /// Creation timestamp for auditability.
    var createdAt: Date

    init(
        id: UUID = UUID(),
        kind: CareEventKind,
        startedAt: Date,
        endedAt: Date? = nil,
        notes: String = "",
        mealKind: MealKind? = nil,
        amountDescription: String? = nil,
        reliefStatus: WalkReliefStatus? = nil,
        createdAt: Date = Date()
    ) {
        self.id = id
        self.kind = kind
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.notes = notes
        self.mealKind = mealKind
        self.amountDescription = amountDescription
        self.reliefStatus = reliefStatus
        self.createdAt = createdAt
    }

    /// True when a walk has started but not ended yet.
    var isActiveWalk: Bool {
        kind == .walk && endedAt == nil
    }

    /// Best-effort duration in minutes for completed walks.
    var durationMinutes: Int? {
        guard kind == .walk, let endedAt else { return nil }
        return max(Int(endedAt.timeIntervalSince(startedAt) / 60), 0)
    }
}

/// Per-dog settings that influence dashboard summaries and overdue indicators.
///
/// This is a single-dog app in v1, but the name keeps the design obvious for
/// later expansion to multiple pets if Mike wants it.
struct DogProfile: Codable, Equatable {
    var dogName: String
    var walkReminderHours: Double
    var feedingReminderHours: Double
    var defaultMealAmount: String

    static let `default` = DogProfile(
        dogName: "Moose",
        walkReminderHours: 6,
        feedingReminderHours: 12,
        defaultMealAmount: "1 meal"
    )
}

/// The persisted snapshot written to disk.
///
/// Keeping one top-level snapshot makes migration straightforward later.
struct DogCareSnapshot: Codable {
    var profile: DogProfile
    var events: [CareEvent]
}
