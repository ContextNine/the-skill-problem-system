import type { TraceExportFilters } from './trace-export';
import { createLangfuseV1ClientFromEnvironment } from './langfuse-v1-client';
import { exportLangfuseTraces } from './trace-export';

function usage(): never {
  throw new Error(
    'Usage: cli.ts <export|audit> --env <ENVIRONMENT> [--since 24h] [--trace-id ID] [--workflow ID] [--action ID] [--agent ID] [--release ID] [--status success|error|cancelled] [--limit N]',
  );
}

function parseArgs(argv: string[]): { command: 'export' | 'audit'; filters: TraceExportFilters } {
  const command = argv.shift();
  if (command !== 'export' && command !== 'audit') usage();
  const values = new Map<string, string>();
  while (argv.length > 0) {
    const flag = argv.shift();
    if (!flag?.startsWith('--')) usage();
    const value = argv.shift();
    if (!value || value.startsWith('--')) usage();
    values.set(flag, value);
  }
  const environment = values.get('--env');
  if (!environment || !/^[a-z][a-z0-9-]{0,31}$/u.test(environment)) {
    throw new Error('--env must be a configured environment name.');
  }
  const status = values.get('--status');
  if (status && status !== 'success' && status !== 'error' && status !== 'cancelled') {
    throw new Error("--status must be 'success', 'error', or 'cancelled'.");
  }
  const limit = Number(values.get('--limit') ?? '100');
  if (!Number.isInteger(limit) || limit < 1 || limit > 1000)
    throw new Error('--limit must be an integer from 1 to 1000.');

  return {
    command,
    filters: {
      environment,
      since: values.get('--since') ?? (command === 'audit' ? '24h' : undefined),
      traceId: values.get('--trace-id'),
      workflow: values.get('--workflow'),
      action: values.get('--action'),
      agent: values.get('--agent'),
      release: values.get('--release'),
      status: status as TraceExportFilters['status'],
      limit,
    },
  };
}

async function main() {
  const { command, filters } = parseArgs(process.argv.slice(2));
  const result = await exportLangfuseTraces({ client: createLangfuseV1ClientFromEnvironment(), filters });
  process.stdout.write(`${result.summary}\nOutput: ${result.outputDir}\n`);
  if (command === 'audit') {
    const failures = result.traces.filter((item) => item.warnings.length > 0 || item.status !== 'success');
    process.stdout.write(`Audit findings: ${failures.length} trace(s) need review.\n`);
  }
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
