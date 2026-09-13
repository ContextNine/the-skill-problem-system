// utils/cookies.ts
import { parse, serialize } from 'cookie';

function getUserPreferencesCookieDomains(currentHostname: string): string[] {
  const domains = new Set<string>([currentHostname, `.${currentHostname}`]);

  if (currentHostname === 'localhost' || currentHostname.endsWith('.localhost')) {
    domains.add('localhost');
    domains.add('.localhost');
  }

  return [...domains];
}

function clearLocalhostUserPreferencesCookieVariants(name: string, currentHostname: string) {
  if (name !== 'userPreferences') {
    return;
  }

  const expiredAt = 'Thu, 01 Jan 1970 00:00:00 GMT';
  document.cookie = `${name}=; expires=${expiredAt}; path=/; SameSite=Lax`;
  for (const domain of getUserPreferencesCookieDomains(currentHostname)) {
    document.cookie = `${name}=; expires=${expiredAt}; path=/; domain=${domain}; SameSite=Lax`;
  }
}

export function setCookieObject(
  name: string,
  value: object,
  days: number = 60,
) {
  if (typeof window === 'undefined') return;

  const jsonString = JSON.stringify(value);
  const date = new Date();
  date.setTime(date.getTime() + days * 24 * 60 * 60 * 1000);
  const expires = 'expires=' + date.toUTCString();
  const domain = window.location.hostname;
  const secure = window.location.protocol === 'https:';

  clearLocalhostUserPreferencesCookieVariants(name, domain);
  document.cookie = `${name}=${jsonString}; ${expires}; path=/; domain=${domain}${secure ? '; secure' : ''}; SameSite=Lax`;
}

export function getCookieObject(name: string): Record<string, any> | null {
  if (typeof window === 'undefined') return null;
  const cookies = parse(document.cookie);
  const cookieValue = cookies[name];

  return cookieValue ? JSON.parse(cookieValue) : null;
}

export function getServerSideCookieObject(
  req: Request,
  name: string,
): Record<string, any> | null {
  const cookies = parse(req.headers.get('cookie') || '');
  const cookieValue = cookies[name];

  return cookieValue ? JSON.parse(cookieValue) : null;
}
