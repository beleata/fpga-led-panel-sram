"""Stream RGB frames or a composited GIF into Pico RAM over USB CDC."""
import argparse
import binascii
import json
import math
import re
import sys
import time
from pathlib import Path

import serial
from serial.tools import list_ports
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel.make_pattern import coordinate


def pack_image(image):
    if image.size != (64, 32):
        raise ValueError('Expected 64x32 RGB image')
    image = image.convert('RGB')
    payload = bytearray(6144)
    for row in range(8):
        for channel in range(16):
            for chip in range(8):
                address = (row * 16 + channel) * 8 + chip
                for lane in range(2):
                    pixel = image.getpixel(coordinate(row, channel, chip, lane))
                    for color in range(3):
                        payload[(lane * 3 + color) * 1024 + address] = pixel[color]
    return bytes(payload)


def packet(command, sequence, payload=b''):
    if command not in (1, 2) or len(payload) != (6144 if command == 1 else 0):
        raise ValueError('Invalid command or payload length')
    body = bytes((command, sequence)) + payload
    return b'PV' + body + binascii.crc_hqx(body, 0xffff).to_bytes(2, 'big')


def prepare_image(image, rotate=0, fit='contain'):
    image = image.convert('RGBA')
    background = Image.new('RGBA', image.size, (0, 0, 0, 255))
    image = Image.alpha_composite(background, image).convert('RGB')
    rotations = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
                 270: Image.Transpose.ROTATE_90}
    if rotate:
        image = image.transpose(rotations[rotate])
    if image.size == (64, 32):
        return image
    if fit == 'exact':
        raise ValueError(f'After rotation image is {image.size}, not 64x32')
    if fit == 'stretch':
        return image.resize((64, 32), Image.Resampling.NEAREST)
    image = ImageOps.contain(image, (64, 32), Image.Resampling.NEAREST)
    canvas = Image.new('RGB', (64, 32))
    canvas.paste(image, ((64 - image.width) // 2, (32 - image.height) // 2))
    return canvas


def load_frames(path, rotate=0, fit='contain'):
    frames = []
    with Image.open(path) as source:
        for i in range(getattr(source, 'n_frames', 1)):
            # Pillow seek composites GIF offsets/disposal before conversion.
            source.seek(i)
            image = prepare_image(source.convert('RGBA'), rotate, fit)
            duration = max(0.01, source.info.get('duration', 100) / 1000)
            frames.append((image, pack_image(image), duration))
    return frames


def find_port():
    ports = [p.device for p in list_ports.comports() if (p.vid, p.pid) == (0x2e8a, 0x000a)]
    if len(ports) != 1:
        raise RuntimeError(f'Expected one Pico USB CDC device; found {ports}. Use --port.')
    return ports[0]


REPLY = re.compile(rb'PICO_VIDEO (\w+) seq=(\d+) crc=([0-9a-f]+) frames=(\d+) '
                   rb'txstall=(\d+) dma_error=([0-9a-f]+)')


class Display:
    def __init__(self, port=None):
        self.port = port or find_port()
        self.serial = serial.Serial(self.port, 115200, timeout=0.1, write_timeout=3)
        self.sequence = 0
        self.serial.reset_input_buffer()

    def close(self):
        self.serial.close()

    def exchange(self, command, payload=b'', timeout=4):
        self.sequence = (self.sequence + 1) & 255
        raw = packet(command, self.sequence, payload)
        self.serial.write(raw)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.serial.readline()
            match = REPLY.fullmatch(line.strip())
            if not match:
                continue
            status, sequence, crc, frames, stalls, errors = match.groups()
            if int(sequence) != self.sequence:
                continue
            state = dict(status=status.decode(), sequence=int(sequence), crc=int(crc, 16),
                         frames=int(frames), txstall=int(stalls), dma_error=int(errors, 16))
            if status != (b'ACK' if command == 1 else b'STATUS'):
                raise RuntimeError(f'Frame rejected: {state}')
            if state['crc'] != int.from_bytes(raw[-2:], 'big'):
                raise RuntimeError(f'Wrong acknowledgement CRC: {state}')
            if state['txstall'] or state['dma_error']:
                raise RuntimeError(f'Panel signal engine reports an error: {state}')
            return state
        raise TimeoutError('No Pico acknowledgement; check firmware/USB. No automatic resend.')


def play_playlist(display, clips, seconds=10, loops=0, stop_file=None,
                  clock=time.monotonic, sleep=time.sleep):
    """Switch on elapsed wall time, not GIF loop count; never interrupt a packet."""
    if not clips or any(not frames for _, frames in clips):
        raise ValueError('Playlist must contain nonempty clips')
    if not math.isfinite(seconds) or seconds <= 0 or loops < 0:
        raise ValueError('Invalid playlist duration or loop count')
    started = clock()
    due = started
    previous_slot = -1
    index = 0
    while True:
        if stop_file and stop_file.exists():
            return
        now = clock()
        slot = int((now - started) / seconds)
        if loops and slot >= loops * len(clips):
            return
        changed = slot != previous_slot
        if changed:
            previous_slot, index, due = slot, 0, now
        deadline = started + (slot + 1) * seconds
        if now < due:
            sleep(min(due - now, deadline - now, 0.1))
            continue
        path, frames = clips[slot % len(clips)]
        _, payload, duration = frames[index]
        state = display.exchange(1, payload)
        if changed:
            print(json.dumps(dict(event='clip', file=str(path), slot=slot,
                                  elapsed=round(clock() - started, 3), **state)), flush=True)
        index = (index + 1) % len(frames)
        due = max(due + duration, clock())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('image', type=Path, nargs='?')
    ap.add_argument('--playlist', type=Path, nargs='+', help='Alternate GIFs in supplied order')
    ap.add_argument('--seconds', type=float, default=10, help='Wall-clock seconds per playlist clip')
    ap.add_argument('--port')
    ap.add_argument('--rotate', type=int, choices=(0, 90, 180, 270), default=0,
                    help='Clockwise rotation before fitting')
    ap.add_argument('--fit', choices=('contain', 'exact', 'stretch'), default='contain')
    ap.add_argument('--loops', type=int, default=1, help='0 repeats until Ctrl+C or --stop-file')
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--preview', type=Path, help='Save transformed GIF without opening USB')
    ap.add_argument('--stop-file', type=Path)
    args = ap.parse_args()
    if args.loops < 0:
        ap.error('--loops must be nonnegative')
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        ap.error('--seconds must be finite and positive')
    if sum(bool(x) for x in (args.image, args.playlist, args.status)) != 1:
        ap.error('Choose exactly one image/GIF, --playlist, or --status')
    if args.playlist and args.preview:
        ap.error('--preview supports a single image only')
    frames = load_frames(args.image, args.rotate, args.fit) if args.image else []
    clips = [(p, load_frames(p, args.rotate, args.fit)) for p in (args.playlist or [])]
    if args.preview:
        if not frames:
            ap.error('--preview requires an image')
        images = [f[0] for f in frames]
        images[0].save(args.preview, save_all=True, append_images=images[1:], loop=0,
                       duration=[round(f[2] * 1000) for f in frames], disposal=2)
        print(f'Saved {len(frames)} frames at 64x32: {args.preview}')
        return
    display = Display(args.port)
    sent = 0
    started = time.monotonic()
    try:
        print(json.dumps(dict(port=display.port, **display.exchange(2))), flush=True)
        if args.status:
            return
        if clips:
            play_playlist(display, clips, args.seconds, args.loops, args.stop_file)
            return
        print(f'{len(frames)} source frames; duration={sum(f[2] for f in frames):.3f}s; '
              f'rotate={args.rotate} clockwise', flush=True)
        cycle = 0
        # Schedule presentation intervals, including transfer time, without dropping frames.
        due = time.monotonic()
        while args.loops == 0 or cycle < args.loops:
            for _, payload, duration in frames:
                if args.stop_file and args.stop_file.exists():
                    return
                time.sleep(max(0, due - time.monotonic()))
                state = display.exchange(1, payload)
                sent += 1
                due = max(due + duration, time.monotonic())
            cycle += 1
            if cycle == 1 or cycle % 10 == 0 or cycle == args.loops:
                print(json.dumps(dict(cycles=cycle, sent=sent,
                                      fps=round(sent / (time.monotonic() - started), 2), **state)), flush=True)
    except KeyboardInterrupt:
        print('Stopped; Pico keeps the last complete frame.', flush=True)
    finally:
        display.close()


if __name__ == '__main__':
    main()
