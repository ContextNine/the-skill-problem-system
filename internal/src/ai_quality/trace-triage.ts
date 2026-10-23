import { createHash } from 'node:crypto';
import { chmod, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { z } from 'zod';

import type { LangfuseObservation, LangfuseScore, LangfuseTrace, LangfuseTraceReadClient } from './langfuse-v1-client';
import type { TraceStatus } from './trace-export';
import { redactTraceValue } from './redaction';
import { collectInstrumentationWarnings, renderTraceMarkdown } from './trace-export';

const DAY_MS = 86_400_000;
const MAX_TRACES = 10_000;
const PAGE_SIZE = 100;
const DETAIL_CONCURRENCY = 4;
const DOSSIER_LIMIT = 100;
export const TRACE_TRIAGE_ALGORITHM_REVISION = '1';

const countMapSchema = z.record(z.string(), z.number().int().nonnegative());
const distributionSchema = z.object({
  count: z.number().int().nonnegative(),
  p50: z.number().nullable(),
  p95: z.number().nullable(),
  p99: z.number().nullable(),
});
const metricPointSchema = z.object({
  traceId: z.string(),
  value: z.number(),
  name: z.string(),
  timestamp: z.string(),
});
const fingerprintSchema = z.object({
  fingerprint: z.string(),
  count: z.number().int().positive(),
  repeated: z.boolean(),
  traceIds: z.array(z.string()),
});

export const TraceTriageEvidenceSchema = z.object({
  schemaVersion: z.literal(1),
  evaluationId: z.string(),
  environment: z.string().min(1),
  requestedInterval: z.object({ start: z.string(), end: z.string() }),
  retainedInterval: z.object({ earliest: z.string().nullable(), latest: z.string().nullable() }),
  completeness: z.object({
    complete: z.boolean(),
    truncated: z.boolean(),
    pagesRead: z.number().int().nonnegative(),
    reportedTotalItems: z.number().int().nonnegative().nullable(),
    warnings: z.array(z.string()),
  }),
  totals: z.object({
    traces: z.number().int().nonnegative(),
    observations: z.number().int().nonnegative(),
    scores: z.number().int().nonnegative(),
  }),
  tracesBy: z.object({
    status: countMapSchema,
    workflow: countMapSchema,
    agent: countMapSchema,
    action: countMapSchema,
    release: countMapSchema,
    model: countMapSchema,
    provider: countMapSchema,
  }),
  reliability: z.object({
    errorRate: z.number().nullable(),
    cancellationRate: z.number().nullable(),
    errorFingerprints: z.array(fingerprintSchema),
    toolFailureFingerprints: z.array(fingerprintSchema),
    retries: z.number().int().nonnegative(),
    fallbacks: z.number().int().nonnegative(),
    toolFailures: z.number().int().nonnegative(),
  }),
  latency: z.object({
    tracesMs: distributionSchema,
    generationsMs: distributionSchema,
    toolsMsByTool: z.record(z.string(), distributionSchema),
    slowestTraces: z.array(metricPointSchema),
    slowestGenerations: z.array(metricPointSchema),
    slowestTools: z.array(metricPointSchema),
  }),
  cost: z.object({
    totalUsd: z.number().nullable(),
    perTraceUsd: distributionSchema,
    costliestTraces: z.array(metricPointSchema),
  }),
  tokens: z.object({
    input: z.number().nullable(),
    output: z.number().nullable(),
    total: z.number().nullable(),
    largestTraces: z.array(metricPointSchema),
  }),
  scores: z.object({
    feedback: z.object({
      positive: z.number().int().nonnegative(),
      negative: z.number().int().nonnegative(),
      cleared: z.number().int().nonnegative(),
    }),
    evaluators: z.record(z.string(), countMapSchema),
  }),
  instrumentation: z.object({
    completenessRate: z.number().nullable(),
    gaps: countMapSchema,
  }),
  selectedTraces: z.array(
    z.object({
      traceId: z.string(),
      status: z.enum(['success', 'error', 'cancelled']),
      file: z.string(),
      reasons: z.array(z.string()),
    }),
  ),
  omittedDossiersByReason: countMapSchema,
});

export const TraceTriageManifestSchema = z.object({
  schemaVersion: z.literal(1),
  evaluationId: z.string(),
  environment: z.string().min(1),
  requestedStart: z.string(),
  requestedEnd: z.string(),
  retainedEarliest: z.string().nullable(),
  retainedLatest: z.string().nullable(),
  traceCount: z.number().int().nonnegative(),
  observationCount: z.number().int().nonnegative(),
  scoreCount: z.number().int().nonnegative(),
  completeness: z.object({ complete: z.boolean(), truncated: z.boolean(), warnings: z.array(z.string()) }),
  langfuseOrigin: z.string(),
  triageAlgorithmRevision: z.string(),
  fileHashes: z.record(z.string(), z.string()),
  cliRelease: z.string(),
  createdAt: z.string(),
});

export type TraceTriageEvidence = z.infer<typeof TraceTriageEvidenceSchema>;
export type TraceTriageManifest = z.infer<typeof TraceTriageManifestSchema>;

type DetailedTrace = {
  trace: LangfuseTrace;
  observations: LangfuseObservation[];
  scores: LangfuseScore[];
  timestamp: string;
  status: TraceStatus;
  durationMs?: number;
  costUsd?: number;
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  errorFingerprints: string[];
  toolFailureFingerprints: string[];
  warnings: string[];
  models: string[];
  providers: string[];
  workflow: string;
  agent: string;
  action: string;
  release: string;
  retries: number;
  fallbacks: number;
  hasNegativeScore: boolean;
  hasFailingEvaluator: boolean;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringValue(...values: unknown[]): string | undefined {
  return values.find((value): value is string => typeof value === 'string' && value.trim().length > 0)?.trim();
}

function numberValue(value: unknown): number | undefined {
  const number = typeof value === 'number' ? value : typeof value === 'string' && value.trim() ? Number(value) : NaN;
  return Number.isFinite(number) ? number : undefined;
}

function timestampOf(value: LangfuseTrace | LangfuseObservation): string {
  return stringValue(value.startTime, value.timestamp, value.createdAt, value.updatedAt) ?? '';
}

function metadataOf(value: LangfuseTrace | LangfuseObservation): Record<string, unknown> {
  return value.metadata ?? {};
}

function observationType(value: LangfuseObservation): string {
  return stringValue(value.type, value.asType)?.toLowerCase() ?? '';
}

function durationBetween(start: unknown, end: unknown): number | undefined {
  if (typeof start !== 'string' || typeof end !== 'string') return undefined;
  const duration = Date.parse(end) - Date.parse(start);
  return Number.isFinite(duration) && duration >= 0 ? duration : undefined;
}

function legacyLatencyMs(value: unknown): number | undefined {
  const seconds = numberValue(value);
  return seconds === undefined || seconds < 0 ? undefined : seconds * 1_000;
}

function observationDurationMs(observation: LangfuseObservation): number | undefined {
  return durationBetween(observation.startTime, observation.endTime) ?? legacyLatencyMs(observation.latency);
}

function traceDurationMs(trace: LangfuseTrace, observations: LangfuseObservation[]): number | undefined {
  const explicit = durationBetween(trace.startTime ?? trace.timestamp, trace.endTime);
  if (explicit !== undefined) return explicit;
  const starts = observations.map(timestampOf).filter(Boolean).map(Date.parse).filter(Number.isFinite);
  const ends = observations
    .map((observation) => observation.endTime)
    .filter((value): value is string => typeof value === 'string')
    .map(Date.parse)
    .filter(Number.isFinite);
  if (starts.length > 0 && ends.length > 0) return Math.max(...ends) - Math.min(...starts);
  return legacyLatencyMs(trace.latency ?? trace.duration);
}

function readMetric(record: Record<string, unknown> | null, keys: string[]): number | undefined {
  if (!record) return undefined;
  for (const key of keys) {
    const value = numberValue(record[key]);
    if (value !== undefined) return value;
  }
  return undefined;
}

function usageOf(observation: LangfuseObservation): { input?: number; output?: number; total?: number } {
  const usage = asRecord(observation.usageDetails) ?? asRecord(observation.usage);
  const input = readMetric(usage, ['input', 'inputTokens', 'promptTokens', 'prompt_tokens']);
  const output = readMetric(usage, ['output', 'outputTokens', 'completionTokens', 'completion_tokens']);
  const total =
    readMetric(usage, ['total', 'totalTokens', 'total_tokens']) ??
    (input !== undefined || output !== undefined ? (input ?? 0) + (output ?? 0) : undefined);
  return { input, output, total };
}

function observationCost(observation: LangfuseObservation): number | undefined {
  return (
    readMetric(asRecord(observation.costDetails), ['total', 'totalCost', 'calculatedTotalCost']) ??
    numberValue(observation.totalCost) ??
    numberValue(observation.calculatedTotalCost)
  );
}

function isGeneration(observation: LangfuseObservation): boolean {
  return observationType(observation) === 'generation';
}

function isTool(observation: LangfuseObservation): boolean {
  const metadata = metadataOf(observation);
  const type = observationType(observation);
  const name = stringValue(metadata.toolName, metadata.tool, observation.name)?.toLowerCase() ?? '';
  return (
    type === 'tool' ||
    metadata.toolName !== undefined ||
    metadata.tool !== undefined ||
    /(^|[.:/_-])tool([.:/_-]|$)/.test(name)
  );
}

function statusOf(trace: LangfuseTrace, observations: LangfuseObservation[]): TraceStatus {
  const values = [trace, ...observations];
  if (values.some((value) => /cancel/i.test(stringValue(value.statusMessage) ?? ''))) return 'cancelled';
  if (values.some((value) => stringValue(value.level)?.toUpperCase() === 'ERROR')) return 'error';
  return 'success';
}

export function normalizeErrorFingerprint(value: string): string {
  return value
    .toLowerCase()
    .replace(/https?:\/\/\S+/g, '<url>')
    .replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, '<id>')
    .replace(/\b\d+(?:\.\d+)?\b/g, '<n>')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 240);
}

