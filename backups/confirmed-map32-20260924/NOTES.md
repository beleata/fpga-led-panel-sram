# ICND1065L bring-up, 2026-09-24

## Confirmed baseline: 32-column mapping

On 2026-09-24 the user confirmed the physical panel exactly matches
`pattern-upside-down.png`: arrow, circle, all four colored corner markers,
and the entire white border are correctly positioned. The panel is physically
upside down. This visually confirms the candidate mapping and RGB ordering
for the static target. The previously reported slight flicker was not assessed
in this confirmation; do not claim it has been eliminated or that all grayscale
levels have been tested. Leave this known-good static test running.

Confirmed source, ROM, bitstream, constraints and build helpers are archived in
`backups/confirmed-map32-20260924/` with the successful programming log.

The user's photograph of the first static target showed intact colored markers
but a fragmented perimeter and circle. Accounting for the panel's 180-degree
orientation, the best 32x8 tile permutation (observed to original, row-major)
was [3, 1, 2, 0, 7, 5, 6, 4]. `analyze_photo.py` saved the approximate fit in
`photo-analysis.json`; 103/2048 classified pixels differ, so this is evidence
for a candidate mapping, not pixel-perfect physical validation.

Each RGB lane now maps serial columns 0..31 to x=0..31/y=8..15,
32..63 to x=0..31/y=0..7, 64..95 to x=32..63/y=8..15, and
96..127 to x=32..63/y=0..7. Lane 2 adds 16 to y.
Only `make_pattern.py` and its generated ROM changed the hardware behavior;
`panel.v`, timing, registers and brightness are unchanged.

One corrected static image was programmed and all 32768 affected bytes read
back correctly; CDONE=1. Bitstream SHA256:
`67585d59fa611daf4f84dd8c150be4e4850993ebe156254a5ed402678dc9f708`.
Log: `logs/program-static-map32.log`. Regression tests in `test_mapping.py`
passed; HDL simulation checked all 6144 channel words. Route timing passed
50.34 MHz against 25 MHz, with 441 logic cells and 2 RAM blocks.

The previous static source/ROM/binary is preserved in
`backups/static-map64-20260924-133633/`; its flash prefix was saved at
`backups/20260924-133724-flash-prefix.bin` before programming.
The intended image is unchanged. At the user's upside-down orientation it
must match `pattern-upside-down.png`: magenta/blue upper corners, green/red
lower corners, intact border and yellow circle, white arrow pointing left.
The user has now confirmed this exact result, as recorded above.
Do not flash another experiment without coordinating the next test.

## Previous test: first static mapping target

The user confirmed stable solid fields with no persistent white points, but
some individual-pixel flicker, then requested a recognizable figure. The active
test was ONE fixed image: white perimeter, yellow circle, white right arrow,
and red/green/blue/magenta corner markers. No alternating test modes.
WAIT FOR THE USER'S OBSERVATION before changing or flashing another image.

The clock, brightness, scan timing and driver register values remain those of
the stable solid test. `make_pattern.py` generates `pattern.hex` and the two
reference PNGs. The previous candidate followed DMD pattern 3 for GKGD P5 1/8:
the first 64 serial columns in each lane address its lower eight-row strip.
This physical mapping is a HYPOTHESIS until the photographed figure agrees.

Validation: a bijection covers all 2048 assumed physical coordinates; simulation
checks all 6144 grayscale channel words in the visible frame, plus register
broadcast, latch counts and all eight binary row addresses. Place-and-route uses
441/1280 logic cells and 2/16 RAM blocks; timing passes 25/100 MHz constraints.
The bitstream SHA256 is
`cc71529da34e16644321758634a731ea837f476fc5114a47131fedd259e3fb78`.
Flash readback verified all 32768 affected bytes and CDONE=1.
See `logs/program-static-pattern.log`.

Solid-test source and binary are preserved in
`backups/stable-solid-scan8-20260924-132852/`. The pre-figure flash backup is
`backups/20260924-132933-flash-prefix.bin`, identical to the stable scan-8
backup below. Rebuild ROM after any image edits with `python panel/make_pattern.py`.

## Recovery baseline: binary scan-8 solid test

The solid-field source uses SCAN=8, CHIPS=8, ROW_MODE=0. Its 32220-byte image
SHA256 is `0cefa7ab07cdbb255227598f1af3f0cb1f283cb6eb12e4d6d993c8c69d30c0a3`.
The first-light scan-16 image below is HISTORICAL and has persistent white
points and only four illuminated rows in the user's photographs.

After the user corrected a physical connection, three complete reads were
identical, CDONE=1, and the panel briefly displayed the scan-8 test without
the white points (user report). I then restored the first-light image as a
recovery step, which the user reported brought the defects back. Comparing
the preserved prefix proved that the better intermediate image was exactly
the scan-8 build, despite the earlier unreliable readback over the bad link.

The better image has now been restored from
`backups/20260924-132102-flash-prefix.bin`. All 32768 bytes were verified and
CDONE=1. See `logs/restore-improved-scan8.log`. Do not revert to scan-16 as
the default recovery image. Full physical geometry is still unconfirmed:
the user's approximate count of 24 driver ICs conflicts with the assumed
eight-chip chains. Visual improvements do not resolve that uncertainty.

