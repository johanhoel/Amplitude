import Foundation

// Saves instances and polls /api/status of the selected one once a second.
@MainActor
final class ConnectionManager: ObservableObject {
    @Published var instances: [DanteInstance] = [] {
        didSet { saveInstances() }
    }
    @Published var selectedID: DanteInstance.ID? {
        didSet { if selectedID != oldValue { restartPolling() } }
    }
    @Published private(set) var status: DeviceStatus?
    @Published private(set) var txMeters: [MeterRow] = []
    @Published private(set) var rxMeters: [MeterRow] = []
    @Published var error: String?

    private var pollTask: Task<Void, Never>?
    private let session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 3
        return URLSession(configuration: config)
    }()
    private static let defaultsKey = "instances"

    var selected: DanteInstance? { instances.first { $0.id == selectedID } }

    init() {
        if let data = UserDefaults.standard.data(forKey: Self.defaultsKey),
           let saved = try? JSONDecoder().decode([DanteInstance].self, from: data) {
            instances = saved.map { var i = $0; i.password = Keychain.password(for: i.id); return i }
        }
        selectedID = instances.first?.id
        restartPolling()
    }

    // Adds a new host, or replaces the saved one with the same id.
    func save(_ instance: DanteInstance) {
        Keychain.setPassword(instance.password, for: instance.id)
        if let i = instances.firstIndex(where: { $0.id == instance.id }) {
            instances[i] = instance
            restartPolling()
        } else {
            instances.append(instance)
        }
        selectedID = instance.id
    }

    func removeSelected() {
        guard let id = selectedID else { return }
        Keychain.setPassword("", for: id)
        instances.removeAll { $0.id == id }
        selectedID = instances.first?.id
    }

    func start() { post("/api/start") }
    func stop() { post("/api/stop") }
    func restart() { post("/api/restart") }

    private func saveInstances() {
        if let data = try? JSONEncoder().encode(instances) {
            UserDefaults.standard.set(data, forKey: Self.defaultsKey)
        }
    }

    private func restartPolling() {
        pollTask?.cancel()
        status = nil
        txMeters = []
        rxMeters = []
        error = nil
        guard let instance = selected else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.fetchStatus(instance)
                try? await Task.sleep(nanoseconds: 1_000_000_000)
            }
        }
    }

    private func request(_ instance: DanteInstance, _ path: String, method: String = "GET") -> URLRequest? {
        guard let url = URL(string: "http://\(instance.address)\(path)") else { return nil }
        var req = URLRequest(url: url)
        req.httpMethod = method
        // Virgil asks other computers for remote_password with HTTP Basic auth (any user name).
        if !instance.password.isEmpty {
            let token = Data("app:\(instance.password)".utf8).base64EncodedString()
            req.setValue("Basic \(token)", forHTTPHeaderField: "Authorization")
        }
        return req
    }

    private func fetchStatus(_ instance: DanteInstance) async {
        guard let req = request(instance, "/api/status") else {
            error = "Invalid host: \(instance.host)"
            return
        }
        do {
            let (data, response) = try await session.data(for: req)
            guard instance.id == selectedID, !Task.isCancelled else { return }
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard code == 200 else {
                status = nil
                error = Self.describeHTTPError(code, data)
                return
            }
            let s = try JSONDecoder().decode(DeviceStatus.self, from: data)
            status = s
            txMeters = MeterRow.build(peaks: s.meters.tx, names: s.txNames, prefix: "TX")
            rxMeters = MeterRow.build(peaks: s.meters.rx, names: s.rxNames, prefix: "RX")
            error = s.error.isEmpty ? nil : s.error
        } catch is CancellationError {
        } catch {
            guard instance.id == selectedID else { return }
            status = nil
            self.error = "Cannot reach \(instance.address) (\(error.localizedDescription))"
        }
    }

    private func post(_ path: String) {
        guard let instance = selected, var req = request(instance, path, method: "POST") else { return }
        // Virgil refuses POSTs without this header (its CSRF guard).
        req.setValue("1", forHTTPHeaderField: "X-Virgil-Request")
        Task {
            do {
                let (data, response) = try await session.data(for: req)
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                if code != 200 { error = Self.describeHTTPError(code, data) }
            } catch {
                self.error = error.localizedDescription
            }
            await fetchStatus(instance)
        }
    }

    private static func describeHTTPError(_ code: Int, _ body: Data) -> String {
        let message = (try? JSONSerialization.jsonObject(with: body) as? [String: Any])?["error"] as? String
        switch code {
        case 401: return "Wrong or missing password (Virgil remote_password)."
        case 403: return message ?? "Refused. Turn on remote access in Virgil, or use an SSH tunnel to localhost."
        case 429: return "Too many wrong passwords. Wait a minute and try again."
        default: return "HTTP \(code): \(message ?? String(decoding: body, as: UTF8.self))"
        }
    }
}
