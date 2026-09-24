$ErrorActionPreference = 'Stop'
$cadRoot = 'C:\oss-cad-suite'
$env:PATH = "$cadRoot\bin;$cadRoot\lib;$env:PATH"
$env:YOSYSHQ_ROOT = $cadRoot
Push-Location "$PSScriptRoot\panel"
try {
    & yosys -Q -l synthesis.log synth.ys
    if ($LASTEXITCODE) { throw 'Synthesis failed' }
    & nextpnr-ice40 --hx1k --package vq100 --json panel.json --pcf panel.pcf --asc panel.asc --freq 25 --pre-pack clocks.py --log route.log
    if ($LASTEXITCODE) { throw 'Place and route failed' }
    & icepack panel.asc panel.bin
    if ($LASTEXITCODE) { throw 'Bitstream packing failed' }
    Get-FileHash panel.bin -Algorithm SHA256
} finally { Pop-Location }
