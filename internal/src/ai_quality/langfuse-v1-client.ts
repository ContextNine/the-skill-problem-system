import { z } from 'zod';

const metadataSchema = z.record(z.string(), z.unknown());
const promptSchema = z
  .object({
    name: z.string().optional(),
    version: z.union([z.string(), z.number()]).optional(),
  })
  .passthrough();

export const LangfuseTraceSchema = z
  .object({
    id: z.string(),
    name: z.string().optional(),
    timestamp: z.string().optional(),
    startTime: z.string().optional(),
    endTime: z.string().optional(),
    createdAt: z.string().optional(),
    updatedAt: z.string().optional(),
    environment: z.string().optional(),
    release: z.string().nullable().optional(),
    version: z.string().nullable().optional(),
    projectId: z.string().optional(),
    sessionId: z.string().nullable().optional(),
    input: z.unknown().optional(),
    output: z.unknown().optional(),
    metadata: metadataSchema.optional(),
    tags: z.array(z.string()).optional(),
    level: z.string().optional(),
    statusMessage: z.string().nullable().optional(),
    latency: z.union([z.number(), z.string()]).optional(),
    duration: z.union([z.number(), z.string()]).optional(),
    totalCost: z.union([z.number(), z.string()]).nullable().optional(),
    calculatedTotalCost: z.union([z.number(), z.string()]).nullable().optional(),
  })
  .passthrough();

export const LangfuseObservationSchema = z
  .object({
    id: z.string(),
    traceId: z.string().optional(),
    parentObservationId: z.string().nullable().optional(),
    parentId: z.string().nullable().optional(),
    name: z.string().optional(),
    type: z.string().optional(),
    asType: z.string().optional(),
    startTime: z.string().optional(),
    endTime: z.string().nullable().optional(),
    timestamp: z.string().optional(),
    createdAt: z.string().optional(),
    updatedAt: z.string().optional(),
    level: z.string().optional(),
    statusMessage: z.string().nullable().optional(),
    input: z.unknown().optional(),
    output: z.unknown().optional(),
    metadata: metadataSchema.optional(),
    model: z.string().nullable().optional(),
    providedModelName: z.string().nullable().optional(),
    promptName: z.string().nullable().optional(),
    promptVersion: z.union([z.string(), z.number()]).nullable().optional(),
    prompt: promptSchema.nullable().optional(),
    usage: z.unknown().optional(),
    usageDetails: z.unknown().optional(),
    costDetails: z.unknown().optional(),
    totalCost: z.union([z.number(), z.string()]).nullable().optional(),
    calculatedTotalCost: z.union([z.number(), z.string()]).nullable().optional(),
    latency: z.union([z.number(), z.string()]).optional(),
  })
  .passthrough();

export const LangfuseScoreSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    value: z.unknown().optional(),
    stringValue: z.string().nullable().optional(),
    dataType: z.string().optional(),
    source: z.string().optional(),
    timestamp: z.string().optional(),
    createdAt: z.string().optional(),
    updatedAt: z.string().optional(),
    traceId: z.string().nullable().optional(),
    observationId: z.string().nullable().optional(),
    comment: z.string().nullable().optional(),
    subject: z.unknown().optional(),
  })
  .passthrough();

const pageMetaSchema = z
  .object({
    page: z.number().int().positive().optional(),
    limit: z.number().int().positive().optional(),
    totalItems: z.number().int().nonnegative().optional(),
    totalPages: z.number().int().nonnegative().optional(),
    cursor: z.string().nullable().optional(),
  })
  .passthrough();

function pageSchema<TSchema extends z.ZodType>(itemSchema: TSchema) {
  return z.object({
    data: z.array(itemSchema).default([]),
    meta: pageMetaSchema.default({}),
  });
}

const tracePageSchema = pageSchema(LangfuseTraceSchema);
const observationPageSchema = pageSchema(LangfuseObservationSchema);
const scorePageSchema = pageSchema(LangfuseScoreSchema);

