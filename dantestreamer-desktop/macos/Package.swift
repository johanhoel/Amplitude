// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "DanteStreamerController",
    platforms: [
        .macOS(.v12)
    ],
    products: [
        .executable(
            name: "DanteStreamerController",
            targets: ["DanteStreamerController"]
        )
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-async-algorithms.git", from: "1.0.0")
    ],
    targets: [
        .executableTarget(
            name: "DanteStreamerController",
            dependencies: [
                .product(name: "AsyncAlgorithms", package: "swift-async-algorithms")
            ],
            path: "Sources"
        )
    ]
)
