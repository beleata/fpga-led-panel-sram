$ErrorActionPreference = 'Stop'
# Finish the current acknowledged frame, release COM18, and retain that image.
$stopPath = Join-Path $PSScriptRoot 'animation.stop'
$null = New-Item -ItemType File -Path $stopPath -Force
Write-Output 'Stop requested. The current frame finishes before COM18 is released.'
