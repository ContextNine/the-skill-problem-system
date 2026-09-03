'use client';

import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { GoogleTagManagerConsentProvider } from '@/components/forms_dialogs/cookies/google-tag-manager-consent-form';
import { nextTopLoaderColor } from '@/components/styles/common';
import { lemonSqueezyStoreName } from '@/config/next-config';
import { env } from '@/env';
import NextTopLoader from 'nextjs-toploader';

import { LocalStoragePreferencesProvider } from './localstorage-provider';
import { ThemeProvider } from './theme-provider';

type PublicProvidersProps = {
  children: ReactNode;
  hostname?: string | null;
  initialHasExplicitThemePreference?: boolean;
  pathname: string;
};

export function PublicProviders({
  children,
  hostname,
  initialHasExplicitThemePreference = false,
  pathname,
}: PublicProvidersProps) {
  useEffect(() => {
    if (typeof window.createLemonSqueezy === 'function') {
      window.createLemonSqueezy();
    }
  }, []);

  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="light"
      disableTransitionOnChange
      hostname={hostname}
      initialHasExplicitThemePreference={initialHasExplicitThemePreference}
      pathname={pathname}
    >
      <NextTopLoader color={nextTopLoaderColor} />
      <LocalStoragePreferencesProvider>
        <GoogleTagManagerConsentProvider gtmId={env.NEXT_PUBLIC_GTM_ID} autoGrant={true}>
          <div
            dangerouslySetInnerHTML={{
              __html: `
              <script src="https://app.lemonsqueezy.com/js/lemon.js" defer></script>
              <script>window.lemonSqueezyAffiliateConfig = { store: "${lemonSqueezyStoreName}", debug: true };</script>
              <script src="https://lmsqueezy.com/affiliate.js" defer></script>
            `,
            }}
          />
          {children}
        </GoogleTagManagerConsentProvider>
      </LocalStoragePreferencesProvider>
    </ThemeProvider>
  );
}
