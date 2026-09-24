# Verification, 2026-09-24

## Confirmed Physical Result

FPGA was programmed once with this new image; the first serially loaded
frame contains the text SRAM, a cyan border and red/green/blue/yellow blocks.
The user answered yes when asked whether this exact picture is visible,
stable, and free of white dots/flicker. The panel is physically upside down.
The picture was initially left running. The user subsequently requested
a six-frame animation test; that separate test is recorded below.

Active bitstream: `video/video.bin`, 32220 bytes.
SHA256: `2c926b003a3d54a3c8ab7683ae0de9ba5894b31ca99ca25665a45670b34f23f1`.
Pre-program double-read backup: `backups/20260924-170608-flash-prefix.bin`.
Backup SHA256: `2036624bbd79b4127b4dc96e252a7b8ae74836d2639e874c99fbbe31fea5fcb9`.
Programming checked all 32768 affected bytes and CDONE/reset release.
See `logs/program-video.log`.

## Hardware Protocol Results

- Boot reported SRAM initialized, no SRAM error, bank 0, stable scanning.
- Frame 1: sequence 1, CRC 44409 (`AD79`), bank 1, status 0, ready true.
- Transfer plus display acknowledgement: 0.323 seconds for this one frame.
  This is a measured single transaction, not a sustained frame-rate benchmark.
- Deliberately inverted image with wrong CRC: rejected with status 2;
  active bank, sequence and CRC unchanged.
- Incomplete 100-byte packet followed by 1.2 seconds silence: abandoned;
  previous frame identity and ready state retained.
- Repeated original valid packet: successful ACK, no extra bank swap.
- Closing/reopening COM18 and retraining the bridge with BREAK did not reset
  the FPGA or lose its active frame.

Evidence: `logs/video-status-boot.json`, `logs/video-first-frame.json`,
`logs/video-hardware-verification.json`. `verify_hardware.py` reproduces the
negative tests, requiring `last-sent.png` to match the active frame CRC first.

The board-level SRAM proof is FPGA write/readback of all bytes, including
6144 initial pattern bytes and every received payload byte. There is no
host command for arbitrary SRAM dump, and no exhaustive whole-chip memory
or address-line diagnostic is claimed.

## Automated Tests

Three Python unit tests passed: all 6144 packed positions independently
checked, CRC standard vector and packet residue, ACK checksum handling.

The HDL integration simulation passed with an asynchronous 10 ns SRAM model
and exact 500 ns UART bits (2 Mbaud). It verifies:

- All 6144 initialized SRAM bytes and no read/write bus contention.
- UART receive and ACK transmit at real baud timing.
- Two distinct complete payloads, both SRAM bank directions.
- 98304 panel SCLK samples, all six RGB bits, including all 256 input levels.
- CRC error, duplicate frame, partial timeout, BREAK recovery.
- Injected SRAM readback failure rejected with status 3.

The simulation accelerates the panel clock divider and hold, and reduces
the packet timeout. It is not an electrical model of the LED driver ICs.
Evidence: `logs/test-video.log`.

## Build And Remaining Limits

1077/1280 logic cells (84%), 2/16 block RAMs, 46/72 IOs.
Post-route timing: 62.86 MHz for the 25 MHz logic clock;
655.31 MHz for the 100 MHz divider clock. Both pass.
Evidence: `video/synthesis.log`, `video/route.log`, `logs/build-video.log`.

The original stable panel and diagnostic bitstreams remain unchanged:

- Panel SHA256: `b78fb7d55cf977bcf4902dc009b04d8d9af7a3111f0af55a4674b78caf37d09f`.
- Link diagnostic SHA256: `e6e675a3e2145f5f83ecc53c2e2f99b437c255de51df6ad6ed5c9d60c57ab34f`.

Not yet verified: long-duration animation endurance, transition tearing under
repeated updates, calibrated grayscale/gamma, behavior across voltage/temperature
extremes. SRAM loses the user frame on power loss or FPGA reset; boot then
loads the original ROM geometry pattern. No flash persistence was added.

## Six-Frame Test Requested Afterwards

`python video/animate.py --cycles 3` sent six unique numbered frames three
times, with no deliberate hold between acknowledgements. All 18 packets
passed ACK status, ready state, sequence, CRC, and expected alternating-bank
checks. No FPGA reprogramming was required. The final frame is number 6.

- 18 frames in 5.6944623 seconds: **3.1609657 frames/second**.
- Mean USB-bridge sending time: 0.2576832 seconds/frame.
- Mean remaining wait for FPGA ACK: 0.0585700 seconds/frame.
- Individual transactions: 0.3088239..0.3302250 seconds.
- Four host-side tests now pass, including six distinct generated frames.
- Evidence: `logs/video-animation.json`, `logs/video-animation-run.log`.

This measures the current stop-and-wait bridge path using 48-byte chunks.
It is not the ultimate achievable speed of this hardware. The 2 Mbaud UART
alone carries 6150-byte 8N1 packets in 30.75 ms (32.52 packets/s), before any
USB overhead or panel refresh time. No claim of visually tear-free animation
is made from the acknowledgements alone. The user confirmed seeing all six
frames and requested continuous repetition. The loop is started separately
with `video/start_animation.ps1`; `video/stop_animation.ps1` requests a clean
stop after the current frame. While running, COM18 belongs to this process.

### Longer Run Observation

During the subsequent GitHub upload task, the first background loop stopped
after 1308 acknowledged frames with a host `TimeoutError` waiting for an ACK.
The error location was `display.receive(sequence)` in `animate.py`.
The cause has not been established; continuous long-duration reliability
must not be inferred from the earlier 18-frame test.

A fresh status request succeeded: ready=true, SRAM initialized=true,
SRAM error=false, bank=0, last_sequence=48, last_crc=54420. The loop was
restarted without FPGA reprogramming and again acknowledged frames at
approximately 3.16 fps. Automatic retry/recovery is not implemented in the
animation runner; it deliberately stops on an unconfirmed frame.
