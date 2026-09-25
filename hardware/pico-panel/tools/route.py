"""Critical routes, Specctra exchange and ground pour; no manufacturing release."""
from pathlib import Path
import sys
import pcbnew as p
from kitools import _find_block
ROOT=Path(__file__).resolve().parents[1]
PCB=ROOT/'pico-panel.kicad_pcb'
b=p.LoadBoard(str(PCB))
def v(x,y):return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
fps={f.GetReference():f for f in b.GetFootprints()}
def pad(ref,num):return next(q for q in fps[ref].Pads() if q.GetNumber()==str(num))
def xy(ref,num):
    a=pad(ref,num).GetPosition();return (a.x/1e6,a.y/1e6)
def wire(net,points,width=.2,layer=p.F_Cu,locked=True):
    for a,c in zip(points,points[1:]):
        if a==c:continue
        t=p.PCB_TRACK(b);t.SetStart(v(*a));t.SetEnd(v(*c));t.SetWidth(p.FromMM(width))
        t.SetLayer(layer);t.SetNet(b.FindNet(net));t.SetLocked(locked);b.Add(t)
def via(net,x,y):
    q=p.PCB_VIA(b);q.SetPosition(v(x,y));q.SetWidth(p.FromMM(.6));q.SetDrill(p.FromMM(.3))
    q.SetViaType(p.VIATYPE_THROUGH);q.SetLayerPair(p.F_Cu,p.B_Cu);q.SetNet(b.FindNet(net));q.SetLocked(True);b.Add(q)

mode=sys.argv[1]
if mode=='critical':
    assert 'HRO_TYPE-C-31-M-12' in str(fps['J2'].GetFPID()), 'Old USB routing geometry: redesign for vertical J2 after placement approval'
    assert not list(b.GetTracks()),'Refuse to overwrite an already routed board'
    # USB neck-down at the QFN and series resistors; pair stays over a bottom reference area.
    wire('USB_DP_MCU',[xy('U1',47),(36,18.9),(35.8,18.7),xy('R8',2)],.127)
    wire('USB_DM_MCU',[xy('U1',46),(36.4,18.9),(36.625,18.675),(37.5,18.675),xy('R9',2)],.127)
    wire('USB_DP',[xy('R8',1),(35.8,15.6),(36.5,14.9),(39,14.9)],.2)
    wire('USB_DM',[xy('R9',1),(38,15.85),(39.4,15.85)],.2)
    wire('USB_DP',[(39,14.9),(43,14.9),(44.2,13.7)],.8)
    wire('USB_DM',[(39.4,15.85),(43.5,15.85)],.8)
    wire('USB_DP',[(44.2,13.7),(45.55,13.7),xy('U3',1)],.2)
    wire('USB_DM',[(43.5,15.85),(47.45,15.85),xy('U3',3)],.2)
    # USB-C orientation duplicates: the D+ bridge changes layer only at the connector.
    for num in ('A6','B6'):
        pt=xy('J2',num)
        wire('USB_DP',[pt,(pt[0],9.6)],.127)
        via('USB_DP',pt[0],9.6)
    wire('USB_DP',[(46.25,9.6),(47.25,9.6)],.2,p.B_Cu)
    wire('USB_DP',[(46.25,9.6),(45.55,10.3),xy('U3',6)],.127)
    wire('USB_DM',[xy('J2','A7'),(46.75,10.3),(47.45,11.0),xy('U3',4)],.127)
    wire('USB_DM',[xy('J2','B7'),(47.75,9.2),(48.2,9.65),(48.2,10.8),xy('U3',4)],.127)
    # The ESD device internally joins its paired I/O pins, but the PCB needs that connection too.
    for net,nums,x in [('USB_DP',(1,6),45.55),('USB_DM',(3,4),47.45)]:
        wire(net,[xy('U3',nums[0]),xy('U3',nums[1])],.2)
    # Ground escape from exposed pad, outside solder paste: no open via in the thermal pad.
    for x,y in [(32.9,21.8),(37.1,24.2)]:
        via('GND',x,y)
        wire('GND',[xy('U1',57),(x,y)],.3)
    # Preserve a continuous copper reference below the principal USB route.
    z=p.ZONE(b);z.SetLayer(p.B_Cu);z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(False);z.SetDoNotAllowZoneFills(False)
    z.SetZoneName('USB_BOTTOM_REFERENCE_NO_SIGNAL_TRACKS')
    poly=z.Outline();poly.NewOutline()
    for x,y in [(35,11.3),(49,11.3),(49,19),(35,19)]:poly.Append(int(p.FromMM(x)),int(p.FromMM(y)))
    b.Add(z)
    p.SaveBoard(str(PCB),b)
elif mode=='export':
    dest=ROOT/'reports/panel.dsn'
    assert p.ExportSpecctraDSN(b,str(dest))
    text=dest.read_text()
    start=text.index('(class kicad_default')
    block=_find_block(text,start)
    # QFN pitch requires a 0.127 mm escape width. Supply nets get explicit wider classes.
    names=block[:block.index('(circuit')].split()[2:]
    power={'3V3','SYS_5V','PANEL_5V','PANEL_5V_IN','USB_5V','1V1','GND'}
    def group(name,nets,width):
        return f'(class {name} '+ ' '.join(nets)+'\n (circuit (use_via "Via[0-1]_600:300_um"))\n'+f' (rule (width {width}) (clearance 127)))'
    replacement=group('kicad_default',[n for n in names if n not in power],127)+'\n'+group('power',[n for n in names if n in power],250)
    text=text[:start]+replacement+text[start+len(block):]
    dest.write_text(text)
    print('Exported two-layer DSN, 0.127 mm signal / 0.25 mm power, 0.6/0.3 vias.')
elif mode=='import':
    assert p.ImportSpecctraSES(b,str(ROOT/'reports/panel.ses'))
    p.SaveBoard(str(PCB),b)
elif mode=='pour':
    for layer in (p.F_Cu,p.B_Cu):
        z=p.ZONE(b);z.SetLayer(layer);z.SetNet(b.FindNet('GND'));z.SetLocalClearance(p.FromMM(.2))
        z.SetThermalReliefGap(p.FromMM(.2));z.SetThermalReliefSpokeWidth(p.FromMM(.25))
        z.SetPadConnection(p.ZONE_CONNECTION_FULL);z.SetMinThickness(p.FromMM(.127))
        poly=z.Outline();poly.NewOutline()
        for x,y in [(.3,.3),(57.5,.3),(57.5,45.8),(.3,45.8)]:poly.Append(p.FromMM(x),p.FromMM(y))
        b.Add(z)
    b.BuildConnectivity();p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(str(PCB),b)
else:raise SystemExit('Expected critical/export/import/pour')
