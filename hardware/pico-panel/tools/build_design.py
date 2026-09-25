"""Generate the schematic and explicit pin-net manifest. Run with KiCad Python."""
from pathlib import Path
import json
import re
from kitools import Sch, snap_pt

ROOT = Path(__file__).resolve().parents[1]
s = Sch('pico-panel', paper='A0')
parts = []
RFP = 'Resistor_SMD:R_0603_1608Metric'
CFP = 'Capacitor_SMD:C_0603_1608Metric'
SO8 = 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'
SOT23 = 'Package_TO_SOT_SMD:SOT-23'


def alias(source, name):
    block = s.libs.get(source)
    block = re.sub(r'\(symbol "[^"]+"', f'(symbol "Panel:{name}"', block, count=1)
    block = re.sub(r'\(symbol "[^\"]*_(\d+_\d+)"', lambda m: f'(symbol "{name}_{m[1]}"', block)
    s.libs.add_custom('Panel:'+name, block)
    return 'Panel:'+name


FLASH = alias('Memory_Flash:W25Q32JVSS', 'W25Q64JVSSIQ')
RS485 = alias('Interface_UART:THVD1450D', 'SN65HVD75DR')
W5500 = alias('Interface_Ethernet:W5500', 'W5500')
# The stock library incorrectly calls INT an input; W5500 datasheet p10 says output.
from kitools import _find_block
wb = s.libs.get(W5500)
for pin_block in list(s.libs.pin_blocks(wb)):
    if '(number "36"' in pin_block:
        wb = wb.replace(pin_block,pin_block.replace('(pin input line','(pin output line',1))
s.libs.add_custom(W5500,wb)


def add(ref, value, lib, fp, nets, sch, pcb, lcsc='', rot=0, side='F', assembly='SMT'):
    sch = snap_pt(sch)
    comp = s.symbol(lib, ref, value, sch, footprint=fp, lcsc=lcsc,
                    props={'Assembly': assembly})
    used = {}
    for pin, net in nets.items():
        number = s.num(comp, str(pin))
        used[number] = net
    # Stacked supply pins share one wire, but every pin remains in the manifest.
    drawn = set()
    for pin in comp['pins']:
        point = s.pin(comp, pin)
        if point in drawn:
            continue
        drawn.add(point)
        if used.get(pin):
            direction = s.pin_dir(comp, pin)
            s.net(comp, pin, used[pin], length=5.08,
                  label_rot=90 if abs(direction[1]) > .5 else 0)
        else:
            s.no_connect(point)
    parts.append(dict(ref=ref,value=value,lib=lib,footprint=fp,nets=used,
                      pcb=pcb,rot=rot,side=side,lcsc=lcsc,assembly=assembly))
    return comp


def r(ref,val,n1,n2,sch,pcb,lcsc='C25804',rot=0,fp=RFP):
    return add(ref,val,'Device:R',fp,{'1':n1,'2':n2},sch,pcb,lcsc,rot)


def c(ref,val,n1,n2,sch,pcb,lcsc='C14663',rot=0,fp=CFP):
    return add(ref,val,'Device:C',fp,{'1':n1,'2':n2},sch,pcb,lcsc,rot)


signal_names = ['R1','G1','B1','R2','G2','B2','A','B','C','SCLK','LAT','OE']
panel_pins = [1,2,3,5,6,7,9,10,11,13,14,15]
mcu = {str(p):'3V3' for p in (1,10,22,33,42,43,44,48,49)}
mcu.update({str(p):'1V1' for p in (23,45,50)})
mcu.update({'2':'UART_TX','3':'UART_RX','18':'RS485_DIR',
            '19':'GND','20':'XIN','21':'XOUT','24':'SWCLK','25':'SWDIO','26':'RUN',
            '35':'PANEL_SENSE','36':'USB_SENSE','37':'LED_STATUS','46':'USB_DM_MCU',
            '47':'USB_DP_MCU','51':'QSPI_D3','52':'QSPI_CLK','53':'QSPI_D0',
            '54':'QSPI_D2','55':'QSPI_D1','56':'QSPI_CS','57':'GND'})
