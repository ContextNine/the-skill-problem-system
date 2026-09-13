'use client';

import { useEffect } from 'react';
import ErrorView from '@/components/shared/error-view';
import { IS_LOCAL } from '@/config/next-config';
import { parseReactError } from '@/lib/errors/error-helper';
import { reportReactClientError } from '@/lib/monitoring/client-error-handler';

import { AUTHENTICATION_ERROR_MESSAGE } from '@acme/shared/utils/errors';

import NotSignedIn from './app_subdomain/(auth)/not-signed-in';

export default function ErrorPage({
  error,
}: {
  error: Error & {
    digest?: string;
  };
}) {
  // Enhanced logging for debugging
  useEffect(() => {
    reportReactClientError(error);
    console.error('Original error:', error);

    // Check if this is a minified React error
    if (error.message?.includes('Minified React error #')) {
      // Try to parse the error code and provide more context
      const enhancedError = parseReactError(error);
      console.error('Enhanced error details:', enhancedError);

      // Save to window for debugging
      if (typeof window !== 'undefined') {
        (window as any).__LAST_REACT_ERROR__ = {
          original: error,
          enhanced: enhancedError,
          time: new Date().toISOString(),
        };

        console.info(
          '%c React Error Debugging Info Available! %c\n' +
            'Type window.__LAST_REACT_ERROR__ to see details\n' +
            'For maximum update depth exceeded errors, look for components that update state in useEffect hooks',
          'background: #ff5555; color: white; font-weight: bold; padding: 2px 6px;',
          'color: #333; font-weight: normal;',
        );
      }
    }
  }, [error]);

  const isAuthenticationError = error.message.includes(AUTHENTICATION_ERROR_MESSAGE);

  //message is already minified and/or obfuscated on prod. May as well not show it - not useful.
  const displayMessage = IS_LOCAL ? error.message : null;

  return (
    <>
      {isAuthenticationError ? (
        <>
          <NotSignedIn />
        </>
      ) : (
        <ErrorView message={displayMessage} />
      )}
    </>
  );
}
