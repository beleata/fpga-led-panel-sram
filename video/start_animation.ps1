$ErrorActionPreference = 'Stop'
$statePath = Join-Path $PSScriptRoot 'animation-process.json'
if (Test-Path -LiteralPath $statePath) {
    $old = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$($old.pid)" -ErrorAction SilentlyContinue
    if ($existing -and $existing.CommandLine -like '*animate.py*--loop*') {
        throw "Animation is already running as PID $($old.pid)"
    }
}
$stopPath = Join-Path $PSScriptRoot 'animation.stop'
if (Test-Path -LiteralPath $stopPath) { Remove-Item -LiteralPath $stopPath }
$python = (Get-Command python).Source
$script = Join-Path $PSScriptRoot 'animate.py'
$logRoot = Join-Path (Split-Path $PSScriptRoot) 'logs'
$process = Start-Process -FilePath $python -ArgumentList @('-u', ('"' + $script + '"'), '--loop') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'animation-loop.stdout.log') -RedirectStandardError (Join-Path $logRoot 'animation-loop.stderr.log') -PassThru
@{pid=$process.Id;stop_file=$stopPath;started=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $statePath
Start-Sleep -Seconds 3
if ($process.HasExited) { throw 'Animation exited; inspect logs/animation-loop.stderr.log' }
Get-Content -LiteralPath (Join-Path $PSScriptRoot 'animation-live.json') -Raw
