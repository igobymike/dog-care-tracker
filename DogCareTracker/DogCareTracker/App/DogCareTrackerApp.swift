import SwiftUI

@main
struct DogCareTrackerApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .task {
                    await autoConfigureIfNeeded()
                    AppDelegate.pushManager = PushNotificationManager()
                    AppDelegate.pushManager?.register()
                }
        }
    }

    /// Auto-configure on first launch by fetching pair config from the deploy server.
    ///
    /// Hits /api/deploy/pair-config over Tailscale (100.x.x.x IPs are allowed without
    /// auth by the deploy server). Reads DeployServerIP + DeployServerPort from Info.plist.
    /// Writes gatewayURL, bootstrapToken, cfAccessClientId/Secret to UserDefaults.
    /// @AppStorage("setupComplete") in your root view will react automatically.
    @MainActor
    private func autoConfigureIfNeeded() async {
        guard !UserDefaults.standard.bool(forKey: "setupComplete") else { return }
        guard let ip = Bundle.main.object(forInfoDictionaryKey: "DeployServerIP") as? String,
              !ip.isEmpty,
              let portStr = Bundle.main.object(forInfoDictionaryKey: "DeployServerPort") as? String,
              let port = Int(portStr),
              let url = URL(string: "http://\(ip):\(port)/api/deploy/pair-config")
        else { return }

        var req = URLRequest(url: url)
        req.timeoutInterval = 10

        guard let (data, _) = try? await URLSession.shared.data(for: req),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let gatewayURL = json["url"] as? String, !gatewayURL.isEmpty,
              let bootstrapToken = json["bootstrapToken"] as? String, !bootstrapToken.isEmpty
        else { return }

        UserDefaults.standard.set(gatewayURL, forKey: "gatewayURL")
        UserDefaults.standard.set(bootstrapToken, forKey: "bootstrapToken")
        if let cfId = json["cfAccessClientId"] as? String, !cfId.isEmpty {
            UserDefaults.standard.set(cfId, forKey: "cfAccessClientId")
        }
        if let cfSecret = json["cfAccessClientSecret"] as? String, !cfSecret.isEmpty {
            UserDefaults.standard.set(cfSecret, forKey: "cfAccessClientSecret")
        }
        UserDefaults.standard.set(true, forKey: "setupComplete")
    }
}
