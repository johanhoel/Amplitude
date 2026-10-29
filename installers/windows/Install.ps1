# Windows installer for one Amplitude project. The build (.github/workflows/installers.yml) puts the project name in
# place of __PROJECT__ and turns this script into <Project>-Setup.exe with ps2exe (it asks for administrator rights).
#
# What it does:
#   1. installs WSL when Windows does not have it yet (Windows then restarts once, and the installer goes on by itself)
#   2. creates a Linux system (Ubuntu 24.04) named after the project, e.g. "CamWatch", with systemd switched on
#   3. runs installers/linux/setup.sh from GitHub in it: Docker, the project, its first settings
#   4. keeps it running after you log in (a hidden task), adds a desktop shortcut and an entry in Apps -> Uninstall
#   <Project>-Setup.exe -Uninstall removes all of it again, recordings included.
param([string]$Project = '__PROJECT__', [switch]$Uninstall)
$ErrorActionPreference = 'Stop'

$Info = @{
    camwatch      = @{ Name = 'CamWatch';      Url = 'http://localhost:8080';  Ports = @(8080) }
    homedeck      = @{ Name = 'Home Deck';     Url = 'http://localhost:8089';  Ports = @(80, 8088, 8089) }
    dstreamer = @{ Name = 'DStreamer'; Url = 'http://localhost:8480';  Ports = @(8480) }
}
if (-not $Info.ContainsKey($Project)) { throw "Unknown project '$Project' (camwatch, homedeck or dstreamer)" }
$P = $Info[$Project]
$Name = $P.Name
$Distro = $Name -replace ' ', ''
$Dir = Join-Path $env:LOCALAPPDATA "Amplitude\$Distro"
$SetupUrl = 'https://raw.githubusercontent.com/johanhoel/amplitude/main/installers/linux/setup.sh'
$WslVmCreator = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'     # the id Windows uses for WSL in its Hyper-V firewall
$TaskName = "Amplitude $Distro"
$Self = (Get-Process -Id $PID).Path                             # the .exe itself (ps2exe)

function Say($text) { Write-Host ''; Write-Host "==> $text" -ForegroundColor Cyan }
function Done($code) { Write-Host ''; Read-Host 'Press Enter to close'; exit $code }
function Wsl {
    # wsl.exe writes UTF-16; read it as such so names and messages compare correctly
    $old = [Console]::OutputEncoding
    try { [Console]::OutputEncoding = [Text.Encoding]::Unicode } catch { }
    try { $out = & wsl.exe @args 2>&1; $code = $LASTEXITCODE } finally { try { [Console]::OutputEncoding = $old } catch { } }
    return @{ Out = ($out | Out-String) -replace "`0", ''; Code = $code }
}
function DistroExists { (Wsl --list --quiet).Out -split "`r?`n" | Where-Object { $_.Trim() -eq $Distro } }

New-Item -ItemType Directory -Force -Path $Dir | Out-Null
Start-Transcript -Path (Join-Path $Dir 'install.log') -Append | Out-Null
Write-Host "$Name for Windows" -ForegroundColor White

# ---------------------------------------------------------------- remove
if ($Uninstall) {
    $answer = Read-Host "Remove $Name and everything in it, recordings and settings included? Type yes"
    if ($answer -ne 'yes') { Write-Host 'Nothing removed.'; Done 0 }
    Say 'Removing'
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    if (DistroExists) { Wsl --unregister $Distro | Out-Null }
    Get-NetFirewallHyperVRule -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "Amplitude-$Distro-*" } |
        Remove-NetFirewallHyperVRule -ErrorAction SilentlyContinue
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath('Desktop')) "$Name.url")
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath('Programs')) $Name)
    Remove-Item -Force -ErrorAction SilentlyContinue "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Amplitude$Distro"
    Stop-Transcript | Out-Null
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $Dir
    Write-Host "$Name is removed."
    Done 0
}

# ---------------------------------------------------------------- checks
if ([Environment]::OSVersion.Version.Build -lt 19041) {
    Write-Host 'This needs Windows 10 version 2004 or newer, or Windows 11.' -ForegroundColor Red; Done 1
}
if ($Project -eq 'dstreamer') {
    Write-Host ''
    Write-Host 'DStreamer needs direct access to the network for its clock (PTP) and audio.' -ForegroundColor Yellow
    Write-Host 'On Windows it runs in WSL, which sits behind a virtual network. Audio can drop out or stay silent.' -ForegroundColor Yellow
    Write-Host 'A Linux computer or a Raspberry Pi works better.' -ForegroundColor Yellow
    if ((Read-Host 'Install anyway? Type yes') -ne 'yes') { Done 0 }
}

