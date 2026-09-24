$ErrorActionPreference = 'Stop'
$env:PATH = "C:\oss-cad-suite\bin;C:\oss-cad-suite\lib;$env:PATH"
$env:YOSYSHQ_ROOT = 'C:\oss-cad-suite'
Push-Location $PSScriptRoot
try {
    Copy-Item -LiteralPath ../panel/pattern.hex -Destination pattern.hex
    & yosys -Q -l synthesis.log synth.ys
    if ($LASTEXITCODE) { throw 'Synthesis failed' }
    & nextpnr-ice40 --hx1k --package vq100 --json link_diag.json --pcf link_diag.pcf --asc link_diag.asc --freq 25 --pre-pack clocks.py --log route.log
    if ($LASTEXITCODE) { throw 'Routing failed' }
    & icepack link_diag.asc link_diag.bin
    if ($LASTEXITCODE) { throw 'Packing failed' }
    Get-FileHash link_diag.bin
} finally { Pop-Location }
