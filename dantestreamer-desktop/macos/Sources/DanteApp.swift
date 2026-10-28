import SwiftUI

@main
struct DanteStreamerControllerApp: App {
    @StateObject private var connectionManager = ConnectionManager()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(connectionManager)
        }
        .windowStyle(.automatic)
        .commands {
            CommandGroup(replacing: .appSettings) {
                NavigationLink(destination: SettingsView()) {
                    Text("Settings...")
                }
                .keyboardShortcut(",", modifiers: .command)
            }
        }
    }
}
