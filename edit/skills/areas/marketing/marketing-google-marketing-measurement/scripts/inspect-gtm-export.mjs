#!/usr/bin/env node

import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const exportPath = process.argv[2];
if (!exportPath) {
  console.error('Usage: inspect-gtm-export.mjs <container-export.json>');
  process.exit(2);
}

const parsed = JSON.parse(await readFile(resolve(exportPath), 'utf8'));
const version = parsed.containerVersion;
if (!version?.container) {
  throw new Error('Expected a GTM export with containerVersion.container');
}

const builtInTriggerNames = {
  '2147479553': 'All Pages',
  '2147479572': 'Consent Initialization - All Pages',
};

const parameterValue = (tag, key) => tag.parameter?.find((item) => item.key === key)?.value ?? null;
const tags = (version.tag ?? []).map((tag) => ({
  name: tag.name,
  type: tag.type,
  tagId: parameterValue(tag, 'tagId'),
  firingTriggers: (tag.firingTriggerId ?? []).map((id) => ({ id, name: builtInTriggerNames[id] ?? null })),
  consentStatus: tag.consentSettings?.consentStatus ?? null,
}));

const summary = {
  exportFormatVersion: parsed.exportFormatVersion,
  exportTime: parsed.exportTime,
  accountId: version.accountId,
  containerId: version.containerId,
  containerVersionId: version.containerVersionId,
  containerName: version.container.name,
  publicId: version.container.publicId,
  counts: {
    tags: version.tag?.length ?? 0,
    triggers: version.trigger?.length ?? 0,
    variables: version.variable?.length ?? 0,
    builtInVariables: version.builtInVariable?.length ?? 0,
    customTemplates: version.customTemplate?.length ?? 0,
  },
  tags,
  builtInVariables: (version.builtInVariable ?? []).map((item) => item.name),
  customTemplates: (version.customTemplate ?? []).map((item) => ({ name: item.name, templateId: item.templateId })),
};

console.log(JSON.stringify(summary, null, 2));