function errorFingerprints(trace: LangfuseTrace, observations: LangfuseObservation[], status: TraceStatus): string[] {
  if (status === 'success') return [];
  const messages = [trace, ...observations]
    .filter((value) =>
      status === 'cancelled'
        ? /cancel/i.test(stringValue(value.statusMessage) ?? '')
        : stringValue(value.level)?.toUpperCase() === 'ERROR',
    )
    .map((value) => stringValue(value.statusMessage))
    .filter((value): value is string => Boolean(value));
  return [...new Set((messages.length > 0 ? messages : [status]).map(normalizeErrorFingerprint))];
}

function scoreValue(score: LangfuseScore): unknown {
  return score.value ?? score.stringValue;
}

function scoreLabel(score: LangfuseScore): string {
  const value = scoreValue(score);
  if (typeof value === 'boolean') return String(value);
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : 'unknown';
  return typeof value === 'string' && value.trim() ? value.trim().toLowerCase() : 'unknown';
}

function isFeedback(score: LangfuseScore): boolean {
  return /feedback|helpful/i.test(score.name);
}

function isFailingScore(score: LangfuseScore): boolean {
  const value = scoreValue(score);
  if (typeof value === 'boolean') return !value;
  if (typeof value === 'number') return value <= 0;
  return (
    typeof value === 'string' && /^(down|fail|failed|false|negative|incorrect|not[_ -]?helpful)$/i.test(value.trim())
  );
}

