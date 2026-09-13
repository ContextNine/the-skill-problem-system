export const GOOGLE_CONSENT_COOKIE_NAME = 'gtm_cookie_consent';
export const GOOGLE_ANALYTICS_CONSENT_COOKIE_NAME = 'analytics_consent';
export const GOOGLE_CONSENT_UPDATE_EVENT = 'consent_preferences_updated';
export const GOOGLE_CONSENT_COOKIE_VERSION = 2;

export const GOOGLE_CONSENT_TYPES = [
  'ad_storage',
  'analytics_storage',
  'ad_user_data',
  'ad_personalization',
  'functionality_storage',
  'personalization_storage',
  'security_storage',
] as const;

export type GoogleConsentType = (typeof GOOGLE_CONSENT_TYPES)[number];
export type GoogleConsentValue = 'granted' | 'denied';
export type GoogleConsentState = Record<GoogleConsentType, GoogleConsentValue>;
export type GoogleConsentSource = 'auto' | 'user' | 'legacy';

export type GoogleConsentCookie = GoogleConsentState & {
  version: typeof GOOGLE_CONSENT_COOKIE_VERSION;
  source: GoogleConsentSource;
  updated_at: string;
};

export const ALL_GOOGLE_CONSENT_GRANTED: GoogleConsentState = {
  ad_storage: 'granted',
  analytics_storage: 'granted',
  ad_user_data: 'granted',
  ad_personalization: 'granted',
  functionality_storage: 'granted',
  personalization_storage: 'granted',
  security_storage: 'granted',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function createGoogleConsentCookie(
  consent: GoogleConsentState,
  source: GoogleConsentSource,
  updatedAt = new Date().toISOString(),
): GoogleConsentCookie {
  return {
    version: GOOGLE_CONSENT_COOKIE_VERSION,
    source,
    updated_at: updatedAt,
    ...consent,
  };
}

export function parseGoogleConsentCookie(value: unknown): GoogleConsentCookie | null {
  let candidate = value;

  if (typeof candidate === 'string') {
    try {
      candidate = JSON.parse(candidate);
    } catch {
      return null;
    }
  }

  if (!isRecord(candidate)) {
    return null;
  }

  const consent = {} as GoogleConsentState;
  for (const type of GOOGLE_CONSENT_TYPES) {
    const state = candidate[type];
    if (state !== 'granted' && state !== 'denied') {
      return null;
    }
    consent[type] = state;
  }

  const source =
    candidate.source === 'auto' || candidate.source === 'user' || candidate.source === 'legacy'
      ? candidate.source
      : 'legacy';
  const updatedAt = typeof candidate.updated_at === 'string' ? candidate.updated_at : new Date(0).toISOString();

  return createGoogleConsentCookie(consent, source, updatedAt);
}

export function getGoogleConsentState(cookie: GoogleConsentCookie): GoogleConsentState {
  return Object.fromEntries(GOOGLE_CONSENT_TYPES.map((type) => [type, cookie[type]])) as GoogleConsentState;
}
