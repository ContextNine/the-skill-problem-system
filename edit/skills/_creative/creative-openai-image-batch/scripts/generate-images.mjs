#!/usr/bin/env node

import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';

const API_URL = 'https://api.openai.com/v1/images/generations';
const DEFAULTS = {
  model: 'gpt-image-2',
  quality: 'medium',
  format: 'png',
  concurrency: 1,
};

function usage(exitCode = 0) {
  const text = `
Usage:
  node generate-images.mjs --manifest prompts.json --out renders/images [options]

Options:
  --manifest PATH       JSON manifest with defaults and images[]
  --out DIR             Output directory
  --dry-run             Validate and print planned requests without API calls
  --force               Overwrite existing output files
  --concurrency N       Parallel API calls, default 1
  --quality VALUE       Default quality: low, medium, high, auto
  --format VALUE        Default format: png, jpeg, webp
  --help                Show this help
`;
  console.log(text.trim());
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = {
    dryRun: false,
    force: false,
    concurrency: DEFAULTS.concurrency,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = () => {
      index += 1;
      if (index >= argv.length || argv[index].startsWith('--')) {
        throw new Error(`${arg} needs a value`);
      }
      return argv[index];
    };

    if (arg === '--help' || arg === '-h') usage(0);
    else if (arg === '--manifest') args.manifest = next();
    else if (arg === '--out') args.out = next();
    else if (arg === '--dry-run') args.dryRun = true;
    else if (arg === '--force') args.force = true;
    else if (arg === '--concurrency') args.concurrency = Number.parseInt(next(), 10);
    else if (arg === '--quality') args.quality = next();
    else if (arg === '--format') args.format = next();
    else throw new Error(`Unknown option: ${arg}`);
  }

  if (!args.manifest) throw new Error('Missing --manifest');
  if (!args.out) throw new Error('Missing --out');
  if (!Number.isInteger(args.concurrency) || args.concurrency < 1) {
    throw new Error('--concurrency must be a positive integer');
  }

  return args;
}

function parseSize(size) {
  const match = /^(\d+)x(\d+)$/.exec(String(size ?? ''));
  if (!match) throw new Error(`Invalid size "${size}". Use WIDTHxHEIGHT, for example 1024x1280.`);
  return { width: Number(match[1]), height: Number(match[2]) };
}

function gcd(a, b) {
  return b === 0 ? a : gcd(b, a % b);
}

function nearestMultipleOf16(value) {
  return Math.max(16, Math.round(value / 16) * 16);
}

function suggestSize(width, height) {
  const targetPixels = Math.min(Math.max(width * height, 655360), 8294400);
  const ratio = width / height;
  const suggestedHeight = Math.sqrt(targetPixels / ratio);
  let candidateWidth = nearestMultipleOf16(suggestedHeight * ratio);
  let candidateHeight = nearestMultipleOf16(suggestedHeight);

  candidateWidth = Math.min(candidateWidth, 3840);
  candidateHeight = Math.min(candidateHeight, 3840);

  while (candidateWidth * candidateHeight > 8294400) {
    candidateWidth -= 16;
    candidateHeight = nearestMultipleOf16(candidateWidth / ratio);
  }

  while (candidateWidth * candidateHeight < 655360) {
    candidateWidth += 16;
    candidateHeight = nearestMultipleOf16(candidateWidth / ratio);
  }

  return `${candidateWidth}x${candidateHeight}`;
}

function validateSize(size) {
  const { width, height } = parseSize(size);
  const errors = [];
  const maxEdge = Math.max(width, height);
  const minEdge = Math.min(width, height);
  const pixels = width * height;
  const divisor = gcd(width, height);
  const ratioLabel = `${width / divisor}:${height / divisor}`;

  if (width % 16 !== 0 || height % 16 !== 0) errors.push('both edges must be multiples of 16');
  if (maxEdge > 3840) errors.push('maximum edge must be <= 3840');
  if (maxEdge / minEdge > 3) errors.push('long edge to short edge ratio must be <= 3:1');
  if (pixels < 655360 || pixels > 8294400) errors.push('total pixels must be 655360..8294400');

  if (errors.length > 0) {
    throw new Error(`Invalid size ${size} (${ratioLabel}). ${errors.join('; ')}. Try ${suggestSize(width, height)}.`);
  }

  return { width, height };
}

function validateChoice(name, value, allowed) {
  if (!allowed.includes(value)) {
    throw new Error(`Invalid ${name} "${value}". Allowed: ${allowed.join(', ')}`);
  }
}

function slugify(value) {
  return String(value)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 120);
}

async function loadManifest(filePath) {
  const raw = await readFile(filePath, 'utf8');
  const manifest = JSON.parse(raw);
  if (!manifest || typeof manifest !== 'object') throw new Error('Manifest must be a JSON object');
  if (!Array.isArray(manifest.images) || manifest.images.length === 0) {
    throw new Error('Manifest must include non-empty images[]');
  }
  return manifest;
}

