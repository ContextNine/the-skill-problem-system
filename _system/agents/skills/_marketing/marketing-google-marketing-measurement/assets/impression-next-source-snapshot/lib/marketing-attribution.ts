import { getCookieValue, setSharedCookieValue } from '@/lib/browser-apis/shared-cookies';

export const MARKETING_FIRST_TOUCH_COOKIE_NAME = 'marketing_first_touch_v1';
const MARKETING_FIRST_TOUCH_MAX_AGE_SECONDS = 60 * 60 * 24 * 90;

export type MarketingFirstTouch = {
  captured_at: string;
  landing_host: string;
  landing_path: string;
  landing_url: string;
  referrer: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  utm_term: string | null;
  utm_content: string | null;
  utm_id: string | null;
  gclid: string | null;
  fbclid: string | null;
  msclkid: string | null;
  ttclid: string | null;
};

function getParamValue(url: URL, key: string): string | null {
  const value = url.searchParams.get(key);
  return value && value.length > 0 ? value : null;
}

export function getMarketingFirstTouch(): MarketingFirstTouch | null {
  const value = getCookieValue(MARKETING_FIRST_TOUCH_COOKIE_NAME);
  if (!value) {
    return null;
  }

  try {
    return JSON.parse(value) as MarketingFirstTouch;
  } catch {
    return null;
  }
}

export function setMarketingFirstTouch(firstTouch: MarketingFirstTouch): void {
  setSharedCookieValue(MARKETING_FIRST_TOUCH_COOKIE_NAME, JSON.stringify(firstTouch), {
    maxAgeSeconds: MARKETING_FIRST_TOUCH_MAX_AGE_SECONDS,
    includeHostOnlyCopy: false,
  });
}

export function captureMarketingFirstTouchIfMissing(): MarketingFirstTouch | null {
  const existing = getMarketingFirstTouch();
  if (existing) {
    setMarketingFirstTouch(existing);
    return existing;
  }

  if (typeof window === 'undefined') {
    return null;
  }

  const url = new URL(window.location.href);
  const firstTouch: MarketingFirstTouch = {
    captured_at: new Date().toISOString(),
    landing_host: url.host,
    landing_path: url.pathname,
    landing_url: url.href,
    referrer: document.referrer || null,
    utm_source: getParamValue(url, 'utm_source'),
    utm_medium: getParamValue(url, 'utm_medium'),
    utm_campaign: getParamValue(url, 'utm_campaign'),
    utm_term: getParamValue(url, 'utm_term'),
    utm_content: getParamValue(url, 'utm_content'),
    utm_id: getParamValue(url, 'utm_id'),
    gclid: getParamValue(url, 'gclid'),
    fbclid: getParamValue(url, 'fbclid'),
    msclkid: getParamValue(url, 'msclkid'),
    ttclid: getParamValue(url, 'ttclid'),
  };

  setMarketingFirstTouch(firstTouch);
  return firstTouch;
}

export function getMarketingFirstTouchPostHogPersonProperties(): Record<string, string> {
  const firstTouch = getMarketingFirstTouch();
  if (!firstTouch) {
    return {};
  }

  const properties: Record<string, string> = {};
  const mapping = {
    first_touch_utm_source: firstTouch.utm_source,
    first_touch_utm_medium: firstTouch.utm_medium,
    first_touch_utm_campaign: firstTouch.utm_campaign,
    first_touch_utm_term: firstTouch.utm_term,
    first_touch_utm_content: firstTouch.utm_content,
    first_touch_utm_id: firstTouch.utm_id,
    first_touch_gclid: firstTouch.gclid,
    first_touch_fbclid: firstTouch.fbclid,
    first_touch_msclkid: firstTouch.msclkid,
    first_touch_ttclid: firstTouch.ttclid,
    first_touch_landing_host: firstTouch.landing_host,
    first_touch_landing_path: firstTouch.landing_path,
    first_touch_referrer: firstTouch.referrer,
    first_touch_captured_at: firstTouch.captured_at,
  } satisfies Record<string, string | null>;

  for (const [key, value] of Object.entries(mapping)) {
    if (value) {
      properties[key] = value;
    }
  }

  return properties;
}

export function getMarketingAttributionForSignup(pagePath?: string): Record<string, string | null> {
  if (typeof window === 'undefined') {
    return {};
  }

  const url = new URL(window.location.href);
  const firstTouch = captureMarketingFirstTouchIfMissing();

  return {
    current_host: url.host,
    current_url: url.href,
    page_path: pagePath ?? url.pathname,
    referrer: document.referrer || null,
    utm_source: getParamValue(url, 'utm_source'),
    utm_medium: getParamValue(url, 'utm_medium'),
    utm_campaign: getParamValue(url, 'utm_campaign'),
    utm_term: getParamValue(url, 'utm_term'),
    utm_content: getParamValue(url, 'utm_content'),
    utm_id: getParamValue(url, 'utm_id'),
    gclid: getParamValue(url, 'gclid'),
    fbclid: getParamValue(url, 'fbclid'),
    msclkid: getParamValue(url, 'msclkid'),
    ttclid: getParamValue(url, 'ttclid'),
    first_touch_utm_source: firstTouch?.utm_source ?? null,
    first_touch_utm_medium: firstTouch?.utm_medium ?? null,
    first_touch_utm_campaign: firstTouch?.utm_campaign ?? null,
    first_touch_utm_term: firstTouch?.utm_term ?? null,
    first_touch_utm_content: firstTouch?.utm_content ?? null,
    first_touch_utm_id: firstTouch?.utm_id ?? null,
    first_touch_gclid: firstTouch?.gclid ?? null,
    first_touch_fbclid: firstTouch?.fbclid ?? null,
    first_touch_msclkid: firstTouch?.msclkid ?? null,
    first_touch_ttclid: firstTouch?.ttclid ?? null,
    first_touch_landing_host: firstTouch?.landing_host ?? null,
    first_touch_landing_path: firstTouch?.landing_path ?? null,
    first_touch_referrer: firstTouch?.referrer ?? null,
    first_touch_captured_at: firstTouch?.captured_at ?? null,
  };
}
