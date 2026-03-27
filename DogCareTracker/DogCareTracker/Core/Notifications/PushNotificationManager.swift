// =============================================================================
// PushNotificationManager.swift
// ios-deploy-kit — Generic APNs Push Registration & OTA Install Trigger
// =============================================================================
//
// PURPOSE:
//   Registers for remote push notifications with APNs, receives the device
//   token, and sends it to the deploy server so it can push OTA update
//   notifications to this device.
//
// SETUP:
//   1. Add "DeployWebhookURL" key to Info.plist pointing to your deploy server's
//      /api/deploy/device-token endpoint.
//   2. Include AppDelegate.swift in your project.
//   3. In your @main App struct: @UIApplicationDelegateAdaptor(AppDelegate.self)
//   4. Call AppDelegate.pushManager?.register() in your app's .task { } modifier.
//
// FLOW:
//   App launches → register() → iOS prompts for permission → APNs returns token
//   → sendTokenToServer() → server stores token → build deploys → APNs push sent
//   → user taps notification → UIApplication.open(itms-services://) → iOS installs
//
// INFO.PLIST KEY:
//   <key>DeployWebhookURL</key>
//   <string>https://myapp.example.com/api/deploy/device-token</string>
//
// =============================================================================

import UIKit
import UserNotifications

/// Manages APNs push notification registration and device token delivery.
@Observable
final class PushNotificationManager: NSObject, UNUserNotificationCenterDelegate {

    /// The hex-encoded APNs device token (nil until registration succeeds).
    private(set) var deviceToken: String?

    /// Registration error message (nil if successful).
    private(set) var registrationError: String?

    /// Token endpoint — read from Info.plist key "DeployWebhookURL".
    private let tokenEndpoint: String = {
        Bundle.main.object(forInfoDictionaryKey: "DeployWebhookURL") as? String
            ?? ""
    }()

    /// Register for remote push notifications.
    func register() {
        guard !tokenEndpoint.isEmpty else {
            print("[Push] DeployWebhookURL not set in Info.plist — push registration skipped")
            return
        }
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(
            options: [.alert, .sound, .badge]
        ) { granted, error in
            if let error {
                self.registrationError = error.localizedDescription
                return
            }
            if granted {
                DispatchQueue.main.async {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
        }
    }

    /// Called by AppDelegate when APNs registration succeeds.
    func didRegister(token: Data) {
        let hex = token.map { String(format: "%02x", $0) }.joined()
        deviceToken       = hex
        registrationError = nil
        sendTokenToServer(hex)
    }

    /// Called by AppDelegate when APNs registration fails.
    func didFailToRegister(error: Error) {
        registrationError = error.localizedDescription
        print("[Push] Registration failed: \(error.localizedDescription)")
    }

    /// POST the device token to the deploy server.
    private func sendTokenToServer(_ token: String) {
        guard let url = URL(string: tokenEndpoint) else {
            print("[Push] Invalid token endpoint URL: \(tokenEndpoint)")
            return
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let bundleId = Bundle.main.bundleIdentifier ?? ""
        request.httpBody    = try? JSONEncoder().encode(["token": token, "bundle_id": bundleId])
        request.timeoutInterval = 10

        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error {
                print("[Push] Token send failed: \(error.localizedDescription)")
                return
            }
            if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                print("[Push] Device token registered with deploy server")
            }
        }.resume()
    }

    // MARK: - UNUserNotificationCenterDelegate

    /// Show notification banner even when app is in the foreground.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .badge])
    }

    /// Handle notification tap — open itms-services:// URL for native install.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo

        if let installURL = userInfo["install_url"] as? String,
           let url = URL(string: installURL) {
            DispatchQueue.main.async {
                UIApplication.shared.open(url)
            }
        }

        completionHandler()
    }
}
