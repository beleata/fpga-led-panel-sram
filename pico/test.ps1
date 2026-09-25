$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
$env:PATH="C:\oss-cad-suite\bin;C:\oss-cad-suite\lib;$env:PATH"
python "$PSScriptRoot\generate_wave.py"
if($LASTEXITCODE) {throw 'Generator failed'}
python -m unittest discover -s $PSScriptRoot -p test_wave.py -v
if($LASTEXITCODE) {throw 'Wave tests failed'}
iverilog -g2012 -DSIMULATION -s tb_reference -o "$PSScriptRoot\generated\reference.vvp" "$PSScriptRoot\tb_reference.v" "$root\panel\panel.v"
if($LASTEXITCODE) {throw 'Reference compile failed'}
Push-Location "$root\panel"
try { vvp "$PSScriptRoot\generated\reference.vvp" } finally {Pop-Location}
if($LASTEXITCODE) {throw 'Reference simulation failed'}
python "$PSScriptRoot\generate_wave.py" --reference "$PSScriptRoot\generated\fpga-reference.bin"
if($LASTEXITCODE) {throw 'FPGA/PIO comparison failed'}
