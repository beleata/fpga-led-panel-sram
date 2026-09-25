$ErrorActionPreference='Stop'
$tools=Join-Path $env:USERPROFILE '.cache\pico-panel'
$cmake=Join-Path $tools 'python\cmake\data\bin\cmake.exe'
$ninja=Join-Path $tools 'python\bin\ninja.exe'
$compiler=Get-ChildItem (Join-Path $tools 'arm') -Filter arm-none-eabi-gcc.exe -Recurse | Select-Object -First 1
if(-not $compiler) {throw 'Arm compiler is not installed'}
$env:PICO_SDK_PATH=Join-Path $tools 'pico-sdk'
$env:PICO_TOOLCHAIN_PATH=Split-Path $compiler.DirectoryName
$env:PATH="$($compiler.DirectoryName);$env:PATH"
python (Join-Path $PSScriptRoot 'generate_wave.py')
if($LASTEXITCODE) {throw 'Wave generation failed'}
& $cmake -S $PSScriptRoot -B "$PSScriptRoot\build" -G Ninja "-DCMAKE_MAKE_PROGRAM=$ninja" '-DPICO_BOARD=vcc-gnd_yd-rp2040_8m' "-Dpioasm_DIR=$tools\pico-sdk-tools-2.3.1-x64-win\pioasm" "-Dpicotool_DIR=$tools\picotool-2.3.1-x64-win\picotool" '-DCMAKE_BUILD_TYPE=Release'
if($LASTEXITCODE) {throw 'CMake configuration failed'}
& $cmake --build "$PSScriptRoot\build" -j 8
if($LASTEXITCODE) {throw 'Pico build failed'}
Get-FileHash "$PSScriptRoot\build\pico_panel.uf2"
