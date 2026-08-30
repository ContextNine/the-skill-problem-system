import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { NotionAPI } from "notion-client";
import { defaultMapImageUrl, mergeRecordMaps } from "notion-utils";
import got from "got";
import sanitize from "sanitize-filename";
import mime from "mime-types";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function cliValue(name, fallback = "") {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] || fallback : fallback;
}

function normalizeUuid(raw) {
  const clean = String(raw || "").replaceAll("-", "");
  if (clean.length !== 32) return raw;
  return `${clean.slice(0, 8)}-${clean.slice(8, 12)}-${clean.slice(12, 16)}-${clean.slice(16, 20)}-${clean.slice(20)}`;
}

function extractPageId(input) {
  const value = String(input || "");
  const compact = value.match(/[0-9a-fA-F]{32}/)?.[0];
  if (compact) return normalizeUuid(compact);
  const dashed = value.match(/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/)?.[0];
  if (dashed) return normalizeUuid(dashed);
  return "";
}

const SOURCE_URL = cliValue("--url", "");
const ROOT_ID = normalizeUuid(cliValue("--page-id", extractPageId(SOURCE_URL) || "14fa58a3-11cf-8083-a477-f89086614353"));
const HOST = cliValue("--host", SOURCE_URL ? new URL(SOURCE_URL).origin : "https://www.notion.so");
const OUT = path.resolve(process.cwd(), cliValue("--out", "."));

const dirs = {
  rawRecordMaps: path.join(OUT, "raw_record_maps"),
  rawHtml: path.join(OUT, "raw_html"),
  pages: path.join(OUT, "pages"),
  pagesHtml: path.join(OUT, "pages_html"),
  assets: path.join(OUT, "assets"),
  databases: path.join(OUT, "databases"),
};

for (const dir of Object.values(dirs)) await fs.mkdir(dir, { recursive: true });

const api = new NotionAPI({
  userTimeZone: "Asia/Makassar",
  kyOptions: {
    headers: {
      origin: HOST,
      referer: `${HOST}/`,
    },
  },
});

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const uuidToId = (id) => String(id || "").replaceAll("-", "");
const idToUuid = (id) => {
  const clean = uuidToId(id);
  if (clean.length !== 32) return id;
  return normalizeUuid(clean);
};
const blockValue = (record) => record?.value?.value || record?.value || record;
const safeName = (name, fallback = "untitled") =>
  sanitize(String(name || fallback).replace(/\s+/g, " ").trim()).slice(0, 90) || fallback;
const pageUrl = (id, title = "") => `${HOST}/${slug(title)}-${uuidToId(id)}`;
const slug = (text) =>
  safeName(String(text || "page").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""), "page");

function richText(value, mode = "md") {
  if (!Array.isArray(value)) return "";
  return value
    .map((part) => {
      if (!Array.isArray(part)) return "";
      let text = String(part[0] ?? "");
      const marks = Array.isArray(part[1]) ? part[1] : [];
      const link = marks.find((mark) => Array.isArray(mark) && mark[0] === "a")?.[1];
      if (mode === "html") {
        text = escapeHtml(text);
        if (link) text = `<a href="${escapeAttr(link)}">${text}</a>`;
        return text;
      }
      return link ? `[${text}](${link})` : text;
    })
    .join("");
}

function plainRichText(value) {
  if (!Array.isArray(value)) return "";
  return value.map((part) => (Array.isArray(part) ? String(part[0] ?? "") : "")).join("");
}

function titleOf(block) {
  return plainRichText(block?.properties?.title) || "Untitled";
}