function isEmpty(value: unknown): boolean {
  if (value === undefined || value === null || value === '') return true;
  if (Array.isArray(value)) return value.length === 0;
  const record = asRecord(value);
  return record ? Object.keys(record).length === 0 : false;
}

function addCount(target: Record<string, number>, key: string): void {
  target[key || 'unknown'] = (target[key || 'unknown'] ?? 0) + 1;
}

export function nearestRank(values: number[], percentile: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.max(0, Math.ceil(percentile * sorted.length) - 1)] ?? null;
}

function distribution(values: number[]): z.infer<typeof distributionSchema> {
  return {
    count: values.length,
    p50: nearestRank(values, 0.5),
    p95: nearestRank(values, 0.95),
    p99: nearestRank(values, 0.99),
  };
}

function sumKnown(values: Array<number | undefined>): number | null {
  const known = values.filter((value): value is number => value !== undefined);
  return known.length > 0 ? known.reduce((sum, value) => sum + value, 0) : null;
}

function stableHash(value: string): string {
  return createHash('sha256').update(value).digest('hex');
}

function safeName(value: string): string {
  return (
    value
      .replace(/[^a-zA-Z0-9._-]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 100) || 'trace'
  );
}

function langfuseOrigin(baseUrl: string): string {
  const parsed = new URL(baseUrl);
  return parsed.origin;
}

async function mapWithConcurrency<T, TResult>(
  items: T[],
  limit: number,
  worker: (item: T) => Promise<TResult>,
): Promise<TResult[]> {
  const results = new Array<TResult>(items.length);
  let cursor = 0;
  await Promise.all(
    Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (cursor < items.length) {
        const index = cursor;
        cursor += 1;
        results[index] = await worker(items[index]!);
      }
    }),
  );
  return results;
}

export async function collectTraceSummaries(args: {
  client: LangfuseTraceReadClient;
  environment: string;
  start: string;
  end: string;
}): Promise<{ traces: LangfuseTrace[]; pagesRead: number; reportedTotalItems: number | null }> {
  const traces = new Map<string, LangfuseTrace>();
  let page = 1;
  let pagesRead = 0;
  let reportedTotalItems: number | null = null;
  while (true) {
    if (page > 101) throw new Error('Langfuse page budget exhausted; triage is incomplete.');
    const response = await args.client.listTracePage({
      environment: args.environment,
      fromTimestamp: args.start,
      toTimestamp: args.end,
      page,
      limit: PAGE_SIZE,
    });
    pagesRead += 1;
    reportedTotalItems = response.meta.totalItems ?? reportedTotalItems;
    if ((response.meta.totalItems ?? 0) > MAX_TRACES) {
      throw new Error(`Langfuse returned more than the 10,000-trace safety maximum. Triage is incomplete.`);
    }
    for (const trace of response.data) {
      traces.set(trace.id, trace);
      if (traces.size > MAX_TRACES) {
        throw new Error(`Langfuse returned more than the 10,000-trace safety maximum. Triage is incomplete.`);
      }
    }
    const totalPages = response.meta.totalPages;
    if (
      response.data.length === 0 ||
      (totalPages !== undefined ? page >= totalPages : response.data.length < PAGE_SIZE)
    )
      break;
    page += 1;
  }
  if (reportedTotalItems !== null && traces.size < reportedTotalItems)
    throw new Error('Langfuse returned fewer traces than reported; triage is incomplete.');
  return { traces: [...traces.values()], pagesRead, reportedTotalItems };
}

