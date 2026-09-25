"""HanRun HR963380AE land pattern, PDF page 3 and LCSC EasyEDA cross-check."""
from pathlib import Path
import json
import pcbnew as p

ROOT = Path(__file__).resolve().parents[1]
NAME = 'RJ45_HanRun_HR963380AE_Vertical'
LIB = ROOT/'Panel.pretty'
LIB.mkdir(exist_ok=True)
lines = [f'(footprint "{NAME}" (version 20241229) (generator "pcbnew")',
         '(layer "F.Cu") (attr smd)',
         '(descr "HanRun HR963380AE C19724763. PDF Rev00 p3 component-side land pattern, cross-checked against LCSC package b633f41d663444f8849f9de977d45e24. Origin: midpoint of locating holes. See ETHERNET_FOOTPRINT_BG.md for 0.05mm drawing discrepancy.")',
         '(tags "RJ45 vertical integrated magnetics 14 contacts shield SMT")',
         '(property "Reference" "REF**" (at 0 -11.5) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
         f'(property "Value" "{NAME}" (at 0 11.5) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))']

def rect(x1,y1,x2,y2,layer,width):
    lines.append(f'(fp_rect (start {x1} {y1}) (end {x2} {y2}) (stroke (width {width}) (type default)) (fill none) (layer "{layer}"))')

def line(x1,y1,x2,y2,layer='F.SilkS',width=.12):
    lines.append(f'(fp_line (start {x1} {y1}) (end {x2} {y2}) (stroke (width {width}) (type default)) (layer "{layer}"))')

# Nominal body from the manufacturer. Courtyard encloses all lands plus 0.5 mm.
rect(-8.1,-8.25,8.1,8.25,'F.Fab',.1)
rect(-8.6,-10.55,8.6,10.55,'F.CrtYd',.05)
for x in (-8.22,8.22):
    line(x,-8.35,x,8.35)
line(7,8.35,8.22,8.35)
line(-8.22,8.35,-7,8.35)
line(7.1,7.2,7.6,7.6,'F.Fab',.1)
line(7.6,7.6,7.1,8,'F.Fab',.1)
line(7.1,8,7.1,7.2,'F.Fab',.1)

expected = {}
def pad(number,x,y,w,h):
    expected[str(number)] = [x,y,w,h]
    lines.append(f'(pad "{number}" smd rect (at {x:.6f} {y:.6f}) (size {w} {h}) (layers "F.Cu" "F.Paste" "F.Mask"))')
    ly = y-2.05 if number <= 10 else y+2.85
    if number == 15:
        ly = y+2.05
    lines.append(f'(fp_text user "{number}" (at {x:.6f} {ly:.6f}) (layer "F.Fab") (effects (font (size .7 .7) (thickness .1))))')

# 8.60 = 10.05 - 2.90/2. Supplier CAD uses this center, not the 8.55 callout.
for number in range(1,11):
    pad(number,6.075-(number-1)*1.35,8.60,.85,2.90)
for number,x in [(11,6.55),(12,4.01),(13,-4.01),(14,-6.55)]:
    pad(number,x,-7.95,1.10,4.20)
pad(15,0,-8.75,2.50,2.60)
for x in (-7,7):
    lines.append(f'(pad "" np_thru_hole circle (at {x} 0) (size 1.4 1.4) (drill 1.4) (layers "*.Cu" "*.Mask"))')
lines.append(')')
(LIB/(NAME+'.kicad_mod')).write_text('\n'.join(lines)+'\n')

# Compare every copper land and both locating holes with the supplier's CAD.
source = json.loads((ROOT/'reference/HR963380AE-easyeda.json').read_text())['result']
assert source['lcsc']['number']=='C19724763'
package = source['packageDetail']
assert package['uuid']=='b633f41d663444f8849f9de977d45e24'
shapes = [s.split('~') for s in package['dataStr']['shape']]
holes = [s for s in shapes if s[0]=='HOLE']
assert len(holes)==2
ox = sum(float(s[1]) for s in holes)/2
oy = sum(float(s[2]) for s in holes)/2
diffs = {}
for s in shapes:
    if s[0] != 'PAD':
        continue
    assert s[1]=='RECT' and s[6]=='1' and float(s[11])==0
    number = s[8]
    supplier = [(float(s[2])-ox)*.254,(float(s[3])-oy)*.254,
                float(s[4])*.254,float(s[5])*.254]
    diffs[number] = max(abs(a-b) for a,b in zip(supplier,expected[number]))
assert set(diffs)==set(expected)
assert max(diffs.values())<.001,diffs
for s in holes:
    assert abs(abs((float(s[1])-ox)*.254)-7)<.001
    assert abs((float(s[2])-oy)*.254)<.001
    assert abs(float(s[3])*.254*2-1.4)<.001

fp = p.FootprintLoad(str(LIB),NAME)
assert fp
copper = [pad for pad in fp.Pads() if pad.GetNumber()]
npth = [pad for pad in fp.Pads() if not pad.GetNumber()]
assert len(copper)==15 and len(npth)==2
for item in copper:
    number = item.GetNumber()
    xy = item.GetPosition()
    size = item.GetSize()
    got = [xy.x/1e6,xy.y/1e6,size.x/1e6,size.y/1e6]
    assert max(abs(a-b) for a,b in zip(got,expected[number]))<.00001
    assert item.GetAttribute()==p.PAD_ATTRIB_SMD
for item in npth:
    assert item.GetAttribute()==p.PAD_ATTRIB_NPTH
    assert item.GetDrillSize().x==p.FromMM(1.4)

report = {'footprint':'Panel:'+NAME,'pads':expected,'npth_holes_mm':[[-7,0,1.4],[7,0,1.4]],
          'supplier_package_uuid':package['uuid'],'max_supplier_delta_mm':max(diffs.values()),
          'verified':'15 SMT pads and 2 NPTH holes; pin numbering and every pad coordinate/size match supplier within 0.001 mm',
          'drawing_discrepancy':'PDF p3 says y=8.55 but 10.05-2.90/2=8.60; supplier CAD uses 8.60. Not manufacturing release.'}
(ROOT/'reports/ethernet-footprint.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['verified'])
print('Largest supplier CAD rounding delta:',max(diffs.values()),'mm')