function propValue(prop) {
  if (Array.isArray(prop)) return plainRichText(prop);
  if (prop == null) return "";
  if (typeof prop === "object") return JSON.stringify(prop);
  return String(prop);
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeAttr(text) {
  return escapeHtml(text).replaceAll('"', "&quot;");
}

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function collectIdsFromRecordMap(recordMap) {
  const ids = new Set();
  for (const [id, record] of Object.entries(recordMap.block || {})) {
    const block = blockValue(record);
    if (!block?.alive) continue;
    if (block.type === "page") ids.add(id);
    for (const childId of block.content || []) ids.add(childId);
  }
  for (const collectionQueries of Object.values(recordMap.collection_query || {})) {
    for (const viewQuery of Object.values(collectionQueries || {})) {
      for (const reducer of Object.values(viewQuery || {})) {
        for (const rowId of reducer?.blockIds || []) ids.add(rowId);
      }
    }
  }
  return ids;
}

function collectAssetCandidates(globalRecordMap) {
  const candidates = new Map();
  const add = (url, block, reason) => {
    if (!url || typeof url !== "string") return;
    if (url.startsWith("data:")) return;
    if (url.startsWith("/icons") || url.startsWith("/images")) {
      candidates.set(`${block.id}:${reason}:${url}`, {
        originalUrl: url,
        downloadUrl: `https://www.notion.so${url}`,
        blockId: block.id,
        blockType: block.type,
        reason,
      });
      return;
    }
    if (!/^https?:\/\//.test(url)) return;
    const mediaLike =
      /(?:png|jpe?g|gif|webp|svg|pdf|mp4|mov|mp3|wav)(?:\?|$)/i.test(url) ||
      /prod-files-secure|file\.notion\.so|notion-static|amazonaws|images\.unsplash/.test(url);
    if (!mediaLike) return;
    let downloadUrl = url;
    if (globalRecordMap.signed_urls?.[block.id]) {
      downloadUrl = globalRecordMap.signed_urls[block.id];
    } else {
      try {
        downloadUrl = defaultMapImageUrl(url, block) || url;
      } catch {
        downloadUrl = url;
      }
    }
    const key = `${block.id}:${url}`;
    if (candidates.has(key)) {
      const existing = candidates.get(key);
      if (!existing.reason.split(",").includes(reason)) existing.reason = `${existing.reason},${reason}`;
      return;
    }
    candidates.set(key, {
      originalUrl: url,
      downloadUrl,
      blockId: block.id,
      blockType: block.type,
      reason,
    });
  };

  for (const record of Object.values(globalRecordMap.block || {})) {
    const block = blockValue(record);
    if (!block?.id) continue;
    const props = block.properties || {};
    const format = block.format || {};
    for (const key of ["source", "caption"]) {
      const raw = propValue(props[key]);
      if (raw) add(raw, block, key);
    }
    for (const key of ["display_source", "page_icon", "page_cover", "social_media_image_preview_url"]) {
      add(format[key], block, key);
    }
    if (block.type === "image" || block.type === "file" || block.type === "video" || block.type === "pdf") {
      for (const value of findUrls(block)) add(value, block, block.type);
    }
  }
  return [...candidates.values()];
}

function findUrls(value, out = []) {
  if (typeof value === "string") {
    if (/^(https?:\/\/|\/icons|\/images)/.test(value)) out.push(value);
    return out;
  }
  if (Array.isArray(value)) {
    for (const item of value) findUrls(item, out);
    return out;
  }
  if (value && typeof value === "object") {
    for (const item of Object.values(value)) findUrls(item, out);
  }
  return out;
}

async function downloadAssets(candidates) {
  const assets = [];
  const urlToLocal = new Map();
  let index = 0;
  for (const candidate of candidates) {
    index += 1;
    const hash = crypto.createHash("sha1").update(candidate.downloadUrl).digest("hex").slice(0, 10);
    let ext = path.extname(new URL(candidate.downloadUrl).pathname).split("?")[0];
    let base = safeName(path.basename(decodeURIComponent(new URL(candidate.originalUrl, "https://www.notion.so").pathname), ext) || candidate.reason, "asset");
    if (!ext || ext.length > 8) ext = "";
    const filenameBase = `${String(index).padStart(4, "0")}-${candidate.blockId.slice(0, 8)}-${base}-${hash}`;
    let filename = `${filenameBase}${ext}`;
    let status = "ok";
    let bytes = 0;
    let contentType = "";
    const fallbackUrls = [...new Set([candidate.downloadUrl, candidate.originalUrl].filter(Boolean))];
    try {
      let response;
      let usedUrl = "";
      let lastError;
      for (const url of fallbackUrls) {
        try {
          response = await got(url, {
            timeout: { request: 30000 },
            retry: { limit: 2 },
            headers: { referer: `${HOST}/`, "user-agent": "Mozilla/5.0" },
          });
          usedUrl = url;
          break;
        } catch (error) {
          lastError = error;
        }
      }
      if (!response) throw lastError;
      candidate.downloadUrl = usedUrl || candidate.downloadUrl;
      contentType = response.headers["content-type"] || "";
      if (!ext) {
        const guessed = mime.extension(contentType.split(";")[0]);
        if (guessed) filename = `${filenameBase}.${guessed}`;
      }
      await fs.writeFile(path.join(dirs.assets, filename), response.rawBody);
      bytes = response.rawBody.length;
    } catch (error) {
      status = `failed: ${error.message}`;
      filename = "";
    }
    const localPath = filename ? `../assets/${filename}` : "";
    assets.push({ ...candidate, filename, localPath, bytes, contentType, status });
    if (filename) {
      urlToLocal.set(candidate.originalUrl, localPath);
      urlToLocal.set(candidate.downloadUrl, localPath);
    }
    if (index % 20 === 0) await sleep(250);
  }
  await fs.writeFile(path.join(OUT, "assets_manifest.json"), JSON.stringify(assets, null, 2));
  return { urlToLocal, assets };
}

function renderProperties(block, globalRecordMap, mode) {
  if (!block?.properties) return "";
  const collection = block.parent_table === "collection" ? blockValue(globalRecordMap.collection?.[block.parent_id]) : null;
  const schema = collection?.schema || {};
  const lines = [];
  for (const [key, prop] of Object.entries(block.properties)) {
    if (key === "title") continue;
    const label = schema[key]?.name || key;
    const value = propValue(prop);
    if (value) lines.push([label, value]);
  }
  if (!lines.length) return "";
  if (mode === "html") {
    return `<dl class="props">${lines
      .map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd>`)
      .join("")}</dl>`;
  }
  return lines.map(([k, v]) => `- ${k}: ${v}`).join("\n") + "\n\n";
}

function renderBlock(id, globalRecordMap, mode, urlToLocal, depth = 0, seen = new Set()) {
  if (seen.has(id)) return "";
  seen.add(id);
  const record = globalRecordMap.block?.[id];
  const block = blockValue(record);
  if (!block?.alive) return "";
  const indent = "  ".repeat(depth);
  const text = richText(block.properties?.title, mode);
  const children = (block.content || [])
    .map((childId) => renderBlock(childId, globalRecordMap, mode, urlToLocal, depth + 1, seen))
    .filter(Boolean)
    .join(mode === "html" ? "\n" : "");

  if (mode === "html") {
    switch (block.type) {
      case "page":
        return `<section class="block page-ref"><h${Math.min(3 + depth, 6)}>${escapeHtml(titleOf(block))}</h${Math.min(
          3 + depth,
          6,
        )}>${renderProperties(block, globalRecordMap, mode)}${children}</section>`;
      case "header":
        return `<h1>${text}</h1>`;
      case "sub_header":
        return `<h2>${text}</h2>`;
      case "sub_sub_header":
        return `<h3>${text}</h3>`;
      case "text":
        return text || children ? `<p>${text}</p>${children}` : "";
      case "bulleted_list":
        return `<ul><li>${text}${children}</li></ul>`;
      case "numbered_list":
        return `<ol><li>${text}${children}</li></ol>`;
      case "to_do":
        return `<p><input type="checkbox" disabled ${block.properties?.checked ? "checked" : ""}> ${text}</p>${children}`;
      case "quote":
        return `<blockquote>${text}${children}</blockquote>`;
      case "callout":
        return `<aside class="callout">${text}${children}</aside>`;
      case "code":
        return `<pre><code>${escapeHtml(plainRichText(block.properties?.title))}</code></pre>`;
      case "divider":
        return "<hr>";
      case "image": {
        const original = propValue(block.properties?.source) || block.format?.display_source;
        const src = urlToLocal.get(original) || urlToLocal.get(defaultMapImageUrl(original, block) || "") || original;
        return src ? `<figure><img src="${escapeAttr(src)}" alt="${escapeAttr(text || "image")}"><figcaption>${text}</figcaption></figure>` : "";
      }
      case "embed":
      case "bookmark":
      case "file":
      case "video":
      case "pdf": {
        const source = propValue(block.properties?.source) || block.format?.display_source || "";
        return source ? `<p><a href="${escapeAttr(source)}">${escapeHtml(text || source)}</a></p>` : "";
      }
      case "collection_view":
      case "collection_view_page":
        return `<section class="collection"><h3>Database</h3>${children}</section>`;
      case "column_list":
      case "column":
        return `<div class="${block.type}">${children}</div>`;
      default:
        return text || children ? `<div class="block ${escapeAttr(block.type || "unknown")}">${text}${children}</div>` : "";
    }
  }

  switch (block.type) {
    case "page":
      return `${"\n".repeat(depth ? 1 : 0)}${"#".repeat(Math.min(1 + depth, 6))} ${titleOf(block)}\n\n${renderProperties(
        block,
        globalRecordMap,
        mode,
      )}${children}`;
    case "header":
      return `# ${text}\n\n`;
    case "sub_header":
      return `## ${text}\n\n`;
    case "sub_sub_header":
      return `### ${text}\n\n`;
    case "text":
      return text || children ? `${text}\n\n${children}` : "";
    case "bulleted_list":
      return `${indent}- ${text}\n${children}`;
    case "numbered_list":
      return `${indent}1. ${text}\n${children}`;
    case "to_do":
      return `${indent}- [${block.properties?.checked ? "x" : " "}] ${text}\n${children}`;
    case "quote":
      return `> ${text}\n\n${children}`;
    case "callout":
      return `> ${text}\n\n${children}`;
    case "code":
      return `\`\`\`\n${plainRichText(block.properties?.title)}\n\`\`\`\n\n`;
    case "divider":
      return "---\n\n";
    case "image": {
      const original = propValue(block.properties?.source) || block.format?.display_source;
      const mapped = defaultMapImageUrl(original, block) || "";
      const src = urlToLocal.get(original) || urlToLocal.get(mapped) || original;
      return src ? `![${text || "image"}](${src})\n\n` : "";
    }
    case "embed":
    case "bookmark":
    case "file":
    case "video":
    case "pdf": {
      const source = propValue(block.properties?.source) || block.format?.display_source || "";
      return source ? `[${text || source}](${source})\n\n` : "";
    }
    case "collection_view":
    case "collection_view_page":
      return `\n## Database\n\n${children}`;
    case "column_list":
    case "column":
      return children;
    default:
      return text || children ? `${text}\n\n${children}` : "";
  }
}

