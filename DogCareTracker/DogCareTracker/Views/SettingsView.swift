import SwiftUI

// =============================================================================
// SettingsView.swift
// =============================================================================
// Small settings screen for the MVP.
//
// Why this exists in v1:
// - Different dogs need different feeding/walk cadence.
// - Mike should be able to rename the dog and adjust reminder windows without a
//   rebuild.
// - Keeping settings simple helps the dashboard produce more meaningful status.
// =============================================================================

struct SettingsView: View {
    @ObservedObject var store: DogCareStore

    @State private var draftProfile: DogProfile

    init(store: DogCareStore) {
        self.store = store
        self._draftProfile = State(initialValue: store.profile)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Dog name", text: $draftProfile.dogName)
                    TextField("Default meal amount", text: $draftProfile.defaultMealAmount)
                } header: {
                    Text("Dog")
                }

                Section {
                    Stepper(value: $draftProfile.walkReminderHours, in: 1...24, step: 0.5) {
                        Text(String(format: "Walk reminder every %.1f hours", draftProfile.walkReminderHours))
                    }

                    Stepper(value: $draftProfile.feedingReminderHours, in: 1...24, step: 0.5) {
                        Text(String(format: "Feeding reminder every %.1f hours", draftProfile.feedingReminderHours))
                    }
                } header: {
                    Text("Timing")
                } footer: {
                    Text("These settings drive the due/overdue status on the dashboard. They do not yet schedule native notifications.")
                }

                Section {
                    Button("Save settings") {
                        store.updateProfile(draftProfile)
                    }
                }
            }
            .navigationTitle("Settings")
            .onReceive(store.$profile) { profile in
                // If another part of the app updates the profile, keep the form
                // in sync instead of leaving the user with stale values.
                draftProfile = profile
            }
        }
    }
}
