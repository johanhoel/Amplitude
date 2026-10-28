import Foundation

// A DanteStreamer found on the network.
struct FoundHost: Identifiable, Hashable {
    var id: String { address }
    let name: String
    let address: String
}

// Finds DanteStreamer hosts by their AirPlay receiver (_raop._tcp). DanteStreamer's
// receiver is Shairport Sync, which says so in its TXT record (am=ShairportSync);
// Apple TVs and HomePods do not. Info.plist lists _raop._tcp in NSBonjourServices,
// which macOS needs before it lets an app browse.
final class Discovery: NSObject, NetServiceBrowserDelegate, NetServiceDelegate {
    private let browser = NetServiceBrowser()
    private var services: [NetService] = []
    private var found: [String: FoundHost] = [:]

    // Runs on the main thread, so the browser's callbacks arrive on the main run loop
    // while the task sleeps.
    @MainActor
    func find(seconds: Double) async -> [FoundHost] {
        browser.delegate = self
        browser.searchForServices(ofType: "_raop._tcp.", inDomain: "local.")
        try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
        browser.stop()
        services.forEach { $0.stop() }
        services.removeAll()
        return found.values.sorted { $0.name < $1.name }
    }

    func netServiceBrowser(_ browser: NetServiceBrowser, didFind service: NetService, moreComing: Bool) {
        services.append(service)
        service.delegate = self
        service.resolve(withTimeout: 2)
    }

    func netServiceDidResolveAddress(_ sender: NetService) {
        guard let txt = sender.txtRecordData(),
              let am = NetService.dictionary(fromTXTRecord: txt)["am"],
              String(decoding: am, as: UTF8.self).contains("ShairportSync") else { return }
        guard let address = Self.ipv4(sender.addresses ?? []) ?? sender.hostName else { return }
        // "A84985A16ECB@DanteStreamer" -> "DanteStreamer"
        let name = sender.name.split(separator: "@", maxSplits: 1).last.map(String.init) ?? sender.name
        found[address] = FoundHost(name: name, address: address)
    }

    private static func ipv4(_ addresses: [Data]) -> String? {
        for data in addresses {
            let ip: String? = data.withUnsafeBytes { raw in
                guard raw.count >= MemoryLayout<sockaddr_in>.size,
                      raw.load(as: sockaddr.self).sa_family == sa_family_t(AF_INET) else { return nil }
                var sin = raw.load(as: sockaddr_in.self)
                var buf = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
                guard inet_ntop(AF_INET, &sin.sin_addr, &buf, socklen_t(INET_ADDRSTRLEN)) != nil else { return nil }
                return String(cString: buf)
            }
            if let ip { return ip }
        }
        return nil
    }
}
