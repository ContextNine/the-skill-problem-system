#!/usr/bin/env node

const target = process.argv[2];

if (!target) {
  console.error('Usage: audit-live-nextjs-seo.mjs https://example.com');
  process.exit(2);
}

let base;
try {
  base = new URL(target);
} catch {
  console.error(`Invalid URL: ${target}`);
  process.exit(2);
}

if (!['http:', 'https:'].includes(base.protocol)) {
  console.error('URL must use http or https');
  process.exit(2);
}

base.pathname = '/';
base.search = '';
base.hash = '';

const userAgents = {
  browser: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36',
  googlebot: 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
  social: 'facebookexternalhit/1.1',
};

function stripTags(value = '') {
  return value
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/\s+/g, ' ')
    .trim();
}

function firstMatch(html, patterns) {
  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match?.[1]) return stripTags(match[1]);
  }
  return null;
}

function attrFromTag(tag, name) {
  const quoted = tag.match(new RegExp(`\\b${name}\\s*=\\s*(["'])(.*?)\\1`, 'i'));
  if (quoted) return quoted[2];
  const bare = tag.match(new RegExp(`\\b${name}\\s*=\\s*([^\\s>]+)`, 'i'));
  return bare?.[1] ?? null;
}

function findMeta(html, selectorName, selectorValue) {
  const tags = html.match(/<meta\b[^>]*>/gi) ?? [];
  for (const tag of tags) {
    if ((attrFromTag(tag, selectorName) ?? '').toLowerCase() === selectorValue.toLowerCase()) {
      return attrFromTag(tag, 'content');
    }
  }
  return null;
}

function findLink(html, relValue) {
  const tags = html.match(/<link\b[^>]*>/gi) ?? [];
  for (const tag of tags) {
    const rel = (attrFromTag(tag, 'rel') ?? '').toLowerCase().split(/\s+/);
    if (rel.includes(relValue.toLowerCase())) return attrFromTag(tag, 'href');
  }
  return null;
}

