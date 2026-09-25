"""Export actual KiCad footprints in a labelled placement-only review drawing."""
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import pcbnew as p

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'preview'
CLI = Path(r'C:/Users/user/Tools/KiCad/bin/kicad-cli.exe')
study = '--ethernet-study' in sys.argv
prefix = 'ethernet-fit' if study else 'placement-review'
board = p.LoadBoard(str(OUT/'ethernet-mechanical.kicad_pcb' if study else ROOT/'pico-panel.kicad_pcb'))
assert board.GetCopperLayerCount() == 2
assert len(list(board.GetTracks())) == 0, 'This review is for placement, not routing'
removed_text = []
for fp in board.GetFootprints():
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    for item in list(fp.GraphicalItems()):
        if isinstance(item, p.PCB_TEXT):
            item.SetVisible(False)
            item.SetText('')
copy = OUT/(prefix+'-plot.kicad_pcb')
p.SaveBoard(str(copy),board)
raw = OUT/(prefix+'-geometry.svg')
subprocess.run([str(CLI),'pcb','export','svg','--layers','F.Cu,B.Cu,F.Fab,B.Fab,Edge.Cuts',
                '--mode-single','--fit-page-to-board','--exclude-drawing-sheet',
                '--output',str(raw),str(copy)],check=True)
ET.register_namespace('','http://www.w3.org/2000/svg')
svg = ET.parse(raw).getroot()
# Plot geometry stays unchanged; recolor the native layers for a light drawing.
for node in svg.iter():
    for key,value in list(node.attrib.items()):
        for old,new in [('#C83434','#bd8c32'),('#4D7FC4','#bd8c32'),
                        ('#AFAFAF','#43564d'),('#000080','#305f99'),
                        ('#FFFF00','#243e32'),('#C2C2C2','#243e32')]:
            value=value.replace(old,new)
        node.set(key,value)
geometry = ET.Element('{http://www.w3.org/2000/svg}g',{'transform':'translate(90 175) scale(17)'})
for node in svg:
    geometry.append(node)
pieces=['<svg xmlns="http://www.w3.org/2000/svg" width="1530" height="1080" viewBox="0 0 1530 1080">',
        '<rect width="1530" height="1080" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#172c23} .small{font-size:17px} .label{font-size:23px;font-weight:bold} .note{font-size:19px;fill:#52665c}</style>']
def text(x,y,value,cls='',extra=''):
    size = {'small':17,'label':23,'note':19}.get(cls,17)
    font = '' if 'font-size=' in extra else f'font-size="{size}"'
    weight = 'font-weight="bold"' if cls=='label' else ''
    fill = '#ffffff' if 'fill:white' in extra else ('#52665c' if cls=='note' else '#172c23')
    pieces.append(f'<text x="{x}" y="{y}" font-family="Arial" fill="{fill}" {font} {weight} {extra}>{value}</text>')
text(55,55,'RP2040 / ICND1065L',extra='font-size="32" font-weight="bold"')
text(55,87,'Механична проба: вертикален Ethernet · НЕПЪЛНА компоновка' if study else
     'Вариант 4: RS-485 до конектора · поглед отгоре · без трасиране', 'note')
text(1110,52,'REV A / 25.09.2026','note')
pieces.append('<rect x="90" y="175" width="982.6" height="783.7" fill="#f1f6f2" stroke="#172c23" stroke-width="2"/>')
pieces.append(ET.tostring(geometry,encoding='unicode'))
def line(x1,y1,x2,y2,color='#63776c',dash=''):
    pieces.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.4" stroke-dasharray="{dash}"/>')
line(90,134,1072.6,134);line(90,123,90,168);line(1072.6,123,1072.6,168)
text(537,122,'57,8 mm','note')
line(49,175,49,958.7);line(39,175,83,175);line(39,958.7,83,958.7)
text(33,625,'46,1 mm','note',extra='transform="rotate(-90 33 625)"')
def at(x,y):return 90+17*x,175+17*y
def label(x,y,value,size=14):
    xx,yy=at(x,y)
    text(xx,yy,value,extra=f'font-size="{size}" font-weight="bold" text-anchor="middle"')
