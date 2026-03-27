// =============================================================================
// AppDelegate.swift
// ios-deploy-kit — UIApplicationDelegate for APNs token delivery
// =============================================================================
//
// PURPOSE:
//   SwiftUI apps don't have an AppDelegate by default, but APNs token delivery
//   requires UIApplicationDelegate callbacks. This file bridges them.
//
// USAGE:
//   In your @main App struct:
//
//     @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
//
//   Then in your app's .task { } modifier:
//
//     AppDelegate.pushManager = PushNotificationManager()
//     AppDelegate.pushManager?.register()
//
// =============================================================================

import UIKit

class AppDelegate: NSObject, UIApplicationDelegate {

    /// Shared push manager. Set this before UIApplication registers for APNs.
    static var pushManager: PushNotificationManager?

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        AppDelegate.pushManager?.didRegister(token: deviceToken)
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        AppDelegate.pushManager?.didFailToRegister(error: error)
    }
}
