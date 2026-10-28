import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var manager: ConnectionManager
    @State private var showAdd = false

    var body: some View {
        NavigationView {
            List(selection: $manager.selectedID) {
                Section("Instances") {
                    ForEach(manager.instances) { instance in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(instance.name).bold()
                            Text(instance.address).font(.caption).foregroundColor(.secondary)
                        }
                        .padding(.vertical, 2)
                        .tag(instance.id)
                    }
                }
            }
            .listStyle(.sidebar)
            .frame(minWidth: 220)
            .toolbar {
                ToolbarItemGroup {
                    Button { showAdd = true } label: { Label("Add", systemImage: "plus") }
                        .help("Add a DanteStreamer instance")
                    Button { manager.removeSelected() } label: { Label("Remove", systemImage: "minus") }
                        .help("Remove the selected instance")
                        .disabled(manager.selectedID == nil)
                }
            }

            DetailView()
        }
        .sheet(isPresented: $showAdd) {
            AddInstanceView { manager.add($0) }
        }
        .onAppear {
            if manager.instances.isEmpty { showAdd = true }
        }
    }
}

struct DetailView: View {
    @EnvironmentObject private var manager: ConnectionManager

    var body: some View {
        VStack(spacing: 0) {
            if let error = manager.error {
                Text(error)
                    .foregroundColor(.red)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                    .background(Color.red.opacity(0.1))
            }
            if let status = manager.status {
                TabView {
                    StatusTab(status: status).tabItem { Text("Status") }
                    MetersTab().tabItem { Text("Meters") }
                }
                .padding()
            } else {
                Spacer()
                Text(manager.selected == nil ? "Add or select an instance" : "Connecting to \(manager.selected!.address)")
                    .font(.title3)
                    .foregroundColor(.secondary)
                Spacer()
            }
        }
        .frame(minWidth: 480)
    }
}

struct StatusTab: View {
    @EnvironmentObject private var manager: ConnectionManager
    let status: DeviceStatus

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                GroupBox {
                    VStack(alignment: .leading, spacing: 8) {
                        row("Device", status.device.name)
                        row("Engine", status.status)
                        row("Network", "\(status.device.address) (\(status.device.interface))")
                        row("Virgil version", status.version)
                        HStack {
                            Button("Start") { manager.start() }
                            Button("Stop") { manager.stop() }
                            Button("Restart audio") { manager.restart() }
                        }
                        .padding(.top, 4)
                    }
                    .padding(8)
                }
                GroupBox {
                    VStack(alignment: .leading, spacing: 8) {
                        row("Clock", status.clock.state, color: status.clockLocked ? .green : .red)
                        row("Clock leader", status.clock.grandmaster)
                        row("Sample rate", "\(status.device.sampleRate) Hz")
                        row("Channels", "TX \(status.device.txChannels) / RX \(status.device.rxChannels)")
                        row("Dropouts (last hour)", "\(status.dropoutsLastHour)")
                        row("Apps", status.appsText)
                    }
                    .padding(8)
                }
            }
            .padding()
        }
    }

    private func row(_ label: String, _ value: String, color: Color = .primary) -> some View {
        HStack(alignment: .top) {
            Text(label).foregroundColor(.secondary).frame(width: 160, alignment: .leading)
            Text(value).bold().foregroundColor(color).textSelection(.enabled)
            Spacer()
        }
    }
}

struct MetersTab: View {
    @EnvironmentObject private var manager: ConnectionManager

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                GroupBox("Transmit (TX). AirPlay plays on channels 1 and 2.") {
                    meters(manager.txMeters)
                }
                GroupBox("Receive (RX)") {
                    meters(manager.rxMeters)
                }
                Text("Scale: -60 to 0 dBFS").font(.caption).foregroundColor(.secondary)
            }
            .padding()
        }
    }

    private func meters(_ rows: [MeterRow]) -> some View {
        VStack(spacing: 6) {
            ForEach(rows) { m in
                HStack {
                    Text(m.name).lineLimit(1).frame(width: 140, alignment: .leading)
                    ProgressView(value: m.position).tint(.green)
                    Text(m.level).font(.caption).foregroundColor(.secondary).frame(width: 80, alignment: .trailing)
                }
            }
        }
        .padding(8)
    }
}

struct AddInstanceView: View {
    @Environment(\.dismiss) private var dismiss
    let onSave: (DanteInstance) -> Void

    @State private var name = ""
    @State private var host = "localhost"
    @State private var port = "8480"
    @State private var password = ""

    private var portNumber: Int? {
        guard let p = Int(port), (1...65535).contains(p) else { return nil }
        return p
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Add instance").font(.headline)
            Form {
                TextField("Name (optional)", text: $name)
                TextField("Host or IP", text: $host)
                TextField("Port", text: $port)
                SecureField("Remote password", text: $password)
            }
            Text("Leave the password blank for localhost through an SSH tunnel: ssh -L 8480:127.0.0.1:8480 user@host")
                .font(.caption)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Save") {
                    let h = host.trimmingCharacters(in: .whitespaces)
                    let n = name.trimmingCharacters(in: .whitespaces)
                    onSave(DanteInstance(name: n.isEmpty ? h : n, host: h, port: portNumber ?? 8480, password: password))
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(host.trimmingCharacters(in: .whitespaces).isEmpty || portNumber == nil)
            }
        }
        .padding(20)
        .frame(width: 400)
    }
}
