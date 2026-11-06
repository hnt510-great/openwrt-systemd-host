#!/usr/bin/python3
"""Debian-side pull and deduplication. Install/run explicitly on Debian."""
import argparse,json,sqlite3,subprocess,time
p=argparse.ArgumentParser();p.add_argument('router');p.add_argument('--database',default='router-audit.sqlite');p.add_argument('--identity');a=p.parse_args()
if a.router.startswith('-'):p.error('invalid SSH destination')
db=sqlite3.connect(a.database)
db.executescript('CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY, time TEXT, module TEXT, payload TEXT); CREATE TABLE IF NOT EXISTS state(host TEXT PRIMARY KEY,cursor TEXT); CREATE INDEX IF NOT EXISTS batches_module_time ON batches(module,time); CREATE INDEX IF NOT EXISTS batches_time ON batches(time);')
r=db.execute('select cursor from state where host=?',(a.router,)).fetchone()
for _ in range(100):
    cmd=['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=10',a.router,'router-audit-export','samples','--limit','500']
    if a.identity:cmd[1:1]=['-i',a.identity]
    # First run: backfill the router's whole 24-hour buffer instead of the export default 15m.
    cmd+=['--cursor',r[0]] if r else ['--since','24h']
    response=subprocess.run(cmd,capture_output=True,text=True,timeout=40,check=True)
    batch=json.loads(response.stdout)
    with db:
        for record in batch['data']['records']:
            key=record['host_id']+':'+record['module']+':'+record['collected_at']
            db.execute('insert or ignore into batches values(?,?,?,?)',(key,record['collected_at'],record['module'],json.dumps(record)))
        cursor=batch.get('next_cursor')
        if cursor:db.execute('insert or replace into state values(?,?)',(a.router,cursor))
        db.execute("delete from batches where time < strftime('%Y-%m-%dT%H:%M:%SZ','now','-30 days')")
    if batch['data'].get('cursor_expired'):print('Warning: router buffer gap')
    r=(cursor,)
    if not batch['data']['truncated']:break
print('Stored records:',db.execute('select count(*) from batches').fetchone()[0])
