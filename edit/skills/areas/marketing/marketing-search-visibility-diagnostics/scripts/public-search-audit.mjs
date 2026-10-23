#!/usr/bin/env node

import { writeFile } from 'node:fs/promises';

const USER_AGENTS = {
  browser: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/150 Safari/537.36',
  googlebot: 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
  inspection: 'Mozilla/5.0 (compatible; Google-InspectionTool/1.0;)',
  bingbot: 'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)',
};

function usage() {
  console.error('Usage: public-search-audit.mjs <https-url> [--pages /,/about] [--output report.json]');
  process.exit(2);
}

function parseArgs(argv) {
  if (!argv[0] || argv[0].startsWith('--')) usage();
  const options = { url: argv[0], pages: ['/'], output: null };
  for (let index = 1; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--pages' && argv[index + 1]) {
      options.pages = argv[++index].split(',').map((value) => value.trim()).filter(Boolean);
    } else if (argument === '--output' && argv[index + 1]) {
      options.output = argv[++index];
    } else {
      usage();
    }
  }
  return options;
}

function normalizeUrl(value) {
  const url = new URL(value);
  url.hash = '';
  if (url.pathname !== '/') url.pathname = url.pathname.replace(/\/+$/, '');
  return url.toString();
}

function getAttribute(tag, name) {
  const expression = new RegExp(`(?:^|\\s)${name}\\s*=\\s*(?:["']([^"']*)["']|([^\\s>]+))`, 'i');
  const match = tag.match(expression);
  return match ? (match[1] ?? match[2] ?? '') : null;
}

