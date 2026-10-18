#!/usr/bin/env python3
"""Inspect compact maintenance problems and migrate private queues."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import time

from maintenance_runtime import Queue, lock, state_root
from maintenance_issues import deliver


def migrate(root):
    """Explicit one-time schema cutover: archive old groups, preserve all cursors."""
    path = root / 'state.sqlite3'
    if not path.exists():
        return {'job':root.name,'migration':'no previous queue'}
    with lock(root/'run.lock'), lock(state_root()/'mutation.lock'):
        db = sqlite3.connect(path)
        if 'windows' in {row[1] for row in db.execute('PRAGMA table_info(incidents)')}:
            db.close()
            return {'job':root.name,'migration':'already current'}
        backup_root = root/'migration-backups'
        backup_root.mkdir(mode=0o700,exist_ok=True)
        backup = backup_root/f'{time.time_ns()}.sqlite3'
        descriptor = os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        os.close(descriptor)
        with sqlite3.connect(backup) as saved:
            db.backup(saved)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='incidents'").fetchone():
            count = db.execute("SELECT count(*) FROM fingerprints").fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE name='fingerprints'").fetchone() else 0
            with db:
                db.execute('DROP TABLE IF EXISTS fingerprints')
                db.execute('DROP TABLE IF EXISTS outbox')
            db.close()
            queue=Queue(path)
            queue.db.close()
            return {'job':root.name,'archived_groups':count,'backup':str(backup),'cursors':'preserved'}
        with db:
            for name,definition in [('windows','INTEGER NOT NULL DEFAULT 0'),('window_ns','INTEGER NOT NULL DEFAULT 0'),('verified_ns','INTEGER'),('evidence_hash','TEXT'),('investigated_hash','TEXT'),('impact','TEXT')]:
                db.execute(f'ALTER TABLE incidents ADD COLUMN {name} {definition}')
            retired = db.execute("UPDATE incidents SET status='closed',completed_ns=?,impact='Historical group archived at cutover; fresh collection determines current problems'",(time.time_ns(),)).rowcount
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('schema_version','2')")
            db.execute('DROP TABLE IF EXISTS fingerprints')
            db.execute('DROP TABLE IF EXISTS outbox')
        db.close()
        queue=Queue(path)
        queue.prune()
        queue.db.close()
        return {'job':root.name,'archived_groups':retired,'backup':str(backup),'cursors':'preserved'}


def read_job(root):
    path = root/'state.sqlite3'
    if not path.exists():
        return {'job':root.name,'collection_ns':None,'coverage':[]},[]
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        meta=dict(db.execute('SELECT key,value FROM metadata'))
        if meta.get('schema_version')!='2':
            raise RuntimeError(f'{root.name}: run fleet maintenance migrate before reading problems')
        rows=[dict(row) for row in db.execute("SELECT * FROM incidents WHERE status IN ('pending','active','blocked','unresolved','approval_required') ORDER BY verified_ns DESC")]
        links={}
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='issue_delivery'").fetchone():
            for incident_id,url,error in db.execute('SELECT incident_id,url,error FROM issue_delivery'):
                links.setdefault(incident_id,[]).append({'url':url,'error':error})
    for row in rows:
        row['job']=root.name
        row['issues']=links.get(row['id'],[])
    return {'job':root.name,'collection_ns':int(meta['collection_ns']) if meta.get('collection_ns') else None,'coverage':json.loads(meta.get('coverage','[]'))},rows


def snapshot(base=None,limit=5):
    jobs,rows=[],[]
    for job in ('triage','cluster-wizard'):
        meta,items=read_job((base or state_root())/job)
        jobs.append(meta); rows.extend(items)
    rows.sort(key=lambda row:(row['status']!='approval_required',-(row['verified_ns'] or 0)))
    problems=[]
    for row in rows[:limit]:
        outcome=json.loads(row['outcome'] or '{}')
        problems.append({key:row[key] for key in ('id','job','service','status','count','verified_ns','impact')}|{
            'issues':row.get('issues',[]),
            'summary':outcome.get('summary') or row['impact'],
            'next_action':outcome.get('next_action') or 'Await the next scheduled investigation.'})
    return {'problems':problems,'remaining':max(0,len(rows)-limit),'active_count':len(rows),'collectors':jobs}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['maintenance'])
    parser.add_argument('operation',choices=['status','show','migrate','retry','deliver-issues'])
    parser.add_argument('id',nargs='?')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    if args.operation=='migrate':
        print(json.dumps([migrate(state_root()/job) for job in ('triage','cluster-wizard')],indent=2)); return 0
    if args.operation=='deliver-issues':
        results={}
        for job in ('triage','cluster-wizard'):
            root=state_root()/job
            if not (root/'state.sqlite3').exists(): continue
            with lock(root/'run.lock'):
                queue=Queue(root/'state.sqlite3')
                try:
                    results[job]=deliver(queue,job,force=True)
                finally:
                    queue.db.close()
        print(json.dumps(results,indent=2))
        return 1 if any(result.get('failed') for result in results.values()) else 0
    view=snapshot()
    if args.operation=='status':
        if args.json:
            print(json.dumps(view,indent=2)); return 0
        print(f"{view['active_count']} current problems; showing {len(view['problems'])}, {view['remaining']} more")
        for row in view['problems']:
            stamp=datetime.fromtimestamp(row['verified_ns']/1e9,timezone.utc).isoformat() if row['verified_ns'] else 'unverified'
            print(f"{row['id']} {row['service']} [{row['status']}]\n  {row['summary']}\n  Next: {row['next_action']}\n  Verified: {stamp}")
            for issue in row['issues']:
                if issue['url']: print(f"  Issue: {issue['url']}")
                if issue['error']: print(f"  Issue delivery pending: {issue['error']}")
        for item in view['collectors']:
            stamp=datetime.fromtimestamp(item['collection_ns']/1e9,timezone.utc).isoformat() if item['collection_ns'] else 'never collected'
            missing=[row['source'] for row in item['coverage'] if not row['complete']]
            print(f"{item['job']}: {stamp}; incomplete: {', '.join(missing) or 'none'}")
        return 0
    if not args.id:
        parser.error('show/retry require a problem ID')
    for job in ('triage','cluster-wizard'):
        root=state_root()/job
        path=root/'state.sqlite3'
        if not path.exists():continue
        if args.operation=='show':
            with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
                db.row_factory=sqlite3.Row
                row=db.execute('SELECT * FROM incidents WHERE id=?',(args.id,)).fetchone()
                if row:
                    value=dict(row)
                    for key in ('evidence','outcome'):value[key]=json.loads(value[key]) if value[key] else None
                    print(json.dumps(value,indent=2)); return 0
        else:
            with lock(root/'run.lock'),lock(state_root()/'mutation.lock'):
                queue=Queue(path)
                with queue.db:
                    changed=queue.db.execute("UPDATE incidents SET status='pending' WHERE id=? AND status IN ('blocked','unresolved','approval_required')",(args.id,)).rowcount
                queue.db.close()
                if changed:
                    print('Retry queued for the next scheduled run'); return 0
    parser.error('problem not found or not eligible for retry')


if __name__=='__main__':
    raise SystemExit(main())
