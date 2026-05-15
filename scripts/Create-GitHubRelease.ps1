<#
.SYNOPSIS
    Creates a GitHub Release and uploads the beta ZIP as a downloadable asset.

.DESCRIPTION
    Requires GitHub CLI (gh) to be installed and authenticated.
    Run once: gh auth login
    Then run this script from the repo root.

.EXAMPLE
    .\scripts\Create-GitHubRelease.ps1
    .\scripts\Create-GitHubRelease.ps1 -Tag "v0.9-beta" -ZipName "sw-copilot-beta9"
#>
param(
    [string]$Tag      = "v0.9-beta",
    [string]$ZipName  = "sw-copilot-beta9",
    [string]$Repo     = "siddgawad/sw-copilot"
)

$ErrorActionPreference = "Stop"
$gh = "C:\Program Files\GitHub CLI\gh.exe"

if (-not (Test-Path $gh)) { throw "GitHub CLI not found. Install from: https://cli.github.com" }

$zipPath = Join-Path $PSScriptRoot "..\artifacts\$ZipName.zip"
$zipPath = (Resolve-Path $zipPath).Path

if (-not (Test-Path $zipPath)) {
    throw "ZIP not found: $zipPath`nRun Build-BetaPackage.ps1 -PackageName $ZipName first."
}

$notes = @"
## SW Copilot $Tag — Workflow Automation

Chat-based SolidWorks automation. No macros. No generated code. Deterministic COM execution.

### What's new
- ``update_title_block`` — set revision, drawn by, date, and custom properties from chat
- ``export_file`` — export to PDF/DXF/STEP/IGES/STL with filename templates
- ``check_drawing`` — advisory drawing QA scan (missing properties, empty sheets, dangling dims)
- Deterministic fast paths: box, cylinder, shaft, gear, base plate — no API quota used
- Help/greeting handler — type ``hi`` or ``what can you do?`` for a capability list

### How to install
See [SETUP.md](https://github.com/$Repo/blob/main/SETUP.md) — takes about 10 minutes.

**Requirements:** SolidWorks 2021, Windows 10/11 x64, free [Groq API key](https://console.groq.com/keys)

### SHA-256
``$(Get-FileHash $zipPath -Algorithm SHA256 | Select-Object -ExpandProperty Hash)``
"@

Write-Host "Creating GitHub Release $Tag on $Repo..."
Write-Host "ZIP: $zipPath ($([math]::Round((Get-Item $zipPath).Length/1MB,1)) MB)"
Write-Host ""

& $gh release create $Tag `
    --repo $Repo `
    --title "SW Copilot $Tag — Workflow Automation" `
    --notes $notes `
    "$zipPath#$ZipName.zip"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Release created: https://github.com/$Repo/releases/tag/$Tag"
    Write-Host "Direct download: https://github.com/$Repo/releases/download/$Tag/$ZipName.zip"
}
