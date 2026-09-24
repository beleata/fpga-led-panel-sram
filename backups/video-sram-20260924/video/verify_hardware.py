"""Negative tests only: never commit a different image to the physical panel."""
import argparse
import json
import time
from PIL import Image
from send_image import Display, ROOT, pack_image, packet


def identity(state):
    return tuple(state[key] for key in ('bank', 'last_sequence', 'last_crc'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', default='COM18')
    args = ap.parse_args()
    display = Display(args.port)
    results = {}
    try:
        initial = display.wait_ready()
        results['before'] = initial
        original = packet(1, initial['last_sequence'], pack_image(Image.open(ROOT / 'last-sent.png')))
        if int.from_bytes(original[-2:], 'big') != initial['last_crc']:
            raise RuntimeError('Saved image does not match active frame; no test packets sent')
        altered = bytes(value ^ 255 for value in original[4:-2])
        sequence = (initial['last_sequence'] + 1) & 255
        bad = bytearray(packet(1, sequence, altered))
        bad[-1] ^= 1
        rejected = display.exchange(bad)
        assert rejected['status'] == 2 and identity(rejected) == identity(initial), rejected
        results['bad_crc_rejected'] = rejected
        display.send_raw(packet(1, sequence, altered)[:100])
        time.sleep(1.2)
        partial = display.status()
        assert partial['ready'] and identity(partial) == identity(initial), partial
        results['partial_timeout_retained'] = partial
        duplicate = display.exchange(original)
        assert duplicate['status'] == 0 and identity(duplicate) == identity(initial), duplicate
        results['duplicate_did_not_swap'] = duplicate
    finally:
        display.close()
    display = Display(args.port)
    try:
        retained = display.status()
        assert retained['ready'] and identity(retained) == identity(initial), retained
        results['retained_after_reconnect'] = retained
    finally:
        display.close()
    results['passed'] = True
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
