import fs from "node:fs";
import path from "node:path";
import { execFileSync, spawnSync } from "node:child_process";

function arg(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] || fallback : fallback;
}

const exportDir = path.resolve(process.cwd(), arg("--export-dir", "."));
const outDir = path.resolve(exportDir, arg("--out", "FINAL"));
const pagesDir = path.join(exportDir, "pages");
const assetsDir = path.join(exportDir, "assets");
const dbDir = path.join(exportDir, "databases");
const manifestPath = path.join(exportDir, "manifest.json");
const assetsManifestPath = path.join(exportDir, "assets_manifest.json");
const trackingPath = path.join(outDir, "_tracking.md");
const tesseractAvailable = spawnSync("tesseract", ["--version"], { encoding: "utf8" }).status === 0;
const generatedAt = new Date().toISOString();
const ocrCache = new Map();
const processedPages = new Set();
const processedDbs = new Set();
let trackingEntries = 0;

const topicFiles = {
  profile: "01-the-profile-template.md",
  postTemplates: "02-post-templates.md",
  dmTemplates: "03-dm-templates.md",
  contentPlan: "04-365-day-ai-content-plan-template-generator.md",
  routine: "05-7-minute-content-creation-routine.md",
  contentIdeas: "06-71-winning-content-ideas.md",
  launchChecklist: "07-linkedin-profile-launch-checklist.md",
  swipeFile: "08-master-swipe-file-of-top-content-that-booked-calls.md",
  microOfferGenerator: "09-custom-micro-offer-generator.md",
  microOfferIdeas: "10-15-micro-offer-ideas.md",
};

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function ensureCleanDir(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const next = text[i + 1];
    if (quoted) {
      if (ch === '"' && next === '"') {
        cell += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        cell += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(cell);
      cell = "";
    } else if (ch === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (ch !== "\r") {
      cell += ch;
    }
  }
  if (cell || row.length) {
    row.push(cell);
    rows.push(row);
  }
  const header = rows.shift() || [];
  return rows.filter((r) => r.some(Boolean)).map((r) => Object.fromEntries(header.map((h, i) => [h, r[i] || ""])));
}

function readPages() {
  return fs
    .readdirSync(pagesDir)
    .filter((name) => name.endsWith(".md"))
    .sort()
    .map((name) => {
      const fullPath = path.join(pagesDir, name);
      const text = fs.readFileSync(fullPath, "utf8");
      const title = text.match(/^# (.+)$/m)?.[1]?.trim() || name;
      const suffix = name.match(/-([0-9a-f]{8})\.md$/i)?.[1] || "";
      return { name, path: fullPath, title, suffix, text };
    });
}

function dbFile(pattern) {
  const found = fs.readdirSync(dbDir).find((name) => pattern.test(name));
  if (!found) throw new Error(`Missing database file matching ${pattern}`);
  return path.join(dbDir, found);
}

function markdownTable(headers, rows) {
  const clean = (value) => String(value || "").replace(/\n/g, " ").replace(/\|/g, "\\|").trim();
  return [
    `| ${headers.map(clean).join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
    ...rows.map((row) => `| ${headers.map((h) => clean(row[h])).join(" | ")} |`),
  ].join("\n");
}

function titleBlock(title, summary, toc) {
  return `# ${title}\n\n## Source Summary\n\n${summary}\n\n## Table Of Contents\n\n${toc.map((item) => `- ${item}`).join("\n")}\n\n`;
}

function stripTitle(text) {
  return text.replace(/^# .+\n+/, "").trim();
}

function stripLeadingDbProps(text) {
  const lines = stripTitle(text).split("\n");
  while (lines.length && !lines[0].trim()) lines.shift();
  while (lines.length && /^- /.test(lines[0])) lines.shift();
  while (lines.length && !lines[0].trim()) lines.shift();
  return lines.join("\n").trim();
}

function cleanOcr(text) {
  const cleaned = String(text || "")
    .replace(/\f/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  const words = cleaned.match(/[A-Za-z0-9$@#][A-Za-z0-9$@#'.,:+/-]*/g) || [];
  return words.length >= 8 ? cleaned : "";
}

function isDecorative(filename) {
  const lower = filename.toLowerCase();
  return (
    lower.endsWith(".svg") ||
    lower.includes("facebook_post_-_20") ||
    lower.includes("frame_4") ||
    lower.includes("socialmediapreviewimage") ||
    lower.includes("brain_yellow") ||
    lower.includes("document_yellow") ||
    lower.includes("mail_yellow") ||
    lower.includes("badge_yellow") ||
    lower.includes("layers_yellow") ||
    lower.includes("currency_yellow") ||
    lower.includes("stopwatch_yellow") ||
    lower.includes("light-bulb_yellow")
  );
}

function ocrAsset(assetPath) {
  if (!tesseractAvailable) return "";
  if (ocrCache.has(assetPath)) return ocrCache.get(assetPath);
  let result = "";
  try {
    result = cleanOcr(
      execFileSync("tesseract", [assetPath, "stdout", "--psm", "6"], {
        encoding: "utf8",
        timeout: 30000,
        stdio: ["ignore", "pipe", "ignore"],
      }),
    );
  } catch {
    result = "";
  }
  ocrCache.set(assetPath, result);
  return result;
}

function transformImages(markdown, context) {
  const stats = { inspected: 0, ocrKept: 0, dropped: 0, keptVisuals: 0, missing: 0 };
  const transformed = markdown.replace(/!\[([^\]]*)\]\((\.\.\/assets\/[^)]+)\)/g, (match, alt, relPath) => {
    stats.inspected += 1;
    const filename = decodeURIComponent(relPath.replace("../assets/", ""));
    const assetPath = path.join(assetsDir, filename);
    if (!fs.existsSync(assetPath)) {
      stats.missing += 1;
      return `> Missing source image: \`${relPath}\``;
    }
    if (isDecorative(filename)) {
      stats.dropped += 1;
      return "";
    }
    const finalRel = `../assets/${filename}`;
    const ext = path.extname(filename).toLowerCase();
    const ocrText = ext === ".png" || ext === ".gif" ? ocrAsset(assetPath) : "";
    if (ocrText) {
      stats.ocrKept += 1;
      stats.keptVisuals += 1;
      return `![${alt || "source image"}](${finalRel})\n\n**Image Text:**\n\n\`\`\`text\n${ocrText}\n\`\`\``;
    }
    if (context.keepVisuals) {
      stats.keptVisuals += 1;
      return `![${alt || "source image"}](${finalRel})\n\n> Visual source retained. OCR produced no useful text.`;
    }
    stats.dropped += 1;
    return "";
  });
  return { markdown: transformed.replace(/\n{4,}/g, "\n\n\n").trim(), stats };
}

function appendTracking({ source, target, status = "processed", assets = {}, notes = "" }) {
  trackingEntries += 1;
  const line = [
    `\n## ${trackingEntries}. ${source}`,
    "",
    `- timestamp: ${new Date().toISOString()}`,
    `- target: ${target}`,
    `- status: ${status}`,
    `- assets inspected: ${assets.inspected || 0}`,
    `- OCR kept: ${assets.ocrKept || 0}`,
    `- images kept as visuals: ${assets.keptVisuals || 0}`,
    `- images dropped: ${assets.dropped || 0}`,
    `- missing local assets: ${assets.missing || 0}`,
    `- notes: ${notes || "none"}`,
    "",
  ].join("\n");
  fs.appendFileSync(trackingPath, line);
}

function pageSection(page, target, options = {}) {
  const body = options.stripDbProps ? stripLeadingDbProps(page.text) : stripTitle(page.text);
  const { markdown, stats } = transformImages(body, { keepVisuals: options.keepVisuals ?? true });
  processedPages.add(page.name);
  appendTracking({ source: page.name, target, assets: stats, notes: options.notes || `title: ${page.title}` });
  return markdown;
}

function sourceTrace(items) {
  return `\n## Source Trace\n\n${items.map((item) => `- ${item}`).join("\n")}\n`;
}

function writeTopic(filename, title, summary, toc, content, trace) {
  fs.writeFileSync(path.join(outDir, filename), `${titleBlock(title, summary, toc)}${content.trim()}\n${sourceTrace(trace)}`);
}

function pageByTitle(pages, title) {
  const page = pages.find((p) => p.title === title);
  if (!page) throw new Error(`Missing page title: ${title}`);
  return page;
}

function pageById(pages, id) {
  const suffix = String(id || "").replaceAll("-", "").slice(-8);
  return pages.find((p) => p.suffix === suffix);
}

function sourceLabel(row, index) {
  const hook = row.Hook || row.Name || row["Post Link"] || row.id;
  return `${String(index + 1).padStart(2, "0")}. ${hook.length > 90 ? `${hook.slice(0, 87)}...` : hook}`;
}

ensureCleanDir(outDir);

const manifest = readJson(manifestPath, {});
const assetsManifest = readJson(assetsManifestPath, []);
const pages = readPages();
const postDbPath = dbFile(/^post-templates-.*\.csv$/);
const swipeDbPath = dbFile(/^media-engine-master-swipe-file-.*\.csv$/);
const postRows = parseCsv(fs.readFileSync(postDbPath, "utf8"));
const swipeRows = parseCsv(fs.readFileSync(swipeDbPath, "utf8"));

fs.writeFileSync(
  trackingPath,
  `# FINAL Organization Tracking\n\n- initialized: ${generatedAt}\n- export dir: ${exportDir}\n- source pages: ${pages.length}\n- databases: ${manifest.collections ?? 2}\n- blocks: ${manifest.blocks ?? "unknown"}\n- unique downloaded asset URLs: ${manifest.assetsDownloaded ?? "unknown"}\n- blocked asset URLs: ${manifest.assetsFailed ?? assetsManifest.filter((a) => a.status !== "ok").length}\n- tesseract available: ${tesseractAvailable ? "yes" : "no"}\n`,
);

const profile = pageByTitle(pages, "The Profile Template");
writeTopic(
  topicFiles.profile,
  "The Profile Template",
  "Profile template supporting document from the root Notion vault.",
  ["Profile template note", "Source trace"],
  `## Profile Template Note\n\n${pageSection(profile, topicFiles.profile, { keepVisuals: true }) || "_No additional body text in source export._"}`,
  [profile.name],
);

const postIndex = pageByTitle(pages, "Post Templates");
let postContent = `## Database Index\n\n${pageSection(postIndex, topicFiles.postTemplates, {
  keepVisuals: false,
  notes: "database wrapper/index page",
}) || "_Database wrapper page._"}\n\n## Template Table\n\n${markdownTable(["Name", "Format", "Type", "id", "url"], postRows)}\n\n`;
const postTrace = [postIndex.name, path.relative(exportDir, postDbPath)];
processedDbs.add(path.basename(postDbPath));
appendTracking({
  source: path.relative(exportDir, postDbPath),
  target: topicFiles.postTemplates,
  notes: `${postRows.length} Post Templates rows processed as authority`,
});
postRows.forEach((row, index) => {
  const page = pageById(pages, row.id);
  postContent += `\n## ${index + 1}. ${row.Name}\n\n`;
  postContent += `- Format: ${row.Format || "n/a"}\n- Type: ${row.Type || "n/a"}\n- Source: ${row.url}\n- Row ID: ${row.id}\n\n`;
  if (page) {
    postContent += `${pageSection(page, topicFiles.postTemplates, {
      keepVisuals: true,
      stripDbProps: true,
      notes: `post template row: ${row.Name}`,
    })}\n\n`;
    postTrace.push(page.name);
  } else {
    postContent += "_No matching row page found._\n\n";
  }
});
writeTopic(
  topicFiles.postTemplates,
  "Post Templates",
  `20 post template database rows, using \`${path.basename(postDbPath)}\` as row authority.`,
  ["Database index", "Template table", "20 template sections", "Source trace"],
  postContent,
  postTrace,
);

const dm = pageByTitle(pages, "DM Templates");
writeTopic(
  topicFiles.dmTemplates,
  "DM Templates",
  "DM template module from the Notion vault.",
  ["Overview", "Outbound categories", "Source trace"],
  `## Overview\n\n${pageSection(dm, topicFiles.dmTemplates, { keepVisuals: true })}`,
  [dm.name],
);

const contentPlan = pageByTitle(pages, "365 Day AI Content Plan Template Generator");
writeTopic(
  topicFiles.contentPlan,
  "365 Day AI Content Plan Template Generator",
  "Mega-prompt for generating year-long LinkedIn content plans.",
  ["Mega-prompt", "Example output visual", "Source trace"],
  `## Mega-Prompt\n\n${pageSection(contentPlan, topicFiles.contentPlan, { keepVisuals: true })}`,
  [contentPlan.name],
);

const routine = pageByTitle(pages, "7-Minute Content Creation Routine");
writeTopic(
  topicFiles.routine,
  "7-Minute Content Creation Routine",
  "Short routine note from the Notion vault.",
  ["Routine", "Source trace"],
  `## Routine\n\n${pageSection(routine, topicFiles.routine, { keepVisuals: true })}`,
  [routine.name],
);

const ideas = pageByTitle(pages, "71 Winning Content Ideas");
writeTopic(
  topicFiles.contentIdeas,
  "71 Winning Content Ideas",
  "External spreadsheet resource linked from the vault.",
  ["Spreadsheet link", "Source trace"],
  `## Spreadsheet Link\n\n${pageSection(ideas, topicFiles.contentIdeas, { keepVisuals: true })}`,
  [ideas.name],
);

const checklist = pageByTitle(pages, "LinkedIn Profile Launch Checklist");
writeTopic(
  topicFiles.launchChecklist,
  "LinkedIn Profile Launch Checklist",
  "Checklist for profile headline, CTA, banner, about section, micro-offer positioning, content, and outreach.",
  ["Checklist", "Source trace"],
  `## Checklist\n\n${pageSection(checklist, topicFiles.launchChecklist, { keepVisuals: true })}`,
  [checklist.name],
);

const swipeIndex = pageByTitle(pages, "Master Swipe File Of Top Content That Booked Calls (Updated LIVE)");
let swipeContent = `## Database Index\n\n${pageSection(swipeIndex, topicFiles.swipeFile, {
  keepVisuals: true,
  notes: "swipe database wrapper/index page",
})}\n\n## Swipe Table\n\n${markdownTable(["Post Link", "Hook", "Design Style", "Type", "Niche/Industry", "Funnel", "id", "url"], swipeRows)}\n\n`;
const swipeTrace = [swipeIndex.name, path.relative(exportDir, swipeDbPath)];
processedDbs.add(path.basename(swipeDbPath));
appendTracking({
  source: path.relative(exportDir, swipeDbPath),
  target: topicFiles.swipeFile,
  notes: `${swipeRows.length} Swipe File rows processed as authority`,
});
swipeRows.forEach((row, index) => {
  const page = pageById(pages, row.id);
  swipeContent += `\n## ${sourceLabel(row, index)}\n\n`;
  swipeContent += `- Post Link: ${row["Post Link"] || "n/a"}\n- Hook: ${row.Hook || "n/a"}\n- Design Style: ${row["Design Style"] || "n/a"}\n- Type: ${row.Type || "n/a"}\n- Niche/Industry: ${row["Niche/Industry"] || "n/a"}\n- Funnel: ${row.Funnel || "n/a"}\n- Row ID: ${row.id}\n- Notion Row: ${row.url}\n\n`;
  if (page) {
    swipeContent += `${pageSection(page, topicFiles.swipeFile, {
      keepVisuals: true,
      stripDbProps: true,
      notes: `swipe row: ${row.Hook || row["Post Link"]}`,
    })}\n\n`;
    swipeTrace.push(page.name);
  } else {
    swipeContent += "_No matching row page found._\n\n";
  }
});
writeTopic(
  topicFiles.swipeFile,
  "Master Swipe File Of Top Content That Booked Calls",
  `70 swipe database rows, using \`${path.basename(swipeDbPath)}\` as row authority.`,
  ["Database index", "Swipe table", "70 swipe sections", "Source trace"],
  swipeContent,
  swipeTrace,
);

const microGenerator = pageByTitle(pages, "Accelerate Leads: Custom Micro Offer Generator");
writeTopic(
  topicFiles.microOfferGenerator,
  "Accelerate Leads: Custom Micro Offer Generator",
  "Prompt and context for generating 10 micro-offer ideas.",
  ["Context", "Prompt", "Source trace"],
  `## Context And Prompt\n\n${pageSection(microGenerator, topicFiles.microOfferGenerator, { keepVisuals: true })}`,
  [microGenerator.name],
);

const microIdeas = pageByTitle(pages, "Accelerate Leads: 15 Micro Offer Ideas");
writeTopic(
  topicFiles.microOfferIdeas,
  "Accelerate Leads: 15 Micro Offer Ideas",
  "List of 15 fast-to-deliver micro-offer concepts.",
  ["Ideas", "Source trace"],
  `## Ideas\n\n${pageSection(microIdeas, topicFiles.microOfferIdeas, { keepVisuals: true })}`,
  [microIdeas.name],
);

const root = pages.find((p) => p.title === "LinkedIn Copy N’ Paste Vault");
if (root) {
  processedPages.add(root.name);
  appendTracking({
    source: root.name,
    target: "_tracking.md",
    status: "marked duplicate/root index",
    notes: "root rollup used for topic order only; content duplicated by topic files/databases",
  });
}

const unprocessed = pages.filter((p) => !processedPages.has(p.name));
const unresolvedAssets = assetsManifest.filter((asset) => asset.status !== "ok");
fs.appendFileSync(
  trackingPath,
  [
    "\n# Final Summary",
    "",
    `- completed: ${new Date().toISOString()}`,
    `- processed source pages: ${processedPages.size}`,
    `- processed databases: ${processedDbs.size}`,
    `- unprocessed source pages: ${unprocessed.length}`,
    `- unresolved/blocked assets: ${unresolvedAssets.length}`,
    `- OCR cache entries: ${ocrCache.size}`,
    "",
    "## Unprocessed Pages",
    "",
    ...(unprocessed.length ? unprocessed.map((p) => `- ${p.name} (${p.title})`) : ["- none"]),
    "",
    "## Blocked Assets",
    "",
    ...(unresolvedAssets.length
      ? unresolvedAssets.map((a) => `- ${a.reason}: ${a.blockId} ${a.originalUrl}`)
      : ["- none"]),
    "",
  ].join("\n"),
);

const expected = Object.values(topicFiles).map((file) => path.join(outDir, file));
const missingFinal = expected.filter((file) => !fs.existsSync(file));
if (missingFinal.length || unprocessed.length) {
  console.error({ missingFinal, unprocessed: unprocessed.map((p) => p.name) });
  process.exitCode = 1;
} else {
  console.log(
    JSON.stringify(
      {
        outDir,
        topicFiles: expected.length,
        tracking: path.relative(process.cwd(), trackingPath),
        pagesProcessed: processedPages.size,
        databasesProcessed: processedDbs.size,
        blockedAssets: unresolvedAssets.length,
      },
      null,
      2,
    ),
  );
}
