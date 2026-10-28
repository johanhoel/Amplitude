# Release the committed code (HEAD) to the server with automatic rollback (extras/release.sh).
#   powershell -File dev\release.ps1 staging
#   powershell -File dev\release.ps1 production      (asks first; staging should have run this commit)
# The server: -Server root@<address>, or set CAMWATCH_SERVER once, e.g. setx CAMWATCH_SERVER root@192.168.1.20
# For humans only - coding agents never deploy (AGENTS.md).
param([Parameter(Mandatory)][ValidateSet("staging", "production")][string]$Target,
      [string]$Server = $(if ($env:CAMWATCH_SERVER) { $env:CAMWATCH_SERVER } else { "root@camwatch.local" }), [switch]$Force)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (git status --porcelain) { throw "uncommitted changes - commit first (the release is exactly HEAD)" }
$commit = git log -1 --format="%h %s"
if ($Target -eq "production") {
    $answer = Read-Host "Release '$commit' to PRODUCTION on $Server? (yes/no)"
    if ($answer -ne "yes") { "cancelled"; return }
}
Write-Host ">> $Target <- $commit"
Get-Content extras\release.sh -Raw | ssh $Server "cat > /tmp/camwatch-release.sh"
$flag = if ($Force) { "--force" } else { "" }
cmd /c "git archive HEAD | ssh $Server `"bash /tmp/camwatch-release.sh $Target $flag`""
if ($LASTEXITCODE -ne 0) { throw "release failed (exit $LASTEXITCODE) - see above" }
