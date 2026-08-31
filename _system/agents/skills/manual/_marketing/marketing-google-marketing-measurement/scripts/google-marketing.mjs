#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';

const [command, ...args] = process.argv.slice(2);

function usage() {
  console.log(`Usage:
  google-marketing.mjs validate --manifest <file>
  google-marketing.mjs hash --file <file>
  google-marketing.mjs snapshot --manifest <file> --out <file>
  google-marketing.mjs diff --manifest <file> --snapshot <file>
  google-marketing.mjs apply --manifest <file> [--execute --confirm APPLY-<property-id>-<gtm-public-id>]
  google-marketing.mjs publish --manifest <file> --version <id> [--execute --confirm PUBLISH-<gtm-public-id>-<version>]

Authentication: Application Default Credentials with Analytics Edit and Tag Manager scopes. Tokens are read in memory and never printed.`);
}

function flagsFrom(values) {
  const flags = {};
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (!value.startsWith('--')) throw new Error(`Unexpected argument: ${value}`);
    const key = value.slice(2);
    if (key === 'execute') {
      flags.execute = true;
      continue;
    }
    const next = values[index + 1];
    if (!next || next.startsWith('--')) throw new Error(`Missing value for --${key}`);
    flags[key] = next;
    index += 1;
  }
  return flags;
}

async function readJson(path) {
  return JSON.parse(await readFile(resolve(path), 'utf8'));
}

function validateManifest(manifest) {
  const required = [
    ['googleAnalytics.account.id', manifest.googleAnalytics?.account?.id],
    ['googleAnalytics.property.id', manifest.googleAnalytics?.property?.id],
    ['googleAnalytics.webStream.id', manifest.googleAnalytics?.webStream?.id],
    ['googleAnalytics.webStream.measurementId', manifest.googleAnalytics?.webStream?.measurementId],
    ['tagManager.account.id', manifest.tagManager?.account?.id],
    ['tagManager.container.resourceId', manifest.tagManager?.container?.resourceId],
    ['tagManager.container.publicId', manifest.tagManager?.container?.publicId],
  ];
  const missing = required.filter(([, value]) => !value).map(([name]) => name);
  if (missing.length) throw new Error(`Manifest is missing: ${missing.join(', ')}`);
  if (!String(manifest.googleAnalytics.webStream.measurementId).startsWith('G-')) {
    throw new Error('Measurement ID must start with G-');
  }
  if (!String(manifest.tagManager.container.publicId).startsWith('GTM-')) {
    throw new Error('Public container ID must start with GTM-');
  }
  return manifest;
}

