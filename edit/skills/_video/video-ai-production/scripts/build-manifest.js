#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

function usage() {
  console.error("Usage: build-manifest.js --project <dir> [--out renders/manifest.json]");
  process.exit(2);
}

const args = process.argv.slice(2);
let project = "";
let out = "";

for (let i = 0; i < args.length; i += 1) {
  if (args[i] === "--project") project = args[++i] || "";
  else if (args[i] === "--out") out = args[++i] || "";
  else if (args[i] === "--help") usage();
  else usage();
}

if (!project) usage();

const root = path.resolve(project);
const candidates = [
  "reference/source-manifest.md",
  "scripts/timing-map.json",
  "raw-media/voice/manifest.json",
  "raw-media/avatar/manifest.json",
  "renders/render-log.md",
  "renders/final.mp4",
  "qa/report.md"
];

function statFor(relativePath) {
  const absolutePath = path.join(root, relativePath);
  if (!fs.existsSync(absolutePath)) return { path: relativePath, exists: false };
  const stat = fs.statSync(absolutePath);
  return {
    path: relativePath,
    exists: true,
    type: stat.isDirectory() ? "directory" : "file",
    bytes: stat.size,
    modifiedAt: stat.mtime.toISOString()
  };
}

const manifest = {
  project: root,
  generatedAt: new Date().toISOString(),
  artifacts: candidates.map(statFor)
};

const json = `${JSON.stringify(manifest, null, 2)}\n`;
if (out) {
  const outputPath = path.isAbsolute(out) ? out : path.join(root, out);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, json);
} else {
  process.stdout.write(json);
}

