#Requires -Version 5.1
param(
    [string]$InstallDir = "$env:USERPROFILE\Indus Transports Auto Dialer",
    [switch]$UseExeOnly,
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$PythonInstallerUrl = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
$AppName = "Indus Transports Auto Dialer"
$ExeName = "IndusTransports_AutoDialer.exe"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Add-PathIfExists([string]$Path) {
    if ((Test-Path $Path) -and ($env:Path -notlike "*$Path*")) {
        $env:Path = "$Path;$env:Path"
    }
}

function Ensure-Python {
    Add-PathIfExists "$env:ProgramFiles\Python312"
    Add-PathIfExists "$env:ProgramFiles\Python312\Scripts"
    Add-PathIfExists "$env:LocalAppData\Programs\Python\Python312"
    Add-PathIfExists "$env:LocalAppData\Programs\Python\Python312\Scripts"
    if ((Test-Command "py") -or (Test-Command "python")) {
        Write-Host "Python already installed." -ForegroundColor Green
        return
    }
    Write-Step "Installing Python 3.12"
    $pythonExe = Join-Path $env:TEMP "indus-dialer-python-3.12.exe"
    Invoke-WebRequest -Uri $PythonInstallerUrl -OutFile $pythonExe -UseBasicParsing
    $p = Start-Process -FilePath $pythonExe -ArgumentList @(
        "/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_launcher=1", "Include_test=0"
    ) -Wait -PassThru
    if ($p.ExitCode -notin @(0, 3010)) {
        throw "Python installer failed with exit code $($p.ExitCode)."
    }
    Add-PathIfExists "$env:ProgramFiles\Python312"
    Add-PathIfExists "$env:ProgramFiles\Python312\Scripts"
}

function Ensure-RuntimeDirs([string]$Root) {
    foreach ($name in @("logs", "data", "chrome_profiles")) {
        $path = Join-Path $Root $name
        if (-not (Test-Path -LiteralPath $path)) {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }
    }
}

function New-DesktopShortcut([string]$Target, [string]$WorkDir, [string]$Label) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $lnk = Join-Path $desktop "$Label.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($lnk)
    $shortcut.TargetPath = $Target
    $shortcut.WorkingDirectory = $WorkDir
    $icon = Join-Path $WorkDir "logo.ico"
    if (Test-Path -LiteralPath $icon) { $shortcut.IconLocation = $icon }
    $shortcut.Description = $Label
    $shortcut.Save()
    Write-Host "Desktop shortcut: $lnk" -ForegroundColor Green
}

$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Step "Preparing install folder: $InstallDir"
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

$distExe = Join-Path $SourceRoot "dist\$ExeName"
$rootExe = Join-Path $SourceRoot $ExeName
$hasExe = (Test-Path -LiteralPath $distExe) -or (Test-Path -LiteralPath $rootExe)

if ($hasExe -or $UseExeOnly) {
    Write-Step "Installing packaged EXE"
    $exeSource = if (Test-Path -LiteralPath $distExe) { $distExe } else { $rootExe }
    if (-not (Test-Path -LiteralPath $exeSource)) {
        throw "EXE not found. Run 'Build Auto Dialer.bat' on the administrator PC first."
    }
    Copy-Item -LiteralPath $exeSource -Destination (Join-Path $InstallDir $ExeName) -Force
    foreach ($name in @("dialer_config.json", "indus_transports_logo.jpg", "logo.ico")) {
        $src = Join-Path $SourceRoot $name
        if (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $InstallDir $name) -Force
        }
    }
    Ensure-RuntimeDirs $InstallDir
    $launchTarget = Join-Path $InstallDir $ExeName
} else {
    Write-Step "Installing Python source build"
    Ensure-Python
    Write-Step "Copying application files"
    $exclude = @("build", "dist", ".git", ".codegraph", ".pytest_cache", "chrome_profiles", "logs", "__pycache__")
    Get-ChildItem -LiteralPath $SourceRoot -Force | Where-Object {
        $_.Name -notin $exclude
    } | ForEach-Object {
        $dest = Join-Path $InstallDir $_.Name
        if ($_.PSIsContainer) {
            if (-not (Test-Path -LiteralPath $dest)) {
                Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force
            }
        } else {
            Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
        }
    }
    Ensure-RuntimeDirs $InstallDir
    Write-Step "Installing Python packages (may take several minutes)"
    Push-Location $InstallDir
    try {
        python -m pip install --upgrade pip
        python -m pip install -r requirements.txt
    } finally {
        Pop-Location
    }
    $launchTarget = Join-Path $InstallDir "Start Auto Dialer.bat"
    if (-not (Test-Path -LiteralPath $launchTarget)) {
        @"
@echo off
cd /d "%~dp0"
python autodialer_gui.py
"@ | Set-Content -LiteralPath $launchTarget -Encoding ASCII
    }
}

if (-not $NoShortcut) {
    New-DesktopShortcut -Target $launchTarget -WorkDir $InstallDir -Label $AppName
}

Write-Step "Install complete"
Write-Host ""
Write-Host "Installed to: $InstallDir" -ForegroundColor Green
Write-Host "Launch with the desktop shortcut or Start Auto Dialer.bat"
Write-Host ""
Write-Host "CLIENT LOGIN: use credentials from your administrator."
Write-Host "If this is a fresh client PC, copy the admin export package"
Write-Host "(dialer_config.json, logs, data, chrome_profiles) into this folder."
