"""Two-layer autorouter trial on a copy of the user's placement, not a release."""
from pathlib import Path
import json
import shutil
import sys
import pcbnew as p
from kitools import _find_block

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'routing-trial'
OUT.mkdir(exist_ok=True)
SOURCE = ROOT / 'pico-panel.kicad_pcb'
PCB = OUT / 'pico-panel.kicad_pcb'

def placements(board):
    return {fp.GetReference(): [fp.GetPosition().x,fp.GetPosition().y,
            fp.GetOrientationDegrees(),int(fp.GetLayer())] for fp in board.GetFootprints()}

mode = sys.argv[1]
if mode == 'export':
    assert not (OUT/'panel.ses').exists(), 'Archive previous trial before exporting again'
    b = p.LoadBoard(str(SOURCE))
    assert b.GetCopperLayerCount() == 2
    assert len(list(b.GetFootprints())) == 103
    assert not list(b.GetTracks()), 'This trial expects placement only'
    shutil.copy2(SOURCE,PCB)
    shutil.copy2(ROOT/'pico-panel.kicad_pro',OUT/'pico-panel.kicad_pro')
    (OUT/'placements-before.json').write_text(json.dumps(placements(b),indent=2)+'\n')
    dest = OUT/'panel.dsn'
    assert p.ExportSpecctraDSN(b,str(dest))
    text = dest.read_text()
    start = text.index('(class kicad_default')
    block = _find_block(text,start)
    names = block[:block.index('(circuit')].split()[2:]
    power = {'3V3','SYS_5V','PANEL_5V','PANEL_5V_IN','USB_5V','1V1','GND','ETH_AVDD','ETH_CT'}
    switch = {'BUCK_SW'}
    def group(name,nets,width):
        assert nets
        return ('(class '+name+' '+' '.join(nets)+'\n'
                ' (circuit (use_via "Via[0-1]_600:300_um"))\n'
                f' (rule (width {width}) (clearance 127)))')
    replacement = '\n'.join([
        group('kicad_default',[n for n in names if n not in power|switch],127),
        group('power',[n for n in names if n in power],250),
        group('switch_power',[n for n in names if n in switch],500)])
    text = text[:start]+replacement+text[start+len(block):]
    dest.write_text(text)
    print('Exported user placement: 103 components, 2 layers; signal 0.127 mm, power 0.25 mm, SW 0.5 mm.')
    print('Trial only: differential impedance, return paths and switcher loops require manual review.')
elif mode == 'import':
    b = p.LoadBoard(str(SOURCE))
    before = json.loads((OUT/'placements-before.json').read_text())
    assert placements(b) == before
    session = sys.argv[2] if len(sys.argv) > 2 else 'panel.ses'
    assert p.ImportSpecctraSES(b,str(OUT/session))
    # DSN uses micrometres; restore sub-micrometre position rounding on import.
    for fp in b.GetFootprints():
        x,y,angle,layer = before[fp.GetReference()]
        pos = fp.GetPosition()
        assert abs(pos.x-x) <= 1000 and abs(pos.y-y) <= 1000
        assert fp.GetOrientationDegrees() == angle and int(fp.GetLayer()) == layer
        fp.SetPosition(p.VECTOR2I(x,y))
    assert placements(b) == before, 'Autorouter changed a footprint'
    assert b.GetCopperLayerCount() == 2
    assert placements(p.LoadBoard(str(SOURCE))) == before, 'Source placement changed during trial'
    p.SaveBoard(str(PCB),b)
    tracks = list(b.GetTracks())
    report = {'components':len(before),'layers':2,'placement_unchanged':True,
              'tracks_and_vias':len(tracks),'vias':sum(isinstance(t,p.PCB_VIA) for t in tracks),
              'status':'AUTOROUTER TRIAL - NOT FOR MANUFACTURE'}
    (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
else:
    raise SystemExit('Expected export or import')
