'use client';

import { useEffect } from 'react';
import { reportReactClientError } from '@/lib/monitoring/client-error-handler';

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    reportReactClientError(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="flex min-h-screen items-center justify-center bg-white p-6 text-mono-900">
        <main className="max-w-md text-center">
          <h1 className="text-2xl font-semibold">Something went wrong</h1>
          <p className="mt-3 text-sm text-mono-600">The error has been recorded. You can safely try again.</p>
          <button
            type="button"
            className="mt-6 border border-neutral-800 bg-black px-5 py-3 text-sm font-medium text-white"
            onClick={reset}
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
