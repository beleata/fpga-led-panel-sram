"""Measure error-checked UART round trips through the OLIMEXINO bridge."""
import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from iceprog import Prog


def set_baud(programmer, baud):
    programmer.send(0xE0, baud.to_bytes(4, 'big'))
    reply = programmer.recv(2)
    if reply is None or reply[0] != 0xE0 or len(reply[1]) != 3:
        raise RuntimeError(f'UART configuration failed: {reply}')
    hi, lo, fast = reply[1]
    divisor = (hi << 8) | lo
    return 16000000 / ((8 if fast else 16) * (divisor + 1))


def check_rate(programmer, baud, size, seed):
    actual = set_baud(programmer, baud)
    rng = random.Random(seed)
    payload = (bytes(range(256)) + bytes((0x55, 0xAA, 0, 0xFF)) * 64
               + rng.randbytes(max(0, size-512)))[:size]
    start = time.monotonic()
    received = bytearray()
    bad = missing = 0
    tested = 0
    for offset in range(0, size, 48):
        block = payload[offset:offset+48]
        programmer.send(0xE1, block)
        response = programmer.recv(2)
        if response is None or response[0] != 0xE1 or not response[1]:
            raise RuntimeError(f'Bad transfer response: {response}')
        count, echo = response[1][0], response[1][1:]
        if count != len(echo):
            raise RuntimeError('Malformed bridge length')
        expected = bytes(b ^ 0xA5 for b in block)
        bad += sum(a != b for a, b in zip(echo, expected))
        missing += abs(len(echo) - len(expected))
        received.extend(echo)
        tested += len(block)
        if bad or missing:
            break
    elapsed = time.monotonic() - start
    return dict(requested_baud=baud, actual_avr_baud=actual,
                bytes_tested=tested, bytes_received=len(received),
                wrong_bytes=bad, missing_bytes=missing, seconds=elapsed,
                payload_bytes_per_second=tested / elapsed,
                passed=(tested == size and bad == missing == 0), seed=seed,
                mode='48-byte full-duplex XOR-A5 round-trip bursts')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', default='COM18')
    ap.add_argument('--rates', type=int, nargs='+', default=[4800,9600,19200,38400,
                    57600,115200,230400,250000,460800,500000,921600,1000000,2000000])
    ap.add_argument('--bytes', type=int, default=4096)
    ap.add_argument('--seed', type=int, default=104729)
    ap.add_argument('--output', type=Path, default=Path('logs/uart-sweep.json'))
    args = ap.parse_args()
    results=[]
    programmer=Prog(args.port,230400,timeout=0.05)
    try:
        for baud in args.rates:
            result=check_rate(programmer,baud,args.bytes,args.seed)
            results.append(result)
            print(json.dumps(result),flush=True)
            args.output.write_text(json.dumps(results,indent=2),encoding='ascii')
    finally:
        programmer.close()


if __name__ == '__main__':
    main()