export type LangfuseTrace = z.infer<typeof LangfuseTraceSchema>;
export type LangfuseObservation = z.infer<typeof LangfuseObservationSchema>;
export type LangfuseScore = z.infer<typeof LangfuseScoreSchema>;
export type LangfuseRecord = LangfuseTrace | LangfuseObservation;
export type LangfusePage<T> = {
  data: T[];
  meta: z.infer<typeof pageMetaSchema>;
};

export type LangfuseV1Config = {
  baseUrl: string;
  publicKey: string;
  secretKey: string;
  fetch?: typeof fetch;
  sleep?: (milliseconds: number) => Promise<void>;
  maxAttempts?: number;
};

export type LangfuseTraceQuery = {
  environment: string;
  fromTimestamp?: string;
  toTimestamp?: string;
  release?: string;
  limit: number;
};

export interface LangfuseTraceReadClient {
  readonly baseUrl: string;
  listTracePage(
    query: Omit<LangfuseTraceQuery, 'limit'> & { page: number; limit: number },
  ): Promise<LangfusePage<LangfuseTrace>>;
  listTraces(query: LangfuseTraceQuery): Promise<LangfuseTrace[]>;
  getTrace(traceId: string): Promise<LangfuseTrace>;
  listObservations(traceId: string): Promise<LangfuseObservation[]>;
  listScores(traceId: string): Promise<LangfuseScore[]>;
}

function parseRetryAfter(value: string | null, now = Date.now()): number | null {
  if (!value) return null;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1_000;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? Math.max(0, timestamp - now) : null;
}

export class LangfuseV1Client implements LangfuseTraceReadClient {
  readonly baseUrl: string;
  private readonly authorization: string;
  private readonly fetcher: typeof fetch;
  private readonly sleep: (milliseconds: number) => Promise<void>;
  private readonly maxAttempts: number;

