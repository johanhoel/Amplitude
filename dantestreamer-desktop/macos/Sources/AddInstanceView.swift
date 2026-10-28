import SwiftUI

struct AddInstanceView: View {
    @EnvironmentObject var connectionManager: ConnectionManager
    @Environment(\.dismiss) var dismiss

    @State private var name = ""
    @State private var host = ""
    @State private var port = "8480"
    @State private var password = ""
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Instance Details") {
                    TextField("Name", text: $name)
                        .placeholder(when: name.isEmpty) {
                            Text("e.g., Studio Main")
                        }

                    TextField("Host", text: $host)
                        .placeholder(when: host.isEmpty) {
                            Text("192.168.1.100 or hostname.local")
                        }
                        .textContentType(.URL)

                    TextField("Port", text: $port)
                        .placeholder(when: port.isEmpty) {
                            Text("8480")
                        }
                        .keyboardType(.numberPad)

                    SecureField("Password (optional)", text: $password)
                }

                Section {
                    if let error = error {
                        Text(error)
                            .foregroundColor(.red)
                            .font(.caption)
                    }
                }

                Section {
                    Button(action: addInstance) {
                        if name.isEmpty || host.isEmpty {
                            Label("Add Instance", systemImage: "plus.circle")
                                .foregroundColor(.gray)
                        } else {
                            Label("Add Instance", systemImage: "plus.circle")
                        }
                    }
                    .disabled(name.isEmpty || host.isEmpty)
                }
            }
            .navigationTitle("Add Instance")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
            }
        }
    }

    private func addInstance() {
        guard !name.isEmpty, !host.isEmpty else {
            error = "Name and host are required"
            return
        }

        guard let port = Int(port), port > 0, port < 65536 else {
            error = "Invalid port number"
            return
        }

        let instance = DanteInstance(
            name: name,
            host: host,
            port: port,
            password: password.isEmpty ? nil : password
        )

        connectionManager.addInstance(instance)
        dismiss()
    }
}

extension View {
    func placeholder<Content: View>(when shouldShow: Bool, alignment: Alignment = .leading, @ViewBuilder placeholder: () -> Content) -> some View {
        ZStack(alignment: alignment) {
            placeholder().opacity(shouldShow ? 1 : 0)
            self
        }
    }
}

#Preview {
    AddInstanceView()
        .environmentObject(ConnectionManager())
}
