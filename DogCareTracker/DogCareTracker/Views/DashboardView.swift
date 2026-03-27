import SwiftUI

// =============================================================================
// DashboardView.swift
// =============================================================================
// Home screen for the app.
//
// What this screen optimizes for:
// - one-glance awareness of today's care activity
// - ultra-fast logging for walks and feedings
// - obvious overdue / due-soon status
// - a simple timeline that feels useful immediately
// =============================================================================

struct DashboardView: View {
    @ObservedObject var store: DogCareStore

    @State private var showingFeedingSheet = false
    @State private var showingManualWalkSheet = false
    @State private var showingFinishWalkSheet = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    headerCard
                    statusCards
                    quickActionsCard
                    todaySummaryCard
                    timelineCard
                    if let lastError = store.lastError, !lastError.isEmpty {
                        errorCard(lastError)
                    }
                }
                .padding()
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Dog Care")
            .sheet(isPresented: $showingFeedingSheet) {
                FeedingEntryView(store: store)
            }
            .sheet(isPresented: $showingManualWalkSheet) {
                ManualWalkEntryView(store: store)
            }
            .sheet(isPresented: $showingFinishWalkSheet) {
                FinishWalkView(store: store)
            }
        }
    }

    /// Hero card with dog name and the highest-value current context.
    private var headerCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(store.profile.dogName)
                .font(.largeTitle.weight(.bold))

            Text("Walking and feeding tracker")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            Divider()

            if let activeWalk = store.activeWalk {
                VStack(alignment: .leading, spacing: 6) {
                    Label("Walk in progress", systemImage: "figure.walk")
                        .font(.headline)
                    TimelineView(.periodic(from: .now, by: 60)) { context in
                        let minutes = max(Int(context.date.timeIntervalSince(activeWalk.startedAt) / 60), 0)
                        Text("Started \(activeWalk.startedAt.formatted(date: .omitted, time: .shortened)) · \(minutes) min so far")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
            } else {
                Text("No walk running right now")
                    .font(.headline)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    /// High-signal status row for feeding + walking cadence.
    private var statusCards: some View {
        HStack(spacing: 12) {
            statusCard(
                title: "Walk status",
                value: store.walkStatusText,
                systemImage: "figure.walk"
            )

            statusCard(
                title: "Feeding status",
                value: store.feedingStatusText,
                systemImage: "fork.knife"
            )
        }
    }

    private func statusCard(title: String, value: String, systemImage: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: systemImage)
                .font(.headline)
            Text(value)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    /// Fastest logging actions live here.
    private var quickActionsCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Quick actions")
                .font(.headline)

            if store.activeWalk == nil {
                Button {
                    store.startWalk()
                } label: {
                    actionRow(title: "Start walk", subtitle: "Begin a live walk timer", systemImage: "play.fill")
                }
                .buttonStyle(.plain)
            } else {
                Button {
                    showingFinishWalkSheet = true
                } label: {
                    actionRow(title: "Finish current walk", subtitle: "Log relief status and notes", systemImage: "checkmark.circle.fill")
                }
                .buttonStyle(.plain)
            }

            Button {
                showingManualWalkSheet = true
            } label: {
                actionRow(title: "Log manual walk", subtitle: "For walks you forgot to start in-app", systemImage: "clock.arrow.circlepath")
            }
            .buttonStyle(.plain)

            Button {
                showingFeedingSheet = true
            } label: {
                actionRow(title: "Log feeding", subtitle: "Record meal, amount, and notes", systemImage: "fork.knife.circle.fill")
            }
            .buttonStyle(.plain)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    private func actionRow(title: String, subtitle: String, systemImage: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.title3)
                .frame(width: 32)
                .foregroundStyle(Color.accentColor)

            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.body.weight(.semibold))
                Text(subtitle)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.footnote.weight(.bold))
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 6)
    }

    /// Dashboard totals for the current day.
    private var todaySummaryCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Today")
                .font(.headline)

            HStack(spacing: 12) {
                metricCard(title: "Walks", value: "\(store.todaysWalkCount)")
                metricCard(title: "Walk min", value: "\(store.todaysWalkMinutes)")
                metricCard(title: "Feedings", value: "\(store.todaysFeedingCount)")
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    private func metricCard(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title2.weight(.bold))
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    /// Human-readable timeline for today's activity.
    private var timelineCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Today's timeline")
                .font(.headline)

            if store.todaysEvents.isEmpty {
                Text("No events logged today yet.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(store.todaysEvents) { event in
                    EventRowView(event: event)
                    if event.id != store.todaysEvents.last?.id {
                        Divider()
                    }
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    private func errorCard(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Save warning", systemImage: "exclamationmark.triangle.fill")
                .font(.headline)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.red.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

// =============================================================================
// Reusable event row
// =============================================================================

struct EventRowView: View {
    let event: CareEvent

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: event.kind.systemImage)
                .font(.title3)
                .frame(width: 28)
                .foregroundStyle(Color.accentColor)

            VStack(alignment: .leading, spacing: 5) {
                Text(title)
                    .font(.body.weight(.semibold))
                Text(subtitle)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                if !event.notes.isEmpty {
                    Text(event.notes)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()
        }
    }

    private var title: String {
        switch event.kind {
        case .walk:
            return event.isActiveWalk ? "Walk in progress" : "Walk"
        case .feeding:
            return event.mealKind?.title ?? "Feeding"
        }
    }

    private var subtitle: String {
        switch event.kind {
        case .walk:
            let timeText = event.startedAt.formatted(date: .omitted, time: .shortened)
            let durationText = event.durationMinutes.map { " · \($0) min" } ?? ""
            let reliefText = event.reliefStatus.map { " · \($0.title)" } ?? ""
            return "\(timeText)\(durationText)\(reliefText)"
        case .feeding:
            let meal = event.mealKind?.title ?? "Meal"
            let amount = event.amountDescription ?? ""
            let timeText = event.startedAt.formatted(date: .omitted, time: .shortened)
            return "\(meal) · \(amount) · \(timeText)"
        }
    }
}

// =============================================================================
// Feeding sheet
// =============================================================================

struct FeedingEntryView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var store: DogCareStore

    @State private var mealKind: MealKind = .breakfast
    @State private var amount: String = ""
    @State private var notes: String = ""
    @State private var timestamp: Date = .now

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Meal", selection: $mealKind) {
                        ForEach(MealKind.allCases) { meal in
                            Text(meal.title).tag(meal)
                        }
                    }

                    TextField("Amount", text: $amount, prompt: Text(store.profile.defaultMealAmount))
                    DatePicker("Time", selection: $timestamp)
                    TextField("Notes", text: $notes, axis: .vertical)
                        .lineLimit(3...6)
                } header: {
                    Text("Feeding")
                } footer: {
                    Text("Log what was fed, when it happened, and anything worth remembering.")
                }
            }
            .navigationTitle("Log feeding")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") {
                        store.addFeeding(mealKind: mealKind, amount: amount, notes: notes, at: timestamp)
                        dismiss()
                    }
                }
            }
        }
    }
}

