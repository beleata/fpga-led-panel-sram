$ErrorActionPreference = 'Stop'
$env:PATH = "C:\oss-cad-suite\bin;C:\oss-cad-suite\lib;$env:PATH"
$env:YOSYSHQ_ROOT = 'C:\oss-cad-suite'
Push-Location $PSScriptRoot
try {
    & yosys -Q -l synthesis.log synth.ys
    if ($LASTEXITCODE) { throw 'Synthesis failed' }
    & nextpnr-ice40 --hx1k --package vq100 --json video.json --pcf video.pcf --asc video.asc --freq 25 --pre-pack clocks.py --log route.log
    if ($LASTEXITCODE) { throw 'Routing failed' }
    & icepack video.asc video.bin
    if ($LASTEXITCODE) { throw 'Packing failed' }
    Get-FileHash video.bin
} finally { Pop-Location }
