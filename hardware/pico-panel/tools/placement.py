"""Placement defaults for regeneration. Do not overwrite a manually edited PCB."""
from placement_wide import WIDTH, HEIGHT, OVERRIDES

def apply(parts):
    for part in parts:
        if part['ref'] in OVERRIDES:
            x, y, angle = OVERRIDES[part['ref']]
            part.update(pcb=[x, y], rot=angle)
        if part['ref'].startswith('C') and 4 <= int(part['ref'][1:]) <= 14:
            part['footprint'] = 'Capacitor_SMD:C_0402_1005Metric'
            part['lcsc'] = 'C1525'
