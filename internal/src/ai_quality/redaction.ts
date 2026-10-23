const REDACTED = '[REDACTED]';
const BINARY_DATA = '[BINARY DATA OMITTED]';
const SENSITIVE_KEY_PATTERN =
  /(^|_)(authorization|cookie|set_cookie|password|passwd|secret|token|api_key|apikey|private_key|access_key|refresh_token)($|_)/i;
const SIGNED_QUERY_PARAM_PATTERN =
  /([?&](?:x-amz-signature|x-amz-credential|x-amz-security-token|signature|sig|token|key)=)[^&#\s]*/gi;
const BEARER_PATTERN = /\bBearer\s+[A-Za-z0-9._~+/=-]+/gi;

function redactString(value: string): string {
  if (/^data:[^;,]+(?:;[^,]*)?,/i.test(value)) {
    return BINARY_DATA;
  }

  return value
    .replace(/-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|$)/g, REDACTED)
    .replace(BEARER_PATTERN, 'Bearer [REDACTED]')
    .replace(SIGNED_QUERY_PARAM_PATTERN, `$1${REDACTED}`)
    .replace(
      /([\w-]*(?:password|secret|token|cookie|authorization|api[_-]?key)[\w-]*["']?\s*[=:]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi,
      `$1${REDACTED}`,
    )
    .replace(/\b(?:sk-|gh[pousr]_|github_pat_)[A-Za-z0-9_-]{16,}\b/g, REDACTED);
}

function redactInternal(value: unknown, seen: WeakSet<object>): unknown {
  if (typeof value === 'string') {
    return redactString(value);
  }

  if (value === null || typeof value !== 'object') {
    return value;
  }

  if (
    Buffer.isBuffer(value) ||
    value instanceof ArrayBuffer ||
    ArrayBuffer.isView(value) ||
    (typeof Blob !== 'undefined' && value instanceof Blob)
  ) {
    return BINARY_DATA;
  }

  if (seen.has(value)) {
    return '[CIRCULAR]';
  }
  seen.add(value);

  if (Array.isArray(value)) {
    return value.map((item) => redactInternal(item, seen));
  }

  if (value instanceof Date) {
    return value.toISOString();
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, nestedValue]) => {
      const normalizedKey = key.replace(/([a-z0-9])([A-Z])/g, '$1_$2').replace(/-/g, '_');
      return [key, SENSITIVE_KEY_PATTERN.test(normalizedKey) ? REDACTED : redactInternal(nestedValue, seen)];
    }),
  );
}

export function redactTraceValue(value: unknown): unknown {
  return redactInternal(value, new WeakSet<object>());
}