mcu.update({'27':'ETH_MISO','28':'ETH_CS','29':'ETH_SCK','30':'ETH_MOSI',
            '31':'ETH_RESET','32':'ETH_INT'})
for pin,sig in zip((4,5,6,7,8,9,11,12,13,14,15,16),signal_names):
    mcu[str(pin)]='PANEL_'+sig
add('U1','RP2040','MCU_RaspberryPi:RP2040',
    'Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm',mcu,(160,130),(35,23),'C2040')
add('U2','W25Q64JVSSIQ',FLASH,'Package_SO:SOIC-8_5.3x5.3mm_P1.27mm',
    {'1':'QSPI_CS','2':'QSPI_D1','3':'QSPI_D2','4':'GND','5':'QSPI_D0','6':'QSPI_CLK','7':'QSPI_D3','8':'3V3'},
    (65,145),(35,12),'C179171',rot=180)
r('R1','10k','3V3','QSPI_CS',(30,185),(39.5,12))
r('R2','1k','QSPI_CS','BOOT_SW',(55,185),(37,7),'C21190')
add('SW1','BOOTSEL','Switch:SW_Push','Button_Switch_SMD:SW_SPST_TL3342',
    {'1':'BOOT_SW','2':'GND'},(85,185),(31,5),assembly='HAND')
add('SW2','RESET','Switch:SW_Push','Button_Switch_SMD:SW_SPST_TL3342',
    {'1':'RUN','2':'GND'},(120,185),(23,5),assembly='HAND')
r('R3','10k','3V3','RUN',(145,205),(30,29))
add('Y1','ABM8-272-T3 12MHz','Device:Crystal_GND24','Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm',
    {'1':'XIN','2':'GND','3':'XTAL_OUT','4':'GND'},(55,230),(35,32),'C20625731')
r('R4','1k','XOUT','XTAL_OUT',(30,230),(35,28.5),'C21190')
c('C1','15p','XIN','GND',(80,230),(32,32),'C1644')
c('C2','15p','XTAL_OUT','GND',(105,230),(38,32),'C1644')
c('C3','100n','3V3','GND',(130,230),(40,15))
# Each MCU supply has its own local capacitor; C4..C12 are the nine 3V3 pins.
cap_positions=[(30,20),(30,24),(33,28),(40,25),(40,22),(40,20),(40,18),(36,18),(33,18)]
for i,pos in enumerate(cap_positions,4):
    c(f'C{i}','100n','3V3','GND',(30+(i-4)*23,275),pos)
c('C13','100n','1V1','GND',(30,315),(34,28))
c('C14','100n','1V1','GND',(55,315),(32,18))
c('C15','1u','1V1','GND',(80,315),(39,18),'C15849')
c('C16','1u','3V3','GND',(105,315),(41,18),'C15849')
add('J4','SWD 3V3 GND CLK IO RUN','Connector_Generic:Conn_01x05',
    'Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical',
    {'1':'3V3','2':'GND','3':'SWCLK','4':'SWDIO','5':'RUN'},(220,185),(44,39),rot=90,assembly='HAND')
r('R5','1k','LED_STATUS','LED_A',(145,315),(51,23),'C21190')
add('D1','STATUS green','Device:LED','LED_SMD:LED_0805_2012Metric',
    {'1':'GND','2':'LED_A'},(175,315),(54,23),'C2297')

# USB and power. Panel-fed controller is independent of the high-current LED supply.
usb={'A1':'GND','A12':'GND','B1':'GND','B12':'GND','SH':'GND',
     'A4':'USB_5V','A9':'USB_5V','B4':'USB_5V','B9':'USB_5V',
     'A5':'CC1','B5':'CC2','A6':'USB_DP','B6':'USB_DP','A7':'USB_DM','B7':'USB_DM'}
add('J2','USB-C VERTICAL H6.5','Connector:USB_C_Receptacle_USB2.0_16P',
    'Panel:USB_C_SHOUHAN_TYPE-C_16PLT-H6.5_Vertical',usb,(325,90),(47,5),'C3151748')