function detailFrom(trace: LangfuseTrace, observations: LangfuseObservation[], scores: LangfuseScore[]): DetailedTrace {
  const redactedTrace = redactTraceValue(trace) as LangfuseTrace;
  const redactedObservations = (redactTraceValue(observations) as LangfuseObservation[]).sort(
    (left, right) => timestampOf(left).localeCompare(timestampOf(right)) || left.id.localeCompare(right.id),
  );
  const redactedScores = redactTraceValue(scores) as LangfuseScore[];
  const traceMetadata = metadataOf(redactedTrace);
  const generations = redactedObservations.filter(isGeneration);
  const models = [
    ...new Set(
      generations
        .map((item) => stringValue(item.model, item.providedModelName, metadataOf(item).actualModel))
        .filter((value): value is string => Boolean(value)),
    ),
  ];
  const providers = [
    ...new Set(
      generations
        .map((item) =>
          stringValue(metadataOf(item).actualProvider, metadataOf(item).requestedProvider, metadataOf(item).provider),
        )
        .filter((value): value is string => Boolean(value)),
    ),
  ];
  const status = statusOf(redactedTrace, redactedObservations);
  const usage = generations.map(usageOf);
  const generationCosts = generations.map(observationCost).filter((value): value is number => value !== undefined);
  const directCost = numberValue(redactedTrace.totalCost ?? redactedTrace.calculatedTotalCost);
  const retryValues = generations.map((item) => numberValue(metadataOf(item).retry) ?? 0);
  const toolFailures = redactedObservations
    .filter((item) => isTool(item) && stringValue(item.level)?.toUpperCase() === 'ERROR')
    .map((item) => normalizeErrorFingerprint(stringValue(item.statusMessage, item.name, 'tool failure')!));
  const workflow =
    stringValue(traceMetadata.workflowId, traceMetadata.workflow, traceMetadata.actionId, redactedTrace.name) ??
    'unknown';
  return {
    trace: redactedTrace,
    observations: redactedObservations,
    scores: redactedScores,
    timestamp: timestampOf(redactedTrace),
    status,
    durationMs: traceDurationMs(redactedTrace, redactedObservations),
    costUsd: generationCosts.length > 0 ? generationCosts.reduce((sum, value) => sum + value, 0) : directCost,
    inputTokens: sumKnown(usage.map((item) => item.input)) ?? undefined,
    outputTokens: sumKnown(usage.map((item) => item.output)) ?? undefined,
    totalTokens: sumKnown(usage.map((item) => item.total)) ?? undefined,
    errorFingerprints: errorFingerprints(redactedTrace, redactedObservations, status),
    toolFailureFingerprints: toolFailures,
    warnings: collectInstrumentationWarnings(redactedTrace, redactedObservations),
    models,
    providers,
    workflow,
    agent: stringValue(traceMetadata.agentId, traceMetadata.agent) ?? 'unknown',
    action: stringValue(traceMetadata.actionId, traceMetadata.action) ?? 'unknown',
    release: stringValue(redactedTrace.release, redactedTrace.version, traceMetadata.release) ?? 'unknown',
    retries: retryValues.filter((value) => value > 0).length,
    fallbacks: generations.filter((item) => metadataOf(item).fallback === true).length,
    hasNegativeScore: redactedScores.some((score) => isFeedback(score) && scoreLabel(score) === 'down'),
    hasFailingEvaluator: redactedScores.some((score) => !isFeedback(score) && isFailingScore(score)),
  };
}

function fingerprintRows(
  details: DetailedTrace[],
  selector: (detail: DetailedTrace) => string[],
): z.infer<typeof fingerprintSchema>[] {
  const groups = new Map<string, string[]>();
  for (const detail of details) {
    for (const fingerprint of selector(detail)) {
      const ids = groups.get(fingerprint) ?? [];
      ids.push(detail.trace.id);
      groups.set(fingerprint, ids);
    }
  }
  return [...groups.entries()]
    .map(([fingerprint, traceIds]) => ({
      fingerprint,
      count: traceIds.length,
      repeated: traceIds.length > 1,
      traceIds: [...new Set(traceIds)].sort(),
    }))
    .sort((left, right) => right.count - left.count || left.fingerprint.localeCompare(right.fingerprint));
}

function metricPoint(detail: DetailedTrace, value: number): z.infer<typeof metricPointSchema> {
  return { traceId: detail.trace.id, value, name: detail.trace.name ?? detail.workflow, timestamp: detail.timestamp };
}

function topMetric(
  details: DetailedTrace[],
  read: (detail: DetailedTrace) => number | undefined,
  limit = 20,
): z.infer<typeof metricPointSchema>[] {
  return details
    .flatMap((detail) => {
      const value = read(detail);
      return value === undefined ? [] : [metricPoint(detail, value)];
    })
    .sort(
      (left, right) =>
        right.value - left.value ||
        right.timestamp.localeCompare(left.timestamp) ||
        left.traceId.localeCompare(right.traceId),
    )
    .slice(0, limit);
}

