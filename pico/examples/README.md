# GIF playback examples

These three user-supplied GIFs are the inputs used for the physical panel tests.
Original authors and redistribution licenses have not been established here;
including them does not grant ownership or a new license to the artwork.

Run from the repository root after installing `requirements.txt` and flashing
`pico/pico_panel_usb.uf2` to the connected YD-RP2040:

```powershell
# Sonic: 32x64 -> 64x32, clockwise rotation, repeat until Ctrl+C
python pico/usb_video.py pico/examples/sonic-finger-ezgif.com-resize.gif --rotate 90 --fit exact --loops 0

# Stop the previous command before starting this playlist.
# Native 64x32 GIFs, alternating every 10 seconds, repeat until Ctrl+C
python pico/usb_video.py --playlist pico/examples/led_matrices_sine_tube.gif pico/examples/led_matrices_ruby_walk.gif --seconds 10 --fit exact --loops 0

# Equivalent hidden background playback on Windows
./pico/start_video.ps1 -Image pico/examples/led_matrices_sine_tube.gif,pico/examples/led_matrices_ruby_walk.gif -Rotate 0 -Seconds 10
./pico/stop_video.ps1
```

Only one sender may hold the Pico COM port at a time. Closing the sender leaves
the last frame displayed while both Pico and the panel remain powered.
