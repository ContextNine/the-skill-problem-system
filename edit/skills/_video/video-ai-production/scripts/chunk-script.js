#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

function usage() {
  console.error("Usage: chunk-script.js <script.md> [--out chunks.json] [--max-seconds 55] [--wpm 150]");
  process.exit(2);
}

const args = process.argv.slice(2);
if (args.length < 1 || args.includes("--help")) usage();

const input = args[0];
let out = "";
let maxSeconds = 55;
let wpm = 150;

for (let i = 1; i < args.length; i += 1) {
  if (args[i] === "--out") out = args[++i] || "";
  else if (args[i] === "--max-seconds") maxSeconds = Number(args[++i]);
  else if (args[i] === "--wpm") wpm = Number(args[++i]);
  else usage();
}

if (!Number.isFinite(maxSeconds) || maxSeconds <= 0) usage();
if (!Number.isFinite(wpm) || wpm <= 0) usage();

const text = fs.readFileSync(input, "utf8")
  .replace(/^---[\s\S]*?---\s*/m, "")
  .replace(/```[\s\S]*?```/g, " ")
  .replace(/^#+\s+/gm, "")
  .replace(/\s+/g, " ")
  .trim();

if (!text) {
  console.error(`No script text found in ${input}`);
  process.exit(1);
}

const sentenceMatches = text.match(/[^.!?]+[.!?]+(?:["')\]]+)?|[^.!?]+$/g) || [text];
const maxWords = Math.max(1, Math.floor((maxSeconds / 60) * wpm));
const chunks = [];
let current = [];
let currentWords = 0;

function wordCount(value) {
  return (value.trim().match(/\S+/g) || []).length;
}

function pushChunk() {
  if (!current.length) return;
  const chunkText = current.join(" ").trim();
  const words = wordCount(chunkText);
  const estimatedSeconds = Math.max(1, Math.round((words / wpm) * 60));
  const id = `voice_${String(chunks.length + 1).padStart(3, "0")}`;
  chunks.push({
    id,
    text: chunkText,
    words,
    estimatedSeconds,
    outputPath: `raw-media/voice/${id}.mp3`,
    status: "planned"
  });
  current = [];
  currentWords = 0;
}

for (const rawSentence of sentenceMatches) {
  const sentence = rawSentence.trim();
  if (!sentence) continue;
  const words = wordCount(sentence);
  if (currentWords > 0 && currentWords + words > maxWords) pushChunk();
  current.push(sentence);
  currentWords += words;
}
pushChunk();

const manifest = {
  source: path.normalize(input),
  maxSeconds,
  wpm,
  chunkCount: chunks.length,
  chunks
};

const json = `${JSON.stringify(manifest, null, 2)}\n`;
if (out) {
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, json);
} else {
  process.stdout.write(json);
}

