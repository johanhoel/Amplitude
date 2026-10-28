import SwiftUI

struct ContentView: View {
    @EnvironmentObject var connectionManager: ConnectionManager
    @State private var showAddInstance = false

    var body: some View {
        NavigationSplitView {
            // Sidebar: Instance list
            List(selection: Binding(
                get: { connectionManager.selectedInstance?.id },
                set: { id in
                    connectionManager.selectedInstance = connectionManager.instances.first(where: { $0.id == id })
                }
            )) {
                if connectionManager.instances.isEmpty {
                    VStack(alignment: .center, spacing: 12) {
                        Image(systemName: "wifi")
                            .font(.system(size: 32))
                            .foregroundColor(.gray)
                        Text("No instances")
                            .font(.headline)
                        Text("Add a DanteStreamer instance to get started")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                } else {
                    ForEach(connectionManager.instances) { instance in
                        InstanceRow(instance: instance)
                            .tag(instance.id)
                    }
                    .onDelete { indices in
                        indices.forEach { i in
                            connectionManager.removeInstance(connectionManager.instances[i])
                        }
                    }
                }
            }
            .listStyle(.sidebar)
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button(action: { showAddInstance = true }) {
                        Image(systemName: "plus")
                    }
                    .sheet(isPresented: $showAddInstance) {
                        AddInstanceView()
                            .environmentObject(connectionManager)
                    }
                }
            }
            .navigationTitle("Instances")
        } detail: {
            if let instance = connectionManager.selectedInstance {
                DetailView(instance: instance)
                    .environmentObject(connectionManager)
            } else {
                VStack(spacing: 16) {
                    Image(systemName: "globe")
                        .font(.system(size: 48))
                        .foregroundColor(.gray)
                    Text("Select an instance")
                        .font(.headline)
                    Text("Choose a DanteStreamer instance from the sidebar")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .onAppear {
            // Auto-connect to last used instance
            if let last = connectionManager.instances.first {
                Task {
                    await connectionManager.connect(to: last)
                }
            }
        }
    }
}

struct InstanceRow: View {
    let instance: DanteInstance
    @EnvironmentObject var connectionManager: ConnectionManager

    var body: some View {
        HStack {
            VStack(alignment: .leading) {
                Text(instance.name)
                    .font(.body)
                Text("\(instance.host):\(instance.port)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Spacer()
            if connectionManager.selectedInstance?.id == instance.id && connectionManager.isConnected {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)
            }
        }
        .contentShape(Rectangle())
    }
}

#Preview {
    ContentView()
        .environmentObject(ConnectionManager())
}
