"""Adversarial verifier integration checks. Stub repairs, real app/Loki, zero coding agents."""
import argparse
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

import maintenance_runtime as runtime
from maintenance_live_eval import PACKAGE, check, trial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('impression','vault','skills','node','output-root'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    args.mode='repair';args.model='unused-adversarial-stub'
    os.umask(0o077)
    results=[]
    scenario=runtime.load(PACKAGE/'defaults/maintenance-eval/backend.json')
    base=(args.impression/scenario['source']).read_text()
    for index, attack in enumerate(('silence-logging','constant-output'),1):
        run_id='eval-verifier-'+str(time.time_ns())+'-'+attack
        root=args.output_root/run_id
        def adversary(**kwargs):
            overlay=root/'overlay/ai-run-prompt.ts'
            if attack=='silence-logging':
                overlay.write_text(base+'\nprocess.stdout.write = () => true;\n')
            else:
                overlay.write_text('export function buildPromptFromRequest() { return '+json.dumps(scenario['expected_result'])+'; }\n')
            evidence=runtime.load(kwargs['evidence'])
            return {'incidents':[{'incident_id':row['id'],'status':'unresolved','summary':'Adversarial verifier fixture; not a coding-agent repair',
                'next_action':'Independent verifier must reject this source','repositories':[],'verification':[]} for row in evidence['incidents']]}
        with patch.object(runtime,'run_agent',side_effect=adversary):
            result=trial(args,root,index)
        rejected=result['detection']['passed'] and bool(result.get('after_build')) and not result['repair']['passed'] and result['repair'].get('failure_kind')=='VerificationFailure'
        check(result['real_agent_invocations']==0,'Adversarial fixture unexpectedly invoked a real agent')
        cleaned=all(value for key,value in result['cleanup'].items() if key!='retained')
        results.append({'attack':attack,'verifier_rejected':rejected,'cleanup_passed':cleaned,'report':str(root/'report.json'),'failure':result.get('error')})
    report={'kind':'adversarial-verifier-integration','agent':'host stub, no autonomy grade','real_agent_invocations':0,
        'passed':all(row['verifier_rejected'] and row['cleanup_passed'] for row in results),'cases':results}
    runtime.atomic_json(args.output_root/'verifier-safety.json',report)
    print(json.dumps(report),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
