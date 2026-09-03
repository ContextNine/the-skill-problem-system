'use client';

import { useEffect } from 'react';
import { reportClientErrorAction } from '@/data/errors/error-actions';
import posthog from 'posthog-js';
import { usePostHog } from 'posthog-js/react';

type ClientErrorType = 'error' | 'unhandledrejection' | 'react-error';
type CaptureClient = {
  capture: (eventName: string, properties?: Record<string, unknown>) => unknown;
};

const SENSITIVE_QUERY_VALUE = /([?&](?:access_token|api_key|code|email|key|secret|token)=)[^&#\s]+/gi;
const BEARER_TOKEN = /bearer\s+[a-z0-9._~+/=-]+/gi;
const EMAIL_ADDRESS = /[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}/gi;

export function sanitizeClientErrorText(value: string | undefined, maxLength: number): string | undefined {
  if (!value) return undefined;

  return value
    .replace(SENSITIVE_QUERY_VALUE, '$1[redacted]')
    .replace(BEARER_TOKEN, 'Bearer [redacted]')
    .replace(EMAIL_ADDRESS, '[redacted-email]')
    .slice(0, maxLength);
}

function sanitizedCurrentUrl(): string | undefined {
  if (typeof window === 'undefined') return undefined;

  try {
    const url = new URL(window.location.href);
    url.search = '';
    url.hash = '';
    return url.href.slice(0, 2000);
  } catch {
    return undefined;
  }
}

function reportClientError({
  captureClient,
  colno,
  error,
  lineno,
  source,
  type,
}: {
  captureClient?: CaptureClient;
  colno?: number;
  error: Error;
  lineno?: number;
  source?: string;
  type: ClientErrorType;
}): void {
  const message = sanitizeClientErrorText(error.message || 'Unknown error', 2000) ?? 'Unknown error';
  const stack = sanitizeClientErrorText(error.stack, 5000);
  const sanitizedSource = sanitizeClientErrorText(source, 500);
  const url = sanitizedCurrentUrl();

  captureClient?.capture('$exception', {
    $exception_message: message,
    $exception_stack_trace_raw: stack,
    $exception_type: error.name || 'Error',
    $exception_source: sanitizedSource,
    $exception_lineno: lineno,
    $exception_colno: colno,
  });

  reportClientErrorAction({
    type,
    message,
    stack,
    source: sanitizedSource,
    lineno,
    colno,
    url,
    userAgent: typeof navigator === 'undefined' ? undefined : sanitizeClientErrorText(navigator.userAgent, 500),
  }).catch(() => {});
}

export function reportReactClientError(error: Error): void {
  reportClientError({
    captureClient: posthog,
    error,
    type: 'react-error',
  });
}

export function ClientErrorHandler(): null {
  const posthogClient = usePostHog();

  useEffect(() => {
    const previousOnError = window.onerror;

    window.onerror = (message, source, lineno, colno, error) => {
      const normalizedError = error ?? new Error(typeof message === 'string' ? message : 'Unknown browser error');

      reportClientError({
        captureClient: posthogClient,
        colno: colno ?? undefined,
        error: normalizedError,
        lineno: lineno ?? undefined,
        source: typeof source === 'string' ? source : undefined,
        type: 'error',
      });

      if (previousOnError) {
        return previousOnError(message, source, lineno, colno, error);
      }
      return false;
    };

    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      const normalizedError =
        event.reason instanceof Error
          ? event.reason
          : new Error(typeof event.reason === 'string' ? event.reason : 'Unhandled promise rejection');

      reportClientError({
        captureClient: posthogClient,
        error: normalizedError,
        type: 'unhandledrejection',
      });
    };

    window.addEventListener('unhandledrejection', handleUnhandledRejection);

    return () => {
      window.onerror = previousOnError;
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
    };
  }, [posthogClient]);

  return null;
}
