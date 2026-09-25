"""Check direct-panel wiring and power isolation against the generated netlist."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
parts = {p['ref']: p for p in json.loads((root / 'parts.json').read_text())}
removed = {'U5', 'U6', 'Q1', 'Q2', 'R14', 'R15', 'R16', 'R17', 'C20', 'C21', 'D3'}
assert not removed.intersection(parts)
assert '17' not in parts['U1']['nets'], 'GP14 must be unused'
actual = {}
for net in ET.parse(root / 'reports/netlist.xml').findall('.//nets/net'):
    for node in net.findall('node'):
        actual[node.attrib['ref'], node.attrib['pin']] = net.attrib['name'].lstrip('/')

signals = ['R1', 'G1', 'B1', 'R2', 'G2', 'B2', 'A', 'B', 'C', 'SCLK', 'LAT', 'OE']
for i, (signal, mcu_pin, panel_pin) in enumerate(zip(
        signals, [4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16],
        [1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15])):
    resistor = f'R{20+i}'
    assert resistor not in parts
    assert actual['U1', str(mcu_pin)] == actual['J1', str(panel_pin)] == 'PANEL_' + signal

assert all(not n.startswith('BUF_') for p in parts.values() for n in p['nets'].values())
assert {ref for ref, p in parts.items() if 'SYS_5V' in p['nets'].values()} == {'D2', 'U4', 'C18', 'C25'}
assert parts['D2']['nets'] == {'1': 'SYS_5V', '2': 'PANEL_5V'}
assert {ref for ref, p in parts.items() if 'USB_5V' in p['nets'].values()} == {'J2', 'U3', 'C17', 'R10'}
print('PASS: 12 direct 3.3 V channels without series resistors; GP14 unused; buffer circuit absent.')
print('PASS: USB VBUS does not feed SYS_5V; controller requires panel power.')