function buildJobs(manifest, args) {
  const defaults = {
    ...DEFAULTS,
    ...(manifest.defaults ?? {}),
    ...(args.quality ? { quality: args.quality } : {}),
    ...(args.format ? { format: args.format } : {}),
  };

  validateChoice('quality', defaults.quality, ['low', 'medium', 'high', 'auto']);
  validateChoice('format', defaults.format, ['png', 'jpeg', 'webp']);

  return manifest.images.map((image, index) => {
    if (!image || typeof image !== 'object') throw new Error(`images[${index}] must be an object`);
    if (!image.prompt || typeof image.prompt !== 'string') throw new Error(`images[${index}] missing prompt`);
    if (!image.size) throw new Error(`images[${index}] missing size`);

    const job = {
      id: slugify(image.id ?? `image-${index + 1}`),
      prompt: image.prompt,
      model: image.model ?? defaults.model,
      size: image.size,
      n: image.n ?? defaults.n ?? 1,
      quality: image.quality ?? defaults.quality,
      format: image.format ?? defaults.format,
      outputCompression: image.output_compression ?? defaults.output_compression,
    };

    if (!job.id) throw new Error(`images[${index}] id becomes empty after slugify`);
    if (!Number.isInteger(job.n) || job.n < 1 || job.n > 10) throw new Error(`${job.id}: n must be integer 1..10`);
    validateChoice('quality', job.quality, ['low', 'medium', 'high', 'auto']);
    validateChoice('format', job.format, ['png', 'jpeg', 'webp']);
    if (job.model !== 'gpt-image-2') throw new Error(`${job.id}: only model gpt-image-2 is supported by this script`);
    validateSize(job.size);

    if (job.outputCompression !== undefined) {
      if (!['jpeg', 'webp'].includes(job.format)) {
        throw new Error(`${job.id}: output_compression only applies to jpeg or webp`);
      }
      if (!Number.isInteger(job.outputCompression) || job.outputCompression < 0 || job.outputCompression > 100) {
        throw new Error(`${job.id}: output_compression must be integer 0..100`);
      }
    }

    return job;
  });
}

function outputPath(outDir, job, itemIndex) {
  const extension = job.format === 'jpeg' ? 'jpg' : job.format;
  const suffix = String(itemIndex + 1).padStart(2, '0');
  return path.join(outDir, `${job.id}-${suffix}.${extension}`);
}

async function generateJob(job, args, apiKey) {
  const plannedPaths = Array.from({ length: job.n }, (_, index) => outputPath(args.out, job, index));
  if (!args.force) {
    const existing = plannedPaths.filter((filePath) => existsSync(filePath));
    if (existing.length > 0) {
      throw new Error(`${job.id}: output exists. Use --force to overwrite: ${existing.join(', ')}`);
    }
  }

  if (args.dryRun) {
    return {
      id: job.id,
      dryRun: true,
      request: {
        model: job.model,
        size: job.size,
        n: job.n,
        quality: job.quality,
        output_format: job.format,
      },
      files: plannedPaths,
    };
  }

  const body = {
    model: job.model,
    prompt: job.prompt,
    size: job.size,
    n: job.n,
    quality: job.quality,
    output_format: job.format,
  };

  if (job.outputCompression !== undefined) {
    body.output_compression = job.outputCompression;
  }

  const response = await fetch(API_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.error?.message ?? response.statusText;
    throw new Error(`${job.id}: OpenAI API error ${response.status}: ${detail}`);
  }

  if (!Array.isArray(payload?.data) || payload.data.length === 0) {
    throw new Error(`${job.id}: OpenAI response did not include data[]`);
  }

  const files = [];
  for (const [index, item] of payload.data.entries()) {
    if (!item.b64_json) throw new Error(`${job.id}: data[${index}] missing b64_json`);
    const filePath = outputPath(args.out, job, index);
    await writeFile(filePath, Buffer.from(item.b64_json, 'base64'));
    files.push(filePath);
  }

  return {
    id: job.id,
    size: job.size,
    quality: job.quality,
    format: job.format,
    files,
  };
}

async function runQueue(jobs, args, apiKey) {
  const results = [];
  let nextIndex = 0;

  async function worker() {
    while (nextIndex < jobs.length) {
      const job = jobs[nextIndex];
      nextIndex += 1;
      results.push(await generateJob(job, args, apiKey));
    }
  }

  const workers = Array.from({ length: Math.min(args.concurrency, jobs.length) }, () => worker());
  await Promise.all(workers);
  return results;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const manifest = await loadManifest(args.manifest);
  const jobs = buildJobs(manifest, args);

  if (!args.dryRun && !process.env.OPENAI_API_KEY) {
    throw new Error('Missing OPENAI_API_KEY. Run this command through its reviewed Secret Bindings profile.');
  }

  await mkdir(args.out, { recursive: true });
  const results = await runQueue(jobs, args, process.env.OPENAI_API_KEY);
  const summaryPath = path.join(args.out, 'generation-results.json');
  const summary = {
    generatedAt: new Date().toISOString(),
    dryRun: args.dryRun,
    manifest: path.resolve(args.manifest),
    results,
  };

  if (!args.dryRun) {
    await writeFile(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
  }

  console.log(JSON.stringify(summary, null, 2));
}

main().catch((error) => {
  console.error(`Error: ${error.message}`);
  process.exit(1);
});
