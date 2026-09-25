$ErrorActionPreference = 'Stop'
$generated = Join-Path $PSScriptRoot 'generated'
New-Item -ItemType Directory -Force $generated | Out-Null
New-Item -ItemType File -Force (Join-Path $generated 'video.stop') | Out-Null
Write-Output 'Stop requested. The Pico keeps the last complete frame in RAM while powered.'