function inspectHtml(html, requestedUrl, finalUrl) {
  const head = html.match(/<head\b[^>]*>([\s\S]*?)<\/head>/i)?.[1] ?? '';
  const body = html.match(/<body\b[^>]*>([\s\S]*?)<\/body>/i)?.[1] ?? '';
  const h1s = [...html.matchAll(/<h1\b[^>]*>([\s\S]*?)<\/h1>/gi)].map((match) => stripTags(match[1]));
  const jsonLd = [...html.matchAll(/<script\b[^>]*type\s*=\s*(["'])application\/ld\+json\1[^>]*>([\s\S]*?)<\/script>/gi)];
  const jsonLdErrors = [];

  for (const [, , value] of jsonLd) {
    try {
      JSON.parse(value);
    } catch (error) {
      jsonLdErrors.push(error instanceof Error ? error.message : String(error));
    }
  }

  const titleHead = firstMatch(head, [/<title\b[^>]*>([\s\S]*?)<\/title>/i]);
  const titleBody = firstMatch(body, [/<title\b[^>]*>([\s\S]*?)<\/title>/i]);
  const descriptionHead = findMeta(head, 'name', 'description');
  const descriptionBody = findMeta(body, 'name', 'description');
  const canonicalHead = findLink(head, 'canonical');
  const canonicalBody = findLink(body, 'canonical');
  const robots = findMeta(html, 'name', 'robots');
  const ogImage = findMeta(html, 'property', 'og:image');
  const twitterImage = findMeta(html, 'name', 'twitter:image');
  const findings = [];

  if (!titleHead && titleBody) findings.push('title_streamed_or_placed_in_body');
  if (!descriptionHead && descriptionBody) findings.push('description_streamed_or_placed_in_body');
  if (!canonicalHead && canonicalBody) findings.push('canonical_streamed_or_placed_in_body');
  if (!titleHead && !titleBody) findings.push('missing_title');
  if (!descriptionHead && !descriptionBody) findings.push('missing_description');
  if (!canonicalHead && !canonicalBody) findings.push('missing_canonical');
  if (h1s.length === 0) findings.push('missing_h1');
  if (h1s.length > 1) findings.push('multiple_h1');
  if (jsonLd.length === 0) findings.push('missing_json_ld');
  if (jsonLdErrors.length) findings.push('invalid_json_ld');
  if (!ogImage) findings.push('missing_open_graph_image');

  const canonical = canonicalHead ?? canonicalBody;
  if (canonical) {
    try {
      const canonicalUrl = new URL(canonical, finalUrl);
      const final = new URL(finalUrl);
      if (canonicalUrl.protocol !== 'https:') findings.push('canonical_not_https');
      if (canonicalUrl.hostname !== final.hostname) findings.push('canonical_host_differs_from_final_host');
    } catch {
      findings.push('invalid_canonical_url');
    }
  }

  return {
    requestedUrl,
    finalUrl,
    bytes: Buffer.byteLength(html),
    title: titleHead ?? titleBody,
    titleLocation: titleHead ? 'head' : titleBody ? 'body' : null,
    description: descriptionHead ?? descriptionBody,
    descriptionLocation: descriptionHead ? 'head' : descriptionBody ? 'body' : null,
    canonical,
    canonicalLocation: canonicalHead ? 'head' : canonicalBody ? 'body' : null,
    robots,
    ogImage,
    twitterImage,
    h1Count: h1s.length,
    h1s,
    jsonLdCount: jsonLd.length,
    jsonLdErrors,
    findings,
  };
}

async function fetchText(url, options = {}) {
  const startedAt = performance.now();
  const response = await fetch(url, {
    redirect: options.redirect ?? 'follow',
    headers: options.userAgent ? { 'user-agent': options.userAgent } : {},
    signal: AbortSignal.timeout(20_000),
  });
  const text = await response.text();
  return {
    requestedUrl: url,
    status: response.status,
    location: response.headers.get('location'),
    finalUrl: response.url,
    contentType: response.headers.get('content-type'),
    cacheControl: response.headers.get('cache-control'),
    xRobotsTag: response.headers.get('x-robots-tag'),
    elapsedMs: Math.round(performance.now() - startedAt),
    text,
  };
}

async function inspectRedirect(url) {
  try {
    const response = await fetchText(url, { redirect: 'manual', userAgent: userAgents.googlebot });
    return {
      url,
      status: response.status,
      location: response.location,
      permanent: [301, 308].includes(response.status),
    };
  } catch (error) {
    return { url, error: error instanceof Error ? error.message : String(error) };
  }
}

function sitemapSummary(xml, origin) {
  const locations = [...xml.matchAll(/<loc>([\s\S]*?)<\/loc>/gi)].map((match) => stripTags(match[1]));
  const lastmods = [...xml.matchAll(/<lastmod>([\s\S]*?)<\/lastmod>/gi)].map((match) => stripTags(match[1]));
  const invalidLocations = [];

  for (const location of locations) {
    try {
      const parsed = new URL(location);
      if (parsed.origin !== origin || parsed.search || parsed.hash || parsed.protocol !== 'https:') invalidLocations.push(location);
    } catch {
      invalidLocations.push(location);
    }
  }

  const uniqueLastmods = new Set(lastmods);
  const allLastmodsIdentical = lastmods.length > 1 && uniqueLastmods.size === 1;
  const nearNow = lastmods.filter((value) => {
    const timestamp = Date.parse(value);
    return Number.isFinite(timestamp) && Math.abs(Date.now() - timestamp) < 24 * 60 * 60 * 1000;
  }).length;

  return {
    urlCount: locations.length,
    duplicateUrlCount: locations.length - new Set(locations).size,
    invalidLocations,
    lastmodCount: lastmods.length,
    uniqueLastmodCount: uniqueLastmods.size,
    allLastmodsIdentical,
    lastmodsWithin24Hours: nearNow,
    findings: [
      ...(invalidLocations.length ? ['noncanonical_or_invalid_sitemap_locations'] : []),
      ...(allLastmodsIdentical && nearNow === lastmods.length ? ['all_sitemap_lastmods_identical_and_current'] : []),
    ],
  };
}

async function main() {
  const preferred = new URL(base);
  preferred.protocol = 'https:';
  const http = new URL(preferred);
  http.protocol = 'http:';
  const alternateHost = new URL(preferred);
  alternateHost.hostname = preferred.hostname.startsWith('www.') ? preferred.hostname.slice(4) : `www.${preferred.hostname}`;
  const alternateHttp = new URL(alternateHost);
  alternateHttp.protocol = 'http:';

  const redirectMatrix = await Promise.all(
    [preferred, http, alternateHost, alternateHttp].map((url) => inspectRedirect(url.href)),
  );
  const redirectFindings = [];
  const [preferredResult, httpResult, alternateHostResult, alternateHttpResult] = redirectMatrix;
  if (preferredResult.status !== 200) redirectFindings.push('preferred_https_not_200');
  for (const [name, result] of [
    ['http', httpResult],
    ['alternate_https', alternateHostResult],
    ['alternate_http', alternateHttpResult],
  ]) {
    if (!result.permanent) redirectFindings.push(`${name}_not_permanent_redirect`);
    if (result.location) {
      try {
        const destination = new URL(result.location, result.url);
        if (destination.href !== preferred.href) redirectFindings.push(`${name}_does_not_redirect_directly_to_preferred`);
      } catch {
        redirectFindings.push(`${name}_has_invalid_redirect_location`);
      }
    } else {
      redirectFindings.push(`${name}_missing_redirect_location`);
    }
  }

  const pages = {};
  for (const [name, userAgent] of Object.entries(userAgents)) {
    const response = await fetchText(preferred.href, { userAgent });
    pages[name] = {
      status: response.status,
      contentType: response.contentType,
      cacheControl: response.cacheControl,
      xRobotsTag: response.xRobotsTag,
      elapsedMs: response.elapsedMs,
      ...inspectHtml(response.text, preferred.href, response.finalUrl),
    };
  }

  const robotsUrl = new URL('/robots.txt', preferred).href;
  const sitemapUrl = new URL('/sitemap.xml', preferred).href;
  const [robots, sitemap] = await Promise.all([fetchText(robotsUrl), fetchText(sitemapUrl)]);
  const robotsSitemaps = [...robots.text.matchAll(/^\s*Sitemap:\s*(\S+)\s*$/gim)].map((match) => match[1]);
  const nonstandardRobotsDirectives = [...robots.text.matchAll(/^\s*([A-Za-z][A-Za-z-]*):/gm)]
    .map((match) => match[1].toLowerCase())
    .filter((name) => !['user-agent', 'allow', 'disallow', 'sitemap', 'crawl-delay', 'host'].includes(name));

  const report = {
    schemaVersion: 1,
    auditedAt: new Date().toISOString(),
    target: preferred.href,
    redirectMatrix,
    redirectFindings,
    pages,
    robots: {
      url: robotsUrl,
      status: robots.status,
      sitemapDeclarations: robotsSitemaps,
      nonstandardDirectives: [...new Set(nonstandardRobotsDirectives)],
      findings: [
        ...(robots.status !== 200 ? ['robots_not_200'] : []),
        ...(robotsSitemaps.length === 0 ? ['robots_missing_sitemap'] : []),
        ...(nonstandardRobotsDirectives.length ? ['robots_has_nonstandard_directives'] : []),
      ],
    },
    sitemap: {
      url: sitemapUrl,
      status: sitemap.status,
      ...(sitemap.status === 200 ? sitemapSummary(sitemap.text, preferred.origin) : { findings: ['sitemap_not_200'] }),
    },
  };

  console.log(JSON.stringify(report, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exit(1);
});
