"""Place a TWO-layer prototype board. Never exports fabrication files."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET
import pcbnew as p

ROOT=Path(__file__).resolve().parents[1]
FP_ROOT=Path(r'C:/Users/user/Tools/KiCad/share/kicad/footprints')
from placement import WIDTH as W, HEIGHT as H
parts=json.loads((ROOT/'parts.json').read_text())
board=p.BOARD()
board.SetCopperLayerCount(2)
board.GetDesignSettings().SetBoardThickness(p.FromMM(0.8))
def v(x,y): return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
def box(fp):
    shapes=[g for g in fp.GraphicalItems() if g.GetLayer() in (p.F_CrtYd,p.B_CrtYd)]
    if not shapes: return None
    bounds=[g.GetBoundingBox() for g in shapes]
    return (min(b.GetLeft() for b in bounds)/1e6+.025,min(b.GetTop() for b in bounds)/1e6+.025,
            max(b.GetRight() for b in bounds)/1e6-.025,max(b.GetBottom() for b in bounds)/1e6-.025)
def overlap(a,b): return a[0]<b[2]-.001 and b[0]<a[2]-.001 and a[1]<b[3]-.001 and b[1]<a[3]-.001

tree=ET.parse(ROOT/'reports/netlist.xml')
actual={}
for net in tree.findall('.//nets/net'):
    name=net.attrib['name'].lstrip('/')
    for node in net.findall('node'):
        actual[(node.attrib['ref'],node.attrib['pin'])]=name
for part in parts:
    for pin,net in part['nets'].items():
        assert actual.get((part['ref'],pin))==net,(part['ref'],pin,net,actual.get((part['ref'],pin)))

nets={}
for name in sorted({n for part in parts for n in part['nets'].values()}):
    nets[name]=p.NETINFO_ITEM(board,name)
    board.Add(nets[name])
fps={}
for part in parts:
    lib,name=part['footprint'].split(':')
    fp=p.FootprintLoad(str((ROOT if lib=='Panel' else FP_ROOT)/(lib+'.pretty')),name)
    assert fp, part['footprint']
    board.Add(fp)
    fp.SetReference(part['ref'])
    fp.SetValue(part['value'])
    fp.SetField('LCSC',part['lcsc'])
    fp.SetField('Assembly',part['assembly'])
    for field in fp.GetFields():
        field.SetLayer(p.F_Fab if part['side']=='F' else p.B_Fab)
        field.SetVisible(field.GetName()=='Reference')
    fp.SetOrientationDegrees(part['rot'])
    fp.SetPosition(v(*part['pcb']))
    if part['side']=='B':
        fp.Flip(fp.GetPosition(),p.FLIP_DIRECTION_LEFT_RIGHT)
    fp.Reference().SetTextSize(v(.7,.7))
    fp.Reference().SetTextThickness(p.FromMM(.12))
    fp.Reference().SetLayer(p.F_Fab if part['side']=='F' else p.B_Fab)
    fp.Value().SetVisible(False)
    for pad in fp.Pads():
        name=part['nets'].get(pad.GetNumber())
        if name: pad.SetNet(nets[name])
    available={pad.GetNumber() for pad in fp.Pads()}
    assert set(part['nets'])<=available,(part['ref'],set(part['nets'])-available)
    fps[part['ref']]=fp

corners=[(0,0),(W,0),(W,H),(0,H)]
for a,b in zip(corners,corners[1:]+corners[:1]):
    line=p.PCB_SHAPE(board)
    line.SetShape(p.SHAPE_T_SEGMENT)
    line.SetStart(v(*a)); line.SetEnd(v(*b))
    line.SetLayer(p.Edge_Cuts); line.SetWidth(p.FromMM(.05)); board.Add(line)

for text,x,y,size in [('RP2040 PANEL / REV A',27,.9,.8),('DRAFT - NOT FOR FAB',19,11.8,.8),
                       ('1',13.202,13.2,.8),('16',17.6,35.8,.8),
                       ('+5V',7.2,6,.8),('GND',7.2,8.54,.8),
                       ('A',6.5,38,.8),('B',6.5,40.54,.8),('GND',4,45.5,.8)]:
    t=p.PCB_TEXT(board);t.SetText(text);t.SetPosition(v(x,y));t.SetTextSize(v(size,size))
    t.SetTextThickness(p.FromMM(.12));t.SetLayer(p.F_SilkS);board.Add(t)

coordinates={}
for pad in fps['J1'].Pads():
    num=int(pad.GetNumber());pos=pad.GetPosition()
    expected=(13.202+((num-1)%2)*2.54,15.600+((num-1)//2)*2.54)
    coordinates[num]=[pos.x/1e6,pos.y/1e6,pad.GetNetname()]
    assert abs(pos.x/1e6-expected[0])<.00001 and abs(pos.y/1e6-expected[1])<.00001,(num,coordinates[num],expected)
assert fps['J1'].GetLayer()==p.B_Cu
assert board.GetCopperLayerCount()==2
p.SaveBoard(str(ROOT/'pico-panel.kicad_pcb'),board)

project={'meta':{'filename':'pico-panel.kicad_pro','version':1},
         'board':{'design_settings':{'rules':{'min_clearance':.127,'min_track_width':.127,
                    'min_via_diameter':.6,'min_through_hole_diameter':.3,'min_via_annular_width':.15,
                    'min_copper_edge_clearance':.3}}},
         'net_settings':{'classes':[{'name':'Default','clearance':.127,'track_width':.2,
              'via_diameter':.6,'via_drill':.3,'diff_pair_width':.8,'diff_pair_gap':.15,
              'diff_pair_via_gap':.25}],'meta':{'version':4}},'schematic':{},'text_variables':{}}
(ROOT/'pico-panel.kicad_pro').write_text(json.dumps(project,indent=2)+'\n')
(ROOT/'reports/connector-top-view.json').write_text(json.dumps(coordinates,indent=2)+'\n')
boxes={ref:box(fp) for ref,fp in fps.items()}
clashes=[]
for i,(a,ba) in enumerate(boxes.items()):
    if ba is None: continue
    for b,bb in list(boxes.items())[i+1:]:
        if bb and fps[a].GetLayer()==fps[b].GetLayer() and overlap(ba,bb): clashes.append([a,b])
outside=[ref for ref,b in boxes.items() if b and (b[0]<0 or b[1]<0 or b[2]>W or b[3]>H)]
report={'components':len(parts),'layers':2,'board_mm':[W,H], 'courtyard_overlaps':clashes,
        'outside':outside,'boxes':boxes,'status':'UNROUTED DRAFT'}
(ROOT/'reports/placement.json').write_text(json.dumps(report,indent=2)+'\n')
print('Pin-net manifest matches KiCad netlist; all 16 J1 coordinates verified.')
print('Courtyard overlaps:',clashes,'Outside:',outside)
