import SwiftUI

struct DetailView: View {
    let instance: DanteInstance
    @EnvironmentObject var connectionManager: ConnectionManager

    var body: some View {
        VStack {
            if let status = connectionManager.status {
                TabView {
                    StatusTab(status: status)
                        .tabItem {
                            Label("Status", systemImage: "info.circle")
                        }

                    MetersTab(meters: connectionManager.meters ?? ChannelMeters(from: status))
                        .tabItem {
                            Label("Meters", systemImage: "waveform.circle")
                        }
                }
            } else if let error = connectionManager.error {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(.red)
                    Text("Connection Error")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Button("Reconnect") {
                        Task {
                            await connectionManager.connect(to: instance)
                        }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .navigationTitle(instance.name)
    }
}

struct StatusTab: View {
    let status: DeviceStatus

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Device")
                        .font(.headline)
                    Divider()

                    HStack {
                        Text("Name")
                            .foregroundColor(.secondary)
                        Spacer()
                        Text(status.deviceName)
                    }

                    HStack {
                        Text("Status")
                            .foregroundColor(.secondary)
                        Spacer()
                        HStack(spacing: 4) {
                            Circle()
                                .fill(status.enabled ? Color.green : Color.red)
                                .frame(width: 8, height: 8)
                            Text(status.enabled ? "Enabled" : "Disabled")
                        }
                    }

                    HStack {
                        Text("Clock")
                            .foregroundColor(.secondary)
                        Spacer()
                        HStack(spacing: 4) {
                            Circle()
                                .fill(status.clockLocked ? Color.green : Color.orange)
                                .frame(width: 8, height: 8)
                            Text(status.clockLocked ? "Locked" : "Unlocked")
                        }
                    }
                }
                .padding()
                .background(Color(.controlBackgroundColor))
                .cornerRadius(8)

                VStack(alignment: .leading, spacing: 12) {
                    Text("Audio")
                        .font(.headline)
                    Divider()

                    HStack {
                        Text("Sample Rate")
                            .foregroundColor(.secondary)
                        Spacer()
                        Text("\(status.sampleRate) Hz")
                    }

                    HStack {
                        Text("Channels")
                            .foregroundColor(.secondary)
                        Spacer()
                        Text("TX: \(status.txChannels), RX: \(status.rxChannels)")
                    }
                }
                .padding()
                .background(Color(.controlBackgroundColor))
                .cornerRadius(8)
            }
            .padding()
        }
    }
}

struct MetersTab: View {
    let meters: ChannelMeters

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Transmit (TX)")
                        .font(.headline)

                    ForEach(0..<meters.txMeters.count, id: \.self) { i in
                        MeterRow(
                            name: meters.txNames[i],
                            level: meters.txMeters[i]
                        )
                    }
                }
                .padding()
                .background(Color(.controlBackgroundColor))
                .cornerRadius(8)

                VStack(alignment: .leading, spacing: 12) {
                    Text("Receive (RX)")
                        .font(.headline)

                    ForEach(0..<meters.rxMeters.count, id: \.self) { i in
                        MeterRow(
                            name: meters.rxNames[i],
                            level: meters.rxMeters[i]
                        )
                    }
                }
                .padding()
                .background(Color(.controlBackgroundColor))
                .cornerRadius(8)
            }
            .padding()
        }
    }
}

struct MeterRow: View {
    let name: String
    let level: Float

    var levelColor: Color {
        switch level {
        case ..<(-40): return .gray
        case -40..<(-6): return .green
        case -6..<(-3): return .yellow
        default: return .red
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(name)
                    .font(.caption)
                Spacer()
                Text(String(format: "%.1f dB", level))
                    .font(.caption)
                    .monospacedDigit()
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color(.controlBackgroundColor))

                    Capsule()
                        .fill(levelColor)
                        .frame(width: max(0, geo.size.width * CGFloat((level + 60) / 60)))
                }
            }
            .frame(height: 8)
        }
    }
}

#Preview {
    DetailView(instance: DanteInstance(name: "Studio", host: "192.168.1.100"))
        .environmentObject(ConnectionManager())
}
