#!/usr/bin/env python3
"""Program an iCE40HX1K-EVB through an OLIMEXINO-32U4 running the iceprog2 sketch.

Why this exists instead of Olimex's winiceprogduino.exe:
  * that binary hardcodes CBR_57600, and
  * it passes "COM16" straight to CreateFile(), which Windows only accepts for
    COM1..COM9 - so the Arduino's port cannot be opened at all.

Why iceprog2.ino instead of the stock iceprog.ino:
  * the stock parser is off by one, so a minimal <CMD><FCS>FEND frame can never
    pass its checksum and the board answers nothing.

Wire format, both directions (implemented in ../programmer-fw/iceprog2):
  FEND CMD <escaped data...> FCS FEND
  FCS chosen so (CMD + data + FCS) & 0xFF == 0xFF
  FEND/FESC inside data escaped as FESC TFEND / FESC TFESC
  Addresses are three bytes: high, mid, low.

Usage:
  python iceprog.py -p COM16 id
  python iceprog.py -p COM16 write ..\\blink\\example.bin
  python iceprog.py -p COM16 read dump.bin
  python iceprog.py -p COM16 erase
"""

import argparse
import sys
import time

import serial

FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD

READ_ID = 0x9F
BULK_ERASE = 0xC7
SEC_ERASE = 0xD8
PROG = 0x02
READ = 0x03
ENTER = 0xEE
EXIT = 0xEF

READY = 0x44
ERROR = 0x45

PAGE = 256
FLASH_SIZE = 2 * 1024 * 1024


def esc(data):
    out = bytearray()
    for b in data:
        if b == FEND:
            out += bytes((FESC, TFEND))
        elif b == FESC:
            out += bytes((FESC, TFESC))
        else:
            out.append(b)
    return bytes(out)


def frame(cmd, payload=b""):
    body = bytes((cmd,)) + bytes(payload)
    fcs = 0xFF - (sum(body) & 0xFF)
    return bytes((FEND,)) + esc(body + bytes((fcs,))) + bytes((FEND,))


def unesc(data):
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == FESC and i + 1 < len(data):
            nxt = data[i + 1]
            out.append(FEND if nxt == TFEND else FESC if nxt == TFESC else nxt)
            i += 2
        else:
            out.append(b)
            i += 1
    return bytes(out)


def parse_frame(raw):
    """raw: bytes between two FEND delimiters. Returns (cmd, payload) or None."""
    if not raw:
        return None
    body = unesc(raw)
    if len(body) < 2 or (sum(body) & 0xFF) != 0xFF:
        return None
    return body[0], body[1:-1]


