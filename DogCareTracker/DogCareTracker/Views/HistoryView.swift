import SwiftUI

// =============================================================================
// HistoryView.swift
// =============================================================================
// Durable audit trail for dog care.
//
// Why this matters:
// - Mike needs confidence that walks/feedings were actually logged.
// - Reviewing a day or week should be easy.
// - Deleting mistakes must be possible without digging into storage.
// =============================================================================

struct HistoryView: View {
    @ObservedObject var store: DogCareStore

    var body: some View {
        NavigationStack {
            List {
                if store.groupedEvents.isEmpty {
                    ContentUnavailableView(
                        "No history yet",
                        systemImage: "clock.arrow.circlepath",
                        description: Text("Log a walk or feeding from the Dashboard and it will appear here.")
                    )
                } else {
                    ForEach(store.groupedEvents, id: \.date) { section in
                        Section {
                            ForEach(section.events) { event in
                                EventRowView(event: event)
                            }
                            .onDelete { offsets in
                                store.deleteEvents(at: offsets, within: section.events)
                            }
                        } header: {
                            Text(section.date.formatted(date: .abbreviated, time: .omitted))
                        } footer: {
                            Text(summaryFooter(for: section.events))
                        }
                    }
                }
            }
            .navigationTitle("History")
        }
    }

    /// Small daily footer so each section tells a story at a glance.
    private func summaryFooter(for events: [CareEvent]) -> String {
        let walks = events.filter { $0.kind == .walk }.count
        let feedings = events.filter { $0.kind == .feeding }.count
        let minutes = events.compactMap(\.durationMinutes).reduce(0, +)
        return "\(walks) walk(s), \(feedings) feeding(s), \(minutes) total walk minutes"
    }
}
