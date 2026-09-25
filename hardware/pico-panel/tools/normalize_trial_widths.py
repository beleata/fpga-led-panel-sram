"""Trial correction of undersized fanout tracks; accept only after fresh DRC."""
from pathlib import Path
import pcbnew as p

root = Path(__file__).resolve().parents[1] / 'routing-trial'
path = root / 'pico-panel.kicad_pcb'
b = p.LoadBoard(str(path))
changed = 0
for track in b.GetTracks():
    if isinstance(track,p.PCB_VIA):
        continue
    width = track.GetWidth()
    if width < 127000:
        assert width in (95200,125000), f'Unexpected narrow trace: {width}'
        track.SetWidth(127000)
        changed += 1
p.SaveBoard(str(path),b)
print(f'Adjusted {changed} undersized fanout tracks to 0.127 mm; rerun DRC before accepting.')
