import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var connectionManager: ConnectionManager

    var body: some View {
        NavigationStack {
            Form {
                Section("Instances") {
                    List(connectionManager.instances) { instance in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(instance.name)
                                    .font(.body)
                                Text("\(instance.host):\(instance.port)")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                            Button(action: {
                                connectionManager.removeInstance(instance)
                            }) {
                                Image(systemName: "xmark.circle")
                                    .foregroundColor(.red)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                Section("About") {
                    HStack {
                        Text("Version")
                        Spacer()
                        Text("1.0.0")
                            .foregroundColor(.secondary)
                    }
                }
            }
            .navigationTitle("Settings")
        }
    }
}

#Preview {
    SettingsView()
        .environmentObject(ConnectionManager())
}