  constructor(config: LangfuseV1Config) {
    this.baseUrl = config.baseUrl.replace(/\/$/, '');
    this.authorization = `Basic ${Buffer.from(`${config.publicKey}:${config.secretKey}`).toString('base64')}`;
    this.fetcher = config.fetch ?? fetch;
    this.sleep = config.sleep ?? ((milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)));
    this.maxAttempts = config.maxAttempts ?? 3;
  }

  private async request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
    for (let attempt = 1; attempt <= this.maxAttempts; attempt += 1) {
      const response = await this.fetcher(`${this.baseUrl}${path}`, {
        ...init,
        signal: AbortSignal.timeout(30_000),
        headers: {
          accept: 'application/json',
          authorization: this.authorization,
          ...init?.headers,
        },
      });
      if (response.ok) {
        if (response.status === 204) return schema.parse(undefined);
        return schema.parse(await response.json());
      }

      const retryable = response.status === 429 || response.status >= 500;
      if (retryable && attempt < this.maxAttempts) {
        const retryAfter = parseRetryAfter(response.headers.get('retry-after'));
        await this.sleep(Math.min(5_000, retryAfter ?? 200 * 2 ** (attempt - 1)));
        continue;
      }

      throw new Error(`Langfuse request failed (${response.status} ${response.statusText}); response body omitted.`);
    }
    throw new Error('Langfuse request exhausted its retry budget.');
  }

  async listTracePage(
    query: Omit<LangfuseTraceQuery, 'limit'> & { page: number; limit: number },
  ): Promise<LangfusePage<LangfuseTrace>> {
    const params = new URLSearchParams({
      page: String(query.page),
      limit: String(Math.min(100, Math.max(1, query.limit))),
      environment: query.environment,
    });
    if (query.fromTimestamp) params.set('fromTimestamp', query.fromTimestamp);
    if (query.toTimestamp) params.set('toTimestamp', query.toTimestamp);
    if (query.release) params.set('release', query.release);
    return this.request(`/api/public/traces?${params.toString()}`, tracePageSchema);
  }

  async listTraces(query: LangfuseTraceQuery): Promise<LangfuseTrace[]> {
    const traces: LangfuseTrace[] = [];
    let page = 1;
    const pageSize = Math.min(100, Math.max(1, query.limit));

    while (traces.length < query.limit) {
      const response = await this.listTracePage({ ...query, page, limit: pageSize });
      traces.push(...response.data);
      const totalPages = response.meta.totalPages;
      if (
        response.data.length === 0 ||
        (totalPages === undefined ? response.data.length < pageSize : page >= totalPages)
      )
        break;
      page += 1;
    }

    return traces.slice(0, query.limit);
  }

  getTrace(traceId: string): Promise<LangfuseTrace> {
    return this.request(`/api/public/traces/${encodeURIComponent(traceId)}`, LangfuseTraceSchema);
  }

  async listObservations(traceId: string): Promise<LangfuseObservation[]> {
    const observations: LangfuseObservation[] = [];
    let page = 1;

    while (true) {
      if (page > 100) throw new Error('Observation page budget exhausted; coverage is incomplete.');
      const params = new URLSearchParams({ traceId, page: String(page), limit: '100' });
      const response = await this.request(`/api/public/observations?${params.toString()}`, observationPageSchema);
      observations.push(...response.data);
      const totalPages = response.meta.totalPages;
      if (response.data.length === 0 || (totalPages === undefined ? response.data.length < 100 : page >= totalPages))
        break;
      page += 1;
    }

    return observations;
  }

  async listScores(traceId: string): Promise<LangfuseScore[]> {
    const scores: LangfuseScore[] = [];
    let page = 1;
    while (true) {
      if (page > 100) throw new Error('Score page budget exhausted; coverage is incomplete.');
      const params = new URLSearchParams({ traceId, page: String(page), limit: '100' });
      const response = await this.request(`/api/public/scores?${params.toString()}`, scorePageSchema);
      scores.push(...response.data);
      const totalPages = response.meta.totalPages;
      if (response.data.length === 0 || (totalPages === undefined ? response.data.length < 100 : page >= totalPages))
        break;
      page += 1;
    }
    return scores;
  }

  async listErrorObservations(query: { environment: string; start: string; end: string }) {
    const observations = new Map<string, LangfuseObservation>();
    for (let page = 1; page <= 100; page++) {
      const params = new URLSearchParams({
        environment: query.environment,
        fromStartTime: query.start,
        toStartTime: query.end,
        level: 'ERROR',
        page: String(page),
        limit: '100',
      });
      const response = await this.request(`/api/public/observations?${params}`, observationPageSchema);
      for (const observation of response.data) observations.set(observation.id, observation);
      const totalPages = response.meta.totalPages;
      if (totalPages === undefined ? response.data.length < 100 : page >= totalPages) {
        if (response.meta.totalItems !== undefined && observations.size < response.meta.totalItems) {
          throw new Error('Missing error observations; coverage incomplete.');
        }
        return { observations: [...observations.values()], pages: page };
      }
      if (!response.data.length) throw new Error('Empty observation page before reported end; coverage incomplete.');
    }
    throw new Error('Error observation page budget exhausted; coverage incomplete.');
  }
}

export function createLangfuseV1ClientFromEnvironment(): LangfuseV1Client {
  const required = ['LANGFUSE_URL', 'LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY'] as const;
  const missing = required.filter((name) => !process.env[name]);
  if (missing.length > 0) {
    throw new Error(`Missing required environment variables: ${missing.join(', ')}.`);
  }
  return new LangfuseV1Client({
    baseUrl: process.env.LANGFUSE_URL!,
    publicKey: process.env.LANGFUSE_PUBLIC_KEY!,
    secretKey: process.env.LANGFUSE_SECRET_KEY!,
  });
}
