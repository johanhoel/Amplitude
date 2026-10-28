import Foundation
import Combine

@MainActor
class ConnectionManager: ObservableObject {
    @Published var instances: [DanteInstance] = []
    @Published var selectedInstance: DanteInstance?
    @Published var status: DeviceStatus?
    @Published var meters: ChannelMeters?
    @Published var isConnected = false
    @Published var error: String?

    private var statusTask: Task<Void, Never>?
    private var metersTask: Task<Void, Never>?
    private let userDefaults = UserDefaults.standard

    init() {
        loadSavedInstances()
    }

    func connect(to instance: DanteInstance) async {
        selectedInstance = instance
        isConnected = true
        error = nil
        startPolling()
        saveInstances()
    }

    func disconnect() {
        statusTask?.cancel()
        metersTask?.cancel()
        selectedInstance = nil
        isConnected = false
        status = nil
        meters = nil
    }

    private func startPolling() {
        statusTask?.cancel()
        metersTask?.cancel()

        statusTask = Task {
            while !Task.isCancelled {
                await fetchStatus()
                try? await Task.sleep(for: .seconds(2))
            }
        }

        metersTask = Task {
            while !Task.isCancelled {
                await fetchMeters()
                try? await Task.sleep(for: .milliseconds(100))
            }
        }
    }

    private func fetchStatus() async {
        guard let instance = selectedInstance else { return }

        do {
            let url = URL(string: "http://\(instance.host):\(instance.port)/api/status")!
            let (data, _) = try await URLSession.shared.data(from: url)
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            status = try decoder.decode(DeviceStatus.self, from: data)
            error = nil
        } catch {
            self.error = "Status fetch failed: \(error.localizedDescription)"
        }
    }

    private func fetchMeters() async {
        guard let instance = selectedInstance else { return }

        do {
            let url = URL(string: "http://\(instance.host):\(instance.port)/api/status")!
            let (data, _) = try await URLSession.shared.data(from: url)
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            let status = try decoder.decode(DeviceStatus.self, from: data)
            meters = ChannelMeters(from: status)
        } catch {
            // Silently fail for meter updates
        }
    }

    func addInstance(_ instance: DanteInstance) {
        if !instances.contains(where: { $0.id == instance.id }) {
            instances.append(instance)
            saveInstances()
        }
    }

    func removeInstance(_ instance: DanteInstance) {
        instances.removeAll { $0.id == instance.id }
        if selectedInstance?.id == instance.id {
            disconnect()
        }
        saveInstances()
    }

    private func saveInstances() {
        if let encoded = try? JSONEncoder().encode(instances) {
            userDefaults.set(encoded, forKey: "savedInstances")
        }
    }

    private func loadSavedInstances() {
        if let data = userDefaults.data(forKey: "savedInstances"),
           let decoded = try? JSONDecoder().decode([DanteInstance].self, from: data) {
            instances = decoded
        }
    }
}

struct DanteInstance: Identifiable, Codable {
    let id: UUID
    var name: String
    var host: String
    var port: Int = 8480
    var password: String?

    init(name: String, host: String, port: Int = 8480, password: String? = nil) {
        self.id = UUID()
        self.name = name
        self.host = host
        self.port = port
        self.password = password
    }
}

struct DeviceStatus: Codable {
    let deviceName: String
    let enabled: Bool
    let clockLocked: Bool
    let sampleRate: Int
    let txChannels: Int
    let rxChannels: Int
    let txMeters: [Float]
    let rxMeters: [Float]
    let txChannelNames: [String]?
    let rxChannelNames: [String]?

    enum CodingKeys: String, CodingKey {
        case deviceName = "device_name"
        case enabled, clockLocked = "clock_locked"
        case sampleRate = "sample_rate"
        case txChannels = "tx_channels"
        case rxChannels = "rx_channels"
        case txMeters = "tx_meters"
        case rxMeters = "rx_meters"
        case txChannelNames = "tx_channel_names"
        case rxChannelNames = "rx_channel_names"
    }
}

struct ChannelMeters {
    let txMeters: [Float]
    let rxMeters: [Float]
    let txNames: [String]
    let rxNames: [String]

    init(from status: DeviceStatus) {
        self.txMeters = status.txMeters
        self.rxMeters = status.rxMeters
        self.txNames = (0..<status.txChannels).map { i in
            status.txChannelNames?[i] ?? "TX \(i+1)"
        }
        self.rxNames = (0..<status.rxChannels).map { i in
            status.rxChannelNames?[i] ?? "RX \(i+1)"
        }
    }
}