def addr3(addr):
    return bytes(((addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF))


class Prog:
    def __init__(self, port, baud, timeout=10.0):
        self.ser = serial.Serial(port, baud, timeout=timeout, write_timeout=timeout)
        time.sleep(0.3)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def close(self):
        self.ser.close()

    def send(self, cmd, payload=b""):
        self.ser.write(frame(cmd, payload))
        self.ser.flush()

    def recv(self, timeout=None):
        """Read one well-formed frame. Returns (cmd, payload) or None on timeout.

        Deliberately byte-at-a-time: read_until(FEND) returns immediately with an
        empty buffer when the frame is already queued, which silently eats the
        leading FEND and makes the next read start mid-frame.
        """
        budget = self.ser.timeout if timeout is None else timeout
        deadline = time.time() + budget
        buf = bytearray()
        in_frame = False
        while time.time() < deadline:
            chunk = self.ser.read(1)
            if not chunk:
                continue
            b = chunk[0]
            if not in_frame:
                if b == FEND:
                    in_frame = True
                    buf = bytearray()
                continue
            if b == FEND:
                if not buf:
                    continue                      # back-to-back delimiters
                parsed = parse_frame(bytes(buf))
                if parsed is not None:
                    return parsed
                in_frame = False                  # bad checksum, resync
                buf = bytearray()
                continue
            buf.append(b)
        return None

    def expect(self, want, timeout=None, tries=1):
        for _ in range(tries):
            got = self.recv(timeout)
            if got and got[0] == want:
                return got[1]
        return None

    # --- operations -------------------------------------------------------

    def enter(self):
        """Hold CRESET low so the FPGA forwards SPI to the flash. Required before
        any flash command; without it every read returns FF FF FF."""
        self.send(ENTER)
        got = self.recv(timeout=5.0)
        if got is None:
            raise RuntimeError("no answer to ENTER")
        if got[0] == ERROR:
            raise RuntimeError(
                "ENTER refused: CDONE is still high, the FPGA is running and the "
                "SPI pass-through is closed (is PGM1 pin 6 wired to D2?)")
        if got[0] != READY:
            raise RuntimeError("unexpected answer to ENTER: 0x%02X" % got[0])

    def exit(self):
        self.send(EXIT)
        self.expect(READY, timeout=5.0)

    def read_id(self):
        self.send(READ_ID)
        payload = self.expect(READ_ID, timeout=4.0, tries=2)
        if payload is None or len(payload) < 3:
            return None
        return payload[0], payload[1], payload[2]

    def bulk_erase(self):
        self.send(BULK_ERASE)
        if self.expect(READY, timeout=25.0, tries=2) is None:
            raise RuntimeError("no READY after bulk erase")

    def sector_erase(self, addr):
        self.send(SEC_ERASE, addr3(addr))
        if self.expect(READY, timeout=10.0, tries=2) is None:
            raise RuntimeError("no READY after sector erase 0x%06X" % addr)

    def write_page(self, addr, data):
        assert len(data) <= PAGE
        for attempt in range(6):
            self.send(PROG, addr3(addr) + bytes(data))
            if self.expect(READY, timeout=6.0) is not None:
                return
        raise RuntimeError("page 0x%06X never acknowledged" % addr)

    def write(self, blob, verbose=True, skip_ff=True):
        total = len(blob)
        for off in range(0, total, PAGE):
            chunk = blob[off:off + PAGE]
            if skip_ff and all(b == 0xFF for b in chunk):
                continue
            self.write_page(off, chunk)
            if verbose:
                done = min(off + PAGE, total)
                sys.stderr.write("\r  %d/%d bytes (%d%%)" % (done, total, done * 100 // total))
                sys.stderr.flush()
        if verbose:
            sys.stderr.write("\n")

    def read_page(self, addr):
        self.send(READ, addr3(addr))
        got = self.expect(READ, timeout=4.0, tries=2)
        if got is None or len(got) < 2:
            return None
        return got[2:]


def jedec_note(mfr, mem, cap):
    known = {(0xEF, 0x40, 0x15): "Winbond W25Q16BV (2 MB)"}
    return known.get((mfr, mem, cap), "unknown flash")


def main():
    ap = argparse.ArgumentParser(description="iceprog2 client for OLIMEXINO-32U4")
    ap.add_argument("-p", "--port", required=True, help="e.g. COM16")
    ap.add_argument("-b", "--baud", type=int, default=230400)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("id", help="read the flash JEDEC ID")
    sub.add_parser("erase", help="bulk erase the whole flash")
    w = sub.add_parser("write", help="write a bitstream")
    w.add_argument("file")
    w.add_argument("--all-pages", action="store_true", help="write 0xFF pages too")
    r = sub.add_parser("read", help="dump the whole flash to a file")
    r.add_argument("file")

    args = ap.parse_args()

    prog = Prog(args.port, args.baud)
    try:
        prog.enter()
        jid = prog.read_id()
        if jid is None:
            print("no answer to READ_ID - check the PGM1 cable and that the "
                  "OLIMEXINO's switch is on 3.3V", file=sys.stderr)
            return 2
        print("JEDEC ID: %02X %02X %02X - %s" % (jid[0], jid[1], jid[2], jedec_note(*jid)))

        if args.cmd == "id":
            return 0

        if args.cmd == "erase":
            print("bulk erase..")
            prog.bulk_erase()
            print("done")
            return 0

        if args.cmd == "write":
            with open(args.file, "rb") as fh:
                blob = fh.read()
            print("writing %s (%d bytes).." % (args.file, len(blob)))
            prog.bulk_erase()
            prog.write(blob, skip_ff=not args.all_pages)
            print("done")
            return 0

        if args.cmd == "read":
            print("reading %d bytes (this takes a while).." % FLASH_SIZE)
            buf = bytearray(b"\xFF" * FLASH_SIZE)
            for page in range(FLASH_SIZE // PAGE):
                data = prog.read_page(page * PAGE)
                if data:
                    buf[page * PAGE:page * PAGE + len(data)] = data
                if page % 512 == 0:
                    sys.stderr.write("\r  page %d/%d" % (page, FLASH_SIZE // PAGE))
                    sys.stderr.flush()
            sys.stderr.write("\n")
            with open(args.file, "wb") as fh:
                fh.write(buf)
            print("wrote %s" % args.file)
            return 0
    finally:
        # always hand the FPGA back to the flash, even after a failure
        try:
            prog.exit()
        except Exception:
            pass
        prog.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
