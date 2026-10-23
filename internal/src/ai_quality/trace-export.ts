import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import type { LangfuseObservation, LangfuseTrace, LangfuseTraceReadClient } from './langfuse-v1-client';
import { redactTraceValue } from './redaction';

export type TraceStatus = 'success' | 'error' | 'cancelled';

export type TraceExportFilters = {
  environment: string;
  since?: string;
  traceId?: string;
  workflow?: string;
  action?: string;
  agent?: string;
  release?: string;
  status?: TraceStatus;
  limit: number;
};

export type ExportedTrace = {
  trace: LangfuseTrace;
  observations: LangfuseObservation[];
  status: TraceStatus;
  warnings: string[];
  markdown: string;
  fileName: string;
};

function timestampOf(value: LangfuseTrace | LangfuseObservation): string {
  return value.startTime ?? value.timestamp ?? value.createdAt ?? value.updatedAt ?? '';
}

function metadataOf(value: LangfuseTrace | LangfuseObservation): Record<string, unknown> {
  return value.metadata && typeof value.metadata === 'object' ? value.metadata : {};
}

function observationType(value: LangfuseObservation): string {
  return String(value.type ?? value.asType ?? '').toLowerCase();
}

function traceStatus(trace: LangfuseTrace, observations: LangfuseObservation[]): TraceStatus {
  const values = [trace, ...observations];
  if (values.some((value) => String(value.level ?? '').toUpperCase() === 'ERROR')) return 'error';
  if (values.some((value) => /cancel/i.test(String(value.statusMessage ?? '')))) return 'cancelled';
  return 'success';
}

export function collectInstrumentationWarnings(trace: LangfuseTrace, observations: LangfuseObservation[]): string[] {
  const warnings: string[] = [];
  if (!trace.environment) warnings.push('Trace has no environment.');
  if (!trace.release && !trace.version && !metadataOf(trace).release) warnings.push('Trace has no release.');
  if (observations.length === 0) warnings.push('Trace has no observations.');

  for (const observation of observations) {
    if (observationType(observation) !== 'generation') continue;
    const metadata = metadataOf(observation);
    const promptId = metadata.promptId ?? observation.promptName ?? observation.prompt?.name;
    const promptRevision = metadata.promptRevision ?? observation.promptVersion ?? observation.prompt?.version;
    if (!promptId || promptRevision === undefined) {
      warnings.push(`Generation ${observation.id ?? observation.name ?? 'unknown'} has no prompt ID/revision.`);
    }
    if (observation.input === undefined || observation.output === undefined) {
      warnings.push(`Generation ${observation.id ?? observation.name ?? 'unknown'} has incomplete input/output.`);
    }
  }

  return [...new Set(warnings)];
}

function formatJson(value: unknown): string {
  return JSON.stringify(redactTraceValue(value), null, 2) ?? 'null';
}

function safeName(value: string): string {
  return (
    value
      .replace(/[^a-zA-Z0-9._-]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 100) || 'trace'
  );
}

function renderObservationTree(observations: LangfuseObservation[]): string {
  const byId = new Map(observations.map((observation) => [observation.id, observation]));
  const depthOf = (observation: LangfuseObservation): number => {
    let depth = 0;
    let parentId = observation.parentObservationId ?? observation.parentId;
    const seen = new Set<string>();
    while (parentId && byId.has(parentId) && !seen.has(parentId)) {
      seen.add(parentId);
      depth += 1;
      parentId = byId.get(parentId)?.parentObservationId ?? byId.get(parentId)?.parentId;
    }
    return depth;
  };

  return observations
    .map((observation) => {
      const duration =
        observation.latency ??
        (observation.startTime && observation.endTime
          ? `${Date.parse(observation.endTime) - Date.parse(observation.startTime)}ms`
          : 'unknown');
      return `${'  '.repeat(depthOf(observation))}- ${timestampOf(observation) || 'unknown time'} — ${observation.name ?? 'unnamed'} (${observationType(observation) || 'observation'}, ${duration})`;
    })
    .join('\n');
}

