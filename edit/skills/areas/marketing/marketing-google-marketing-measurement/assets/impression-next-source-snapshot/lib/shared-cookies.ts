import { parse } from 'cookie';

export type SharedCookieOptions = {
  maxAgeSeconds?: number;
  expires?: Date;
  includeHostOnlyCopy?: boolean;
};

function getSharedCookieDomain(): string | undefined {
  if (typeof window === 'undefined') return undefined;

  const hostname = window.location.hostname;
  if (!hostname) return undefined;

  // Browsers do not support a shared parent-domain cookie for localhost.
  if (hostname === 'localhost' || hostname.endsWith('.localhost')) {
    return undefined;
  }

  const parts = hostname.split('.');
  if (parts.length < 2) return undefined;

  return `.${parts.slice(-2).join('.')}`;
}

export function getCookieValue(name: string): string | undefined {
  if (typeof window === 'undefined') return undefined;

  const cookies = parse(document.cookie || '');
  return cookies[name];
}

export function setSharedCookieValue(name: string, value: string, options: SharedCookieOptions = {}): void {
  if (typeof window === 'undefined') return;

  const secure = window.location.protocol === 'https:';
  let cookieBase = `${name}=${encodeURIComponent(value)}; path=/; SameSite=Lax`;

  if (options.maxAgeSeconds !== undefined) {
    cookieBase += `; max-age=${options.maxAgeSeconds}`;
  }

  if (options.expires) {
    cookieBase += `; expires=${options.expires.toUTCString()}`;
  }

  const cookieWithSecurity = `${cookieBase}${secure ? '; secure' : ''}`;
  const sharedDomain = getSharedCookieDomain();
  if (sharedDomain && options.includeHostOnlyCopy === false) {
    document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax${secure ? '; secure' : ''}`;
    document.cookie = `${cookieBase}; domain=${sharedDomain}${secure ? '; secure' : ''}`;
    return;
  }

  document.cookie = cookieWithSecurity;
  if (sharedDomain) {
    document.cookie = `${cookieBase}; domain=${sharedDomain}${secure ? '; secure' : ''}`;
  }
}
export function deleteSharedCookie(name: string): void {
  if (typeof window === 'undefined') return;

  const secure = window.location.protocol === 'https:';
  const sharedDomain = getSharedCookieDomain();

  const cookieBase = `${name}=; path=/; max-age=0; SameSite=Lax`;
  document.cookie = `${cookieBase}${secure ? '; secure' : ''}`;

  if (sharedDomain) {
    document.cookie = `${cookieBase}; domain=${sharedDomain}${secure ? '; secure' : ''}`;
  }
}