function buildEvidence(args: {
  evaluationId: string;
  environment: string;
  start: string;
  end: string;
  details: DetailedTrace[];
  pagesRead: number;
  reportedTotalItems: number | null;
  retainedEarliest: string | null;
  retainedLatest: string | null;
  warnings: string[];
}): TraceTriageEvidence {
  const tracesBy = {
    status: {},
    workflow: {},
    agent: {},
    action: {},
    release: {},
    model: {},
    provider: {},
  } as TraceTriageEvidence['tracesBy'];
  const gaps: Record<string, number> = {};
  const generationDurations: Array<{ detail: DetailedTrace; observation: LangfuseObservation; value: number }> = [];
  const toolDurations: Array<{ detail: DetailedTrace; observation: LangfuseObservation; value: number; tool: string }> =
    [];
  const toolsByName = new Map<string, number[]>();
  const evaluatorScores: Record<string, Record<string, number>> = {};
  const feedback = { positive: 0, negative: 0, cleared: 0 };

  for (const detail of args.details) {
    addCount(tracesBy.status, detail.status);
    addCount(tracesBy.workflow, detail.workflow);
    addCount(tracesBy.agent, detail.agent);
    addCount(tracesBy.action, detail.action);
    addCount(tracesBy.release, detail.release);
    for (const model of detail.models.length > 0 ? detail.models : ['unknown']) addCount(tracesBy.model, model);
    for (const provider of detail.providers.length > 0 ? detail.providers : ['unknown'])
      addCount(tracesBy.provider, provider);
    for (const warning of detail.warnings) {
      const key = warning.includes('no release')
        ? 'missing_release'
        : warning.includes('no observations')
          ? 'missing_observations'
          : warning.includes('prompt ID/revision')
            ? 'missing_prompt_id_or_revision'
            : warning.includes('incomplete input/output')
              ? 'incomplete_generation_io'
              : 'other';
      addCount(gaps, key);
    }
    if (isEmpty(detail.trace.output)) addCount(gaps, 'empty_or_missing_root_output');
    if (detail.models.includes('unknown') || detail.models.length === 0) addCount(gaps, 'missing_model');
    if (detail.providers.includes('unknown') || detail.providers.length === 0) addCount(gaps, 'missing_provider');

    for (const observation of detail.observations) {
      const duration = observationDurationMs(observation);
      if (duration !== undefined && isGeneration(observation))
        generationDurations.push({ detail, observation, value: duration });
      if (duration !== undefined && isTool(observation)) {
        const tool =
          stringValue(metadataOf(observation).toolName, metadataOf(observation).tool, observation.name) ?? 'unknown';
        toolDurations.push({ detail, observation, value: duration, tool });
        toolsByName.set(tool, [...(toolsByName.get(tool) ?? []), duration]);
      }
    }
    for (const score of detail.scores) {
      const label = scoreLabel(score);
      if (isFeedback(score)) {
        if (label === 'up') feedback.positive += 1;
        else if (label === 'down') feedback.negative += 1;
        else if (label === 'cleared') feedback.cleared += 1;
      } else {
        evaluatorScores[score.name] ??= {};
        addCount(evaluatorScores[score.name]!, label);
      }
    }
  }

  const errorFingerprints = fingerprintRows(args.details, (detail) => detail.errorFingerprints);
  const toolFailureFingerprints = fingerprintRows(args.details, (detail) => detail.toolFailureFingerprints);
  const traceDurations = args.details
    .map((detail) => detail.durationMs)
    .filter((value): value is number => value !== undefined);
  const traceCosts = args.details
    .map((detail) => detail.costUsd)
    .filter((value): value is number => value !== undefined);
  const completeCount = args.details.filter(
    (detail) =>
      detail.warnings.length === 0 &&
      !isEmpty(detail.trace.output) &&
      detail.models.length > 0 &&
      detail.providers.length > 0,
  ).length;
  const generationTop = generationDurations
    .sort((left, right) => right.value - left.value || left.observation.id.localeCompare(right.observation.id))
    .slice(0, 20)
    .map(({ detail, observation, value }) => ({
      traceId: detail.trace.id,
      value,
      name: observation.name ?? observation.id,
      timestamp: timestampOf(observation),
    }));
  const toolTop = toolDurations
    .sort((left, right) => right.value - left.value || left.observation.id.localeCompare(right.observation.id))
    .slice(0, 20)
    .map(({ detail, observation, value }) => ({
      traceId: detail.trace.id,
      value,
      name: observation.name ?? observation.id,
      timestamp: timestampOf(observation),
    }));

  const selection = selectDossiers(args.details, errorFingerprints);
  return TraceTriageEvidenceSchema.parse({
    schemaVersion: 1,
    evaluationId: args.evaluationId,
    environment: args.environment,
    requestedInterval: { start: args.start, end: args.end },
    retainedInterval: { earliest: args.retainedEarliest, latest: args.retainedLatest },
    completeness: {
      complete: true,
      truncated: false,
      pagesRead: args.pagesRead,
      reportedTotalItems: args.reportedTotalItems,
      warnings: args.warnings,
    },
    totals: {
      traces: args.details.length,
      observations: args.details.reduce((sum, detail) => sum + detail.observations.length, 0),
      scores: args.details.reduce((sum, detail) => sum + detail.scores.length, 0),
    },
    tracesBy,
    reliability: {
      errorRate: args.details.length > 0 ? (tracesBy.status.error ?? 0) / args.details.length : null,
      cancellationRate: args.details.length > 0 ? (tracesBy.status.cancelled ?? 0) / args.details.length : null,
      errorFingerprints,
      toolFailureFingerprints,
      retries: args.details.reduce((sum, detail) => sum + detail.retries, 0),
      fallbacks: args.details.reduce((sum, detail) => sum + detail.fallbacks, 0),
      toolFailures: args.details.reduce((sum, detail) => sum + detail.toolFailureFingerprints.length, 0),
    },
    latency: {
      tracesMs: distribution(traceDurations),
      generationsMs: distribution(generationDurations.map((item) => item.value)),
      toolsMsByTool: Object.fromEntries(
        [...toolsByName.entries()]
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([name, values]) => [name, distribution(values)]),
      ),
      slowestTraces: topMetric(args.details, (detail) => detail.durationMs),
      slowestGenerations: generationTop,
      slowestTools: toolTop,
    },
    cost: {
      totalUsd: sumKnown(args.details.map((detail) => detail.costUsd)),
      perTraceUsd: distribution(traceCosts),
      costliestTraces: topMetric(
        args.details.filter((detail) => detail.costUsd !== undefined && detail.costUsd > 0),
        (detail) => detail.costUsd,
      ),
    },
    tokens: {
      input: sumKnown(args.details.map((detail) => detail.inputTokens)),
      output: sumKnown(args.details.map((detail) => detail.outputTokens)),
      total: sumKnown(args.details.map((detail) => detail.totalTokens)),
      largestTraces: topMetric(args.details, (detail) => detail.totalTokens),
    },
    scores: { feedback, evaluators: evaluatorScores },
    instrumentation: { completenessRate: args.details.length > 0 ? completeCount / args.details.length : null, gaps },
    selectedTraces: selection.selected.map(({ detail, reasons, file }) => ({
      traceId: detail.trace.id,
      status: detail.status,
      file,
      reasons,
    })),
    omittedDossiersByReason: selection.omitted,
  });
}

