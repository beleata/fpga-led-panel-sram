"""Back up affected 4 KiB sectors, program, read back, and check CDONE."""
import argparse
import hashlib
import time
from pathlib import Path

from iceprog import Prog, READ, READY, EXIT, addr3


def read_page(p, address):
    time.sleep(0.005)
    p.send(READ, addr3(address))
    reply = p.recv(4)
    tag = bytes((0, (address >> 8) & 255))
    if reply is None or reply[0] != READ or len(reply[1]) != 258 or reply[1][:2] != tag:
        raise RuntimeError(f'Invalid read response at {address:#x}: {reply and (reply[0], len(reply[1]))}')
    return reply[1][2:]


def read_range(p, size):
    return b''.join(read_page(p, off) for off in range(0, size, 256))


def write_verified_sectors(p, desired):
    for sector in range(0, len(desired), 4096):
        expected = desired[sector:sector + 4096]
        for attempt in range(3):
            p.sector_erase(sector)
            time.sleep(0.15)
            for offset in range(0, 4096, 256):
                page = expected[offset:offset + 256]
                if page != b'\xff' * 256:
                    p.write_page(sector + offset, page)
                    time.sleep(0.005)
            actual = b''.join(read_page(p, sector + offset) for offset in range(0, 4096, 256))
            if actual == expected:
                print(f'Sector {sector:#06x}: verified (attempt {attempt + 1})', flush=True)
                break
            print(f'Sector {sector:#06x}: mismatch, retrying', flush=True)
        else:
            raise RuntimeError(f'Sector {sector:#x} could not be verified')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file', type=Path)
    ap.add_argument('--port', default='COM18')
    ap.add_argument('--verify-only', action='store_true')
    args = ap.parse_args()
    blob = args.file.read_bytes()
    if not 0 < len(blob) <= 2 * 1024 * 1024:
        raise ValueError('Invalid bitstream size')
    size = (len(blob) + 4095) // 4096 * 4096
    p = Prog(args.port, 230400, timeout=0.5)
    try:
        p.enter()
        if p.read_id() != (0xEF, 0x40, 0x15):
            raise RuntimeError('Unexpected flash identity')
        if not args.verify_only:
            old = read_range(p, size)
            if old != read_range(p, size):
                raise RuntimeError('Two backup reads differ; refusing to erase')
            backups = Path(__file__).parent / 'backups'
            backups.mkdir(exist_ok=True)
            path = backups / (time.strftime('%Y%m%d-%H%M%S') + '-flash-prefix.bin')
            with path.open('xb') as f:
                f.write(old)
            print(f'Backup: {path} ({len(old)} bytes), SHA256 {hashlib.sha256(old).hexdigest()}', flush=True)
            # Preserve any data beyond the bitstream in the final erased sector.
            desired = blob + old[len(blob):]
            write_verified_sectors(p, desired)
        else:
            desired = blob
        actual = read_range(p, size)
        if actual[:len(desired)] != desired:
            first = next(i for i, (a, b) in enumerate(zip(actual, desired)) if a != b)
            raise RuntimeError(f'Flash mismatch at {first:#x}')
        print(f'VERIFIED: {len(desired)} bytes, bitstream SHA256 {hashlib.sha256(blob).hexdigest()}', flush=True)
    finally:
        try:
            p.send(EXIT)
            if p.expect(READY, timeout=3) is None:
                raise RuntimeError('No acknowledgement releasing FPGA reset')
        finally:
            p.close()
    time.sleep(0.5)
    p = Prog(args.port, 230400, timeout=0.5)
    try:
        p.send(0xF7)
        reply = p.recv(3)
        print(f'STATUS: {reply}', flush=True)
        if reply is None or reply[0] != 0xF7 or reply[1][:2] != b'\x01\x01':
            raise RuntimeError('FPGA did not assert CDONE with reset released')
    finally:
        p.close()


if __name__ == '__main__':
    main()