label(35,22.8,'RP2040',15); label(35,24.1,'U1',12)
label(34,10.6,'FLASH',15);label(34,11.7,'8 MiB',12)
label(47,5.3,'USB-C',15)
label(6.5,2.7,'+5 V / GND',13)
label(4,35.3,'RS-485',13)
label(20.5,4.7,'RESET',12); label(30,4.7,'BOOT',12)
label(12.5,38.6,'RS-485',12)
label(17.8,41.5,'TERM',11)
label(35,32.2,'12 MHz',11)
if study:
    label(20,13.3,'SWD',12)
    label(34,39.1,'W5500',14)
    label(48.6,34.4,'RJ45',22)
    label(48.6,36.1,'ВЕРТИКАЛЕН',14)
    label(48.6,37.7,'с трансформатори',12)
    for pad in next(fp for fp in board.GetFootprints() if fp.GetReference()=='J6').Pads():
        if not pad.GetNumber():
            continue
        pos=pad.GetPosition();n=int(pad.GetNumber())
        dy=-2.05 if n<=10 else (2.05 if n==15 else 2.85)
        label(pos.x/1e6,pos.y/1e6+dy,str(n),11)
else:
    label(48.1,45.3,'SWD / DEBUG',13)
color='#16644d'
items=[(1,14.5,12.2,'Конектор към панела','J1: женски 2×8, отдолу','Стъпка 2,54 mm; без промяна'),
       (2,52,5,'Вертикална USB-C','J2: кабелът влиза отгоре','SHOU HAN C3151748, H = 6,5 mm'),
       (3,7.5,6,'Захранване от панела','J3: 1×2, стъпка 2,54 mm','Пин 1: +5 V; пин 2: GND'),
       (4,7.5,40,'RS-485 долу вляво','J5: 1×3, стъпка 2,54 mm','Пинове 1–3: A / B / GND'),
       (5,53.5,40.9,'Програмиране / диагностика','J4: SWD; SW1: BOOTSEL','SW2: RESET; D1: статус')]
if study:
    items[4]=(5,22.6,15.5,'SWD преместен','J4 е между J1 и резисторите','Основният проект е запазен')
    items.append((6,55,31.5,'RJ45 с реални площадки','14 контакта + корпус (пад 15)','2 отвора Ø1,40 mm; без трасета'))
for i,x,y,title,sub1,sub2 in items:
    xx,yy=at(x,y)
    pieces.append(f'<circle cx="{xx}" cy="{yy}" r="13" fill="{color}"/>')
    text(xx,yy+5,str(i),extra='text-anchor="middle" style="fill:white" font-size="15" font-weight="bold"')
    ly=202+(i-1)*(111 if study else 132)
    pieces.append(f'<circle cx="1121" cy="{ly-7}" r="15" fill="{color}"/>')
    text(1121,ly-1,str(i),extra='text-anchor="middle" style="fill:white" font-size="17" font-weight="bold"')
    text(1148,ly,title,'label');text(1110,ly+34,sub1,'small');text(1110,ly+61,sub2,'small')
# Panel pin 1 coordinate is shown in the same top view, not mirrored.
xx,yy=at(13.202,15.6)
pieces.append(f'<circle cx="{xx}" cy="{yy}" r="16" fill="none" stroke="#c03f32" stroke-width="3"/>')
line(xx-19,yy,90,yy,'#c03f32','4 4');line(xx,175,xx,yy-19,'#c03f32','4 4')
text(1120,904,'Пин 1: x = 13,202 mm','small')
text(1120,931,'y = 15,600 mm от горния ляв ъгъл','small')
text(90,1002,'Още НЕ са поставени: 25 MHz кварц, Ethernet пасивни елементи и ново захранване.' if study else
     '2 медни слоя · 77 компонента · 3,3 V сигнали без буфери','note')
text(90,1033,'Това проверява мястото за двата големи корпуса, НЕ доказва готова платка.' if study else
     'Корпусите са от KiCad. Долният J1 е показан прозрачно през платката.','note')
pieces.append('</svg>')
(OUT/(prefix+'.svg')).write_text('\n'.join(pieces),encoding='utf-8')
print(f'Saved {prefix}.svg, derived from KiCad geometry.')
