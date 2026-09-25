"""Read-only verification of selected LCSC codes against the installed plugin catalog."""
from pathlib import Path
import json
import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[1]
DB=Path.home()/'Documents/KiCad/10.0/scripting/plugins/kicad-jlcpcb-tools/jlcpcb/current-parts-fts5.db'
c=sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True)
c.row_factory=sqlite3.Row
parts=json.loads((ROOT/'parts.json').read_text())
result=[]
for code in sorted({p['lcsc'] for p in parts if p['lcsc']}):
    row=c.execute('SELECT * FROM parts WHERE "LCSC Part"=?',(code,)).fetchone()
    values={p['value'] for p in parts if p['lcsc']==code}
    item={'code':code,'intended':sorted(values),'catalog':dict(row) if row else None}
    result.append(item)
    print(code,','.join(values),row['MFR.Part'] if row else 'MISSING',row['Package'] if row else '',row['Description'] if row else '')
(ROOT/'reports/parts-catalog.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
