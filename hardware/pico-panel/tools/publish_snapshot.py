"""Export a BOM and synchronize manifest coordinates from the saved manual PCB."""
from pathlib import Path
import csv
import hashlib
import json
import pcbnew as p

root = Path(__file__).resolve().parents[1]
board = p.LoadBoard(str(root/'pico-panel.kicad_pcb'))
fps = {f.GetReference():f for f in board.GetFootprints()}
parts = json.loads((root/'parts.json').read_text())
assert len(parts) == len(fps) == 103
for part in parts:
    fp = fps[part['ref']]
    pos = fp.GetPosition()
    part.update(pcb=[pos.x/1e6,pos.y/1e6],rot=fp.GetOrientationDegrees(),
                side='B' if fp.GetLayer()==p.B_Cu else 'F')
    for pad in fp.Pads():
        if pad.GetNumber() in part['nets']:
            assert pad.GetNetname() == part['nets'][pad.GetNumber()]
(root/'parts.json').write_text(json.dumps(parts,indent=2)+'\n')
with (root/'BOM.csv').open('w',newline='',encoding='utf-8') as stream:
    writer = csv.writer(stream)
    writer.writerow(['Reference','Value','Footprint','LCSC','Assembly','Side','X_mm','Y_mm','Rotation_deg'])
    for part in parts:
        writer.writerow([part['ref'],part['value'],part['footprint'],part['lcsc'],
                         part['assembly'],part['side'],*part['pcb'],part['rot']])

trial = p.LoadBoard(str(root/'routing-trial/pico-panel.kicad_pcb'))
assert len(list(trial.GetFootprints())) == 103
assert board.GetCopperLayerCount() == trial.GetCopperLayerCount() == 2
for fp in trial.GetFootprints():
    old = fps[fp.GetReference()]
    assert (fp.GetPosition().x,fp.GetPosition().y,fp.GetOrientationDegrees(),fp.GetLayer()) == (
        old.GetPosition().x,old.GetPosition().y,old.GetOrientationDegrees(),old.GetLayer())
files = ['pico-panel.kicad_sch','pico-panel.kicad_pcb','pico-panel.kicad_pro',
         'routing-trial/pico-panel.kicad_pcb','routing-trial/drc.json','parts.json','BOM.csv']
report = {'status':'DEVELOPMENT SNAPSHOT - NOT FOR MANUFACTURE','components':103,
          'layers':2,'manual_placement_preserved':True,
          'sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}}
(root/'reports/publication-snapshot.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: 103 BOM entries; saved user placement synchronized; trial positions identical; 2 layers.')
