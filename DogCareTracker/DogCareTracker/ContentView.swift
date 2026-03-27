import SwiftUI

// =============================================================================
// ContentView.swift
// =============================================================================
// Root user-facing shell for the app.
//
// This keeps the app dead simple:
// - Dashboard for logging and today's status
// - History for reviewing care activity
// - Settings for dog-specific timing/preferences
// =============================================================================

struct ContentView: View {
    @StateObject private var store = DogCareStore()

    var body: some View {
        TabView {
            DashboardView(store: store)
                .tabItem {
                    Label("Dashboard", systemImage: "house.fill")
                }

            HistoryView(store: store)
                .tabItem {
                    Label("History", systemImage: "clock.fill")
                }

            SettingsView(store: store)
                .tabItem {
                    Label("Settings", systemImage: "gearshape.fill")
                }
        }
        .tint(Color.accentColor)
    }
}
