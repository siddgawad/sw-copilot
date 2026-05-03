<#
.SYNOPSIS
    Builds a local beta ZIP folder for SW Copilot.

.DESCRIPTION
    Produces a self-contained folder under artifacts\sw-copilot-beta containing:
      - addin\SwCopilotAddin.dll and managed dependencies
      - addin\backend\SwCopilotBackend\SwCopilotBackend.exe
      - Install-SwCopilot.ps1 / Uninstall-SwCopilot.ps1
      - README-BETA.txt

    The generated install script registers the add-in in place with RegAsm.
    Users must keep the extracted folder after installation because /codebase
    points COM registration at that physical DLL path.
#>
param(
    [string]$Configuration = "Release",
    [string]$PackageName = "sw-copilot-beta",
    [switch]$SkipBackendBuild,
    [switch]$SkipAddinBuild
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$addinProject = Join-Path $repoRoot "sw-addin-client\SwCopilotAddin.csproj"
$backendDir = Join-Path $repoRoot "agent-backend"
$artifactsRoot = Join-Path $repoRoot "artifacts"
$stagingRoot = Join-Path $artifactsRoot "_staging"
$addinOut = Join-Path $stagingRoot "addin"
$packageRoot = Join-Path $artifactsRoot $PackageName
$packageAddin = Join-Path $packageRoot "addin"
$packageBackendParent = Join-Path $packageAddin "backend"
$backendDist = Join-Path $backendDir "dist\SwCopilotBackend"

function Reset-Directory([string]$Path) {
    if (Test-Path $Path) {
        $resolved = (Resolve-Path $Path).Path
        if (-not $resolved.StartsWith($artifactsRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove path outside artifacts: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }

    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

New-Item -ItemType Directory -Force -Path $artifactsRoot | Out-Null
Reset-Directory $stagingRoot
Reset-Directory $packageRoot
New-Item -ItemType Directory -Force -Path $addinOut | Out-Null
New-Item -ItemType Directory -Force -Path $packageBackendParent | Out-Null

if (-not $SkipAddinBuild) {
    Write-Host "Building C# add-in..."
    & dotnet build $addinProject `
        -c $Configuration `
        -p:Platform=x64 `
        -p:RegisterForComInterop=false `
        "-p:OutDir=$addinOut\"
    if ($LASTEXITCODE -ne 0) { throw "dotnet build failed with exit code $LASTEXITCODE" }
}

if (-not $SkipBackendBuild) {
    $python = Join-Path $backendDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        throw "Backend venv not found: $python. Create it first with: py -3.11 -m venv agent-backend\.venv"
    }

    Push-Location $backendDir
    try {
        & $python -m PyInstaller --version *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller is not installed. Run: .venv\Scripts\python.exe -m pip install -r requirements-build.txt"
        }

        Write-Host "Building packaged backend..."
        & $python -m PyInstaller sw_copilot_backend.spec --noconfirm --clean
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $addinOut "SwCopilotAddin.dll"))) {
    throw "Add-in build output missing: $addinOut\SwCopilotAddin.dll"
}
if (-not (Test-Path (Join-Path $backendDist "SwCopilotBackend.exe"))) {
    throw "Backend build output missing: $backendDist\SwCopilotBackend.exe"
}

Copy-Item -Path (Join-Path $addinOut "*") -Destination $packageAddin -Recurse -Force
Copy-Item -Path $backendDist -Destination $packageBackendParent -Recurse -Force

$envExample = @"
# Required. Get a key from https://console.groq.com/keys
GROQ_API_KEY=replace_with_your_key

# Optional
GROQ_MODEL=llama-3.3-70b-versatile
"@
$backendPackageDir = Join-Path $packageBackendParent "SwCopilotBackend"
$envExample | Set-Content -Path (Join-Path $backendPackageDir ".env.example") -Encoding UTF8

$installScript = @'
#Requires -RunAsAdministrator
param(
    [string]$SolidWorksPath = "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS 2021"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$addinDir = Join-Path $root "addin"
$addinDll = Join-Path $addinDir "SwCopilotAddin.dll"
$regasm = Join-Path $env:SystemRoot "Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"

if (-not (Test-Path $addinDll)) { throw "Add-in DLL not found: $addinDll" }
if (-not (Test-Path $regasm)) { throw "64-bit RegAsm not found: $regasm" }

$interopDlls = @(
    "SolidWorks.Interop.sldworks.dll",
    "SolidWorks.Interop.swconst.dll",
    "SolidWorks.Interop.swpublished.dll"
)

$copied = @()
foreach ($dll in $interopDlls) {
    $src = Join-Path $SolidWorksPath $dll
    $dst = Join-Path $addinDir $dll
    if (-not (Test-Path $src)) { throw "SolidWorks interop DLL not found: $src" }
    if (-not (Test-Path $dst)) {
        Copy-Item $src $dst -Force
        $copied += $dst
    }
}

try {
    & $regasm $addinDll /codebase
    if ($LASTEXITCODE -ne 0) { throw "RegAsm failed with exit code $LASTEXITCODE" }
    Write-Host "SW Copilot registered. Restart SolidWorks, then enable SW Copilot in Tools > Add-Ins."
}
finally {
    foreach ($dst in $copied) {
        Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue
    }
}
'@
$installScript | Set-Content -Path (Join-Path $packageRoot "Install-SwCopilot.ps1") -Encoding UTF8

$uninstallScript = @'
#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$addinDll = Join-Path $PSScriptRoot "addin\SwCopilotAddin.dll"
$regasm = Join-Path $env:SystemRoot "Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"

if (-not (Test-Path $addinDll)) { throw "Add-in DLL not found: $addinDll" }
& $regasm $addinDll /unregister
if ($LASTEXITCODE -ne 0) { throw "RegAsm unregister failed with exit code $LASTEXITCODE" }
Write-Host "SW Copilot unregistered. Restart SolidWorks."
'@
$uninstallScript | Set-Content -Path (Join-Path $packageRoot "Uninstall-SwCopilot.ps1") -Encoding UTF8

$readme = @"
SW Copilot Beta Package
=======================

Install:
1. Extract this folder somewhere stable. Do not run from inside the ZIP.
2. Copy addin\backend\SwCopilotBackend\.env.example to .env and set GROQ_API_KEY.
3. Close SolidWorks.
4. Open PowerShell as Administrator in this folder.
5. Run: .\Install-SwCopilot.ps1
6. Start SolidWorks, open Tools > Add-Ins, enable SW Copilot.

Backend:
- The add-in auto-starts addin\backend\SwCopilotBackend\SwCopilotBackend.exe.
- The backend listens on http://127.0.0.1:8001.
- A fresh auth token is written to %LOCALAPPDATA%\SwCopilotAddin\backend.token every backend startup.

Uninstall:
1. Close SolidWorks.
2. Open PowerShell as Administrator in this folder.
3. Run: .\Uninstall-SwCopilot.ps1
"@
$readme | Set-Content -Path (Join-Path $packageRoot "README-BETA.txt") -Encoding UTF8

$zipPath = Join-Path $artifactsRoot "$PackageName.zip"
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $packageRoot "*") -DestinationPath $zipPath -Force

Write-Host ""
Write-Host "Beta package ready:"
Write-Host "  $packageRoot"
Write-Host "  $zipPath"
