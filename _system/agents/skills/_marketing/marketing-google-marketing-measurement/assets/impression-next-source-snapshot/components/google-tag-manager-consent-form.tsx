'use client';

import type { ReactNode } from 'react';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { setCookieObject } from '@/lib/browser-apis/cookies';
import { getCookieValue } from '@/lib/browser-apis/shared-cookies';
import {
  ALL_GOOGLE_CONSENT_GRANTED,
  createGoogleConsentCookie,
  getGoogleConsentState,
  GOOGLE_ANALYTICS_CONSENT_COOKIE_NAME,
  GOOGLE_CONSENT_COOKIE_NAME,
  GOOGLE_CONSENT_COOKIE_VERSION,
  GOOGLE_CONSENT_UPDATE_EVENT,
  GoogleConsentCookie,
  GoogleConsentSource,
  GoogleConsentState,
  parseGoogleConsentCookie,
} from '@/lib/monitoring/google-consent';
import { GoogleTagManager } from '@next/third-parties/google';

import { CookieBanner } from './cookie-banner';
import { cookieDescription } from './cookie-config';
import { CookieSettingsDialog, CookieToggleState } from './cookie-settings-dialog';

type GoogleMarketingConsentContextValue = {
  openCookieSettings: () => void;
};

const GoogleMarketingConsentContext = createContext<GoogleMarketingConsentContextValue>({
  openCookieSettings: () => {},
});

export function useGoogleMarketingConsent(): GoogleMarketingConsentContextValue {
  return useContext(GoogleMarketingConsentContext);
}

function toToggleState(consent: GoogleConsentState | null): CookieToggleState {
  return {
    personalization: consent?.personalization_storage === 'granted',
    statistics: consent?.analytics_storage === 'granted',
    marketing: consent?.ad_storage === 'granted' && consent.ad_user_data === 'granted',
  };
}

function selectedConsent(state: CookieToggleState): GoogleConsentState {
  return {
    ad_storage: state.marketing ? 'granted' : 'denied',
    analytics_storage: state.statistics ? 'granted' : 'denied',
    ad_user_data: state.marketing ? 'granted' : 'denied',
    ad_personalization: state.personalization ? 'granted' : 'denied',
    functionality_storage: 'granted',
    personalization_storage: state.personalization ? 'granted' : 'denied',
    security_storage: 'granted',
  };
}

export function GoogleTagManagerConsentProvider({
  autoGrant = false,
  children,
  gtmId,
}: {
  autoGrant?: boolean;
  children: ReactNode;
  gtmId?: string;
}) {
  const [decisionMade, setDecisionMade] = useState<boolean | null>(null);
  const [consent, setConsent] = useState<GoogleConsentState | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [hasLoadedGTM, setHasLoadedGTM] = useState(false);

  const initializeDataLayer = useCallback(() => {
    if (typeof window !== 'undefined') {
      window.dataLayer = window.dataLayer || [];
    }
  }, []);

  const setGTMCookie = useCallback((value: GoogleConsentCookie) => {
    if (typeof window === 'undefined') return;

    const jsonString = JSON.stringify(value);
    const date = new Date();
    date.setTime(date.getTime() + 365 * 24 * 60 * 60 * 1000);
    const secure = window.location.protocol === 'https:' ? '; Secure' : '';

    document.cookie = `${GOOGLE_CONSENT_COOKIE_NAME}=${jsonString}; expires=${date.toUTCString()}; path=/; SameSite=Lax${secure}`;
  }, []);

  const pushConsentUpdate = useCallback(() => {
    if (typeof window === 'undefined') return;
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({ event: GOOGLE_CONSENT_UPDATE_EVENT });
  }, []);

  const persistDecision = useCallback(
    (nextConsent: GoogleConsentState, source: GoogleConsentSource, notifyGTM: boolean) => {
      const cookie = createGoogleConsentCookie(nextConsent, source);
      setGTMCookie(cookie);
      setCookieObject(
        GOOGLE_ANALYTICS_CONSENT_COOKIE_NAME,
        { granted: nextConsent.analytics_storage === 'granted' },
        365,
      );
      setDecisionMade(true);
      setConsent(nextConsent);
      if (nextConsent.analytics_storage === 'granted') {
        setHasLoadedGTM(true);
      }
      if (notifyGTM) {
        pushConsentUpdate();
      }
    },
    [pushConsentUpdate, setGTMCookie],
  );

  const handleDecision = useCallback(
    (nextConsent: GoogleConsentState) => {
      persistDecision(nextConsent, 'user', true);
      setDialogOpen(false);
    },
    [persistDecision],
  );

  useEffect(() => {
    initializeDataLayer();
    const rawConsent = getCookieValue(GOOGLE_CONSENT_COOKIE_NAME);
    const existingConsent = parseGoogleConsentCookie(rawConsent);

    if (existingConsent) {
      const existingState = getGoogleConsentState(existingConsent);
      if (!rawConsent?.includes(`\"version\":${GOOGLE_CONSENT_COOKIE_VERSION}`)) {
        setGTMCookie(existingConsent);
      }
      setDecisionMade(true);
      setConsent(existingState);
      if (existingState.analytics_storage === 'granted') {
        setHasLoadedGTM(true);
      }
    } else if (rawConsent) {
      setDecisionMade(false);
    } else if (autoGrant) {
      persistDecision(ALL_GOOGLE_CONSENT_GRANTED, 'auto', false);
    } else {
      setDecisionMade(false);
    }
  }, [autoGrant, initializeDataLayer, persistDecision, setGTMCookie]);

  const defaultToggleState = useMemo(() => toToggleState(consent), [consent]);
  const analyticsGranted = consent?.analytics_storage === 'granted';
  const shouldRenderGTM = Boolean(gtmId && (analyticsGranted || hasLoadedGTM));
  const contextValue = useMemo(
    () => ({
      openCookieSettings: () => setDialogOpen(true),
    }),
    [],
  );

  return (
    <GoogleMarketingConsentContext.Provider value={contextValue}>
      {shouldRenderGTM && gtmId ? <GoogleTagManager gtmId={gtmId} /> : null}
      {children}
      {decisionMade === false && !dialogOpen ? (
        <CookieBanner
          header="Cookie Settings"
          message={<span>{cookieDescription}</span>}
          acceptText="Accept All"
          manageText="Manage Settings"
          onAccept={() => handleDecision(ALL_GOOGLE_CONSENT_GRANTED)}
          onManage={() => setDialogOpen(true)}
        />
      ) : null}
      {decisionMade !== null ? (
        <CookieSettingsDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          defaultState={defaultToggleState}
          onAcceptAll={() => handleDecision(ALL_GOOGLE_CONSENT_GRANTED)}
          onAcceptSelected={(state) => handleDecision(selectedConsent(state))}
        />
      ) : null}
    </GoogleMarketingConsentContext.Provider>
  );
}
