"""Generate one static 64x32 mapping target and its six-lane upload ROM.

User-confirmed mapping: each 32-column segment alternates lower/upper
eight-row strips, then advances to the right half. RGB2 is 16 rows below RGB1.
Geometry and colors were confirmed on the physical panel on 2026-09-24.
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 64, 32


def pixel(x, y):
    """Return RGB channel enables, red in bit zero."""
    if x in (0, 63) or y in (0, 31):
        return 7
    if 3 <= x <= 7 and 3 <= y <= 7:
        return 1
    if 56 <= x <= 60 and 3 <= y <= 7:
        return 2
    if 3 <= x <= 7 and 24 <= y <= 28:
        return 4
    if 56 <= x <= 60 and 24 <= y <= 28:
        return 5
    distance4 = (2 * x - 63) ** 2 + (2 * y - 31) ** 2
    if 18 ** 2 <= distance4 <= 21 ** 2:
        return 3
    # A right-facing arrow distinguishes mirrors and rotation of the circle.
    if (27 <= x <= 36 and y in (15, 16)) or (
        33 <= x <= 37 and abs(2 * y - 31) == 2 * (37 - x) + 1
    ):
        return 7
    return 0


def coordinate(scan_row, channel, chip, lane):
    serial_column = chip * 16 + channel
    x = (serial_column // 64) * 32 + serial_column % 32
    y = scan_row + (8 if (serial_column // 32) % 2 == 0 else 0) + 16 * lane
    return x, y


def main():
    values = []
    visited = set()
    for row in range(8):
        for channel in range(16):
            for chip in range(8):
                lanes = []
                for lane in range(2):
                    xy = coordinate(row, channel, chip, lane)
                    assert xy not in visited
                    visited.add(xy)
                    lanes.append(pixel(*xy))
                values.append(lanes[0] | (lanes[1] << 3))
    assert visited == {(x, y) for y in range(32) for x in range(64)}
    assert len(values) == 1024
    (ROOT / 'pattern.hex').write_text(''.join(f'{v:02x}\n' for v in values), encoding='ascii')
    image = Image.new('RGB', (WIDTH, HEIGHT))
    image.putdata([tuple(240 if pixel(x, y) & (1 << c) else 0 for c in range(3))
                   for y in range(HEIGHT) for x in range(WIDTH)])
    image.resize((768, 384), Image.Resampling.NEAREST).save(ROOT / 'pattern-expected.png')
    image.rotate(180).resize((768, 384), Image.Resampling.NEAREST).save(ROOT / 'pattern-upside-down.png')
    print('Generated: 1024 six-lane words; each of 2048 physical pixels addressed once')


if __name__ == '__main__':
    main()
