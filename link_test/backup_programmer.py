"""Read the ATmega32U4 flash twice through its existing Caterina bootloader."""
import hashlib
import subprocess
import time
from pathlib import Path

import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parents[1]
AVR = Path.home() / 'AppData/Local/Arduino15/packages/arduino/tools/avrdude/8.0.0-arduino1'


def boot_port(app_port):
    before = {p.device for p in list_ports.comports()}
    with serial.Serial(app_port, 1200) as connection:
        connection.dtr = False
    end = time.monotonic() + 10
    while time.monotonic() < end:
        for port in list_ports.comports():
            if port.device not in before and port.vid in (0x2341, 0x2A03):
                return port.device
        time.sleep(0.08)
    raise RuntimeError('Caterina bootloader port did not appear')


def wait_app():
    end = time.monotonic() + 15
    while time.monotonic() < end:
        for port in list_ports.comports():
            if port.vid in (0x2341, 0x2A03) and port.pid == 0x8036:
                time.sleep(0.5)
                return port.device
        time.sleep(0.1)
    raise RuntimeError('Leonardo application port did not return')


def main():
    folder = ROOT / 'backups' / ('programmer-' + time.strftime('%Y%m%d-%H%M%S'))
    folder.mkdir()
    for index in range(2):
        port = boot_port(wait_app())
        target = folder / f'flash-read-{index + 1}.bin'
        command = [str(AVR / 'bin/avrdude.exe'), '-C', str(AVR / 'etc/avrdude.conf'),
                   '-p', 'atmega32u4', '-c', 'avr109', '-P', port, '-b', '57600', '-A',
                   '-U', f'flash:r:{target}:r']
        result = subprocess.run(command, capture_output=True, text=True)
        (folder / f'read-{index + 1}.log').write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        print(f'Read {index + 1}: {target.stat().st_size} bytes', flush=True)
        wait_app()
    first = (folder / 'flash-read-1.bin').read_bytes()
    if first != (folder / 'flash-read-2.bin').read_bytes():
        raise RuntimeError('Programmer backup reads differ; DO NOT FLASH')
    if len(first) != 32768 or len(set(first[:28672])) < 32:
        raise RuntimeError('Backup appears incomplete or blank; DO NOT FLASH')
    print('MATCHING BACKUPS:', folder, hashlib.sha256(first).hexdigest(), flush=True)


if __name__ == '__main__':
    main()