function accessToken() {
  try {
    return execFileSync('gcloud', ['auth', 'application-default', 'print-access-token'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
  } catch {
    throw new Error('No usable Application Default Credentials. Run the documented one-time OAuth setup.');
  }
}

async function requestJson(url, { method = 'GET', body, token }) {
  const response = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${method} ${url} failed (${response.status}): ${text.slice(0, 1000)}`);
  return text ? JSON.parse(text) : {};
}

function gaBase(version, path) {
  return `https://analyticsadmin.googleapis.com/${version}/${path}`;
}

function gtmBase(path) {
  return `https://tagmanager.googleapis.com/tagmanager/v2/${path}`;
}

async function snapshot(manifest) {
  const token = accessToken();
  const propertyId = manifest.googleAnalytics.property.id;
  const streamId = manifest.googleAnalytics.webStream.id;
  const accountId = manifest.tagManager.account.id;
  const containerId = manifest.tagManager.container.resourceId;
  const gaParent = `properties/${propertyId}`;
  const streamPath = `${gaParent}/dataStreams/${streamId}`;
  const gtmContainerPath = `accounts/${accountId}/containers/${containerId}`;

  const [property, stream, retention, enhancedMeasurement, customDimensions, keyEvents, gtmAccount, container, liveVersion] =
    await Promise.all([
      requestJson(gaBase('v1beta', gaParent), { token }),
      requestJson(gaBase('v1beta', streamPath), { token }),
      requestJson(gaBase('v1beta', `${gaParent}/dataRetentionSettings`), { token }),
      requestJson(gaBase('v1alpha', `${streamPath}/enhancedMeasurementSettings`), { token }),
      requestJson(gaBase('v1beta', `${gaParent}/customDimensions`), { token }),
      requestJson(gaBase('v1beta', `${gaParent}/keyEvents`), { token }),
      requestJson(gtmBase(`accounts/${accountId}`), { token }),
      requestJson(gtmBase(gtmContainerPath), { token }),
      requestJson(gtmBase(`${gtmContainerPath}/versions:live`), { token }),
    ]);

  return {
    schemaVersion: 1,
    capturedAt: new Date().toISOString(),
    googleAnalytics: { property, stream, retention, enhancedMeasurement, customDimensions, keyEvents },
    tagManager: { account: gtmAccount, container, liveVersion },
  };
}

function desiredOperations(manifest, observed) {
  const ga = manifest.googleAnalytics;
  const gtm = manifest.tagManager;
  const operations = [
    ['GA4 property name', observed?.googleAnalytics?.property?.displayName, ga.property.desiredName],
    ['GA4 stream name', observed?.googleAnalytics?.stream?.displayName, ga.webStream.desiredName],
    ['GA4 stream URL', observed?.googleAnalytics?.stream?.webStreamData?.defaultUri, ga.webStream.desiredUrl],
    ['GA4 event retention', observed?.googleAnalytics?.retention?.eventDataRetention, `FOURTEEN_MONTHS`],
    ['GTM account name', observed?.tagManager?.account?.name, gtm.account.desiredName],
    ['GTM container name', observed?.tagManager?.container?.name, gtm.container.desiredName],
  ];
  return operations.map(([field, before, after]) => ({ field, before: before ?? null, after, changed: before !== after }));
}

async function apply(manifest, flags) {
  const confirmation = `APPLY-${manifest.googleAnalytics.property.id}-${manifest.tagManager.container.publicId}`;
  const operations = desiredOperations(manifest);
  if (!flags.execute) return { dryRun: true, confirmationRequired: confirmation, operations };
  if (flags.confirm !== confirmation) throw new Error(`Refusing mutation. Pass --confirm ${confirmation}`);

  const token = accessToken();
  const propertyId = manifest.googleAnalytics.property.id;
  const streamId = manifest.googleAnalytics.webStream.id;
  const gaParent = `properties/${propertyId}`;
  const streamPath = `${gaParent}/dataStreams/${streamId}`;
  const accountPath = `accounts/${manifest.tagManager.account.id}`;
  const containerPath = `${accountPath}/containers/${manifest.tagManager.container.resourceId}`;

  await requestJson(`${gaBase('v1beta', gaParent)}?updateMask=displayName`, {
    method: 'PATCH',
    token,
    body: { name: gaParent, displayName: manifest.googleAnalytics.property.desiredName },
  });
  await requestJson(`${gaBase('v1beta', streamPath)}?updateMask=displayName,webStreamData.defaultUri`, {
    method: 'PATCH',
    token,
    body: {
      name: streamPath,
      displayName: manifest.googleAnalytics.webStream.desiredName,
      webStreamData: { defaultUri: manifest.googleAnalytics.webStream.desiredUrl },
    },
  });
  await requestJson(`${gaBase('v1beta', `${gaParent}/dataRetentionSettings`)}?updateMask=eventDataRetention`, {
    method: 'PATCH',
    token,
    body: { name: `${gaParent}/dataRetentionSettings`, eventDataRetention: 'FOURTEEN_MONTHS' },
  });

  const currentAccount = await requestJson(gtmBase(accountPath), { token });
  await requestJson(gtmBase(accountPath), { method: 'PUT', token, body: { ...currentAccount, name: manifest.tagManager.account.desiredName } });
  const currentContainer = await requestJson(gtmBase(containerPath), { token });
  await requestJson(gtmBase(containerPath), {
    method: 'PUT',
    token,
    body: { ...currentContainer, name: manifest.tagManager.container.desiredName },
  });

  const live = await snapshot(manifest);
  const customDimensions = live.googleAnalytics.customDimensions.customDimensions ?? [];
  for (const dimension of manifest.googleAnalytics.desiredCustomDimensions ?? []) {
    if (!customDimensions.some((item) => item.parameterName === dimension.parameterName)) {
      await requestJson(gaBase('v1beta', `${gaParent}/customDimensions`), {
        method: 'POST',
        token,
        body: {
          displayName: dimension.displayName,
          parameterName: dimension.parameterName,
          scope: dimension.scope,
        },
      });
    }
  }
  const keyEvents = live.googleAnalytics.keyEvents.keyEvents ?? [];
  for (const eventName of manifest.googleAnalytics.desiredKeyEvents ?? []) {
    if (!keyEvents.some((item) => item.eventName === eventName)) {
      await requestJson(gaBase('v1beta', `${gaParent}/keyEvents`), {
        method: 'POST',
        token,
        body: { eventName },
      });
    }
  }

  return { dryRun: false, applied: true };
}

async function publish(manifest, flags) {
  if (!flags.version) throw new Error('publish requires --version');
  const confirmation = `PUBLISH-${manifest.tagManager.container.publicId}-${flags.version}`;
  if (!flags.execute) return { dryRun: true, confirmationRequired: confirmation };
  if (flags.confirm !== confirmation) throw new Error(`Refusing publish. Pass --confirm ${confirmation}`);
  const token = accessToken();
  const path = `accounts/${manifest.tagManager.account.id}/containers/${manifest.tagManager.container.resourceId}/versions/${flags.version}:publish`;
  return requestJson(gtmBase(path), { method: 'POST', token });
}

if (!command || command === '--help' || command === '-h') {
  usage();
  process.exit(command ? 0 : 2);
}

const flags = flagsFrom(args);

if (command === 'hash') {
  if (!flags.file) throw new Error('hash requires --file');
  const content = await readFile(resolve(flags.file));
  console.log(createHash('sha256').update(content).digest('hex'));
} else {
  if (!flags.manifest) throw new Error(`${command} requires --manifest`);
  const manifest = validateManifest(await readJson(flags.manifest));

  if (command === 'validate') {
    console.log(JSON.stringify({ valid: true, project: manifest.project }, null, 2));
  } else if (command === 'snapshot') {
    if (!flags.out) throw new Error('snapshot requires --out');
    const value = await snapshot(manifest);
    await mkdir(dirname(resolve(flags.out)), { recursive: true });
    await writeFile(resolve(flags.out), `${JSON.stringify(value, null, 2)}\n`);
    console.log(JSON.stringify({ written: resolve(flags.out), capturedAt: value.capturedAt }, null, 2));
  } else if (command === 'diff') {
    if (!flags.snapshot) throw new Error('diff requires --snapshot');
    const observed = await readJson(flags.snapshot);
    console.log(JSON.stringify(desiredOperations(manifest, observed), null, 2));
  } else if (command === 'apply') {
    console.log(JSON.stringify(await apply(manifest, flags), null, 2));
  } else if (command === 'publish') {
    console.log(JSON.stringify(await publish(manifest, flags), null, 2));
  } else {
    usage();
    process.exit(2);
  }
}
