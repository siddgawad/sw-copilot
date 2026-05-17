#Requires -Version 5.1
<#
.SYNOPSIS
  Deploy the freshly-built C:\Projects\sw-copilot DLL into the location
  SolidWorks is registered to load from (C:\Users\theof\sw-addin-client\...).

.DESCRIPTION
  Two repos drifted apart. SolidWorks is registered against the C:\Users\theof
  path, but C:\Projects\sw-copilot is now the source of truth. Rather than
  re-registering (which requires admin), this script just overwrites the
  loaded DLL location with the freshly-built Projects DLL and its
  dependencies. No admin needed.

  After running this, restart SolidWorks and the add-in will load the
  merged-and-rebuilt code.

.NOTES
  Requires SolidWorks to be CLOSED. The script aborts if SLDWORKS.exe is
  running. Run this from any PowerShell prompt (no elevation needed).
#>

[CmdletBinding()]
param(
    [string] $Source = 'C:\Projects\sw-copilot\sw-addin-client\bin\x64\Release-beta2\net48',
    [string] $Target = 'C:\Users\theof\sw-addin-client\bin\x64\Release-beta2\net48'
)

$ErrorActionPreference = 'Stop'

$sw = Get-Process -Name SLDWORKS -ErrorAction SilentlyContinue
if ($sw) {
    Write-Error "SolidWorks is running (PID $($sw.Id)). Close it first, then re-run this script."
    exit 1
}

if (-not (Test-Path $Source)) {
    Write-Error "Source not found: $Source. Build the Projects solution first."
    exit 1
}

if (-not (Test-Path $Target)) {
    Write-Error "Target not found: $Target. SolidWorks may not be registered against this path."
    exit 1
}

Write-Host "Source: $Source"
Write-Host "Target: $Target"
Write-Host ""

$files = Get-ChildItem $Source -File
foreach ($file in $files) {
    $dest = Join-Path $Target $file.Name
    Copy-Item $file.FullName $dest -Force
    Write-Host "  copied: $($file.Name)"
}

Write-Host ""
Write-Host "Deployment complete. Restart SolidWorks to load the new DLL."
Write-Host "The next /generate call will route through patterns/plate.py (no LLM)."
