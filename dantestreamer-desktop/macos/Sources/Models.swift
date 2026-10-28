import Foundation

// A saved DanteStreamer host. Port 8480 is the Virgil control panel.
struct DanteInstance: Codable, Identifiable, Hashable {
    var id = UUID()
    var name: String
    var host: String
    var port: Int = 8480
    // Virgil remote_password; empty when reached through an SSH tunnel on localhost.
    var password: String = ""

    var address: String { "\(host):\(port)" }
}

// GET /api/status, as built by status_json() in Virgil's src/daemon/control.cpp.
struct DeviceStatus: Decodable {
    var version: String = ""
    var status: String = ""      // "running", "stopped", "restarting" or "error"
    var error: String = ""
    var device: DeviceInfo
    var txNames: [String] = []
    var rxNames: [String] = []
    var dropoutsLastHour: Int = 0
    var clock: ClockInfo
    var clients: [ClientInfo] = []
    var meters: MeterValues

    enum CodingKeys: String, CodingKey {
        case version, status, error, device, clock, clients, meters
        case txNames = "tx_names"
        case rxNames = "rx_names"
        case dropoutsLastHour = "dropouts_last_hour"
    }

    var clockLocked: Bool { clock.state == "ptp-locked" || clock.state == "ptp-master" }

    var appsText: String {
        clients.isEmpty ? "none" : clients.map { $0.active ? "\($0.name) (playing)" : $0.name }.joined(separator: ", ")
    }
}

struct DeviceInfo: Decodable {
    var name: String
    var interface: String
    var address: String
    var sampleRate: Int
    var txChannels: Int
    var rxChannels: Int
    var latencyUs: Int

    enum CodingKeys: String, CodingKey {
        case name, interface, address
        case sampleRate = "sample_rate"
        case txChannels = "tx_channels"
        case rxChannels = "rx_channels"
        case latencyUs = "latency_us"
    }
}

struct ClockInfo: Decodable {
    var state: String            // "stopped", "free-run", "ptp-locked" or "ptp-master"
    var grandmaster: String
}

struct ClientInfo: Decodable {
    var name: String
    var active: Bool
}

struct MeterValues: Decodable {
    // Linear peak per channel, 0 to 1 (1 = 0 dBFS)
    var tx: [Double] = []
    var rx: [Double] = []
}

// One meter row in the Meters tab.
struct MeterRow: Identifiable {
    let id: Int
    let name: String
    // 0 to 1 across -60..0 dBFS, the same scale as the Virgil web panel
    let position: Double
    let level: String

    static func build(peaks: [Double], names: [String], prefix: String) -> [MeterRow] {
        (0..<max(peaks.count, names.count)).map { i in
            let lin = i < peaks.count ? peaks[i] : 0
            let db = lin > 0 ? 20 * log10(lin) : -.infinity
            let name = i < names.count && !names[i].isEmpty ? names[i] : "\(prefix) \(i + 1)"
            return MeterRow(
                id: i,
                name: name,
                position: lin > 0 ? min(max((db + 60) / 60, 0), 1) : 0,
                level: lin > 0 ? String(format: "%.1f dBFS", db) : "silent"
            )
        }
    }
}