// =============================================================================
// Manual walk sheet
// =============================================================================

struct ManualWalkEntryView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var store: DogCareStore

    @State private var durationMinutes: Int = 20
    @State private var reliefStatus: WalkReliefStatus = .both
    @State private var endedAt: Date = .now
    @State private var notes: String = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Stepper("Duration: \(durationMinutes) min", value: $durationMinutes, in: 1...240, step: 1)
                    Picker("Relief", selection: $reliefStatus) {
                        ForEach(WalkReliefStatus.allCases) { status in
                            Text(status.title).tag(status)
                        }
                    }
                    DatePicker("Ended at", selection: $endedAt)
                    TextField("Notes", text: $notes, axis: .vertical)
                        .lineLimit(3...6)
                } header: {
                    Text("Walk details")
                } footer: {
                    Text("Use manual entry when you already finished the walk before opening the app.")
                }
            }
            .navigationTitle("Manual walk")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") {
                        store.addManualWalk(durationMinutes: durationMinutes, reliefStatus: reliefStatus, notes: notes, endedAt: endedAt)
                        dismiss()
                    }
                }
            }
        }
    }
}

// =============================================================================
// Finish active walk sheet
// =============================================================================

struct FinishWalkView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var store: DogCareStore

    @State private var reliefStatus: WalkReliefStatus = .both
    @State private var notes: String = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Relief", selection: $reliefStatus) {
                        ForEach(WalkReliefStatus.allCases) { status in
                            Text(status.title).tag(status)
                        }
                    }
                    TextField("Notes", text: $notes, axis: .vertical)
                        .lineLimit(3...6)
                } header: {
                    Text("Finish walk")
                } footer: {
                    Text("Close the active walk and record what happened.")
                }
            }
            .navigationTitle("Finish walk")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") {
                        store.finishWalk(reliefStatus: reliefStatus, notes: notes)
                        dismiss()
                    }
                }
            }
        }
    }
}
