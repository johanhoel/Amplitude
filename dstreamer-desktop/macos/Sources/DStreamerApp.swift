import AppKit
import SwiftUI

@main
struct DStreamerApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var manager = ConnectionManager()

    var body: some Scene {
        WindowGroup("DStreamer Controller") {
            ContentView()
                .environmentObject(manager)
                .frame(minWidth: 720, minHeight: 480)
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Needed when started with `swift run` outside an .app bundle.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}