function parseDocument(html) {
  const headEnd = html.search(/<\/head\s*>/i);
  const head = headEnd >= 0 ? html.slice(0, headEnd) : '';
  const metaTags = [...head.matchAll(/<meta\b[^>]*>/gi)].map((match) => match[0]);
  const linkTags = [...head.matchAll(/<link\b[^>]*>/gi)].map((match) => match[0]);
  const descriptionTag = metaTags.find((tag) => getAttribute(tag, 'name')?.toLowerCase() === 'description');
  const robotsTag = metaTags.find((tag) => getAttribute(tag, 'name')?.toLowerCase() === 'robots');
  const canonicalTag = linkTags.find((tag) => getAttribute(tag, 'rel')?.toLowerCase().split(/\s+/).includes('canonical'));
  const title = head.match(/<title\b[^>]*>([\s\S]*?)<\/title\s*>/i)?.[1]?.replace(/\s+/g, ' ').trim() ?? null;

  return {
    headClosed: headEnd >= 0,
    headEnd,
    title,
    description: descriptionTag ? getAttribute(descriptionTag, 'content') : null,
    canonical: canonicalTag ? getAttribute(canonicalTag, 'href') : null,
    robots: robotsTag ? getAttribute(robotsTag, 'content') : null,
    h1Count: [...html.matchAll(/<h1\b/gi)].length,
    jsonLdCount: [...html.matchAll(/<script\b[^>]*type=["']application\/ld\+json["'][^>]*>/gi)].length,
  };
}

function cacheHeaders(headers) {
  return Object.fromEntries(
    ['cache-control', 'cf-cache-status', 'age', 'vary', 'x-robots-tag']
      .map((name) => [name, headers.get(name)])
      .filter(([, value]) => value !== null),
  );
}

async function fetchWithRedirects(input, userAgent, limit = 8) {
  const hops = [];
  let current = input;
  for (let index = 0; index <= limit; index += 1) {
    const response = await fetch(current, {
      redirect: 'manual',
      headers: { accept: 'text/html,application/xhtml+xml', 'user-agent': userAgent },
    });
    const location = response.headers.get('location');
    hops.push({ url: current, status: response.status, location, headers: cacheHeaders(response.headers) });
    if (!location || response.status < 300 || response.status >= 400) {
      return { response, hops, finalUrl: current };
    }
    current = new URL(location, current).toString();
  }
  throw new Error(`Redirect limit exceeded for ${input}`);
}

async function auditHtml(url, label, userAgent) {
  try {
    const { response, hops, finalUrl } = await fetchWithRedirects(url, userAgent);
    const contentType = response.headers.get('content-type') ?? '';
    const html = await response.text();
    const document = parseDocument(html);
    const headerRobots = response.headers.get('x-robots-tag') ?? '';
    const robots = `${document.robots ?? ''},${headerRobots}`.toLowerCase();
    const failures = [];
    if (!response.ok) failures.push(`final status is ${response.status}`);
    if (!contentType.toLowerCase().includes('text/html')) failures.push(`content-type is ${contentType || '<missing>'}`);
    if (!document.headClosed) failures.push('document has no closing head');
    if (!document.title) failures.push('title is missing from head');
    if (!document.description) failures.push('description is missing from head');
    if (!document.canonical) failures.push('canonical is missing from head');
    if (robots.split(/[;,]/).map((value) => value.trim()).includes('noindex')) failures.push('response is noindex');
    if (document.h1Count < 1) failures.push('document has no h1');

    return {
      label,
      requestedUrl: url,
      finalUrl,
      status: response.status,
      contentType,
      headers: cacheHeaders(response.headers),
      redirects: hops,
      document,
      failures,
      ok: failures.length === 0,
    };
  } catch (error) {
    return { label, requestedUrl: url, ok: false, failures: [error instanceof Error ? error.message : String(error)] };
  }
}

async function fetchText(url, accept) {
  try {
    const response = await fetch(url, { redirect: 'follow', headers: { accept, 'user-agent': USER_AGENTS.googlebot } });
    return { url, status: response.status, ok: response.ok, text: await response.text(), headers: cacheHeaders(response.headers) };
  } catch (error) {
    return { url, status: null, ok: false, text: '', error: error instanceof Error ? error.message : String(error), headers: {} };
  }
}

function robotsBlocksAll(text) {
  const lines = text.split(/\r?\n/).map((line) => line.replace(/#.*/, '').trim()).filter(Boolean);
  let applies = false;
  let disallowAll = false;
  let allowRoot = false;
  for (const line of lines) {
    const [rawName, ...rawValue] = line.split(':');
    const name = rawName.trim().toLowerCase();
    const value = rawValue.join(':').trim();
    if (name === 'user-agent') {
      applies = value === '*';
    } else if (applies && name === 'disallow' && value === '/') {
      disallowAll = true;
    } else if (applies && name === 'allow' && value === '/') {
      allowRoot = true;
    }
  }
  return disallowAll && !allowRoot;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const canonical = new URL(options.url);
  if (canonical.protocol !== 'https:') throw new Error('Canonical URL must use https');
  canonical.pathname = '/';
  canonical.search = '';
  canonical.hash = '';

  const pageUrls = options.pages.map((page) => new URL(page, canonical).toString());
  const homepageAudits = await Promise.all(
    Object.entries(USER_AGENTS).map(([label, userAgent]) => auditHtml(pageUrls[0], label, userAgent)),
  );
  const additionalPages = await Promise.all(
    pageUrls.slice(1).map((url) => auditHtml(url, 'browser', USER_AGENTS.browser)),
  );

  const robots = await fetchText(new URL('/robots.txt', canonical).toString(), 'text/plain,*/*');
  const sitemapMatches = [...robots.text.matchAll(/^\s*Sitemap:\s*(\S+)/gim)].map((match) => match[1]);
  const sitemapUrl = sitemapMatches[0] ?? new URL('/sitemap.xml', canonical).toString();
  const sitemap = await fetchText(sitemapUrl, 'application/xml,text/xml,*/*');
  const sitemapLocations = [...sitemap.text.matchAll(/<loc>\s*([^<]+)\s*<\/loc>/gi)].map((match) => match[1].trim());

  const redirectInputs = new Set([
    canonical.toString(),
    `http://${canonical.host}/`,
    canonical.hostname.startsWith('www.') ? null : `https://www.${canonical.hostname}/`,
    canonical.hostname.startsWith('www.') ? null : `http://www.${canonical.hostname}/`,
  ].filter(Boolean));
  const redirects = await Promise.all(
    [...redirectInputs].map(async (url) => {
      try {
        const result = await fetchWithRedirects(url, USER_AGENTS.browser);
        return { requestedUrl: url, finalUrl: result.finalUrl, finalStatus: result.response.status, hops: result.hops };
      } catch (error) {
        return { requestedUrl: url, error: error instanceof Error ? error.message : String(error) };
      }
    }),
  );

  const failures = [];
  for (const audit of [...homepageAudits, ...additionalPages]) {
    for (const failure of audit.failures ?? []) failures.push(`${audit.label} ${audit.requestedUrl}: ${failure}`);
  }
  if (!robots.ok) failures.push(`robots.txt status is ${robots.status ?? 'unavailable'}`);
  if (robotsBlocksAll(robots.text)) failures.push('robots.txt blocks all crawlers');
  if (!sitemap.ok) failures.push(`sitemap status is ${sitemap.status ?? 'unavailable'}`);

  const report = {
    generatedAt: new Date().toISOString(),
    canonicalOrigin: canonical.origin,
    pages: pageUrls,
    ok: failures.length === 0,
    failures,
    homepageAudits,
    additionalPages,
    redirects,
    robots: { url: robots.url, status: robots.status, headers: robots.headers, blocksAll: robotsBlocksAll(robots.text), sitemapUrls: sitemapMatches },
    sitemap: { url: sitemap.url, status: sitemap.status, headers: sitemap.headers, urlCount: sitemapLocations.length, urls: sitemapLocations },
  };

  const serialized = `${JSON.stringify(report, null, 2)}\n`;
  if (options.output) await writeFile(options.output, serialized, 'utf8');
  process.stdout.write(serialized);
  process.exitCode = report.ok ? 0 : 1;
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 2;
});
