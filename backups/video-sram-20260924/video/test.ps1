$ErrorActionPreference = 'Stop'
$env:PATH = "C:\oss-cad-suite\bin;C:\oss-cad-suite\lib;$env:PATH"
Push-Location $PSScriptRoot
try {
    python -m unittest -v test_sender
    if ($LASTEXITCODE) { throw 'Sender tests failed' }
    iverilog -g2012 -DSIMULATION -s tb_video -o tb_video.vvp tb_video.v video.v panel_scan.v uart.v frame_memory.v frame_protocol.v
    if ($LASTEXITCODE) { throw 'Simulation compile failed' }
    vvp tb_video.vvp
    if ($LASTEXITCODE) { throw 'Simulation failed' }
} finally { Pop-Location }