export function renderTraceMarkdown(args: {
  trace: LangfuseTrace;
  observations: LangfuseObservation[];
  warnings: string[];
  baseUrl: string;
}): string {
  const { trace, observations, warnings } = args;
  const metadata = metadataOf(trace);
  const traceLink = trace.projectId
    ? `${args.baseUrl}/project/${trace.projectId}/traces/${trace.id}`
    : `${args.baseUrl}/trace/${trace.id}`;
  const lines = [
    `# ${trace.name ?? 'AI trace'}`,
    '',
    `- Environment: ${trace.environment ?? metadata.environment ?? 'unknown'}`,
    `- Release: ${trace.release ?? trace.version ?? metadata.release ?? 'unknown'}`,
    `- Trace ID: ${trace.id ?? 'unknown'}`,
    `- AI run ID: ${metadata.aiRunId ?? 'n/a'}`,
    `- Thread/session ID: ${trace.sessionId ?? metadata.threadId ?? 'n/a'}`,
    `- Status: ${traceStatus(trace, observations)}`,
    `- Duration: ${trace.latency ?? trace.duration ?? 'unknown'}`,
    `- Langfuse: ${traceLink}`,
    '',
  ];

  if (warnings.length > 0) {
    lines.push('## Instrumentation warnings', '', ...warnings.map((warning) => `- ${warning}`), '');
  }

  lines.push(
    '## Root input',
    '',
    '~~~json',
    formatJson(trace.input),
    '~~~',
    '',
    '## Root output',
    '',
    '~~~json',
    formatJson(trace.output),
    '~~~',
    '',
    '## Chronological observation tree',
    '',
    renderObservationTree(observations) || '_No observations._',
    '',
  );

  observations.forEach((observation, index) => {
    const metadata = metadataOf(observation);
    lines.push(
      `### ${index + 1}. ${observation.name ?? observation.id ?? 'Observation'}`,
      '',
      `- Type: ${observationType(observation) || 'unknown'}`,
      `- ID: ${observation.id ?? 'unknown'}`,
      `- Parent: ${observation.parentObservationId ?? observation.parentId ?? 'root'}`,
      `- Model/provider: ${observation.model ?? metadata.actualModel ?? 'n/a'} / ${metadata.actualProvider ?? metadata.requestedProvider ?? 'n/a'}`,
      `- Prompt: ${metadata.promptId ?? observation.promptName ?? observation.prompt?.name ?? 'n/a'} @ ${metadata.promptRevision ?? observation.promptVersion ?? observation.prompt?.version ?? 'n/a'}`,
      `- Rendered input hash: ${metadata.renderedInputHash ?? 'n/a'}`,
      `- Usage: ${formatJson(observation.usageDetails ?? observation.usage ?? null)}`,
      `- Cost: ${formatJson(observation.costDetails ?? observation.calculatedTotalCost ?? null)}`,
      `- Status/error: ${observation.level ?? 'DEFAULT'} — ${observation.statusMessage ?? 'none'}`,
      '',
      'Input:',
      '',
      '~~~json',
      formatJson(observation.input),
      '~~~',
      '',
      'Output:',
      '',
      '~~~json',
      formatJson(observation.output),
      '~~~',
      '',
      'Metadata:',
      '',
      '~~~json',
      formatJson(metadata),
      '~~~',
      '',
    );
  });

  return `${lines.join('\n')}\n`;
}

function matchesFilter(
  trace: LangfuseTrace,
  observations: LangfuseObservation[],
  filters: TraceExportFilters,
): boolean {
  const searchable = JSON.stringify({ name: trace.name, metadata: metadataOf(trace), tags: trace.tags }).toLowerCase();
  if (filters.workflow && !searchable.includes(filters.workflow.toLowerCase())) return false;
  if (filters.action && !searchable.includes(filters.action.toLowerCase())) return false;
  if (filters.agent && !searchable.includes(filters.agent.toLowerCase())) return false;
  if (filters.release) {
    const release = trace.release ?? trace.version ?? metadataOf(trace).release;
    if (release !== filters.release) return false;
  }
  return !filters.status || traceStatus(trace, observations) === filters.status;
}

function parseDuration(value: string): number {
  const match = /^(\d+)(h|d|w)$/.exec(value);
  if (!match) throw new Error(`Invalid duration '${value}'. Use hours, days, or weeks, for example 24h, 7d, 2w.`);
  const count = Number(match[1]);
  const multiplier = match[2] === 'h' ? 3_600_000 : match[2] === 'd' ? 86_400_000 : 604_800_000;
  return count * multiplier;
}

