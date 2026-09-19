$ErrorActionPreference='Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$Python=Join-Path (Get-Location).Path '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Run SETUP_WINDOWS.cmd first.' }
& $Python -c "import fl_studio_mcp"
if ($LASTEXITCODE -ne 0) { throw 'Run setup and select the live adapter before connecting FL.' }
Write-Host 'Close FL Studio before bridge deployment. Keep other PostFader/MCP clients closed.' -ForegroundColor Yellow
Write-Host 'A bidirectional virtual MIDI endpoint must already exist. This script installs no drivers.'
$Endpoint=Read-Host 'Exact MIDI endpoint name for both input and output'
if ([string]::IsNullOrWhiteSpace($Endpoint) -or $Endpoint.Length -gt 160) { throw 'A nonempty exact endpoint name is required.' }
$Settings=Join-Path (Get-Location).Path 'local-settings.json'
if (Test-Path $Settings) {
    $Config=Get-Content -Raw $Settings | ConvertFrom-Json
    $Config | Add-Member -MemberType NoteProperty -Name midi_port -Value $Endpoint -Force
    $Confirm=Read-Host 'Update only the MIDI endpoint in existing local-settings.json? [y/N]'
    if ($Confirm -notmatch '^[Yy]$') { throw 'Existing settings preserved.' }
} else { $Config=[PSCustomObject]@{midi_port=$Endpoint} }
$env:FL_BRIDGE_MIDI_PORT=$Endpoint
$env:FL_BRIDGE_ENABLE_MIDI='1'
if ($Config.PSObject.Properties['fl_user_data']) { $env:FL_STUDIO_USER_DATA_DIR=$Config.fl_user_data }
$PostFader=Join-Path (Get-Location).Path '.venv\Scripts\postfader.exe'
& $PostFader setup
if ($LASTEXITCODE -ne 0) { throw 'PostFader setup did not finish. Existing local settings have not been overwritten.' }
$Config | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 ($Settings+'.tmp')
Move-Item -Force ($Settings+'.tmp') $Settings
Write-Host 'MIDI endpoint saved. Complete the FL input/output port settings and reload Universal Bridge.' -ForegroundColor Green
Write-Host 'Then use a disposable project, run START_LIVE.cmd, and click Inspect session.'
