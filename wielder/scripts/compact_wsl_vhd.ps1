[CmdletBinding()]
param(
    [string]$DistroName,
    [string]$VhdPath,
    [switch]$EnableSparseForFutureReclaim
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[compact-wsl-vhd] $Message"
}

function Assert-Administrator {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This script must be run from an elevated PowerShell session."
    }
}

function Resolve-DistroVhdPath {
    param([string]$ResolvedDistroName)

    $lxssRoot = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss"
    if (-not (Test-Path $lxssRoot)) {
        throw "Could not find the WSL registry root at [$lxssRoot]."
    }

    $matches = @()
    foreach ($entry in Get-ChildItem -Path $lxssRoot) {
        $props = Get-ItemProperty -Path $entry.PSPath
        if ($props.DistributionName -eq $ResolvedDistroName) {
            $matches += $props
        }
    }

    $matches = @($matches)

    if ($matches.Count -eq 0) {
        throw "Could not find a registered WSL distribution named [$ResolvedDistroName]."
    }
    if ($matches.Count -gt 1) {
        throw "Found multiple WSL distributions named [$ResolvedDistroName]. Resolve the VHD path explicitly with -VhdPath."
    }

    $basePath = $matches[0].BasePath
    if (-not $basePath) {
        throw "WSL registry entry for [$ResolvedDistroName] does not expose a BasePath."
    }

    $candidateRoots = @(
        $basePath,
        (Join-Path $basePath "LocalState")
    ) | Select-Object -Unique

    $vhds = @()
    foreach ($root in $candidateRoots) {
        if (Test-Path $root) {
            $vhds += Get-ChildItem -Path $root -Filter *.vhd* -File -ErrorAction SilentlyContinue
        }
    }

    $vhds = @($vhds | Select-Object -Unique FullName)
    if ($vhds.Count -eq 0) {
        throw "No VHD/VHDX files were found under [$basePath] for distro [$ResolvedDistroName]."
    }
    if ($vhds.Count -gt 1) {
        throw "Found multiple VHD/VHDX files for distro [$ResolvedDistroName]. Resolve the path explicitly with -VhdPath.`n$($vhds.FullName -join "`n")"
    }

    return $vhds[0].FullName
}

function Invoke-DiskpartCompact {
    param([string]$ResolvedVhdPath)

    $diskpartScript = @"
select vdisk file="$ResolvedVhdPath"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@

    $scriptPath = Join-Path $env:TEMP ("compact-wsl-vhd-" + [guid]::NewGuid().ToString() + ".txt")
    Set-Content -Path $scriptPath -Value $diskpartScript -Encoding Ascii
    try {
        Write-Step "Running diskpart compaction for [$ResolvedVhdPath]."
        & diskpart /s $scriptPath
    }
    finally {
        Remove-Item -Path $scriptPath -Force -ErrorAction SilentlyContinue
    }
}

Assert-Administrator

if (-not $VhdPath -and -not $DistroName) {
    throw "Provide either -DistroName <name> or -VhdPath <path-to-vhdx>."
}

if (-not $DistroName -and $EnableSparseForFutureReclaim) {
    throw "-EnableSparseForFutureReclaim requires -DistroName."
}

if (-not $VhdPath) {
    $VhdPath = Resolve-DistroVhdPath -ResolvedDistroName $DistroName
}

if (-not (Test-Path $VhdPath)) {
    throw "The resolved VHD path does not exist: [$VhdPath]"
}

if ($EnableSparseForFutureReclaim) {
    Write-Step "Enabling sparse VHD for future automatic reclaim on distro [$DistroName]."
    & wsl.exe --manage $DistroName --set-sparse true
}

Write-Step "Shutting down WSL before compaction."
& wsl.exe --shutdown

Write-Step "Compacting [$VhdPath]."
Invoke-DiskpartCompact -ResolvedVhdPath $VhdPath

Write-Step "Done. If the Windows disk still looks inflated, verify no WSL instance or Docker Desktop process restarted during compaction."
