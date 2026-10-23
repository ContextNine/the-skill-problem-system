import { execFileSync } from 'node:child_process';
import { relative } from 'node:path';

import { createLangfuseV1ClientFromEnvironment } from './langfuse-v1-client';
import { triageLangfuseQuality } from './trace-triage';

const DURATION_PATTERN = /^(\d+)(h|d)$/u;

function parseArgs(argv: string[]): { environment: string; sinceMs: number } {
  const values = new Map<string, string>();
  while (argv.length > 0) {
    const flag = argv.shift();
    const value = argv.shift();
    if (!flag?.startsWith('--') || !value?.length) throw new Error('Usage: triage-cli.ts --env ENVIRONMENT --since 7d');
    values.set(flag, value);
  }
  const environment = values.get('--env');
  if (!environment || !/^[a-z][a-z0-9-]{0,31}$/u.test(environment))
    throw new Error('--env must be a configured environment name.');
  const duration = DURATION_PATTERN.exec(values.get('--since') ?? '7d');
  if (!duration) throw new Error('--since must be a bounded duration such as 24h, 7d, or 30d.');
  const count = Number(duration[1]);
  const sinceMs = count * (duration[2] === 'd' ? 86_400_000 : 3_600_000);
  if (!Number.isSafeInteger(sinceMs) || sinceMs < 3_600_000 || sinceMs > 90 * 86_400_000)
    throw new Error('--since must be between 1 hour and 90 days.');
  return { environment, sinceMs };
}

function gitRelease(): string {
  try {
    return execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  } catch {
    return process.env.RELEASE_VERSION ?? process.env.GIT_COMMIT_SHA ?? 'unknown';
  }
}

async function main(): Promise<void> {
  const { environment, sinceMs } = parseArgs(process.argv.slice(2));
  const result = await triageLangfuseQuality({
    client: createLangfuseV1ClientFromEnvironment(),
    environment,
    cliRelease: gitRelease(),
    sinceMs,
  });
  process.stdout.write(
    [
      `Evaluation ID: ${result.manifest.evaluationId}`,
      `Requested UTC interval: [${result.manifest.requestedStart}, ${result.manifest.requestedEnd})`,
      `Evidence bundle: ${relative(process.cwd(), result.outputDir)}`,
      `Traces: ${result.manifest.traceCount}; observations: ${result.manifest.observationCount}; scores: ${result.manifest.scoreCount}`,
    ].join('\n') + '\n',
  );
}

main().catch((error: unknown) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
