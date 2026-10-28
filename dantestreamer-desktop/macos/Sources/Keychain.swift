import Foundation
import Security

// Remote passwords live in the login keychain, one item per saved host.
enum Keychain {
    private static let service = "com.dantestreamer.controller"

    private static func query(_ account: UUID) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account.uuidString]
    }

    static func password(for account: UUID) -> String {
        var q = query(account)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return "" }
        return String(decoding: data, as: UTF8.self)
    }

    static func setPassword(_ password: String, for account: UUID) {
        SecItemDelete(query(account) as CFDictionary)
        guard !password.isEmpty else { return }
        var q = query(account)
        q[kSecValueData as String] = Data(password.utf8)
        q[kSecAttrLabel as String] = "DanteStreamer Controller remote password"
        SecItemAdd(q as CFDictionary, nil)
    }
}
