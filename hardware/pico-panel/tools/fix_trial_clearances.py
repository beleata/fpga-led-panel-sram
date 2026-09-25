"""Move two fanout vias 0.02 mm away from reported tracks; fresh DRC is mandatory."""
from pathlib import Path
import json
import math
import pcbnew as p

root = Path(__file__).resolve().parents[1] / 'routing-trial'
path = root / 'pico-panel.kicad_pcb'
b = p.LoadBoard(str(path))
issues = json.loads((root/'drc.json').read_text())['violations']
assert len(issues) == 2 and all(v['type']=='clearance' for v in issues)
tracks = list(b.GetTracks())
lookup = {t.m_Uuid.AsString():t for t in tracks}
for issue in issues:
    pair = [lookup[i['uuid']] for i in issue['items']]
    via = next(t for t in pair if isinstance(t,p.PCB_VIA))
    trace = next(t for t in pair if not isinstance(t,p.PCB_VIA))
    assert via.GetNetname() in ('ETH_SCK','PANEL_G1')
    pos, a, c = via.GetPosition(), trace.GetStart(), trace.GetEnd()
    dx, dy = c.x-a.x, c.y-a.y
    u = max(0,min(1,((pos.x-a.x)*dx+(pos.y-a.y)*dy)/(dx*dx+dy*dy)))
    ex, ey = pos.x-(a.x+u*dx), pos.y-(a.y+u*dy)
    length = math.hypot(ex,ey)
    new = p.VECTOR2I(pos.x+round(ex/length*20000),pos.y+round(ey/length*20000))
    for t in tracks:
        if isinstance(t,p.PCB_VIA) or t.GetNetCode()!=via.GetNetCode():
            continue
        if t.GetStart().x==pos.x and t.GetStart().y==pos.y:
            t.SetStart(new)
        if t.GetEnd().x==pos.x and t.GetEnd().y==pos.y:
            t.SetEnd(new)
    via.SetPosition(new)
    print('Shifted via',via.GetNetname(),'by 0.020 mm; attached endpoints updated.')
p.SaveBoard(str(path),b)
