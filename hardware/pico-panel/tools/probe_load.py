from pathlib import Path
import subprocess
import build_design as d
from kitools import Sch

original=list(d.s.body)
lo,hi=0,len(original)
while lo<hi:
    mid=(lo+hi)//2
    t=d.s
    t.body=original[:mid+1]
    path=d.ROOT/'reports'/f'probe-{mid}.kicad_sch'
    t.save(str(path))
    result=subprocess.run([r'C:/Users/user/Tools/KiCad/bin/kicad-cli.exe','sch','export','netlist',
                           '-o',str(d.ROOT/'reports'/'probe.net'),str(path)],capture_output=True,text=True)
    print(mid,result.returncode,flush=True)
    if result.returncode:
        hi=mid
    else:
        lo=mid+1
print('FIRST BAD:',lo,original[lo])