r('R6','5.1k','CC1','GND',(380,75),(43,9),'C23186')
r('R7','5.1k','CC2','GND',(405,75),(50,9),'C23186')
add('U3','USBLC6-2SC6','Power_Protection:USBLC6-2SC6','Package_TO_SOT_SMD:SOT-23-6',
    {'1':'USB_DP','6':'USB_DP','3':'USB_DM','4':'USB_DM','2':'GND','5':'USB_5V'},
    (380,125),(46,11),'C7519')
r('R8','27','USB_DP','USB_DP_MCU',(420,125),(38,17),'C25190')
r('R9','27','USB_DM','USB_DM_MCU',(445,125),(36,17),'C25190')
c('C17','1u','USB_5V','GND',(380,165),(51,11),'C15849')
r('R10','100k','USB_5V','USB_SENSE',(410,165),(49,16),'C25803')
r('R11','100k','USB_SENSE','GND',(435,165),(51,16),'C25803')
add('J3','PANEL POWER +5V GND','Connector_Generic:Conn_01x02',
    'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',
    {'1':'PANEL_5V_IN','2':'GND'},(315,230),(5,5),assembly='HAND')
add('F1','PTC 0.5A','Device:Polyfuse','Fuse:Fuse_1206_3216Metric',
    {'1':'PANEL_5V_IN','2':'PANEL_5V'},(350,230),(5,12),'C70076')
add('D2','SS14','Device:D_Schottky','Diode_SMD:D_SMA',
    {'1':'SYS_5V','2':'PANEL_5V'},(380,230),(6,17),'C2480')
add('U4','AP63203WU-7','Regulator_Switching:AP63203WU','Package_TO_SOT_SMD:TSOT-23-6',
    {'1':'3V3','2':'SYS_5V','3':'SYS_5V','4':'GND','5':'BUCK_SW','6':'BUCK_BST'},
    (450,230),(5,22.5),'C780769')
c('C18','10u 16V','SYS_5V','GND',(340,275),(3,19.2),'C1713',fp='Capacitor_SMD:C_0805_2012Metric')
c('C19','22u 10V','3V3','GND',(365,275),(3,32),'C29277',fp='Capacitor_SMD:C_0805_2012Metric')
add('L1','3.9u SWPA4030S3R9MT','Device:L','Inductor_SMD:L_Sunlord_SWPA4030S',
    {'1':'BUCK_SW','2':'3V3'},(330,500),(5,27.3),'C96899')
c('C23','100n','BUCK_BST','BUCK_SW',(380,500),(7.4,22.5))
c('C24','22u 10V','3V3','GND',(430,500),(6,32),'C29277',fp='Capacitor_SMD:C_0805_2012Metric')
c('C25','100n','SYS_5V','GND',(480,500),(6,19.2))
r('R12','100k','PANEL_5V','PANEL_SENSE',(410,275),(5,29),'C25803')
r('R13','100k','PANEL_SENSE','GND',(435,275),(8,30),'C25803')

# Direct 3.3 V outputs match the tested Pico; USB cannot power the controller.
pnet={str(pin):'PANEL_'+sig for pin,sig in zip(panel_pins,signal_names)}
pnet.update({str(pin):'GND' for pin in (4,8,12,16)})
add('J1','PANEL BOTTOM 2x8','Connector_Generic:Conn_02x08_Odd_Even',
    'Connector_PinSocket_2.54mm:PinSocket_2x08_P2.54mm_Vertical',pnet,(720,140),
    (13.202,15.600),side='B',assembly='HAND')
