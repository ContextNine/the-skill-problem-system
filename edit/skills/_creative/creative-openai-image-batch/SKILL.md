---
name: creative-openai-image-batch
description: Generate batches of images with the OpenAI Image API using GPT-Image 2, custom resolutions, and per-image prompts. Use when creating multiple images, website assets, prompt batches, or GPT-Image 2 outputs from a JSON manifest.
---

# Creative · OpenAI Image Batch

## Quick Start

This legacy direct-API helper has no approved schema-v2 Vault run profile yet. Prefer the installed ImageGen capability. If the direct API helper is specifically required, stop and create a reviewed Secret Bindings profile and protected binding before running it; do not source the quarantined Vault env.

After that profile exists, invoke the exact command through Secret Bindings rather than running the script directly:

```bash
cd "$(vault root)"
secret-bindings run <reviewed-profile>
```

The underlying script still supports a credential-free dry run during profile design:

```bash
node _system/agents/edit/skills/_creative/creative-openai-image-batch/scripts/generate-images.mjs --manifest prompts.json --out renders/images --dry-run
```

## Manifest

```json
{
  "defaults": {
    "quality": "medium",
    "format": "png"
  },
  "images": [
    {
      "id": "ctx9-cta",
      "size": "2880x1920",
      "prompt": "Engineering command desk..."
    },
    {
      "id": "ctx9-service-strategy",
      "size": "1024x1280",
      "n": 2,
      "prompt": "Abstract business terrain map..."
    }
  ]
}
```

## Rules

- Env key is `OPENAI_API_KEY`; read `_system/local/env/README.md`. Never add or update the ignored plaintext source.
- Model defaults to `gpt-image-2`.
- Script accepts per-image `id`, `prompt`, `size`, `n`, `quality`, `format`, and `output_compression`.
- Valid `gpt-image-2` sizes need both edges divisible by `16`, max edge `3840`, ratio `<= 3:1`, and total pixels from `655360` to `8294400`.
- For legacy odd sizes, generate nearest valid ratio size, then crop/resize final files separately.
- Use `--force` to overwrite existing files.
- Use `--concurrency N` only when rate limits and cost are understood.

## Commands

```bash
node _system/agents/edit/skills/_creative/creative-openai-image-batch/scripts/generate-images.mjs \
  --manifest prompts.json \
  --out renders/images \
  --quality high \
  --format webp \
  --concurrency 1
```

Outputs are named `<id>-01.<format>` and summarized in `generation-results.json`.
