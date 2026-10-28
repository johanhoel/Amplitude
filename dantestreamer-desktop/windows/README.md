# DanteStreamer Controller for Windows

WPF app on .NET 8 for 64-bit Windows 10 or later.

## Build and run

Needs the .NET 8 SDK.

```bash
cd dantestreamer-desktop/windows
dotnet run -c Release
```

The release build in CI is one self-contained exe:

```bash
dotnet publish -c Release -r win-x64 --self-contained=true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true -o publish
```

On Linux or macOS, add `-p:EnableWindowsTargeting=true` to check that it
compiles. It cannot run there.

## Files

- `ViewModels/ConnectionViewModel.cs`: saved hosts, polling `/api/status`
  once a second on the UI thread, start/stop/restart, HTTP Basic auth for
  the remote password.
- `MainWindow.xaml`: sidebar with the Add/Edit form, Status and Meters tabs.
- `Models/DanteModels.cs`: the `/api/status` JSON, matching `status_json()`
  in Virgil's `src/daemon/control.cpp`.
- `Converters.cs`: visibility and color converters used by the XAML.

Saved hosts: `%APPDATA%\DanteStreamerController\instances.json`. The
password is stored as `password_dpapi`, encrypted for the current Windows
user. Files from the first version had a plain `password` field; the app
reads it and writes it back encrypted on the next save.
