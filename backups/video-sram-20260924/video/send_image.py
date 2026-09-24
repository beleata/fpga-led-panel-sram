"""Send one 64x32 RGB image to SRAM through the existing OLIMEXINO bridge."""
import argparse
import binascii
import json
import sys
import time
from functools import reduce
from operator import xor
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from iceprog import Prog, READY
from panel.make_pattern import coordinate


def pack_image(image):
    if image.size != (64, 32):
        raise ValueError('Image must be exactly 64x32; use --resize explicitly')
    image = image.convert('RGB')
    planes = [bytearray(1024) for _ in range(6)]
    for row in range(8):
        for channel in range(16):
            for chip in range(8):
                address = (row * 16 + channel) * 8 + chip
                for lane in range(2):
                    rgb = image.getpixel(coordinate(row, channel, chip, lane))
                    for color in range(3):
                        planes[lane * 3 + color][address] = rgb[color]
    return b''.join(planes)


def packet(command, sequence, payload=b''):
    if command not in (1, 2) or len(payload) != (6144 if command == 1 else 0):
        raise ValueError('Invalid command or payload length')
    body = bytes((command, sequence)) + payload
    return b'VR' + body + binascii.crc_hqx(body, 0xffff).to_bytes(2, 'big')


def parse_reply(data):
    if len(data) != 9 or data[:2] != b'\xa5\x5a' or reduce(xor, data):
        raise ValueError('Invalid FPGA reply')
    flags = data[4]
    return dict(sequence=data[2], status=data[3], ready=bool(flags & 1),
                sram_initialized=bool(flags & 2), bank=(flags >> 2) & 1,
                sram_error=bool(flags & 8), last_sequence=data[5],
                last_crc=int.from_bytes(data[6:8], 'big'))


class Display:
    def __init__(self, port='COM18'):
        self.prog = Prog(port, 230400, timeout=0.05)
        self.pending = bytearray()
        try:
            answer = self.bridge(0xe0, (2000000).to_bytes(4, 'big'), 0xe0)
            if answer != b'\x00\x00\x01':
                raise RuntimeError(f'Unexpected 2 Mbaud UART configuration: {answer.hex()}')
            self.read_uart()
            self.pending.clear()
        except Exception:
            self.close()
            raise

    def close(self):
        self.prog.close()

    def bridge(self, command, payload=b'', expected=READY):
        self.prog.send(command, payload)
        reply = self.prog.recv(2)
        if reply is None or reply[0] != expected:
            raise RuntimeError(f'Bridge command {command:02x}: {reply}')
        return reply[1]

    def send_raw(self, data):
        for offset in range(0, len(data), 48):
            self.bridge(0xf9, data[offset:offset + 48])

    def read_uart(self):
        raw = self.bridge(0xf8, (10).to_bytes(2, 'big'), 0xf8)
        if not raw or raw[0] != len(raw) - 1:
            raise RuntimeError('Malformed UART bridge receive response')
        self.pending.extend(raw[1:])

    def receive(self, sequence, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.read_uart()
            while len(self.pending) >= 9:
                if self.pending[:2] != b'\xa5\x5a':
                    del self.pending[0]
                    continue
                raw = bytes(self.pending[:9])
                try:
                    reply = parse_reply(raw)
                except ValueError:
                    del self.pending[0]
                    continue
                del self.pending[:9]
                if reply['sequence'] == sequence:
                    return reply
        raise TimeoutError('No complete FPGA acknowledgement; previous image is not confirmed changed')

    def exchange(self, data):
        self.send_raw(data)
        return self.receive(data[3])

    def status(self):
        return self.exchange(packet(2, 0))

    def wait_ready(self, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.status()
            if state['sram_error'] or state['status']:
                raise RuntimeError(f'FPGA initialization failed: {state}')
            if state['ready'] and state['sram_initialized']:
                return state
            time.sleep(0.05)
        raise TimeoutError('Panel is not ready')

    def load(self, image):
        state = self.wait_ready()
        sequence = (state['last_sequence'] + 1) & 255
        data = packet(1, sequence, pack_image(image))
        started = time.monotonic()
        reply = self.exchange(data)
        if reply['status'] or not reply['ready'] or reply['last_crc'] != int.from_bytes(data[-2:], 'big'):
            raise RuntimeError(f'Frame was not committed: {reply}')
        reply['seconds'] = round(time.monotonic() - started, 3)
        return reply


def test_image():
    image = Image.new('RGB', (64, 32))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 63, 31), outline=(0, 255, 255))
    draw.text((5, 4), 'SRAM', fill=(255, 255, 255))
    for i, color in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0))):
        draw.rectangle((4 + i * 15, 19, 14 + i * 15, 27), fill=color)
    return image


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--image', type=Path)
    group.add_argument('--test-pattern', action='store_true')
    group.add_argument('--status', action='store_true')
    ap.add_argument('--port', default='COM18')
    ap.add_argument('--resize', action='store_true')
    ap.add_argument('--rotate', type=int, choices=(0, 180), default=0)
    ap.add_argument('--preview-only', action='store_true')
    args = ap.parse_args()
    image = None
    if not args.status:
        image = test_image() if args.test_pattern else Image.open(args.image).convert('RGB')
        if args.resize:
            image = image.resize((64, 32), Image.Resampling.LANCZOS)
        if args.rotate:
            image = image.rotate(180)
        pack_image(image)
        image.save(ROOT / 'last-sent.png')
        image.resize((768, 384), Image.Resampling.NEAREST).save(ROOT / 'last-sent-preview.png')
    if args.preview_only:
        return
    display = Display(args.port)
    try:
        print(json.dumps(display.status() if args.status else display.load(image), indent=2))
    finally:
        display.close()


if __name__ == '__main__':
    main()