# ---------------------------------------------------------------- 1. WSL
Say 'Windows Subsystem for Linux (WSL)'
$status = Wsl --status
if ($status.Code -ne 0 -or $status.Out -match 'not installed|--install') {
    Write-Host 'Installing WSL. Windows has to restart once after this.'
    $r = Wsl --install --no-distribution
    Write-Host $r.Out
    # go on by itself after the restart
    Copy-Item -Force $Self (Join-Path $Dir "$Distro-Setup.exe")
    Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name "Amplitude$Distro" `
        -Value ('"' + (Join-Path $Dir "$Distro-Setup.exe") + '"')
    Write-Host ''
    Write-Host "Restart Windows now. After the restart, the $Name installer goes on by itself." -ForegroundColor Yellow
    if ((Read-Host 'Restart now? Type yes') -eq 'yes') { Restart-Computer -Force }
    Done 0
}
Wsl --update | Out-Null

# ---------------------------------------------------------------- 2. the Linux system
# Phones and other computers reach the project through the PC's own address (Windows 11 22H2 or newer)
$wslconfig = Join-Path $env:USERPROFILE '.wslconfig'
$text = if (Test-Path $wslconfig) { Get-Content $wslconfig -Raw } else { '' }
if ($text -notmatch 'networkingMode') {
    if ($text -match '\[wsl2\]') { $text = $text -replace '\[wsl2\]', "[wsl2]`r`nnetworkingMode=mirrored" }
    else { $text = $text.TrimEnd() + "`r`n[wsl2]`r`nnetworkingMode=mirrored`r`n" }
    Set-Content -Path $wslconfig -Value $text.TrimStart() -Encoding ASCII
    Wsl --shutdown | Out-Null
}
foreach ($port in $P.Ports) {
    try {
        if (-not (Get-NetFirewallHyperVRule -Name "Amplitude-$Distro-$port" -ErrorAction SilentlyContinue)) {
            New-NetFirewallHyperVRule -Name "Amplitude-$Distro-$port" -DisplayName "$Name (port $port)" -Direction Inbound `
                -VMCreatorId $WslVmCreator -Protocol TCP -LocalPorts $port | Out-Null
        }
    } catch { }    # Windows 10 has no Hyper-V firewall: nothing to open
}

if (-not (DistroExists)) {
    Say "Creating the Linux system '$Distro' (Ubuntu 24.04)"
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
    $image = Join-Path $Dir 'ubuntu.tar.gz'
    $url = "https://cloud-images.ubuntu.com/wsl/releases/24.04/current/ubuntu-noble-wsl-$arch-24.04lts.rootfs.tar.gz"
    Write-Host "Downloading Ubuntu (about 350 MB)"
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $url -OutFile $image -UseBasicParsing
    $r = Wsl --import $Distro (Join-Path $Dir 'disk') $image --version 2
    if ($r.Code -ne 0) { Write-Host $r.Out -ForegroundColor Red; Done 1 }
    Remove-Item $image -Force
    $conf = "[boot]`nsystemd=true`n[user]`ndefault=root`n[network]`nhostname=$($Distro.ToLower())`n"
    $r = Wsl -d $Distro -u root -- sh -c "printf '%s' '$conf' > /etc/wsl.conf"
    Wsl --terminate $Distro | Out-Null
}

# ---------------------------------------------------------------- 3. the project
Say "Installing $Name in '$Distro' (the first time takes 5 to 20 minutes)"
$tz = 'Etc/UTC'
try {
    [void][Windows.Globalization.Calendar, Windows.Globalization, ContentType = WindowsRuntime]
    $tz = ([Windows.Globalization.Calendar]::new()).GetTimeZone()
} catch { }
& wsl.exe -d $Distro -u root -- bash -c "curl -fsSL '$SetupUrl' | HOST_TZ='$tz' bash -s $Project"
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host "The installation stopped with an error. The log is in $Dir\install.log" -ForegroundColor Red
    Write-Host 'Run the installer again to retry: it goes on where it stopped.'
    Done 1
}

# ---------------------------------------------------------------- 4. keep it running, shortcuts
Say 'Start with Windows, shortcuts'
$vbs = Join-Path $Dir 'keep-running.vbs'
Set-Content -Path $vbs -Encoding ASCII -Value "CreateObject(""WScript.Shell"").Run ""wsl.exe -d $Distro -u root -- sleep infinity"", 0, False"
$action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "`"$vbs`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

$desktop = [Environment]::GetFolderPath('Desktop')
Set-Content -Path (Join-Path $desktop "$Name.url") -Encoding ASCII -Value "[InternetShortcut]`r`nURL=$($P.Url)`r`n"
$menu = Join-Path ([Environment]::GetFolderPath('Programs')) $Name
New-Item -ItemType Directory -Force -Path $menu | Out-Null
Set-Content -Path (Join-Path $menu "$Name.url") -Encoding ASCII -Value "[InternetShortcut]`r`nURL=$($P.Url)`r`n"
Copy-Item -Force $Self (Join-Path $Dir "$Distro-Setup.exe") -ErrorAction SilentlyContinue
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path $menu "Uninstall $Name.lnk"))
$lnk.TargetPath = Join-Path $Dir "$Distro-Setup.exe"; $lnk.Arguments = '-Uninstall'; $lnk.Save()
$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Amplitude$Distro"
New-Item -Force -Path $key | Out-Null
Set-ItemProperty -Path $key -Name DisplayName -Value $Name
Set-ItemProperty -Path $key -Name Publisher -Value 'johanhoel/amplitude'
Set-ItemProperty -Path $key -Name UninstallString -Value ('"' + (Join-Path $Dir "$Distro-Setup.exe") + '" -Uninstall')
Set-ItemProperty -Path $key -Name InstallLocation -Value $Dir

# ---------------------------------------------------------------- the result
Say 'Done'
& wsl.exe -d $Distro -u root -- cat "/root/$Project-install.txt"
Write-Host ''
Write-Host "On this PC: $($P.Url)   (shortcut on the desktop)"
Write-Host "From a phone: the PC's address instead of localhost, e.g. http://192.168.1.20:$($P.Ports[-1])"
Write-Host "Remove it again: Settings -> Apps -> $Name -> Uninstall"
Start-Process $P.Url
Stop-Transcript | Out-Null
Done 0
