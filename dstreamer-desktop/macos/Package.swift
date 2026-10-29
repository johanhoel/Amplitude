// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "DStreamerController",
    platforms: [
        .macOS(.v12)
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "DStreamerController",
            path: "Sources"
        )
    ]
)
