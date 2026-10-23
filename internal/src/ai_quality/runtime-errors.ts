import { createHash } from 'node:crypto';
import { writeFile, rename } from 'node:fs/promises';
import type { LangfuseV1Client } from './langfuse-v1-client';
import { createLangfuseV1ClientFromEnvironment } from './langfuse-v1-client';
import { redactTraceValue } from './redaction';

const hash = (value: string) => createHash('sha256').update(value).digest('hex');

export async function collectRuntimeErrors(options: {
  client: Pick<LangfuseV1Client, 'listErrorObservations'>;
  environment: string;
  start: string;
  end: string;
  service: string;
  repository: string;
}) {
  const population = await options.client.listErrorObservations(options);
  const events = [];
  for (const failure of population.observations) {
    const stamp = failure.startTime ?? failure.timestamp;
    if (!stamp || !Number.isFinite(Date.parse(stamp)))
      throw new Error('Runtime error has no valid timestamp; coverage incomplete.');
    if (Date.parse(stamp) < Date.parse(options.start) || Date.parse(stamp) >= Date.parse(options.end)) continue;
    if (failure.level?.toUpperCase() !== 'ERROR')
      throw new Error('Error observation filter was not honored; coverage incomplete.');
    const message = failure.statusMessage || failure.name || 'Langfuse runtime failure';
    events.push({
      source: 'langfuse',
      service: options.service,
      repository: options.repository,
      timestamp_ns: (BigInt(Date.parse(stamp)) * 1_000_000n).toString(),
      event_id: hash(`langfuse:${failure.id}`),
      correlation: failure.traceId ? [hash(failure.traceId)] : [],
      line: String(redactTraceValue(message)).slice(0, 6000),
    });
  }
  return {
    events,
    coverage: {
      source: `langfuse/${options.repository}`,
      complete: true,
      observations: population.observations.length,
      pages: population.pages,
    },
  };
}

export async function main() {
  const args = process.argv.slice(2);
  const flags = new Map<string, string>();
  for (let index = 0; index < args.length; index += 2) {
    const flag = args[index];
    const value = args[index + 1];
    if (!flag || !value) throw new Error('Missing runtime-error argument');
    flags.set(flag, value);
  }
  function required(flag: string) {
    const value = flags.get(flag);
    if (!value) throw new Error(`Missing ${flag}`);
    return value;
  }
  const start = required('--start');
  const end = required('--end');
  if (!Number.isFinite(Date.parse(start)) || !Number.isFinite(Date.parse(end)) || Date.parse(start) >= Date.parse(end))
    throw new Error('Invalid error collection interval');
  const result = await collectRuntimeErrors({
    client: createLangfuseV1ClientFromEnvironment(),
    environment: required('--env'),
    start,
    end,
    service: required('--service'),
    repository: required('--repository'),
  });
  const output = required('--output');
  const temporary = `${output}.${process.pid}.tmp`;
  await writeFile(temporary, JSON.stringify(result), { mode: 0o600, flag: 'wx' });
  await rename(temporary, output);
}