function pageFileStem(index, page) {
  return `${String(index).padStart(4, "0")}-${slug(titleOf(page))}-${uuidToId(page.id).slice(-8)}`;
}

async function fetchRawHtml(id, title, stem) {
  try {
    const response = await got(pageUrl(id, title), {
      timeout: { request: 20000 },
      retry: { limit: 1 },
      headers: { "user-agent": "Mozilla/5.0" },
    });
    await fs.writeFile(path.join(dirs.rawHtml, `${stem}.html`), response.body);
    return { status: "ok", bytes: Buffer.byteLength(response.body) };
  } catch (error) {
    return { status: `failed: ${error.message}`, bytes: 0 };
  }
}

async function readCachedRecordMap(id) {
  const file = path.join(dirs.rawRecordMaps, `${uuidToId(id)}.json`);
  try {
    return JSON.parse(await fs.readFile(file, "utf8"));
  } catch {
    return null;
  }
}

async function getPageWithBackoff(id) {
  const cached = await readCachedRecordMap(id);
  if (cached) return { recordMap: cached, source: "cache" };

  let lastError;
  for (let attempt = 1; attempt <= 7; attempt += 1) {
    try {
      return { recordMap: await api.getPage(id), source: "network" };
    } catch (error) {
      lastError = error;
      const isRateLimit = String(error.message || "").includes("429");
      const delay = isRateLimit ? Math.min(90000, attempt * 15000) : Math.min(10000, attempt * 1500);
      process.stdout.write(`retry ${attempt}/7 ${id}: ${error.message}; wait=${delay}ms\n`);
      await sleep(delay);
    }
  }
  throw lastError;
}

