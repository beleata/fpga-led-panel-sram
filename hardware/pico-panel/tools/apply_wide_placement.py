"""Apply the approved larger outline and placement to the existing unrouted PCB."""
from pathlib import Path
import json
import pcbnew as p
from placement_wide import WIDTH, HEIGHT, OVERRIDES

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'pico-panel.kicad_pcb'
board = p.LoadBoard(str(path))
assert board.GetCopperLayerCount() == 2
assert not list(board.GetTracks()), 'Do not run after routing or manual placement review'
fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
assert set(fps) == set(OVERRIDES) | {'J1'}
assert len(fps) == 103
def vector(x,y):
    return p.VECTOR2I(p.FromMM(x),p.FromMM(y))

for ref, (x,y,angle) in OVERRIDES.items():
    fp = fps[ref]
    fp.SetOrientationDegrees(angle)
    fp.SetPosition(vector(x,y))

edges = [d for d in board.GetDrawings() if d.GetLayer() == p.Edge_Cuts]
assert len(edges) == 4
for edge in edges:
    for get, set_ in [(edge.GetStart, edge.SetStart), (edge.GetEnd, edge.SetEnd)]:
        point = get()
        assert round(point.x / 1e6,3) in (0,57.8,WIDTH)
        assert round(point.y / 1e6,3) in (0,HEIGHT)
        if point.x:
            point.x = p.FromMM(WIDTH)
        set_(point)
    edge.SetLocked(True)

# Keep only a few board-level labels; connector pin labels remain with each footprint.
labels = {'RP2040 PANEL / REV A':(65,4), 'DRAFT - NOT FOR FAB':(71,44),
          '+5V':(4,2.7), 'GND':(4,10), 'A':(1.5,36), 'B':(1.5,38.54),
          '1':(13.202,13.2), '16':(17.6,35.8)}
for text in board.GetDrawings():
    if isinstance(text,p.PCB_TEXT):
        if text.GetText() == 'GND' and text.GetPosition().y / 1e6 > 30:
            text.SetPosition(vector(4,44))
        elif text.GetText() in labels:
            text.SetPosition(vector(*labels[text.GetText()]))

for pad in fps['J1'].Pads():
    num = int(pad.GetNumber())
    expected = vector(13.202 + ((num-1)%2)*2.54,15.6 + ((num-1)//2)*2.54)
    pos = pad.GetPosition()
    assert abs(pos.x-expected.x) <= 2 and abs(pos.y-expected.y) <= 2
assert fps['J1'].GetLayer() == p.B_Cu
fps['J1'].SetLocked(True)

parts = json.loads((ROOT / 'parts.json').read_text())
for part in parts:
    fp = fps[part['ref']]
    pos = fp.GetPosition()
    part.update(pcb=[pos.x/1e6,pos.y/1e6],rot=fp.GetOrientationDegrees())
    for pad in fp.Pads():
        if pad.GetNumber() in part['nets']:
            assert pad.GetNetname() == part['nets'][pad.GetNumber()]

def courtyard(fp):
    items = [g.GetBoundingBox() for g in fp.GraphicalItems()
             if g.GetLayer() in (p.F_CrtYd,p.B_CrtYd)]
    if not items:
        return None
    return [min(b.GetLeft() for b in items)/1e6+.025,
            min(b.GetTop() for b in items)/1e6+.025,
            max(b.GetRight() for b in items)/1e6-.025,
            max(b.GetBottom() for b in items)/1e6-.025]
boxes = {ref:courtyard(fp) for ref,fp in fps.items()}
clashes = []
for i,(a,ba) in enumerate(boxes.items()):
    if not ba:
        continue
    for b,bb in list(boxes.items())[i+1:]:
        if bb and fps[a].GetLayer() == fps[b].GetLayer():
            if ba[0]<bb[2]-.001 and bb[0]<ba[2]-.001 and ba[1]<bb[3]-.001 and bb[1]<ba[3]-.001:
                clashes.append([a,b])
outside = [ref for ref,b in boxes.items() if b and
           (b[0]<0 or b[1]<0 or b[2]>WIDTH or b[3]>HEIGHT)]
p.SaveBoard(str(path),board)
(ROOT/'parts.json').write_text(json.dumps(parts,indent=2)+'\n')
report = {'components':len(parts),'layers':2,'board_mm':[WIDTH,HEIGHT],
          'courtyard_overlaps':clashes,'outside':outside,'boxes':boxes,'status':'UNROUTED DRAFT'}
(ROOT/'reports/placement.json').write_text(json.dumps(report,indent=2)+'\n')
print('Board:',WIDTH,HEIGHT,'Components:',len(parts),'J1: all 16 coordinates unchanged')
print('Courtyard overlaps:',clashes,'Outside:',outside)
