import AppKit
import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var manager: ConnectionManager
    // The host being added or edited; nil when the sheet is closed.
    @State private var editing: DanteInstance?
    // Run Find on network as soon as the Add sheet opens.
    @State private var findOnOpen = false

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
                    Button { add(find: false) } label: { Label("Add", systemImage: "plus") }
                        .help("Add a DanteStreamer")
                    Button { editing = manager.selected } label: { Label("Edit", systemImage: "pencil") }
                        .help("Edit the selected instance")
                        .disabled(manager.selected == nil)
                    Button { manager.removeSelected() } label: { Label("Remove", systemImage: "minus") }
                        .help("Remove the selected instance")
                        .disabled(manager.selectedID == nil)
                }
            }

            DetailView { add(find: true) }
        }
        .sheet(item: $editing) { instance in
            InstanceForm(instance: instance,
                         isNew: manager.instances.allSatisfy { $0.id != instance.id },
                         findOnOpen: findOnOpen) {
                manager.save($0)
            }
        }
    }

    private func add(find: Bool) {
        findOnOpen = find
        editing = DanteInstance(name: "", host: "")
    }
}

struct DetailView: View {
    @EnvironmentObject private var manager: ConnectionManager
    let onFind: () -> Void

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
                StartView(onFind: onFind)
            }
        }
        .frame(minWidth: 480)
    }
}

// Shown until a DanteStreamer answers: the two ways to set one up.
struct StartView: View {
    @EnvironmentObject private var manager: ConnectionManager
    let onFind: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Set up DanteStreamer").font(.title2).bold()
                if let selected = manager.selected {
                    Text("Connecting to \(selected.name)...").foregroundColor(.secondary)
                }
                Text("DanteStreamer sends sound to Dante speakers and amplifiers. Pick the setup that matches yours.")
                    .fixedSize(horizontal: false, vertical: true)

                GroupBox {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("A. This Mac plays to the Dante speakers").font(.headline)
                        Text("No other equipment needed: this Mac joins the Dante network and sends its own sound (Music, Spotify, a browser, everything) to the speakers.")
                            .foregroundColor(.secondary)
                        step("1.", "Click Install Virgil. Virgil is the free Dante engine DanteStreamer uses, and it comes with this app. macOS asks for your password once. The app connects by itself when it is done.")
                        step("2.", "The Status tab then shows this Mac on the Dante network. If Virgil was already installed, click Use this Mac instead.")
                        step("3.", "Send the Mac's sound to Dante: in the menu bar, click the Virgil icon, choose Desktop audio…, click Add…, pick Default output device (or one app, like Spotify) on transmit channels 1 and 2. macOS asks once to allow audio recording: click Allow. This needs macOS 14.2 or later.")
                        step("4.", "In Dante Controller, route this Mac's transmit channels 1 and 2 to your speakers.")
                        HStack {
                            Button(ConnectionManager.bundledVirgil == nil ? "Download Virgil" : "Install Virgil") { manager.installVirgil() }
                                .keyboardShortcut(.defaultAction)
                                .disabled(manager.installing)
                            Button("Use this Mac") { manager.useThisComputer() }
                        }
                        .padding(.top, 4)
                        if let message = manager.installMessage {
                            Text(message).foregroundColor(.accentColor)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Text("Virgil is free software under the GNU GPL v3. Source: github.com/Audbol/Virgil-Virtual-Soundcard")
                            .font(.caption).foregroundColor(.secondary)
                    }
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                GroupBox {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("B. A DanteStreamer box on the network").font(.headline)
                        Text("DanteStreamer already runs on another computer, for example a small Linux box that phones play to with AirPlay. That box needs remote access turned on once: REMOTE_PASSWORD in its .env file. The setup guide shows how.")
                            .foregroundColor(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                        HStack {
                            Button("Find on network", action: onFind)
                            Button("Setup guide") { NSWorkspace.shared.open(ConnectionManager.guideURL) }
                        }
                        .padding(.top, 4)
                    }
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(24)
            .frame(maxWidth: 640, alignment: .leading)
        }
    }

    private func step(_ number: String, _ text: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Text(number).bold()
            Text(text).fixedSize(horizontal: false, vertical: true)
        }
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
                            Spacer()
                            if let url = manager.selected?.panelURL {
                                Button("Open web panel") { NSWorkspace.shared.open(url) }
                                    .help("Settings, routing and diagnostics in Virgil's own panel")
                            }
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

struct InstanceForm: View {
    @Environment(\.dismiss) private var dismiss
    let instance: DanteInstance
    let isNew: Bool
    let findOnOpen: Bool
    let onSave: (DanteInstance) -> Void

    @State private var found: [FoundHost] = []
    @State private var findMessage: String?
    @State private var searching = false

    @State private var name = ""
    @State private var host = ""
    @State private var port = ""
    @State private var password = ""

    private var portNumber: Int? {
        guard let p = Int(port), (1...65535).contains(p) else { return nil }
        return p
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(isNew ? "Add DanteStreamer" : "Edit DanteStreamer").font(.headline)
            HStack {
                Button(searching ? "Searching..." : "Find on network") { Task { await find() } }
                    .disabled(searching)
                Spacer()
            }
            if let findMessage {
                Text(findMessage).font(.caption).foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if found.count > 1 {
                Picker("Found", selection: Binding(get: { host }, set: { pick($0) })) {
                    ForEach(found) { Text("\($0.name) (\($0.address))").tag($0.address) }
                }
            }
            Form {
                TextField("Name (optional)", text: $name)
                TextField("Host or IP", text: $host)
                TextField("Port", text: $port)
                SecureField("Password", text: $password)
            }
            Text("The password is REMOTE_PASSWORD from the DanteStreamer box's .env file. Leave it blank for this Mac.")
                .font(.caption)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Button("How do I connect?") { NSWorkspace.shared.open(ConnectionManager.guideURL) }
                .buttonStyle(.link)
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Save") {
                    let h = host.trimmingCharacters(in: .whitespaces)
                    let n = name.trimmingCharacters(in: .whitespaces)
                    var saved = instance
                    saved.name = n.isEmpty ? h : n
                    saved.host = h
                    saved.port = portNumber ?? 8480
                    saved.password = password
                    onSave(saved)
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(host.trimmingCharacters(in: .whitespaces).isEmpty || portNumber == nil)
            }
        }
        .padding(20)
        .frame(width: 400)
        .onAppear {
            name = instance.name
            host = instance.host
            port = String(instance.port)
            password = instance.password
            if findOnOpen { Task { await find() } }
        }
    }

    private func pick(_ address: String) {
        guard let h = found.first(where: { $0.address == address }) else { return }
        name = h.name
        host = h.address
        port = "8480"
    }

    @MainActor
    private func find() async {
        searching = true
        findMessage = "Searching the network..."
        found = await Discovery().find(seconds: 3)
        searching = false
        switch found.count {
        case 0: findMessage = "No DanteStreamer found. Check that it is switched on and on the same network, or type its IP address below."
        case 1: findMessage = "Found 1 DanteStreamer. It is filled in below."
        default: findMessage = "Found \(found.count). Pick one from the list."
        }
        if let first = found.first { pick(first.address) }
    }
}
