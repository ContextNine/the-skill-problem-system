'use client';

import { ReactNode, Suspense, useEffect, useLayoutEffect } from 'react';
import { GoogleTagManagerConsentProvider } from '@/components/forms_dialogs/cookies/google-tag-manager-consent-form';
import { nextTopLoaderColor } from '@/components/styles/common';
import { EditorProvider } from '@/components/tiptap/editor-ref-and-size-provider';
import { isProduction, lemonSqueezyStoreName } from '@/config/next-config';
import { TRPCReactProvider } from '@/data/trpc/react';
import { env } from '@/env';
import { ClientErrorHandler } from '@/lib/monitoring/client-error-handler';
import PostHogPageView from '@/lib/monitoring/posthog-page-view';
import NextTopLoader from 'nextjs-toploader';
import posthog from 'posthog-js';
import { PostHogProvider } from 'posthog-js/react';

import { isSubdomainHost } from '@acme/shared/utils/hostname';

import { LocalStoragePreferencesProvider } from './localstorage-provider';
import { PollingProvider } from './polling-provider';
import { ThemeProvider } from './theme-provider';

const postHogInitOptions = {
  api_host: env.NEXT_PUBLIC_POSTHOG_ORIGIN,
  capture_pageview: false,
  enable_heatmaps: true,
  session_recording: {},
};

function initializePostHog() {
  const client = posthog as typeof posthog & { __loaded?: boolean };

  if (client.__loaded) {
    posthog.set_config(postHogInitOptions);
    return;
  }

  posthog.init(env.NEXT_PUBLIC_POSTHOG_KEY || '', postHogInitOptions);
}

type GlobalProvidersProps = {
  children: ReactNode;
  hostname?: string | null;
  initialHasExplicitThemePreference?: boolean;
  pathname: string;
};

export function GlobalProviders({
  children,
  hostname,
  initialHasExplicitThemePreference = false,
  pathname,
}: GlobalProvidersProps) {
  const isAppSubdomain = isSubdomainHost(hostname);
  const shouldEnableGTM = !isAppSubdomain;
  const shouldEnablePostHog =
    isAppSubdomain &&
    isProduction &&
    env.NEXT_PUBLIC_POSTHOG_ORIGIN?.startsWith('https://') &&
    env.NEXT_PUBLIC_POSTHOG_KEY !== undefined;

  useLayoutEffect(() => {
    if (!shouldEnablePostHog) {
      return;
    }

    initializePostHog();
  }, [shouldEnablePostHog]);

  useEffect(() => {
    // // Suppress react-devtools-bridge console messages
    // if (typeof window !== 'undefined' && !isProduction) {
    //   const originalLog = console.log;
    //   console.log = (...args) => {
    //     if (
    //       args.length > 0 &&
    //       typeof args[0] === 'string' &&
    //       args[0].includes('react-devtools-bridge') || args[0].includes('react-devtools-content-script')
    //     ) {
    //       return;
    //     }
    //     originalLog.apply(console, args);
    //   };
    // }

    if (typeof window.createLemonSqueezy === 'function') {
      window.createLemonSqueezy();
    }
  }, []);

  const measurementContent = (
    <>
      <div
        dangerouslySetInnerHTML={{
          __html: `
            <script src="https://app.lemonsqueezy.com/js/lemon.js" defer></script>
            <script>window.lemonSqueezyAffiliateConfig = { store: "${lemonSqueezyStoreName}", debug: true };</script>
            <script src="https://lmsqueezy.com/affiliate.js" defer></script>
          `,
        }}
      />
      {shouldEnablePostHog ? (
        <PostHogProvider client={posthog}>
          <Suspense>
            <PostHogPageView />
          </Suspense>
          <ClientErrorHandler />
          {children}
        </PostHogProvider>
      ) : (
        children
      )}
    </>
  );

  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="light"
      disableTransitionOnChange
      hostname={hostname}
      initialHasExplicitThemePreference={initialHasExplicitThemePreference}
      pathname={pathname}
    >
      <EditorProvider>
        <PollingProvider>
          <NextTopLoader color={nextTopLoaderColor} />
          <TRPCReactProvider>
            <LocalStoragePreferencesProvider>
              {shouldEnableGTM ? (
                <GoogleTagManagerConsentProvider gtmId={env.NEXT_PUBLIC_GTM_ID} autoGrant={true}>
                  {measurementContent}
                </GoogleTagManagerConsentProvider>
              ) : (
                measurementContent
              )}
            </LocalStoragePreferencesProvider>
          </TRPCReactProvider>
        </PollingProvider>
      </EditorProvider>
    </ThemeProvider>
  );
}