function selectDossiers(details: DetailedTrace[], fingerprints: z.infer<typeof fingerprintSchema>[]) {
  const byId = new Map(details.map((detail) => [detail.trace.id, detail]));
  const candidates: Array<{ detail: DetailedTrace; reason: string }> = [];
  const omitted: Record<string, number> = {};
  const errorCandidates: Array<{ detail: DetailedTrace; reason: string }> = [];
  for (const fingerprint of fingerprints) {
    const matching = fingerprint.traceIds
      .map((id) => byId.get(id))
      .filter((detail): detail is DetailedTrace => Boolean(detail))
      .sort(
        (left, right) => right.timestamp.localeCompare(left.timestamp) || left.trace.id.localeCompare(right.trace.id),
      );
    for (const detail of matching.slice(0, fingerprint.repeated ? 3 : 1))
      errorCandidates.push({ detail, reason: `error:${fingerprint.fingerprint}` });
  }
  candidates.push(...errorCandidates.slice(0, 50));
  if (errorCandidates.length > 50) omitted.error_fingerprint_limit = errorCandidates.length - 50;

  for (const point of topMetric(details, (detail) => detail.durationMs))
    candidates.push({ detail: byId.get(point.traceId)!, reason: 'slow_trace' });
  for (const point of topMetric(
    details.filter((detail) => detail.costUsd !== undefined && detail.costUsd > 0),
    (detail) => detail.costUsd,
  ))
    candidates.push({ detail: byId.get(point.traceId)!, reason: 'cost_outlier' });
  const scored = details
    .filter((detail) => detail.hasNegativeScore || detail.hasFailingEvaluator)
    .sort(
      (left, right) => right.timestamp.localeCompare(left.timestamp) || left.trace.id.localeCompare(right.trace.id),
    );
  for (const detail of scored.slice(0, 30))
    candidates.push({ detail, reason: detail.hasNegativeScore ? 'negative_feedback' : 'failing_evaluator' });
  if (scored.length > 30) omitted.score_limit = scored.length - 30;
  const successes = details
    .filter((detail) => detail.status === 'success')
    .sort(
      (left, right) =>
        stableHash(left.trace.id).localeCompare(stableHash(right.trace.id)) ||
        left.trace.id.localeCompare(right.trace.id),
    );
  for (const detail of successes.slice(0, 20)) candidates.push({ detail, reason: 'successful_comparison' });
  if (successes.length > 20) omitted.success_comparison_limit = successes.length - 20;

  const selectedMap = new Map<string, { detail: DetailedTrace; reasons: string[] }>();
  for (const candidate of candidates) {
    const existing = selectedMap.get(candidate.detail.trace.id);
    if (existing) {
      if (!existing.reasons.includes(candidate.reason)) existing.reasons.push(candidate.reason);
    } else if (selectedMap.size < DOSSIER_LIMIT) {
      selectedMap.set(candidate.detail.trace.id, { detail: candidate.detail, reasons: [candidate.reason] });
    } else {
      addCount(omitted, 'dossier_cap');
    }
  }
  const severity = { error: 0, cancelled: 1, success: 2 } as const;
  const selected = [...selectedMap.values()]
    .sort(
      (left, right) =>
        severity[left.detail.status] - severity[right.detail.status] ||
        right.detail.timestamp.localeCompare(left.detail.timestamp) ||
        left.detail.trace.id.localeCompare(right.detail.trace.id),
    )
    .map((item) => ({
      ...item,
      file: `traces/${safeName(item.detail.timestamp.replace(/[:.]/g, '-'))}--${safeName(item.detail.trace.name ?? item.detail.workflow)}--${safeName(item.detail.trace.id)}.md`,
    }));
  return { selected, omitted };
}