async function main() {
  let globalRecordMap = {};
  const queue = [ROOT_ID];
  const fetched = new Set();
  const fetchLog = [];

  for (let cursor = 0; cursor < queue.length; cursor += 1) {
    const id = idToUuid(queue[cursor]);
    if (fetched.has(id)) continue;
    fetched.add(id);
    try {
      const { recordMap, source } = await getPageWithBackoff(id);
      await fs.writeFile(path.join(dirs.rawRecordMaps, `${uuidToId(id)}.json`), JSON.stringify(recordMap, null, 2));
      globalRecordMap = mergeRecordMaps(globalRecordMap, recordMap);
      const discovered = collectIdsFromRecordMap(recordMap);
      for (const discoveredId of discovered) {
        const normalized = idToUuid(discoveredId);
        const block = blockValue(recordMap.block?.[normalized]);
        if (block?.type === "page" && !fetched.has(normalized)) queue.push(normalized);
      }
      fetchLog.push({ id, status: "ok", source, blocks: Object.keys(recordMap.block || {}).length });
      process.stdout.write(`fetched ${fetchLog.length}: ${id} source=${source} blocks=${Object.keys(recordMap.block || {}).length}\n`);
      await sleep(source === "cache" ? 10 : 1100);
    } catch (error) {
      fetchLog.push({ id, status: `failed: ${error.message}`, blocks: 0 });
      process.stdout.write(`failed ${id}: ${error.message}\n`);
    }
  }

  await fs.writeFile(path.join(OUT, "all-record-map.json"), JSON.stringify(globalRecordMap, null, 2));
  await fs.writeFile(path.join(OUT, "fetch-log.json"), JSON.stringify(fetchLog, null, 2));

  const candidates = collectAssetCandidates(globalRecordMap);
  const { urlToLocal, assets } = await downloadAssets(candidates);

  const pages = Object.values(globalRecordMap.block || {})
    .map(blockValue)
    .filter((block) => block?.alive && block.type === "page")
    .sort((a, b) => (a.created_time || 0) - (b.created_time || 0));

  const htmlResults = [];
  let index = 0;
  for (const page of pages) {
    index += 1;
    const stem = pageFileStem(index, page);
    const md = renderBlock(page.id, globalRecordMap, "md", urlToLocal, 0, new Set());
    const htmlBody = renderBlock(page.id, globalRecordMap, "html", urlToLocal, 0, new Set());
    await fs.writeFile(path.join(dirs.pages, `${stem}.md`), md);
    await fs.writeFile(
      path.join(dirs.pagesHtml, `${stem}.html`),
      `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(titleOf(page))}</title><style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;line-height:1.45;max-width:880px;margin:40px auto;padding:0 24px;color:#27241f}img{max-width:100%;height:auto}pre{white-space:pre-wrap;background:#f6f6f6;padding:12px;border-radius:6px}.callout{background:#f7f7f5;padding:12px 14px;border-radius:6px}.props{display:grid;grid-template-columns:max-content 1fr;gap:4px 12px;background:#fafafa;padding:10px;border-radius:6px}.props dt{font-weight:600}</style></head><body>${htmlBody}</body></html>`,
    );
    htmlResults.push({ id: page.id, title: titleOf(page), ...await fetchRawHtml(page.id, titleOf(page), stem) });
  }

  const dbSummaries = [];
  for (const [collectionId, record] of Object.entries(globalRecordMap.collection || {})) {
    const collection = blockValue(record);
    const name = plainRichText(collection?.name) || collection?.name?.[0]?.[0] || collectionId;
    const schema = collection?.schema || {};
    const props = Object.entries(schema).sort(([a], [b]) => (a === "title" ? -1 : b === "title" ? 1 : a.localeCompare(b)));
    const rows = pages.filter((page) => page.parent_table === "collection" && page.parent_id === collectionId);
    const csvRows = [[...props.map(([, def]) => def.name), "id", "url"].map(csvCell).join(",")];
    for (const row of rows) {
      csvRows.push(
        [
          ...props.map(([key]) => (key === "title" ? titleOf(row) : propValue(row.properties?.[key]))),
          row.id,
          pageUrl(row.id, titleOf(row)),
        ]
          .map(csvCell)
          .join(","),
      );
    }
    const stem = `${slug(name)}-${uuidToId(collectionId).slice(-8)}`;
    await fs.writeFile(path.join(dirs.databases, `${stem}.csv`), csvRows.join("\n"));
    dbSummaries.push({ id: collectionId, name, rows: rows.length, properties: props.map(([, def]) => def.name) });
  }

  const blockTypeCounts = {};
  for (const record of Object.values(globalRecordMap.block || {})) {
    const type = blockValue(record)?.type || "unknown";
    blockTypeCounts[type] = (blockTypeCounts[type] || 0) + 1;
  }

  const manifest = {
    source: pageUrl(ROOT_ID, "LinkedIn Copy N Paste Vault"),
    generatedAt: new Date().toISOString(),
    fetchedPages: fetched.size,
    exportedPages: pages.length,
    collections: dbSummaries.length,
    assetsAttempted: candidates.length,
    assetsDownloaded: assets.filter((asset) => asset.status === "ok").length,
    assetsFailed: assets.filter((asset) => asset.status !== "ok").length,
    blocks: Object.keys(globalRecordMap.block || {}).length,
    blockTypeCounts,
    databases: dbSummaries,
    htmlFetches: htmlResults,
    failedFetches: fetchLog.filter((entry) => entry.status !== "ok"),
  };
  await fs.writeFile(path.join(OUT, "manifest.json"), JSON.stringify(manifest, null, 2));
  await fs.writeFile(
    path.join(OUT, "README.md"),
    `# LinkedIn Copy N Paste Vault Export\n\nSource: ${manifest.source}\n\n- Exported pages: ${manifest.exportedPages}\n- Databases: ${manifest.collections}\n- Blocks: ${manifest.blocks}\n- Assets downloaded: ${manifest.assetsDownloaded}\n\nFolders:\n\n- \`pages/\`: Markdown exports.\n- \`pages_html/\`: generated readable HTML per page.\n- \`raw_html/\`: fetched Notion shell HTML per page.\n- \`raw_record_maps/\`: raw Notion API payloads per fetched page.\n- \`databases/\`: CSV exports for each database.\n- \`assets/\`: downloaded media.\n`,
  );
  process.stdout.write(JSON.stringify(manifest, null, 2) + "\n");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
