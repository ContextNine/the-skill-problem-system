"""Runs inside the browser eval namespace, using the approved task-scoped CLI."""
import json
import os
from pathlib import Path
import re
import subprocess
import time

server = subprocess.Popen(['/opt/node', '/browser.cjs'])
cli = ['/opt/node', '/playwright-cli/playwright-cli.js', '-s=' + os.environ['K3S_EVAL_RUN_ID']]


def invoke(arguments):
    result = subprocess.run(cli + arguments, cwd='/tmp', capture_output=True, text=True, timeout=45)
    print(result.stdout, flush=True)
    if result.returncode or '### Error' in result.stdout:
        print(result.stderr, flush=True)
        raise RuntimeError('Owned Playwright CLI operation failed')
    return result.stdout


try:
    time.sleep(1)
    config = json.loads(Path('/browser-config.json').read_text())
    config['browser']['contextOptions'] = {'extraHTTPHeaders': {'Authorization': 'Bearer ' + os.environ['K3S_EVAL_AUTH']}}
    # Only this namespace's tmpfs holds the synthetic browser header. It is not retained.
    Path('/tmp/browser-config.json').write_text(json.dumps(config))
    invoke(['open', '--config=/tmp/browser-config.json'])
    url = 'http://127.0.0.1:18482/eval/' + os.environ['K3S_EVAL_RUN_ID']
    setup = """async page => {
      await page.goto(__URL__);
      await page.waitForFunction(() => typeof window.onerror === 'function');
    }""".replace('__URL__', json.dumps(url))
    invoke(['run-code', setup])
    invoke(['snapshot', '--filename=/tmp/browser-snapshot.yml'])
    snapshot = Path('/tmp/browser-snapshot.yml').read_text()
    print(snapshot, flush=True)
    button = re.search(r'button "Run browser case" \[ref=(e\d+)\]', snapshot)
    if not button:
        raise RuntimeError('Expected browser action missing from snapshot')
    invoke(['run-code', """async page => {
      const pageError = page.waitForEvent('pageerror');
      const response = page.waitForResponse(response => response.url().endsWith('/scenario/browser-report'));
      await page.getByRole('button', {name: 'Run browser case'}).click();
      const [error, report] = await Promise.all([pageError, response]);
      const body = await report.json();
      if (report.status() !== 200 || body.validationErrors || body.serverError) throw new Error('Actual client action failed');
      return {browser_exception: error.message, forwarding_status: report.status(), actual_action_accepted: true};
    }"""])
finally:
    try:
        invoke(['close'])
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
