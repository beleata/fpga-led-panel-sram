"""One-time migration of an existing placement; never regenerates the PCB."""
from pathlib import Path
import json
import subprocess
import sys
import pcbnew as p

root = Path(__file__).resolve().parents[1]
path = root / 'pico-panel.kicad_pcb'
board = p.LoadBoard(str(path))
removed = {f'R{i}' for i in range(20, 32)}
signals = ['R1', 'G1', 'B1', 'R2', 'G2', 'B2', 'A', 'B', 'C', 'SCLK', 'LAT', 'OE']
mapping = {'MCU_' + s: 'PANEL_' + s for s in signals}
footprints = {f.GetReference(): f for f in board.GetFootprints()}
assert removed <= footprints.keys(), 'Migration already applied or unexpected board'
assert not list(board.GetTracks()), 'Review routed copper before this migration'

def placement(fp):
    pos = fp.GetPosition()
    return (pos.x, pos.y, fp.GetOrientationDegrees(), int(fp.GetLayer()), fp.IsLocked())

before = {ref: placement(fp) for ref, fp in footprints.items() if ref not in removed}
for ref in removed:
    board.Remove(footprints[ref])
for fp in board.GetFootprints():
    for pad in fp.Pads():
        name = pad.GetNetname()
        if name in mapping:
            pad.SetNet(board.FindNet(mapping[name]))
# Rebuild only the schematic, then retain the actual, user-edited PCB coordinates.
subprocess.run([sys.executable, str(root / 'tools/build_design.py')], check=True)
parts = json.loads((root / 'parts.json').read_text())
assert len(parts) == len(before) == 103
for part in parts:
    fp = footprints[part['ref']]
    pos = fp.GetPosition()
    part.update(pcb=[pos.x / 1e6, pos.y / 1e6],
                rot=fp.GetOrientationDegrees(), side='B' if fp.GetLayer() == p.B_Cu else 'F')
    for pad in fp.Pads():
        if pad.GetNumber() in part['nets']:
            assert pad.GetNetname() == part['nets'][pad.GetNumber()]
(root / 'parts.json').write_text(json.dumps(parts, indent=2) + '\n')
staged = root / 'panel-series-migration.kicad_pcb'
p.SaveBoard(str(staged), board)
reloaded = p.LoadBoard(str(staged))
after = {fp.GetReference(): placement(fp) for fp in reloaded.GetFootprints()}
assert before == after, 'A retained footprint changed placement'
assert reloaded.GetCopperLayerCount() == 2
staged.replace(path)
report = {'removed': sorted(removed), 'components': len(after),
          'unchanged_placement': True, 'tracks': 0, 'layers': 2,
          'direct_signals': mapping}
(root / 'reports/remove-panel-series.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS: 12 series resistors removed; all 103 remaining placements and locks unchanged.')
