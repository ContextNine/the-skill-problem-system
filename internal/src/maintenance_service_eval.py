"""Second-service detection using Testimonials' real readiness/error/logging path."""
import argparse
import json
import os
from pathlib import Path
import secrets
import time

import maintenance_runtime as runtime
from maintenance_live_eval import application, check, collector_module, digest, events_for, loki, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--testimonials', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    run_id = 'eval-service-' + time.strftime('%Y%m%d-%H%M%S', time.gmtime()) + '-' + secrets.token_hex(4)
    root = args.output_root / run_id
    root.mkdir(mode=0o700)
    ledger = {'run_id':run_id,'owner_pid':os.getpid()}
    repo = args.testimonials.resolve()
    hashes = {str(path):digest(path) for path in [Path(__file__),repo/'src/server.ts',repo/'src/store.ts',repo/'scripts/evals/maintenance-backend.ts',repo/'scripts/evals/build-maintenance.mjs']}
    report = {'run_id':run_id,'started_ns':time.time_ns(),'real_agent_invocations':0,'repair':'not_graded','passed':False,
              'source':{'testimonials_sha':run(['git','rev-parse','HEAD'],cwd=repo),'files':hashes},'limitations':['Synthetic unavailable dependency only','No production acceptance or repair grade']}
    runtime.atomic_json(root/'checkpoint.json',{'phase':'setup','report':report})
    queue = runtime.Queue(root/'queue.sqlite3')
    try:
        artifact = root/'service.mjs'
        run([args.node,'scripts/evals/build-maintenance.mjs',artifact],cwd=repo,env={'PATH':'/usr/bin:/bin','HOME':str(Path.home()),'NODE_ENV':'test','ENVIRONMENT':'test'})
        collector, path = collector_module()
        report['source']['collector_sha256'] = digest(path)
        with loki(root,run_id,ledger) as endpoint:
            config = {'test_only':True,'loki':{'test_url':endpoint,'namespace':'test','service':'loki','port':3100},
                      'services':[{'namespace':run_id,'app':'testimonials','id':'testimonials','workspace':'testimonials'}]}
            start = time.time_ns()
            with application(root,args.node,artifact,run_id,endpoint,ledger,'service',app_label='testimonials') as (call,identity):
                empty = events_for(collector,config,run_id,start,time.time_ns())
                check(not empty,'Initial service window was not empty')
                status, body = call({})
                check(status==500 and body.get('error',{}).get('code')=='internal-error','Real service operation did not fail')
                report['operation']={'status':status,'body':body,'identity':identity}
            end = time.time_ns()
            events = events_for(collector,config,run_id,start,end)
            check(len(events)==1 and 'internal-error' in events[0]['line'],'Actual service error telemetry missing')
            check(events[0]['service']=='testimonials' and events[0]['repository']=='testimonials','Second-service ownership routing failed')
            coverage=[{'source':'loki/'+run_id,'complete':True,'cursor_ns':end}]
            queue.collect(events,end,coverage=coverage,source_cursors={coverage[0]['source']:end})
            check(len(queue.pending())==1 and queue.pending()[0]['count']==1,'Service grouping failed')
            queue.collect(events_for(collector,config,run_id,start,end),end+1)
            check(queue.pending()[0]['count']==1,'Service replay duplicated an occurrence')
            runtime.atomic_json(root/'telemetry.json',{'start_ns':start,'end_ns':end,'events':events,'coverage':coverage})
            report['detection']={'passed':True,'events':1,'groups':1,'routing':'passed','replay':'passed',
                                 'path':'real Testimonials readyz -> real pg connection refusal inside isolated namespace -> actual server catch/log -> private Loki -> actual collector/queue'}
    except BaseException as error:
        report['error']=f'{type(error).__name__}: {error}'
    finally:
        queue.db.close()
        report['cleanup']={'container_removed':ledger.get('container',{}).get('removed',False),
            'application_exited':all(item.get('exited') and item.get('socket_removed') and item.get('shipper_exited') for item in ledger.get('applications',[])),
            'immutable_sources_unchanged':all(digest(path)==value for path,value in hashes.items())}
        report['finished_ns']=time.time_ns();report['runtime_seconds']=round((report['finished_ns']-report['started_ns'])/1e9,2)
        report['passed']=report.get('detection',{}).get('passed',False) and all(report['cleanup'].values()) and 'error' not in report
        runtime.atomic_json(root/'report.json',report)
        runtime.atomic_json(root/'checkpoint.json',{'phase':'complete','passed':report['passed']})
    print(json.dumps({'run_id':run_id,'passed':report['passed'],'error':report.get('error'),'report':str(root/'report.json')}),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
