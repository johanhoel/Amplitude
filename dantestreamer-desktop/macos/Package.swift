// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "DanteStreamerController",
    platforms: [
        .macOS(.v12)
    ],
    dependencies: [],
    targets: [
        .target(
            name: "DanteStreamerController",
            path: "Sources"
        )
    ]
)
