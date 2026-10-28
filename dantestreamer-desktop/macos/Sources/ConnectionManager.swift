import AppKit
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
    @Published var installMessage: String?
    @Published private(set) var installing = false

    private var pollTask: Task<Void, Never>?
    private let session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 3
        return URLSession(configuration: config)
    }()
    private static let defaultsKey = "instances"

    var selected: DanteInstance? { instances.first { $0.id == selectedID } }

    static let thisComputer = "localhost"
    // Virgil's macOS installer (DanteStreamer's Dante engine) is on its releases page.
    static let virgilDownloadURL = URL(string: "https://github.com/Audbol/Virgil-Virtual-Soundcard/releases")!
    static let guideURL = URL(string: "https://github.com/johanhoel/Amplitude/blob/main/dantestreamer-desktop/README.md#connect-to-your-dantestreamer")!

    init() {
        if let data = UserDefaults.standard.data(forKey: Self.defaultsKey),
           let saved = try? JSONDecoder().decode([DanteInstance].self, from: data) {
            instances = saved.map { var i = $0; i.password = Keychain.password(for: i.id); return i }
        }
        selectedID = instances.first?.id
        restartPolling()
        if instances.isEmpty { Task { await detectThisComputer() } }
    }

    // First start: if Virgil already runs on this Mac, add it without asking.
    private func detectThisComputer() async {
        guard let url = URL(string: "http://\(Self.thisComputer):8480/api/status"),
              let result = try? await session.data(from: url),
              (result.1 as? HTTPURLResponse)?.statusCode == 200,
              instances.isEmpty else { return }
        useThisComputer()
    }

    // Virgil's package, built and signed in CI (build-desktop.yml) and placed in
    // the app's Resources. `swift run` builds have none and use the download page.
    static var bundledVirgil: URL? { Bundle.main.url(forResource: "Virgil", withExtension: "pkg") }

    // Installs the bundled package with /usr/sbin/installer. macOS asks for an
    // administrator password once; then the app connects to Virgil on this Mac.
    func installVirgil() {
        guard let pkg = Self.bundledVirgil else {
            NSWorkspace.shared.open(Self.virgilDownloadURL)
            return
        }
        // AppleScript string: escape backslashes and quotes; `quoted form of` handles the shell.
        let path = pkg.path.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"")
        let script = "do shell script \"/usr/sbin/installer -pkg \" & quoted form of \"\(path)\" & \" -target /\" with administrator privileges"
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = ["-e", script]
        let stderr = Pipe()
        process.standardError = stderr
        process.terminationHandler = { p in
            let message = String(decoding: stderr.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            Task { @MainActor in self.installFinished(status: p.terminationStatus, message: message) }
        }
        installing = true
        installMessage = "Installing Virgil. macOS asks for your password."
        do {
            try process.run()
        } catch {
            installing = false
            installMessage = "Could not start the installer: \(error.localizedDescription)"
        }
    }

    private func installFinished(status: Int32, message: String) {
        installing = false
        guard status == 0 else {
            // -128 = the password dialog was cancelled
            installMessage = message.contains("-128")
                ? "Installation cancelled. Click Install Virgil to try again."
                : "Virgil was not installed: \(message.trimmingCharacters(in: .whitespacesAndNewlines))"
            return
        }
        installMessage = "Virgil is installed. Connecting..."
        Task {
            try? await Task.sleep(nanoseconds: 3_000_000_000) // the Virgil service starts its panel
            useThisComputer()
            installMessage = nil
        }
    }

    func useThisComputer() {
        if let existing = instances.first(where: { $0.host == Self.thisComputer || $0.host == "127.0.0.1" }) {
            if selectedID == existing.id { restartPolling() } else { selectedID = existing.id }
            return
        }
        save(DanteInstance(name: "This Mac", host: Self.thisComputer))
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

    func start() { post("/api/start", busy: "Starting Virgil...") }
    func stop() { post("/api/stop", busy: "Stopping Virgil...") }
    func restart() { post("/api/restart", busy: "Restarting the audio engine...") }

    // Start is offered only while the engine is stopped, Stop and Restart only
    // while it is not, so a click always changes something.
    var engineStopped: Bool { status?.status == "stopped" || status?.status == "error" }

    // Result of Start/Stop/Restart. Kept apart from `error`, which every status
    // poll rewrites, and cleared once the engine reaches the new state.
    @Published var actionMessage: String?
    private var waitingFor: String?
    private var actionSince = Date()

    private func checkAction(_ s: DeviceStatus) {
        guard let want = waitingFor else { return }
        if s.status == want {
            actionMessage = nil
            waitingFor = nil
        } else if Date().timeIntervalSince(actionSince) > 20 {
            actionMessage = "Virgil is \(s.status). Check its log (Virgil menu, Open log)."
            waitingFor = nil
        }
    }

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
        actionMessage = nil
        waitingFor = nil
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
            checkAction(s)
            txMeters = MeterRow.build(peaks: s.meters.tx, names: s.txNames, prefix: "TX")
            rxMeters = MeterRow.build(peaks: s.meters.rx, names: s.rxNames, prefix: "RX")
            error = s.error.isEmpty ? nil : s.error
        } catch is CancellationError {
        } catch let e as URLError where e.code == .cannotConnectToHost {
            guard instance.id == selectedID else { return }
            status = nil
            error = Self.refusedHint(instance)
        } catch {
            guard instance.id == selectedID else { return }
            status = nil
            self.error = "Cannot reach \(instance.address) (\(error.localizedDescription))"
        }
    }

    private func post(_ path: String, busy: String) {
        guard let instance = selected, var req = request(instance, path, method: "POST") else { return }
        // Virgil refuses POSTs without this header (its CSRF guard).
        req.setValue("1", forHTTPHeaderField: "X-Virgil-Request")
        actionMessage = busy
        Task {
            do {
                let (data, response) = try await session.data(for: req)
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                guard code == 200 else {
                    actionMessage = Self.describeHTTPError(code, data)
                    return
                }
                waitingFor = path == "/api/stop" ? "stopped" : "running"
                actionSince = Date()
            } catch {
                actionMessage = "Virgil did not answer: \(error.localizedDescription)"
                return
            }
            await fetchStatus(instance)
        }
    }

    // The computer answered but nothing listens on the port. Virgil listens
    // only on 127.0.0.1 until remote access is turned on.
    private static func refusedHint(_ i: DanteInstance) -> String {
        if i.host == "localhost" || i.host == "127.0.0.1" {
            return "Virgil is not running on this Mac. Click Install Virgil below, or open Virgil Control from Applications; "
                + "this page connects by itself once it runs. For a DanteStreamer box on the network, add it by its IP address instead."
        }
        return "\(i.host) does not accept connections on port \(i.port). Remote access is probably off on that DanteStreamer: "
            + "add REMOTE_PASSWORD to its .env file and run docker compose up -d, then enter that password here. Click Setup guide for the steps."
    }

    private static func describeHTTPError(_ code: Int, _ body: Data) -> String {
        let message = (try? JSONSerialization.jsonObject(with: body) as? [String: Any])?["error"] as? String
        switch code {
        case 401: return "Wrong or missing password. Use the REMOTE_PASSWORD from DanteStreamer's .env file: select the host and click Edit."
        case 403: return message ?? "Refused. Turn on remote access in Virgil, or use an SSH tunnel to localhost."
        case 429: return "Too many wrong passwords. Wait a minute and try again."
        default: return "HTTP \(code): \(message ?? String(decoding: body, as: UTF8.self))"
        }
    }
}
