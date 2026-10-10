# Installs the Archipelago bridge for Mass Effect 1 (LE): copies LE1APBridge.asi and LE1APBridge.checks.tsv from the
# ASI folder next to this script into <game>\Game\ME1\Binaries\Win64\ASI, replacing older LE1APBridge*.asi files.
# Usage: right-click > Run with PowerShell, or:  powershell -ExecutionPolicy Bypass -File install-bridge.ps1 -GamePath "D:\Games\Mass Effect Legendary Edition"
param([string]$GamePath)
$ErrorActionPreference = 'Stop'

function Test-Game([string]$Path) {
    return $Path -and (Test-Path -LiteralPath (Join-Path $Path 'Game\ME1\Binaries\Win64\MassEffect1.exe'))
}

$candidates = @()
if ($GamePath) { $candidates += $GamePath }
else {
    $steamRoots = @('C:\Program Files (x86)\Steam', 'C:\Steam')
    try { $steamRoots += (Get-ItemProperty 'HKCU:\Software\Valve\Steam' -ErrorAction Stop).SteamPath -replace '/', '\' } catch {}
    foreach ($root in ($steamRoots | Select-Object -Unique)) {
        $vdf = Join-Path $root 'steamapps\libraryfolders.vdf'
        $libraries = @($root)
        if (Test-Path -LiteralPath $vdf) {
            $libraries += Select-String -LiteralPath $vdf -Pattern '"path"\s+"([^"]+)"' | ForEach-Object { $_.Matches[0].Groups[1].Value -replace '\\\\', '\' }
        }
        foreach ($lib in $libraries) { $candidates += Join-Path $lib 'steamapps\common\Mass Effect Legendary Edition' }
    }
    $candidates += 'C:\Program Files\EA Games\Mass Effect Legendary Edition'
}

$game = $candidates | Where-Object { Test-Game $_ } | Select-Object -First 1
if (-not $game) {
    Write-Host "Mass Effect Legendary Edition not found. Run again with -GamePath ""<folder that contains Game\ME1>""." -ForegroundColor Red
    if (-not $GamePath) { Read-Host 'Press Enter to close' }
    exit 1
}

$source = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'ASI'
$asiDir = Join-Path $game 'Game\ME1\Binaries\Win64\ASI'
New-Item -ItemType Directory -Force -Path $asiDir | Out-Null
Get-ChildItem -LiteralPath $asiDir -Filter 'LE1APBridge*.asi' | Remove-Item -Force
Copy-Item -LiteralPath (Join-Path $source 'LE1APBridge.asi') -Destination $asiDir -Force
Copy-Item -LiteralPath (Join-Path $source 'LE1APBridge.checks.tsv') -Destination $asiDir -Force
Write-Host "Bridge installed to $asiDir" -ForegroundColor Green
if (-not $GamePath) { Read-Host 'Press Enter to close' }
