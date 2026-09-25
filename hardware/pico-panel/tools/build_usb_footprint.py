"""SHOU HAN C3151748 land pattern, manufacturer PDF page 2, dimensions in mm."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
name = 'USB_C_SHOUHAN_TYPE-C_16PLT-H6.5_Vertical'
folder = ROOT / 'Panel.pretty'
folder.mkdir(exist_ok=True)
lines = [f'(footprint "{name}" (version 20241229) (generator "pcbnew")',
         '(layer "F.Cu") (attr smd)',
         '(descr "SHOU HAN TYPE-C 16PLT-H6.5 C3151748. Vertical receptacle; manufacturer recommended land pattern PDF page 2. Height 6.5 mm; recommended PCB 0.8 mm.")',
         '(property "Reference" "REF**" (at 0 -3.5) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
         f'(property "Value" "{name}" (at 0 3.5) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))']
for layer, w, h, stroke in [('F.Fab',8.94,4.9,.1),('F.CrtYd',9.5,6,.05),('F.SilkS',9.1,5.8,.12)]:
    lines.append(f'(fp_rect (start {-w/2} {-h/2}) (end {w/2} {h/2}) (stroke (width {stroke}) (type default)) (fill none) (layer "{layer}"))')
xs = [-2.75,-1.25,-.75,-.25,.25,.75,1.25,2.75]
for row, y in [(['A1','A4','A5','A6','A7','A8','A9','A12'],-.865),
               (['B12','B9','B8','B7','B6','B5','B4','B1'],.865)]:
    for pin,x in zip(row,xs):
        lines.append(f'(pad "{pin}" smd rect (at {x} {y}) (size 0.30 0.87) (layers "F.Cu" "F.Paste" "F.Mask"))')
for x in [-2.4,2.4]:
    for y in [-2.15,2.15]:
        lines.append(f'(pad "SH" thru_hole oval (at {x} {y}) (size 1.35 1.10) (drill oval 0.85 0.60) (layers "*.Cu" "*.Mask"))')
for x in [-3.75,3.75]:
    lines.append(f'(pad "" np_thru_hole circle (at {x} 0) (size 0.52 0.52) (drill 0.52) (layers "*.Cu" "*.Mask"))')
lines.append(')')
(folder / (name+'.kicad_mod')).write_text('\n'.join(lines)+'\n')
(ROOT/'fp-lib-table').write_text('(fp_lib_table (version 7)\n (lib (name "Panel")(type "KiCad")(uri "${KIPRJMOD}/Panel.pretty")(options "")(descr "Verified local connector footprint")))\n')
print('Generated vertical USB-C: 16 SMT contacts, 4 plated slots, 2 locating holes.')
