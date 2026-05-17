#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Registers SwCopilotAddin.dll with RegAsm for development/testing.

.DESCRIPTION
    RegAsm must resolve all referenced assemblies at registration time.
    The SolidWorks interop DLLs are marked Private=false in the csproj
    (correct — SolidWorks loads them from its own directory at runtime),
    but that means they are NOT copied to the build output.

    This script copies the three required interop DLLs alongside the add-in
    DLL, runs RegAsm /codebase, then restores the output directory to its
    original state by removing the temporary copies.

.PARAMETER BuildConfig
    Which build configuration to register. Default: Release-beta2.

.PARAMETER SolidWorksPath
    Path to the SolidWorks installation directory.
    Default: read from Directory.Build.props, or C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS.

.EXAMPLE
    # From an elevated PowerShell prompt in sw-addin-client\:
    .\Register-DevAddin.ps1

.EXAMPLE
    .\Register-DevAddin.ps1 -BuildConfig Release-beta2
#>
param(
    [string]$BuildConfig  = "Release-beta2",
    [string]$SolidWorksPath = ""
)

$ErrorActionPreference = "Stop"

# ── Resolve paths ─────────────────────────────────────────────────────────────

$scriptDir = $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($SolidWorksPath)) {
    # Try to read from Directory.Build.props
    $propsFile = Join-Path $scriptDir "Directory.Build.props"
    if (Test-Path $propsFile) {
        [xml]$props = Get-Content $propsFile
        $SolidWorksPath = $props.Project.PropertyGroup.SolidWorksPath
    }
    if ([string]::IsNullOrWhiteSpace($SolidWorksPath)) {
        $SolidWorksPath = "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS"
    }
}

function Ensure-RuntimeDependencies {
    param(
        [Parameter(Mandatory = $true)][string]$OutputDirectory
    )

    $requiredRuntimeDlls = @(
        "Newtonsoft.Json.dll",
        "Microsoft.CodeAnalysis.dll",
        "Microsoft.CodeAnalysis.CSharp.dll",
        "System.Buffers.dll",
        "System.Collections.Immutable.dll",
        "System.Memory.dll",
        "System.Numerics.Vectors.dll",
        "System.Reflection.Metadata.dll",
        "System.Runtime.CompilerServices.Unsafe.dll",
        "System.Text.Encoding.CodePages.dll",
        "System.Threading.Tasks.Extensions.dll"
    )

    $missing = @($requiredRuntimeDlls | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $OutputDirectory $_))
    })

    if ($missing.Count -eq 0) {
        return
    }

    Write-Host "Runtime dependencies missing from $OutputDirectory"
    foreach ($dll in $missing) {
        Write-Host "  Missing: $dll"
    }
    Write-Host "Rebuilding add-in output to restore runtime dependencies..."

    $projectFile = Join-Path $scriptDir "SwCopilotAddin.csproj"
    & dotnet build $projectFile -c Release -p:Platform=x64 -p:RegisterForComInterop=false "-p:OutDir=$OutputDirectory\"
    if ($LASTEXITCODE -ne 0) {
        throw "dotnet build failed while restoring runtime dependencies."
    }

    $stillMissing = @($requiredRuntimeDlls | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $OutputDirectory $_))
    })

    if ($stillMissing.Count -gt 0) {
        throw "Build completed but runtime dependencies are still missing from ${OutputDirectory}: $($stillMissing -join ', ')"
    }
}

$outDir  = Join-Path $scriptDir "bin\x64\$BuildConfig\net48"
$addinDll = Join-Path $outDir "SwCopilotAddin.dll"
$regasm  = Join-Path $env:SystemRoot "Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"

if (-not (Test-Path $addinDll)) {
    throw "DLL not found: $addinDll`nBuild the project first: dotnet build -c Release -p:Platform=x64 -p:OutDir=$outDir"
}
if (-not (Test-Path $regasm)) {
    throw "64-bit RegAsm not found: $regasm"
}

# ── Interop DLLs needed by RegAsm at registration time ───────────────────────

Ensure-RuntimeDependencies -OutputDirectory $outDir

$interopDlls = @(
    "SolidWorks.Interop.sldworks.dll",
    "SolidWorks.Interop.swconst.dll",
    "SolidWorks.Interop.swpublished.dll"
)

$copied = @()
foreach ($dll in $interopDlls) {
    $src = Join-Path $SolidWorksPath $dll
    $dst = Join-Path $outDir $dll
    if (-not (Test-Path $src)) {
        throw "SolidWorks interop DLL not found: $src`nCheck -SolidWorksPath parameter."
    }
    if (-not (Test-Path $dst)) {
        Copy-Item $src $dst -Force
        $copied += $dst
        Write-Host "  Copied $dll → $outDir"
    }
}

# ── Register ──────────────────────────────────────────────────────────────────

try {
    Write-Host ""
    Write-Host "Registering: $addinDll"
    & $regasm $addinDll /codebase
    if ($LASTEXITCODE -ne 0) {
        throw "RegAsm exited with code $LASTEXITCODE."
    }
    Write-Host ""
    Write-Host "Registration complete. Restart SolidWorks to load the updated add-in."
}
finally {
    # Remove the temporary interop copies — they must not ship with the add-in.
    foreach ($dst in $copied) {
        Remove-Item $dst -Force -ErrorAction SilentlyContinue
    }
    if ($copied.Count -gt 0) {
        Write-Host "Cleaned up temporary interop DLL copies."
    }
}
