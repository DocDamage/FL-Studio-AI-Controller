param([switch]$CoreOnly)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$Root = (Get-Location).Path
function Check-Native([string]$Message) { if ($LASTEXITCODE -ne 0) { throw $Message } }
Write-Host "FL Studio AI Copilot 0.4.0 - Windows source setup" -ForegroundColor Green
Write-Host "This creates a local .venv and downloads Python dependencies. No FL project is changed."
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    $Launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($Launcher) {
        & py -3.13 -c "import sys,struct; assert struct.calcsize('P')==8; print(sys.version)"
        if ($LASTEXITCODE -eq 0) {
            & py -3.13 -m venv .venv
            Check-Native 'Could not create the Python 3.13 environment.'
        } else {
            throw 'Install 64-bit Python 3.13 including the py launcher, then run setup again.'
        }
    } else {
        $Base = Get-Command python -ErrorAction SilentlyContinue
        if (-not $Base) { throw 'Install 64-bit Python 3.13 with the py launcher, then rerun setup.' }
        & python -c "import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize('P')==8, 'Use 64-bit Python 3.13'"
        Check-Native 'Use 64-bit Python 3.13 for this development build.'
        & python -m venv .venv
        Check-Native 'Could not create the Python environment.'
    }
}
& $Python -c "import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize('P')==8, 'Use 64-bit Python 3.13'"
Check-Native 'The existing .venv must use 64-bit Python 3.13. Rename it and rerun setup.'
& $Python -m pip install --upgrade pip 'setuptools>=77'
Check-Native 'pip / setuptools installation failed.'
& $Python -m pip install -r requirements-core.txt
Check-Native 'Core dependency installation failed.'
& $Python -m pip install --no-deps -e .
Check-Native 'Application installation failed.'
if (-not $CoreOnly) {
    $Answer = Read-Host 'Install the pinned PostFader live adapter too? [Y/n]'
    if ($Answer -notmatch '^[Nn]') {
        & $Python -m pip install -r requirements-postfader.txt
        Check-Native 'Live adapter installation failed. Core-only audio/demo still works.'
        & $Python -m pip check
        Check-Native 'Dependency conflict detected; do not use the live adapter until resolved.'
        Write-Host 'Installed live adapter source. Actual Windows/FL qualification still needs your disposable project.' -ForegroundColor Yellow
        Write-Host 'Next: close FL, configure a bidirectional virtual MIDI endpoint, then run CONNECT_FL.cmd.'
    }
}
Write-Host 'Setup finished. Run START_DEMO.cmd to test the interface without touching FL.' -ForegroundColor Green
Write-Host 'START_LIVE.cmd uses the bridge; imported-audio tools also work while disconnected.'
