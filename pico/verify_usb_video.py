"""Opt-in hardware test: reject damaged packets, recover, then stream a GIF."""
import argparse
import json
import time
from usb_video import Display, packet, load_frames


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('image')
    ap.add_argument('--port')
    args = ap.parse_args()
    frames = load_frames(args.image, 90, 'exact')
    display = Display(args.port)
    try:
        before = display.exchange(2)
        bad = bytearray(packet(1, 200, frames[0][1]))
        bad[-1] ^= 1
        display.serial.write(bad)
        line = display.serial.readline()
        assert b'CRC_ERROR seq=200' in line, line
        assert display.exchange(2)['frames'] == before['frames']
        display.serial.write(packet(1, 201, frames[0][1])[:127])
        time.sleep(1.15)
        line = display.serial.readline()
        assert b'TIMEOUT seq=201' in line, line
        assert display.exchange(2)['frames'] == before['frames']
        started = time.monotonic()
        for _ in range(10):
            for _, payload, _ in frames:
                state = display.exchange(1, payload)
        elapsed = time.monotonic() - started
        assert state['frames'] == before['frames'] + 70
        display.close()
        time.sleep(1.1)
        display = Display(args.port)
        held = display.exchange(2)
        assert held['frames'] == state['frames']
        print(json.dumps(dict(result='PASS', crc_rejected=True, timeout_recovered=True,
                              usb_reopen_kept_frame=True, accepted=70,
                              seconds=round(elapsed, 3), fps=round(70/elapsed, 2),
                              final=held), indent=2))
    finally:
        display.close()


if __name__ == '__main__':
    main()