function renderDistribution(value: z.infer<typeof distributionSchema>, unit: string): string {
  return value.count === 0
    ? 'unknown'
    : `p50 ${value.p50}${unit}, p95 ${value.p95}${unit}, p99 ${value.p99}${unit} (${value.count} known)`;
}

function renderTriage(evidence: TraceTriageEvidence): string {
  const warnings =
    evidence.completeness.warnings.length > 0
      ? evidence.completeness.warnings.map((warning) => `- ${warning}`)
      : ['- None.'];
  const fingerprintLines =
    evidence.reliability.errorFingerprints.length > 0
      ? evidence.reliability.errorFingerprints.map(
          (item) => `- ${item.count} trace(s): \`${item.fingerprint}\`${item.repeated ? ' (repeated)' : ' (one-off)'}`,
        )
      : ['- No error or cancellation fingerprints.'];
  const evidenceLines =
    evidence.selectedTraces.length > 0
      ? evidence.selectedTraces.map(
          (item) => `- [${item.traceId}](${item.file}) — ${item.status}; ${item.reasons.join(', ')}`,
        )
      : ['- No detailed dossiers selected.'];
  return `${[
    '# Langfuse trace triage',
    '',
    '## Scope and retained coverage',
    '',
    `- Evaluation ID: ${evidence.evaluationId}`,
    `- Environment: ${evidence.environment}`,
    `- Requested UTC interval: [${evidence.requestedInterval.start}, ${evidence.requestedInterval.end})`,
    `- Retained trace interval: ${evidence.retainedInterval.earliest ?? 'unknown'} to ${evidence.retainedInterval.latest ?? 'unknown'}`,
    `- Retrieved: ${evidence.totals.traces} traces, ${evidence.totals.observations} observations, ${evidence.totals.scores} scores`,
    '',
    '## Data completeness warnings',
    '',
    ...warnings,
    '',
    '## Reliability summary',
    '',
    `- Status counts: ${JSON.stringify(evidence.tracesBy.status)}`,
    `- Error rate: ${evidence.reliability.errorRate ?? 'unknown'}`,
    `- Cancellation rate: ${evidence.reliability.cancellationRate ?? 'unknown'}`,
    `- Retries: ${evidence.reliability.retries}; fallbacks: ${evidence.reliability.fallbacks}; tool failures: ${evidence.reliability.toolFailures}`,
    '',
    '## Repeated failure fingerprints',
    '',
    ...fingerprintLines,
    '',
    '## Latency and cost distributions',
    '',
    `- Trace duration: ${renderDistribution(evidence.latency.tracesMs, 'ms')}`,
    `- Generation latency: ${renderDistribution(evidence.latency.generationsMs, 'ms')}`,
    `- Per-trace cost: ${renderDistribution(evidence.cost.perTraceUsd, ' USD')}`,
    `- Total known cost: ${evidence.cost.totalUsd ?? 'unknown'} USD`,
    '',
    '## Slowest and costliest paths',
    '',
    ...evidence.latency.slowestTraces
      .slice(0, 20)
      .map((item) => `- Slow: ${item.name} (${item.traceId}) — ${item.value}ms`),
    ...evidence.cost.costliestTraces
      .slice(0, 20)
      .map((item) => `- Cost: ${item.name} (${item.traceId}) — ${item.value} USD`),
    '',
    '## Feedback and evaluator scores',
    '',
    `- User feedback: ${JSON.stringify(evidence.scores.feedback)}`,
    `- Existing evaluators: ${JSON.stringify(evidence.scores.evaluators)}`,
    '',
    '## Instrumentation gaps',
    '',
    `- Complete trace rate: ${evidence.instrumentation.completenessRate ?? 'unknown'}`,
    `- Gaps: ${JSON.stringify(evidence.instrumentation.gaps)}`,
    '',
    '## Selected evidence index',
    '',
    ...evidenceLines,
    '',
    'Unexpected-output judgment is intentionally deferred to the independent agent evaluation phase.',
    '',
  ].join('\n')}\n`;
}

async function sha256File(filePath: string): Promise<string> {
  return createHash('sha256')
    .update(await readFile(filePath))
    .digest('hex');
}

