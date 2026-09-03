#!/usr/bin/env node

const [command, input, ...rawArgs] = process.argv.slice(2);

function usage() {
  console.log(`Usage:
  campaign-url.mjs build <url> --source <value> --medium <value> --campaign <value> [--content <value>] [--term <value>] [--id <value>]
  campaign-url.mjs parse <url>`);
}

function parseFlags(args) {
  const flags = {};
  for (let index = 0; index < args.length; index += 2) {
    const key = args[index];
    const value = args[index + 1];
    if (!key?.startsWith('--') || value === undefined) {
      throw new Error(`Expected --name value, received ${key ?? '<end>'}`);
    }
    flags[key.slice(2)] = value;
  }
  return flags;
}

function normalizeCampaignValue(value) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/_{2,}/g, '_');
}

if (!command || !input || command === '--help' || command === '-h') {
  usage();
  process.exit(command === '--help' || command === '-h' ? 0 : 2);
}

const url = new URL(input);

if (command === 'build') {
  const flags = parseFlags(rawArgs);
  for (const required of ['source', 'medium', 'campaign']) {
    if (!flags[required]) {
      throw new Error(`Missing required --${required}`);
    }
  }

  const mapping = {
    source: 'utm_source',
    medium: 'utm_medium',
    campaign: 'utm_campaign',
    content: 'utm_content',
    term: 'utm_term',
    id: 'utm_id',
  };

  for (const [flag, parameter] of Object.entries(mapping)) {
    if (flags[flag]) {
      const normalized = normalizeCampaignValue(flags[flag]);
      if (!normalized) throw new Error(`--${flag} must contain a letter or number`);
      url.searchParams.set(parameter, normalized);
    }
  }

  console.log(url.toString());
} else if (command === 'parse') {
  console.log(
    JSON.stringify(
      {
        url: `${url.origin}${url.pathname}`,
        source: url.searchParams.get('utm_source'),
        medium: url.searchParams.get('utm_medium'),
        campaign: url.searchParams.get('utm_campaign'),
        content: url.searchParams.get('utm_content'),
        term: url.searchParams.get('utm_term'),
        id: url.searchParams.get('utm_id'),
      },
      null,
      2,
    ),
  );
} else {
  usage();
  process.exit(2);
}
