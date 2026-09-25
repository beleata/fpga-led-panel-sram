param(
    [Parameter(Mandatory=$true)][string[]]$Image,
    [ValidateSet(0,90,180,270)][int]$Rotate = 90,
    [ValidateRange(0.1,86400)][double]$Seconds = 10
)
$ErrorActionPreference = 'Stop'
$imagePaths = @($Image | ForEach-Object { (Resolve-Path -LiteralPath $_).Path })
$generated = Join-Path $PSScriptRoot 'generated'
New-Item -ItemType Directory -Force $generated | Out-Null
$statePath = Join-Path $generated 'video-process.json'
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId = $($state.pid)"
    if ($existing -and $existing.CommandLine -like '*usb_video.py*') {
        throw 'Video sender is already running. Run stop_video.ps1 first.'
    }
}
$stopPath = Join-Path $generated 'video.stop'
if (Test-Path -LiteralPath $stopPath) { Remove-Item -LiteralPath $stopPath }
$python = (Get-Command python).Source
$arguments = @('-u', ('"' + (Join-Path $PSScriptRoot 'usb_video.py') + '"'))
if ($imagePaths.Count -gt 1) { $arguments += '--playlist' }
$arguments += @($imagePaths | ForEach-Object { '"' + $_ + '"' })
$arguments += @('--seconds', $Seconds.ToString([Globalization.CultureInfo]::InvariantCulture),
    '--rotate', $Rotate, '--loops', '0',
    '--stop-file', ('"' + $stopPath + '"'))
$process = Start-Process -FilePath $python -ArgumentList $arguments -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $generated 'video-live.log') `
    -RedirectStandardError (Join-Path $generated 'video-error.log')
@{pid=$process.Id; images=$imagePaths; rotate=$Rotate; seconds=$Seconds; started=(Get-Date).ToString('o')} |
    ConvertTo-Json | Set-Content -LiteralPath $statePath
Write-Output "Video sender started, PID $($process.Id). Stop with pico/stop_video.ps1."