export async function triageLangfuseQuality(args: {
  client: LangfuseTraceReadClient;
  environment: string;
  outputRoot?: string;
  now?: Date;
  cliRelease?: string;
  sinceMs?: number;
}): Promise<{ outputDir: string; manifest: TraceTriageManifest; evidence: TraceTriageEvidence; triage: string }> {
  const now = args.now ?? new Date();
  const sinceMs = args.sinceMs ?? 7 * DAY_MS;
  if (!Number.isInteger(sinceMs) || sinceMs < 60 * 60 * 1_000 || sinceMs > 90 * DAY_MS)
    throw new Error('AI triage interval must be between 1 hour and 90 days.');
  const end = now.toISOString();
  const start = new Date(now.getTime() - sinceMs).toISOString();
  const intervalLabel = sinceMs % DAY_MS === 0 ? `${sinceMs / DAY_MS}d` : `${sinceMs / (60 * 60 * 1_000)}h`;
  const filterHash = stableHash(JSON.stringify({ environment: args.environment, start, end })).slice(0, 8);
  const evaluationId = `${end.replace(/[:.]/g, '-')}-${args.environment}-${intervalLabel}-${filterHash}`;
  const root = path.resolve(args.outputRoot ?? '.agents/evaluations');
  const outputDir = path.resolve(root, evaluationId);
  if (!outputDir.startsWith(`${root}${path.sep}`))
    throw new Error('Evaluation output path escaped the configured output root.');
  await mkdir(path.join(outputDir, 'traces'), { recursive: true, mode: 0o700 });
  await mkdir(path.join(outputDir, 'recommendations'), { recursive: true, mode: 0o700 });
  await chmod(outputDir, 0o700).catch(() => undefined);

  const collected = await collectTraceSummaries({ client: args.client, environment: args.environment, start, end });
  const details = await mapWithConcurrency(collected.traces, DETAIL_CONCURRENCY, async (summary) => {
    const [trace, observations, scores] = await Promise.all([
      args.client.getTrace(summary.id),
      args.client.listObservations(summary.id),
      args.client.listScores(summary.id),
    ]);
    return detailFrom(trace, observations, scores);
  });
  details.sort(
    (left, right) => left.timestamp.localeCompare(right.timestamp) || left.trace.id.localeCompare(right.trace.id),
  );
  const retainedTimestamps = details
    .map((detail) => detail.timestamp)
    .filter(Boolean)
    .sort();
  const retainedEarliest = retainedTimestamps[0] ?? null;
  const retainedLatest = retainedTimestamps.at(-1) ?? null;
  const warnings: string[] = [];
  if (retainedEarliest && Date.parse(retainedEarliest) > Date.parse(start) + DAY_MS)
    warnings.push(
      `No retained traces were returned before ${retainedEarliest}; the requested interval begins ${start}.`,
    );
  if (collected.reportedTotalItems !== null && collected.reportedTotalItems !== collected.traces.length)
    warnings.push(
      `Langfuse reported ${collected.reportedTotalItems} trace(s), while ${collected.traces.length} unique trace(s) were retrieved.`,
    );
  const evidence = buildEvidence({
    evaluationId,
    environment: args.environment,
    start,
    end,
    details,
    pagesRead: collected.pagesRead,
    reportedTotalItems: collected.reportedTotalItems,
    retainedEarliest,
    retainedLatest,
    warnings,
  });
  const selection = selectDossiers(details, evidence.reliability.errorFingerprints);
  await Promise.all(
    selection.selected.map(({ detail, file }) =>
      writeFile(
        path.join(outputDir, file),
        renderTraceMarkdown({
          trace: detail.trace,
          observations: detail.observations,
          warnings: detail.warnings,
          baseUrl: langfuseOrigin(args.client.baseUrl),
        }),
        { encoding: 'utf8', mode: 0o600 },
      ),
    ),
  );
  const triage = renderTriage(evidence);
  const evidencePath = path.join(outputDir, 'evidence.json');
  const triagePath = path.join(outputDir, 'triage.md');
  await Promise.all([
    writeFile(evidencePath, `${JSON.stringify(evidence, null, 2)}\n`, { encoding: 'utf8', mode: 0o600 }),
    writeFile(triagePath, triage, { encoding: 'utf8', mode: 0o600 }),
  ]);
  const generatedFiles = ['evidence.json', 'triage.md', ...evidence.selectedTraces.map((item) => item.file)].sort();
  const fileHashes = Object.fromEntries(
    await Promise.all(
      generatedFiles.map(async (file) => [file, await sha256File(path.join(outputDir, file))] as const),
    ),
  );
  const manifest = TraceTriageManifestSchema.parse({
    schemaVersion: 1,
    evaluationId,
    environment: args.environment,
    requestedStart: start,
    requestedEnd: end,
    retainedEarliest,
    retainedLatest,
    traceCount: evidence.totals.traces,
    observationCount: evidence.totals.observations,
    scoreCount: evidence.totals.scores,
    completeness: { complete: true, truncated: false, warnings },
    langfuseOrigin: langfuseOrigin(args.client.baseUrl),
    triageAlgorithmRevision: TRACE_TRIAGE_ALGORITHM_REVISION,
    fileHashes,
    cliRelease: args.cliRelease ?? process.env.RELEASE_VERSION ?? process.env.GIT_COMMIT_SHA ?? 'unknown',
    createdAt: end,
  });
  await writeFile(path.join(outputDir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, {
    encoding: 'utf8',
    mode: 0o600,
  });
  return { outputDir, manifest, evidence, triage };
}
