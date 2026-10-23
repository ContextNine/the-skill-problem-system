#!/usr/bin/env python3
"""Inspect compact maintenance problems and migrate private queues."""
import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from maintenance_runtime import CLOSED, Queue, fingerprint, lock, state_root
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


def regroup(root, *, apply=False, expected_plan=None):
    """Merge fragmented identities without losing history, cursors or issue links."""
    path = root/'state.sqlite3'
    if not path.is_file():
        return {'job': root.name, 'groups_before': 0, 'groups_after': 0, 'duplicates': 0}
    with lock(root/'run.lock') if apply else nullcontext(), lock(state_root()/'mutation.lock') if apply else nullcontext():
        with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            if dict(db.execute('SELECT key,value FROM metadata')).get('schema_version') != '2':
                raise RuntimeError('Migrate the queue before regrouping')
            superseded = set()
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='incident_supersession'").fetchone():
                superseded = {row[0] for row in db.execute('SELECT incident_id FROM incident_supersession')}
            rows = [dict(row) for row in db.execute('SELECT * FROM incidents ORDER BY first_ns,id') if row['id'] not in superseded]
            linked = {row[0] for row in db.execute('SELECT incident_id FROM issue_delivery WHERE issue_number IS NOT NULL')}
        if any(row['status'] == 'active' for row in rows):
            raise RuntimeError('An agent is active; wait for it before regrouping')
        groups = {}
        for row in rows:
            event = json.loads(row['evidence'])
            identity = fingerprint(row['service'], event['line'])
            groups.setdefault(identity, []).append(row)
        plan = {'rows': rows, 'linked': sorted(linked),
                'groups': {identity: [row['id'] for row in group] for identity, group in groups.items()}}
        digest = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
        result = {'job': root.name, 'groups_before': len(rows), 'groups_after': len(groups),
                  'duplicates': len(rows)-len(groups), 'plan_sha256': digest, 'applied': False}
        if not apply:
            return result
        if not expected_plan or expected_plan != digest:
            raise RuntimeError('Regroup plan changed or is not confirmed; preview again')
        changed = any(len(group) > 1 or group[0]['fingerprint'] != identity for identity, group in groups.items())
        if not changed:
            return {**result, 'applied': True, 'unchanged': True}
        backup_root = root/'migration-backups'
        backup_root.mkdir(mode=0o700, exist_ok=True)
        backup = backup_root/f'regroup-{time.time_ns()}.sqlite3'
        fd = os.open(backup, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
        os.close(fd)
        with sqlite3.connect(path) as source, sqlite3.connect(backup) as saved:
            source.backup(saved)
        queue = Queue(path)
        now = time.time_ns()
        try:
            with queue.db:
                for identity, group in groups.items():
                    canonical = min(group, key=lambda row: (row['id'] != identity, row['id'] not in linked, row['first_ns'], row['id']))
                    latest = max(group, key=lambda row: (row['last_ns'], row['id']))
                    reviewed = [row for row in group if row['outcome']]
                    approvals = [row for row in reviewed if row['status'] == 'approval_required']
                    owner = max(approvals or reviewed or [latest], key=lambda row: (row['completed_ns'] or 0, row['last_ns']))
                    status = owner['status']
                    if status in CLOSED and any(row['status'] == 'pending' and row['last_ns'] > (owner['completed_ns'] or 0) for row in group):
                        status = 'pending'
                    outcome = json.loads(owner['outcome']) if owner['outcome'] else None
                    if outcome:
                        outcome['incident_id'] = canonical['id']
                    queue.db.execute('''UPDATE incidents SET fingerprint=?,first_ns=?,last_ns=?,count=?,status=?,completed_ns=?,
                      evidence=?,outcome=?,run_id=?,windows=?,window_ns=?,verified_ns=?,evidence_hash=?,investigated_hash=?,impact=? WHERE id=?''',
                      (identity, min(row['first_ns'] for row in group), latest['last_ns'], sum(row['count'] for row in group),
                       status, owner['completed_ns'], latest['evidence'], json.dumps(outcome) if outcome else None, owner['run_id'],
                       max(row['windows'] for row in group), max(row['window_ns'] for row in group),
                       max((row['verified_ns'] for row in group if row['verified_ns'] is not None), default=None),
                       latest['evidence_hash'], owner['investigated_hash'], owner['impact'], canonical['id']))
                    for row in group:
                        if row['id'] == canonical['id']:
                            continue
                        summary = f"Duplicate grouped into incident {canonical['id']}; no repair is claimed by grouping"
                        prior = json.loads(row['outcome']) if row['outcome'] else None
                        archived = {'incident_id': row['id'], 'status': 'filtered', 'summary': summary,
                                    'next_action': f"Follow incident {canonical['id']}", 'superseded_by': canonical['id'],
                                    'previous_outcome': prior, 'verification': ['Deterministic fingerprint consolidation; original row and issue link retained']}
                        queue.db.execute("UPDATE incidents SET fingerprint=?,status='filtered',completed_ns=?,impact=?,outcome=? WHERE id=?",
                                         ('superseded:'+canonical['id'], now, summary, json.dumps(archived), row['id']))
                        queue.db.execute('INSERT OR IGNORE INTO incident_supersession VALUES (?,?)', (row['id'],canonical['id']))
                        queue.db.execute('INSERT OR IGNORE INTO correlations SELECT ?,source,hash FROM correlations WHERE incident_id=?',
                                         (canonical['id'], row['id']))
        finally:
            queue.db.close()
        return {**result, 'applied': True, 'backup': str(backup), 'cursors': 'preserved', 'history_and_issue_links': 'preserved'}


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
    parser.add_argument('operation',choices=['status','show','migrate','regroup','retry','deliver-issues'])
    parser.add_argument('id',nargs='?')
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--expected-plan')
    args=parser.parse_args()
    if args.operation=='regroup':
        if args.id not in ('triage','cluster-wizard'):
            parser.error('regroup requires the triage or cluster-wizard job name')
        print(json.dumps(regroup(state_root()/args.id, apply=args.apply, expected_plan=args.expected_plan), indent=2)); return 0
    if args.apply or args.expected_plan:
        parser.error('--apply and --expected-plan are only for regroup')
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