Recovery for the CURRENT baseline:

```powershell
python program_panel.py backups/20260924-132102-flash-prefix.bin
```

The sections below describe the original experiment, not the current defaults.

## Observed on this machine

- Original project found at `C:\Users\user\Documents\New folder (3)\fpga`.
- Tools found at `C:\oss-cad-suite`.
- Programmer COM18 responds with JEDEC `EF 40 15`.
- First new bitstream written with `python program_panel.py panel/panel.bin`.
- All 32768 affected bytes read back correctly; CDONE=1, CRESET=1.
- UART on FPGA pin 7 returned repeated `U` at 4800 baud. Thus the new design
  is actually running, independently of the flash readback result.
- Visible panel output still requires the operator's observation.
- First backup: `backups/20260924-130648-flash-prefix.bin` (32768 bytes).
  Only those eight 4-KiB sectors were erased; the rest of flash was untouched.
  SHA256: `a0e989f3c27b0b00d7529ce7302dc18e03625cf16af6ce73d31789934944ed76`.
- Initial test image SHA256:
  `5a7233112e1aa24e5ceb7df4c31320ab26ab8ffeb151e88ea7a6c429205c7bd7`.

## Source evidence

Upstream snapshots were cloned under `reference/` and are unmodified.

- [Olimex GPIO mapping](https://github.com/OLIMEX/iCE40HX1K-EVB/blob/master/gpio1-pcf/GPIO1-VQ100.txt):
  GPIO1 pin 34 is FPGA pin 24, NOT ground. Ground is GPIO1 2, 4, or 8.
- [SPWM implementation](https://github.com/kingdo9/rpi-rgb-led-matrix_pwm_experiment/tree/5da13cb3b0d38d66bb5201f03704b5bef9e4446b/lib/spwm):
  `spwm_send_rgb_register()` repeats ONE word to every chip in a frame and
  advances to the next word in the next frame. It does not truncate the
  configuration sequence to the number of chips. Data upload is 16 bits per
  channel, latching after the final chip, for all 16 channels and every scan row.
- [DMD_STM32 driver](https://github.com/board707/DMD_STM32/blob/398ec1d8636bce866709fbe9c3f0035c90645e7a/DMD_SPWM_Driver_RP.h):
  ICN1065 defaults and `0x200 | (nRows - 1)` scan field; grayscale uses 12 bits
  in a 16-bit word, with the upper four bits zero.
- [DMD_STM32 row selection](https://github.com/board707/DMD_STM32/blob/398ec1d8636bce866709fbe9c3f0035c90645e7a/DMD_Multiplexer.cpp):
  595 transport uses A=clock, B=latch, C=serial data (one on wrap to row zero).

## First test assumptions

This is a bring-up test, not a claim of panel support. Row-driver identity,
actual scan ratio, shift-chain length, and signal integrity are not established.
The user confirmed the separate 5-V supply, signal wiring, and common ground.

- First geometry: 16 scan rows, 4 driver chips per RGB lane, 64 serial pixels.
- Row transport: A/B/C shift-register (parameter `ROW_MODE=2`).
- 25-MHz internal clock, 1.5625-MHz panel clock.
- 128-clock scan period, four-clock OE pulse at phase 100, row latch at 112,
  row clock at 114. This timing is an explicit test assumption inspired by
  the DMD separated row/PWM transport, not a captured waveform of this panel.
- The 22-word addressed sequence uses the SPWM sequence's addresses with DMD
  defaults. Registers omitted from that sequence retain their existing values.
  Compatibility of those values with this exact panel is unverified.
- Each frame sends the LAT 3/11/14 commands and AA/config/55 register blocks;
  a different addressed configuration word is broadcast on each frame.
- Pixels stay zero until all 22 words have been transmitted. Then low-level
  red/green/blue/black fields cycle, with grayscale `0x0100`.
- LED1 indicates full register traversal; LED2 is a heartbeat.
- TX emits `U` at 4800 baud through FPGA pin 7, GPIO1 pin 13.

## Verification and reproduction

From the workspace root:

```powershell
.\build.ps1
python program_panel.py panel/panel.bin
python program_panel.py panel/panel.bin --verify-only
```

Simulation (from `panel`, with OSS CAD bin/lib on PATH):

```powershell
iverilog -g2012 -DSIMULATION -s tb_panel -o tb_panel.vvp panel.v tb_panel.v
vvp tb_panel.vvp
```

Simulation passed: all 22 configuration words broadcast identically to four
chips, 16384 data clocks and 256 channel latches per frame, blanking until
configuration completes, and the `0x0100` pixel word. The test accelerates
the clock divider and hold interval, leaving protocol counts unchanged.
Initial route: 477/1280 logic cells, internal timing 47.59 MHz against 25 MHz;
input divider timing 626.57 MHz against 100 MHz. No timing exceptions used.

To restore the saved prefix using the same verified programming procedure:

```powershell
python program_panel.py backups/20260924-130648-flash-prefix.bin
```

The original HARDWARE.md is historical context. In particular, absence of D
does not establish scan ratio: an 8-scan panel can use a binary A/B/C address.
Also, 3.3-V compatibility is not established merely by other users driving
different panels from a Raspberry Pi.
