#!/usr/bin/env python3
"""Verify a harmless official-plugin session and emit only sanitized evidence."""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import stat
import tempfile
import urllib.parse
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--key-id', required=True)
    parser.add_argument('--expected-input', type=int, required=True)
    parser.add_argument('--expected-cached-input', type=int, required=True)
    parser.add_argument('--expected-output', type=int, required=True)
    parser.add_argument('--state-output', type=Path)
    args = parser.parse_args()
    path = Path.home() / '.codex/langfuse.json'
    assert not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == 0o600, 'JSON must be a regular user-only file'
    assert path.stat().st_uid == os.getuid(), 'JSON owner mismatch'
    config = json.loads(path.read_text())
    assert config['enabled'] is True and config['base_url'].startswith('https://'), 'Tracing configuration is not enabled'
    authorization = base64.b64encode((config['public_key'] + ':' + config['secret_key']).encode()).decode()

    def api(route):
        request = urllib.request.Request(config['base_url'].rstrip('/') + '/api/public/' + route,
            headers={'Authorization': 'Basic ' + authorization, 'User-Agent': 'ctx9-codex-langfuse/1.0'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    machine = (Path.home() / '.agents/state/machine-id').read_text().strip()
    metadata = json.loads((Path.home() / '.agents/settings/integrations/langfuse.json').read_text())
    expected_project = metadata.get('project', {'name': 'codex'})
    projects = api('projects')['data']
    assert len(projects) == 1 and projects[0]['name'] == expected_project['name'], 'Project scope mismatch'
    if expected_project.get('id'):
        assert projects[0]['id'] == expected_project['id'], 'Project identity mismatch'
    traces = api('traces?' + urllib.parse.urlencode({'sessionId': args.session_id, 'limit': 100}))['data']
    assert len(traces) >= 2, 'Two harmless turns required'
    assert all('machine:' + machine in t['tags'] and t['userId'] == getpass.getuser() for t in traces), 'Machine/user labels differ'
    observations = [o for t in traces for o in api('traces/' + t['id'])['observations']]
    generations = [o for o in observations if o['type'] == 'GENERATION']
    actual = (sum(o['usage']['input'] for o in generations),
              sum(o['usageDetails'].get('input_cached_tokens', 0) for o in generations),
              sum(o['usage']['output'] for o in generations))
    assert actual == (args.expected_input, args.expected_cached_input, args.expected_output), 'Provider and server totals differ'
    assert any(o['type'] == 'TOOL' for o in observations), 'Harmless tool span missing'
    assert generations and all(o.get('modelId') for o in generations), 'Unmatched model pricing'
    models = {o['modelId']: api('models/' + o['modelId']) for o in generations}
    for observation in generations:
        tier = next(t for t in models[observation['modelId']]['pricingTiers'] if t['name'] == observation['usagePricingTierName'])
        expected = sum(observation['usageDetails'].get(k, 0) * price for k, price in tier['prices'].items())
        assert abs(expected - observation['calculatedTotalCost']) < 1e-8, 'Server and matched model cost differ'
    record = {
        'accepted': False, 'tracing_ready': True, 'desktop_verified': False,
        'credentials_verified': True, 'trace_verified': True, 'cost_pricing_verified': True,
        'custody': 'official-local-json-0600', 'integration': 'official-codex-plugin',
        'key_id': args.key_id, 'project_id': projects[0]['id'],
        'verified_at': datetime.now(timezone.utc).isoformat(),
        'session_id': args.session_id, 'trace_ids': [t['id'] for t in traces],
        'input_tokens': actual[0], 'cached_input_tokens': actual[1], 'output_tokens': actual[2],
        'api_equivalent_cost_usd': sum(o['calculatedTotalCost'] for o in generations),
        'model_ids': sorted(models), 'remaining_acceptance': ['fresh desktop chat after restart'],
    }
    if args.state_output:
        state = json.loads(args.state_output.read_text())
        state.setdefault('machines', {}).setdefault(machine, {})['langfuse-coding-agent-api'] = record
        descriptor, name = tempfile.mkstemp(dir=args.state_output.parent, prefix='.langfuse-acceptance-')
        try:
            with os.fdopen(descriptor, 'w') as file:
                json.dump(state, file, indent=2, sort_keys=True)
                file.write('\n')
            os.replace(name, args.state_output)
        finally:
            Path(name).unlink(missing_ok=True)
    print(json.dumps({'machine': machine, **record}))


if __name__ == '__main__':
    main()