for i,sig in enumerate(signal_names):
    r(f'R{40+i}','47k','PANEL_'+sig,'GND',(540+(i%6)*36,310+(i//6)*45),
      (10,14+i*1.7),'C25819',rot=90)

# Non-isolated RS485 with built-in receiver fail-safe and optional termination.
add('U7','SN65HVD75DR',RS485,SO8,
    {'1':'UART_RX','2':'RS485_DIR','3':'RS485_DIR','4':'UART_TX','5':'GND','6':'RS485_A','7':'RS485_B','8':'3V3'},
    (350,395),(46,30),'C57928')
c('C22','100n','3V3','GND',(310,435),(46,26))
r('R18','10k','RS485_DIR','GND',(335,435),(41,29))
add('D4','SM712','Diode:SM712_SOT23',SOT23,
    {'1':'RS485_A','2':'RS485_B','3':'GND'},(395,395),(52,30),'C32677')
add('J5','RS485 A B GND','Connector_Generic:Conn_01x03',
    'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical',
    {'1':'RS485_A','2':'RS485_B','3':'GND'},(450,395),(44,44),rot=0,assembly='HAND')
r('R19','120 0.25W','RS485_A','TERM',(380,435),(53,35),'C17909',fp='Resistor_SMD:R_1206_3216Metric')
add('JP1','TERM 120R','Connector_Generic:Conn_01x02',
    'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',
    {'1':'TERM','2':'RS485_B'},(425,435),(55,37),assembly='HAND')

# Ethernet uses the official connected-center-tap network, not the isolated-CT circuit.
eth={'1':'ETH_TX_N','2':'ETH_TX_P','5':'ETH_RX_N','6':'ETH_RX_P',
     '10':'ETH_EXRES','20':'ETH_TOCAP','22':'ETH_1V2','23':'GND',
     '25':'ETH_LINK','27':'ETH_ACT','28':'3V3','29':'GND','30':'ETH_XI','31':'ETH_XO',
     '32':'ETH_CS','33':'ETH_SCK','34':'ETH_MISO','35':'ETH_MOSI','36':'ETH_INT','37':'ETH_RESET',
     '43':'3V3','44':'3V3','45':'3V3'}
eth.update({str(pin):'ETH_AVDD' for pin in (4,8,11,15,17,21)})
eth.update({str(pin):'GND' for pin in (3,9,14,16,19,48)})
add('U8','W5500',W5500,'Package_QFP:LQFP-48_7x7mm_P0.5mm',eth,(160,670),(34,39),'C32843')
add('J6','HR963380AE MAGJACK','Connector_Generic:Conn_01x15',
    'Panel:RJ45_HanRun_HR963380AE_Vertical',
    {'1':'ETH_TX_P','2':'ETH_TX_N','3':'ETH_J_RX_P','4':'ETH_J_RX_N','5':'ETH_CT','6':'ETH_CT',
     '11':'ETH_ACT_K','12':'3V3','13':'ETH_LINK_K','14':'3V3','15':'CHASSIS'},
    (320,665),(48.6,35.1),'C19724763')

ei=0
def loc():
    global ei
    pos=(400+(ei%10)*65,610+(ei//10)*45)
    ei+=1
    return pos

add('FB1','120R@100MHz 2A','Device:FerriteBead','Inductor_SMD:L_0603_1608Metric',
    {'1':'3V3','2':'ETH_AVDD'},loc(),(24,35),'C14709')
for i,pin in enumerate((4,8,11,15,17,21),30):
    c(f'C{i}','100n','ETH_AVDD','GND',loc(),(20+i-30,35),'C1525',fp='Capacitor_SMD:C_0402_1005Metric')
c('C36','10u 16V','ETH_AVDD','GND',loc(),(23,37),'C1713',fp='Capacitor_SMD:C_0805_2012Metric')
c('C37','100n','3V3','GND',loc(),(23,39),'C1525',fp='Capacitor_SMD:C_0402_1005Metric')
c('C38','4.7u','3V3','GND',loc(),(23,41),'C19666')
c('C39','4.7u','ETH_TOCAP','GND',loc(),(27,41),'C19666')
c('C40','10n','ETH_1V2','GND',loc(),(27,43),'C57112')
r('R60','12.4k 1%','ETH_EXRES','GND',loc(),(27,35),'C11692',fp='Resistor_SMD:R_0402_1005Metric')
add('Y2','ABM8-25.000MHZ-D2Y-T','Device:Crystal_GND24','Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm',
    {'1':'ETH_XI','2':'GND','3':'ETH_XO','4':'GND'},loc(),(25,40),'C179643')
c('C41','27p C0G','ETH_XI','GND',loc(),(22,40),'C1656')
c('C42','27p C0G','ETH_XO','GND',loc(),(28,40),'C1656')
r('R61','1M','ETH_XI','ETH_XO',loc(),(25,37),'C22935')
r('R62','10k','3V3','ETH_RESET',loc(),(26,30))
c('C43','100n','ETH_RESET','GND',loc(),(28,30))
r('R63','10k','3V3','ETH_CS',loc(),(26,28))
for ref,net in [('R64','ETH_TX_P'),('R65','ETH_TX_N')]:
    r(ref,'49.9 1%',net,'ETH_AVDD',loc(),(39,29 if ref=='R64' else 31),'C23185')
for ref,net in [('R66','ETH_RX_P'),('R67','ETH_RX_N')]:
    r(ref,'49.9 1%',net,'ETH_RX_BIAS',loc(),(39,33 if ref=='R66' else 35),'C23185')
c('C44','10n','ETH_RX_BIAS','GND',loc(),(39,37),'C57112')
c('C45','6.8n','ETH_RX_P','ETH_J_RX_P',loc(),(41,31),'C84723')
c('C46','6.8n','ETH_RX_N','ETH_J_RX_N',loc(),(41,33),'C84723')
r('R68','10','ETH_AVDD','ETH_CT',loc(),(41,28),'C22859')
c('C47','100n','ETH_CT','GND',loc(),(44,28))
r('R69','470','ETH_LINK','ETH_LINK_K',loc(),(43,44),'C23179')
r('R70','470','ETH_ACT','ETH_ACT_K',loc(),(47,44),'C23179')
c('C48','1n 1kV','CHASSIS','GND',loc(),(52,24),'C1941',fp='Capacitor_SMD:C_1206_3216Metric')
s.text('ETHERNET / W5500 / COMMON-CT MAGJACK / NO PoE',(25,595),size=3)

# Dedicated supply flags represent the passive diode-fed rails, not hidden ERC suppression.
for i,rail in enumerate(('PANEL_5V_IN','PANEL_5V','USB_5V','SYS_5V','GND','3V3','ETH_AVDD')):
    p=s.flag(snap_pt((40+i*40,480)))
    s.net(p,'1',rail,length=5.08)
for at,title in [((25,35),'RP2040 / FLASH / CLOCK / DEBUG'),((300,35),'USB-C / POWER'),
                 ((530,35),'PANEL OUTPUTS: 3.3V, BOTTOM CONNECTOR'),((300,350),'RS-485: NON-ISOLATED')]:
    s.text(title,at,size=3)
s.text('REV A DRAFT - NOT FOR MANUFACTURE',(25,530),size=4)
s.text('GP2..13: direct 3.3V, no series resistors. GP14 unused; GP23 senses panel power.\n'
       'RS485: GP0 TX, GP1 RX, GP15 direction. Panel 5V required also for USB programming.\n'
       'J1 pin 1 = (13.202,15.600) mm from top-left, TOP VIEW. Verify mating height before fabrication.',
       (25,550),size=2)
issues=s.verify()+s.verify_pin_overlap()+list(s.verify_label_collisions())
assert not issues, issues
from placement import apply
apply(parts)
# Reflect component package changes in the schematic, not only the PCB manifest.
for part in parts:
    index=next(i for i,b in enumerate(s.body) if '(symbol\n' in b and f'"Reference" "{part["ref"]}"' in b)
    s.body[index]=re.sub(r'(\(property "Footprint" ")[^"]*',lambda m:m[1]+part['footprint'],s.body[index])
    if part['lcsc']:
        s.body[index]=re.sub(r'(\(property "LCSC" ")[^"]*',lambda m:m[1]+part['lcsc'],s.body[index])
s.save(str(ROOT/'pico-panel.kicad_sch'),title='RP2040 ICND1065L Panel Controller',rev='A DRAFT')
s.dump_library(str(ROOT/'Panel.kicad_sym'),lib_prefix='Panel:')
(ROOT/'sym-lib-table').write_text('(sym_lib_table (version 7)\n (lib (name "Panel")(type "KiCad")(uri "${KIPRJMOD}/Panel.kicad_sym")(options "")(descr "Pin-compatible parts verified against datasheets")))\n')
(ROOT/'parts.json').write_text(json.dumps(parts,indent=2)+'\n')
print(f'Generated schematic and manifest: {len(parts)} components')