export async function exportLangfuseTraces(args: {
  client: LangfuseTraceReadClient;
  filters: TraceExportFilters;
  outputRoot?: string;
  now?: Date;
}): Promise<{ outputDir: string; traces: ExportedTrace[]; summary: string }> {
  const now = args.now ?? new Date();
  const fromTimestamp = args.filters.since
    ? new Date(now.getTime() - parseDuration(args.filters.since)).toISOString()
    : undefined;
  const summaries = args.filters.traceId
    ? [await args.client.getTrace(args.filters.traceId)]
    : await args.client.listTraces({
        environment: args.filters.environment,
        fromTimestamp,
        toTimestamp: now.toISOString(),
        release: args.filters.release,
        limit: Math.max(args.filters.limit * 3, args.filters.limit),
      });

  const exported: ExportedTrace[] = [];
  for (const summary of summaries) {
    if (exported.length >= args.filters.limit) break;
    const trace = summary.id ? await args.client.getTrace(summary.id) : summary;
    const observations = (trace.id ? await args.client.listObservations(trace.id) : [])
      .map((observation) => redactTraceValue(observation) as LangfuseObservation)
      .sort((a, b) => timestampOf(a).localeCompare(timestampOf(b)) || String(a.id).localeCompare(String(b.id)));
    const redactedTrace = redactTraceValue(trace) as LangfuseTrace;
    if (!matchesFilter(redactedTrace, observations, args.filters)) continue;
    const status = traceStatus(redactedTrace, observations);
    const warnings = collectInstrumentationWarnings(redactedTrace, observations);
    const operation = safeName(redactedTrace.name ?? 'trace');
    const timestamp = safeName(timestampOf(redactedTrace).replace(/[:.]/g, '-'));
    const fileName = `${timestamp}--${operation}--${safeName(redactedTrace.id ?? 'unknown')}.md`;
    exported.push({
      trace: redactedTrace,
      observations,
      status,
      warnings,
      fileName,
      markdown: renderTraceMarkdown({
        trace: redactedTrace,
        observations,
        warnings,
        baseUrl: args.client.baseUrl,
      }),
    });
  }

  const filterHash = createHash('sha256').update(JSON.stringify(args.filters)).digest('hex').slice(0, 8);
  const exportId = `${now.toISOString().replace(/[:.]/g, '-')}-${args.filters.environment}-${filterHash}`;
  const outputDir = path.resolve(args.outputRoot ?? '.logs/ai-traces', exportId);
  const tracesDir = path.join(outputDir, 'traces');
  await mkdir(tracesDir, { recursive: true });
  await Promise.all(exported.map((item) => writeFile(path.join(tracesDir, item.fileName), item.markdown, 'utf8')));

  const warningCount = exported.reduce((count, item) => count + item.warnings.length, 0);
  const errorCount = exported.filter((item) => item.status === 'error').length;
  const summary = [
    '# AI trace export',
    '',
    `- Export ID: ${exportId}`,
    `- Environment: ${args.filters.environment}`,
    `- Traces: ${exported.length}`,
    `- Errors: ${errorCount}`,
    `- Instrumentation warnings: ${warningCount}`,
    '',
    ...exported.map(
      (item) =>
        `- [${item.trace.name ?? item.trace.id}](traces/${item.fileName}) — ${item.status}; ${item.warnings.length} warning(s)`,
    ),
    '',
  ].join('\n');
  const manifest = {
    schemaVersion: 1,
    exportId,
    createdAt: now.toISOString(),
    filters: args.filters,
    traceCount: exported.length,
    errorCount,
    warningCount,
    traces: exported.map((item) => ({
      id: item.trace.id,
      name: item.trace.name,
      status: item.status,
      file: `traces/${item.fileName}`,
    })),
  };
  await Promise.all([
    writeFile(path.join(outputDir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8'),
    writeFile(path.join(outputDir, 'summary.md'), `${summary}\n`, 'utf8'),
  ]);

  return { outputDir, traces: exported, summary };
}
