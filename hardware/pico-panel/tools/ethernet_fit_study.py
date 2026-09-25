"""Non-electrical mechanical study. Never modifies the main board or its BOM."""
from pathlib import Path
import json
import pcbnew as p

ROOT = Path(__file__).resolve().parents[1]
board = p.LoadBoard(str(ROOT/'pico-panel.kicad_pcb'))
assert not list(board.GetTracks()), 'Placement-only study requires an unrouted source'
fps = {f.GetReference(): f for f in board.GetFootprints()}
def v(x,y): return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
for ref,x,y,angle in [('J4',20,15.5,0),('C7',40,23.6,90),
                      ('R3',28.5,29.5,90)]:
    fps[ref].SetOrientationDegrees(angle)
    fps[ref].SetPosition(v(x,y))

u8 = p.FootprintLoad(r'C:/Users/user/Tools/KiCad/share/kicad/footprints/Package_QFP.pretty',
                     'LQFP-48_7x7mm_P0.5mm')
assert u8
board.Add(u8)
u8.SetReference('U8');u8.SetValue('W5500 - FIT STUDY ONLY')
u8.SetPosition(v(34,39));fps['U8']=u8
u8.Reference().SetLayer(p.F_Fab)
u8.Reference().SetPosition(v(34,39))
u8.Value().SetVisible(False)
for item in board.GetDrawings():
    if isinstance(item,p.PCB_TEXT) and item.GetText()=='DRAFT - NOT FOR FAB':
        item.SetPosition(v(19,10.5))

j6 = p.FootprintLoad(str(ROOT/'Panel.pretty'),'RJ45_HanRun_HR963380AE_Vertical')
assert j6
board.Add(j6)
j6.SetReference('J6');j6.SetValue('HR963380AE - CIRCUIT PENDING')
j6.SetField('LCSC','C19724763')
j6.Reference().SetVisible(False);j6.Value().SetVisible(False)
j6.SetPosition(v(48.6,35.1));fps['J6']=j6
assert len(list(j6.Pads()))==17

def bounds(fp):
    shapes=[g.GetBoundingBox() for g in fp.GraphicalItems() if g.GetLayer() in (p.F_CrtYd,p.B_CrtYd)]
    return (min(b.GetLeft() for b in shapes)/1e6+.025,min(b.GetTop() for b in shapes)/1e6+.025,
            max(b.GetRight() for b in shapes)/1e6-.025,max(b.GetBottom() for b in shapes)/1e6-.025)
boxes={ref:bounds(fp) for ref,fp in fps.items()}
def overlap(a,b):return a[0]<b[2]-.001 and b[0]<a[2]-.001 and a[1]<b[3]-.001 and b[1]<a[3]-.001
clashes=[]
for i,(a,ba) in enumerate(boxes.items()):
    for name,bb in list(boxes.items())[i+1:]:
        if fps[a].GetLayer()==fps[name].GetLayer() and overlap(ba,bb):clashes.append([a,name])
outside=[name for name,b in boxes.items() if b[0]<0 or b[1]<0 or b[2]>57.8 or b[3]>46.1]
report={'status':'MECHANICAL STUDY ONLY - ETHERNET AUXILIARY PARTS NOT PLACED',
        'rj45':'HR963380AE C19724763; 15 SMT pads and 2 NPTH holes; not yet connected to schematic',
        'body_mm':[16.2,16.5,16.85],'courtyard_overlaps':clashes,'outside':outside,
        'main_board_modified':False,'boxes':boxes}
(ROOT/'reports/ethernet-fit.json').write_text(json.dumps(report,indent=2)+'\n')
assert not clashes and not outside,report
p.SaveBoard(str(ROOT/'preview/ethernet-mechanical.kicad_pcb'),board)
print('Core bodies fit: no courtyard overlaps, no outline overhang. NOT a complete Ethernet placement.')
